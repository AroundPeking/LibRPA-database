#!/usr/bin/env python3
"""解析原生能带、审计占据并绘制可追溯的前沿窗。"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
from typing import Iterable


class BandTable:
    def __init__(self, x: list[float], energies: list[list[float]],
                 occupations: list[list[float]] | None = None,
                 native_kpoint_indices: list[int] | None = None,
                 fractional_kpoints: list[list[float]] | None = None) -> None:
        self.x = x
        self.energies = energies
        self.occupations = occupations
        self.occupation = occupations
        self.native_kpoint_indices = native_kpoint_indices
        self.fractional_kpoints = fractional_kpoints


def parse_band_table(path: Path) -> BandTable:
    """保留通用 ``x energy_1 energy_2 ...`` 接口及原始列顺序。"""
    xs, rows = [], []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            values = [float(item) for item in raw.split()]
        except ValueError as exc:
            raise ValueError(f"line {number}: expected numeric columns") from exc
        if len(values) < 2:
            raise ValueError(f"line {number}: expected x and at least one energy")
        if rows and len(values) - 1 != len(rows[0]):
            raise ValueError("all data rows must have the same number of energy columns")
        xs.append(values[0])
        rows.append(values[1:])
    if not rows:
        raise ValueError("band table contains no data rows")
    return BandTable(xs, rows)


def parse_abacus_band_table(path: Path) -> BandTable:
    """原样保留 index/kx/ky/kz、occupation/energy 对；不猜测占据语义。"""
    rows, occupations, indices, coordinates = [], [], [], []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = raw.split()
        if len(fields) < 6 or (len(fields) - 4) % 2:
            raise ValueError(f"line {number}: expected occupation/energy pairs")
        try:
            values = [float(item) for item in fields]
        except ValueError as exc:
            raise ValueError(f"line {number}: expected numeric columns") from exc
        if not math.isfinite(values[0]) or values[0] != int(values[0]):
            raise ValueError(f"line {number}: native k-point index must be an integer")
        index = int(values[0])
        if index < 1 or (indices and index <= indices[-1]):
            raise ValueError("native k-point indices must be positive and strictly increasing")
        if not all(math.isfinite(value) for value in values[1:4]):
            raise ValueError("fractional k-point coordinates must be finite")
        if rows and len(values[5::2]) != len(rows[0]):
            raise ValueError("all ABACUS rows must have the same number of bands")
        indices.append(index)
        coordinates.append(values[1:4])
        occupations.append(values[4::2])
        rows.append(values[5::2])
    if not rows:
        raise ValueError("ABACUS band table contains no data rows")
    return BandTable([float(index) for index in indices], rows, occupations, indices, coordinates)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_ticks(path: Path | None) -> list[dict]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    ticks = value.get("ticks", value) if isinstance(value, dict) else value
    if not isinstance(ticks, list):
        raise ValueError("labels file must contain a list or an object with a ticks list")
    result = []
    for index, tick in enumerate(ticks):
        if not isinstance(tick, dict) or not isinstance(tick.get("x"), (int, float)) or not isinstance(tick.get("label"), str):
            raise ValueError(f"labels[{index}] must contain numeric x and string label")
        result.append({"x": float(tick["x"]), "label": tick["label"]})
    return result


def integer_occupation_boundary(table: BandTable, contract: dict | None = None) -> tuple[int, dict]:
    """严格整数占据；加权占据仅接受有日志证据的显式合同。"""
    if table.occupations is None:
        raise ValueError("missing occupations: ordinary gap analysis refused")
    if len(table.occupations) != len(table.energies) or any(len(o) != len(e) for o, e in zip(table.occupations, table.energies)):
        raise ValueError("occupation/energy shape mismatch")
    if contract and contract.get("kind") == "logged_raw_boundary":
        count = contract.get("occupied_band_count")
        width = len(table.energies[0])
        if not contract.get("evidence") or not isinstance(count, int) or not 0 < count < width:
            raise ValueError("raw boundary requires an explicit evidence-backed logged count")
        if any(not math.isfinite(value) or abs(value) > 1e-8
               for row in table.occupations for value in row):
            raise ValueError("logged raw boundary contract requires finite all-zero export occupations")
        return count, {"kind": "explicit_logged_raw_boundary", "occupied_band_count": count,
                       "raw_occupation_semantics": "all-zero export is not a physical empty-state classification",
                       "definition": contract.get("definition"), "evidence": contract["evidence"]}
    scale = 1.0
    tolerance = 1e-8
    if contract:
        if contract.get("kind") != "uniform_k_weighted" or not contract.get("evidence"):
            raise ValueError("weighted occupations require an explicit evidence-backed contract")
        count = contract.get("kpoint_count")
        if count != len(table.x) or count < 1:
            raise ValueError("weighted occupation k-point count mismatch")
        scale = float(count)
        tolerance = 5.1e-6 * scale  # 原始表按五位小数输出加权占据。
    boundaries, full_values = [], set()
    for row in table.occupations:
        normalized = [value * scale for value in row]
        if any(not math.isfinite(value) for value in normalized):
            raise ValueError("nonfinite occupation: ordinary gap analysis refused")
        classifications = []
        for value in normalized:
            if abs(value) <= 1e-8:
                classifications.append(False)
            elif abs(value - 1.0) <= tolerance or abs(value - 2.0) <= tolerance:
                classifications.append(True)
                full_values.add(1 if abs(value - 1.0) <= tolerance else 2)
            else:
                raise ValueError("fractional or invalid occupation: ordinary gap analysis refused")
        count = sum(classifications)
        if count == 0 or count == len(row):
            raise ValueError("occupation does not separate occupied and empty bands")
        if classifications != [True] * count + [False] * (len(row) - count):
            raise ValueError("occupied raw bands must precede empty raw bands")
        boundaries.append(count)
    if len(set(boundaries)) != 1 or len(full_values) != 1:
        raise ValueError("variable occupation boundary or full occupation")
    occupied = boundaries[0]
    if contract and contract.get("occupied_band_count") != occupied:
        raise ValueError("occupation boundary disagrees with producer evidence")
    return occupied, {"kind": "fixed_integer" if not contract else "explicit_uniform_k_weighted",
                      "scale": scale, "full_occupation": next(iter(full_values)),
                      "rounding_tolerance": tolerance, "evidence": (contract or {}).get("evidence", [])}


def _endpoints(table: BandTable, columns: list[int], energy: float, reference: float) -> list[dict]:
    return [{"raw_band_index": column, "kpoint_index": row + 1,
             "native_kpoint_index": table.native_kpoint_indices[row] if table.native_kpoint_indices else row + 1,
             "fractional_kpoint": table.fractional_kpoints[row] if table.fractional_kpoints else None,
             "x": table.x[row], "raw_energy_ev": value,
             "aligned_energy_ev": value - reference, "reference_energy_ev": reference}
            for row, energies in enumerate(table.energies) for column in columns
            if (value := energies[column - 1]) == energy]


def audit_raw_spectrum(table: BandTable, occupied: int) -> dict:
    """审计整个未排序谱，不以显示窗口代替完整谱。"""
    width = len(table.energies[0])
    if not 0 < occupied < width:
        raise ValueError("occupied band count must separate two nonempty manifolds")
    if any(len(row) != width for row in table.energies) or len(table.x) != len(table.energies):
        raise ValueError("band table shape mismatch")
    if any(not math.isfinite(x) for x in table.x) or any(b <= a for a, b in zip(table.x, table.x[1:])):
        raise ValueError("native path coordinate must be finite and strictly increasing")
    nonfinite = [{"kpoint_index": k + 1, "raw_band_index": b + 1,
                  "native_kpoint_index": table.native_kpoint_indices[k] if table.native_kpoint_indices else k + 1,
                  "source_column_one_based": 6 + 2 * b, "raw_value": str(value)}
                 for k, row in enumerate(table.energies) for b, value in enumerate(row) if not math.isfinite(value)]
    ranges = []
    for b in range(width):
        finite = [row[b] for row in table.energies if math.isfinite(row[b])]
        ranges.append({"raw_band_index": b + 1, "manifold": "occupied" if b < occupied else "empty",
                       "minimum_ev": min(finite) if finite else None, "maximum_ev": max(finite) if finite else None})
    vbm = max((value for row in table.energies for value in row[:occupied] if math.isfinite(value)), default=None)
    cbm = min((value for row in table.energies for value in row[occupied:] if math.isfinite(value)), default=None)
    gap = cbm - vbm if vbm is not None and cbm is not None and not nonfinite else None
    return {"raw_band_count": width, "kpoint_count": len(table.x), "occupied_band_count": occupied,
            "nonfinite_states": nonfinite, "band_ranges": ranges, "vbm_ev": vbm, "cbm_ev": cbm,
            "sampled_path_gap_ev": gap,
            "empty_states_below_vbm": [item for item in ranges[occupied:] if item["minimum_ev"] is not None and vbm is not None and item["minimum_ev"] <= vbm],
            "ordinary_gap_eligible": gap is not None and gap > 0}


def reorder_display_manifolds(table: BandTable, occupied_bands: list[int], empty_bands: list[int]) -> tuple[list[list[float]], list[list[int]]]:
    """冻结一基raw窗后分别逐k能量排序，并验证完整重构。"""
    selected = occupied_bands + empty_bands
    width = len(table.energies[0])
    if not occupied_bands or not empty_bands or len(set(selected)) != len(selected) or any(b < 1 or b > width for b in selected):
        raise ValueError("invalid frozen raw band window")
    rows, mapping = [], []
    for source in table.energies:
        if any(not math.isfinite(source[b - 1]) for b in selected):
            raise ValueError("nonfinite selected frontier state: figure refused")
        ordered = sorted(occupied_bands, key=lambda b: (source[b - 1], b)) + sorted(empty_bands, key=lambda b: (source[b - 1], b))
        values = [source[b - 1] for b in ordered]
        if sorted(values) != sorted(source[b - 1] for b in selected) or set(ordered) != set(selected):
            raise ValueError("display ordering changed the frozen spectrum")
        if values != [source[b - 1] for b in ordered]:
            raise ValueError("raw-index reconstruction failed")
        rows.append(values)
        mapping.append(ordered)
    return rows, mapping


def analyze_frontier(table: BandTable, occupied_count: int | None = None,
                     occupation_contract: dict | None = None, occupied_window: int = 3,
                     empty_window: int = 4, known_pathological: bool = False,
                     diagnostic_evidence: list[str] | None = None,
                     declared_export_band_count: int | None = None) -> dict:
    """全表审计与显式导出窗分离；仅有限可信导出窗允许路径gap。"""
    original = table
    width = len(table.energies[0])
    export_count = width if declared_export_band_count is None else declared_export_band_count
    if not isinstance(export_count, int) or not 1 < export_count <= width:
        raise ValueError("declared export band count exceeds the raw table or is invalid")
    if export_count != width:
        table = BandTable(table.x, [row[:export_count] for row in table.energies],
                          [row[:export_count] for row in table.occupations] if table.occupations else None,
                          table.native_kpoint_indices, table.fractional_kpoints)
    occupation_error = None
    try:
        occupied, occupation_audit = integer_occupation_boundary(table, occupation_contract)
        if occupied_count is not None and occupied != occupied_count:
            raise ValueError("occupation boundary disagrees with requested raw window")
    except ValueError as exc:
        if occupied_count is None or not diagnostic_evidence:
            raise
        occupied = occupied_count
        occupation_error = str(exc)
        occupation_audit = {"kind": "external_boundary_diagnostic_only", "evidence": diagnostic_evidence,
                            "rejection_reason": occupation_error}
    if occupied_window < 1 or empty_window < 1:
        raise ValueError("frontier window counts must be positive")
    raw = audit_raw_spectrum(original, occupied)
    export_audit = audit_raw_spectrum(table, occupied)
    rejected_tail = list(range(export_count + 1, width + 1))
    occ = list(range(max(1, occupied - occupied_window + 1), occupied + 1))
    empty = list(range(occupied + 1, min(export_count, occupied + empty_window) + 1))
    ordered, mapping = reorder_display_manifolds(table, occ, empty)
    reference = max(row[b - 1] for row in table.energies for b in occ)
    selected_cbm = min(row[b - 1] for row in table.energies for b in empty)
    aligned = [[value - reference for value in row] for row in ordered]
    selected_gap = selected_cbm - reference
    admission_occ = list(range(max(1, occupied - 4), occupied + 1))
    admission_empty = list(range(occupied + 1, min(export_count, occupied + 6) + 1))
    admission_gap = (min(row[b - 1] for row in table.energies for b in admission_empty)
                     - max(row[b - 1] for row in table.energies for b in admission_occ))
    figure_rejection = ("nonpositive frozen selected-window path gap: numerical pathology enters the near-gap window"
                        if selected_gap <= 0 or admission_gap <= 0 else None)
    limits = [-max(2.5, 0.5 * selected_gap), selected_gap + max(3.0, 0.5 * selected_gap)] if not figure_rejection else None
    viewport_cut = [{"kpoint_index": k + 1, "raw_band_index": band,
                     "aligned_energy_ev": table.energies[k][band - 1] - reference,
                     "side": "below" if table.energies[k][band - 1] - reference < limits[0] else "above"}
                    for k in range(len(table.x)) for band in occ + empty
                    if limits and not limits[0] <= table.energies[k][band - 1] - reference <= limits[1]]
    selected = set(occ + empty)
    intrusions = [{**state, "aligned_minimum_ev": state["minimum_ev"] - reference,
                  "aligned_maximum_ev": state["maximum_ev"] - reference}
                 for state in raw["band_ranges"] if state["raw_band_index"] not in selected
                 and state["minimum_ev"] is not None and limits is not None
                 and state["minimum_ev"] - reference <= limits[1]
                 and state["maximum_ev"] - reference >= limits[0]]
    reasons = []
    if occupation_error:
        reasons.append(occupation_error)
    if rejected_tail:
        reasons.append(f"raw tail bands {export_count + 1}–{width} rejected outside declared export window")
    if export_audit["nonfinite_states"]:
        reasons.append("nonfinite states in the declared export spectrum")
    if not export_audit["ordinary_gap_eligible"]:
        reasons.append("declared export spectrum has no finite positive occupation-separated gap")
    if known_pathological:
        reasons.append("known numerical pathology: no ordinary-result promotion")
    full_edge_in_window = export_audit["vbm_ev"] == reference and export_audit["cbm_ev"] == selected_cbm
    if not full_edge_in_window:
        reasons.append("frozen window does not contain the declared-export frontier")
    if figure_rejection:
        reasons.append(figure_rejection)
    status = "diagnostic" if reasons else "reported"
    gap_eligible = not occupation_error and export_audit["ordinary_gap_eligible"] and not known_pathological
    nonfinite_occupations = [{"kpoint_index": k + 1, "raw_band_index": b + 1,
                              "native_kpoint_index": original.native_kpoint_indices[k] if original.native_kpoint_indices else k + 1,
                              "source_column_one_based": 5 + 2 * b,
                              "raw_value": str(value)}
                             for k, row in enumerate(original.occupations or []) for b, value in enumerate(row)
                             if not math.isfinite(value)]
    raw_occupations = [[value if math.isfinite(value) else None for value in row]
                       for row in original.occupations] if original.occupations is not None else None
    return {"status": status, "gap_status": "reported" if gap_eligible else "rejected",
            "diagnostic_reasons": reasons, "occupation_audit": occupation_audit,
            "raw_audit": raw, "declared_export_audit": export_audit,
            "declared_export_band_count": export_count, "rejected_raw_tail_bands": rejected_tail,
            "raw_selected_occupied_bands": occ, "raw_selected_empty_bands": empty,
            "ordering": "per-k energy ranks within separately frozen occupied/empty raw windows; not character tracking; no smoothing",
            "mapping_one_based": mapping, "display_energies_ev": aligned,
            "reconstruction_verified": True, "selected_energy_multisets_unchanged": True,
            "reference": {"kind": "occupied sampled path VBM", "energy_ev": reference, "not_fermi": True},
            "y_limits_ev": limits, "unselected_intrusions": intrusions,
            "figure_status": "rejected" if figure_rejection else "renderable",
            "figure_rejection_reason": figure_rejection,
            "selected_window_path_gap_ev": selected_gap,
            "original_frontier_admission_audit": {"raw_occupied_bands": admission_occ, "raw_empty_bands": admission_empty,
                                                   "sampled_path_gap_ev": admission_gap,
                                                   "note": "Original frozen 5/6-window admission evidence remains binding; reducing displayed bands to 3/4 never repairs or hides known negative-gap pathology."},
            "viewport": {"kind": "method-own near-gap viewport", "formula": "lower=-max(2.5,0.5*selectedgap); upper=selectedgap+max(3,0.5*selectedgap)",
                         "selected_raw_window_frozen_before_sorting": True,
                         "cut_states": viewport_cut,
                         "note": "Viewport clips only drawing; complete frozen energies, raw mappings, full spectrum audit and path gaps are unchanged; no adaptive expansion or energy repair."},
            "sampled_path_gap_ev": export_audit["sampled_path_gap_ev"] if gap_eligible else None,
            "gap_definition": "declared finite export window path gap",
            "diagnostic_selected_window_gap_ev": selected_cbm - reference if status == "diagnostic" else None,
            "edge_scope": "declared finite export spectrum" if full_edge_in_window else "frozen low-energy raw window only",
            "vbm_endpoints": _endpoints(table, occ, reference, reference),
            "cbm_endpoints": _endpoints(table, empty, selected_cbm, reference),
            "native_x": table.x, "native_kpoint_indices": table.native_kpoint_indices,
            "fractional_kpoints": table.fractional_kpoints, "raw_occupations": raw_occupations,
            "nonfinite_raw_occupations": nonfinite_occupations,
            "nonfinite_encoding": "JSON null; original raw value and source column retained in location metadata; source bytes unchanged",
            "x_axis": "native k-point index" if table.native_kpoint_indices else "native path coordinate (source units)"}


METHOD_STYLE = {"KS": ("#00A6B4", "9 5"), "EXX": ("#222222", "11 4 2 4"), "GW": ("#E64B35", "")}


def render_frontier_svg(table: BandTable, analysis: dict, labels: list[dict], title: str, method: str) -> str:
    """可复用的单方法白底矢量图；点位来自未经排序的raw边缘。"""
    if analysis.get("figure_status") == "rejected":
        raise ValueError(analysis["figure_rejection_reason"])
    color, dash = METHOD_STYLE[method]
    width, height = 1080, 740
    left, right, top, bottom = 105, 1045, 88, 636
    lower, upper = analysis["y_limits_ev"]
    xlow, xhigh = table.x[0], table.x[-1]
    if xhigh <= xlow:
        xhigh = xlow + 1
    xmap = lambda x: left + (x - xlow) / (xhigh - xlow) * (right - left)
    ymap = lambda e: top + (upper - e) / (upper - lower) * (bottom - top)
    font = 'font-family="Times New Roman, DejaVu Serif, serif"'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{left}" y="42" {font} font-size="29" font-weight="bold">{html.escape(title)} | {method}</text>',
             f'<defs><clipPath id="frontier-clip"><rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}"/></clipPath></defs>']
    if analysis["status"] == "diagnostic":
        tail = analysis.get("rejected_raw_tail_bands", [])
        warning = (f"Export-window path diagnostic — raw tail {tail[0]}–{tail[-1]} rejected"
                   if tail else "Low-energy path diagnostic — not an accepted full-spectrum gap")
        parts.append(f'<text id="diagnostic-warning" x="{left}" y="68" {font} font-size="18" fill="#755328">{warning}</text>')
    else:
        parts.append(f'<text x="{left}" y="68" {font} font-size="17" fill="#555555">Frozen occupation-separated energy-rank display</text>')
    step_target = (upper - lower) / 6
    power = 10 ** math.floor(math.log10(step_target))
    step = next(s * power for s in (1, 2, 2.5, 5, 10) if s * power >= step_target)
    first = math.ceil(lower / step)
    last = math.floor(upper / step)
    for i in range(first * 2, last * 2 + 1):
        value = i * step / 2
        y = ymap(value)
        major = i % 2 == 0
        if major:
            parts.append(f'<line x1="{left}" y1="{y:.3f}" x2="{right}" y2="{y:.3f}" stroke="#dddddd" stroke-width="1"/>')
            parts.append(f'<text x="{left-13}" y="{y+7:.3f}" text-anchor="end" {font} font-size="21">{value:g}</text>')
        length = 8 if major else 4
        for origin, end in ((left, left + length), (right, right - length)):
            parts.append(f'<line x1="{origin}" y1="{y:.3f}" x2="{end}" y2="{y:.3f}" stroke="black" stroke-width="1.8"/>')
    for tick in labels:
        x = xmap(tick["x"])
        parts.append(f'<line x1="{x:.3f}" y1="{top}" x2="{x:.3f}" y2="{bottom}" stroke="#aaaaaa" stroke-width="1.4"/>')
        parts.append(f'<text x="{x:.3f}" y="{bottom+29}" text-anchor="middle" {font} font-size="24">{html.escape(tick["label"])}</text>')
        for y, end in ((top, top + 8), (bottom, bottom - 8)):
            parts.append(f'<line x1="{x:.3f}" y1="{y}" x2="{x:.3f}" y2="{end}" stroke="black" stroke-width="1.8"/>')
    parts.append(f'<line x1="{left}" y1="{ymap(0):.3f}" x2="{right}" y2="{ymap(0):.3f}" stroke="#888888" stroke-width="1.2"/>')
    for rank, column in enumerate(zip(*analysis["display_energies_ev"]), 1):
        points = " ".join(f'{"M" if k == 0 else "L"}{xmap(table.x[k]):.3f},{ymap(value):.3f}' for k, value in enumerate(column))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<path id="{method}-rank-{rank}" d="{points}" fill="none" stroke="{color}" stroke-width="2.5"{dash_attr} clip-path="url(#frontier-clip)"/>')
    for edge, shape in (("vbm", "circle"), ("cbm", "square")):
        seen = set()
        for number, point in enumerate(analysis[f"{edge}_endpoints"]):
            pair = (point["x"], point["aligned_energy_ev"])
            if pair in seen:
                continue
            seen.add(pair)
            x, y = xmap(pair[0]), ymap(pair[1])
            ident = f'{method}-{edge.upper()}-{number+1}'
            if shape == "circle":
                parts.append(f'<circle id="{ident}" cx="{x:.3f}" cy="{y:.3f}" r="7" fill="none" stroke="{color}" stroke-width="2.5"/>')
            else:
                parts.append(f'<rect id="{ident}" x="{x-6.5:.3f}" y="{y-6.5:.3f}" width="13" height="13" fill="none" stroke="{color}" stroke-width="2.5"/>')
    parts.extend([f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="none" stroke="black" stroke-width="2.5"/>',
                  f'<text x="{(left+right)/2}" y="{bottom+64}" text-anchor="middle" {font} font-size="24">{html.escape(analysis["x_axis"])}</text>',
                  f'<text x="31" y="{(top+bottom)/2}" text-anchor="middle" transform="rotate(-90 31 {(top+bottom)/2})" {font} font-size="25">E − E<tspan baseline-shift="sub" font-size="18">VBM</tspan> (eV)</text>',
                  f'<rect x="{right-190}" y="{top+13}" width="177" height="72" fill="white" stroke="black" stroke-width="1.7"/>',
                  f'<line x1="{right-178}" y1="{top+34}" x2="{right-116}" y2="{top+34}" stroke="{color}" stroke-width="2.5"' + (f' stroke-dasharray="{dash}"' if dash else "") + '/>',
                  f'<text x="{right-102}" y="{top+41}" {font} font-size="23">{method}</text>',
                  f'<circle cx="{right-173}" cy="{top+64}" r="5" fill="none" stroke="{color}" stroke-width="2"/>',
                  f'<text x="{right-161}" y="{top+70}" {font} font-size="16">VBM</text>',
                  f'<rect x="{right-99}" y="{top+59}" width="10" height="10" fill="none" stroke="{color}" stroke-width="2"/>',
                  f'<text x="{right-82}" y="{top+70}" {font} font-size="16">CBM</text>', '</svg>'])
    return "\n".join(parts) + "\n"


def write_sidecar(output: Path, calculation_id: str, input_sha256: str, table_path: Path, labels: Iterable[dict] | None = None) -> dict:
    metadata = {"schema_version": 1, "calculation_id": calculation_id, "input_sha256": input_sha256,
                "table_sha256": _sha256(table_path), "table_path": table_path.name, "labels": list(labels or [])}
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metadata


def render(table: BandTable, output: Path, labels: list[dict], title: str | None = None) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("rendering requires matplotlib; parsing and provenance do not") from exc
    with plt.rc_context({"font.family": "serif", "axes.labelsize": 12, "axes.titlesize": 14, "axes.titleweight": "bold", "axes.linewidth": 1.5}):
        fig, axis = plt.subplots(figsize=(7.2, 4.4), constrained_layout=True)
        for column in zip(*table.energies):
            axis.plot(table.x, column, color="#00A6B4", linewidth=1.5)
        if labels:
            axis.set_xticks([item["x"] for item in labels], [item["label"] for item in labels])
            for item in labels:
                axis.axvline(item["x"], color="#bbbbbb", linewidth=0.7, zorder=0)
        axis.set_xlabel("native path coordinate (source units)")
        axis.set_ylabel("Energy (eV), raw reference")
        axis.tick_params(direction="in", top=True, right=True)
        if title:
            axis.set_title(title)
        fig.savefig(output, dpi=240)
        plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calculation-id", required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--format", choices=("generic", "abacus"), default="generic")
    parser.add_argument("--method", choices=tuple(METHOD_STYLE), default="GW")
    args = parser.parse_args()
    table = parse_abacus_band_table(args.table) if args.format == "abacus" else parse_band_table(args.table)
    labels = _read_ticks(args.labels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "abacus":
        if args.output.suffix.lower() != ".svg":
            parser.error("ABACUS frontier output must be .svg; generic PNG/PDF rendering is separate")
        analysis = analyze_frontier(table)
        args.output.write_text(render_frontier_svg(table, analysis, labels, args.title or args.calculation_id, args.method), encoding="utf-8")
        metadata = write_sidecar(args.output, args.calculation_id, args.input_sha256, args.table, labels)
        metadata["analysis"] = analysis
        args.output.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    else:
        render(table, args.output, labels, args.title)
        write_sidecar(args.output, args.calculation_id, args.input_sha256, args.table, labels)
    print(f"band figure written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
