#!/usr/bin/env python3
"""Plot an exciton density slice written by ABACUS or by a reconstruction tool.

Both producers emit the same text format: a `# ABACUS_EXCITON_SLICE 1` header of
`# key value...` lines, then `nu` rows of `nv` whitespace-separated numbers.

Nothing here re-derives the density. The values are plotted exactly as archived,
so any disagreement with the underlying calculation is visible in the figure
rather than hidden by this script.

The same tool ships with the `oh-my-librpa` skill, where it is used next to the
density reconstruction; this copy lives here because the archived exciton
figures of a calculation record are generated with it, the way `plot_bands.py`
generates the band figures.

Usage:
    plot_exciton_slice.py gm.dat other.dat --labels C --out exciton.svg
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

BOHR_ANGSTROM = 0.529177210903


def _sha256(path: pathlib.Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_slice(path: pathlib.Path) -> dict:
    """Read the header and the nu x nv block; refuse anything ambiguous."""
    if not path.is_file():
        raise ValueError(f"slice file is missing: {path}")
    header: dict[str, str] = {}
    rows: list[list[float]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line[1:].strip()
            key, _, value = body.partition(" ")
            header[key.strip()] = value.strip()
            continue
        try:
            rows.append([float(value) for value in line.split()])
        except ValueError as exc:
            raise ValueError(f"{path}:{number}: non-numeric density value") from exc
    if not rows:
        raise ValueError(f"{path}: no density block")
    widths = {len(row) for row in rows}
    if len(widths) != 1:
        raise ValueError(f"{path}: ragged rows {sorted(widths)}")
    nu, nv = len(rows), widths.pop()
    grid = header.get("grid", "")
    if grid:
        fields = grid.split()
        if len(fields) >= 2 and (int(fields[0]), int(fields[1])) != (nu, nv):
            raise ValueError(f"{path}: header grid {fields[0]}x{fields[1]} disagrees with the {nu}x{nv} block")
    meta = {"nu": nu, "nv": nv, "header": header, "sha256": _sha256(path), "path": str(path)}
    for name in ("u_range", "v_range"):
        text = header.get("grid", "")
        if name in text:
            tail = text.split(name)[1].split()
            if len(tail) >= 2:
                meta[name] = (float(tail[0]), float(tail[1]))
    if "fixed_particle" in header:
        meta["fixed_particle"] = header["fixed_particle"]
    state_text = header.get("state", "")
    if "density_kind" in state_text:
        meta["density_kind"] = state_text.split("density_kind")[1].split()[0]
    dense = None
    return {"dense": dense, "rows": rows, "meta": meta}


MAX_CELLS = 160


def pinned_markers(meta: dict) -> list[tuple[float, float]]:
    """Periodic images of the pinned particle inside the plotted window.

    The header records `fixed_particle <kind> position_bohr x y z`. For an `ab`
    slice the in-plane coordinates are the a and b fractional components.

    The repeat period comes from the number of k points that entered the
    coherent sum, recorded as `kpoints`, not from `bvk`: `bvk` is the coarse mesh
    a dual-grid header inherits, while the coherent sum runs over the dense one.
    Falls back to `bvk` only when `kpoints` is absent, and returns an empty list
    whenever the header cannot justify a marker at all.
    """
    text = meta.get("fixed_particle")
    header = meta.get("header", {})
    if not text or "position_bohr" not in text:
        return []
    period_text = header.get("kpoints") or header.get("bvk")
    urange, vrange = meta.get("u_range"), meta.get("v_range")
    if not period_text or not urange or not vrange:
        return []
    try:
        xyz = [float(value) for value in text.split("position_bohr")[1].split()[:3]]
        basis = [[float(value) for value in header[name].split()[:3]] for name in ("a", "b", "c")]
        period = [int(value) for value in period_text.split()[:3]]
    except (KeyError, ValueError, IndexError):
        return []
    frac = _solve3(basis, xyz)
    if frac is None:
        return []
    axis = {"ab": (0, 1), "bc": (1, 2), "ca": (2, 0)}
    plane = header.get("plane", "").split(" ")[0]
    if plane not in axis:
        return []
    u_axis, v_axis = axis[plane]
    span_u, span_v = period[u_axis], period[v_axis]
    if span_u <= 0 or span_v <= 0:
        return []
    points = []
    for u_shift in range(-8, 9):
        for v_shift in range(-8, 9):
            u = frac[u_axis] + u_shift * span_u
            v = frac[v_axis] + v_shift * span_v
            if urange[0] <= u <= urange[1] and vrange[0] <= v <= vrange[1]:
                points.append((u, v))
    return points


def _solve3(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Solve a 3x3 system by Gauss-Jordan elimination, or None if singular."""
    work = [[float(value) for value in row] + [float(rhs[index])] for index, row in enumerate(matrix)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(work[row][col]))
        if abs(work[pivot][col]) < 1e-12:
            return None
        work[col], work[pivot] = work[pivot], work[col]
        scale = work[col][col]
        work[col] = [value / scale for value in work[col]]
        for row in range(3):
            if row == col:
                continue
            factor = work[row][col]
            work[row] = [a - factor * b for a, b in zip(work[row], work[col])]
    return [work[row][3] for row in range(3)]


