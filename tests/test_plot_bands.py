"""Tests for the portable reference band plotting interface."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/plot_bands.py"


class PlotBandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("plot_bands", SCRIPT)
        cls.plot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.plot)

    def test_parser_preserves_band_column_order_and_skips_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bands.dat"
            source.write_text("# x band columns\n0.0 -2.0 1.0\n1.0 -1.0 2.0\n", encoding="utf-8")
            table = self.plot.parse_band_table(source)
            self.assertEqual(table.x, [0.0, 1.0])
            self.assertEqual(table.energies, [[-2.0, 1.0], [-1.0, 2.0]])

    def test_parser_rejects_inconsistent_band_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bands.dat"
            source.write_text("0.0 -2.0 1.0\n1.0 -1.0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "same number"):
                self.plot.parse_band_table(source)

    def test_abacus_parser_extracts_energy_from_occupation_energy_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "GW_band_spin_1.dat"
            source.write_text(
                "1 0.0 0.0 0.0 2.0 -1.5 0.0 2.5\n"
                "2 0.5 0.0 0.0 2.0 -1.0 0.0 3.0\n",
                encoding="utf-8",
            )
            table = self.plot.parse_abacus_band_table(source)
            self.assertEqual(table.x, [0.0, 1.0])
            self.assertEqual(table.energies, [[-1.5, 2.5], [-1.0, 3.0]])

    def test_abacus_parser_rejects_incomplete_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bad.dat"
            source.write_text("1 0 0 0 2 -1.5 0.0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "occupation/energy"):
                self.plot.parse_abacus_band_table(source)

    def test_sidecar_records_calculation_and_input_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bands.dat"
            source.write_text("0.0 -2.0 1.0\n1.0 -1.0 2.0\n", encoding="utf-8")
            output = root / "bands.png"
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            sidecar = self.plot.write_sidecar(output, "case-1", expected, source)
            self.assertEqual(sidecar["calculation_id"], "case-1")
            self.assertEqual(sidecar["input_sha256"], expected)
            self.assertEqual(json.loads(output.with_suffix(".json").read_text())["table_sha256"], expected)


if __name__ == "__main__":
    unittest.main()
