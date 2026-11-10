#!/usr/bin/env python3
"""Give every basis set the three facts a reader can act on.

An element set is currently identified by a hash-suffixed id::

    Si-SG15-e11ce28df010

That answers "which record is this" and nothing else. A physicist choosing a
basis wants to know how many electrons the pseudopotential keeps, how large the
orbital and auxiliary bases are, and what calculations already used them:

    Si: 4 valence electrons, 3s3p2d (22 functions per atom),
        397 auxiliary functions per atom.
        Used by 2 calculations: Si GW gap 1.06 eV; SiC GW gap 2.26 eV.

The facts are read from the archived payload bytes, not from the recorded
``dimensions``, because the two disagree: 60 auxiliary bases in this library
omit the J and K channels that their own file header lists, so the recorded
Si-SG15 auxiliary dimension is 365 while the file contains 397. The label
describes the file, since the file is what a calculation opens.

Every field written here is derived and recomputable; nothing is hand-entered,
so ``--check`` can prove the catalog is in sync.

    python3 scripts/basis_labels.py --check
    python3 scripts/basis_labels.py --write
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]

DEGENERACY = {"S": 1, "P": 3, "D": 5, "F": 7, "G": 9, "H": 11, "I": 13, "J": 15, "K": 17}
_ANGULAR_ORDER = list(DEGENERACY)
_CHANNEL = re.compile(r"Number of ([A-Z])orbital\s*-->\s*(\d+)")
_Z_VALENCE = re.compile(r'z_valence\s*=\s*"?\s*([0-9.]+)')

LABEL_FIELD = "label"

# A basis is judged by what it produced. A GW gap is the headline when the
# record has one; otherwise an RPA cohesive energy; a DFT-only record has no
# headline, because quoting a PBE gap next to GW numbers would mislead.
HEADLINE_PROPERTIES: tuple[tuple[str, frozenset[str]], ...] = (
    ("band_gap", frozenset({"G0W0", "GW", "QSGW"})),
    ("rpa_cohesive_energy", frozenset({"RPA"})),
)
_HEADLINE_PHRASE = {
    "band_gap": "GW gap",
    "rpa_cohesive_energy": "RPA cohesive energy",
}


class LabelError(ValueError):
    """Raised when a payload cannot supply a fact the label claims."""


def valence_electrons(path: Path) -> int | float | None:
    """Read ``z_valence`` from a UPF pseudopotential, or return None."""
    text = path.read_text(errors="replace")[:65536]
    match = _Z_VALENCE.search(text)
    if match is None:
        return None
    value = float(match.group(1))
    if not math.isfinite(value) or value <= 0:
        return None
    return int(value) if value == int(value) else value


def channels(path: Path) -> dict[str, int]:
    """Read the per-l radial channel counts from an .orb or .abfs header."""
    text = path.read_text(errors="replace")[:65536]
    found = {letter: int(count) for letter, count in _CHANNEL.findall(text)}
    if not found:
        raise LabelError(f"{path.name}: no angular-momentum channels in the header")
    return {letter: found[letter] for letter in _ANGULAR_ORDER if letter in found}


def dimension(counts: Mapping[str, int]) -> int:
    return sum(count * DEGENERACY[letter] for letter, count in counts.items())


def shells(counts: Mapping[str, int]) -> str:
    return "".join(f"{count}{letter.lower()}" for letter, count in counts.items())


def headline(record: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the record's headline measurement, if it has one."""
    for key, methods in HEADLINE_PROPERTIES:
        for item in record.get("properties") or []:
            if not isinstance(item, dict) or item.get("key") != key:
                continue
            method = str(item.get("method") or "")
            if method.upper() not in methods:
                continue
            value = item.get("value")
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            unit = str(item.get("unit") or "")
            return {
                "record_id": record.get("id"),
                "material": record.get("material") or record.get("formula"),
                "formula": record.get("formula"),
                "dimension": record.get("dimension"),
                "kind": key,
                "method": method,
                "value": float(value),
                "unit": unit,
                "text": f"{_HEADLINE_PHRASE[key]} {value:.2f} {unit}".strip(),
            }
    return None


