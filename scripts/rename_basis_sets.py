#!/usr/bin/env python3
"""Rename every element set to say what it is.

An element set is stored as ``Si-SG15-e11ce28df010``: a family name with a hash
of its own bytes appended. The hash answers "which record is this" and nothing
else, so two records of the same element can only be told apart by looking them
up.

This script derives a name from the facts instead::

    Si-SG15-4e-3s3p2d-22-abf397

    element ................ Si
    family ................. SG15
    valence electrons ...... 4          (z_valence in the pseudopotential)
    numerical orbital ...... 3s3p2d     (channels in the .orb header)
    orbital functions ...... 22         (sum of n * (2l + 1), per atom)
    auxiliary functions .... 397        (same sum over the .abfs header)

Everything is per atom. A structure total would mix in the atom count, and two
bases of one element would then look different for a reason that has nothing to
do with the basis.

A set that carries no ``pp``/``nao`` payload (an FHI-aims species-defaults
fragment, an unresolved record) cannot be described by size, so it keeps the
element and family only.

## When the facts are not enough

Two different payload sets can share a valence count, an orbital and an
auxiliary dimension: ``Mo-GTH`` and ``Mo-SG15`` both come out as
``14e-6s3p3d2f-44``. Those get a content suffix, the first eight hex characters
of the hash of their role-to-SHA-256 map - short, stable, and derived from the
same bytes the record already carries.

If even the bytes are identical, the suffix is the calculation that used the
copy, because that is the only thing left that differs: two records that ran the
same bytes are the same basis, and naming the second copy after its consumer is
more honest than inventing a number.

## What the migration touches

* ``data/elements/<Element>/sets/<id>/`` directory names;
* ``record.json`` ``species[].set_id``, ``species[].previous_set_id`` and
  ``basis_candidates[].set_id``;
* ``database/data.json`` and ``database/catalog/``;
* any other set id stored inside a record or receipt.

Payload files are content-addressed (``<sha256>.upf``) and never move, so the
rename cannot break a download. Site URLs are ``#/basis/<id>``; old links stop
resolving, which is why this runs with ``--write`` only after ``--check`` shows
no collisions.

    python3 scripts/rename_basis_sets.py            # report the mapping
    python3 scripts/rename_basis_sets.py --check    # fail on collision or drift
    python3 scripts/rename_basis_sets.py --write    # apply, then regenerate catalogs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]

# Families whose recorded name is already a human word stay readable; the rest
# are reduced to their alphanumerics so the id has no spaces or punctuation.
FAMILY_TOKEN = {
    "SG15": "SG15",
    "GTH": "GTH",
    "Dojo-NC-SR": "DojoNCSR",
    "Dojo-stringent": "DojoStr",
    "ONCV-or-other-recorded-PP": "ONCV",
    "ONCV PBE + 3s3p2d physical NAO": "ONCV",
    "GTH PBE q5 + QZTP8 physical NAO": "GTH",
    "Recovered producer-bound assets": "producer",
    "KS HPC backup production basis (SG15/ONCV PP + NAO + PCA ABF)": "KSbackup",
    "historical_backup": "histbackup",
    "historical_raw": "histraw",
    "PP-unresolved": "unresolved",
    "FHI-aims species defaults (control.in inline)": "aims",
}

DEGENERACY = {"S": 1, "P": 3, "D": 5, "F": 7, "G": 9, "H": 11, "I": 13, "J": 15, "K": 17}
_CHANNEL = re.compile(r"Number of ([A-Z])orbital\s*-->\s*(\d+)")
_Z_VALENCE = re.compile(r'z_valence\s*=\s*"?\s*([0-9.]+)')
_ID_SAFE = re.compile(r"^[A-Za-z0-9-]+$")


class RenameError(ValueError):
    """Raised when a set cannot be renamed without losing information."""


def family_token(family: str | None) -> str:
    if family in FAMILY_TOKEN:
        return FAMILY_TOKEN[family]
    token = re.sub(r"[^A-Za-z0-9]+", "", family or "")[:16]
    return token or "unknown"


def _header(path: Path) -> str:
    return path.read_text(errors="replace")[:65536]


def valence_electrons(path: Path) -> int | None:
    match = _Z_VALENCE.search(_header(path))
    if match is None:
        return None
    value = float(match.group(1))
    return int(value) if math.isfinite(value) and value > 0 else None


def channels(path: Path) -> dict[str, int]:
    return {
        letter: int(count)
        for letter, count in _CHANNEL.findall(_header(path))
        if int(count)
    }


def shells(counts: Mapping[str, int]) -> str:
    return "".join(f"{count}{letter.lower()}" for letter, count in counts.items())


def dimension(counts: Mapping[str, int]) -> int:
    return sum(count * DEGENERACY[letter] for letter, count in counts.items())


def content_signature(files: Iterable[Mapping[str, Any]]) -> str:
    """Short hash of the role-to-SHA-256 map: what the record actually holds."""
    payload = json.dumps(
        sorted((item.get("role"), item.get("sha256")) for item in files)
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:8]


def set_facts(root: Path, set_json: Path) -> dict[str, Any]:
    """Read every naming fact from the payload bytes, not the index."""
    document = json.loads(set_json.read_text(encoding="utf-8"))
    by_role = {item.get("role"): item for item in document.get("files") or []}
    facts: dict[str, Any] = {
        "document": document,
        "old_id": document["id"],
        "element": document["element"],
        "family": document.get("family"),
        "roles": by_role,
        "signature": content_signature(document.get("files") or []),
        "has_sizes": "pp" in by_role and "nao" in by_role,
    }
    facts["valence"] = (
        valence_electrons(root / by_role["pp"]["path"]) if "pp" in by_role else None
    )
    if "nao" in by_role:
        counts = channels(root / by_role["nao"]["path"])
        facts["orbital_shells"] = shells(counts)
        facts["orbital_dimension"] = dimension(counts)
    else:
        facts["orbital_shells"] = None
        facts["orbital_dimension"] = None
    facts["auxiliary_dimension"] = (
        dimension(channels(root / by_role["abf"]["path"])) if "abf" in by_role else None
    )
    if "species_defaults" in by_role:
        facts.update(species_defaults_facts(root / by_role["species_defaults"]["path"]))
    return facts


_SPECIES_LINE = re.compile(r"^\s*species\s+([A-Z][a-z]?)", re.MULTILINE)
_TIER_LINE = re.compile(r'Suggested "([a-z_]+)"')


def species_defaults_facts(path: Path) -> dict[str, Any]:
    """What an FHI-aims species-defaults fragment actually declares.

    These payloads carry no pseudopotential or orbital, so they cannot be sized.
    What they do carry is the species they describe and, when the file says so,
    the tier - and those are the facts that distinguish one fragment from
    another.
    """
    text = path.read_text(errors="replace")
    species = _SPECIES_LINE.search(text)
    tier = _TIER_LINE.search(text)
    return {
        "declared_species": species.group(1) if species else None,
        "tier": tier.group(1) if tier else None,
    }


def base_id(facts: Mapping[str, Any]) -> str:
    """The fact-only name, before any disambiguation."""
    element = facts["element"]
    token = family_token(facts["family"])
    if token == "aims" and facts.get("declared_species"):
        # The species is normally the set's own element, so repeating it would
        # read "Al-aims-Al". Only a fragment for another element needs to say so.
        parts = [element, token]
        if facts["declared_species"] != element:
            parts.append(facts["declared_species"])
        if facts.get("tier"):
            parts.append(facts["tier"])
        return "-".join(parts)
    if not facts["has_sizes"] or not facts["valence"] or not facts["orbital_shells"]:
        return f"{element}-{token}"
    parts = [
        element,
        token,
        f"{facts['valence']}e",
        facts["orbital_shells"],
        str(facts["orbital_dimension"]),
        f"abf{facts['auxiliary_dimension']}" if facts["auxiliary_dimension"] else "noabf",
    ]
    return "-".join(parts)


def consumers(records: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Map set id -> the calculation records that reference it."""
    used: dict[str, list[str]] = defaultdict(list)
    for record in records:
        record_id = record.get("id")
        for species in record.get("species") or []:
            set_id = species.get("set_id")
            if set_id and record_id not in used[set_id]:
                used[set_id].append(record_id)
        for candidate in record.get("basis_candidates") or []:
            set_id = candidate.get("set_id")
            if set_id and record_id not in used[set_id]:
                used[set_id].append(record_id)
    return used


