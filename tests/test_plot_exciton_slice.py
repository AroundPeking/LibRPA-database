"""Contract tests for the standard-library exciton slice plotter."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("plot_exciton_slice", ROOT / "scripts/plot_exciton_slice.py")
plot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plot)

SLICE = """# ABACUS_EXCITON_SLICE 1
# state 0 energy_Ry 0 density_kind conditional_elec
# fixed_particle hole position_bohr {px} {px} {px}
# plane ab slice_pos_bohr {pos}
# grid {n} {n} u_range -2 2 v_range -2 2
# bvk 4 4 4
# kpoints 8 8 8
# lattice_bohr
# a 0.0 5.15097211413 5.15097211413
# b 5.15097211413 0.0 5.15097211413
# c 5.15097211413 5.15097211413 0.0
"""


def slice_text(n: int = 8, px: float = 2.575486057064714, pos: float = 1.8211) -> str:
    header = SLICE.format(n=n, px=px, pos=pos)
    body = "\n".join(" ".join("1.0" if (r + c) % 3 else "4.0" for c in range(n)) for r in range(n))
    return header + body + "\n"


class SliceTests(unittest.TestCase):
    def write(self, text: str) -> pathlib.Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".dat", delete=False)
        handle.write(text)
        handle.close()
        return pathlib.Path(handle.name)

    def test_header_and_block_are_parsed(self) -> None:
        payload = plot.parse_slice(self.write(slice_text()))
        self.assertEqual(payload["meta"]["nu"], 8)
        self.assertEqual(payload["meta"]["nv"], 8)
        self.assertEqual(payload["meta"]["u_range"], (-2.0, 2.0))
        self.assertIn("conditional_elec", payload["meta"]["density_kind"])

    def test_ragged_block_is_rejected(self) -> None:
        path = self.write(slice_text() + "1.0 2.0\n")
        with self.assertRaises(ValueError):
            plot.parse_slice(path)

    def test_header_grid_must_match_the_block(self) -> None:
        path = self.write(slice_text().replace("# grid 8 8", "# grid 9 9"))
        with self.assertRaises(ValueError):
            plot.parse_slice(path)

    def test_pin_period_comes_from_kpoints_not_bvk(self) -> None:
        payload = plot.parse_slice(self.write(slice_text()))
        points = plot.pinned_markers(payload["meta"])
        self.assertEqual(len(points), 1)
        u, v = points[0]
        self.assertAlmostEqual(u, 0.25, places=4)
        self.assertAlmostEqual(v, 0.25, places=4)

    def test_wide_window_shows_the_full_period_set(self) -> None:
        # period comes from kpoints = 8, so a -10..10 window holds the pin at
        # 0.25 plus images at 0.25 +/- 8 in each direction: 3 x 3 = 9 points.
        text = slice_text(n=8).replace("u_range -2 2 v_range -2 2", "u_range -10 10 v_range -10 10")
        payload = plot.parse_slice(self.write(text))
        points = plot.pinned_markers(payload["meta"])
        self.assertEqual(len(points), 9)
        for u, v in points:
            self.assertTrue(-10 <= u <= 10 and -10 <= v <= 10)
        # Adjacent images are one period apart; the set also contains 2x and 3x,
        # so the smallest nonzero spacing is the period itself.
        spacings = sorted({round(abs(a[0] - b[0]), 6) for a in points for b in points if abs(a[0] - b[0]) > 1})
        self.assertTrue(spacings)
        self.assertAlmostEqual(spacings[0], 8.0, places=3)

    def test_marker_absent_without_fixed_particle(self) -> None:
        text = "\n".join(line for line in slice_text().splitlines() if "fixed_particle" not in line) + "\n"
        payload = plot.parse_slice(self.write(text))
        self.assertEqual(plot.pinned_markers(payload["meta"]), [])

    def test_downsample_averages_within_the_original_range(self) -> None:
        # Block averaging must stay inside the original value range and must move
        # the extremes inward rather than inventing values outside them.
        rows = [[float(r + c) for c in range(9)] for r in range(9)]
        reduced, factor = plot.downsample(rows, limit=3)
        self.assertEqual(factor, 3)
        self.assertEqual(len(reduced), 3)
        low = min(min(row) for row in reduced)
        high = max(max(row) for row in reduced)
        self.assertGreater(low, 0.0)
        self.assertLess(high, 16.0)
        self.assertGreaterEqual(low, 0.0)
        self.assertLessEqual(high, 16.0)

    def test_render_writes_svg_and_audit(self) -> None:
        payload = plot.parse_slice(self.write(slice_text()))
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "figure.svg"
            svg = plot.render([payload], ["conditional electron"], "test", output)
            self.assertTrue(output.is_file())
            self.assertIn("<svg", svg)
            self.assertIn("conditional electron", svg)
            self.assertIn("circle", svg)

    def test_display_note_states_block_averaging(self) -> None:
        rows = [[float(r + c) for c in range(400)] for r in range(400)]
        reduced, factor = plot.downsample(rows)
        self.assertGreater(factor, 1)
        self.assertLessEqual(len(reduced), plot.MAX_CELLS)


    def test_no_text_leaves_the_canvas(self) -> None:
        # A long case label used to push the title and the panel captions past the
        # right edge. Every text element must stay inside the canvas.
        import re
        payload = plot.parse_slice(self.write(slice_text().replace(
            "u_range -2 2 v_range -2 2", "u_range -14 14 v_range -14 14")))
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "wide.svg"
            svg = plot.render([payload, payload],
                              ["conditional electron", "conditional hole"],
                              "Si conditional exciton density — LibBSE 7x7x7 → 14x14x14, 28 cells", output)
        width = int(re.search(r'width="(\d+)"', svg).group(1))
        for match in re.finditer(r'<text x="([0-9.]+)" y="([0-9.]+)"(?P<attrs>[^>]*)font-size="([0-9.]+)"[^>]*>(?P<txt>[^<]*)</text>', svg):
            x, size = float(match.group(1)), float(match.group(4))
            span = len(match.group("txt")) * size * 0.52
            left = x - span / 2 if "middle" in match.group("attrs") else x
            self.assertGreaterEqual(left, 0.0, match.group("txt")[:40])
            self.assertLessEqual(left + span, width, match.group("txt")[:40])


if __name__ == "__main__":
    unittest.main()