def uses_by_set(records: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Invert ``species[].set_id`` into per-set lists of linked calculations."""
    uses: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        result = headline(record)
        entry = {
            "record_id": record.get("id"),
            "material": record.get("material"),
            "formula": record.get("formula"),
            "dimension": record.get("dimension"),
            "result": result["text"] if result else None,
        }
        for species in record.get("species") or []:
            if not isinstance(species, dict):
                continue
            set_id = species.get("set_id")
            if set_id:
                uses.setdefault(set_id, []).append(dict(entry))
    for values in uses.values():
        values.sort(key=lambda item: (item["result"] is None, str(item.get("record_id"))))
    return uses


def sentence(element: str, valence, orbital, auxiliary, uses) -> str:
    """The one line a user reads instead of the id."""
    pieces: list[str] = []
    if valence is not None:
        pieces.append(f"{valence} valence electrons")
    if orbital:
        pieces.append(f"{orbital['shells']}, {orbital['dimension_per_atom']} functions per atom")
    if auxiliary:
        pieces.append(f"{auxiliary['dimension_per_atom']} auxiliary functions per atom")
    elif orbital:
        pieces.append("no auxiliary basis")
    head = f"{element}: " + ", ".join(pieces) if pieces else f"{element}: no size information"
    if uses:
        named = "; ".join(
            f"{(use.get('formula') or use.get('material') or use.get('record_id'))}"
            + (f" {use['result']}" if use.get("result") else "")
            for use in uses[:3]
        )
        tail = f"{len(uses)} calculation{'s' if len(uses) != 1 else ''}: {named}"
        tail = tail[:1].upper() + tail[1:]
    else:
        tail = "No calculation in the archive has used it yet"
    return f"{head}. {tail}."


def payload_facts(root: Path, item: Mapping[str, Any]) -> dict[str, Any]:
    """Read size facts for one payload straight from its bytes."""
    path = root / item["path"]
    role = item.get("role")
    if role == "pp":
        value = valence_electrons(path)
        return {"valence_electrons": value}
    counts = channels(path)
    return {
        "channels": counts,
        "shells": shells(counts),
        "dimension_per_atom": dimension(counts),
    }


def label_for_set(root: Path, basis: Mapping[str, Any], uses) -> dict[str, Any]:
    """Build the derived label block for one element set."""
    payloads = {item.get("role"): item for item in basis.get("files") or []}
    orbital = auxiliary = None
    valence = None
    if "pp" in payloads:
        valence = valence_electrons(root / payloads["pp"]["path"])
    if "nao" in payloads:
        counts = channels(root / payloads["nao"]["path"])
        orbital = {
            "shells": shells(counts),
            "channels": counts,
            "dimension_per_atom": dimension(counts),
        }
    if "abf" in payloads:
        counts = channels(root / payloads["abf"]["path"])
        auxiliary = {
            "shells": shells(counts),
            "channels": counts,
            "dimension_per_atom": dimension(counts),
        }
    return {
        "schema_version": 1,
        "element": basis.get("element"),
        "valence_electrons": valence,
        "orbital": orbital,
        "auxiliary": auxiliary,
        "uses": list(uses),
        "sentence": sentence(basis.get("element"), valence, orbital, auxiliary, uses),
    }


def build_labels(catalog: Mapping[str, Any], root: Path = ROOT) -> dict[str, Any]:
    """Return a copy of ``catalog`` with every basis set labelled."""
    result = json.loads(json.dumps(catalog))
    uses = uses_by_set(result.get("calculations") or [])
    for basis in result.get("basis_sets") or []:
        roles = {item.get("role") for item in basis.get("files") or []}
        if not roles & {"pp", "nao"}:
            # FHI-aims species defaults and other non-OML roles carry no payload
            # facts; a label claiming sizes for them would be fabricated.
            continue
        linked = uses.get(basis.get("id"), [])
        basis[LABEL_FIELD] = label_for_set(root, basis, linked)
        # ``used_by`` was maintained by hand at intake time and covers 30 of the
        # 76 sets that records actually reference. The records are the authority,
        # so the list is rebuilt from them; a set nothing links to keeps its
        # recorded list rather than losing history the records cannot express.
        if linked:
            basis["used_by"] = sorted(
                {entry["record_id"] for entry in linked if entry.get("record_id")}
            )
    return result


def load_catalog(root: Path) -> dict[str, Any]:
    path = root / "database" / "data.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true", help="rewrite database/data.json")
    parser.add_argument("--check", action="store_true", help="fail when the catalog is stale")
    parser.add_argument(
        "--report", type=Path, default=None, help="write a summary JSON to this path"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    catalog = load_catalog(root)
    labelled = build_labels(catalog, root)

    stats = {"sets": 0, "with_valence": 0, "with_orbital": 0, "with_auxiliary": 0, "with_uses": 0}
    for basis in labelled.get("basis_sets") or []:
        label = basis.get(LABEL_FIELD)
        if not label:
            continue
        stats["sets"] += 1
        stats["with_valence"] += bool(label.get("valence_electrons"))
        stats["with_orbital"] += bool(label.get("orbital"))
        stats["with_auxiliary"] += bool(label.get("auxiliary"))
        stats["with_uses"] += bool(label.get("uses"))

    if args.write:
        target = root / "database" / "data.json"
        payload = (json.dumps(labelled, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        target.write_bytes(payload)
        print(f"labeled {stats['sets']} basis sets in {target}")
    elif args.check:
        if json.dumps(catalog, sort_keys=True) == json.dumps(labelled, sort_keys=True):
            print(f"basis labels up to date ({stats['sets']} sets)")
        else:
            print("basis labels are missing or stale; run with --write")
            return 1
    else:
        print(json.dumps(stats, indent=2))

    if args.report:
        args.report.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
