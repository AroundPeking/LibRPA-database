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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument("--write", action="store_true", help="显式启用写入；默认仅验证")
    args = parser.parse_args(argv)
    for case_id in args.case or CASES:
        try:
            result = import_case(args.repo_root.resolve(), args.source_root.resolve(), args.raw_root.resolve(), case_id, write=args.write)
        except (ValueError, KeyError, StopIteration, OSError) as error:
            parser.exit(1, f"{case_id}: 停止导入: {error}\n")
        print(json.dumps({"write": args.write, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