def downsample(rows: list[list[float]], limit: int = MAX_CELLS) -> tuple[list[list[float]], int]:
    """Block-average to at most `limit` cells per side so the SVG stays portable.

    A native 225x225 slice would need 50k rectangles per panel. Returns the
    reduced grid and the integer factor used, so the audit can state exactly how
    much was averaged rather than implying the figure is native resolution.
    """
    nu, nv = len(rows), len(rows[0])
    factor = max(1, math.ceil(max(nu, nv) / limit))
    if factor == 1:
        return rows, 1
    reduced = []
    for block_u in range(0, nu, factor):
        band = []
        for block_v in range(0, nv, factor):
            values = [rows[u][v]
                      for u in range(block_u, min(block_u + factor, nu))
                      for v in range(block_v, min(block_v + factor, nv))]
            band.append(sum(values) / len(values))
        reduced.append(band)
    return reduced, factor


def render(payloads: list[dict], labels: list[str], title: str, output: pathlib.Path,
           width: int = 1080, height: int = 780, show_pins: bool = True) -> str:
    """Draw one panel per slice as an SVG grid, keeping the archived values."""
    panels = len(payloads)
    title_height = 96
    panel_w = (width - 24) / panels
    panel_h = height - title_height - 96
    # Shrink the title rather than let it run off the canvas: a long case label is
    # normal, a clipped title is not.
    title_size = 26.0
    while title_size > 15.0 and len(title) * title_size * 0.52 > width - 48:
        title_size -= 1.0
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="24" y="42" font-family="Times New Roman, DejaVu Serif, serif" font-size="{title_size:g}" font-weight="bold">{_escape(title)}</text>']
    for index, (payload, label) in enumerate(zip(payloads, labels)):
        meta = payload["meta"]
        rows, factor = downsample(payload["rows"])
        nu, nv = len(rows), len(rows[0])
        flat = [value for row in rows for value in row]
        finite = [value for value in flat if math.isfinite(value)]
        low, high = min(finite), max(finite)
        origin_x = 12 + index * panel_w
        origin_y = title_height
        parts.append(f'<text x="{origin_x + 8:.2f}" y="{origin_y - 12}" font-family="Times New Roman, DejaVu Serif, serif" font-size="18">{_escape(label)}</text>')
        cell_w = panel_w / nv
        cell_h = panel_h / nu
        for row in range(nu):
            for column in range(nv):
                value = rows[row][column]
                share = 0.0 if high <= low else (value - low) / (high - low)
                parts.append(
                    f'<rect x="{origin_x + column * cell_w:.3f}" y="{origin_y + panel_h - (row + 1) * cell_h:.3f}" '
                    f'width="{cell_w + 0.35:.3f}" height="{cell_h + 0.35:.3f}" fill="{_heat(share)}"/>')
        parts.append(f'<rect x="{origin_x:.2f}" y="{origin_y:.2f}" width="{panel_w:.2f}" height="{panel_h:.2f}" fill="none" stroke="black" stroke-width="1.4"/>')
        def fitted_size(text: str, preferred: float, limit: float) -> float:
            """Largest size at or below `preferred` that keeps text inside `limit`."""
            size = preferred
            while size > 8.0 and len(text) * size * 0.52 > limit:
                size -= 0.5
            return size

        urange = meta.get("u_range")
        vrange = meta.get("v_range")
        axis_note = (f'u ∈ [{urange[0]:g}, {urange[1]:g}], v ∈ [{vrange[0]:g}, {vrange[1]:g}] (primitive cells)'
                     if urange and vrange else "primitive-cell units")
        parts.append(f'<text x="{origin_x + panel_w / 2:.2f}" y="{origin_y + panel_h + 30}" text-anchor="middle" '
                     f'font-family="Times New Roman, DejaVu Serif, serif" '
                     f'font-size="{fitted_size(axis_note, 16.0, panel_w - 8):g}">{_escape(axis_note)}</text>')
        markers = pinned_markers(meta) if show_pins else []
        note = meta.get("fixed_particle")
        if note:
            parts.append(f'<text x="{origin_x + panel_w / 2:.2f}" y="{origin_y + panel_h + 54}" text-anchor="middle" '
                         f'font-family="Times New Roman, DejaVu Serif, serif" '
                         f'font-size="{fitted_size(note, 14.0, panel_w - 8):g}" fill="#555555">{_escape(note)}</text>')
        parts.append(f'<text x="{origin_x + panel_w / 2:.2f}" y="{origin_y + panel_h + 76}" text-anchor="middle" '
                     f'font-family="Times New Roman, DejaVu Serif, serif" font-size="14" fill="#555555">'
                     f'min {low:.3e}  max {high:.3e}</text>')
        if markers:
            urange = meta.get("u_range")
            vrange = meta.get("v_range")
            to_x = lambda u: origin_x + (u - urange[0]) / (urange[1] - urange[0]) * panel_w
            to_y = lambda v: origin_y + panel_h - (v - vrange[0]) / (vrange[1] - vrange[0]) * panel_h
            for u, v in markers:
                parts.append(f'<circle cx="{to_x(u):.2f}" cy="{to_y(v):.2f}" r="7" '
                             f'fill="none" stroke="white" stroke-width="2"/>')
                parts.append(f'<path d="M{to_x(u) - 4:.2f},{to_y(v):.2f} h8 M{to_x(u):.2f},{to_y(v) - 4:.2f} v8" '
                             f'stroke="white" stroke-width="1.6"/>')
    parts.append('</svg>')
    svg = "\n".join(parts)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    return svg


