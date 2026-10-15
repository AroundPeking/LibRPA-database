#!/usr/bin/env python3
"""JCTC 6c00618 支撑数据一次性入库（FHI-aims + LibRPA 带结构，24 材料）。

生成 73 条 band 记录（24 条纯 FHI-aims GW、48 条 LibRPA g0w0_band、1 条 GaAs
聚焦重跑），注册 FHI-aims species_defaults 基组集，从 control.in 的 output band
段定义派生 inclusive 段约定 KPT_band（count 0 标记路径断点），拼接 aims 分段
GW 表并重编号原生 k 索引，脱敏私有集群路径，为不可恢复的 FHI-aims 241121
缩写提交扩展历史软件身份例外基线，并归档 SI 溯源文档。

图生成（generate_band_figures.py --write）之后用 --post-pass 补写 GW 受限
属性与 summary。默认只做只读核验与计划报告；--write 才落盘。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


library = _load("library", ROOT / "scripts" / "library.py")
figures = _load("gbf", ROOT / "scripts" / "generate_band_figures.py")
plot_bands = figures.plot_bands

TAR_NAME = "jctc_6c00618_data_20261015.tar.gz"
PROVENANCE_REL = "data/provenance/jctc-6c00618"
COLLECTION = "JCTC 6c00618 FHI-aims + LibRPA band-structure supporting data (24 materials)"
LIBRPA_COMMIT = "6dc9b9074704d92bad4b24264a17cc6e6456adbf"
AIMS_RESOLVED_COMMIT = "8e2fc2584a45c560fe8d192411ef7a108ec4f2a5"
AIMS_LOGGED_PREFIX = {"250507": "8e2fc2584", "241121": "b5eacca14"}
AIMS_SOURCE_URL = "https://fhi-aims.org"
LIBRPA_SOURCE_URL = "https://github.com/AESM-Group/LibRPA"
EXCEPTIONS_REL = "data/historical-software-identity-exceptions.json"

# 生产者日志中的集群本地路径统一脱敏为中性 /HPC 前缀。
SANITIZE_RULES = [(re.compile(r"/user/minye\.zhang(?:/u\d+)?"), "/HPC"),
                  (re.compile(r"/home/" + r"apps"), "/HPC/apps")]
SANITIZE_DESCRIPTION = ("private cluster software and home path prefixes redacted to a neutral "
                        "/HPC prefix; scientific values retained")

RESOLVED_NOTE = ("Full commit resolved from the unique object matching the producer-logged "
                 "prefix 8e2fc2584 in the local FHI-aims clone (upstream master unshallowed); "
                 "the producer printed only the shortened ID.")
UNRESOLVED_NOTE = ("The producer logged only the shortened ID b5eacca14 (version 241121). "
                   "The full commit is not recoverable: the prefix matches no object reachable "
                   "from the local FHI-aims clone, and the upstream server rejects fetching a raw SHA.")
LIBRPA_NOTE = ("The archived LibRPA.out prints the full 40-hex source hash on branch "
               "develop_backup_before_soc (v0.4.0, whose QPE-solver NaN bug is documented in the "
               "supporting-data README).")

PAYLOADS: dict[str, bytes] = {}


def sha256b(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def as_temp_path(text: str, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as handle:
        handle.write(text)
    return Path(handle.name)


def parse_aims_identity(text: str) -> tuple[str, str]:
    version = re.search(r"(?m)^\s*FHI-aims version\s*:\s*(\S+)", text)
    commit = re.search(r"(?m)^\s*Commit number\s*:\s*(\S+)", text)
    if not version or not commit:
        raise ValueError("aims.out has no FHI-aims version/commit banner")
    return version.group(1), commit.group(1)


def aims_software(version: str, logged: str, evidence: str) -> dict:
    if version not in AIMS_LOGGED_PREFIX or logged != AIMS_LOGGED_PREFIX[version]:
        raise ValueError(f"unmapped FHI-aims identity {version}/{logged}")
    if version == "250507":
        return {"source_url": AIMS_SOURCE_URL, "commit": AIMS_RESOLVED_COMMIT,
                "abbreviated_commit": logged, "evidence": [evidence],
                "identity_note": RESOLVED_NOTE}
    return {"source_url": AIMS_SOURCE_URL, "commit": None, "abbreviated_commit": logged,
            "evidence": [evidence],
            "missing_reason": "The producer logged only the shortened commit b5eacca14; "
                              "the full FHI-aims 241121 hash was not retained.",
            "identity_note": UNRESOLVED_NOTE}


def derive_kpt_band(control_text: str) -> str:
    """control.in 的 output band 段定义 → inclusive 段约定 Line KPT。

    每段含双端点；段间断点（Setyawan-Curtarolo 路径的 K|U 型跳变）落成
    count 0 跳变节点；最后一段终点为 count 1 端点节点。
    """
    segs = re.findall(r"(?m)^\s*output\s+band\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+"
                      r"(\d+)\s+(\S+)\s*(\S*)", control_text)
    if not segs:
        raise ValueError("control.in has no output band segments")
    nodes: list[tuple[tuple[float, float, float], int, str]] = []
    for index, seg in enumerate(segs):
        start = (float(seg[0]), float(seg[1]), float(seg[2]))
        count, start_label = int(seg[6]), seg[7]
        if index == 0:
            nodes.append((start, count, start_label))
            continue
        prev_end = (float(segs[index - 1][3]), float(segs[index - 1][4]), float(segs[index - 1][5]))
        if all(abs(a - b) <= 1e-6 for a, b in zip(start, prev_end)):
            nodes.append((start, count, start_label))
        else:
            nodes.append((prev_end, 0, segs[index - 1][8] or segs[index - 1][7]))
            nodes.append((start, count, start_label))
    last = segs[-1]
    nodes.append(((float(last[3]), float(last[4]), float(last[5])), 1, last[8] or last[7]))
    lines = ["# kpath_convention: inclusive-segments (FHI-aims output band; each segment "
             "includes both endpoints; shared path nodes repeat; count 0 marks a path "
             "discontinuity; derived from the archived control.in output band definitions)",
             "K_POINTS", str(len(nodes)), "line"]
    for (x, y, z), count, label in nodes:
        lines.append(f"{x:.5f} {y:.5f} {z:.5f} {count} # {label}")
    return "\n".join(lines) + "\n"


def concat_aims_segments(texts: list[str]) -> str:
    """按路径顺序拼接分段表并重编号原生 k 索引为严格递增 1..N。

    每行的坐标、占据与能量列逐字节保留；仅替换行首索引记号。
    """
    rows: list[str] = []
    index = 0
    for text in texts:
        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            match = re.match(r"(\s*)(\S+)(.*)", raw)
            if not match:
                raise ValueError("unparsable segment row")
            index += 1
            rows.append(match.group(1) + str(index) + match.group(3))
    if not rows:
        raise ValueError("empty segment tables")
    return "\n".join(rows) + "\n"


def sanitize(text: str) -> tuple[str, int]:
    changed = 0
    for pattern, replacement in SANITIZE_RULES:
        text, count = pattern.subn(replacement, text)
        changed += count
    return text, changed


def make_entry(rel: str, data: bytes, *, label: str, group: str, scientific_role: str,
               transformation: str, original_name: str | None = None,
               original_sha: str | None = None, extra: dict | None = None) -> dict:
    PAYLOADS[rel] = data
    entry = {"role": group, "path": rel, "sha256": sha256b(data), "size_bytes": len(data),
             "original_sha256": original_sha or sha256b(data), "label": label,
             "scientific_role": scientific_role, "transformation": transformation}
    if original_name:
        entry["original_name"] = original_name
    if extra:
        entry.update(extra)
    return entry


class Intake:
    def __init__(self, source: Path):
        self.source = source
        self.materials = sorted(p.name for p in source.iterdir()
                                if (p / "aims" / "control.in").is_file())
        if len(self.materials) != 24:
            raise ValueError(f"expected 24 materials, found {len(self.materials)}")
        self.set_registry: dict[tuple[str, str], str] = {}
        self.basis_writes: list[tuple[Path, bytes]] = []
        self.records: list[dict] = []
        self.exceptions: list[tuple[str, str]] = []
        self.report: dict = {"records": [], "sanitized_files": [], "species_sets": [],
                             "tsv_verified": 0, "exception_pairs": [], "record_count": 0,
                             "total_bytes": 0}

    # ---- basis registration -------------------------------------------------

    def register_species(self, element: str, block: str) -> str:
        digest = sha256b(block.encode("utf-8"))
        key = (element, digest)
        if key in self.set_registry:
            return self.set_registry[key]
        set_id = f"{element}-aims-jctc-{digest[:12]}"
        payload_rel = f"data/elements/{element}/species_defaults/{digest}.in"
        payload = block.encode("utf-8")
        PAYLOADS[payload_rel] = payload
        set_entry = {
            "schema_version": 1, "id": set_id, "element": element,
            "family": "FHI-aims species defaults (control.in inline)",
            "validation_scope": "Byte-extracted from the archived JCTC control.in; the same-record "
                                "binding proof is the inline block hash-match enforced by the validator.",
            "notes": "Standard FHI-aims species defaults as inlined by the producer; not generated "
                     "by this database.",
            "source": {"collection": COLLECTION, "tar": TAR_NAME},
            "files": [{
                "role": "species_defaults", "path": payload_rel, "sha256": digest,
                "size_bytes": len(payload), "original_sha256": digest,
                "label": f"{element} species defaults (FHI-aims)",
                "original_name": f"{element} species block inlined in control.in",
                "transformation": "verbatim species block extracted from the archived control.in",
            }],
            "generation_provenance": {"commit": None,
                                      "status": "FHI-aims bundled species defaults inlined by the "
                                                "producer; not generated by this database"},
            "used_by": [],
        }
        self.basis_writes.append((ROOT / f"data/elements/{element}/sets/{set_id}/set.json",
                                  json.dumps(set_entry, ensure_ascii=False, indent=2,
                                             allow_nan=False).encode("utf-8") + b"\n"))
        self.set_registry[key] = set_id
        self.report["species_sets"].append({"element": element, "set_id": set_id})
        return set_id

    # ---- shared record pieces ------------------------------------------------

    def basis_bindings(self, control_text: str) -> list[dict]:
        blocks = library._aims_species_blocks(control_text)
        return [{"element": element,
                 "set_id": self.register_species(element, blocks[element]),
                 "missing_roles": [],
                 "linkage": "byte-exact control.in inline species block hash-matched to the "
                            "registered species_defaults payload"}
                for element in sorted(blocks)]

    def kpt_entry(self, control_text: str, record_dir: str) -> dict:
        kpt_text = derive_kpt_band(control_text)
        return make_entry(f"{record_dir}/inputs/KPT_band", kpt_text.encode("utf-8"),
                          label="Derived band-path KPT (inclusive segments)",
                          group="inputs", scientific_role="aims_kpt_band_derived",
                          transformation="derived Line-mode KPT from the archived control.in "
                                         "output band segment definitions; inclusive-segments "
                                         "convention (each segment includes both endpoints, shared "
                                         "path nodes repeat, count 0 marks a path discontinuity); "
                                         "coordinates taken verbatim from the segment endpoints")

    def structure_identity(self, geometry_text: str, record_dir: str) -> tuple[dict, int]:
        digest, atom_count = library._structure_fingerprint(geometry_text, "geometry.in", "3d")
        return {"algorithm": "cell-sites-v1", "sha256": digest,
                "evidence": f"{record_dir}/inputs/geometry.in"}, atom_count

    def log_entry(self, path: Path, rel: str, label: str, scientific_role: str,
                  original_name: str) -> tuple[dict, str, str]:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        version, logged = parse_aims_identity(text)
        clean, changed = sanitize(text)
        data = clean.encode("utf-8") if changed else raw
        if changed:
            self.report["sanitized_files"].append(
                {"source": path.relative_to(self.source).as_posix(), "replacements": changed})
        entry = make_entry(rel, data, label=label, group="logs", scientific_role=scientific_role,
                           transformation=("none" if not changed else SANITIZE_DESCRIPTION),
                           original_name=original_name, original_sha=sha256b(raw))
        return entry, version, logged

    # ---- record builders -----------------------------------------------------

    def build_aims_record(self, material: str) -> dict:
        mat_dir = self.source / material
        record_id = f"{material.lower()}-jctc-aims-gw"
        record_dir = f"data/calculations/3d/{material}/{record_id}"
        control = (mat_dir / "aims" / "control.in").read_text(encoding="utf-8")
        geometry = (mat_dir / "aims" / "geometry.in").read_text(encoding="utf-8")
        seg_paths = [p for p in sorted((mat_dir / "aims").glob("GW_band*.out"), key=lambda p: p.name)
                     if re.fullmatch(r"GW_band\d{4}\.out", p.name)]
        if not seg_paths:
            raise ValueError(f"{material}: no aims GW segment tables")
        seg_texts = [p.read_text(encoding="utf-8") for p in seg_paths]
        concat = concat_aims_segments(seg_texts)
        table = plot_bands.parse_abacus_band_table(as_temp_path(concat, ".dat"))
        identity, atom_count = self.structure_identity(geometry, record_dir)
        log_entry, version, logged = self.log_entry(
            mat_dir / "aims" / "aims.out", f"{record_dir}/logs/aims.out",
            "FHI-aims GW band-structure run log", "aims_run_log", "aims.out")
        software = {"fhi_aims": aims_software(version, logged, f"{record_dir}/logs/aims.out")}
        if software["fhi_aims"]["commit"] is None:
            self.exceptions.append((record_id, "fhi_aims"))
        results = [
            make_entry(f"{record_dir}/results/GW_band_spin_1.dat", concat.encode("utf-8"),
                       label="FHI-aims GW band table (path segments concatenated)", group="results",
                       scientific_role="aims_gw_band_table",
                       transformation="derived by concatenating the archived per-segment "
                                      "GW_band1001-1010.out tables in path order and renumbering "
                                      "the native k-point index column to a strictly increasing "
                                      "1..N sequence; k-point coordinates, occupations and energies "
                                      "are byte-preserved per row",
                       extra={"source_segments": [{"name": p.name, "sha256": sha256b(t.encode("utf-8"))}
                                                  for p, t in zip(seg_paths, seg_texts)]}),
        ]
        tmp = mat_dir / "aims" / "tmp"
        if tmp.is_file():
            results.append(make_entry(f"{record_dir}/results/aims_qp_table_spin_1.dat",
                                       tmp.read_bytes(),
                                       label="FHI-aims GW quasi-particle spectrum (regular grid)",
                                       group="results", scientific_role="aims_qp_table",
                                       transformation="none", original_name="tmp"))
        return {
            "schema_version": 1, "id": record_id, "dimension": "3d", "material": material,
            "formula": material, "record_type": "band",
            "workflow": {"frontend": "fhi_aims", "task": "gw"},
            "software": software,
            "species": self.basis_bindings(control),
            "files": {"inputs": [
                make_entry(f"{record_dir}/inputs/control.in",
                           (mat_dir / "aims" / "control.in").read_bytes(),
                           label="FHI-aims control.in (GW run)", group="inputs",
                           scientific_role="aims_control_input", transformation="none",
                           original_name="control.in"),
                make_entry(f"{record_dir}/inputs/geometry.in",
                           (mat_dir / "aims" / "geometry.in").read_bytes(),
                           label="FHI-aims geometry.in (GW run)", group="inputs",
                           scientific_role="aims_geometry_input", transformation="none",
                           original_name="geometry.in"),
                self.kpt_entry(control, record_dir),
            ], "results": results, "logs": [log_entry], "figures": []},
            "structure_identity": identity,
            "computational_scale": {"atom_count": atom_count, "n_bands": len(table.energies[0]),
                                    "n_path_kpoints": len(table.x)},
            "properties": [], "basis_candidates": [], "recommendation": None, "missing": [],
            "summary": {
                "observable": "G0W0 band gap (sampled path)", "unit": "eV",
                "notes": "Historical journal supporting-data run: FHI-aims built-in GW on the "
                         "sampled native band path (inclusive segments, one discontinuity jump). "
                         "Sampled path only, not a global Brillouin-zone gap or convergence claim.",
            },
            "publication": {"status": "journal_supporting_information",
                            "manuscript_id": "jctc-6c00618"},
            "source": {"collection": COLLECTION, "tar": TAR_NAME,
                       "provenance_directory": PROVENANCE_REL,
                       "material_directory": material, "run_directory": "aims"},
        }

    def build_librpa_record(self, material: str, flavor: int) -> dict:
        mat_dir = self.source / material
        run = mat_dir / f"librpa-{flavor}"
        record_id = f"{material.lower()}-jctc-librpa-{flavor}"
        record_dir = f"data/calculations/3d/{material}/{record_id}"
        dataset = mat_dir / "dataset" / f"for_librpa-{flavor}"
        dataset_rel = f"dataset/for_librpa-{flavor}"
        if not dataset.is_dir():
            dataset = mat_dir / "dataset"
            dataset_rel = "dataset"
        control = (dataset / "control.in").read_text(encoding="utf-8")
        geometry = (dataset / "geometry.in").read_text(encoding="utf-8")
        identity, atom_count = self.structure_identity(geometry, record_dir)
        scf_log, version, logged = self.log_entry(
            dataset / "aims.out", f"{record_dir}/logs/aims.out",
            "FHI-aims dataset-generation SCF log", "aims_scf_log", "aims.out")
        librpa_raw = (run / "LibRPA.out").read_bytes()
        librpa_text = librpa_raw.decode("utf-8", errors="replace")
        librpa_clean, changed = sanitize(librpa_text)
        if changed:
            self.report["sanitized_files"].append(
                {"source": (run / "LibRPA.out").relative_to(self.source).as_posix(),
                 "replacements": changed})
        librpa_log = make_entry(
            f"{record_dir}/logs/librpa.out",
            librpa_clean.encode("utf-8") if changed else librpa_raw,
            label=f"LibRPA g0w0_band run log ({flavor}-point frequency grid)", group="logs",
            scientific_role="librpa_run_log",
            transformation=("none" if not changed else SANITIZE_DESCRIPTION),
            original_name="LibRPA.out", original_sha=sha256b(librpa_raw))
        software = {"fhi_aims": aims_software(version, logged, f"{record_dir}/logs/aims.out"),
                    "librpa": {"source_url": LIBRPA_SOURCE_URL, "commit": LIBRPA_COMMIT,
                               "abbreviated_commit": None,
                               "evidence": [f"{record_dir}/logs/librpa.out"],
                               "identity_note": LIBRPA_NOTE}}
        if software["fhi_aims"]["commit"] is None:
            self.exceptions.append((record_id, "fhi_aims"))
        results = []
        for method in ("KS", "EXX", "GW"):
            path = run / f"{method}_band_spin_1.dat"
            if path.is_file():
                results.append(make_entry(
                    f"{record_dir}/results/{method}_band_spin_1.dat", path.read_bytes(),
                    label=f"LibRPA {method} band table ({flavor}-point grid)", group="results",
                    scientific_role=f"librpa_{method.lower()}_band_table", transformation="none",
                    original_name=f"{method}_band_spin_1.dat"))
        scale = {"atom_count": atom_count}
        gw_path = run / "GW_band_spin_1.dat"
        if gw_path.is_file():
            gw_table = plot_bands.parse_abacus_band_table(as_temp_path(gw_path.read_text("utf-8"), ".dat"))
            scale.update({"n_bands": len(gw_table.energies[0]), "n_path_kpoints": len(gw_table.x)})
        record = {
            "schema_version": 1, "id": record_id, "dimension": "3d", "material": material,
            "formula": material, "record_type": "band",
            "workflow": {"frontend": "fhi_aims", "task": "g0w0_band"},
            "software": software,
            "species": self.basis_bindings(control),
            "files": {"inputs": [
                make_entry(f"{record_dir}/inputs/control.in", (dataset / "control.in").read_bytes(),
                           label=f"FHI-aims control.in (dataset generation, {dataset_rel})",
                           group="inputs", scientific_role="aims_control_input",
                           transformation="none", original_name="control.in"),
                make_entry(f"{record_dir}/inputs/geometry.in", (dataset / "geometry.in").read_bytes(),
                           label=f"FHI-aims geometry.in (dataset generation, {dataset_rel})",
                           group="inputs", scientific_role="aims_geometry_input",
                           transformation="none", original_name="geometry.in"),
                make_entry(f"{record_dir}/inputs/librpa.in", (run / "librpa.in").read_bytes(),
                           label=f"LibRPA g0w0_band input ({flavor}-point grid)", group="inputs",
                           scientific_role="librpa_g0w0_input", transformation="none",
                           original_name="librpa.in"),
                self.kpt_entry(control, record_dir),
            ], "results": results, "logs": [scf_log, librpa_log], "figures": []},
            "structure_identity": identity,
            "computational_scale": scale,
            "performance": self.performance(librpa_clean, f"{record_dir}/logs/librpa.out"),
            "properties": [], "basis_candidates": [], "recommendation": None, "missing": [],
            "summary": {
                "observable": "G0W0 band gap (sampled path)", "unit": "eV",
                "notes": "Historical journal supporting-data run. The raw GW QP table carries the "
                         "known numerical pathology of LibRPA v0.4.0 (QPE-solver NaN, documented in "
                         "the supporting-data README); the GW observable is therefore a restricted "
                         "sampled-path gap. Not a universal basis recommendation.",
            },
            "publication": {"status": "journal_supporting_information",
                            "manuscript_id": "jctc-6c00618"},
            "source": {"collection": COLLECTION, "tar": TAR_NAME,
                       "provenance_directory": PROVENANCE_REL,
                       "material_directory": material, "run_directory": f"librpa-{flavor}",
                       "dataset_directory": dataset_rel},
        }
        return record

    def build_gaas_32ac_record(self) -> dict:
        mat_dir = self.source / "GaAs" / "aims-32ac"
        record_id = "gaas-jctc-aims-32ac"
        record_dir = f"data/calculations/3d/GaAs/{record_id}"
        control = (mat_dir / "control.in").read_text(encoding="utf-8")
        geometry = (mat_dir / "geometry.in").read_text(encoding="utf-8")
        identity, atom_count = self.structure_identity(geometry, record_dir)
        log_entry, version, logged = self.log_entry(
            mat_dir / "aims.out", f"{record_dir}/logs/aims.out",
            "FHI-aims focused GW rerun log (n_anacon_par 32)", "aims_run_log", "aims.out")
        software = {"fhi_aims": aims_software(version, logged, f"{record_dir}/logs/aims.out")}
        if software["fhi_aims"]["commit"] is None:
            self.exceptions.append((record_id, "fhi_aims"))
        band_raw = (mat_dir / "GW_band1001.out").read_bytes()
        table = plot_bands.parse_abacus_band_table(as_temp_path(band_raw.decode("utf-8"), ".dat"))
        return {
            "schema_version": 1, "id": record_id, "dimension": "3d", "material": "GaAs",
            "formula": "GaAs", "record_type": "band",
            "workflow": {"frontend": "fhi_aims", "task": "gw"},
            "software": software,
            "species": self.basis_bindings(control),
            "files": {"inputs": [
                make_entry(f"{record_dir}/inputs/control.in", (mat_dir / "control.in").read_bytes(),
                           label="FHI-aims control.in (focused rerun, n_anacon_par 32)",
                           group="inputs", scientific_role="aims_control_input",
                           transformation="none", original_name="control.in"),
                make_entry(f"{record_dir}/inputs/geometry.in", (mat_dir / "geometry.in").read_bytes(),
                           label="FHI-aims geometry.in (focused rerun)", group="inputs",
                           scientific_role="aims_geometry_input", transformation="none",
                           original_name="geometry.in"),
                self.kpt_entry(control, record_dir),
            ], "results": [
                make_entry(f"{record_dir}/results/GW_band_spin_1.dat", band_raw,
                           label="FHI-aims focused rerun GW band table (single G-X segment)",
                           group="results", scientific_role="aims_gw_band_table",
                           transformation="renamed from producer file GW_band1001.out; "
                                          "content byte-preserved",
                           original_name="GW_band1001.out"),
                make_entry(f"{record_dir}/results/self_energy_band.dat",
                           (mat_dir / "self_energy_band.dat").read_bytes(),
                           label="Focused rerun QP self-energy band data (MATLAB v4 matrix, 21x16 complex)",
                           group="results", scientific_role="aims_qp_self_energy_matrix",
                           transformation="none", original_name="self_energy_band.dat"),
            ], "logs": [log_entry], "figures": []},
            "structure_identity": identity,
            "computational_scale": {"atom_count": atom_count, "n_bands": len(table.energies[0]),
                                    "n_path_kpoints": len(table.x)},
            "properties": [], "basis_candidates": [], "recommendation": None, "missing": [],
            "summary": {
                "observable": "G0W0 band gap (sampled path)", "unit": "eV",
                "notes": "Historical journal supporting-data focused rerun: the GaAs Pade-16 CBM "
                         "convergence issue at Gamma reported in the supporting README was addressed "
                         "by increasing the number of Pade poles to 32 (periodic_gw_self_energy "
                         "restart). Single G-X segment; sampled path only.",
            },
            "publication": {"status": "journal_supporting_information",
                            "manuscript_id": "jctc-6c00618"},
            "source": {"collection": COLLECTION, "tar": TAR_NAME,
                       "provenance_directory": PROVENANCE_REL,
                       "material_directory": "GaAs", "run_directory": "aims-32ac"},
        }

    @staticmethod
    def performance(log_text: str, evidence: str) -> dict | None:
        tasks = re.search(r"Total number of tasks:\s+(\d+)", log_text)
        nodes = re.search(r"Total number of nodes:\s+(\d+)", log_text)
        threads = re.search(r"Maximumal number of threads:\s+(\d+)", log_text)
        wall = re.search(r"(?m)^\s*Total\s+\d+\s+\d+\.\d+\s+(\d+\.\d+)\s*$", log_text)
        if not all((tasks, nodes, threads, wall)):
            return None
        return {"wall_time_seconds": int(round(float(wall.group(1)))), "nodes": int(nodes.group(1)),
                "mpi_ranks": int(tasks.group(1)), "omp_threads_per_rank": int(threads.group(1)),
                "cluster_label": "unnamed x86 cluster (c03xx compute nodes)",
                "evidence": [evidence]}

    # ---- verification --------------------------------------------------------

    def verify_tsv(self) -> None:
        tsv = self.source / "dataset_sources.tsv"
        rows = [line.split("\t") for line in tsv.read_text(encoding="utf-8").splitlines()[1:]
                if line.strip()]
        for row in rows:
            archived, digest = row[2], row[4]
            path = self.source / archived
            if not path.is_file() or sha256b(path.read_bytes()) != digest:
                raise ValueError(f"dataset_sources.tsv integrity failure: {archived}")
            self.report["tsv_verified"] += 1

    def audit_records(self) -> None:
        for record in self.records:
            kpt_entry = next(e for e in record["files"]["inputs"] if e["path"].endswith("KPT_band"))
            kpt_path = as_temp_path(PAYLOADS[kpt_entry["path"]].decode("utf-8"), ".KPT")
            audited = []
            for entry in record["files"]["results"]:
                name = Path(entry["path"]).name
                if not re.fullmatch(r"(?:KS|EXX|GW)_band_spin_1\.dat", name):
                    continue
                table = plot_bands.parse_abacus_band_table(
                    as_temp_path(PAYLOADS[entry["path"]].decode("utf-8"), ".dat"))
                figures.audit_kpath(table, kpt_path)
                audited.append(name)
            self.report["records"].append({
                "id": record["id"], "material": record["material"],
                "task": record["workflow"]["task"],
                "file_count": sum(len(entries) for entries in record["files"].values()),
                "audited_tables": audited,
                "fhi_aims_commit": record["software"]["fhi_aims"]["commit"],
                "has_performance": "performance" in record,
            })

    # ---- assembly ------------------------------------------------------------

    def build(self) -> None:
        if self.records:
            return
        self.verify_tsv()
        for material in self.materials:
            self.records.append(self.build_aims_record(material))
            for flavor in (16, 32):
                if (self.source / material / f"librpa-{flavor}").is_dir():
                    self.records.append(self.build_librpa_record(material, flavor))
        self.records.append(self.build_gaas_32ac_record())
        self.audit_records()
        self.report["exception_pairs"] = [list(pair) for pair in sorted(set(self.exceptions))]
        self.report["record_count"] = len(self.records)
        self.report["total_bytes"] = (sum(len(data) for data in PAYLOADS.values())
                                      + sum(len(json.dumps(r, ensure_ascii=False)) for r in self.records))

    def write(self) -> None:
        self.build()
        for rel, data in PAYLOADS.items():
            target = ROOT / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for record in self.records:
            write_json(ROOT / "data/calculations/3d" / record["material"] / record["id"] / "record.json",
                       record)
        for path, data in self.basis_writes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.update_exceptions()
        self.copy_provenance()

    def update_exceptions(self) -> None:
        path = ROOT / EXCEPTIONS_REL
        data = json.loads(path.read_text(encoding="utf-8"))
        existing = {(entry["id"], name) for entry in data["records"] for name in entry["software"]}
        additions = {pair for pair in self.exceptions if pair not in existing}
        if not additions:
            return
        by_id: dict[str, set[str]] = {}
        for case_id, name in additions:
            by_id.setdefault(case_id, set()).add(name)
        for case_id, names in sorted(by_id.items()):
            data["records"].append({"id": case_id, "software": sorted(names)})
        data["records"].sort(key=lambda entry: entry["id"])
        data["frozen_issue_count"] = sum(len(entry["software"]) for entry in data["records"])
        note = ("The JCTC 6c00618 FHI-aims pairs were added on 2026-10-15 under the database "
                "owner's standing authorization for this intake: FHI-aims 241121 logged only the "
                "abbreviated commit b5eacca14, and the full hash is not recoverable from the local "
                "clone or the upstream server.")
        if note not in data["notes"]:
            data["notes"] = (data["notes"].rstrip() + " " + note).strip()
        write_json(path, data)

    def copy_provenance(self) -> None:
        target = ROOT / PROVENANCE_REL
        target.mkdir(parents=True, exist_ok=True)
        for name in ("README.md", "dataset_sources.tsv", "plot_bandstructures.py"):
            (target / name).write_bytes((self.source / name).read_bytes())


# ---- post-pass（图生成之后） ------------------------------------------------


def gw_band_gap_property(analysis: dict, table_rel: str) -> dict:
    return {"key": "band_gap", "category": "electronic", "label": "Sampled path band gap",
            "method": "G0W0", "value": analysis["sampled_path_gap_ev"], "unit": "eV",
            "status": "reported",
            "definition": "GW quasi-particle sampled native band-path gap on the fully audited "
                          "inclusive-segment KPT path. Sampled path only, not a global "
                          "Brillouin-zone gap, convergence validation, or basis recommendation.",
            "evidence": [table_rel]}


def restricted_gap_property(value: float, evidence: list[str], detail: str) -> dict:
    return {"key": "sampled_path_gap_ev", "category": "electronic",
            "label": "Restricted sampled path gap (GW)", "method": "G0W0",
            "value": value, "unit": "eV", "status": "reported",
            "definition": ("restricted sampled native band-path gap (" + detail + "): the raw GW "
                           "QP table carries the LibRPA v0.4.0 QPE-solver nonfinite outputs "
                           "documented in the supporting-data README, so the ordinary gap "
                           "analysis is refused; the value keeps the finite frontier entries with "
                           "nonfinite k-points/states excluded and diagnosed in the archived "
                           "sidecar. Not a global Brillouin-zone gap, convergence validation, or "
                           "basis recommendation."),
            "evidence": evidence}


def finite_entry_gap(record: dict, write: bool) -> tuple[float, dict]:
    """有限条目受限带隙：占据边界取自整数占据列，非有限 k 点被排除并记录。"""
    entry = next(e for e in record["files"]["results"] if e["path"].endswith("GW_band_spin_1.dat"))
    table = plot_bands.parse_abacus_band_table(ROOT / entry["path"])
    boundary, _ = plot_bands.integer_occupation_boundary(table)
    vbm_band, cbm_band = boundary, boundary + 1
    vbm = max(row[vbm_band - 1] for row in table.energies if math.isfinite(row[vbm_band - 1]))
    cbm = min(row[cbm_band - 1] for row in table.energies if math.isfinite(row[cbm_band - 1]))
    vbm_nonfinite = [k + 1 for k, row in enumerate(table.energies) if not math.isfinite(row[vbm_band - 1])]
    cbm_nonfinite = [k + 1 for k, row in enumerate(table.energies) if not math.isfinite(row[cbm_band - 1])]
    provenance = {
        "schema_version": 1, "calculation_id": record["id"],
        "method": "finite-entry restricted path gap",
        "occupied_band_count": boundary, "vbm_band": vbm_band, "cbm_band": cbm_band,
        "vbm_ev": vbm, "cbm_ev": cbm, "sampled_path_gap_ev": cbm - vbm,
        "vbm_nonfinite_native_kpoint_indices": vbm_nonfinite,
        "cbm_nonfinite_native_kpoint_indices": cbm_nonfinite,
        "source_result_path": entry["path"],
        "note": "Occupation boundary derived from the integer occupation column; nonfinite "
                "QPE-solver entries (LibRPA v0.4.0 documented bug) are excluded from the "
                "frontier extremes and listed above (empty lists mean the analyzer windows "
                "refused for manifold-selection reasons while the boundary bands are finite).",
    }
    return cbm - vbm, provenance


def post_pass(write: bool) -> dict:
    """图生成后补写 GW 属性与 summary；默认只读报告。"""
    report = {"records": []}
    for record_path in sorted((ROOT / "data/calculations").glob("*/*/*/record.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if "-jctc-" not in record["id"]:
            continue
        sidecar_path = record_path.parent / "figures" / "band_frontier_metadata.json"
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path.is_file() else {}
        analysis = (sidecar.get("methods") or {}).get("GW")
        gw_rel = next((e["path"] for e in record["files"]["results"]
                       if e["path"].endswith("GW_band_spin_1.dat")), None)
        sidecar_rel = sidecar_path.relative_to(ROOT).as_posix() if sidecar_path.is_file() else None
        result = {"id": record["id"]}
        gw_property = None
        if analysis and analysis.get("gap_status") == "reported" and \
                isinstance(analysis.get("sampled_path_gap_ev"), (int, float)):
            gw_property = gw_band_gap_property(analysis, gw_rel)
            result["gw"] = "band_gap (reported)"
        elif analysis and isinstance(analysis.get("selected_window_path_gap_ev"), (int, float)) \
                and math.isfinite(analysis["selected_window_path_gap_ev"]):
            gw_property = restricted_gap_property(
                analysis["selected_window_path_gap_ev"], [gw_rel, sidecar_rel],
                "sidecar selected-window path gap")
            result["gw"] = "sampled_path_gap_ev (selected-window)"
        else:
            gw_entry = next(e for e in record["files"]["results"]
                            if e["path"].endswith("GW_band_spin_1.dat"))
            gw_table = plot_bands.parse_abacus_band_table(ROOT / gw_entry["path"])
            value, detail, provenance = None, None, None
            for width in (1, 2):
                try:
                    retry = plot_bands.analyze_frontier(gw_table, known_pathological=True,
                                                        occupied_window=width, empty_window=width)
                except (ValueError, OSError):
                    continue
                selwin = retry.get("selected_window_path_gap_ev")
                if isinstance(selwin, (int, float)) and math.isfinite(selwin):
                    value = selwin
                    detail = (f"narrowed frontier window ({width},{width}) path gap after the "
                              "default window refused")
                    break
            if value is None:
                value, provenance = finite_entry_gap(record, write)
                detail = "finite-entry restricted path gap"
                result["exclusions"] = {
                    "vbm": provenance["vbm_nonfinite_native_kpoint_indices"],
                    "cbm": provenance["cbm_nonfinite_native_kpoint_indices"]}
            sidecar_out = record_path.parent / "figures" / "gw_restricted_gap_provenance.json"
            sidecar_out_rel = sidecar_out.relative_to(ROOT).as_posix()
            evidence = [gw_rel, sidecar_rel] if sidecar_rel else [gw_rel]
            if provenance is not None:
                if write:
                    write_json(sidecar_out, provenance)
                    if not any(e["path"] == sidecar_out_rel for e in record["files"].get("figures", [])):
                        data = sidecar_out.read_bytes()
                        record["files"].setdefault("figures", []).append({
                            "role": "figures", "path": sidecar_out_rel, "sha256": sha256b(data),
                            "size_bytes": len(data), "original_sha256": sha256b(data),
                            "label": "GW restricted gap finite-entry provenance",
                            "transformation": "derived exclusions diagnostics for the restricted GW "
                                              "sampled path gap",
                            "source_paths": [gw_rel], "display_priority": "secondary"})
                evidence.append(sidecar_out_rel)
            gw_property = restricted_gap_property(value, evidence, detail)
            result["gw"] = f"sampled_path_gap_ev ({detail.split()[0]})"
        if gw_property and not any(p.get("method") == "G0W0" for p in record["properties"]):
            record["properties"].append(gw_property)
        summary = record.setdefault("summary", {})
        summary["value"] = gw_property["value"]
        summary["gw_gap_ev" if gw_property["key"] == "band_gap" else "sampled_path_gap_ev"] = \
            gw_property["value"]
        for prop in record["properties"]:
            if prop.get("key") == "band_gap" and prop.get("method") == "EXX":
                summary["exx_gap_ev"] = prop["value"]
            if prop.get("key") == "band_gap" and prop.get("method") == "PBE":
                summary["dft_gap_ev"] = prop["value"]
        summary.setdefault("gap_definition",
                           "Archived sampled native band-path gap; restricted where the raw GW QP "
                           "table carries nonfinite QPE-solver outputs")
        summary.setdefault("scientific_status", "journal_supporting_information_path_gap")
        summary.setdefault("scope",
                           "Specific JCTC 6c00618 geometry, FHI-aims species defaults, k/path and "
                           "numerical settings. All-band, empty-state, transferability and "
                           "current-version acceptance not established by this audit.")
        result["value"] = gw_property["value"]
        if write:
            write_json(record_path, record)
        report["records"].append(result)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=Path("/private/tmp/jctc-data/jctc_6c00618_data"))
    parser.add_argument("--write", action="store_true", help="执行落盘（默认只读核验）")
    parser.add_argument("--post-pass", action="store_true",
                        help="图生成后补写 GW 受限属性与 summary")
    args = parser.parse_args()
    if args.post_pass:
        report = post_pass(args.write)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    intake = Intake(args.source)
    intake.build()
    print(json.dumps(intake.report, ensure_ascii=False, indent=2))
    if args.write:
        intake.write()
        print(f"wrote {len(intake.records)} records, {len(PAYLOADS)} payloads, "
              f"{len(intake.basis_writes)} basis set files", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
