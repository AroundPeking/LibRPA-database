#!/usr/bin/env python3
"""Validate element assets and ABACUS + LibRPA calculation records."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from asset_names import enrich_catalog

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
PUBLICATION_STATES = {"database_only", "review", "publishable", "superseded", "legacy_incomplete"}
INTERMEDIATE_PATH = re.compile(
    r"(?:^|/)(?:tmp|temp|scratch|restart|intermediate|out_wfc|out_chg)(?:/|$)|"
    r"(?:\.tmp|\.part|\.bak|\.wfc|\.cube)$",
    re.IGNORECASE,
)
PROPERTY_CATEGORY = re.compile(r"^[a-z][a-z0-9_]*$")
PROPERTY_STATUSES = {"reported", "validated", "provisional", "failed"}


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
    with full.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != actual:
        _fail(f"{label}: SHA-256 mismatch ({digest} != {actual})")


def _publication(item: dict, label: str) -> dict:
    value = item.get("publication", {})
    if value is None:
        value = {}
    if not isinstance(value, dict):
        _fail(f"{label}.publication: expected an object")
    status = value.get("status", "database_only")
    if status not in PUBLICATION_STATES:
        _fail(f"{label}.publication.status: unsupported status {status!r}")
    return value


def _require_public_source(item: dict, label: str) -> None:
    source = item.get("source")
    if not isinstance(source, dict):
        _fail(f"{label}: publishable basis requires source metadata")
    url = source.get("url")
    if not isinstance(url, str) or not re.match(r"^https?://\S+$", url):
        _fail(f"{label}: publishable basis requires a public source URL")
    if not isinstance(source.get("license"), str) or not source["license"].strip():
        _fail(f"{label}: publishable basis requires a license")
    if source.get("redistribution") != "permitted":
        _fail(f"{label}: redistribution must be explicitly permitted")


def _json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return value == value and abs(value) != float("inf")
    if isinstance(value, list):
        return all(_json_value(entry) for entry in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(entry) for key, entry in value.items())
    return False


def _validate_properties(case: dict, label: str, declared_paths: set[str]) -> None:
    properties = case.get("properties", [])
    if not isinstance(properties, list):
        _fail(f"{label}.properties: expected a list")
    seen = set()
    required_strings = ("key", "category", "label", "method", "unit", "status")
    for index, item in enumerate(properties):
        prop_label = f"{label}.properties[{index}]"
        if not isinstance(item, dict):
            _fail(f"{prop_label}: expected an object")
        for field in required_strings:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                _fail(f"{prop_label}.{field}: expected a non-empty string")
        if not PROPERTY_CATEGORY.fullmatch(item["category"]):
            _fail(f"{prop_label}.category: expected a lowercase slug")
        if item["status"] not in PROPERTY_STATUSES:
            _fail(f"{prop_label}.status: unsupported status {item['status']!r}")
        if "value" not in item or item["value"] is None or not _json_value(item["value"]):
            _fail(f"{prop_label}.value: expected a JSON scalar, array, or object")
        identity = (item["category"], item["key"], item["method"])
        if identity in seen:
            _fail(f"{prop_label}: duplicate property category/key/method")
        seen.add(identity)
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            _fail(f"{prop_label}.evidence: expected a non-empty list of declared files")
        for path in evidence:
            parsed = PurePosixPath(path) if isinstance(path, str) else None
            if (parsed is None or parsed.is_absolute() or ".." in parsed.parts
                    or path not in declared_paths):
                _fail(f"{prop_label}.evidence: path must be a file declared by this calculation")


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
    set_publications = {}
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
        publication = _publication(item, label)
        set_publications[set_id] = publication
        if publication.get("status") == "publishable":
            if not {"pp", "nao", "abf"}.issubset(roles):
                _fail(f"{label}: publishable basis requires PP, physical NAO, and ABF files")
            _require_public_source(item, label)
            linked_cases = publication.get("calculation_ids")
            if not isinstance(linked_cases, list) or not linked_cases:
                _fail(f"{label}: publishable basis requires linked calculations")
        by_id[set_id] = item

    all_case_ids = {case.get("id") for case in cases if isinstance(case.get("id"), str)}
    case_ids = set()
    case_publications = {}
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        check_private_paths(case, label)
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            _fail(f"{label}: missing or duplicate id")
        case_ids.add(case_id)
        publication = _publication(case, label)
        case_publications[case_id] = publication
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
        if not isinstance(files, dict):
            _fail(f"{label}: files must be an object")
        declared_paths = set()
        for group in GROUPS:
            values = files.get(group, [])
            if not isinstance(values, list):
                _fail(f"{label}: files.{group} must be a list")
            for n, file_item in enumerate(values):
                _file(root, file_item, f"{label}.files.{group}[{n}]")
                declared_paths.add(file_item["path"])
                if publication.get("status") == "publishable" and INTERMEDIATE_PATH.search(file_item["path"]):
                    _fail(f"{label}: publishable case contains an intermediate file")

        _validate_properties(case, label, declared_paths)

        if publication.get("status") == "publishable":
            if case.get("status") != "gw_validated":
                _fail(f"{label}: publishable case must be gw_validated")
            for name in ("abacus", "librpa"):
                commit = software[name].get("commit")
                if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
                    _fail(f"{label}: publishable case requires a full {name} commit")
            if not files.get("inputs"):
                _fail(f"{label}: publishable case requires at least one input file")
            if not files.get("results"):
                _fail(f"{label}: publishable case requires at least one final result file")
            linked_sets = publication.get("basis_set_ids")
            if not isinstance(linked_sets, list) or not linked_sets:
                _fail(f"{label}: publishable case requires linked basis sets")
            exact_sets = {entry.get("set_id") for entry in species if entry.get("set_id")}
            if not set(linked_sets).issubset(exact_sets):
                _fail(f"{label}: publishable basis links must match exact species bindings")
            for set_id in linked_sets:
                if set_id not in by_id:
                    _fail(f"{label}: unknown publishable basis set {set_id}")
                if set_publications[set_id].get("status") != "publishable":
                    _fail(f"{label}: linked basis set {set_id} is not publishable")
        recommendation = case.get("recommendation")
        if recommendation is not None:
            if case.get("status") != "gw_validated":
                _fail(f"{label}: recommendation requires a GW-validated case")
            if not recommendation.get("scope") or not recommendation.get("evidence_case_ids"):
                _fail(f"{label}: recommendation needs a narrow scope and evidence")
            if any(ref not in all_case_ids for ref in recommendation["evidence_case_ids"]):
                _fail(f"{label}: recommendation references an unknown case")

    for set_id, publication in set_publications.items():
        if publication.get("status") != "publishable":
            continue
        for case_id in publication["calculation_ids"]:
            if case_id not in case_publications:
                _fail(f"basis set {set_id}: unknown linked calculation {case_id}")
            case_publication = case_publications[case_id]
            if case_publication.get("status") != "publishable" or set_id not in case_publication.get("basis_set_ids", []):
                _fail(f"basis set {set_id}: calculation link is not reciprocal")


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
    return enrich_catalog({
        "schema_version": 1,
        "basis_sets": sets,
        "calculations": cases,
    })


def sync_catalog(root: Path, catalog: dict, write: bool = False) -> None:
    target = root / "database/data.json"
    expected = (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(expected)
        return
    if not target.is_file() or target.read_bytes() != expected:
        raise ValueError("database/data.json is missing or stale; run with --write-catalog")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write-catalog", action="store_true")
    parser.add_argument("--check-catalog", action="store_true")
    args = parser.parse_args()
    catalog = build_catalog(args.root)
    if args.check_catalog and args.write_catalog:
        parser.error("--write-catalog and --check-catalog are mutually exclusive")
    if args.check_catalog:
        sync_catalog(args.root, catalog, write=False)
    if args.write_catalog:
        sync_catalog(args.root, catalog, write=True)
    print(f"library OK: {len(catalog['basis_sets'])} basis sets, {len(catalog['calculations'])} calculations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
