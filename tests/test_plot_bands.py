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
            self.assertEqual(table.x, [1.0, 2.0])
            self.assertEqual(table.energies, [[-1.5, 2.5], [-1.0, 3.0]])
            self.assertEqual(table.occupations, [[2.0, 0.0], [2.0, 0.0]])
            self.assertEqual(table.native_kpoint_indices, [1, 2])
            self.assertEqual(table.fractional_kpoints, [[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]])

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

    def make_table(self, rows=None, occupations=None):
        rows = rows or [[-4, -2, 1, 3], [-3, -1, 2, 4]]
        return self.plot.BandTable([1.0, 3.0], rows,
                                   occupations or [[2, 2, 0, 0], [2, 2, 0, 0]],
                                   [1, 3], [[0, 0, 0], [0.5, 0, 0]])

    def test_full_raw_edges_ties_and_native_positions(self):
        table = self.make_table([[-4, -1, 1, 3], [-3, -1, 2, 4]])
        result = self.plot.analyze_frontier(table)
        self.assertEqual(result["sampled_path_gap_ev"], 2)
        self.assertEqual(len(result["vbm_endpoints"]), 2)
        self.assertEqual(result["vbm_endpoints"][1]["native_kpoint_index"], 3)
        self.assertEqual(result["cbm_endpoints"][0]["raw_band_index"], 3)
        self.assertEqual(result["cbm_endpoints"][0]["aligned_energy_ev"], 2)
        self.assertTrue(result["reference"]["not_fermi"])

    def test_fixed_raw_window_sort_mapping_no_mutation(self):
        table = self.make_table([[-1, -4, 8, 2], [-2, -3, 3, 9]])
        original = [row[:] for row in table.energies]
        result = self.plot.analyze_frontier(table)
        self.assertEqual(result["mapping_one_based"], [[2, 1, 4, 3], [2, 1, 3, 4]])
        self.assertEqual(table.energies, original)
        for row, mapping, values in zip(table.energies, result["mapping_one_based"], result["display_energies_ev"]):
            self.assertEqual(values, [row[b - 1] - result["reference"]["energy_ev"] for b in mapping])
            self.assertEqual(sorted(row), sorted(row[b - 1] for b in mapping))

    def test_fractional_variable_nonprefix_and_missing_occupation_refused(self):
        cases = [None, [[0.5, 0.5, 0, 0]] * 2,
                 [[2, 2, 0, 0], [2, 0, 0, 0]],
                 [[2, 0, 2, 0]] * 2, [[0, 0, 0, 0]] * 2,
                 [[float("nan"), 2, 0, 0]] * 2, [[1, 2, 0, 0]] * 2]
        for occupations in cases:
            with self.subTest(occupations=occupations):
                table = self.make_table()
                table.occupations = occupations
                with self.assertRaises(ValueError):
                    self.plot.analyze_frontier(table)

    def test_explicit_weighted_contract_does_not_guess_fractional_occupation(self):
        table = self.make_table(occupations=[[1, 1, 0, 0]] * 2)
        contract = {"kind": "uniform_k_weighted", "kpoint_count": 2,
                    "occupied_band_count": 2, "evidence": ["producer.log"]}
        result = self.plot.analyze_frontier(table, occupation_contract=contract)
        self.assertEqual(result["occupation_audit"]["full_occupation"], 2)
        with self.assertRaises(ValueError):
            self.plot.analyze_frontier(table, occupation_contract={**contract, "evidence": []})
        with self.assertRaises(ValueError):
            self.plot.analyze_frontier(table, occupation_contract={**contract, "occupied_band_count": 1})

    def test_unselected_intrusion_never_changes_frozen_window_or_full_gap(self):
        rows = [[-4, -2, 1, 3, 0.5], [-3, -1, 2, 4, 30]]
        table = self.make_table(rows, [[2, 2, 0, 0, 0]] * 2)
        result = self.plot.analyze_frontier(table, empty_window=2)
        self.assertEqual(result["status"], "diagnostic")
        self.assertEqual(result["gap_status"], "reported")
        self.assertEqual(result["sampled_path_gap_ev"], 1.5)
        self.assertEqual(result["raw_selected_empty_bands"], [3, 4])
        self.assertTrue(all(5 not in row for row in result["mapping_one_based"]))
        self.assertEqual(result["unselected_intrusions"][0]["raw_band_index"], 5)

    def test_bad_high_state_forces_low_energy_diagnostic_not_ordinary_gap(self):
        table = self.make_table([[-4, -2, 1, 3, -800], [-3, -1, 2, 4, 30]], [[2, 2, 0, 0, 0]] * 2)
        result = self.plot.analyze_frontier(table, empty_window=2)
        self.assertEqual(result["gap_status"], "rejected")
        self.assertIsNone(result["sampled_path_gap_ev"])
        self.assertEqual(result["cbm_endpoints"][0]["raw_band_index"], 3)
        self.assertEqual(result["raw_audit"]["cbm_ev"], -800)

    def test_nonfinite_full_spectrum_and_selected_rejection(self):
        table = self.make_table([[-4, -2, 1, 3, float("nan")], [-3, -1, 2, 4, 30]], [[2, 2, 0, 0, 0]] * 2)
        result = self.plot.analyze_frontier(table, empty_window=2)
        self.assertEqual(result["gap_status"], "rejected")
        self.assertEqual(result["raw_audit"]["nonfinite_states"][0]["raw_band_index"], 5)
        with self.assertRaisesRegex(ValueError, "nonfinite selected"):
            self.plot.analyze_frontier(table, empty_window=3)

    def test_known_pathology_cannot_be_promoted(self):
        result = self.plot.analyze_frontier(self.make_table(), known_pathological=True)
        self.assertEqual(result["gap_status"], "rejected")
        self.assertEqual(result["status"], "diagnostic")

    def test_external_boundary_can_only_produce_explicit_diagnostic(self):
        table = self.make_table(occupations=[[0, 0, 0, 0]] * 2)
        with self.assertRaises(ValueError):
            self.plot.analyze_frontier(table, occupied_count=2)
        result = self.plot.analyze_frontier(table, occupied_count=2, diagnostic_evidence=["producer.log"])
        self.assertEqual(result["occupation_audit"]["kind"], "external_boundary_diagnostic_only")
        self.assertEqual(result["gap_status"], "rejected")

    def test_large_exx_gap_shows_complete_existing_selection_with_margin(self):
        table = self.make_table([[-4, -2, 35, 49], [-3, -1, 37, 55]])
        result = self.plot.analyze_frontier(table)
        self.assertEqual(result["y_limits_ev"], [-18, 58.95])
        self.assertEqual(result["viewport"]["cut_states"], [])
        self.assertEqual(result["viewport"]["previous_near_gap_limits_ev"], [-18, 54])
        self.assertEqual(result["display_energies_ev"][-1][-1], 56)
        svg = self.plot.render_frontier_svg(table, result, [{"x": 1, "label": "Γ"}], "EXX test", "EXX")
        self.assertIn('stroke-dasharray="11 4 2 4"', svg)
        self.assertIn('id="EXX-VBM-1"', svg)
        self.assertIn('id="EXX-CBM-1"', svg)
        self.assertIn('fill="none"', svg)
        self.assertIn('native k-point index', svg)
        self.assertIn('Γ', svg)

    def test_nearby_unselected_intrusion_is_reported_without_rejecting_full_gap(self):
        table = self.make_table([[-4, -2, 1, 3, 4], [-3, -1, 2, 4, 5]], [[2, 2, 0, 0, 0]] * 2)
        result = self.plot.analyze_frontier(table, empty_window=2)
        self.assertTrue(result["unselected_intrusions"])
        self.assertEqual(result["status"], "reported")
        self.assertEqual(result["sampled_path_gap_ev"], 2)

    def test_logged_zero_export_boundary_requires_evidence_and_preserves_raw(self):
        table = self.make_table(occupations=[[0, 0, 0, 0]] * 2)
        contract = {"kind": "logged_raw_boundary", "occupied_band_count": 2, "evidence": ["same.log"]}
        result = self.plot.analyze_frontier(table, occupation_contract=contract)
        self.assertEqual(result["sampled_path_gap_ev"], 2)
        self.assertEqual(result["raw_occupations"], table.occupations)
        with self.assertRaises(ValueError):
            self.plot.analyze_frontier(table, occupation_contract={**contract, "evidence": []})
        table.occupations[0][0] = 0.5
        with self.assertRaisesRegex(ValueError, "all-zero"):
            self.plot.analyze_frontier(table, occupation_contract=contract)

    def test_declared_export_is_audited_separately_from_rejected_nonfinite_tail(self):
        table = self.make_table([[-4, -2, 1, 3, float("nan"), -800], [-3, -1, 2, 4, 0, -700]],
                                [[0] * 6] * 2)
        contract = {"kind": "logged_raw_boundary", "occupied_band_count": 2, "evidence": ["same.log"]}
        result = self.plot.analyze_frontier(table, occupation_contract=contract, declared_export_band_count=4)
        self.assertEqual(result["raw_audit"]["raw_band_count"], 6)
        self.assertEqual(result["declared_export_audit"]["raw_band_count"], 4)
        self.assertEqual(result["rejected_raw_tail_bands"], [5, 6])
        self.assertEqual(result["gap_status"], "reported")
        self.assertEqual(result["sampled_path_gap_ev"], 2)
        self.assertEqual(result["status"], "diagnostic")
        self.assertTrue(all(max(row) <= 4 for row in result["mapping_one_based"]))
        self.assertEqual(result["raw_audit"]["nonfinite_states"][0]["source_column_one_based"], 14)
        json.dumps(result, allow_nan=False)
        with self.assertRaises(ValueError):
            self.plot.analyze_frontier(table, occupation_contract=contract, declared_export_band_count=7)

    def test_nonfinite_occupation_is_null_with_original_raw_location_metadata(self):
        table = self.make_table(occupations=[[float("nan"), 2, 0, 0], [2, 2, 0, 0]])
        result = self.plot.analyze_frontier(table, occupied_count=2, diagnostic_evidence=["same.log"])
        self.assertIsNone(result["raw_occupations"][0][0])
        self.assertEqual(result["nonfinite_raw_occupations"][0]["source_column_one_based"], 5)
        self.assertEqual(result["nonfinite_raw_occupations"][0]["raw_value"], "nan")
        self.assertEqual(result["gap_status"], "rejected")
        self.assertIn("null", json.dumps(result, allow_nan=False))

    def test_default_three_four_window_preserves_selection_without_clipping(self):
        rows = [[-100, -80, -60, -20, -1, -2, -3, 6, 7, 8, 9, 100]] * 2
        table = self.make_table(rows, [[2] * 7 + [0] * 5] * 2)
        result = self.plot.analyze_frontier(table)
        self.assertEqual(result["raw_selected_occupied_bands"], [5, 6, 7])
        self.assertEqual(result["raw_selected_empty_bands"], [8, 9, 10, 11])
        self.assertEqual(result["y_limits_ev"], [-3.5, 10.6])
        self.assertEqual(result["viewport"]["cut_states"], [])
        self.assertEqual(result["raw_audit"]["band_ranges"][0]["minimum_ev"], -100)
        self.assertEqual(len(result["mapping_one_based"][0]), 7)

    def test_deep_selected_occupied_bands_are_fully_visible_without_adding_bands(self):
        rows = [[-120, -90, -30, -18, -1, 2, 6, 9, 14, 300],
                [-110, -80, -28, -16, -2, 3, 7, 11, 18, 400]]
        table = self.make_table(rows, [[2] * 5 + [0] * 5] * 2)
        original = [row[:] for row in rows]
        result = self.plot.analyze_frontier(table)
        self.assertEqual(result["raw_selected_occupied_bands"], [3, 4, 5])
        self.assertEqual(result["raw_selected_empty_bands"], [6, 7, 8, 9])
        self.assertEqual(result["mapping_one_based"][0], [3, 4, 5, 6, 7, 8, 9])
        self.assertEqual(result["viewport"]["cut_states"], [])
        self.assertLess(result["y_limits_ev"][0], -29)
        self.assertGreater(result["y_limits_ev"][1], 19)
        self.assertEqual(len(result["display_energies_ev"][0]), 7)
        self.assertEqual(table.energies, original)
        self.assertEqual(result["reference"]["energy_ev"], -1)
        self.assertEqual(result["selected_window_path_gap_ev"], 3)
        self.assertEqual(result["sampled_path_gap_ev"], 3)

    def test_nonpositive_selected_gap_renders_with_metadata_rejection_note(self):
        # 归档条目按原始数据呈现：非正 gap 照画，病理仅记录在元数据。
        table = self.make_table([[-4, -1, -2, 4], [-3, -2, 1, 5]])
        result = self.plot.analyze_frontier(table)
        self.assertEqual(result["figure_status"], "renderable")
        self.assertIsNotNone(result["y_limits_ev"])
        self.assertEqual(result["selected_window_path_gap_ev"], -1)
        self.assertIn("nonpositive frozen", result["figure_rejection_reason"])
        self.assertEqual(result["gap_status"], "rejected")
        svg = self.plot.render_frontier_svg(table, result, [], "bad", "GW")
        self.assertIn("Frozen occupation-separated energy-rank display", svg)

    def test_generic_interface_has_no_automatic_occupation_inference(self):
        table = self.plot.BandTable([0, 1], [[-1, 2], [-2, 3]])
        self.assertIsNone(table.occupations)
        with self.assertRaisesRegex(ValueError, "missing occupations"):
            self.plot.analyze_frontier(table)


if __name__ == "__main__":
    unittest.main()