def _escape(value: object) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _heat(share: float) -> str:
    """Inferno-like ramp: dark purple to yellow, monotone in the value."""
    stops = [(0.0, (0, 0, 4)), (0.25, (87, 16, 110)), (0.5, (188, 55, 84)),
             (0.75, (249, 142, 9)), (1.0, (252, 255, 164))]
    share = min(max(share, 0.0), 1.0)
    for index in range(len(stops) - 1):
        left, lrgb = stops[index]
        right, rrgb = stops[index + 1]
        if left <= share <= right:
            weight = (share - left) / (right - left)
            rgb = tuple(round(lrgb[i] + weight * (rrgb[i] - lrgb[i])) for i in range(3))
            return "#{:02x}{:02x}{:02x}".format(*rgb)
    return "#fcf ffa4".replace(" ", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slices", nargs="+", type=pathlib.Path)
    parser.add_argument("--labels", nargs="+", default=None,
                        help="one panel label per slice; defaults to the file names")
    parser.add_argument("--title", default="Exciton density slice")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--audit", type=pathlib.Path, default=None,
                        help="write the parsed header, SHA-256, value range and display "
                             "downsampling as JSON")
    parser.add_argument("--pinned-marker", choices=("none", "circle"), default="circle",
                        help="mark the pinned particle's periodic images when the header "
                             "records fixed_particle")
    args = parser.parse_args()
    labels = args.labels or [path.name for path in args.slices]
    if len(labels) != len(args.slices):
        parser.error("--labels must match the number of slices")
    payloads = [parse_slice(path) for path in args.slices]
    render(payloads, labels, args.title, args.output,
           show_pins=args.pinned_marker == "circle")
    if args.audit:
        audit = [{"label": label, **payload["meta"],
                  "value_min": min(min(row) for row in payload["rows"]),
                  "value_max": max(max(row) for row in payload["rows"]),
                  "display_cells": len(downsample(payload["rows"])[0]),
                  "display_block_average": downsample(payload["rows"])[1],
                  "display_note": ("native resolution" if downsample(payload["rows"])[1] == 1 else
                                   "block-averaged for display; the archived values are unchanged")}
                 for label, payload in zip(labels, payloads)]
        args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
