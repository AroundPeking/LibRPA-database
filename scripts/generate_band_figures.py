#!/usr/bin/env python3
"""Generate material-detail SVG band figures from archived ABACUS band tables.

The input tables are kept unchanged.  The generated SVG and its JSON sidecar
are derived artifacts, so every record stores the source result paths and
hashes alongside the figure hash.
"""

from __future__ import annotations

import argparse
import html
import hashlib
import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLOT_SCRIPT = ROOT / "scripts/plot_bands.py"
SPEC = importlib.util.spec_from_file_location("plot_bands", PLOT_SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import guard
    raise RuntimeError("cannot load plot_bands.py")
plot_bands = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plot_bands)


METHODS = (
    ("KS", "KS_band_spin_1.dat", "#496ca8"),
    ("EXX", "EXX_band_spin_1.dat", "#c4773c"),
    ("GW", "GW_band_spin_1.dat", "#16818a"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _kpoint_labels(kpt: Path, count: int) -> list[dict]:
    """Extract high-symmetry labels and their row positions from a KPT file."""
    labels: list[dict] = []
    pending = 0
    for raw in kpt.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower() in {"line", "k_points"} or line.isdigit():
            continue
        match = re.search(r"#\s*(\S+)\s*$", line)
        fields = line.split("#", 1)[0].split()
        if len(fields) < 4:
            continue
        try:
            segment_points = int(float(fields[3]))
        except ValueError:
            continue
        label = match.group(1) if match else ""
        if not labels:
            labels.append({"x": 0.0, "label": label or "k0"})
        elif label:
            labels.append({"x": float(min(pending, count - 1)), "label": label})
        pending += segment_points
    if labels:
        labels[-1]["x"] = float(count - 1)
    return labels


def _plot_bundle(output: Path, title: str, tables: dict[str, object], ticks: list[dict], gap: float | None) -> dict:
    upper = max(8.0, min(20.0, (gap or 0.0) + 3.0))
    lower = -6.0
    width, height = 1200, 500
    left, top, panel_width, panel_height, gap_width = 68, 72, 350, 350, 25
    x_max = max(1.0, len(next(iter(tables.values())).x) - 1)
    y_map = lambda value: top + (upper - value) / (upper - lower) * panel_height
    x_map = lambda value, origin: origin + value / x_max * panel_width
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="34" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#1c3441">{html.escape(title)}</text>',
        '<text x="1120" y="34" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#64747c">ABACUS band tables</text>',
        '<defs>',
    ]
    for index in range(3):
        origin = left + index * (panel_width + gap_width)
        parts.append(f'<clipPath id="panel-{index}"><rect x="{origin}" y="{top}" width="{panel_width}" height="{panel_height}"/></clipPath>')
    parts.append('</defs>')
    for index, (method, _filename, color) in enumerate(METHODS):
        origin = left + index * (panel_width + gap_width)
        right = origin + panel_width
        bottom = top + panel_height
        parts.append(f'<text x="{origin}" y="58" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="{color}">{method}</text>')
        for value in (lower, 0, upper):
            y = y_map(value)
            stroke = "#b9c5ca" if value == 0 else "#edf1f2"
            dash = ' stroke-dasharray="4 4"' if value == 0 else ""
            parts.append(f'<line x1="{origin}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="{stroke}" stroke-width="1"{dash}/>')
        for tick in ticks:
            x = x_map(float(tick["x"]), origin)
            parts.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{bottom}" stroke="#dfe7e9" stroke-width="1"/>')
            parts.append(f'<text x="{x:.2f}" y="{bottom + 24}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#556770">{html.escape(str(tick["label"]))}</text>')
        table = tables[method]
        columns = zip(*table.energies)
        for energies in columns:
            if not any(lower - 2.0 <= value <= upper + 2.0 for value in energies):
                continue
            points = " ".join(f"{('M' if idx == 0 else 'L')}{x_map(table.x[idx], origin):.2f},{y_map(value):.2f}" for idx, value in enumerate(energies))
            parts.append(f'<path d="{points}" fill="none" stroke="{color}" stroke-width="1.05" opacity="0.82" clip-path="url(#panel-{index})"/>')
        parts.append(f'<line x1="{origin}" y1="{top}" x2="{origin}" y2="{bottom}" stroke="#8b9aa0" stroke-width="1"/>')
        parts.append(f'<line x1="{origin}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#8b9aa0" stroke-width="1"/>')
        parts.append(f'<text x="{origin + panel_width / 2:.2f}" y="{bottom + 46}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#64747c">k-path</text>')
        if index == 0:
            for value in (lower, 0, upper):
                parts.append(f'<text x="{origin - 10}" y="{y_map(value) + 4:.2f}" text-anchor="end" font-family="Arial, sans-serif" font-size="11" fill="#64747c">{value:g}</text>')
            parts.append(f'<text x="{origin - 48}" y="{top + panel_height / 2:.2f}" transform="rotate(-90 {origin - 48},{top + panel_height / 2:.2f})" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#4e616a">Energy (eV)</text>')
    parts.append('</svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return {"y_limits": [lower, upper], "ticks": ticks}


def _file_entry(path: Path, label: str, transformation: str, source_paths: list[str] | None = None) -> dict:
    digest = sha256(path)
    entry = {
        "role": "figures",
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "size_bytes": path.stat().st_size,
        "original_sha256": digest,
        "label": label,
        "transformation": transformation,
    }
    if source_paths:
        entry["source_paths"] = source_paths
    return entry


def generate_record(record_path: Path) -> bool:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("dimension") != "3d":
        return False
    result_dir = ROOT.joinpath(*record["files"]["results"][0]["path"].split("/")[:-1])
    tables = {}
    source_paths = []
    for method, filename, _color in METHODS:
        path = result_dir / filename
        if not path.is_file():
            return False
        tables[method] = plot_bands.parse_abacus_band_table(path)
        source_paths.append(path.relative_to(ROOT).as_posix())
    ticks = _kpoint_labels(result_dir.parent / "inputs" / "KPT", len(tables["KS"].x))
    gap = record.get("summary", {}).get("gw_gap_ev")
    output = result_dir.parent / "figures" / "band_comparison.svg"
    metadata = _plot_bundle(output, f'{record.get("material", record["id"])} · KS / EXX / GW', tables, ticks, gap)
    sidecar = output.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calculation_id": record["id"],
                "source_result_paths": source_paths,
                "source_sha256": {path: sha256(ROOT / path) for path in source_paths},
                "plot": metadata,
                "note": "Derived from archived ABACUS band tables; source tables are unchanged.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    record["files"]["figures"] = [
        _file_entry(output, "KS / EXX / GW band comparison", "generated from archived ABACUS band tables", source_paths),
        _file_entry(sidecar, "Band figure provenance", "generated alongside the band comparison figure", source_paths),
    ]
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    count = 0
    for record_path in sorted(args.root.glob("data/calculations/3d/*/*/record.json")):
        count += int(generate_record(record_path))
    print(f"generated band figures for {count} 3D records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