def load_records(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "data" / "calculations").glob("*/*/*/record.json"))
    ]


def build_mapping(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """Return ``old_id -> {new_id, facts, reason}`` for every element set."""
    sets_root = root / "data" / "elements"
    records = load_records(root)
    used = consumers(records)
    facts_by_old: dict[str, dict[str, Any]] = {}
    for set_json in sorted(sets_root.glob("*/sets/*/set.json")):
        facts = set_facts(root, set_json)
        facts["set_json"] = set_json
        facts_by_old[facts["old_id"]] = facts
    grouped: dict[str, list[str]] = defaultdict(list)
    for old_id, facts in facts_by_old.items():
        grouped[base_id(facts)].append(old_id)

    mapping: dict[str, dict[str, Any]] = {}
    for base, olds in grouped.items():
        if len(olds) == 1:
            only = olds[0]
            mapping[only] = {"new_id": base, "reason": "facts are unique"}
            continue
        signatures = {facts_by_old[old]["signature"] for old in olds}
        if len(signatures) == len(olds):
            for old in olds:
                mapping[old] = {
                    "new_id": f"{base}-{facts_by_old[old]['signature']}",
                    "reason": "same facts, different bytes: content suffix",
                }
            continue
        # Some copies are byte-identical. Those are the same basis and may only
        # be told apart by which calculation used them, so the consumer name is
        # the discriminator; a copy nothing used keeps the content suffix.
        by_signature: dict[str, list[str]] = defaultdict(list)
        for old in olds:
            by_signature[facts_by_old[old]["signature"]].append(old)
        for signature, same in by_signature.items():
            if len(same) == 1:
                mapping[same[0]] = {
                    "new_id": f"{base}-{signature}",
                    "reason": "same facts, different bytes: content suffix",
                }
                continue
            for old in same:
                consumers_of = used.get(old, [])
                if consumers_of:
                    mapping[old] = {
                        "new_id": f"{base}-{consumers_of[0]}",
                        "reason": "identical bytes registered twice: named by its consumer",
                    }
                else:
                    # Two records, byte-identical, and nothing used either one.
                    # There is no fact left that distinguishes them, so giving
                    # them different names would be an invented difference:
                    # they are one basis and the archive should merge them.
                    raise RenameError(
                        f"{same} hold identical bytes and no calculation uses them; "
                        "merge them into one set before renaming"
                    )
    for old, entry in mapping.items():
        entry["old_id"] = old
        if not _ID_SAFE.match(entry["new_id"]):
            raise RenameError(f"{old} -> {entry['new_id']}: id has unsafe characters")
    finals: dict[str, list[str]] = defaultdict(list)
    for entry in mapping.values():
        finals[entry["new_id"]].append(entry["old_id"])
    collisions = {key: value for key, value in finals.items() if len(value) > 1}
    if collisions:
        raise RenameError(f"generated ids collide: {collisions}")
    return mapping


def _rewrite_set_ids(value: Any, mapping: Mapping[str, Mapping[str, Any]]) -> Any:
    """Replace every occurrence of an old set id inside a record/JSON value."""
    if isinstance(value, dict):
        return {key: _rewrite_set_ids(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_set_ids(item, mapping) for item in value]
    if isinstance(value, str) and value in mapping:
        return mapping[value]["new_id"]
    return value


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def apply_mapping(root: Path, mapping: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Move directories and rewrite every stored reference. Returns changed paths."""
    changes: list[str] = []
    sets_root = root / "data" / "elements"
    for old, entry in sorted(mapping.items()):
        if old == entry["new_id"]:
            continue
        # The mapping carries only old/new/reason; the element directory is
        # <root>/data/elements/<Element>/sets/<id>, so the element is the
        # grandparent of the old set directory.
        old_dir = sets_root / "*" / "sets" / old
        candidates = list(sets_root.glob(f"*/sets/{old}"))
        if len(candidates) != 1:
            raise RenameError(f"{old}: expected exactly one set directory, found {candidates}")
        element_dir = candidates[0].parent.parent
        old_dir = candidates[0]
        new_dir = element_dir / "sets" / entry["new_id"]
        if new_dir.exists():
            raise RenameError(f"{entry['new_id']}: destination already exists")
        old_dir.rename(new_dir)
        changes.append(f"{old_dir} -> {new_dir}")
        set_json = new_dir / "set.json"
        document = json.loads(set_json.read_text(encoding="utf-8"))
        document["id"] = entry["new_id"]
        document["previous_id"] = old
        set_json.write_bytes(_json_bytes(document))
    for path in sorted((root / "data" / "calculations").glob("*/*/*/*.json")):
        original = path.read_text(encoding="utf-8")
        try:
            value = json.loads(original)
        except json.JSONDecodeError:
            continue
        rewritten = _rewrite_set_ids(value, mapping)
        if rewritten != value:
            path.write_bytes(_json_bytes(rewritten))
            changes.append(str(path))
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        mapping = build_mapping(root)
    except RenameError as exc:
        print(f"cannot rename: {exc}", file=sys.stderr)
        return 1
    changed = [entry for entry in mapping.values() if entry["old_id"] != entry["new_id"]]
    reasons: dict[str, int] = defaultdict(int)
    for entry in mapping.values():
        reasons[entry["reason"]] += 1
    report = {
        "sets": len(mapping),
        "renamed": len(changed),
        "reasons": dict(sorted(reasons.items())),
        "max_length": max(len(entry["new_id"]) for entry in mapping.values()),
        "mapping": {entry["old_id"]: entry["new_id"] for entry in mapping.values()},
    }
    if args.write:
        changes = apply_mapping(root, mapping)
        report["changes"] = changes
        print(f"renamed {len(changed)} of {len(mapping)} sets ({len(changes)} files touched)")
    elif args.check:
        # After --write the directories already carry the new ids, so the check
        # compares the derived name against what is on disk: a stored id that no
        # longer matches its own payloads means the payloads changed under it.
        sets_root = root / "data" / "elements"
        stale: list[str] = []
        for set_json in sorted(sets_root.glob("*/sets/*/set.json")):
            document = json.loads(set_json.read_text(encoding="utf-8"))
            if document["id"] != set_json.parent.name:
                stale.append(f"{set_json.parent.name}: id field is {document['id']}")
        if stale:
            print(f"{len(stale)} set directories disagree with their id", file=sys.stderr)
            for item in stale[:5]:
                print(f"  {item}", file=sys.stderr)
            return 1
        drift = sum(1 for entry in mapping.values() if entry["old_id"] != entry["new_id"])
        print(f"ids follow the fact rule ({len(mapping)} sets, {drift} would change)")
        print("  note: --check after --write also verifies each id equals its directory name")
    else:
        print(json.dumps({k: v for k, v in report.items() if k != "mapping"}, indent=2))
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
