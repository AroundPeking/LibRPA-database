#!/usr/bin/env python3
"""One-shot migration: backfill ``structure_identity`` for calculation records
that archive an unambiguous structure input (ABACUS ``STRU`` or FHI-aims
``geometry.in``) but predate the fingerprint convention.

The digest and evidence are computed with the same ``library`` helpers the
validator uses, so every written record passes ``structure_identity``
validation without further edits. A record whose archived structure inputs
disagree (for example both a ``STRU`` and a ``geometry.in`` with different
cells) is skipped and reported instead of guessing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library  # noqa: E402


def structure_candidates(root: Path, case: dict) -> list[tuple[dict, str, str, int]]:
    """Return (item, kind, digest, atom_count) for every archived structure input."""
    found: list[tuple[dict, str, str, int]] = []
    for item in case.get("files", {}).get("inputs", []):
        name = PurePosixPath(item["path"]).name.split("__")[-1]
        kind = "STRU" if library._input_name(item, "STRU") else "geometry.in" if name == "geometry.in" else None
        if kind is None:
            continue
        try:
            text = library._payload_bytes(root, item).decode("utf-8")
            digest, atom_count = library._structure_fingerprint(text, kind, case.get("dimension"))
        except (ValueError, UnicodeError):
            continue
        found.append((item, kind, digest, atom_count))
    return found


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    written: list[str] = []
    skipped: list[tuple[str, str]] = []
    for path in sorted((root / "data/calculations").glob("*/*/*/record.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if case.get("structure_identity"):
            continue
        candidates = structure_candidates(root, case)
        digests = {digest for _, _, digest, _ in candidates}
        if not candidates:
            skipped.append((case["id"], "no archived structure input"))
            continue
        if len(digests) > 1:
            skipped.append((case["id"], f"ambiguous: {len(digests)} distinct archived structures"))
            continue
        item, kind, digest, atom_count = candidates[0]
        scale = case.get("computational_scale")
        if isinstance(scale, dict) and scale.get("atom_count") is not None and scale["atom_count"] != atom_count:
            skipped.append((case["id"], f"atom count {scale['atom_count']} != archived {atom_count}"))
            continue
        identity = {"algorithm": library._STRUCTURE_ALGORITHM, "sha256": digest, "evidence": item["path"]}
        rebuilt = {}
        for key, value in case.items():
            rebuilt[key] = value
            if key == "files":
                rebuilt["structure_identity"] = identity
        if "structure_identity" not in rebuilt:
            rebuilt["structure_identity"] = identity
        path.write_text(json.dumps(rebuilt, indent=2) + "\n", encoding="utf-8")
        written.append(case["id"])
    print(f"backfilled: {len(written)}")
    for case_id in sorted(written):
        print(f"  + {case_id}")
    print(f"skipped: {len(skipped)}")
    for case_id, reason in sorted(skipped):
        print(f"  - {case_id}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
