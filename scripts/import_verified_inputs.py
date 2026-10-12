#!/usr/bin/env python3
"""仅在原输入和三谱的独立哈希链全部成立时恢复历史二维输入。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import tarfile

BACKUP_CASES = {
    "alas-paper-paper": ("AlAs", "ghj", "data/gw/AlAs/paper"),
    "alp-paper-k8_shrink_wing": ("AlP", "rxg", "data/gw/AlP/k8_shrink_wing"),
    "bas-paper-k8_shrink_wing": ("BAs", "rxg", "data/gw/BAs/k8_shrink_wing"),
    "bp-paper-k8_shrink_wing": ("BP", "rxg", "data/gw/BP/k8_shrink_wing"),
    "nacl-paper-sg15": ("NaCl", "rxg", "data/gw/NaCl/sg15"),
}

CASES = {
    "mos2-table-gw": ("MoS2", "mos2", "paper_table_k20", "MoS2/convg_test/k/20"),
    "wse2-table-gw": ("WSe2", "wse2", "paper_table_gw", "WSe2/gw"),
}
CONTROLS = ("INPUT", "KPT", "STRU", "librpa.in", "INPUT_scf", "KPT_scf", "INPUT_nscf", "KPT_nscf")
ROLES = {"pp": ("pseudopotentials", ".upf"), "nao": ("orbitals", ".orb"), "abf": ("auxiliary", ".abfs")}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def portable_path(root: Path, text: str) -> Path:
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("拒绝非便携路径")
    full = root.joinpath(*path.parts)
    if not full.resolve().is_relative_to(root.resolve()):
        raise ValueError("路径逃逸根目录")
    return full


def species_aliases(data: bytes) -> list[dict]:
    sections, current = {}, None
    for raw in data.decode("utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if re.fullmatch(r"[A-Z][A-Z_]+", line):
            current = line
            sections[current] = []
        elif current:
            sections[current].append(line.split())
    rows = sections.get("ATOMIC_SPECIES", [])
    nao = sections.get("NUMERICAL_ORBITAL", [])
    abf = sections.get("ABFS_ORBITAL", [])
    if not rows or len(rows) != len(nao) or len(rows) != len(abf):
        raise ValueError("STRU未完整声明PP/物理NAO/ABF")
    entries = []
    for row, orbital, auxiliary in zip(rows, nao, abf):
        if len(row) != 3 or not re.fullmatch(r"[A-Z][a-z]?", row[0]):
            raise ValueError("STRU原子声明无效")
        aliases = {"pp": row[2], "nao": orbital[0], "abf": auxiliary[0]}
        if any(Path(name).name != name or name in (".", "..") for name in aliases.values()):
            raise ValueError("STRU资产必须为原运行的平铺文件名")
        entries.append({"element": row[0], "asset_aliases": aliases})
    if len({entry["element"] for entry in entries}) != len(entries):
        raise ValueError("STRU元素声明重复")
    return entries


def file_item(role: str, path: str, data: bytes, original_name: str) -> dict:
    digest = sha256(data)
    return {"role": role, "path": path, "sha256": digest, "size_bytes": len(data),
            "original_sha256": digest, "label": original_name, "original_name": original_name,
            "transformation": "none"}


def verify_bands(data: bytes, method: dict) -> dict:
    nocc = method.get("occupied_states")
    nbands, npoints = method.get("raw_band_count"), method.get("npoints")
    if (type(nocc) is not int or type(nbands) is not int or type(npoints) is not int
            or not 0 < nocc < nbands or npoints <= 0):
        raise ValueError("缺少可靠占据计数或原始谱维度")
    rows = [[float(value) for value in line.split()] for line in data.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != npoints or any(len(row) != 4 + 2 * nbands for row in rows):
        raise ValueError("原始三谱维度不匹配")
    if any(not math.isfinite(value) for row in rows for value in row):
        raise ValueError("原始三谱包含非有限值")
    if any(row[0] != index for index, row in enumerate(rows, 1)):
        raise ValueError("原始三谱k索引不是连续1-based")
    if any(any(weight <= 0 for weight in row[4:4 + 2 * nocc:2])
           or any(abs(weight) > 1e-8 for weight in row[4 + 2 * nocc::2]) for row in rows):
        raise ValueError("原始谱占据边界与sidecar计数不符")
    energies = [row[5::2] for row in rows]
    gap = min(value for row in energies for value in row[nocc:]) - max(value for row in energies for value in row[:nocc])
    reported = method.get("path_gap_ev")
    if not isinstance(reported, (int, float)) or not math.isfinite(reported) or abs(gap - reported) > 5e-6:
        raise ValueError("sidecar path_gap_ev与完整原始谱不匹配")
    return {"npoints": npoints, "raw_band_count": nbands, "occupied_states": nocc,
            "nonfinite_entries": 0, "sampled_path_gap_ev": reported}


def prepare_case(repo: Path, source_root: Path, raw_root: Path, case_id: str) -> dict:
    material, source_slug, input_case, run_relative = CASES[case_id]
    case_relative = f"data/calculations/2d/{material}/{case_id}"
    record_path = portable_path(repo, f"{case_relative}/record.json")
    original_record = record_path.read_bytes()
    record = json.loads(original_record)
    if record.get("id") != case_id or record.get("dimension") != "2d" or record.get("material") != material:
        raise ValueError("目标记录身份不匹配")
    source_relative = f"{source_slug}/input_cases/{input_case}"
    source_case = portable_path(source_root, source_relative)
    run = portable_path(raw_root, run_relative)
    provenance_relative = f"{source_slug}/provenance/table_band_source.json"
    provenance_bytes = portable_path(source_root, provenance_relative).read_bytes()
    provenance = json.loads(provenance_bytes)
    sidecar_item = next(item for item in record["files"]["results"] if Path(item["path"]).name == "band_window_and_provenance.json")
    sidecar_bytes = portable_path(repo, sidecar_item["path"]).read_bytes()
    if sha256(sidecar_bytes) != sidecar_item["sha256"]:
        raise ValueError("记录sidecar哈希不匹配")
    sidecar = json.loads(sidecar_bytes)
    if sha256(provenance_bytes) != record.get("source", {}).get("original_sidecar_sha256", sidecar_item.get("original_sha256")):
        raise ValueError("原始provenance与记录既有来源哈希不匹配")
    spectra, band_checks = {}, {}
    for method in ("KS", "EXX", "GW"):
        source = provenance["methods"][method]["source"]
        raw_name = f"{method}_band_spin_1.dat"
        expected_raw = run / raw_name
        if Path(source["original_path"]).resolve() != expected_raw.resolve():
            raise ValueError(f"{method}: 拒绝foreign-run来源")
        raw_data = expected_raw.read_bytes()
        result = next(item for item in record["files"]["results"] if Path(item["path"]).name == f"{method}_bands.dat")
        if not (sha256(raw_data) == source["sha256"] == result["sha256"]
                == sha256(portable_path(repo, result["path"]).read_bytes())
                == sidecar["methods"][method]["source"]["sha256"]):
            raise ValueError(f"{method}: 原始三谱/来源/记录哈希不匹配")
        for key in ("occupied_states", "raw_band_count", "npoints", "path_gap_ev"):
            if provenance["methods"][method][key] != sidecar["methods"][method][key]:
                raise ValueError(f"{method}: 来源与同记录sidecar不一致")
        band_checks[method] = verify_bands(raw_data, sidecar["methods"][method])
        spectra[method] = {"source_name": raw_name, "repository_path": result["path"],
                           "sha256": source["sha256"], "size_bytes": len(raw_data), **band_checks[method]}

    entries = species_aliases((source_case / "STRU").read_bytes())
    required = set(CONTROLS) | {"band_kpath_info"} | {name for entry in entries for name in entry["asset_aliases"].values()}
    if len(required) != 15 or {path.name for path in source_case.iterdir()} != required:
        raise ValueError("原输入集合不是完整15文件")
    originals = {}
    for name in sorted(required):
        data = (source_case / name).read_bytes()
        if data != (run / name).read_bytes():
            raise ValueError(f"{name}: input与独立raw原字节不匹配")
        originals[name] = data

    writes, sets, imported = {}, [], {}
    receipt_path = f"{case_relative}/results/raw_input_receipt.json"
    for entry in entries:
        element = entry["element"]
        role_hashes = {role: sha256(originals[name]) for role, name in entry["asset_aliases"].items()}
        identity = sha256(json.dumps(role_hashes, sort_keys=True, separators=(",", ":")).encode("ascii"))
        set_id = f"{element}-archived-{identity[:12]}"
        entry.update({"set_id": set_id, "source_receipt": receipt_path})
        payloads = []
        for role, name in entry["asset_aliases"].items():
            group, extension = ROLES[role]
            path = f"data/elements/{element}/{group}/{role_hashes[role]}{extension}"
            writes[path] = originals[name]
            payloads.append(file_item(role, path, originals[name], name))
            imported[name] = {"role": role, "repository_path": path, "set_id": set_id}
        basis = {"schema_version": 1, "id": set_id, "element": element, "family": "historical_raw",
                 "role_hashes_sha256": identity, "validation_scope": "exact archived producer input binding only; scientific acceptance not evaluated",
                 "publication": {"status": "database_only"},
                 "source": {"collection": "2D manuscript independently verified raw input", "receipt": receipt_path,
                            "license": "unknown", "redistribution": "unknown"},
                 "files": payloads, "generation_provenance": {"commit": None, "status": "unknown; not inferred from production usage"},
                 "used_by": [case_id]}
        writes[f"data/elements/{element}/sets/{set_id}/set.json"] = json_bytes(basis)
        sets.append(basis)

    new_inputs = []
    for name in CONTROLS:
        path = f"{case_relative}/inputs/{name}"
        writes[path] = originals[name]
        new_inputs.append(file_item("inputs", path, originals[name], name))
        imported[name] = {"role": "inputs", "repository_path": path}
    kpath = f"{case_relative}/results/band_kpath_info"
    writes[kpath] = originals["band_kpath_info"]
    imported["band_kpath_info"] = {"role": "results", "repository_path": kpath}

    log_checks = []
    for log in sorted(run.glob("*.out")):
        if not re.fullmatch(r"(?:abacus|LibRPA)\.\d+\.out", log.name):
            continue
        log_bytes = log.read_bytes()
        commits = re.findall(r"(?im)^\s*Commit:\s*([0-9a-f]{7,64})\b", log_bytes.decode("utf-8", errors="replace"))
        log_checks.append({"source_name": log.name, "sha256": sha256(log_bytes),
                           "recorded_commit_tokens": commits, "full_commit_present": any(len(token) in (40, 64) for token in commits)})
    receipt = {"schema_version": 1, "case_id": case_id, "verification": "independent raw byte equality plus raw/source/record three-spectrum SHA-256 equality",
               "source_collection": "prb2025 archived raw runs", "source_run_relative": run_relative,
               "source_input_case_relative": source_relative,
               "source_provenance": {"path": provenance_relative, "sha256": sha256(provenance_bytes)},
               "record_sidecar": {"path": sidecar_item["path"], "sha256": sidecar_item["sha256"]},
               "input_file_count": len(originals),
               "files": [{"source_name": name, "sha256": sha256(data), "size_bytes": len(data),
                          "byte_equal_to_independent_raw": True, **imported[name]} for name, data in sorted(originals.items())],
               "spectra": spectra, "basis_set_ids": [basis["id"] for basis in sets], "software_log_audit": log_checks,
               "scope": "input provenance only; unknown software full commits, generation provenance and redistribution remain unresolved"}
    writes[receipt_path] = json_bytes(receipt)
    if record["files"].get("inputs") and record["files"]["inputs"] != new_inputs:
        raise ValueError("目标已有不一致inputs，拒绝覆盖")
    if record.get("species") and record["species"] != entries:
        raise ValueError("目标已有不同精确species绑定，拒绝覆盖")
    record["files"]["inputs"] = new_inputs
    record["species"] = entries
    for item in (file_item("results", kpath, originals["band_kpath_info"], "band_kpath_info"),
                 file_item("results", receipt_path, writes[receipt_path], "raw_input_receipt.json")):
        previous = next((value for value in record["files"]["results"] if value["path"] == item["path"]), None)
        if previous is not None and previous != item:
            raise ValueError("目标已有不同不可变receipt或kpath声明")
        if previous is None:
            record["files"]["results"].append(item)
    for raw_method, method in (("KS", "PBE"), ("EXX", "EXX")):
        prop = {"key": "sampled_path_gap_ev", "category": "electronic", "label": "Sampled path gap",
                "method": method, "value": band_checks[raw_method]["sampled_path_gap_ev"], "unit": "eV", "status": "reported",
                "definition": "Sampled path CBM minus VBM from finite original bands with sidecar occupied-state boundary; not a full-Brillouin-zone fundamental gap",
                "evidence": [spectra[raw_method]["repository_path"], sidecar_item["path"], receipt_path],
                "source_sidecar_key": f"methods.{raw_method}.path_gap_ev"}
        properties = record.setdefault("properties", [])
        previous = next((value for value in properties if value.get("key") == prop["key"] and value.get("method") == method), None)
        if previous is not None and previous != prop:
            raise ValueError("目标已有不同path gap property，拒绝覆盖")
        if previous is None:
            properties.append(prop)
    record["missing"] = [note for note in record.get("missing", []) if note != "Exact production STRU/PP/NAO/ABF link pending source-case audit"]
    record.setdefault("source", {})["raw_input_receipt"] = receipt_path
    record.setdefault("publication", {"status": "database_only"})
    writes[f"{case_relative}/record.json"] = json_bytes(record)
    for path, data in writes.items():
        destination = portable_path(repo, path)
        if destination.exists() and path != f"{case_relative}/record.json" and destination.read_bytes() != data:
            raise ValueError(f"不可变目标内容冲突: {path}")
    return {"case_id": case_id, "writes": writes, "record_path": record_path,
            "original_record": original_record, "input_file_count": len(originals), "control_file_count": len(new_inputs),
            "basis_set_ids": receipt["basis_set_ids"], "path_gaps": {method: band_checks[method]["sampled_path_gap_ev"] for method in ("KS", "EXX")}}


def import_case(repo: Path, source_root: Path, raw_root: Path, case_id: str, *, write: bool = False) -> dict:
    plan = prepare_case(repo, source_root, raw_root, case_id)
    if write:
        if plan["record_path"].read_bytes() != plan["original_record"]:
            raise ValueError("record验证后被修改，拒绝覆盖")
        record_relative = plan["record_path"].relative_to(repo).as_posix()
        for path, data in plan["writes"].items():
            if path == record_relative:
                continue
            destination = portable_path(repo, path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                temporary_path = None
                try:
                    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as stream:
                        temporary_path = Path(stream.name)
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    try:
                        os.link(temporary_path, destination)
                    except FileExistsError:
                        if destination.read_bytes() != data:
                            raise ValueError("验证后不可变目标发生变化")
                finally:
                    if temporary_path is not None and temporary_path.exists():
                        temporary_path.unlink()
            elif destination.read_bytes() != data:
                raise ValueError("验证后不可变目标发生变化")
        if plan["record_path"].read_bytes() != plan["original_record"]:
            raise ValueError("record写入前被修改，拒绝覆盖")
        if plan["writes"][record_relative] != plan["original_record"]:
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=plan["record_path"].parent, suffix=".part", delete=False) as stream:
                    temporary_path = Path(stream.name)
                    stream.write(plan["writes"][record_relative])
                    stream.flush()
                    os.fsync(stream.fileno())
                if plan["record_path"].read_bytes() != plan["original_record"]:
                    raise ValueError("record原子替换前被修改，拒绝覆盖")
                os.replace(temporary_path, plan["record_path"])
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
    return {key: value for key, value in plan.items() if key not in ("writes", "record_path", "original_record")}


def checked_destination(repo: Path, relative: str) -> Path:
    destination = portable_path(repo, relative)
    for path in (destination, *destination.parents):
        if path == repo:
            break
        if path.is_symlink() or (path.exists() and path != destination and not path.is_dir()):
            raise ValueError(f"目标路径冲突: {relative}")
    if destination.exists() and not destination.is_file():
        raise ValueError(f"目标路径冲突: {relative}")
    return destination


def asset_header(data: bytes, element: str, role: str) -> dict:
    text = data[:16384].decode("utf-8", errors="strict")
    if role == "pp":
        match = re.search(r"<PP_HEADER\b[^>]*\belement\s*=\s*[\"']\s*([A-Z][a-z]?)\s*[\"']", text, re.S)
        if not match or match.group(1) != element:
            raise ValueError("PP原头部元素不匹配")
        return {"format": "UPF", "element": element, "header_sha256": sha256(data[:16384])}
    match = re.search(r"(?m)^Element\s+([A-Z][a-z]?)\s*$", text)
    if not match or match.group(1) != element or "SUMMARY  END" not in text:
        raise ValueError("NAO/ABF原头部元素不匹配")
    fields = {}
    for key in ("Energy Cutoff(Ry)", "Radius Cutoff(a.u.)", "Lmax"):
        value = re.search(r"(?m)^" + re.escape(key) + r"\s+([\d.]+)\s*$", text)
        if not value:
            raise ValueError("NAO/ABF原头部缺少数值声明")
        fields[key] = float(value.group(1))
    counts = dict(re.findall(r"(?m)^Number of ([A-Z])orbital-->\s+(\d+)\s*$", text))
    if not counts:
        raise ValueError("NAO/ABF原头部缺少轨道计数")
    return {"format": "ABACUS orbital", "element": element, "parameters": fields,
            "orbital_counts": {key: int(value) for key, value in counts.items()},
            "header_sha256": sha256(data[:text.index("SUMMARY  END") + len("SUMMARY  END")])}


def import_backup_assets(repo: Path, report_path: Path, *, write: bool = False) -> dict:
    """验证历史原路径备份关联；默认dry-run，不推断runtime seal或科学验收。"""
    repo, report_path = repo.resolve(), report_path.resolve()
    readset = {}

    def read(path: Path) -> bytes:
        data = path.read_bytes()
        digest = sha256(data)
        if path in readset and readset[path] != digest:
            raise ValueError("读取期间原文件发生变化")
        readset[path] = digest
        return data

    def hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    report_data = read(report_path)
    report = json.loads(report_data)
    cases = report["cases"]
    if report.get("schema_version") != 1 or {case["id"] for case in cases} != set(BACKUP_CASES) or len(cases) != 5:
        raise ValueError("备份报告不是固定三维五例")
    registry = {}
    for item in report["asset_registry"]:
        key = (item["element"], item["role"])
        if key in registry or item["role"] not in ("pp", "nao"):
            raise ValueError("备份报告资产角色重复或无效")
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) or type(item["size_bytes"]) is not int or item["size_bytes"] <= 0:
            raise ValueError("备份报告资产SHA/size无效")
        registry[key] = item
    if len(registry) != 12:
        raise ValueError("备份报告不是12项唯一PP/NAO")
    locations = report["checked_locations"]
    roots = {"ghj": Path(locations["ghj_backup"]).resolve()}
    archive = Path(locations["rxg_archive"]).resolve()
    prefix = locations["rxg_archive_prefix"]
    portable_path(Path("."), prefix)
    records, native_required, plans = {}, {"ghj": set(), "rxg": set()}, []
    for case in sorted(cases, key=lambda value: value["id"]):
        case_id = case["id"]
        material, origin, native = BACKUP_CASES[case_id]
        if (case["material"], case["backup_source"], case["native_relative"]) != (material, origin, native):
            raise ValueError("报告原运行身份不匹配")
        if not {"STRU", "INPUT", "INPUT_scf", "KS", "EXX", "GW", "abacus_log", "librpa_log"}.issubset(case["selected_sha256"]):
            raise ValueError("报告缺少明确的原controls/三谱/日志SHA")
        relative = f"data/calculations/3d/{material}/{case_id}"
        record_path = checked_destination(repo, relative + "/record.json")
        record_data = read(record_path)
        record = json.loads(record_data)
        if (record.get("id"), record.get("dimension"), record.get("material")) != (case_id, "3d", material):
            raise ValueError("目标三维记录身份不匹配")
        if not record["source"]["archive_directory"].endswith("/" + case["archive_directory"]):
            raise ValueError("原归档目录身份不匹配")
        if record.get("audit", {}).get("complete_runtime_handoff_included") is not False:
            raise ValueError("拒绝不符合历史非完整runtime handoff的记录")
        if record.get("publication", {}).get("status", "database_only") != "database_only":
            raise ValueError("三维备份归档不得改变或接受已升级的publication status")
        if len(record["species"]) != 2 or len({entry["element"] for entry in record["species"]}) != 2:
            raise ValueError("目标三维双元素species身份不完整")
        records[case_id] = (record, record_data, relative)
        names = set(CONTROLS) | {f"{method}_band_spin_1.dat" for method in ("KS", "EXX", "GW")}
        names |= {f"abacus.{case['job_ids']['producer']}.out", f"LibRPA.{case['job_ids']['librpa']}.out"}
        evidence_name, evidence_line = case["working_directory_evidence"].rsplit(":", 1)
        if evidence_name != f"slurm-{case['job_ids']['librpa']}.out" or int(evidence_line) <= 0:
            raise ValueError("原工作目录证据身份不匹配")
        names.add(evidence_name)
        for entry in record["species"]:
            for role in ("pp", "nao"):
                asset = registry[(entry["element"], role)]
                if asset["name"] != entry["asset_aliases"][role]:
                    raise ValueError("报告资产与record STRU别名不匹配")
                asset_relative = asset["ghj_relative" if origin == "ghj" else "rxg_member_relative"]
                expected = f"data/gw_bas_pp/{'pp' if role == 'pp' else 'nao'}/{asset['name']}"
                if asset_relative != expected:
                    raise ValueError("拒绝foreign原外置根成员")
                native_required[origin].add(asset_relative)
            names.add(entry["asset_aliases"]["abf"])
        native_required[origin].update(f"{native}/{name}" for name in names)
    source_bytes, backup_metadata = {"ghj": {}, "rxg": {}}, {}
    for origin in ("ghj", "rxg"):
        provenance = report["backup_provenance"][origin]
        if origin == "ghj":
            metadata_names = ("README.md", "MANIFEST.tsv")
        else:
            metadata_names = (provenance["readme_member"], provenance["manifest_member"])
            if metadata_names != (prefix + "/README.md", prefix + "/MANIFEST.tsv"):
                raise ValueError("拒绝foreign备份元数据成员")
            if archive.stat().st_size != provenance["archive_size_bytes"] or hash_file(archive) != provenance["archive_sha256"]:
                raise ValueError("rxg archive原SHA/size不匹配")
            readset[archive] = provenance["archive_sha256"]
        if origin == "ghj":
            for relative in native_required[origin] | set(metadata_names):
                source_bytes[origin][relative] = read(portable_path(roots[origin], relative))
        else:
            wanted = {prefix + "/" + relative for relative in native_required[origin]} | set(metadata_names)
            with tarfile.open(archive, mode="r|gz") as stream:
                for member in stream:
                    if member.name not in wanted:
                        continue
                    if member.name in source_bytes[origin] or not member.isfile() or member.size > 32 * 1024 * 1024:
                        raise ValueError("拒绝重复、链接或过大的指定tar成员")
                    data = stream.extractfile(member).read()
                    if len(data) != member.size:
                        raise ValueError("指定tar成员读取不完整")
                    source_bytes[origin][member.name] = data
            if set(source_bytes[origin]) != wanted:
                raise ValueError("rxg自身原成员缺失；不允许另一备份替代")
            source_bytes[origin] = {name.removeprefix(prefix + "/"): data for name, data in source_bytes[origin].items()}
        readme, manifest = (source_bytes[origin][name] for name in ("README.md", "MANIFEST.tsv"))
        if sha256(readme) != provenance["readme_sha256"] or sha256(manifest) != provenance["manifest_sha256"]:
            raise ValueError("备份README/MANIFEST SHA不匹配")
        original_root = provenance["historical_source_root"]
        if "Source root: " + original_root not in readme.decode("utf-8") or "gw_bas_pp/" not in readme.decode("utf-8"):
            raise ValueError("备份README没有声明原根和gw_bas_pp")
        manifest_rows = {}
        for line in manifest.decode("utf-8").splitlines():
            fields = line.split("\t", 2)
            if len(fields) != 3:
                raise ValueError("备份MANIFEST格式无效")
            relative = "data/" + fields[2].removeprefix("./")
            if relative in native_required[origin]:
                if relative in manifest_rows:
                    raise ValueError("备份MANIFEST指定成员重复")
                manifest_rows[relative] = {"size_bytes": int(fields[0]), "mtime": fields[1]}
        if set(manifest_rows) != native_required[origin]:
            raise ValueError("备份MANIFEST原成员缺失")
        for relative, row in manifest_rows.items():
            if row["size_bytes"] != len(source_bytes[origin][relative]):
                raise ValueError("备份MANIFEST原成员size不匹配")
        backup_metadata[origin] = {"collection": roots[origin].name if origin == "ghj" else prefix,
            "historical_source_root_sha256": sha256(original_root.encode()),
            "readme_sha256": sha256(readme), "manifest_sha256": sha256(manifest), "manifest_rows": manifest_rows}
        if origin == "rxg":
            backup_metadata[origin]["archive_sha256"] = provenance["archive_sha256"]
    writes, original_records, sets_by_id, receipts = {}, {}, {}, []
    for case in sorted(cases, key=lambda value: value["id"]):
        case_id, origin, native = case["id"], case["backup_source"], case["native_relative"]
        record, record_data, relative = records[case_id]
        originals = source_bytes[origin]
        source_root = report["backup_provenance"][origin]["historical_source_root"]
        run_directory = source_root + "/" + native.removeprefix("data/")
        if case["historical_run_directory"] != run_directory:
            raise ValueError("报告原工作目录不属于原备份根")
        evidence_name, evidence_line = case["working_directory_evidence"].rsplit(":", 1)
        line = originals[f"{native}/{evidence_name}"].decode("utf-8").splitlines()[int(evidence_line) - 1]
        if line.strip() != "Working directory is " + run_directory:
            raise ValueError("原slurm工作目录证据不匹配")
        current_checks = []
        for group in ("inputs", "results", "logs"):
            for item in record["files"][group]:
                data = read(portable_path(repo, item["path"]))
                if sha256(data) != item["sha256"] or len(data) != item["size_bytes"]:
                    raise ValueError("record当前文件SHA/size不匹配")
                current_checks.append({"path": item["path"], "sha256": item["sha256"], "size_bytes": len(data)})
        native_checks = []
        pairs = [("inputs", name, name) for name in CONTROLS]
        pairs += [("results", f"{method}_band_spin_1.dat", method) for method in ("KS", "EXX", "GW")]
        pairs += [("logs", f"abacus.{case['job_ids']['producer']}.out", "abacus_log"),
                  ("logs", f"LibRPA.{case['job_ids']['librpa']}.out", "librpa_log")]
        for group, name, report_key in pairs:
            basename = {"abacus_log": "abacus.out", "librpa_log": "librpa.out"}.get(report_key, name)
            item = next(value for value in record["files"][group] if Path(value["path"]).name == basename)
            data = originals[f"{native}/{name}"]
            digest = sha256(data)
            if digest != item.get("original_sha256", item["sha256"]):
                raise ValueError("备份原controls/三谱/日志与record original SHA不匹配")
            if report_key in case["selected_sha256"] and digest != case["selected_sha256"][report_key]:
                raise ValueError("备份原controls/三谱/日志与报告SHA不匹配")
            if item.get("transformation", "none") == "none" and data != read(portable_path(repo, item["path"])):
                raise ValueError("未脱敏原文件字节不匹配")
            native_checks.append({"source_member": f"{native}/{name}", "sha256": digest, "size_bytes": len(data),
                                  "repository_path": item["path"], "repository_sha256": item["sha256"]})
            if name in ("INPUT", "INPUT_scf", "INPUT_nscf"):
                parameters = {}
                for raw in data.decode("utf-8").splitlines():
                    fields = raw.split("#", 1)[0].split()
                    if len(fields) >= 2 and fields[0] in ("pseudo_dir", "orbital_dir"):
                        if fields[0] in parameters:
                            raise ValueError("原INPUT外置根重复")
                        parameters[fields[0]] = fields[1]
                expected_roots = {"pseudo_dir": source_root + "/gw_bas_pp/pp", "orbital_dir": source_root + "/gw_bas_pp/nao"}
                if parameters != expected_roots or any(case["input_external_roots"][key] != value for key, value in expected_roots.items()):
                    raise ValueError("原INPUT外置根不匹配")
        aliases = species_aliases(originals[f"{native}/STRU"])
        if aliases != [{"element": value["element"], "asset_aliases": value["asset_aliases"]} for value in record["species"]]:
            raise ValueError("原STRU与record species角色绑定不匹配")
        if [value["element"] for value in aliases] != case["stru_references"]["elements"]:
            raise ValueError("原STRU与报告元素顺序不匹配")
        receipt_path = relative + "/results/backup_assets_receipt.json"
        asset_checks, set_ids = [], []
        for entry in record["species"]:
            element = entry["element"]
            old_id = entry.get("previous_set_id", entry["set_id"])
            old_path = f"data/elements/{element}/sets/{old_id}/set.json"
            old_data = read(portable_path(repo, old_path))
            old_set = json.loads(old_data)
            if old_set["id"] != old_id or old_set["element"] != element or {value["role"] for value in old_set["files"]} != {"abf"}:
                raise ValueError("原不完整set身份或角色不匹配")
            abf = old_set["files"][0]
            abf_data = read(portable_path(repo, abf["path"]))
            abf_name = entry["asset_aliases"]["abf"]
            if sha256(abf_data) != abf["sha256"] or len(abf_data) != abf["size_bytes"] or abf_data != originals[f"{native}/{abf_name}"]:
                raise ValueError("原ABF与旧set及备份字节不匹配")
            payloads = []
            for role in ("pp", "nao"):
                asset = registry[(element, role)]
                member = asset["ghj_relative" if origin == "ghj" else "rxg_member_relative"]
                data = originals[member]
                if sha256(data) != asset["sha256"] or len(data) != asset["size_bytes"]:
                    raise ValueError("备份PP/NAO原SHA/size不匹配")
                header = asset_header(data, element, role)
                group, extension = ROLES[role]
                path = f"data/elements/{element}/{group}/{asset['sha256']}{extension}"
                writes[path] = data
                payloads.append(file_item(role, path, data, asset["name"]))
                asset_checks.append({"element": element, "role": role, "original_name": asset["name"],
                    "source_member": member, "sha256": asset["sha256"], "size_bytes": len(data), "header": header,
                    "manifest": backup_metadata[origin]["manifest_rows"][member], "repository_path": path})
            asset_header(abf_data, element, "abf")
            payloads.append(abf)
            role_hashes = {item["role"]: item["sha256"] for item in payloads}
            identity = sha256(json.dumps(role_hashes, sort_keys=True, separators=(",", ":")).encode("ascii"))
            set_id = f"{element}-backup-{identity}"
            basis = sets_by_id.setdefault(set_id, {"schema_version": 1, "id": set_id, "element": element,
                "family": "historical_backup", "role_hashes_sha256": identity,
                "validation_scope": "original-path backup association; no runtime sealed manifest or scientific acceptance",
                "publication": {"status": "database_only"},
                "source": {"collection": "Historical 3D original-path compute backup", "receipts": [],
                           "license": "unknown", "redistribution": "unknown"},
                "files": payloads, "generation_provenance": {"commit": None, "status": "unknown; not inferred from historical usage"},
                "used_by": []})
            if basis["files"] != payloads:
                raise ValueError("完整内容寻址set发生角色别名冲突")
            basis["source"]["receipts"].append(receipt_path)
            basis["used_by"].append(case_id)
            if entry.get("previous_set_id") and entry["set_id"] != set_id:
                raise ValueError("已有backup species绑定冲突")
            entry.update({"set_id": set_id, "previous_set_id": old_id, "source_receipt": receipt_path,
                          "missing_roles": [role for role in entry.get("missing_roles", []) if role not in ("pp", "nao")],
                          "linkage": "original-path backup association; not a runtime sealed asset manifest"})
            set_ids.append(set_id)
        metadata = {key: value for key, value in backup_metadata[origin].items() if key != "manifest_rows"}
        receipt = {"schema_version": 1, "case_id": case_id, "verification": "original-path backup association with re-read SHA-256/size and STRU/INPUT binding",
            "report": {"name": report_path.name, "sha256": sha256(report_data)}, "backup": metadata,
            "source_run_member": native, "historical_run_directory_sha256": sha256(run_directory.encode()),
            "input_external_root_sha256": {key: sha256(case["input_external_roots"][key].encode()) for key in ("pseudo_dir", "orbital_dir")},
            "working_directory_evidence": {"source_member": native + "/" + evidence_name, "line": int(evidence_line),
                "sha256": sha256(originals[f"{native}/{evidence_name}"])},
            "original_files": native_checks, "assets": asset_checks, "basis_set_ids": set_ids,
            "previous_sets": [{"element": entry["element"], "set_id": entry["previous_set_id"],
                "sha256": readset[portable_path(repo, f"data/elements/{entry['element']}/sets/{entry['previous_set_id']}/set.json")]} for entry in record["species"]],
            "repository_files_verified": [item for item in current_checks if item["path"] != receipt_path],
            "complete_runtime_handoff_included": False, "runtime_asset_seal_verified": False,
            "scope": "PP/NAO restored from the original external roots in the named backup; no runtime asset seal was saved. Changes before backup cannot be excluded. Runtime shards were excluded by backup policy. Scientific acceptance, generation and redistribution remain unresolved."}
        receipt_data = json_bytes(receipt)
        if any(token in receipt_data for token in (b"/" + b"Users/", b"/mnt/", b"/data/home")):
            raise ValueError("公共receipt包含个人路径")
        writes[receipt_path] = receipt_data
        item = file_item("results", receipt_path, receipt_data, "backup_assets_receipt.json")
        previous = next((value for value in record["files"]["results"] if value["path"] == receipt_path), None)
        if previous is not None and previous != item:
            raise ValueError("已有不可变backup receipt声明冲突")
        if previous is None:
            record["files"]["results"].append(item)
        record["source"]["backup_assets_receipt"] = receipt_path
        if not any(entry["missing_roles"] for entry in record["species"]):
            record["missing"] = [note for note in record.get("missing", []) if note != "Exact PP/NAO assets are absent from the archived case; no substitution was made."]
        record_relative = relative + "/record.json"
        original_records[record_relative] = record_data
        writes[record_relative] = json_bytes(record)
        receipts.append(receipt_path)
        plans.append({"case_id": case_id, "asset_role_count": len(asset_checks), "basis_set_ids": set_ids,
                      "original_file_checks": len(native_checks), "receipt": receipt_path})
    for set_id, basis in sets_by_id.items():
        writes[f"data/elements/{basis['element']}/sets/{set_id}/set.json"] = json_bytes(basis)
    for relative, data in writes.items():
        destination = checked_destination(repo, relative)
        if destination.exists() and relative not in original_records and read(destination) != data:
            raise ValueError(f"不可变目标内容冲突: {relative}")
    if write:
        for path, digest in readset.items():
            if hash_file(path) != digest:
                raise ValueError("readset验证后被修改，拒绝写入")
        for relative, data in writes.items():
            destination = checked_destination(repo, relative)
            if relative in original_records:
                if destination.read_bytes() != original_records[relative]:
                    raise ValueError("record写入前被修改，拒绝覆盖")
            elif destination.exists() and destination.read_bytes() != data:
                raise ValueError("不可变目标验证后发生变化")
        for relative, data in writes.items():
            if relative in original_records:
                continue
            destination = checked_destination(repo, relative)
            if destination.exists():
                if destination.read_bytes() != data:
                    raise ValueError("不可变目标写入前发生变化")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as stream:
                    temporary_path = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary_path, destination)
                except FileExistsError:
                    if destination.read_bytes() != data:
                        raise ValueError("不可变目标原子创建冲突")
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
        for relative, original in original_records.items():
            destination = checked_destination(repo, relative)
            if writes[relative] == original:
                continue
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as stream:
                    temporary_path = Path(stream.name)
                    stream.write(writes[relative])
                    stream.flush()
                    os.fsync(stream.fileno())
                if destination.read_bytes() != original:
                    raise ValueError("record原子替换前被修改，拒绝覆盖")
                os.replace(temporary_path, destination)
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
    return {"write": write, "mode": "backup_assets", "cases": plans, "asset_role_count": 20,
            "unique_asset_sha256_count": len({item["sha256"] for item in registry.values()}),
            "new_complete_set_count": len(sets_by_id), "readset_file_count": len(readset),
            "complete_runtime_handoff_included": False, "publication_status": "database_only"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--backup-assets-report", type=Path, help="独立三维原路径备份资产报告；不需要二维来源根")
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument("--write", action="store_true", help="显式启用写入；默认仅验证")
    args = parser.parse_args(argv)
    if args.backup_assets_report:
        if args.source_root or args.raw_root or args.case:
            parser.error("backup-assets模式不能混用二维来源根或case")
        try:
            result = import_backup_assets(args.repo_root, args.backup_assets_report, write=args.write)
        except (ValueError, KeyError, StopIteration, OSError, tarfile.TarError, IndexError) as error:
            parser.exit(1, f"backup-assets: 停止导入: {error}\n")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.source_root is None or args.raw_root is None:
        parser.error("二维模式必须提供--source-root和--raw-root")
    for case_id in args.case or CASES:
        try:
            result = import_case(args.repo_root.resolve(), args.source_root.resolve(), args.raw_root.resolve(), case_id, write=args.write)
        except (ValueError, KeyError, StopIteration, OSError) as error:
            parser.exit(1, f"{case_id}: 停止导入: {error}\n")
        print(json.dumps({"write": args.write, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
