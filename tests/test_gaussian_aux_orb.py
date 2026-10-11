#!/usr/bin/env python3
"""Smoke test the optional auxiliary-only Gaussian orbital helper."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "generate_gaussian_aux_orb.py"


def make_orbital() -> str:
    lines = [
        "---------------------------------------------------------------------------",
        "Element                     X",
        "Energy Cutoff(Ry)           100",
        "Radius Cutoff(a.u.)         10",
        "Lmax                        2",
        "Number of Sorbital-->       1",
        "Number of Porbital-->       1",
        "Number of Dorbital-->       1",
        "---------------------------------------------------------------------------",
        "SUMMARY  END",
        "",
        "Mesh                        101",
        "dr                          0.1",
    ]
    for angular_momentum in range(3):
        lines.extend(
            [
                "                Type               L               N",
                f"                   0               {angular_momentum}               0",
            ]
        )
        for index in range(101):
            radius = index * 0.1
            value = (radius**angular_momentum) * math.exp(-radius)
            lines.append(f"   {value:.14e}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        source = root / "base.orb"
        output = root / "base-for-aux.orb"
        source.write_text(make_orbital(), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(HELPER), "--input", str(source), "--output", str(output)],
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(result.stdout)
        text = output.read_text(encoding="utf-8")
        assert report["added_channels"] == ["f", "g"]
        assert "Number of Forbital-->       1" in text
        assert "Number of Gorbital-->       1" in text
        assert "Lmax                        4" in text

        f_only = root / "base-for-aux-f-only.orb"
        result = subprocess.run(
            [
                sys.executable,
                str(HELPER),
                "--input",
                str(source),
                "--output",
                str(f_only),
                "--add-channels",
                "f",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        f_only_text = f_only.read_text(encoding="utf-8")
        assert "Number of Forbital-->       1" in f_only_text
        assert "Number of Gorbital-->" not in f_only_text
        assert "Lmax                        3" in f_only_text
    return 0


if __name__ == "__main__":
    sys.exit(main())
