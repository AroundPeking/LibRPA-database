#!/usr/bin/env python3
"""Migrate legacy calculation gap summaries into evidence-linked properties."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path, PurePosixPath

RESULT_PATTERNS = {
    "PBE": re.compile(r"(?:^|[^a-z0-9])(?:ks|pbe|dft)(?:[^a-z0-9]|$)", re.IGNORECASE),
    "EXX": re.compile(r"(?:^|[^a-z0-9])exx(?:[^a-z0-9]|$)", re.IGNORECASE),
    "G0W0": re.compile(r"(?:^|[^a-z0-9])gw(?:[^a-z0-9]|$)", re.IGNORECASE),
    "GW path": re.compile(r"(?:^|[^a-z0-9])gw(?:[^a-z0-9]|$)", re.IGNORECASE),
}
IGNORED_NAMES = ("manifest", "provenance", "receipt", "audit", "eigenvector", "eigenvalue")


def _result_evidence(record: dict, method: str) -> str:
    candidates = []
    for item in record.get("files", {}).get("results", []):
        path = item.get("path", "")
        name = f"{item.get('label', '')} {Path(path).name}"
        lowered = name.lower()
        if any(part in lowered for part in IGNORED_NAMES):
            continue
        if RESULT_PATTERNS[method].search(name):
            is_band_table = bool(re.search(r"band(?:s|_|\b)", lowered))
            has_data_extension = bool(re.search(r"\.(?:dat|txt|csv)(?:\s|$)", lowered))
            candidates.append((not is_band_table, not has_data_extension, path))
    if not candidates:
        raise ValueError(f"{record.get('id', '<unknown>')}: no {method} result file for a legacy property")
    return sorted(candidates)[0][2]


def _property(record: dict, key: str, label: str, method: str, value: object,
              summary: dict, evidence_method: str, summary_key: str) -> dict:
    evidence = _result_evidence(record, evidence_method)
    status = "validated" if record.get("status") == "gw_validated" else "reported"
    return {
        "key": key,
        "category": "electronic",
        "label": label,
        "method": method,
        "value": value,
        "unit": summary.get("unit") or "eV",
        "status": status,
        "source_summary_key": summary_key,
        "evidence": [evidence],
    }


def _same_value(left: object, right: object) -> bool:
    if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
    return left == right


def migrate_record(record: dict) -> dict:
    result = dict(record)
    summary = record.get("summary") or {}
    properties = list(record.get("properties", []))

    def add(item: dict) -> None:
        identity = (item["category"], item["key"], item["method"])
        for index, existing in enumerate(properties):
            if not isinstance(existing, dict) or (existing.get("category"), existing.get("key"), existing.get("method")) != identity:
                continue
            # Equal numeric values do not establish migration ownership. Unmarked
            # contributions and reviewed statuses must never be silently overwritten.
            source_owned = existing.get("source_summary_key") == item["source_summary_key"]
            if source_owned and existing.get("status") == "reported":
                updated = dict(existing)
                if updated.get("definition") in (summary.get("gap_definition"), summary.get("observable")):
                    updated.pop("definition", None)
                updated.update(item)
                properties[index] = updated
            return
        properties.append(item)

    dft_key = "dft_gap_ev" if summary.get("dft_gap_ev") is not None else "pbe_gap_ev"
    dft_value = summary.get(dft_key)
    if dft_value is not None:
        add(_property(record, "band_gap", "Band gap", "PBE", dft_value, summary, "PBE", dft_key))
    if summary.get("exx_gap_ev") is not None:
        add(_property(record, "band_gap", "Band gap", "EXX", summary["exx_gap_ev"], summary, "EXX", "exx_gap_ev"))

    observable = str(summary.get("observable", "")).lower()
    gw_method = "GW path" if "path" in observable else "G0W0"
    if summary.get("gw_gap_ev") is not None:
        add(_property(record, "band_gap", "Band gap", gw_method, summary["gw_gap_ev"], summary, gw_method, "gw_gap_ev"))

    summary_value = summary.get("value")
    if (summary_value is not None and "gap" in observable
            and any(term in observable for term in ("gw", "g0w0"))
            and summary.get("unit") == "eV"):
        value_method = gw_method
        already_mapped = any(item.get("method") == value_method and _same_value(item.get("value"), summary_value)
                             for item in properties if isinstance(item, dict))
        has_summary_row = any(item.get("key") == "summary_value" and item.get("method") == value_method
                              for item in properties if isinstance(item, dict))
        if has_summary_row or not already_mapped:
            label = str(summary.get("observable") or "Reported gap")
            add(_property(record, "summary_value", label, value_method, summary_value, summary, value_method, "value"))

    result["properties"] = properties
    return result


def migrate(root: Path, write: bool) -> int:
    changed = 0
    for path in sorted((root / "data/calculations").glob("*/*/*/record.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        updated = migrate_record(record)
        if updated != record:
            changed += 1
            if write:
                path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _portable(root: Path, text: str) -> Path:
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("证据路径不便携")
    result = root.joinpath(*path.parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError("证据路径逃逸根目录")
    return result


def _verified_file(root: Path, item: dict) -> bytes:
    data = _portable(root, item["path"]).read_bytes()
    if _digest(data) != item["sha256"] or len(data) != item["size_bytes"]:
        raise ValueError(f"记录文件hash/尺寸不匹配: {item['path']}")
    return data


def _native_table(data: bytes, method: dict, native_path: list) -> dict:
    nocc, nbands, npoints = (method.get(key) for key in ("occupied_states", "raw_band_count", "npoints"))
    if (type(nocc) is not int or type(nbands) is not int or type(npoints) is not int
            or not 0 < nocc < nbands or npoints <= 0 or len(native_path) != npoints):
        raise ValueError("缺少可靠原生维度/占据计数/路径")
    rows = [[float(value) for value in line.split()] for line in data.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != npoints or any(len(row) != 4 + 2 * nbands for row in rows):
        raise ValueError("index xyz occ E原谱维度不匹配")
    weights = None
    energies = []
    for index, (row, point) in enumerate(zip(rows, native_path), 1):
        if (row[0] != index or len(point) != 3 or any(not math.isfinite(value) for value in row[:4])
                or any(not math.isfinite(value) or not math.isfinite(reference) or abs(value - reference) > 5e-7 for value, reference in zip(row[1:4], point))):
            raise ValueError("原生index/xyz路径不匹配")
        occupation = row[4::2]
        if (any(not math.isfinite(value) or value <= 0 for value in occupation[:nocc])
                or any(not math.isfinite(value) or abs(value) > 1e-10 for value in occupation[nocc:])):
            raise ValueError("固定正occupied/零empty边界不匹配")
        if weights is None:
            weights = occupation[:nocc]
        if any(abs(value - weights[0]) > 1e-8 for value in occupation[:nocc]):
            raise ValueError("原谱occupied权重不是固定正值")
        energies.append(row[5::2])
    nonfinite = sum(not math.isfinite(value) for row in energies for value in row)
    window = method.get("frozen_raw_window_one_based", [])
    if (not window or any(type(value) is not int or not 1 <= value <= nbands for value in window)
            or len(set(window)) != len(window) or not any(value <= nocc for value in window)
            or not any(value > nocc for value in window)):
        raise ValueError("缺少可靠的侧录选窗占据边界")
    selected = [row[value - 1] for row in energies for value in window]
    if any(not math.isfinite(value) for value in selected):
        raise ValueError("侧录选窗包含非有限值")
    selected_gap = min(row[value - 1] for row in energies for value in window if value > nocc) - max(row[value - 1] for row in energies for value in window if value <= nocc)
    reported = method.get("path_gap_ev")
    raw_gap = None if nonfinite else min(value for row in energies for value in row[nocc:]) - max(value for row in energies for value in row[:nocc])
    if isinstance(reported, bool) or not isinstance(reported, (int, float)) or not math.isfinite(reported):
        raise ValueError("侧录path_gap不是有限数值")
    matches = abs(selected_gap - reported) <= 5e-6
    if not matches and not (raw_gap is not None and raw_gap <= 0):
        raise ValueError("侧录path_gap与原谱选窗不匹配")
    # 已证实异常的原谱只作诊断。保存重新计算的冻结窗与原侧录值的
    # 不一致，不把原侧录数值替代重算值，也不据此生成普通gap。
    return {"occupied_states": nocc, "raw_band_count": nbands, "npoints": npoints,
            "nonfinite_entries": nonfinite, "full_raw_path_gap_ev": raw_gap,
            "selected_window_path_gap_ev": selected_gap, "sidecar_path_gap_ev": reported,
            "sidecar_selected_window_matches": matches}


def recover_table_record(root: Path, source_root: Path, source_path: Path, record: dict) -> tuple[dict, dict]:
    source_data = source_path.read_bytes()
    original_sha = record.get("source", {}).get("original_sidecar_sha256")
    if _digest(source_data) != original_sha:
        raise ValueError("源table_band_source SHA不等于record原始侧录SHA")
    source = json.loads(source_data)
    if source.get("material") not in (None, source_path.parents[1].name):
        raise ValueError("原侧录material与源目录不一致")
    result = copy.deepcopy(record)
    files = result["files"]
    sidecar_item = next(item for item in files["results"] if Path(item["path"]).name == "band_window_and_provenance.json")
    if sidecar_item.get("original_sha256") != original_sha:
        raise ValueError("record侧录原SHA不匹配")
    sidecar = json.loads(_verified_file(root, sidecar_item))
    native = source.get("native_kpath_fractional")
    if not isinstance(native, list) or native != sidecar.get("native_kpath_fractional"):
        raise ValueError("源及记录侧录原生路径不匹配")
    methods, bands = {}, {}
    stats = {"properties_added": 0, "valid_path_gaps": 0, "diagnostics": 0, "figure_links_added": 0}
    for method in ("KS", "EXX", "GW"):
        original_method = source["methods"][method]
        archived_method = sidecar["methods"][method]
        for key in ("occupied_states", "raw_band_count", "npoints", "frozen_raw_window_one_based", "path_gap_ev"):
            if original_method.get(key) != archived_method.get(key):
                raise ValueError(f"{method}: 原始及记录侧录{key}不一致")
        spectrum_item = next(item for item in files["results"] if Path(item["path"]).name == f"{method}_bands.dat")
        data = _verified_file(root, spectrum_item)
        raw_path = Path(original_method["source"]["original_path"])
        if not raw_path.is_absolute():
            raise ValueError("独立原谱必须给出源侧录绝对路径")
        production_data = raw_path.read_bytes()
        converted_npz = raw_path.suffix.lower() == ".npz"
        if converted_npz:
            archive_path = original_method["source"].get("archive_path")
            if method != "KS" or original_method["source"].get("format") != "dat" or not isinstance(archive_path, str):
                raise ValueError(f"{method}: NPZ来源没有明确的已归档KS转换DAT合同")
            # 原侧录的SHA锚定转换DAT；NPZ与DAT不是同一字节资产。
            # 这里只记录原NPZ实际身份，不宣称独立重做或验证转换。
            raw_data = _portable(source_root.parents[1], archive_path).read_bytes()
        else:
            raw_data = production_data
        digest = _digest(raw_data)
        if (data != raw_data
                or digest != original_method["source"]["sha256"]
                or digest != archived_method["source"]["sha256"]
                or spectrum_item.get("original_sha256") != digest):
            raise ValueError(f"{method}: 原谱/源/记录及侧录hash不匹配")
        if converted_npz:
            identity = {
                "source_format": "archived_dat_converted_from_npz",
                "production_source_basename": raw_path.name,
                "production_source_sha256": _digest(production_data),
                "archived_table_sha256": digest,
                "conversion_independently_verified": False,
                "evidence": [sidecar_item["path"]],
            }
            if spectrum_item.get("source_identity") not in (None, identity):
                raise ValueError(f"{method}: 已有NPZ/DAT来源身份冲突")
            spectrum_item["source_identity"] = identity
        metrics = _native_table(raw_data, archived_method, native)
        if original_method["source"].get("shape") != [metrics["npoints"], metrics["raw_band_count"]]:
            raise ValueError(f"{method}: 原谱source.shape不匹配")
        methods[method], bands[method] = metrics, spectrum_item["path"]
        if method == "GW":
            continue
        raw_gap, selected_gap = metrics["full_raw_path_gap_ev"], metrics["sidecar_path_gap_ev"]
        valid = raw_gap is not None and raw_gap > 0 and abs(raw_gap - selected_gap) <= 5e-6
        prop_method = "PBE" if method == "KS" else "EXX"
        if valid:
            stats["valid_path_gaps"] += 1
            properties = result.setdefault("properties", [])
            def same_method(item: dict) -> bool:
                name = str(item.get("method", "")).upper()
                return name in ({"PBE", "KS", "DFT"} if method == "KS" else {"EXX"})
            existing = [item for item in properties if isinstance(item, dict) and same_method(item)
                        and re.fullmatch(r"(?:band_gap|(?:sampled_)?path_gap(?:_ev)?)", str(item.get("key", "")))]
            for item in existing:
                if item.get("source_sidecar_key") == f"methods.{method}.path_gap_ev":
                    value = item.get("value")
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or not math.isfinite(value) or abs(value - selected_gap) > 5e-6
                            or item.get("unit") != "eV"):
                        raise ValueError(f"{method}: 已有来源自有路径性质与原谱数值/单位冲突")
            if not existing:
                definition = "Sampled path CBM minus VBM from finite original bands with sidecar occupied-state boundary; not a full-Brillouin-zone fundamental gap"
                if converted_npz:
                    definition = "Sampled path CBM minus VBM of the hash-verified archived DAT converted from NPZ; original NPZ identity retained but conversion not independently verified; not a full-Brillouin-zone fundamental gap"
                properties.append({"key": "sampled_path_gap_ev", "category": "electronic", "label": "Sampled path gap",
                                   "method": prop_method, "value": selected_gap, "unit": "eV", "status": "reported",
                                   "definition": definition,
                                   "evidence": [bands[method], sidecar_item["path"]],
                                   "source_sidecar_key": f"methods.{method}.path_gap_ev"})
                stats["properties_added"] += 1
        else:
            if raw_gap is not None and raw_gap > 0:
                raise ValueError(f"{method}: 正全谱gap与侧录不一致，拒绝恢复")
            diagnostics = result.setdefault("method_diagnostics", [])
            if not isinstance(diagnostics, list):
                raise ValueError("method_diagnostics必须使用列表合同")
            diagnostic = {"method": prop_method, "status": "rejected", "kind": "archived_raw_band_anomaly", **metrics,
                          "frozen_window_path_gap_ev": metrics["selected_window_path_gap_ev"],
                          "evidence": [bands[method], sidecar_item["path"]],
                          "message": "Full raw and frozen-window anomalies retained separately; not an accepted gap. A smaller window is not a numerical repair; archive completeness remains blocked."
                                     + (" Archived sidecar path value differs from the independently recomputed frozen window; both are retained as diagnostics." if not metrics["sidecar_selected_window_matches"] else "")}
            previous = [item for item in diagnostics if item.get("method") == prop_method]
            if len(previous) > 1 or (previous and previous[0] != diagnostic):
                raise ValueError("已有method_diagnostics与原谱诊断冲突")
            if not previous:
                diagnostics.append(diagnostic)
            stats["diagnostics"] += 1

    figure_root = source_root.parents[1]
    if set(source.get("figure_outputs", {})) != {"KS", "EXX", "GW"}:
        raise ValueError("原始图输出未完整覆盖三谱方法")
    for method, output in source["figure_outputs"].items():
        if method not in bands:
            raise ValueError("原图方法不属于已验证三谱")
        for extension in ("png", "pdf"):
            original_relative = output[extension]
            if PurePosixPath(original_relative).parent != PurePosixPath("figures/table_material_bands"):
                raise ValueError("原图不位于明确table_material_bands目录")
            name = PurePosixPath(original_relative).name
            figure = next(item for item in files["figures"] if Path(item["path"]).name == name)
            figure_data = _verified_file(root, figure)
            original_figure = _portable(figure_root, original_relative).read_bytes()
            if (figure_data != original_figure or _digest(original_figure) != figure.get("original_sha256")):
                raise ValueError("原图字节/hash不等于record归档原图")
            links = [bands[method], sidecar_item["path"]]
            if figure.get("source_paths") not in (None, links) or figure.get("method") not in (None, method):
                raise ValueError("原图已有不同方法/来源关联")
            if figure.get("source_paths") is None:
                stats["figure_links_added"] += 1
            figure.update({"source_paths": links, "method": method})
            if any(item.get("method") == ("PBE" if method == "KS" else method)
                   for item in result.get("method_diagnostics", [])):
                figure["scientific_status"] = "archived_diagnostic"
                figure["notes"] = "Archived diagnostic figure of anomalous original raw bands; not a newly accepted result"
    return result, stats


def recover_table_evidence(root: Path, source_root: Path, write: bool = False) -> dict:
    root, source_root = root.resolve(), source_root.resolve()
    paths = sorted((root / "data/calculations/2d").glob("*/*/record.json"))
    records = [(path, path.read_bytes()) for path in paths]
    by_original = {}
    for path, data in records:
        record = json.loads(data)
        digest = record.get("source", {}).get("original_sidecar_sha256")
        if digest:
            if digest in by_original:
                raise ValueError("二维原侧录SHA映射不唯一")
            by_original[digest] = (path, data, record)
    plans, verified = [], []
    totals = {"records_changed": 0, "records_verified": 0, "properties_added": 0, "valid_path_gaps": 0, "diagnostics": 0, "figure_links_added": 0}
    for source_path in sorted(source_root.glob("*/provenance/table_band_source.json")):
        digest = _digest(source_path.read_bytes())
        if digest not in by_original:
            raise ValueError(f"原侧录未匹配同record: {source_path.parents[1].name}")
        path, before, record = by_original[digest]
        if record.get("dimension") != "2d":
            raise ValueError("恢复模式禁止修改非二维record")
        try:
            updated, stats = recover_table_record(root, source_root, source_path, record)
        except (ValueError, KeyError, StopIteration, OSError) as error:
            raise ValueError(f"{record.get('id')}: {error}") from error
        verified.append(updated)
        totals["records_verified"] += 1
        for key, value in stats.items():
            totals[key] += value
        if updated != record:
            plans.append((path, before, updated))
            totals["records_changed"] += 1
    if not totals["records_verified"]:
        raise ValueError("未找到table_band_source证据")
    totals["anomalies"] = [{"case_id": updated["id"], "method": diagnostic["method"],
                            "full_raw_path_gap_ev": diagnostic["full_raw_path_gap_ev"],
                            "selected_window_path_gap_ev": diagnostic["selected_window_path_gap_ev"]}
                           for updated in verified for diagnostic in updated.get("method_diagnostics", [])
                           if diagnostic.get("kind") == "archived_raw_band_anomaly"]
    if write:
        # 全部输入先预审完成，并确认record未被其他写者改变后才开始原子替换。
        if any(path.read_bytes() != before for path, before, _ in plans):
            raise ValueError("预审后record被修改，拒绝写入")
        for path, before, updated in plans:
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as stream:
                    temporary_path = Path(stream.name)
                    stream.write((json.dumps(updated, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
                if path.read_bytes() != before:
                    raise ValueError("原子替换前record被修改")
                os.replace(temporary_path, path)
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write", action="store_true", help="显式写入迁移结果；默认仅预审")
    parser.add_argument("--source-root", type=Path, help="只读paper_materials原始证据目录")
    parser.add_argument("--recover-table-evidence", action="store_true", help="仅恢复二维原谱路径性质及原图关联，不运行旧summary迁移")
    args = parser.parse_args()
    if args.recover_table_evidence:
        if args.source_root is None:
            parser.error("--recover-table-evidence要求显式--source-root")
        try:
            stats = recover_table_evidence(args.root, args.source_root, write=args.write)
        except (ValueError, KeyError, StopIteration, OSError) as error:
            parser.exit(1, f"二维证据恢复停止，未通过预审: {error}\n")
        print(json.dumps({"write": args.write, **stats}, ensure_ascii=False))
        return 0
    changed = migrate(args.root, write=args.write)
    if args.write:
        print(f"properties migrated: {changed} calculation records updated")
    else:
        print(f"properties migration preview: {changed} calculation records would change; pass --write to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
