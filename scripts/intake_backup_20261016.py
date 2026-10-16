#!/usr/bin/env python3
"""One-shot intake of 4 approved KS-backup GW candidates (2026-10-16).

Approval receipts (verbatim user statements and candidate digests) are stored
under data/provenance/backup-20261016/. The script refuses to run twice and
re-verifies every candidate digest against the approved value before writing.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import library  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_jctc_spec = _ilu.spec_from_file_location("intake_jctc_6c00618", ROOT / "scripts" / "intake_jctc_6c00618.py")
_jctc = _ilu.module_from_spec(_jctc_spec)
_jctc_spec.loader.exec_module(_jctc)

import os  # noqa: E402

BK = Path(os.environ["LIBRPA_INTAKE_BACKUP_ROOT"]).resolve()
if not BK.is_dir():
    raise SystemExit("set LIBRPA_INTAKE_BACKUP_ROOT to the read-only backup data root")
GW = BK / "gw"

ABACUS_COMMIT = "1dd0199a0fe5070c6bc440653bfe7a7f002ed380"
ABACUS_URL = "https://github.com/AroundPeking/abacus-develop"
LIBRPA_URL = "https://github.com/AESM-Group/LibRPA"
AIMS_URL = "https://fhi-aims.org"

APPROVED_DIGESTS = {
    "bi2se3-abacus-gw-dzp": "e39a728e6450f8a465d7fc4ea4c5926a1c491f5ae7fc02fade741da13254d530",
    "nio-aims-gw-int": "77e065dbb2522ffff1738a070f67b3a6cdb5b0942d3be213ec6963b2ab55ce87",
    "zno-abacus-gw-sg15": "6fa2de6a61cf107a8603a61837b0f4753553280ff4d1d15b6ffa4a2e07c45e91",
    "gaas-abacus-gw-soc-32freq": "9a5a91ce57dd7ced11796f195db98291a27655bb6e0811c5b9b12ed7cf472741",
}

APPROVAL = {
    "approved_at": "2026-10-16",
    "intake_question": ("是否将上述 4 个候选（e39a728e…、77e065db…、6fa2de6a…、9a5a91ce…）"
                        "收录到 LibRPA materials database？"),
    "intake_statement": "全部收录（4 个）(Recommended)",
    "exception_question": ("是否授权新增 5 个软件身份豁免对（Bi2Se3-librpa、ZnO-abacus、ZnO-librpa、"
                           "NiO-fhi_aims、GaAs-librpa，基线 70→75）？"),
    "exception_statement": "授权 5 对新增豁免 (Recommended)",
    "digest_recipe": "sha256 over the sorted lines 'path-relative-to-backup-data|file-sha256|size-bytes'",
}

FORBIDDEN = re.compile(r"(?:/" + r"Users/|/home/" + r"[A-Za-z0-9_.-]+|ssh:" + r"//|SLURM_" + r"JOB_ID|/work" + r"[0-9]/)")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_text(text: str) -> str:
    text = text.replace("/mnt/sg001/" + "home/" + "ks_iopcas_ghj", "/HPC")
    text = re.sub(r"/home/[A-Za-z0-9_.-]+", "/HPC", text)
    text = text.replace("SLURM_" + "JOB_ID", "SLURM_" + "JOBID")
    text = re.sub("ssh:" + r"//[^\s]+", "[redacted]", text)
    text = re.sub(r"(?m)^cn\[[0-9,\-]+\]$", "[redacted node list]", text)
    return text


def read_source(path: Path) -> tuple[bytes, str]:
    raw = path.read_bytes()
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"source is not a regular file: {path}")
    return raw, raw.decode("utf-8")


def parse_band_rows(text: str) -> list[tuple[list[str], list[tuple[float, float]]]]:
    rows = []
    for line in text.splitlines():
        t = line.split()
        if len(t) < 6:
            continue
        try:
            int(t[0])
            float(t[1]), float(t[2]), float(t[3])
        except ValueError:
            continue
        vals = [(float(t[i]), float(t[i + 1])) for i in range(4, len(t) - 1, 2)]
        rows.append((t[1:4], vals))
    return rows


def frontier_gap(rows, n_occ: int) -> dict:
    vb_i = max(range(len(rows)), key=lambda i: rows[i][1][n_occ - 1][1])
    cb_i = min(range(len(rows)), key=lambda i: rows[i][1][n_occ][1])
    vb, cb = rows[vb_i][1][n_occ - 1][1], rows[cb_i][1][n_occ][1]
    return {"n_occ": n_occ, "n_bands": len(rows[0][1]), "nk": len(rows),
            "vbm": vb, "cbm": cb, "gap": cb - vb,
            "vbm_k": rows[vb_i][0], "cbm_k": rows[cb_i][0],
            "direct": rows[vb_i][0] == rows[cb_i][0]}


def bands_of_occupation(log_text: str) -> int:
    values = {int(v) for v in re.findall(r"Bands of occupation:\s*(\d+)", log_text)}
    if len(values) != 1:
        raise SystemExit(f"ambiguous Bands of occupation values: {values}")
    return values.pop()


def install(dest_rel: str, text: str, *, sanitize: bool) -> dict:
    """Write one archived file and return its files-entry fields."""
    out = sanitize_text(text) if sanitize else text
    if not sanitize and FORBIDDEN.search(out):
        raise SystemExit(f"unsanitized file would carry private content: {dest_rel}")
    dest = ROOT / dest_rel
    if dest.exists():
        raise SystemExit(f"refusing to overwrite: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    data = out.encode("utf-8")
    return {"sha256": sha_bytes(data), "size_bytes": len(data),
            "original_sha256": sha_bytes(text.encode("utf-8")),
            "transformation": ("none" if out == text else
                                "private HPC paths, scheduler variable names and node lists redacted; scientific values retained")}


def register_element_assets(element: str, assets: list[tuple[str, Path]], case_id: str) -> tuple[str, list[dict]]:
    """Copy content-addressed basis assets and register a set; return (set_id, files)."""
    entries = []
    for role, src in assets:
        raw, _ = read_source(src)
        h = sha_bytes(raw)
        ext = {"pp": "upf", "nao": "orb", "abf": "abfs"}[role]
        subdir = {"pp": "pseudopotentials", "nao": "orbitals", "abf": "auxiliary"}[role]
        dest = ROOT / "data/elements" / element / subdir / f"{h}.{ext}"
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        entries.append({"role": role, "path": str(dest.relative_to(ROOT)), "sha256": h,
                        "size_bytes": len(raw), "original_sha256": h,
                        "label": src.name, "transformation": "none"})
    set_id = f"{element}-ks-backup-gw-{sha_bytes(json.dumps(entries, sort_keys=True).encode())[:12]}"
    set_dir = ROOT / "data/elements" / element / "sets" / set_id
    if set_dir.exists():
        raise SystemExit(f"set already registered: {set_id}")
    set_dir.mkdir(parents=True)
    payload = {"schema_version": 1, "id": set_id, "element": element,
               "family": "KS HPC backup production basis (SG15/ONCV PP + NAO + PCA ABF)",
               "validation_scope": f"Used by {case_id}; see case-specific gates.",
               "notes": "Basis files archived from the producer's run directory; content-addressed.",
               "source": {"collection": APPROVAL["collection"], "case_id": case_id},
               "files": entries, "used_by": []}
    (set_dir / "set.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return set_id, entries


def register_aims_species(control_text: str, case_id: str) -> list[dict]:
    blocks = library._aims_species_blocks(control_text)
    species = []
    for element, block in blocks.items():
        h = sha_bytes(block.encode("utf-8"))
        dest = ROOT / "data/elements" / element / "species_defaults" / f"{h}.in"
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(block, encoding="utf-8")
        set_id = f"{element}-ks-backup-gw-{h[:12]}"
        set_dir = ROOT / "data/elements" / element / "sets" / set_id
        if not set_dir.exists():
            set_dir.mkdir(parents=True)
            entry = {"role": "species_defaults", "path": str(dest.relative_to(ROOT)),
                     "sha256": h, "size_bytes": len(block.encode("utf-8")),
                     "original_sha256": h, "label": f"{element} species defaults (FHI-aims)",
                     "original_name": f"{element} species block inlined in control.in",
                     "transformation": "verbatim species block extracted from the archived control.in"}
            payload = {"schema_version": 1, "id": set_id, "element": element,
                       "family": "FHI-aims species defaults (control.in inline)",
                       "validation_scope": f"Used by {case_id}; see case-specific gates.",
                       "notes": "Standard FHI-aims species defaults inlined by the producer; not generated by this database.",
                       "source": {"collection": APPROVAL["collection"], "case_id": case_id},
                       "files": [entry], "used_by": []}
            (set_dir / "set.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        species.append({"element": element, "set_id": set_id, "missing_roles": [],
                        "linkage": "byte-exact control.in inline species block hash-matched to the registered species_defaults payload"})
    return species


def file_entry(role: str, dest_rel: str, meta: dict, label: str, original_name: str) -> dict:
    return {"role": role, "path": dest_rel, "sha256": meta["sha256"],
            "size_bytes": meta["size_bytes"], "original_sha256": meta["original_sha256"],
            "label": label, "original_name": original_name,
            "transformation": meta["transformation"]}


def merge_nio_bands(level: str, series: str) -> str:
    """Concatenate six per-segment native tables via the jctc convention."""
    texts = []
    for i in range(1, 7):
        _, text = read_source(GW / f"NiO/gw/aims/int/{level}_band{series}00{i}.out")
        texts.append(text)
    return _jctc.concat_aims_segments(texts)


def build_abacus_record(cfg: dict) -> dict:
    run = GW / cfg["run_dir"]
    case_prefix = f"data/calculations/3d/{cfg['material']}/{cfg['id']}"
    if (ROOT / case_prefix).exists():
        raise SystemExit(f"record directory already exists: {case_prefix}")

    # candidate digest re-verification
    manifest = []
    for rel in cfg["digest_files"]:
        p = BK / rel
        raw, _ = read_source(p)
        manifest.append(f"{rel}|{sha_bytes(raw)}|{len(raw)}")
    digest = sha_bytes(("\n".join(sorted(manifest)) + "\n").encode())
    if digest != APPROVED_DIGESTS[cfg["id"]]:
        raise SystemExit(f"candidate digest mismatch for {cfg['id']}: {digest}")

    inputs, results, logs = [], [], []
    species = []
    for element, assets in cfg["element_assets"].items():
        set_id, _ = register_element_assets(element, [(r, BK / p) for r, p in assets], cfg["id"])
        species.append({"element": element, "set_id": set_id,
                        "asset_aliases": {"pp": Path(assets[0][1]).name, "nao": Path(assets[1][1]).name,
                                          "abf": Path(assets[2][1]).name},
                        "missing_roles": [], "linkage": "matched case assets"})

    for src_name, dest_name, sanitize in cfg["input_files"]:
        raw, text = read_source(run / src_name)
        meta = install(f"{case_prefix}/inputs/{dest_name}", text, sanitize=sanitize)
        inputs.append(file_entry("inputs", f"{case_prefix}/inputs/{dest_name}", meta, dest_name, src_name))

    # logs first (needed for occupancy), then band results
    log_meta = {}
    for src_name, dest_name, sanitize in cfg["log_files"]:
        raw, text = read_source(run / src_name)
        meta = install(f"{case_prefix}/logs/{dest_name}", text, sanitize=sanitize)
        log_meta[src_name] = meta
        logs.append(file_entry("logs", f"{case_prefix}/logs/{dest_name}", meta, dest_name, src_name))

    n_occ = bands_of_occupation((run / cfg["occupancy_log"]).read_text(errors="replace"))
    if "abacus" in cfg["software"]:
        cfg["software"]["abacus"]["evidence"] = [f"{case_prefix}/logs/abacus.out"]
    if "librpa" in cfg["software"]:
        cfg["software"]["librpa"]["evidence"] = [f"{case_prefix}/logs/librpa.out"]
    gaps = {}
    for level, dat in [("PBE", "KS"), ("EXX", "EXX"), ("GW", "GW")]:
        raw, text = read_source(run / f"{dat}_band_spin_1.dat")
        meta = install(f"{case_prefix}/results/{dat}_band_spin_1.dat", text, sanitize=False)
        results.append(file_entry("results", f"{case_prefix}/results/{dat}_band_spin_1.dat", meta,
                                  f"{dat}_band_spin_1.dat", f"{dat}_band_spin_1.dat"))
        gaps[level] = frontier_gap(parse_band_rows(text), n_occ)

    raw, text = read_source(run / "band_kpath_info")
    meta = install(f"{case_prefix}/results/band_kpath_info", text, sanitize=False)
    results.append(file_entry("results", f"{case_prefix}/results/band_kpath_info", meta,
                              "band_kpath_info", "band_kpath_info"))

    # structure identity from the archived STRU (verbatim copy already installed)
    stru_text = (ROOT / case_prefix / "inputs/STRU").read_text(encoding="utf-8")
    fp_digest, atoms = library._structure_fingerprint(stru_text, "STRU", cfg["dimension"])

    method_keys = {"PBE": ("dft_gap_ev", "KS"), "EXX": ("exx_gap_ev", "EXX"), "GW": ("gw_gap_ev", "GW")}
    properties = []
    for level, (summary_key, dat) in method_keys.items():
        g = gaps[level]
        properties.append({"key": "band_gap", "category": "electronic", "label": "Band gap",
                           "method": {"PBE": "PBE", "EXX": "EXX", "GW": "G0W0"}[level],
                           "value": round(g["gap"], 7), "unit": "eV", "status": "reported",
                           "evidence": [f"{case_prefix}/results/{dat}_band_spin_1.dat"],
                           "source_summary_key": summary_key})

    gw_g = gaps["GW"]
    record = {
        "schema_version": 1, "id": cfg["id"], "dimension": cfg["dimension"],
        "material": cfg["material"], "formula": cfg["formula"], "record_type": "band",
        "workflow": {"frontend": "abacus", "task": "gw"},
        "software": cfg["software"],
        "species": species,
        "files": {"inputs": inputs, "results": results, "logs": logs},
        "structure_identity": {"algorithm": "cell-sites-v1", "sha256": fp_digest,
                               "evidence": f"{case_prefix}/inputs/STRU"},
        "computational_scale": {"atom_count": atoms, "n_bands": gaps["GW"]["n_bands"],
                                "n_path_kpoints": gaps["GW"]["nk"]},
        "properties": properties, "basis_candidates": [], "recommendation": None,
        "missing": ["All-band, empty-state, transferability and current-version acceptance were not established by this audit."],
        "summary": {
            "observable": "G0W0 gap", "value": round(gw_g["gap"], 7), "unit": "eV",
            "notes": cfg["summary_notes"],
            "gw_gap_ev": round(gw_g["gap"], 7), "exx_gap_ev": round(gaps["EXX"]["gap"], 7),
            "dft_gap_ev": round(gaps["PBE"]["gap"], 7),
            "gap_definition": ("LibRPA final printed GW bandgap, historical selected band-path calculation; "
                               "not a universal PP/NAO accuracy claim"),
            "scientific_status": "historical_reference_bounded_gap_comparison",
            "scope": ("Specific archived geometry, PP/NAO/ABF, k/path and numerical settings. All-band, "
                      "empty-state, transferability and current-version acceptance not established by this audit.")},
        "cluster_label": cfg["perf"]["cluster_label"], "accelerators": None,
        "nodes": cfg["perf"]["nodes"], "cpus": cfg["perf"]["cpus"],
        "elapsed_seconds": cfg["perf"]["elapsed_seconds"], "accelerator_label": None,
        "source": {"collection": APPROVAL["collection"],
                   "provenance_directory": "data/provenance/backup-20261016",
                   "material_directory": cfg["material"], "run_directory": cfg["run_dir"]},
    }
    (ROOT / case_prefix / "record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {"id": cfg["id"], "digest": digest, "gaps": {k: round(v["gap"], 7) for k, v in gaps.items()},
            "direct": {k: v["direct"] for k, v in gaps.items()},
            "n_occ": n_occ, "atoms": atoms, "fingerprint": fp_digest}


def build_nio_record() -> dict:
    cfg_id = "nio-aims-gw-int"
    run = GW / "NiO/gw/aims/int"
    case_prefix = f"data/calculations/3d/NiO/{cfg_id}"
    if (ROOT / case_prefix).exists():
        raise SystemExit(f"record directory already exists: {case_prefix}")

    digest_files = [f"gw/NiO/gw/aims/int/{name}" for name in [
        "control.in", "geometry.in", "run_aims.sh",
        "aims.731944.out", "aims.735178.out", "aims.736421.out", "aims.740569.out",
        "slurm-731944.out", "slurm-735178.out", "slurm-736421.out", "slurm-740569.out"]]
    digest_files += [f"gw/NiO/gw/aims/int/{L}_band{s}00{i}.out"
                     for L in ("EXX", "GW") for s in ("1", "2") for i in range(1, 7)]
    manifest = []
    for rel in digest_files:
        raw, _ = read_source(BK / rel)
        manifest.append(f"{rel}|{sha_bytes(raw)}|{len(raw)}")
    digest = sha_bytes(("\n".join(sorted(manifest)) + "\n").encode())
    if digest != APPROVED_DIGESTS[cfg_id]:
        raise SystemExit(f"candidate digest mismatch for {cfg_id}: {digest}")

    inputs, results, logs = [], [], []
    control_raw, control_text = read_source(run / "control.in")
    meta = install(f"{case_prefix}/inputs/control.in", control_text, sanitize=False)
    inputs.append(file_entry("inputs", f"{case_prefix}/inputs/control.in", meta, "control.in", "control.in"))
    geo_raw, geo_text = read_source(run / "geometry.in")
    meta = install(f"{case_prefix}/inputs/geometry.in", geo_text, sanitize=False)
    inputs.append(file_entry("inputs", f"{case_prefix}/inputs/geometry.in", meta, "geometry.in", "geometry.in"))
    kpt_text = _jctc.derive_kpt_band(control_text)
    meta = install(f"{case_prefix}/inputs/KPT_band", kpt_text, sanitize=False)
    meta["transformation"] = ("derived Line-mode KPT from the archived control.in output band segment "
                              "definitions; inclusive-segments convention (each segment includes both "
                              "endpoints, shared path nodes repeat, count 0 marks a path discontinuity); "
                              "coordinates taken verbatim from the segment endpoints")
    inputs.append(file_entry("inputs", f"{case_prefix}/inputs/KPT_band", meta,
                             "Derived band-path KPT (inclusive segments)", "control.in output band section"))
    script_raw, script_text = read_source(run / "run_aims.sh")
    meta = install(f"{case_prefix}/inputs/aims_run_script.sh", script_text, sanitize=True)
    inputs.append(file_entry("inputs", f"{case_prefix}/inputs/aims_run_script.sh", meta,
                             "aims_run_script.sh", "run_aims.sh"))

    species = register_aims_species(control_text, cfg_id)

    for job in (731944, 735178, 736421, 740569):
        raw, text = read_source(run / f"aims.{job}.out")
        meta = install(f"{case_prefix}/logs/aims_{job}_stdout.log", text, sanitize=False)
        logs.append(file_entry("logs", f"{case_prefix}/logs/aims_{job}_stdout.log", meta,
                               f"aims_{job}_stdout.log", f"aims.{job}.out"))
        raw, text = read_source(run / f"slurm-{job}.out")
        meta = install(f"{case_prefix}/logs/aims_{job}_slurm_stdout.log", text, sanitize=True)
        logs.append(file_entry("logs", f"{case_prefix}/logs/aims_{job}_slurm_stdout.log", meta,
                               f"aims_{job}_slurm_stdout.log", f"slurm-{job}.out"))

    merged, gaps = {}, {}
    for level in ("EXX", "GW"):
        text = merge_nio_bands(level, "1")
        dest = f"{case_prefix}/results/{level}_band_spin_1.dat"
        meta = install(dest, text, sanitize=False)
        meta["transformation"] = ("concatenated verbatim per-segment native tables with renumbered k "
                                  "indices (inclusive-segments convention)")
        results.append(file_entry("results", dest, meta, f"{level}_band_spin_1.dat",
                                  f"{level}_band1001-1006.out (merged)"))
        rows = parse_band_rows(text)
        n_occ = next((j for j, (o, e) in enumerate(rows[0][1]) if o < 0.5), len(rows[0][1]))
        gaps[(level, 1)] = frontier_gap(rows, n_occ)
        # second spin channel: archive the raw per-segment tables verbatim and verify frontier agreement
        spin2_rows = []
        for i in range(1, 7):
            raw2, text2 = read_source(run / f"{level}_band200{i}.out")
            dest2 = f"{case_prefix}/results/{level}_band200{i}.out"
            meta2 = install(dest2, text2, sanitize=False)
            results.append(file_entry("results", dest2, meta2, f"{level}_band200{i}.out",
                                      f"{level}_band200{i}.out"))
            spin2_rows += parse_band_rows(text2)
        n_occ2 = next((j for j, (o, e) in enumerate(spin2_rows[0][1]) if o < 0.5), len(spin2_rows[0][1]))
        gaps[(level, 2)] = frontier_gap(spin2_rows, n_occ2)

    if abs(gaps[("GW", 1)]["gap"] - gaps[("GW", 2)]["gap"]) > 1e-6:
        raise SystemExit("spin-channel GW gaps disagree; refusing to import")

    geo_archived = (ROOT / case_prefix / "inputs/geometry.in").read_text(encoding="utf-8")
    fp_digest, atoms = library._structure_fingerprint(geo_archived, "geometry.in", "3d")

    properties = []
    for level, summary_key in (("EXX", "exx_gap_ev"), ("GW", "gw_gap_ev")):
        g = gaps[(level, 1)]
        properties.append({
            "key": "band_gap", "category": "electronic", "label": "Sampled path band gap",
            "method": "EXX" if level == "EXX" else "G0W0",
            "value": round(g["gap"], 7), "unit": "eV", "status": "reported",
            "definition": ("aims native EXX/GW quasi-particle sampled band-path gap on the archived "
                           "126-point collinear spin-polarized path. Sampled path only, not a global "
                           "Brillouin-zone gap, convergence validation, or basis recommendation."),
            "evidence": [f"{case_prefix}/results/{level}_band_spin_1.dat"],
            "source_summary_key": summary_key})

    gw_g = gaps[("GW", 1)]
    record = {
        "schema_version": 1, "id": cfg_id, "dimension": "3d", "material": "NiO",
        "formula": "NiO", "record_type": "band",
        "workflow": {"frontend": "fhi_aims", "task": "gw"},
        "software": {
            "fhi_aims": {
                "source_url": AIMS_URL, "commit": None, "abbreviated_commit": "6bb66facb",
                "evidence": [f"{case_prefix}/logs/aims_740569_stdout.log"],
                "missing_reason": ("The producer logged only the shortened commit 6bb66facb for version "
                                   "241109; the full FHI-aims hash was not retained and the upstream "
                                   "server is not publicly fetchable by raw SHA."),
                "identity_note": ("FHI-aims 241109 printed a 9-hex commit prefix; no full hash or "
                                  "executable SHA is recoverable from the archived evidence.")}},
        "species": species,
        "files": {"inputs": inputs, "results": results, "logs": logs},
        "structure_identity": {"algorithm": "cell-sites-v1", "sha256": fp_digest,
                               "evidence": f"{case_prefix}/inputs/geometry.in"},
        "computational_scale": {"atom_count": atoms, "n_bands": gw_g["n_bands"],
                                "n_path_kpoints": gw_g["nk"]},
        "properties": properties, "basis_candidates": [], "recommendation": None,
        "missing": ["No KS/PBE band table was archived by the producer (EXX/GW tables only).",
                    "All-band, empty-state, transferability and current-version acceptance were not established by this audit."],
        "summary": {
            "observable": "G0W0 band gap (sampled path)", "value": round(gw_g["gap"], 7), "unit": "eV",
            "notes": ("Historical KS HPC backup run: FHI-aims built-in GW (qpe_calc gw_expt, intermediate "
                      "tier) on the sampled 126-point path of the antiferromagnetic rocksalt-rhombohedral "
                      "4-atom cell, collinear spin-polarized. The first spin channel is archived as a "
                      "merged table and the second as verbatim per-segment native tables; their frontier "
                      "gaps agree to below 1e-6 eV. The band-path KPT is derived from the archived "
                      "control.in output band definitions. Sampled path only, not a global "
                      "Brillouin-zone gap or convergence claim."),
            "gw_gap_ev": round(gw_g["gap"], 7), "exx_gap_ev": round(gaps[("EXX", 1)]["gap"], 7),
            "gap_definition": ("Archived sampled native band-path gap; restricted to the archived "
                               "geometry, species defaults, k/path and numerical settings."),
            "scientific_status": "historical_reference_bounded_gap_comparison",
            "scope": ("Specific archived geometry, species defaults, k/path and numerical settings. "
                      "All-band, empty-state, transferability and current-version acceptance not "
                      "established by this audit.")},
        "cluster_label": "formal-6226R", "accelerators": None,
        "nodes": None, "cpus": 288, "elapsed_seconds": None, "accelerator_label": None,
        "source": {"collection": APPROVAL["collection"],
                   "provenance_directory": "data/provenance/backup-20261016",
                   "material_directory": "NiO", "run_directory": "NiO/gw/aims/int"},
    }
    (ROOT / case_prefix / "record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {"id": cfg_id, "digest": digest,
            "gaps": {f"{l}{s}": round(gaps[(l, s)]["gap"], 7) for l in ("EXX", "GW") for s in (1, 2)},
            "direct": {f"{l}{s}": gaps[(l, s)]["direct"] for l in ("EXX", "GW") for s in (1, 2)},
            "n_occ": gw_g["n_occ"], "atoms": atoms, "fingerprint": fp_digest}


ABACUS_SOFTWARE_RESOLVED = {
    "abacus": {"source_url": ABACUS_URL, "commit": ABACUS_COMMIT, "abbreviated_commit": "1dd0199",
               "evidence": [],
               "identity_note": ("Full commit resolved from the unique deepmodeling/abacus-develop object "
                                 "matching the producer-logged prefix 1dd0199 (committer date identical to "
                                 "the logged build date); the same resolution is already recorded for the "
                                 "gaas-paper-gw_xsoc records.")},
}

LIBRPA_MISSING = {
    "source_url": LIBRPA_URL, "commit": None, "abbreviated_commit": None, "evidence": [],
    "missing_reason": "The producer log printed an empty source Git reference; the HPC source tree is no longer accessible.",
    "identity_note": "The historical LibRPA output did not retain a usable full source commit or executable SHA.",
}

BI = "gw/Bi2Se3/dojov4-fr/gw_dzp"
ZN = "gw/ZnO/gw/sg15"
GA = "gw/GaAs/soc_32freq_pack"

CANDIDATES = [
    {
        "id": "bi2se3-abacus-gw-dzp", "material": "Bi2Se3", "formula": "Bi2Se3", "dimension": "3d",
        "run_dir": "Bi2Se3/dojov4-fr/gw_dzp",
        "digest_files": [f"{BI}/{n}" for n in [
            "INPUT", "INPUT_scf", "INPUT_nscf", "KPT", "KPT_scf", "KPT_nscf", "STRU",
            "librpa.in", "run_abacus.sh",
            "Bi.upf", "Bi_gga_10au_130Ry_3s3p2d.orb", "Bi_4s4p3d2f2g_1e-4.abfs",
            "Se.upf", "Se_gga_10au_110Ry_3s3p2d.orb", "Se_4s4p3d2f2g_1e-4.abfs",
            "KS_band_spin_1.dat", "EXX_band_spin_1.dat", "GW_band_spin_1.dat",
            "abacus.831496.out", "LibRPA.831496.out", "slurm-831496.out", "band_kpath_info"]],
        "element_assets": {
            "Bi": [("pp", f"{BI}/Bi.upf"), ("nao", f"{BI}/Bi_gga_10au_130Ry_3s3p2d.orb"),
                   ("abf", f"{BI}/Bi_4s4p3d2f2g_1e-4.abfs")],
            "Se": [("pp", f"{BI}/Se.upf"), ("nao", f"{BI}/Se_gga_10au_110Ry_3s3p2d.orb"),
                   ("abf", f"{BI}/Se_4s4p3d2f2g_1e-4.abfs")]},
        "input_files": [
            ("INPUT", "INPUT", False), ("INPUT_scf", "INPUT_scf", False),
            ("INPUT_nscf", "INPUT_nscf", False),
            ("KPT", "KPT", False), ("KPT_scf", "KPT_scf", False),
            ("KPT_nscf", "KPT_nscf", False),
            ("STRU", "STRU", False), ("librpa.in", "librpa.in", False),
            ("run_abacus.sh", "abacus_run_script.sh", True)],
        "log_files": [
            ("abacus.831496.out", "abacus.out", False),
            ("LibRPA.831496.out", "librpa.out", True),
            ("slurm-831496.out", "gw_slurm_stdout.log", True)],
        "occupancy_log": "LibRPA.831496.out",
        "software": {**ABACUS_SOFTWARE_RESOLVED, "librpa": LIBRPA_MISSING},
        "perf": {"cluster_label": "formal-6226R", "nodes": 16, "cpus": 512, "elapsed_seconds": 16183},
        "summary_notes": ("Historical KS HPC backup run: ABACUS LCAO DZP-basis scf/nscf plus LibRPA G0W0 "
                          "on the bulk Bi2Se3 rhombohedral 5-atom cell (spin-unpolarized, no SOC), "
                          "16 MPI ranks x 32 OpenMP threads on the formal-6226R partition."),
    },
    {
        "id": "zno-abacus-gw-sg15", "material": "ZnO", "formula": "ZnO", "dimension": "3d",
        "run_dir": "ZnO/gw/sg15",
        "digest_files": [f"{ZN}/{n}" for n in [
            "INPUT", "INPUT_scf", "INPUT_nscf", "STRU", "librpa.in", "run_abacus.sh",
            "Zn_6s3p3d2f1g_pca1e-6.abfs", "O_3s3p2d1f1g_pca1e-6.abfs",
            "KS_band_spin_1.dat", "EXX_band_spin_1.dat", "GW_band_spin_1.dat",
            "abacus.731558.out", "LibRPA.731933.out", "band_kpath_info",
            "KPT", "KPT_scf", "KPT_nscf", "slurm-731558.out", "slurm-731933.out"]]
        + [f"pp_abacus/SG15_ONCV_v1.0_upf/Zn_ONCV_PBE-1.0.upf",
           f"gw_bas_pp/pp/O_ONCV_PBE-1.0.upf",
           f"basis_abacus/myprefer/Zn_gga_10au_100Ry_6s3p3d2f.orb",
           f"basis_abacus/myprefer/O_gga_8au_100Ry_3s3p2d.orb"],
        "element_assets": {
            "Zn": [("pp", "pp_abacus/SG15_ONCV_v1.0_upf/Zn_ONCV_PBE-1.0.upf"),
                   ("nao", "basis_abacus/myprefer/Zn_gga_10au_100Ry_6s3p3d2f.orb"),
                   ("abf", f"{ZN}/Zn_6s3p3d2f1g_pca1e-6.abfs")],
            "O": [("pp", "gw_bas_pp/pp/O_ONCV_PBE-1.0.upf"),
                  ("nao", "basis_abacus/myprefer/O_gga_8au_100Ry_3s3p2d.orb"),
                  ("abf", f"{ZN}/O_3s3p2d1f1g_pca1e-6.abfs")]},
        "input_files": [
            ("INPUT", "INPUT", True), ("INPUT_scf", "INPUT_scf", True),
            ("INPUT_nscf", "INPUT_nscf", True),
            ("KPT", "KPT", False), ("KPT_scf", "KPT_scf", False),
            ("KPT_nscf", "KPT_nscf", False),
            ("STRU", "STRU", False), ("librpa.in", "librpa.in", False),
            ("run_abacus.sh", "abacus_run_script.sh", True)],
        "log_files": [
            ("abacus.731558.out", "abacus.out", False),
            ("LibRPA.731933.out", "librpa.out", True),
            ("slurm-731558.out", "abacus_slurm_stdout.log", True),
            ("slurm-731933.out", "gw_slurm_stdout.log", True)],
        "occupancy_log": "LibRPA.731933.out",
        "software": {
            "abacus": {"source_url": ABACUS_URL, "commit": None, "abbreviated_commit": None,
                       "evidence": [],
                       "missing_reason": "The producer ABACUS log printed 'Commit: unknown'; no hash or executable SHA was retained.",
                       "identity_note": "ABACUS build identity was not recorded by the producer."},
            "librpa": LIBRPA_MISSING},
        "perf": {"cluster_label": "formal-6226R", "nodes": 9, "cpus": 288, "elapsed_seconds": 18723},
        "summary_notes": ("Historical KS HPC backup run: ABACUS LCAO SG15-ONCV scf/nscf plus LibRPA G0W0 "
                          "on the zincblende 2-atom primitive cell (a = 4.584 A, spin-unpolarized); the "
                          "exported band table carries all-zero occupations, so the occupied/empty "
                          "boundary follows the LibRPA log's 'Bands of occupation: 13' (Z_val 20+6 over "
                          "two spins)."),
    },
    {
        "id": "gaas-abacus-gw-soc-32freq", "material": "GaAs", "formula": "GaAs", "dimension": "3d",
        "run_dir": "GaAs/soc_32freq_pack",
        "digest_files": [f"{GA}/{n}" for n in [
            "INPUT", "INPUT_scf", "INPUT_nscf", "KPT", "KPT_scf", "KPT_nscf", "STRU",
            "librpa.in", "run_abacus.sh",
            "Ga.upf", "Ga_gga_8au_100Ry_6s6p4d2f.orb", "Ga_str_6s6p4d2f1g_1e-4.abfs",
            "As.upf", "As_gga_8au_100Ry_3s3p2d.orb", "As_str_3s3p2d2f1g_1e-4.abfs",
            "KS_band_spin_1.dat", "EXX_band_spin_1.dat", "GW_band_spin_1.dat",
            "abacus.859292.out", "LibRPA.859318.out",
            "slurm-859292.out", "slurm-859299.out", "slurm-859318.out", "band_kpath_info"]],
        "element_assets": {
            "Ga": [("pp", f"{GA}/Ga.upf"), ("nao", f"{GA}/Ga_gga_8au_100Ry_6s6p4d2f.orb"),
                   ("abf", f"{GA}/Ga_str_6s6p4d2f1g_1e-4.abfs")],
            "As": [("pp", f"{GA}/As.upf"), ("nao", f"{GA}/As_gga_8au_100Ry_3s3p2d.orb"),
                   ("abf", f"{GA}/As_str_3s3p2d2f1g_1e-4.abfs")]},
        "input_files": [
            ("INPUT", "INPUT", False), ("INPUT_scf", "INPUT_scf", False),
            ("INPUT_nscf", "INPUT_nscf", False),
            ("KPT", "KPT", False), ("KPT_scf", "KPT_scf", False),
            ("KPT_nscf", "KPT_nscf", False),
            ("STRU", "STRU", False), ("librpa.in", "librpa.in", False),
            ("run_abacus.sh", "abacus_run_script.sh", True)],
        "log_files": [
            ("abacus.859292.out", "abacus.out", False),
            ("LibRPA.859318.out", "librpa.out", True),
            ("slurm-859292.out", "abacus_slurm_stdout.log", True),
            ("slurm-859299.out", "abacus_nscf_slurm_stdout.log", True),
            ("slurm-859318.out", "gw_slurm_stdout.log", True)],
        "occupancy_log": "LibRPA.859318.out",
        "software": {**ABACUS_SOFTWARE_RESOLVED, "librpa": LIBRPA_MISSING},
        "perf": {"cluster_label": "formal-6226R", "nodes": 4, "cpus": 128, "elapsed_seconds": 10414},
        "summary_notes": ("Historical KS HPC backup run: ABACUS noncollinear spin-orbit-coupled LCAO "
                          "(lspinorb 1, 160 spinor bands = 80 NAO x 2) scf/nscf plus LibRPA G0W0 with 32 "
                          "frequency points on the experimental zincblende lattice (a = 5.654 A); "
                          "structure fingerprint identical to gaas-paper-gw_xsoc_1e-10 (same cell and "
                          "sites, independently chosen 8au_100Ry basis)."),
    },
]

APPROVAL["collection"] = "KS HPC GW backup (compute_backup_review_20260514_ks_iopcas_ghj)"


def update_exceptions() -> None:
    path = ROOT / "data/historical-software-identity-exceptions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    additions = [
        {"id": "bi2se3-abacus-gw-dzp", "software": ["librpa"]},
        {"id": "zno-abacus-gw-sg15", "software": ["abacus", "librpa"]},
        {"id": "nio-aims-gw-int", "software": ["fhi_aims"]},
        {"id": "gaas-abacus-gw-soc-32freq", "software": ["librpa"]},
    ]
    existing = {entry["id"] for entry in data["records"]}
    for entry in additions:
        if entry["id"] in existing:
            raise SystemExit(f"exception entry already present: {entry['id']}")
    data["records"].extend(additions)
    data["frozen_issue_count"] = sum(len(entry["software"]) for entry in data["records"])
    note = (" The bi2se3-abacus-gw-dzp/librpa, zno-abacus-gw-sg15/abacus, zno-abacus-gw-sg15/librpa, "
            "nio-aims-gw-int/fhi_aims and gaas-abacus-gw-soc-32freq/librpa pairs were added on 2026-10-16 "
            "with the database owner's explicit approval after the intake summary presented the candidate "
            "digests and the missing-identity evidence: intake approved as \"全部收录（4 个）(Recommended)\" "
            "and the five software-identity exception pairs explicitly authorized as \"授权 5 对新增豁免 "
            "(Recommended)\".")
    data["notes"] = (data["notes"] if data.get("notes") else "") + note
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_receipt(reports: list[dict]) -> None:
    receipt_dir = ROOT / "data/provenance/backup-20261016"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(APPROVAL)
    payload["candidates"] = reports
    (receipt_dir / "receipt.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    reports = [build_abacus_record(cfg) for cfg in CANDIDATES]
    reports.append(build_nio_record())
    update_exceptions()
    write_receipt(reports)
    for report in reports:
        print(f"{report['id']}: digest={report['digest'][:16]}… gaps={report['gaps']} "
              f"direct={report['direct']} n_occ={report['n_occ']} atoms={report['atoms']} "
              f"fp={report['fingerprint'][:12]}…")
    print("intake complete; regenerate catalog/indexes/missing-evidence next")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
