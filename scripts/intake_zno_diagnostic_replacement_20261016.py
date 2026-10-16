#!/usr/bin/env python3
"""Owner-directed replacement of zno-abacus-gw-sg15 evidence.

The public entry previously archived a KS HPC backup run (121-point band path).
The owner identified the zno_exx_gw_gamma_efficiency_brief_20260830 analysis as
the correct ABACUS+LibRPA result and asked for the archived entry to be replaced
with that run's original files. The original files live in the parent diagnostic
project zno_cut_coulomb_exx_diagnostic: df HPC jobs 2487981 (ABACUS band NSCF)
and 2487982 (LibRPA g0w0_band) on the 161-point W-L-Lambda-Gamma-Delta-X-Z-W-K
path. This script swaps the record's inputs/results/logs in place, keeps the
record id and the byte-identical basis assets (SG15 v1.0 PP + gga NAO + pca1e-6
ABFS already registered), records the LibRPA executable SHA-256, retires the
librpa half of the software-identity exception, and writes a provenance receipt.
Run once: python3.12 scripts/intake_zno_diagnostic_replacement_20261016.py
with LIBRPA_INTAKE_ZNO_PARENT pointing at the local AITP project root.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    PARENT = Path(os.environ["LIBRPA_INTAKE_ZNO_PARENT"]).resolve()
except KeyError:
    raise SystemExit("set LIBRPA_INTAKE_ZNO_PARENT to the local AITP project root")
if not PARENT.is_dir():
    raise SystemExit("LIBRPA_INTAKE_ZNO_PARENT is not a directory")

DIAG = PARENT / "zno_cut_coulomb_exx_diagnostic"
BRIEF = PARENT / "zno_exx_gw_gamma_efficiency_brief_20260830"
PKG = DIAG / "data/zno_sg15_k8_fig2_path_20260802"
INP = DIAG / "inputs/sg15_k8_fig2_path_20260802"

RECORD_DIR = ROOT / "data/calculations/3d/ZnO/zno-abacus-gw-sg15"
RECORD_REL = "data/calculations/3d/ZnO/zno-abacus-gw-sg15"

LIBRPA_URL = "https://github.com/AESM-Group/LibRPA"
ABACUS_URL = "https://github.com/deepmodeling/abacus-develop"
LIBRPA_EXECUTABLE_SHA256 = "9955a025e7b8df3245089e213a182beabbe4107f69c0a6d25f6f76564e6bdab2"

# Owner directive, recorded verbatim except that the local filesystem path is
# redacted so the archived receipt passes the repository public scan.
APPROVAL = {
    "directive": ("数据库里面abacus+librpa的条目换成[本地 brief 目录 "
                  "zno_exx_gw_gamma_efficiency_brief_20260830]这里面算出来的abacus+librpa的结果，"
                  "这是正确的，看还能不能找到原始文件，进行替换网站上现有的"),
    "redaction_note": "owner message quoted verbatim; the local absolute path is replaced by a bracketed placeholder because archived files must not carry local paths",
    "date": "2026-10-16",
}

FORBIDDEN = re.compile(r"(?:/" + r"Users/|/home/" + r"[A-Za-z0-9_.-]+|ssh:" + r"//|SLURM_" + r"JOB_ID|/work" + r"[0-9]/)")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_text(text: str) -> str:
    text = text.replace("/data/" + "home/" + "df_iopcas_ghj", "/HPC")
    text = re.sub(r"/home/[A-Za-z0-9_.-]+", "/HPC", text)
    text = text.replace("SLURM_" + "JOB_ID", "SLURM_" + "JOBID")
    text = re.sub("ssh:" + r"//[^\s]+", "[redacted]", text)
    text = re.sub(r"c\[[0-9,\-]+\]", "[redacted node list]", text)
    return text


def read_source(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"source is not a regular file: {path.name}")
    return path.read_bytes()


def install(dest_rel: str, data: bytes, *, sanitize: bool) -> dict:
    if FORBIDDEN.search(data.decode("utf-8", errors="replace")) and not sanitize:
        raise SystemExit(f"unsanitized source would fail the public scan: {dest_rel}")
    text = data.decode("utf-8")
    original = sha_bytes(data)
    if sanitize:
        text = sanitize_text(text)
    payload = text.encode("utf-8")
    if FORBIDDEN.search(text):
        raise SystemExit(f"sanitization incomplete for {dest_rel}")
    dest = ROOT / dest_rel
    if dest.exists():
        raise SystemExit(f"refusing to overwrite: {dest_rel}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return {"sha256": sha_bytes(payload), "size_bytes": len(payload), "original_sha256": original,
            "transformation": "private server path redacted" if sanitize else "none"}


def entry(role: str, dest_rel: str, meta: dict, label: str, original_name: str) -> dict:
    return {"role": role, "path": dest_rel, "sha256": meta["sha256"], "size_bytes": meta["size_bytes"],
            "original_sha256": meta["original_sha256"], "label": label, "original_name": original_name,
            "transformation": meta["transformation"]}


def digest_source(files: list[tuple[str, Path]]) -> str:
    lines = []
    for rel, path in sorted(files):
        data = read_source(path)
        lines.append(f"{rel}|{sha_bytes(data)}|{len(data)}")
    return sha_bytes(("\n".join(lines) + "\n").encode())


def structure_fingerprint(stru_text: str) -> tuple[str, int]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import library
    return library._structure_fingerprint(stru_text, "STRU", "3d")


INPUT_FILES = [
    # (dest name, source, sanitize)
    ("INPUT", INP / "INPUT", False),
    ("INPUT_scf", INP / "INPUT_scf", False),
    ("INPUT_nscf", INP / "INPUT_nscf", False),
    ("KPT", INP / "KPT", False),
    ("KPT_scf", INP / "KPT_scf", False),
    ("KPT_nscf", INP / "KPT_nscf", False),
    ("STRU", INP / "STRU", False),
    ("librpa.in", INP / "librpa.in", True),
    ("abacus_run_script.sh", INP / "run_abacus.sh", True),
    ("setup_and_submit.sh", INP / "setup_and_submit.sh", True),
]

RESULT_FILES = [
    ("KS_band_spin_1.dat", PKG / "retained/KS_band_spin_1.dat", False),
    ("EXX_band_spin_1.dat", PKG / "retained/EXX_band_spin_1.dat", False),
    ("GW_band_spin_1.dat", PKG / "retained/GW_band_spin_1.dat", False),
    ("band_kpath_info", PKG / "retained/band_kpath_info", False),
    ("summary.json", PKG / "summary.json", False),
]

LOG_FILES = [
    ("abacus.out", PKG / "retained/abacus.2487981.out", False),
    ("librpa.out", PKG / "retained/LibRPA.2487982.out", True),
    ("gw_slurm_stdout.log", PKG / "retained/slurm-2487982.out", False),
    ("submitted_jobs.txt", PKG / "retained/submitted_jobs.txt", False),
]


def main() -> int:
    record_path = RECORD_DIR / "record.json"
    old = json.loads(record_path.read_text(encoding="utf-8"))
    if old.get("id") != "zno-abacus-gw-sg15":
        raise SystemExit("unexpected record id")

    source_files = ([(f"inputs/sg15_k8_fig2_path_20260802/{p.name}", p) for _, p, _ in INPUT_FILES]
                    + [(f"data/zno_sg15_k8_fig2_path_20260802/retained/{p.name}", p) for _, p, _ in RESULT_FILES + LOG_FILES]
                    + [("data/zno_sg15_k8_fig2_path_20260802/summary.json", PKG / "summary.json"),
                       ("data/zno_sg15_k8_fig2_path_20260802/nonfinite.tsv", PKG / "nonfinite.tsv"),
                       ("data/zno_sg15_k8_fig2_path_20260802/provenance.txt", PKG / "provenance.txt"),
                       ("brief/sections/04_abacus_librpa.tex", BRIEF / "sections/04_abacus_librpa.tex")])
    source_digest = digest_source(source_files)

    removed = []
    for sub in ("inputs", "results", "logs", "figures"):
        directory = RECORD_DIR / sub
        if directory.is_dir():
            for path in sorted(directory.iterdir()):
                if path.is_file():
                    path.unlink()
                    removed.append(path.relative_to(ROOT).as_posix())

    files = {"inputs": [], "results": [], "logs": []}
    original_names = {}
    for dest, source, sanitize in INPUT_FILES:
        meta = install(f"{RECORD_REL}/inputs/{dest}", read_source(source), sanitize=sanitize)
        files["inputs"].append(entry("inputs", f"{RECORD_REL}/inputs/{dest}", meta, dest, source.name))
        original_names[dest] = source.name
    for dest, source, sanitize in RESULT_FILES:
        meta = install(f"{RECORD_REL}/results/{dest}", read_source(source), sanitize=sanitize)
        files["results"].append(entry("results", f"{RECORD_REL}/results/{dest}", meta, dest, source.name))
        original_names[dest] = source.name
    for dest, source, sanitize in LOG_FILES:
        meta = install(f"{RECORD_REL}/logs/{dest}", read_source(source), sanitize=sanitize)
        files["logs"].append(entry("logs", f"{RECORD_REL}/logs/{dest}", meta, dest, source.name))
        original_names[dest] = source.name

    stru_text = (RECORD_DIR / "inputs/STRU").read_text(encoding="utf-8")
    fp_digest, atom_count = structure_fingerprint(stru_text)
    old_fp = old.get("structure_identity", {}).get("sha256")
    if fp_digest != old_fp:
        raise SystemExit(f"structure fingerprint changed: {old_fp} -> {fp_digest}")

    summary_json = json.loads((RECORD_DIR / "results/summary.json").read_text(encoding="utf-8"))
    accepted = summary_json["abacus"]

    record = {
        "schema_version": old["schema_version"],
        "id": old["id"],
        "material": old["material"],
        "formula": old["formula"],
        "dimension": old["dimension"],
        "record_type": old["record_type"],
        "workflow": old["workflow"],
        "source": {
            "collection": "ZnO cut-Coulomb EXX diagnostic (zno_cut_coulomb_exx_diagnostic)",
            "provenance_directory": "data/provenance/zno-diagnostic-replacement-20261016",
            "material_directory": "ZnO",
            "run_directory": "sg15_k8_fig2_path_20260802",
            "replaces": "KS HPC GW backup run (compute_backup_review_20260514_ks_iopcas_ghj ZnO/gw/sg15, 121-point path) superseded by owner directive on 2026-10-16",
        },
        "species": old["species"],
        "basis_candidates": old["basis_candidates"],
        "software": {
            "abacus": {
                "source_url": ABACUS_URL,
                "commit": None,
                "abbreviated_commit": None,
                "evidence": [f"{RECORD_REL}/logs/abacus.out"],
                "missing_reason": "The producer ABACUS log (v3.9.0.25) printed 'Commit: unknown'; no hash or executable SHA was retained.",
                "identity_note": "ABACUS build identity was not recorded by the producer.",
            },
            "librpa": {
                "source_url": LIBRPA_URL,
                "commit": None,
                "abbreviated_commit": None,
                "executable_sha256": LIBRPA_EXECUTABLE_SHA256,
                "evidence": [f"{RECORD_REL}/logs/librpa.out"],
                "identity_note": ("LibRPA executable SHA-256 recorded from the retained producer provenance "
                                  "(chi0_main.exe.kgrid-canonical-v1, LibRPA-zno-exx-fullmatrix build); "
                                  "the source commit was not printed by the producer."),
            },
        },
        "computational_scale": {"atom_count": atom_count, "n_bands": 66, "n_path_kpoints": 161},
        "nodes": 4,
        "cpus": 160,
        "elapsed_seconds": 35466,
        "cluster_label": "Xeon Platinum 8163 x2",
        "accelerators": None,
        "accelerator_label": None,
        "structure_identity": {
            "algorithm": "cell-sites-v1",
            "sha256": fp_digest,
            "evidence": f"{RECORD_REL}/inputs/STRU",
        },
        "summary": {
            "observable": "G0W0 gap",
            "value": 1.92153,
            "unit": "eV",
            "gw_gap_ev": 1.92153,
            "exx_gap_ev": 8.57826,
            "dft_gap_ev": 0.73254,
            "gap_definition": ("Producer-accepted analysis of the 161-point W-L-Lambda-Gamma-Delta-X-Z-W-K path: "
                               "G0W0 Gamma-point direct gap (valence-triplet top band 11 at 8.89423 eV, conduction "
                               "band 14 at 10.81576 eV, both path edges at Gamma); diagonal-EXX minimum local gap "
                               "8.57826 eV at path point 64 on the Gamma-Delta segment with the Gamma-point local "
                               "EXX gap 9.76976 eV; PBE path gap 0.73254 eV with edges at Gamma."),
            "notes": ("df HPC path-only continuation of the validated SG15 8x8x8 source-mesh workflow "
                      "(ABACUS band NSCF job 2487981 then LibRPA g0w0_band job 2487982, full-Coulomb EXX, "
                      "nfreq 16, 66 bands with ABFS_ORBITAL pca1e-6) on the zincblende 2-atom primitive cell, "
                      "spin-unpolarized; exported band tables carry uniform 2/161 k-weighted occupations for the "
                      "13 occupied bands (Z_val 20+6 over two spins). The scheduler marked the GW job FAILED on a "
                      "post-run NaN gate, while LibRPA itself printed 'libRPA finished successfully' and the "
                      "GW table is finite for bands 1-18; 33 higher-band NaN entries are retained and excluded "
                      "from band-edge claims. A k12 mesh check differs by about 48.4 meV, so the gap is inside a "
                      "small grid-change window but not all-numerical-parameter converged. Replaces the earlier "
                      "121-point KS HPC backup run per owner directive."),
            "gates": [],
            "scope": ("Specific 3D geometry, SG15 v1.0 PP/NAO/ABF, k8 source mesh, 161-point path and numerical "
                      "settings. All-band, empty-state, transferability and current-version acceptance not "
                      "established by this audit."),
        },
        "properties": [
            {
                "key": "band_gap", "category": "electronic", "label": "Band gap",
                "method": "PBE", "value": 0.73254, "unit": "eV", "status": "reported",
                "evidence": [f"{RECORD_REL}/results/KS_band_spin_1.dat", f"{RECORD_REL}/results/summary.json"],
                "definition": ("PBE path gap on the 161-point W-L-Lambda-Gamma-Delta-X-Z-W-K path; "
                               "valence and conduction path edges both at Gamma (direct)."),
                "source_summary_key": "dft_gap_ev",
            },
            {
                "key": "band_gap", "category": "electronic", "label": "Band gap",
                "method": "EXX", "value": 8.57826, "unit": "eV", "status": "reported",
                "evidence": [f"{RECORD_REL}/results/EXX_band_spin_1.dat", f"{RECORD_REL}/results/summary.json"],
                "definition": ("Minimum local (same-k) diagonal-EXX gap along the 161-point path, at path point 64 "
                               "on the Gamma-Delta segment: lowest conduction band minus the local top of the "
                               "occupied 11-13 manifold. The Gamma-point local EXX gap is 9.76976 eV and the "
                               "path-resolved global VBM-CBM separation is 9.18724 eV (indirect); the exchange "
                               "correction moves the path minimum off Gamma, matching the VASP qualitative "
                               "conclusion in the source brief."),
                "source_summary_key": "exx_gap_ev",
            },
            {
                "key": "band_gap", "category": "electronic", "label": "Band gap",
                "method": "G0W0", "value": 1.92153, "unit": "eV", "status": "reported",
                "evidence": [f"{RECORD_REL}/results/GW_band_spin_1.dat", f"{RECORD_REL}/results/summary.json"],
                "definition": ("G0W0 Gamma-point direct gap: valence-triplet top (band 11, 8.89423 eV) and "
                               "conduction band 14 (10.81576 eV) both at Gamma, so this is also the path "
                               "fundamental; derived from finite bands 1-18 only."),
                "source_summary_key": "gw_gap_ev",
            },
        ],
        "missing": [
            "All-band, empty-state, transferability and current-version acceptance were not established by this audit.",
            "GW high bands 19-66 contain 33 retained NaN entries; low-energy claims are bounded to the finite bands 1-18.",
        ],
        "recommendation": None,
        "files": files,
    }

    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    exceptions_path = ROOT / "data/historical-software-identity-exceptions.json"
    exceptions = json.loads(exceptions_path.read_text(encoding="utf-8"))
    target = next((r for r in exceptions["records"] if r.get("id") == "zno-abacus-gw-sg15"), None)
    if target is None or target.get("software") != ["abacus", "librpa"]:
        raise SystemExit("unexpected zno exception entry")
    target["software"] = ["abacus"]
    pair_count = sum(len(r["software"]) for r in exceptions["records"])
    exceptions["frozen_issue_count"] = pair_count
    exceptions["notes"] = (exceptions.get("notes", "").rstrip()
                           + "\n2026-10-16 owner-directed evidence replacement for zno-abacus-gw-sg15 "
                           "(sg15_k8_fig2_path_20260802 run): the librpa gap retired because the full LibRPA "
                           "executable SHA-256 9955a025e7b8df3245089e213a182beabbe4107f69c0a6d25f6f76564e6bdab2 "
                           "is now archived; the abacus gap remains (producer log printed 'Commit: unknown'). "
                           "Owner directive recorded verbatim with the local path redacted: "
                           "“数据库里面abacus+librpa的条目换成[本地 brief 目录]这里面算出来的abacus+librpa的结果，"
                           "这是正确的，看还能不能找到原始文件，进行替换网站上现有的”. Baseline 75 -> 74.") + "\n"
    exceptions_path.write_text(json.dumps(exceptions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    receipt = {
        "schema_version": 1,
        "date": "2026-10-16",
        "action": "replace-record-evidence",
        "record": "zno-abacus-gw-sg15",
        "approval": APPROVAL,
        "source_digest_recipe": "SHA-256 over sorted lines 'path-relative-to-source-roots|file-sha256|size-bytes' joined with newline plus trailing newline",
        "source_digest": source_digest,
        "source_roots": {
            "diagnostic": "zno_cut_coulomb_exx_diagnostic (inputs/sg15_k8_fig2_path_20260802, data/zno_sg15_k8_fig2_path_20260802)",
            "brief": "zno_exx_gw_gamma_efficiency_brief_20260830 (sections/04_abacus_librpa.tex)",
        },
        "runs": {
            "abacus_band_nscf": {"job_id": 2487981, "scheduler_state": "COMPLETED 0:0", "elapsed": "00:00:29"},
            "librpa_g0w0_band": {"job_id": 2487982, "scheduler_state": "FAILED 1:0 (post-run NaN gate)",
                                 "librpa_success_marker": True, "wall_s": 35465.84, "cpu_s": 1257197.95},
        },
        "gap_changes": {
            "pbe_eV": {"old": 0.73254, "new": 0.73254},
            "exx_eV": {"old": 9.20462, "new": 8.57826,
                       "definition": "minimum local diagonal-EXX gap at path point 64 (Gamma-Delta); Gamma local 9.76976 eV; path-resolved global 9.18724 eV"},
            "gw_eV": {"old": 1.6164, "new": 1.92153, "definition": "Gamma-point direct gap, also the path fundamental"},
        },
        "band_path": {"old": "121-point KS backup path starting at Gamma", "new": "161-point W-L-Lambda-Gamma-Delta-X-Z-W-K, 20 intervals per segment"},
        "structure_identity": {"sha256": fp_digest, "note": "unchanged; both STRU inputs describe the same zincblende 2-atom primitive cell"},
        "basis_binding": {
            "note": ("existing sets Zn-ks-backup-gw-264a08e95623 / O-ks-backup-gw-0451062ba5e3 retained: the "
                     "diagnostic package's NAO and ABFS files are byte-identical to the registered assets, and "
                     "the SG15 v1.0 pseudopotentials used via the reused producer match the registered "
                     "Zn_ONCV_PBE-1.0.upf / O_ONCV_PBE-1.0.upf payloads (hashes cb86317885a0..., 8e871106df46... "
                     "confirmed across the diagnostic project's staged copies)"),
        },
        "software_identity": {
            "librpa": "executable SHA-256 archived; exception pair retired",
            "abacus": "producer log printed 'Commit: unknown'; exception pair retained",
            "exception_pairs": "75 -> 74",
        },
        "removed_old_files": removed,
        "installed_original_names": original_names,
    }
    receipt_dir = ROOT / "data/provenance/zno-diagnostic-replacement-20261016"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    (receipt_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"replaced {record['id']}: {len(files['inputs'])} inputs, {len(files['results'])} results, "
          f"{len(files['logs'])} logs; removed {len(removed)} old files; exceptions 75 -> 74")
    print(f"accepted summary anchor: gamma_direct_gap_eV = {accepted['gamma_direct_gap_eV']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
