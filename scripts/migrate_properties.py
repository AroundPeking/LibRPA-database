#!/usr/bin/env python3
"""Migrate legacy calculation gap summaries into evidence-linked properties."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

RESULT_PATTERNS = {
    "PBE": re.compile(r"(?:^|[^a-z0-9])(?:ks|pbe|dft)(?:[^a-z0-9]|$)", re.IGNORECASE),
    "EXX": re.compile(r"(?:^|[^a-z0-9])exx(?:[^a-z0-9]|$)", re.IGNORECASE),
    "G0W0": re.compile(r"(?:^|[^a-z0-9])gw(?:[^a-z0-9]|$)", re.IGNORECASE),
    "GW path": re.compile(r"(?:^|[^a-z0-9])gw(?:[^a-z0-9]|$)", re.IGNORECASE),
}
IGNORED_NAMES = ("manifest", "provenance", "receipt", "audit", "eigenvector", "eigenvalue")


def _result_evidence(record: dict, method: str) -> str:
    candidates = []
    for item in record.get("files", {}).get("results", []):
        path = item.get("path", "")
        name = f"{item.get('label', '')} {Path(path).name}"
        lowered = name.lower()
        if any(part in lowered for part in IGNORED_NAMES):
            continue
        if RESULT_PATTERNS[method].search(name):
            is_band_table = bool(re.search(r"band(?:s|_|\b)", lowered))
            has_data_extension = bool(re.search(r"\.(?:dat|txt|csv)(?:\s|$)", lowered))
            candidates.append((not is_band_table, not has_data_extension, path))
    if not candidates:
        raise ValueError(f"{record.get('id', '<unknown>')}: no {method} result file for a legacy property")
    return sorted(candidates)[0][2]


def _property(record: dict, key: str, label: str, method: str, value: object,
              summary: dict, evidence_method: str, summary_key: str) -> dict:
    evidence = _result_evidence(record, evidence_method)
    status = "validated" if record.get("status") == "gw_validated" else "reported"
    return {
        "key": key,
        "category": "electronic",
        "label": label,
        "method": method,
        "value": value,
        "unit": summary.get("unit") or "eV",
        "status": status,
        "source_summary_key": summary_key,
        "evidence": [evidence],
    }


def _same_value(left: object, right: object) -> bool:
    if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
    return left == right


def migrate_record(record: dict) -> dict:
    result = dict(record)
    summary = record.get("summary") or {}
    properties = list(record.get("properties", []))

    def add(item: dict) -> None:
        identity = (item["category"], item["key"], item["method"])
        for index, existing in enumerate(properties):
            if not isinstance(existing, dict) or (existing.get("category"), existing.get("key"), existing.get("method")) != identity:
                continue
            # Equal numeric values do not establish migration ownership. Unmarked
            # contributions and reviewed statuses must never be silently overwritten.
            source_owned = existing.get("source_summary_key") == item["source_summary_key"]
            if source_owned and existing.get("status") == "reported":
                updated = dict(existing)
                if updated.get("definition") in (summary.get("gap_definition"), summary.get("observable")):
                    updated.pop("definition", None)
                updated.update(item)
                properties[index] = updated
            return
        properties.append(item)

    dft_key = "dft_gap_ev" if summary.get("dft_gap_ev") is not None else "pbe_gap_ev"
    dft_value = summary.get(dft_key)
    if dft_value is not None:
        add(_property(record, "band_gap", "Band gap", "PBE", dft_value, summary, "PBE", dft_key))
    if summary.get("exx_gap_ev") is not None:
        add(_property(record, "band_gap", "Band gap", "EXX", summary["exx_gap_ev"], summary, "EXX", "exx_gap_ev"))

    observable = str(summary.get("observable", "")).lower()
    gw_method = "GW path" if "path" in observable else "G0W0"
    if summary.get("gw_gap_ev") is not None:
        add(_property(record, "band_gap", "Band gap", gw_method, summary["gw_gap_ev"], summary, gw_method, "gw_gap_ev"))

    summary_value = summary.get("value")
    if (summary_value is not None and "gap" in observable
            and any(term in observable for term in ("gw", "g0w0"))
            and summary.get("unit") == "eV"):
        value_method = gw_method
        already_mapped = any(item.get("method") == value_method and _same_value(item.get("value"), summary_value)
                             for item in properties if isinstance(item, dict))
        has_summary_row = any(item.get("key") == "summary_value" and item.get("method") == value_method
                              for item in properties if isinstance(item, dict))
        if has_summary_row or not already_mapped:
            label = str(summary.get("observable") or "Reported gap")
            add(_property(record, "summary_value", label, value_method, summary_value, summary, value_method, "value"))

    result["properties"] = properties
    return result


def migrate(root: Path, write: bool) -> int:
    changed = 0
    for path in sorted((root / "data/calculations").glob("*/*/*/record.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        updated = migrate_record(record)
        if updated != record:
            changed += 1
            if write:
                path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write", action="store_true", help="write migrated calculation records")
    args = parser.parse_args()
    changed = migrate(args.root, write=args.write)
    if args.write:
        print(f"properties migrated: {changed} calculation records updated")
    else:
        print(f"properties migration preview: {changed} calculation records would change; pass --write to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
