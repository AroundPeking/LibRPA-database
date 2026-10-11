#!/usr/bin/env python3
"""Validate element assets and ABACUS + LibRPA calculation records."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
STATUSES = {
    "gw_validated", "gw_diagnostic", "path_diagnostic", "pbe_only",
    "generation_only", "failed", "pending",
}
GROUPS = {"inputs", "results", "logs", "figures"}
PRIVATE_PATH = re.compile(
    r"(?:/" + r"Users/|/" + r"home/[A-Za-z0-9_.-]+|/work[0-9]/|/scratch/|/private/var/|file:" + r"//|ssh:" + r"//)"
)


def _fail(message: str) -> None:
    raise ValueError(message)


def _file(root: Path, item: dict, label: str) -> None:
    path_text = item.get("path")
    path = PurePosixPath(path_text) if isinstance(path_text, str) else None
    if path is None or path.is_absolute() or ".." in path.parts:
        _fail(f"{label}: expected a portable repository path")
    full = root.joinpath(*path.parts).resolve()
    try:
        full.relative_to(root.resolve())
    except ValueError:
        _fail(f"{label}: file is missing or escapes the repository")
    if not full.is_file():
        _fail(f"{label}: file is missing or escapes the repository")
    digest = item.get("sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        _fail(f"{label}: expected lowercase SHA-256")
    actual = hashlib.sha256(full.read_bytes()).hexdigest()
    if digest != actual:
        _fail(f"{label}: SHA-256 mismatch ({digest} != {actual})")


def validate(root: Path, sets: list[dict], cases: list[dict]) -> None:
    def check_private_paths(value: object, label: str) -> None:
        if isinstance(value, str) and PRIVATE_PATH.search(value):
            _fail(f"{label}: private path or host in public metadata")
        if isinstance(value, dict):
            for key, nested in value.items():
                check_private_paths(nested, f"{label}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                check_private_paths(nested, f"{label}[{index}]")

    by_id = {}
    for index, item in enumerate(sets):
        label = f"sets[{index}]"
        check_private_paths(item, label)
        set_id, element = item.get("id"), item.get("element")
        if not isinstance(set_id, str) or not set_id or set_id in by_id:
            _fail(f"{label}: missing or duplicate id")
        if not isinstance(element, str) or not element:
            _fail(f"{label}: missing element")
        if not isinstance(item.get("files"), list) or not item["files"]:
            _fail(f"{label}: files must be a non-empty list")
        roles = set()
        for n, file_item in enumerate(item["files"]):
            _file(root, file_item, f"{label}.files[{n}]")
            roles.add(file_item.get("role"))
        if not roles.intersection({"pp", "nao", "abf"}):
            _fail(f"{label}: no basis payload is registered")
        by_id[set_id] = item

    case_ids = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        check_private_paths(case, label)
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            _fail(f"{label}: missing or duplicate id")
        case_ids.add(case_id)
        if case.get("dimension") not in {"2d", "3d"}:
            _fail(f"{label}: dimension must be 2d or 3d")
        if case.get("status") not in STATUSES:
            _fail(f"{label}: unsupported status")
        species = case.get("species")
        if not isinstance(species, list):
            _fail(f"{label}: species must be a list")
        # A historical band record may be useful before its exact production
        # STRU/PP/NAO/ABF binding has been audited.  It must carry an explicit
        # missing-evidence note so an empty list cannot look like a complete
        # calculation record.
        if not species and not case.get("missing"):
            _fail(f"{label}: empty species requires an explicit missing-evidence note")
        for entry in species:
            set_id = entry.get("set_id")
            if set_id is None:
                continue
            if set_id not in by_id:
                _fail(f"{label}: unknown basis set {set_id}")
            if by_id[set_id]["element"] != entry.get("element"):
                _fail(f"{label}: element does not match basis set {set_id}")
        candidates = case.get("basis_candidates", [])
        if not isinstance(candidates, list):
            _fail(f"{label}: basis_candidates must be a list")
        for n, entry in enumerate(candidates):
            if not isinstance(entry, dict):
                _fail(f"{label}.basis_candidates[{n}]: expected an object")
            set_id = entry.get("set_id")
            if set_id not in by_id:
                _fail(f"{label}: unknown candidate basis set {set_id}")
            if by_id[set_id]["element"] != entry.get("element"):
                _fail(f"{label}: candidate element does not match basis set {set_id}")
            if not entry.get("scope"):
                _fail(f"{label}.basis_candidates[{n}]: scope is required")
        software = case.get("software", {})
        for name in ("abacus", "librpa"):
            app = software.get(name)
            if not isinstance(app, dict):
                _fail(f"{label}: software.{name} must be an object")
            commit = app.get("commit")
            if commit is not None and (not isinstance(commit, str) or not COMMIT.fullmatch(commit)):
                _fail(f"{label}: software.{name}.commit must be a full commit or null")
        files = case.get("files", {})
        for group in GROUPS:
            values = files.get(group, [])
            if not isinstance(values, list):
                _fail(f"{label}: files.{group} must be a list")
            for n, file_item in enumerate(values):
                _file(root, file_item, f"{label}.files.{group}[{n}]")
        recommendation = case.get("recommendation")
        if recommendation is not None:
            if case.get("status") != "gw_validated":
                _fail(f"{label}: recommendation requires a GW-validated case")
            if not recommendation.get("scope") or not recommendation.get("evidence_case_ids"):
                _fail(f"{label}: recommendation needs a narrow scope and evidence")
            if any(ref not in case_ids and ref != case_id for ref in recommendation["evidence_case_ids"]):
                _fail(f"{label}: recommendation references an unknown case")


def load_records(root: Path) -> tuple[list[dict], list[dict]]:
    sets, cases = [], []
    for path in sorted((root / "data/elements").glob("*/sets/*/set.json")):
        sets.append(json.loads(path.read_text(encoding="utf-8")))
    for path in sorted((root / "data/calculations").glob("*/*/*/record.json")):
        cases.append(json.loads(path.read_text(encoding="utf-8")))
    return sets, cases


def build_catalog(root: Path) -> dict:
    sets, cases = load_records(root)
    validate(root, sets, cases)
    return {
        "schema_version": 1,
        "basis_sets": sets,
        "calculations": cases,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write-catalog", action="store_true")
    args = parser.parse_args()
    catalog = build_catalog(args.root)
    if args.write_catalog:
        target = args.root / "database/data.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"library OK: {len(catalog['basis_sets'])} basis sets, {len(catalog['calculations'])} calculations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
