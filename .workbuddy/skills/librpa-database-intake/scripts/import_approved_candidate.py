#!/usr/bin/env python3
"""Apply a hash-bound import plan only with a matching explicit approval receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def target_path(repo: Path, value: str) -> Path:
    relative = PurePosixPath(value) if isinstance(value, str) else None
    if relative is None or relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"unsafe repository target: {value!r}")
    target = repo.joinpath(*relative.parts).resolve()
    if not target.is_relative_to(repo):
        raise ValueError(f"target escapes repository: {value}")
    return target


def source_bytes(value: str, expected: str) -> bytes:
    path = Path(value)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"source is missing or a symlink: {value}")
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError(f"source SHA-256 changed: {value}")
    return data


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    plan = load_json(Path(args.plan))
    approval = load_json(Path(args.approval))
    if plan.get("schema_version") != 1 or approval.get("schema_version") != 1:
        raise ValueError("unsupported plan or approval schema")
    candidate = plan.get("candidate_sha256")
    if (approval.get("approved") is not True or approval.get("candidate_sha256") != candidate
            or not isinstance(approval.get("user_statement"), str) or not approval["user_statement"].strip()):
        raise ValueError("matching explicit user approval receipt is required")
    writes = []
    for item in plan.get("copies", []):
        if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
            raise ValueError("invalid copy entry")
        writes.append({"target": target_path(repo, item.get("target")),
                       "data": source_bytes(item.get("source"), item["sha256"]),
                       "mode": "immutable", "expected_sha256": None})
    for item in plan.get("json_writes", []):
        if not isinstance(item, dict) or "content" not in item:
            raise ValueError("invalid JSON write entry")
        expected = item.get("expected_sha256")
        if expected is not None and (not isinstance(expected, str) or len(expected) != 64):
            raise ValueError("JSON expected_sha256 must be a lowercase SHA-256 or null")
        writes.append({"target": target_path(repo, item.get("target")),
                       "data": canonical_json(item["content"]),
                       "mode": "atomic_json", "expected_sha256": expected})
    targets = [item["target"] for item in writes]
    if len(set(targets)) != len(targets):
        raise ValueError("duplicate write target")
    for item in writes:
        path, data = item["target"], item["data"]
        if path.is_symlink():
            raise ValueError(f"target is a symlink: {path}")
        if item["mode"] == "immutable" and path.exists() and (not path.is_file() or path.read_bytes() != data):
            raise ValueError(f"immutable target collision with different bytes: {path}")
        if item["mode"] == "atomic_json" and path.exists():
            if not path.is_file() or digest(path.read_bytes()) != item["expected_sha256"]:
                raise ValueError(f"JSON target does not match expected pre-write SHA-256: {path}")
    if not args.apply:
        print(json.dumps({"approved_candidate": candidate, "write_count": len(writes), "mode": "dry-run"}, indent=2))
        return
    with tempfile.TemporaryDirectory(prefix=".intake-stage-", dir=repo) as stage_name:
        stage = Path(stage_name)
        staged = []
        for index, item in enumerate(writes):
            temp = stage / str(index)
            temp.write_bytes(item["data"])
            staged.append({**item, "temp": temp})
        for item in plan.get("copies", []):
            source_bytes(item["source"], item["sha256"])
        for item in staged:
            target, temp, data = item["target"], item["temp"], item["data"]
            if item["mode"] == "immutable" and target.exists():
                if target.read_bytes() != data:
                    raise ValueError(f"immutable target changed before apply: {target}")
                continue
            if item["mode"] == "atomic_json" and target.exists():
                if target.is_symlink() or digest(target.read_bytes()) != item["expected_sha256"]:
                    raise ValueError(f"JSON target changed before apply: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if item["mode"] == "atomic_json":
                os.replace(temp, target)
                continue
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(temp.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                target.unlink(missing_ok=True)
                raise
    print(json.dumps({"approved_candidate": candidate, "write_count": len(writes), "mode": "applied"}, indent=2))


if __name__ == "__main__":
    main()
