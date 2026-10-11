#!/usr/bin/env python3
"""Build deterministic log ownership and publishable basis indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

from library import build_catalog


def _portable_file(root: Path, item: dict, label: str) -> Path:
    path_text = item.get("path")
    path = PurePosixPath(path_text) if isinstance(path_text, str) else None
    if path is None or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label}: expected a portable repository path")
    full = root.joinpath(*path.parts).resolve()
    try:
        full.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label}: path escapes repository") from exc
    if not full.is_file():
        raise ValueError(f"{label}: referenced log is missing")
    digest = hashlib.sha256(full.read_bytes()).hexdigest()
    if item.get("sha256") != digest:
        raise ValueError(f"{label}: SHA-256 mismatch")
    return full


def build_log_index(root: Path, cases: list[dict]) -> dict:
    entries = []
    owners = {}
    case_ids = set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise ValueError("calculation records contain a missing or duplicate id")
        case_ids.add(case_id)
        logs = case.get("files", {}).get("logs", [])
        if not isinstance(logs, list):
            raise ValueError(f"{case_id}: files.logs must be a list")
        for item in logs:
            label = f"{case_id}.files.logs"
            _portable_file(root, item, label)
            path = item["path"]
            if path in owners:
                raise ValueError(f"log {path} belongs to multiple calculations")
            owners[path] = case_id
            entries.append({
                "calculation_id": case_id,
                "path": path,
                "sha256": item["sha256"],
                "label": item.get("label") or PurePosixPath(path).name,
            })

    logs_root = root / "data/calculations"
    discovered = {
        path.relative_to(root).as_posix()
        for path in logs_root.rglob("*")
        if path.is_file() and "logs" in path.relative_to(logs_root).parts
    }
    unindexed = sorted(discovered - set(owners))
    if unindexed:
        raise ValueError(f"log files are not indexed: {', '.join(unindexed)}")
    return {
        "schema_version": 1,
        "entries": sorted(entries, key=lambda entry: (entry["calculation_id"], entry["path"])),
    }


def build_release_index(sets: list[dict]) -> dict:
    entries = []
    for item in sets:
        publication = item.get("publication") or {}
        if publication.get("status") != "publishable":
            continue
        files = [
            {"role": file_item["role"], "path": file_item["path"], "sha256": file_item["sha256"]}
            for file_item in item["files"]
            if file_item.get("role") in {"pp", "nao", "for_aux", "abf"}
        ]
        entries.append({
            "set_id": item["id"],
            "element": item["element"],
            "calculation_ids": sorted(publication["calculation_ids"]),
            "files": sorted(files, key=lambda file_item: (file_item["role"], file_item["path"])),
        })
    return {"schema_version": 1, "sets": sorted(entries, key=lambda entry: entry["set_id"])}


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def update_indexes(root: Path, write: bool) -> None:
    catalog = build_catalog(root)
    indexes = {
        "data/log-index.json": build_log_index(root, catalog["calculations"]),
        "data/release-index.json": build_release_index(catalog["basis_sets"]),
    }
    for relative, expected in indexes.items():
        target = root / relative
        content = _json_bytes(expected)
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        elif not target.is_file() or target.read_bytes() != content:
            raise ValueError(f"{relative} is missing or stale; run scripts/build_indexes.py --write")
    print(f"indexes OK: {len(indexes['data/log-index.json']['entries'])} logs, "
          f"{len(indexes['data/release-index.json']['sets'])} publishable basis sets")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write generated indexes")
    mode.add_argument("--check", action="store_true", help="fail when generated indexes are stale")
    args = parser.parse_args()
    update_indexes(args.root, write=not args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
