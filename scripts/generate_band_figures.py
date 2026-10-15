#!/usr/bin/env python3
"""从实际归档表生成单方法前沿图；默认只审计，--write 显式写入。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("plot_bands", ROOT / "scripts/plot_bands.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load plot_bands.py")
plot_bands = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plot_bands)
METHODS = ("KS", "EXX", "GW")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _kpt_nodes(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    inclusive = bool(re.search(r"(?m)^\s*#\s*kpath_convention:\s*inclusive", text))
    lines = [line.strip() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) < 4 or lines[0].upper() != "K_POINTS" or lines[2].lower() != "line":
        raise ValueError("only explicit fractional Line KPT paths are supported")
    count = int(lines[1])
    nodes = []
    for line in lines[3:]:
        fields = line.split("#", 1)[0].split()
        if len(fields) != 4:
            raise ValueError("KPT line nodes require kx ky kz integer segment count")
        coordinates = [float(value) for value in fields[:3]]
        segment = float(fields[3])
        floor = 0 if inclusive else 1
        if not all(math.isfinite(value) for value in coordinates) or segment != int(segment) or segment < floor:
            raise ValueError("invalid KPT coordinate or segment sampling count")
        label = line.split("#", 1)[1].strip() if "#" in line else f"k{len(nodes)}"
        label = "Γ" if label.upper() in {"G", "GAMMA", "\\GAMMA"} else label
        nodes.append({"fractional_kpoint": coordinates, "segment_points": int(segment), "label": label})
    if len(nodes) != count or nodes[-1]["segment_points"] != 1:
        raise ValueError("KPT node count or final endpoint count mismatch")
    return nodes


def _inclusive_kpath_convention(kpt: Path) -> bool:
    """FHI-aims `output band` 段含双端点；共享路径节点在原生表中重复出现。"""
    text = kpt.read_text(encoding="utf-8", errors="replace")
    return bool(re.search(r"(?m)^\s*#\s*kpath_convention:\s*inclusive", text))


def audit_kpath(table: object, kpt: Path, info: Path | None = None) -> dict:
    """核验完整原生采样坐标而非将端点均匀摊开。"""
    nodes = _kpt_nodes(kpt)
    inclusive = _inclusive_kpath_convention(kpt)
    expected, ticks = [], []
    for number, node in enumerate(nodes):
        last = number == len(nodes) - 1
        jump = inclusive and node["segment_points"] == 0
        ticks.append({"x": None, "label": node["label"],
                      "row_index": len(expected) if (inclusive and (last or jump)) else len(expected) + 1,
                      "fractional_kpoint": node["fractional_kpoint"]})
        if last:
            if not inclusive:
                expected.append(node["fractional_kpoint"])
            break
        destination = nodes[number + 1]["fractional_kpoint"]
        count = node["segment_points"]
        if jump:
            continue
        if inclusive:
            if count < 2:
                raise ValueError("inclusive segment convention requires at least two sampled points per segment")
            for index in range(count):
                expected.append([a + (b - a) * index / (count - 1) for a, b in zip(node["fractional_kpoint"], destination)])
        else:
            for index in range(count):
                expected.append([a + (b - a) * index / count for a, b in zip(node["fractional_kpoint"], destination)])
    if table.fractional_kpoints is None or len(expected) != len(table.x):
        raise ValueError("KPT sampling count does not match native table")
    error = max(abs(a - b) for row, source in zip(expected, table.fractional_kpoints) for a, b in zip(row, source))
    if error > 5.1e-7:
        raise ValueError(f"native table fractional path differs from KPT (max error {error:g})")
    for tick in ticks:
        tick["x"] = table.x[tick["row_index"] - 1]
    result = {"status": "verified", "ticks": ticks, "kpt_sha256": sha256(kpt),
              "kpath_convention": "inclusive-segments" if inclusive else "exclusive-segments",
              "coordinate_tolerance": 5.1e-7, "max_kpt_coordinate_error": error,
              "x_axis": "native k-point index", "reciprocal_metric_available": False,
              "note": "Native sampling retained; no reciprocal-distance or inverse-angstrom claim."}
    if info is not None and info.is_file():
        lines = [line.split() for line in info.read_text().splitlines() if line.strip()]
        header = [int(value) for value in lines[0]]
        coordinates = [[float(value) for value in row] for row in lines[1:]]
        if len(header) != 4 or header[3] != len(table.x) or header[2] != 1 or len(coordinates) != len(table.x) or any(len(row) != 3 for row in coordinates):
            raise ValueError("band_kpath_info header or coordinate count mismatch (spin2 unsupported)")
        info_error = max(abs(a - b) for row, source in zip(coordinates, table.fractional_kpoints) for a, b in zip(row, source))
        if info_error > 5.1e-7:
            raise ValueError("band_kpath_info disagrees with native table coordinates")
        result.update({"band_kpath_info_sha256": sha256(info), "band_kpath_info_header": header,
                       "max_info_coordinate_error": info_error})
    return result


def find_audited_kpath(table: object, inputs: dict, root: Path, info: Path | None) -> tuple[dict, dict]:
    """只用同record实际归档的Line路径，逐候选核验全部采样。"""
    candidates = sorted((entry for name, entry in inputs.items() if name.startswith("KPT")),
                        key=lambda entry: (Path(entry["path"]).name != "KPT_nscf",
                                           Path(entry["path"]).name != "KPT", entry["path"]))
    attempts = []
    for entry in candidates:
        try:
            path = root / entry["path"]
            if not path.is_file() or sha256(path) != entry["sha256"]:
                raise ValueError("missing or hash-mismatched archived KPT")
            audit = audit_kpath(table, path, info)
            audit.update({"source_path": entry["path"], "rejected_candidates": attempts})
            return entry, audit
        except (ValueError, OSError) as exc:
            attempts.append({"path": entry["path"], "reason": str(exc)})
    raise ValueError("no archived Line KPT passed full audit: " + "; ".join(item["reason"] for item in attempts))


def _tail_diagnostics(table: object, export_count: int) -> dict:
    width = len(table.energies[0])
    tail = [row[export_count:] for row in table.energies]
    finite = [value for row in tail for value in row if math.isfinite(value)]
    result = {"rejected_raw_band_indices": list(range(export_count + 1, width + 1)),
              "finite_minimum_ev": min(finite) if finite else None,
              "finite_maximum_ev": max(finite) if finite else None,
              "nonfinite_state_count": sum(not math.isfinite(value) for row in tail for value in row),
              "zero_state_count": sum(value == 0 for row in tail for value in row)}
    if width > export_count:
        matches = [k + 1 for k in range(len(tail) - 1)
                   if tail[k] == table.energies[k + 1][:width - export_count]]
        result.update({"next_k_head_exact_match_rows": matches,
                       "next_k_head_compared_row_count": len(tail) - 1,
                       "note": "Tail is rejected by explicit export dimensions, never repaired by sorting; pattern is a separate full-table diagnostic."})
    return result


def _file_entry(path: Path, root: Path, label: str, sources: list[str]) -> dict:
    digest = sha256(path)
    return {"role": "figures", "path": path.relative_to(root).as_posix(), "sha256": digest,
            "size_bytes": path.stat().st_size, "original_sha256": digest, "label": label,
            "transformation": "derived frozen occupation-separated frontier display; raw data unchanged",
            "source_paths": sources, "display_priority": "primary"}


def _write_json(path: Path, value: dict) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def _known_pathology(record: dict, method: str) -> bool:
    properties = record.get("properties", [])
    aliases = {"KS": {"PBE", "DFT", "KS"}, "EXX": {"EXX"}, "GW": {"GW", "G0W0"}}[method]
    if any(p.get("method") in aliases and p.get("status") == "failed" for p in properties):
        return True
    texts = [str(record.get("summary", {}).get("notes", "")), str(record.get("audit", {}))]
    return any(re.search(r"patholog|nonfinite|numerical artifact|unphysical", text, re.I) and method.lower() in text.lower() for text in texts)


def generate_record(record_path: Path, root: Path = ROOT, write: bool = False,
                    allow_weighted_occupations: bool = False) -> dict:
    root = root.resolve()
    record_path = record_path.resolve()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    report = {"calculation_id": record["id"], "generated_methods": [], "added_properties": [], "rejected": {}}
    if record.get("dimension") != "3d":
        return report
    results = {Path(entry["path"]).name: entry for entry in record.get("files", {}).get("results", [])}
    inputs = {Path(entry["path"]).name: entry for entry in record.get("files", {}).get("inputs", [])}
    logs = {Path(entry["path"]).name: entry for entry in record.get("files", {}).get("logs", [])}
    log_entry = logs.get("librpa.out")
    occupied_count = None
    if log_entry and (root / log_entry["path"]).is_file():
        if sha256(root / log_entry["path"]) != log_entry["sha256"]:
            raise ValueError("producer log archive hash mismatch")
        values = set(int(value) for value in re.findall(r"Bands of occupation:\s*(\d+)", (root / log_entry["path"]).read_text(errors="replace")))
        if len(values) == 1:
            occupied_count = next(iter(values))
    if any((record_path.parent / "results").glob("*_band_spin_[2-9]*.dat")):
        report["rejected"]["all"] = "spin2 table present; this single-spin generator refuses rather than silently omitting spin2"
        return report
    metadata = {"schema_version": 2, "calculation_id": record["id"], "energy_unit": "eV",
                "comparison_mode": "single method, own occupied sampled-path VBM reference",
                "note": "Sampled path only, not a global Brillouin-zone gap or numerical acceptance. Original comparison artifacts and raw sources unchanged.",
                "source_sha256": {}, "methods": {}, "rejected": report["rejected"]}
    generated = []
    all_sources = []
    for method in METHODS:
        filename = f"{method}_band_spin_1.dat"
        entry = results.get(filename)
        if not entry:
            report["rejected"][method] = "raw archived band table absent"
            continue
        source = root / entry["path"]
        if not source.is_file() or sha256(source) != entry["sha256"]:
            report["rejected"][method] = "raw archived band table absent or SHA-256 mismatch"
            continue
        try:
            table = plot_bands.parse_abacus_band_table(source)
            info_entry = results.get("band_kpath_info")
            info = root / info_entry["path"] if info_entry else None
            if info_entry and (not info.is_file() or sha256(info) != info_entry["sha256"]):
                raise ValueError("band_kpath_info archive hash mismatch")
            kpt_entry, path_audit = find_audited_kpath(table, inputs, root, info)
            header = path_audit.get("band_kpath_info_header")
            export_count = header[1] if header else len(table.energies[0])
            if header and (not 0 < header[1] <= header[0] or len(table.energies[0]) not in {header[0], header[1]}):
                raise ValueError("raw table width disagrees with declared nbasis/nbands dimensions")
            path_audit["header_schema"] = ["nbasis", "nbands", "nspins", "nkpts"]
            path_audit["schema_evidence"] = "consumer read_data.cpp:2078–2089 and dataset_format.md; preprocess write_kpath_info emits nbasis, nbands, nspins, nkpts; schema evidence is not historical producer commit identification"
            sources = [entry["path"], kpt_entry["path"]] + ([info_entry["path"]] if info_entry else [])
            if log_entry:
                sources.append(log_entry["path"])
            contract = None
            exported_occupations = [row[:export_count] for row in table.occupations]
            if occupied_count is not None and all(math.isfinite(value) and abs(value) <= 1e-8
                                                  for row in exported_occupations for value in row):
                contract = {"kind": "logged_raw_boundary", "occupied_band_count": occupied_count,
                            "evidence": [log_entry["path"]],
                            "definition": "explicit same-log unique Bands of occupation fixes the prefix raw occupied/empty boundary; all-zero export occupations are retained, not guessed as physical empty states"}
            if allow_weighted_occupations and occupied_count is not None and header and contract is None:
                nonzero = [value for row in exported_occupations for value in row if abs(value) > 1e-8]
                if nonzero and all(abs(value * len(table.x) - 2) <= len(table.x) * 5.1e-6 for value in nonzero):
                    contract = {"kind": "uniform_k_weighted", "kpoint_count": len(table.x),
                                "occupied_band_count": occupied_count,
                                "evidence": [log_entry["path"], info_entry["path"]],
                                "definition": "explicit archive contract: full occupied value is 2/nk rounded to five decimals; independently logged occupied-band count agrees"}
            analysis = plot_bands.analyze_frontier(table, occupied_count=occupied_count,
                                                   occupation_contract=contract,
                                                   diagnostic_evidence=[log_entry["path"]] if occupied_count and log_entry else None,
                                                   known_pathological=(_known_pathology(record, method) or
                                                                       (method == "GW" and export_count < len(table.energies[0]))),
                                                   declared_export_band_count=export_count)
            analysis["rejected_tail_audit"] = _tail_diagnostics(table, export_count)
            analysis["kpath_audit"] = path_audit
            analysis["source_result_path"] = entry["path"]
            analysis["source_result_sha256"] = sha256(source)
            metadata["methods"][method] = analysis
            for path in sources:
                metadata["source_sha256"][path] = sha256(root / path)
            all_sources.extend(path for path in sources if path not in all_sources)
            if analysis["status"] != "reported":
                report["rejected"][method] = "; ".join(analysis["diagnostic_reasons"])
            output = record_path.parent / "figures" / f"{method.lower()}_frontier.svg"
            if analysis["figure_status"] == "rejected":
                analysis["unreferenced_previous_svg"] = output.relative_to(root).as_posix()
                continue
            report["generated_methods"].append(method)
            if write:
                output.parent.mkdir(parents=True, exist_ok=True)
                svg = plot_bands.render_frontier_svg(table, analysis, path_audit["ticks"], record.get("material", record["id"]), method)
                if not output.exists() or output.read_text(encoding="utf-8") != svg:
                    output.write_text(svg, encoding="utf-8")
                generated.append(_file_entry(output, root, f"{method} occupation-separated frontier" + (" (diagnostic)" if analysis["status"] == "diagnostic" else ""), sources))
        except (ValueError, OSError) as exc:
            report["rejected"][method] = str(exc)
    sidecar = record_path.parent / "figures/band_frontier_metadata.json"
    for method, property_method in (("KS", "PBE"), ("EXX", "EXX")):
        analysis = metadata["methods"].get(method)
        aliases = {"PBE", "DFT", "KS"} if method == "KS" else {"EXX"}
        if not analysis or analysis["gap_status"] != "reported" or any(item.get("key") == "band_gap" and item.get("method") in aliases for item in record.get("properties", [])):
            continue
        item = {"key": "band_gap", "category": "electronic", "label": "Sampled path band gap",
                "method": property_method, "value": analysis["sampled_path_gap_ev"], "unit": "eV", "status": "reported",
                "definition": "declared finite export window path gap: raw CBM(empty) minus VBM(occupied) over all declared nbands on the fully audited sampled native KPT path; explicit occupation-separated raw boundary, rejected raw tail excluded and diagnosed in sidecar. Not a global Brillouin-zone gap, convergence validation, historical producer identification, or PP recommendation.",
                "evidence": [analysis["source_result_path"], sidecar.relative_to(root).as_posix()]}
        report["added_properties"].append({"method": property_method, "value_ev": item["value"]})
        if write:
            record.setdefault("properties", []).append(item)
    if write and (metadata["methods"] or metadata["rejected"]):
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        _write_json(sidecar, metadata)
        generated.append(_file_entry(sidecar, root, "Frontier display mappings, raw audit and provenance", all_sources))
        new_paths = {entry["path"] for entry in generated}
        rejected_svg_paths = {analysis["unreferenced_previous_svg"] for analysis in metadata["methods"].values()
                              if analysis["figure_status"] == "rejected"}
        retained = [entry for entry in record["files"].get("figures", [])
                    if entry["path"] not in new_paths | rejected_svg_paths]
        for entry in retained:
            if Path(entry["path"]).name in {"band_comparison.svg", "band_comparison.json"}:
                entry["display_priority"] = "secondary"
        record["files"]["figures"] = generated + retained
        _write_json(record_path, record)
    return report


def generate_hbn_record(record_path: Path, root: Path = ROOT, write: bool = False) -> dict:
    """Audit the manuscript replacement hBN chain; never promote its GW spectrum."""
    root = root.resolve()
    record_path = record_path.resolve()
    original = record_path.read_bytes()
    record = json.loads(original)
    if (record.get("id") != "hbn-tzdp10-fgext-20261008"
            or record.get("dimension") != "2d"
            or "status" in record):
        raise ValueError("replacement hBN identity mismatch or reintroduced record-level status")
    declared = {entry["path"]: entry for group in record["files"].values() for entry in group}
    verified = {}

    def source(name: str) -> tuple[dict, bytes]:
        matches = [entry for entry in declared.values() if Path(entry["path"]).name == name]
        if len(matches) != 1:
            raise ValueError(f"ambiguous or missing same-record source: {name}")
        entry = matches[0]
        path = root / entry["path"]
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError("hBN source escapes archive")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"] or len(data) != entry["size_bytes"]:
            raise ValueError(f"hBN source hash/size mismatch: {name}")
        verified[entry["path"]] = data
        return entry, data

    receipt_entry, receipt_data = source("calculation__gw_k12_fgext_20261008__PBE_PATH_RECEIPT.json")
    receipt = json.loads(receipt_data)
    if (receipt.get("route") != "same_producer_pbe_path" or receipt.get("path_points") != 91
            or receipt.get("states") != 44 or receipt.get("spin") != 1
            or abs(receipt.get("path_occupied_band_weight", 0) * 91 - 2) > 1e-6):
        raise ValueError("hBN PBE path receipt does not establish the weighted 91/44/1 contract")
    nscf_entry, nscf_data = source("calculation__pbe_path_91_20261008__OUT.ABACUS__running_nscf.log")
    scf_entry, scf_data = source("calculation__OUT.ABACUS__running_scf.log")
    commits = []
    for data in (scf_data, nscf_data):
        text = data.decode("utf-8")
        if set(re.findall(r"Occupied electronic states\s*=\s*(\d+)", text)) != {"4"}:
            raise ValueError("hBN logged occupied-state boundary is not uniquely four")
        if set(re.findall(r"NBANDS\)\s*=\s*(\d+)", text)) != {"44"}:
            raise ValueError("hBN logged band dimension mismatch")
        identities = set(re.findall(r"(?m)^\s*Commit:\s*([0-9a-f]{40})\b", text))
        if len(identities) != 1:
            raise ValueError("hBN each SCF/NSCF log must establish one full source identity")
        commits.append(next(iter(identities)))
    if commits[0] != commits[1]:
        raise ValueError("hBN SCF/NSCF full source identity is conflicting")
    commit = commits[0]
    app = record.setdefault("software", {}).setdefault("abacus", {})
    if app.get("commit") not in (None, commit):
        raise ValueError("hBN recorded ABACUS identity conflicts with original logs")
    kpt_entry, _ = source("calculation__KPT_nscf")
    contract = {"kind": "uniform_k_weighted", "kpoint_count": 91, "occupied_band_count": 4,
                "evidence": [receipt_entry["path"], nscf_entry["path"]]}
    sidecar = record_path.parent / "figures/hbn_frontier_audit.json"
    sidecar_relative = sidecar.relative_to(root).as_posix()
    metadata = {"schema_version": 2, "calculation_id": record["id"], "energy_unit": "eV",
                "comparison_mode": "method-own occupied path VBM, fixed raw bands 1-8",
                "scientific_status": "path_diagnostic; unchanged",
                "source_identity": {"abacus": commit, "librpa": "not inferred; original log GITDIR-NOTFOUND"},
                "chain_scope": "Same-record replacement manuscript chain, PBE path receipt and logged boundary; not a complete offline runtime handoff or full-spectrum GW acceptance.",
                "source_sha256": {}, "methods": {}}
    writes, generated = {}, []
    all_sources = []
    for method in METHODS:
        entry, _ = source(f"{method}_band_spin_1.dat")
        table = plot_bands.parse_abacus_band_table(root / entry["path"])
        if len(table.x) != 91 or len(table.energies[0]) != 44:
            raise ValueError("hBN original spectrum dimensions mismatch")
        path_audit = audit_kpath(table, root / kpt_entry["path"])
        analysis = plot_bands.analyze_frontier(table, occupation_contract=contract,
                                              occupied_window=4, empty_window=4,
                                              known_pathological=method == "GW")
        if analysis["occupation_audit"].get("full_occupation") != 2:
            raise ValueError("hBN single-spin receipt requires occupied weights of 2/nk")
        if method in ("KS", "EXX"):
            gap = analysis.get("sampled_path_gap_ev")
            if (analysis.get("gap_status") != "reported" or type(gap) not in (int, float)
                    or not math.isfinite(gap) or gap <= 0):
                raise ValueError(f"hBN {method} requires a finite reported full-spectrum path gap")
        if method == "KS" and abs(analysis["sampled_path_gap_ev"] - receipt["fundamental_gap_eV"]) > 5e-6:
            raise ValueError("hBN original KS table disagrees with same-producer receipt")
        if method == "GW" and (analysis["gap_status"] != "rejected"
                or abs(analysis["selected_window_path_gap_ev"] - record["summary"]["value"]) > 5e-6):
            raise ValueError("hBN fixed frontier disagrees with recorded restricted observable")
        sources = [entry["path"], kpt_entry["path"], receipt_entry["path"], scf_entry["path"], nscf_entry["path"]]
        analysis.update({"source_result_path": entry["path"], "source_sha256": entry["sha256"],
                         "kpath_audit": path_audit, "source_paths": sources})
        metadata["methods"][method] = analysis
        all_sources.extend(sources)
        output = record_path.parent / f"figures/{method.lower()}_frontier.svg"
        svg = plot_bands.render_frontier_svg(table, analysis, path_audit["ticks"], "hBN", method).encode("utf-8")
        relative = output.relative_to(root).as_posix()
        writes[relative] = svg
        generated.append({"role": "figures", "path": relative, "sha256": hashlib.sha256(svg).hexdigest(),
                          "size_bytes": len(svg), "label": f"hBN {method} frozen frontier" + (" (diagnostic)" if method == "GW" else ""),
                          "transformation": "derived audited method-own frontier; original bytes unchanged",
                          "source_paths": sources, "display_priority": "primary",
                          "scientific_status": "archived_diagnostic" if method == "GW" else "sampled_path_only"})
    metadata["source_sha256"] = {path: hashlib.sha256(data).hexdigest() for path, data in sorted(verified.items())}
    data = (json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    writes[sidecar_relative] = data
    generated.append({"role": "figures", "path": sidecar_relative, "sha256": hashlib.sha256(data).hexdigest(),
                      "size_bytes": len(data), "label": "hBN original spectrum audit and frozen display mappings",
                      "source_paths": sorted(set(all_sources))})
    exx = {"key": "sampled_path_gap_ev", "category": "electronic", "label": "Sampled path gap",
           "method": "EXX", "value": metadata["methods"]["EXX"]["sampled_path_gap_ev"], "unit": "eV", "status": "reported",
           "definition": "Finite occupation-separated gap over all 44 raw bands of the same-record 91-point EXX path; logged four occupied states and receipt-backed 2/nk weights. Not a global BZ gap, an old hBN value, or scientific convergence acceptance.",
           "evidence": [metadata["methods"]["EXX"]["source_result_path"], sidecar_relative]}
    props = record.setdefault("properties", [])
    existing = [prop for prop in props if prop.get("method") == "EXX"]
    if existing and existing != [exx]:
        raise ValueError("hBN EXX property conflict; refusing overwrite")
    if not existing:
        props.append(exx)
    for prop in props:
        if prop.get("key") == "summary_value" and prop.get("method") == "GW path":
            prop["definition"] = "Restricted raw-band-5 frontier path gap of the replacement hBN production chain. Higher raw states intrude and one full-spectrum value is nonfinite; not an accepted fundamental gap."
            prop["evidence"] = [metadata["methods"]["GW"]["source_result_path"], sidecar_relative]
    app["commit"] = commit
    app["evidence"] = [scf_entry["path"], nscf_entry["path"]]
    app.pop("missing_reason", None)
    app["identity_note"] = "Full source commit printed identically in the archived SCF and same-producer NSCF logs. Executable hash and source-tree dirtiness were not retained; not a current-profile validation."
    new_paths = {entry["path"] for entry in generated}
    retained = [entry for entry in record["files"]["figures"] if entry["path"] not in new_paths]
    record["files"]["figures"] = generated + retained
    record_relative = record_path.relative_to(root).as_posix()
    writes[record_relative] = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if write:
        # Recheck the complete read set before any write; never alter raw inputs/results.
        if record_path.read_bytes() != original or any((root / path).read_bytes() != content for path, content in verified.items()):
            raise ValueError("hBN read set changed during verification")
        for relative, content in writes.items():
            destination = root / relative
            if destination.exists() and relative != record_relative and destination.read_bytes() != content:
                # Viewport-only revisions may replace the exact currently
                # registered derived file; arbitrary conflicting bytes still fail.
                previous = declared.get(relative)
                before = destination.read_bytes()
                if (previous is None or previous.get("role") != "figures"
                        or hashlib.sha256(before).hexdigest() != previous["sha256"]
                        or len(before) != previous["size_bytes"]):
                    raise ValueError("hBN derived artifact conflict; refusing overwrite")
        for relative, content in writes.items():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or destination.read_bytes() != content:
                destination.write_bytes(content)
    return {"calculation_id": record["id"], "write": write, "generated_methods": list(METHODS),
            "abacus_commit": commit, "exx_path_gap_ev": exx["value"],
            "gw_restricted_path_gap_ev": metadata["methods"]["GW"]["selected_window_path_gap_ev"],
            "source_files_verified": len(verified), "gw_full_spectrum_accepted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--audit", action="store_true", help="只读审计，不写文件（默认）")
    mode.add_argument("--write", action="store_true", help="显式写入新SVG/sidecar并补齐可报告的缺失属性")
    parser.add_argument("--allow-weighted-occupations", action="store_true", help="explicit evidence-backed 2/nk archive contract; never infer all-zero occupations")
    parser.add_argument("--replacement-hbn", action="store_true", help="audit only the exact replacement manuscript hBN chain and preserve restricted GW status")
    args = parser.parse_args()
    if args.replacement_hbn:
        path = args.root / "data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008/record.json"
        print(json.dumps(generate_hbn_record(path, args.root, args.write), ensure_ascii=False, indent=2))
        return 0
    reports = [generate_record(path, args.root, args.write, args.allow_weighted_occupations)
               for path in sorted(args.root.glob("data/calculations/3d/*/*/record.json"))]
    print(json.dumps({"write": args.write, "records": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
