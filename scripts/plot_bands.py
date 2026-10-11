#!/usr/bin/env python3
"""Plot a portable x-plus-energy-column band table with provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


class BandTable:
    def __init__(self, x: list[float], energies: list[list[float]]) -> None:
        self.x = x
        self.energies = energies


def parse_band_table(path: Path) -> BandTable:
    """Read ``x energy_1 energy_2 ...`` rows and retain column order."""
    x_values: list[float] = []
    rows: list[list[float]] = []
    width: int | None = None
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        try:
            values = [float(item) for item in fields]
        except ValueError as exc:
            raise ValueError(f"line {line_number}: expected numeric columns") from exc
        if len(values) < 2:
            raise ValueError(f"line {line_number}: expected x and at least one energy")
        row_width = len(values) - 1
        if width is None:
            width = row_width
        elif row_width != width:
            raise ValueError("all data rows must have the same number of energy columns")
        x_values.append(values[0])
        rows.append(values[1:])
    if not rows:
        raise ValueError("band table contains no data rows")
    return BandTable(x_values, rows)


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


def write_sidecar(output: Path, calculation_id: str, input_sha256: str, table_path: Path, labels: Iterable[dict] | None = None) -> dict:
    metadata = {
        "schema_version": 1,
        "calculation_id": calculation_id,
        "input_sha256": input_sha256,
        "table_sha256": _sha256(table_path),
        "table_path": table_path.name,
        "labels": list(labels or []),
    }
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metadata


def render(table: BandTable, output: Path, labels: list[dict], title: str | None = None) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("rendering requires matplotlib; parsing and provenance do not") from exc
    fig, axis = plt.subplots(figsize=(7.2, 4.4), constrained_layout=True)
    xs = table.x
    for column in range(len(table.energies[0])):
        axis.plot(xs, [row[column] for row in table.energies], color="#176b87", linewidth=0.9)
    axis.axhline(0.0, color="#59676d", linewidth=0.6, linestyle="--")
    if labels:
        axis.set_xticks([item["x"] for item in labels], [item["label"] for item in labels])
        for item in labels:
            axis.axvline(item["x"], color="#d7dfe1", linewidth=0.6, zorder=0)
    axis.set_xlabel("k-path")
    axis.set_ylabel("Energy (eV)")
    if title:
        axis.set_title(title)
    axis.grid(axis="y", color="#e7ecec", linewidth=0.5)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table", type=Path, help="plain-text x plus energy columns")
    parser.add_argument("--output", type=Path, required=True, help="PNG/PDF output path")
    parser.add_argument("--calculation-id", required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--title")
    args = parser.parse_args()
    table = parse_band_table(args.table)
    labels = _read_ticks(args.labels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    render(table, args.output, labels, args.title)
    write_sidecar(args.output, args.calculation_id, args.input_sha256, args.table, labels)
    print(f"band figure written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
