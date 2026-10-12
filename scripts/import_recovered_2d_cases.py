#!/usr/bin/env python3
"""Import recovered production inputs and exact basis bindings for four 2D records.

User-supplied original evidence (2026-10-12):

- GeTe: production_20260906/GeTe_stringent_tzdp10_n12_direct2d (scf/band controls,
  gw librpa.in) plus producer assets/Ge and assets/Te PP/NAO/ABF payloads.
- SnSe: production_20260909/snse_library_tzdp10_plusg_20260909 (scf/band controls,
  gw + exx librpa.in) plus assets/Sn and assets/Se payloads with REGISTRY_MANIFEST.
- Phosphorene: compute_backup_review_20260514 gw/2d/phosphorene pbe + gw stage
  controls and P PP/NAO/ABF payloads.
- hBN legacy (hbn-table-gw): compute_backup_review_20260514 gw/2d/mono-hBN/gw_14au/
  6_3_ccp controls and B/N NAO/ABF plus N PP payloads. The B production PP
  (B.PD04.PBE.UPF, pseudo_dir ./) was not preserved in any available backup and
  remains an explicit missing role; no other PP is substituted.

GeTe/SnSe EXX spectra are pathological. This importer records the raw-band
frontier path observable as an explicitly restricted property with the archived
spectrum as evidence; it does not fabricate an ordinary EXX gap.

prepare() captures a complete readset (spec inputs, source payloads/controls,
current records, every write target). apply() re-verifies the readset twice
before writing, writes payloads immutably, and updates records atomically.
Default mode is a dry run; --write applies; --check re-runs the strict
completeness gate and asserts the expected remaining issues per case.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path, PurePosixPath

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import library  # noqa: E402

GETE_ROOT = Path("/Users/ghj/同步空间/AITP_project/2d_gw_applications_20260905/production_20260906/GeTe_stringent_tzdp10_n12_direct2d")
SNSE_ROOT = Path("/Users/ghj/同步空间/AITP_project/2d_gw_applications_20260905/production_20260909/snse_library_tzdp10_plusg_20260909")
BACKUP_2D = Path("/Users/ghj/同步空间/ks_data/compute_backup_review_20260514_ks_iopcas_ghj/data/gw/2d")

INPUT_SCOPE = ("Recovered production controls from the original run directory; byte-preserved. "
               "Directory association is not an immutable full production chain or a self-contained "
               "rerun bundle; software identities and scientific acceptance are not changed by this import.")
BINDING_SCOPE = "Original production STRU plus payload SHA-256 association; not a full immutable runtime seal."
SOFTWARE_MISSING = "Full per-case ABACUS/LibRPA commits pending source-case audit"


def _stage_files(root: Path, stage: str, names: list[str]) -> list[dict]:
    return [{"stage": stage, "source": root / stage / name, "name": name} for name in names]


def _species(element: str, payloads: dict, aliases: dict, missing: list[str] | None = None) -> dict:
    return {"element": element, "payloads": payloads, "aliases": aliases, "missing_roles": missing or []}


CASES = {
    "gete-table-gw": {
        "material": "GeTe",
        "source_note": "production_20260906 GeTe stringent TZDP direct-2D producer directory",
        "inputs": (_stage_files(GETE_ROOT, "scf", ["INPUT", "KPT", "STRU"])
                   + _stage_files(GETE_ROOT, "band", ["INPUT", "KPT", "STRU"])
                   + _stage_files(GETE_ROOT, "gw", ["librpa.in"])),
        "species": [
            _species("Ge",
                     {"pp": GETE_ROOT / "assets/Ge/Ge.upf",
                      "nao": GETE_ROOT / "assets/Ge/Ge_gga_10au_150Ry_6s6p3d2f.orb",
                      "abf": GETE_ROOT / "assets/Ge/Ge_stringent_plusg_pca1e-4.abfs"},
                     {"pp": "../assets/Ge/Ge.upf",
                      "nao": "../assets/Ge/Ge_gga_10au_150Ry_6s6p3d2f.orb",
                      "abf": "../assets/Ge/Ge_stringent_plusg_pca1e-4.abfs"}),
            _species("Te",
                     {"pp": GETE_ROOT / "assets/Te/Te.upf",
                      "nao": GETE_ROOT / "assets/Te/Te_gga_10au_150Ry_6s6p3d2f.orb",
                      "abf": GETE_ROOT / "assets/Te/Te_stringent_plusg_pca1e-4.abfs"},
                     {"pp": "../assets/Te/Te.upf",
                      "nao": "../assets/Te/Te_gga_10au_150Ry_6s6p3d2f.orb",
                      "abf": "../assets/Te/Te_stringent_plusg_pca1e-4.abfs"}),
        ],
        "exx_restricted": {
            "value": -1002817.14856,
            "scope": "Sampled Γ–X–S–Y–Γ path; provisional pathological diagnostic, not an accepted gap.",
        },
        "missing_after": [SOFTWARE_MISSING],
    },
    "snse-table-gw": {
        "material": "SnSe",
        "source_note": "production_20260909 SnSe library TZDP plus-G producer directory",
        "inputs": (_stage_files(SNSE_ROOT, "scf", ["INPUT", "KPT", "STRU"])
                   + _stage_files(SNSE_ROOT, "band", ["INPUT", "KPT", "STRU"])
                   + [{"stage": "gw", "source": SNSE_ROOT / "gw_3328621_b6_20260913/librpa.in", "name": "librpa.in"},
                      {"stage": "exx", "source": SNSE_ROOT / "exx/librpa.in", "name": "librpa.in"}]),
        "species": [
            _species("Se",
                     {"pp": SNSE_ROOT / "assets/Se/PP.upf",
                      "nao": SNSE_ROOT / "assets/Se/physical.orb",
                      "abf": SNSE_ROOT / "assets/Se/auxiliary.abfs"},
                     {"pp": "../assets/Se/PP.upf",
                      "nao": "../assets/Se/physical.orb",
                      "abf": "../assets/Se/auxiliary.abfs"}),
            _species("Sn",
                     {"pp": SNSE_ROOT / "assets/Sn/PP.upf",
                      "nao": SNSE_ROOT / "assets/Sn/physical.orb",
                      "abf": SNSE_ROOT / "assets/Sn/auxiliary.abfs"},
                     {"pp": "../assets/Sn/PP.upf",
                      "nao": "../assets/Sn/physical.orb",
                      "abf": "../assets/Sn/auxiliary.abfs"}),
        ],
        "exx_restricted": {
            "value": -1898024.7638299998,
            "scope": "Sampled path; provisional pathological diagnostic, not an accepted gap.",
        },
        "missing_after": [SOFTWARE_MISSING],
    },
    "phosphorene-table-gw": {
        "material": "Phosphorene",
        "source_note": "compute_backup_review_20260514 gw/2d/phosphorene pbe and gw stage directories",
        # Only the self-contained gw/ chain is archived: its scf→nscf→librpa controls all
        # declare the same 2f1g ABF used by the production run. The separate earlier pbe/
        # directory used a different 1f1g ABF and is not part of this record's chain.
        "inputs": _stage_files(BACKUP_2D / "phosphorene", "gw",
                               ["INPUT", "INPUT_scf", "INPUT_nscf", "KPT", "KPT_scf", "KPT_nscf", "STRU", "librpa.in"]),
        "species": [
            _species("P",
                     {"pp": BACKUP_2D / "phosphorene/gw/P_ONCV_PBE-1.0.upf",
                      "nao": BACKUP_2D / "phosphorene/gw/P_gga_10au_100Ry_3s3p2d.orb",
                      "abf": BACKUP_2D / "phosphorene/gw/P_3s3p2d2f1g_pca1e-6.abfs"},
                     {"pp": "P_ONCV_PBE-1.0.upf",
                      "nao": "P_gga_10au_100Ry_3s3p2d.orb",
                      "abf": "P_3s3p2d2f1g_pca1e-6.abfs"}),
        ],
        "exx_restricted": None,
        "missing_after": [SOFTWARE_MISSING],
    },
    "hbn-table-gw": {
        "material": "hBN",
        "source_note": "compute_backup_review_20260514 gw/2d/mono-hBN/gw_14au/6_3_ccp production directory",
        "inputs": ([{"stage": "gw", "source": BACKUP_2D / "mono-hBN/gw_14au/6_3_ccp" / name, "name": name}
                    for name in ["INPUT", "INPUT_scf", "INPUT_nscf", "KPT", "KPT_scf", "KPT_nscf", "STRU", "librpa.in"]]),
        "species": [
            _species("B",
                     {"nao": BACKUP_2D / "mono-hBN/gw_14au/6_3_ccp/B_gga_14au_150Ry_3s3p2d.orb",
                      "abf": BACKUP_2D / "mono-hBN/gw_14au/6_3_ccp/B_14au_4s4p3d2f1g_pca1e-6.abfs"},
                     {"pp": "B.PD04.PBE.UPF",
                      "nao": "B_gga_14au_150Ry_3s3p2d.orb",
                      "abf": "B_14au_4s4p3d2f1g_pca1e-6.abfs"},
                     missing=["pp"]),
            _species("N",
                     {"pp": BACKUP_2D / "mono-hBN/gw_14au/6_3_ccp/N_ONCV_PBE-1.0.upf",
                      "nao": BACKUP_2D / "mono-hBN/gw_14au/6_3_ccp/N_gga_14au_150Ry_3s3p2d.orb",
                      "abf": BACKUP_2D / "mono-hBN/gw_14au/6_3_ccp/N_14au_3s3p2d2f1g_pca1e-6.abfs"},
                     {"pp": "N_ONCV_PBE-1.0.upf",
                      "nao": "N_gga_14au_150Ry_3s3p2d.orb",
                      "abf": "N_14au_3s3p2d2f1g_pca1e-6.abfs"}),
        ],
        "exx_restricted": None,
        "missing_after": [
            "B production PP (B.PD04.PBE.UPF) payload was not preserved in available backups; N and the B NAO/ABF are bound, the B PP stays an explicit missing role",
            SOFTWARE_MISSING,
        ],
    },
}

ROLE_DIRS = {"pp": ("pseudopotentials", ".upf"), "nao": ("orbitals", ".orb"), "abf": ("auxiliary", ".abfs")}
EXPECTED_ISSUES = {
    "gete-table-gw": {"software.abacus.commit: full immutable commit is required",
                      "software.librpa.commit: full immutable commit is required"},
    "snse-table-gw": {"software.abacus.commit: full immutable commit is required",
                      "software.librpa.commit: full immutable commit is required"},
    "phosphorene-table-gw": {"software.abacus.commit: full immutable commit is required",
                             "software.librpa.commit: full immutable commit is required"},
    "hbn-table-gw": {"species B: missing_roles is not empty: ['pp']",
                     "species B: expected one unambiguous pp payload, found 0",
                     "software.abacus.commit: full immutable commit is required",
                     "software.librpa.commit: full immutable commit is required"},
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def case_dir(repo: Path, case_id: str) -> Path:
    matches = sorted((repo / "data/calculations/2d").glob(f"*/{case_id}/record.json"))
    if len(matches) != 1:
        raise ValueError(f"case directory not unique for {case_id}: {matches}")
    return matches[0].parent


def read_file(readset: dict, path: Path) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"readset source missing or symlink: {path}")
    data = path.read_bytes()
    key = str(path)
    entry = (sha256_bytes(data), len(data))
    if key in readset and readset[key] != entry:
        raise ValueError(f"conflicting readset entry: {path}")
    readset[key] = entry
    return data


def verify_readset(readset: dict) -> None:
    for key, (digest, size) in readset.items():
        path = Path(key)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"readset dependency changed or missing: {key}")
        data = path.read_bytes()
        if sha256_bytes(data) != digest or len(data) != size:
            raise ValueError(f"readset dependency modified after prepare: {key}")


def set_identity(case_id: str, element: str, role_hashes: dict) -> str:
    text = "|".join([case_id, element] + [role_hashes.get(role, "") for role in ("pp", "nao", "abf")])
    return f"{element}-producer-{sha256_bytes(text.encode())[:20]}"


def prepare(repo: Path) -> tuple[dict, dict, dict]:
    """Collect every write and capture the complete readset; no writes happen here."""
    repo = repo.resolve()
    readset: dict[str, tuple[str, int]] = {}
    writes: dict[str, dict] = {}
    report = {"cases": {}, "new_payloads": [], "new_sets": []}

    for case_id, spec in CASES.items():
        directory = case_dir(repo, case_id)
        record_path = directory / "record.json"
        record = json.loads(read_file(readset, record_path))
        prefix = f"data/calculations/2d/{record['material']}/{case_id}"
        case_report = {"inputs": [], "sets": [], "property_added": bool(spec["exx_restricted"])}

        if record.get("species"):
            raise ValueError(f"{case_id}: species already bound; refusing ambiguous re-import")
        if record.get("files", {}).get("inputs"):
            raise ValueError(f"{case_id}: inputs already archived; refusing duplicate import")

        # Production controls.
        for item in spec["inputs"]:
            data = read_file(readset, item["source"])
            target = f"{prefix}/inputs/recovered/{item['stage']}/{item['name']}"
            if target in writes:
                raise ValueError(f"duplicate write target: {target}")
            writes[target] = {"kind": "new", "data": data}
            case_report["inputs"].append({"path": target, "sha256": sha256_bytes(data), "size_bytes": len(data),
                                          "stage": item["stage"], "original_name": item["name"]})

        # STRU declarations must match the reviewed aliases exactly.
        stru_texts = []
        for item in spec["inputs"]:
            if item["name"] == "STRU":
                stru_texts.append((item["stage"], item["source"].read_text(encoding="utf-8")))
        declared_globally = set()
        for stage, text in stru_texts:
            sections = library._stru_sections(text)
            rows = [line.split() for line in sections.get("ATOMIC_SPECIES", [])]
            order = [row[0] for row in rows if row]
            if set(order) != {entry["element"] for entry in spec["species"]}:
                raise ValueError(f"{case_id} {stage} STRU elements {order} do not match species spec")
            declared = {"pp": [row[2] if len(row) > 2 else "" for row in rows]}
            for role, section in (("nao", "NUMERICAL_ORBITAL"), ("abf", "ABFS_ORBITAL")):
                if section in sections:
                    declared[role] = [line.split()[0] for line in sections[section]]
            declared_globally.update(declared)
            for role, names in declared.items():
                if len(names) != len(order):
                    raise ValueError(f"{case_id} {stage} STRU {role} declarations do not cover ATOMIC_SPECIES")
                for element, name in zip(order, names):
                    entry = next(entry for entry in spec["species"] if entry["element"] == element)
                    if name != entry["aliases"].get(role):
                        raise ValueError(f"{case_id} {stage} STRU {element} {role} declaration {name!r} "
                                         f"differs from reviewed alias {entry['aliases'].get(role)!r}")
        for role in ("nao", "abf"):
            if stru_texts and role not in declared_globally:
                raise ValueError(f"{case_id}: no production STRU declares exact {role} payloads")

        # Species payloads and set records.
        species_entries = []
        species_hashes = []
        for entry in spec["species"]:
            element = entry["element"]
            role_hashes, files = {}, []
            for role in ("pp", "nao", "abf"):
                source = entry["payloads"].get(role)
                if source is None:
                    continue
                data = read_file(readset, source)
                digest = sha256_bytes(data)
                role_hashes[role] = digest
                subdir, suffix = ROLE_DIRS[role]
                payload_path = f"data/elements/{element}/{subdir}/{digest}{suffix}"
                existing = repo / payload_path
                if existing.exists() or existing.is_symlink():
                    existing_data = read_file(readset, existing)
                    if sha256_bytes(existing_data) != digest:
                        raise ValueError(f"immutable payload conflict: {payload_path}")
                else:
                    writes[payload_path] = {"kind": "immutable", "data": data}
                    report["new_payloads"].append(payload_path)
                files.append({"role": role, "path": payload_path, "sha256": digest, "size_bytes": len(data),
                              "original_sha256": digest, "label": entry["aliases"][role],
                              "original_name": entry["aliases"][role], "transformation": "none",
                              "source_declarations": [entry["aliases"][role]]})
            set_id = set_identity(case_id, element, role_hashes)
            set_record = {
                "schema_version": 1,
                "id": set_id,
                "element": element,
                "family": "Recovered producer-bound assets",
                "validation_scope": ("Original production STRU and payload SHA-256 association; "
                                     "scientific acceptance and full runtime handoff not reassessed."),
                "publication": {"status": "database_only"},
                "source": {"collection": "Recovered production assets (user-supplied original evidence, 2026-10-12)",
                           "receipts": [f"{prefix}/results/producer_assets_receipt.json"]},
                "files": files,
                "generation_provenance": {"status": "historical production association verified; generation history not reassessed"},
                "used_by": [case_id],
            }
            set_target = f"data/elements/{element}/sets/{set_id}/set.json"
            if (repo / set_target).exists():
                raise ValueError(f"set already exists: {set_target}")
            writes[set_target] = {"kind": "new", "data": (json.dumps(set_record, indent=2, ensure_ascii=False) + "\n").encode()}
            report["new_sets"].append(set_id)
            case_report["sets"].append(set_id)
            species_hashes.append(role_hashes)
            species_entries.append({"element": element, "set_id": set_id,
                                    "missing_roles": entry["missing_roles"],
                                    "asset_aliases": entry["aliases"],
                                    "binding_scope": BINDING_SCOPE})

        # Receipt.
        receipt = {
            "schema_version": 1,
            "case_id": case_id,
            "imported_at": "2026-10-12",
            "record_before_sha256": readset[str(record_path)][0],
            "source_note": spec["source_note"],
            "inputs": case_report["inputs"],
            "structures": [
                {"archived_stru_path": item["path"], "sha256": item["sha256"]}
                for item in case_report["inputs"] if item["original_name"] == "STRU"
            ],
            "references": [
                {"element": entry["element"], "set_id": species["set_id"],
                 "declared_names": entry["aliases"], "missing_roles": entry["missing_roles"],
                 "payload_sha256": hashes}
                for entry, species, hashes in zip(spec["species"], species_entries, species_hashes)
            ],
            "remaining_gaps": spec["missing_after"],
            "notes": ("Inputs and PP/NAO/ABF payloads are byte-preserved originals from the user-located "
                      "production evidence. This receipt closes input and basis-binding evidence only; "
                      "software identities, full runtime handoff and scientific acceptance are unchanged."),
        }
        receipt_target = f"{prefix}/results/producer_assets_receipt.json"
        if (repo / receipt_target).exists():
            raise ValueError(f"receipt already exists: {receipt_target}")
        writes[receipt_target] = {"kind": "new", "data": (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode()}

        # Record update.
        updated = json.loads(json.dumps(record))
        receipt_data = writes[receipt_target]["data"]
        updated.setdefault("files", {}).setdefault("results", []).append({
            "role": "results", "path": receipt_target, "sha256": sha256_bytes(receipt_data),
            "size_bytes": len(receipt_data), "original_sha256": sha256_bytes(receipt_data),
            "label": "producer_assets_receipt.json", "original_name": "producer_assets_receipt.json",
            "transformation": "none"})
        inputs_group = updated["files"].setdefault("inputs", [])
        for item in case_report["inputs"]:
            inputs_group.append({
                "role": "inputs", "path": item["path"], "sha256": item["sha256"], "size_bytes": item["size_bytes"],
                "original_sha256": item["sha256"], "label": f"{item['stage']} / {item['original_name']}",
                "original_name": item["original_name"], "transformation": "none",
                "original_size_bytes": item["size_bytes"], "stage_id": item["stage"],
                "evidence_scope": INPUT_SCOPE,
            })
        updated["species"] = species_entries
        updated.setdefault("source", {})["producer_assets_receipt"] = receipt_target
        updated["missing"] = list(spec["missing_after"])
        if spec["exx_restricted"]:
            band_path = f"{prefix}/results/EXX_bands.dat"
            if not any(item.get("path") == band_path for item in updated["files"].get("results", [])):
                raise ValueError(f"{case_id}: archived EXX band result missing for restricted property evidence")
            updated.setdefault("properties", []).append({
                "key": "restricted_raw_band_frontier_path_gap",
                "category": "electronic",
                "label": "Restricted EXX raw-band frontier path gap",
                "method": "EXX",
                "value": spec["exx_restricted"]["value"],
                "unit": "eV",
                "status": "provisional",
                "definition": ("Restricted raw-band frontier path gap: full raw path CBM − VBM of the "
                               "archived EXX spectrum; pathological negative value retained for "
                               "traceability, not an accepted gap"),
                "scope": spec["exx_restricted"]["scope"],
                "evidence": [band_path],
            })
        record_rel = f"{prefix}/record.json"
        writes[record_rel] = {"kind": "mutable", "data": (json.dumps(updated, indent=2, ensure_ascii=False) + "\n").encode(),
                              "expected_sha256": readset[str(record_path)][0]}
        report["cases"][case_id] = case_report

    return writes, report, readset


def apply(repo: Path, writes: dict, readset: dict) -> None:
    repo = repo.resolve()
    verify_readset(readset)
    for relative, entry in writes.items():
        target = repo / relative
        if target.is_symlink():
            raise ValueError(f"refusing symlink target: {relative}")
        if entry["kind"] in {"new", "immutable"} and target.exists():
            raise ValueError(f"target already exists: {relative}")
        if entry["kind"] == "mutable":
            current = target.read_bytes() if target.exists() else b""
            if sha256_bytes(current) != entry["expected_sha256"]:
                raise ValueError(f"mutable target changed after prepare: {relative}")
    verify_readset(readset)
    for relative, entry in writes.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = entry["data"]
        if entry["kind"] == "immutable":
            with target.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                temp = stream.name
            os.replace(temp, target)


def check(repo: Path) -> dict:
    repo = repo.resolve()
    sets, cases = library.load_records(repo)
    library.validate(repo, sets, cases)
    by_id = {case["id"]: case for case in cases}
    remaining = {}
    for case_id, expected in EXPECTED_ISSUES.items():
        issues = set(library.completeness_issues(repo, sets, by_id[case_id]))
        if issues != expected:
            raise ValueError(f"{case_id}: unexpected remaining issues:\n  only got: {sorted(issues - expected)}\n"
                             f"  missing: {sorted(expected - issues)}")
        remaining[case_id] = sorted(issues)
    report = library.completeness_report(repo, sets, cases)
    return {"remaining": remaining, "stats": report["stats"], "integrity_issues": report["integrity_issues"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="apply the reviewed import (default: dry run)")
    parser.add_argument("--check", action="store_true", help="assert expected remaining strict issues per case")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    repo = args.repo.resolve()

    if args.check:
        result = check(repo)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    writes, report, readset = prepare(repo)
    total_bytes = sum(len(entry["data"]) for entry in writes.values())
    print(f"prepared {len(writes)} writes ({total_bytes} bytes), readset {len(readset)} dependencies")
    print(f"new payloads: {len(report['new_payloads'])}, new sets: {len(report['new_sets'])}")
    for case_id, case_report in report["cases"].items():
        print(f"  {case_id}: {len(case_report['inputs'])} inputs, sets {case_report['sets']}, "
              f"restricted EXX property: {case_report['property_added']}")
    if not args.write:
        print("dry run only; pass --write to apply")
        return 0
    apply(repo, writes, readset)
    print("applied; running strict check…")
    result = check(repo)
    print(json.dumps(result["stats"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
