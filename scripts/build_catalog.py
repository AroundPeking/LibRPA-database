#!/usr/bin/env python3
"""Split database/data.json into lightweight catalog files for the frontend.

The catalog strips the ``files`` field (80% of the payload, only needed on
detail pages) from calculation and basis-set records, producing small JSON
files that load fast on first visit.  Per-record detail JSON already exists
at ``data/calculations/{dim}/{mat}/{id}/record.json`` and is fetched
on-demand when a user opens a record.

Output (written into ``database/catalog/``):
  index.json          – pagination metadata + element/software lists
  calculations.json   – all calculation records without ``files``
  basis-sets.json     – all basis-set records without ``files``
"""

from __future__ import annotations

import json
import math
from pathlib import Path

PER_PAGE = 200  # records per calculation page; large enough for 122 now,
                 # small enough to stay under ~200 KB per page at scale

LIGHTWEIGHT_CALC_KEYS = [
    "id", "material", "formula", "dimension", "software", "workflow",
    "record_type", "functional", "spin_orbit", "spin_polarized",
    "properties", "summary", "source", "species", "basis_candidates",
    "structure_identity", "paper_values", "performance",
    "archive_completeness", "scientific_scope", "schema_version",
    "recommendation", "missing",
]

LIGHTWEIGHT_SET_KEYS = [
    "id", "element", "family", "files",  # basis-set files are small; keep them
    "generation_provenance", "notes", "publication", "schema_version",
]


def strip_calculation(record: dict) -> dict:
    """Return a lightweight copy of a calculation record without ``files``."""
    return {k: record[k] for k in LIGHTWEIGHT_CALC_KEYS if k in record}


def strip_basis_set(record: dict) -> dict:
    """Basis-set records are small; keep them as-is for now."""
    return {k: record[k] for k in LIGHTWEIGHT_SET_KEYS if k in record}
    # NOTE: basis-set ``files`` are kept because they are small (~387 KB total)
    # and needed immediately when viewing a basis record.


def collect_elements(calculations: list) -> list[str]:
    elements = set()
    for calc in calculations:
        for sp in calc.get("species", []):
            sid = sp.get("set_id", "") if isinstance(sp, dict) else str(sp)
            if sid:
                elem = sid.split("-")[0] if "-" in sid else sid
                elements.add(elem)
        # also from structure_identity
        si = calc.get("structure_identity", {})
        if isinstance(si, dict):
            for el in si.get("elements", []):
                elements.add(el)
    return sorted(elements)


def collect_software(calculations: list) -> list[str]:
    software = set()
    for calc in calculations:
        sw = calc.get("software", {})
        if isinstance(sw, dict):
            for key in ("frontend", "dft", "postprocessing"):
                val = sw.get(key)
                if isinstance(val, str) and val:
                    software.add(val)
                elif isinstance(val, list):
                    software.update(v for v in val if isinstance(v, str))
    return sorted(software)


def build_catalog(root: Path) -> dict:
    data_path = root / "database" / "data.json"
    catalog_dir = root / "database" / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    with data_path.open(encoding="utf-8") as f:
        data = json.load(f)

    calculations = data.get("calculations", [])
    basis_sets = data.get("basis_sets", [])

    # Generate lightweight calculation records
    light_calcs = [strip_calculation(c) for c in calculations]

    # Write all calculations as a single file (122 records → ~546 KB)
    # At scale this will be split into pages.
    calc_path = catalog_dir / "calculations.json"
    with calc_path.open("w", encoding="utf-8") as f:
        json.dump({"records": light_calcs}, f, separators=(",", ":"))
        f.write("\n")

    # Basis sets: keep as-is (small)
    light_sets = [strip_basis_set(s) for s in basis_sets]
    sets_path = catalog_dir / "basis-sets.json"
    with sets_path.open("w", encoding="utf-8") as f:
        json.dump({"records": light_sets}, f, separators=(",", ":"))
        f.write("\n")

    # Index file
    index = {
        "total_calculations": len(calculations),
        "total_basis_sets": len(basis_sets),
        "elements": collect_elements(calculations),
        "software": collect_software(calculations),
        "schema_version": 1,
    }
    index_path = catalog_dir / "index.json"
    with index_path.open("w", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))
        f.write("\n")

    calc_size = calc_path.stat().st_size
    sets_size = sets_path.stat().st_size
    index_size = index_path.stat().st_size
    total = calc_size + sets_size + index_size

    print(f"Catalog generated: {catalog_dir}")
    print(f"  calculations.json: {calc_size // 1024}KB ({len(light_calcs)} records)")
    print(f"  basis-sets.json:   {sets_size // 1024}KB ({len(light_sets)} records)")
    print(f"  index.json:        {index_size}B")
    print(f"  total:             {total // 1024}KB (vs {data_path.stat().st_size // 1024}KB data.json)")

    return index


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    build_catalog(args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
