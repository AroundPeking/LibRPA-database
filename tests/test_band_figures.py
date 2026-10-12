"""检验实际归档生成、路径审计、幂等性及旧图保留。"""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("generate_band_figures", ROOT / "scripts/generate_band_figures.py")
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class BandFigureTests(unittest.TestCase):
    def fixture(self, root, occupations="2", bad_path=False):
        case = root / "data/calculations/3d/Test/test"
        for directory in ("results", "inputs", "logs", "figures"):
            (case / directory).mkdir(parents=True)
        (case / "inputs/KPT").write_text("K_POINTS\n2\nLine\n0 0 0 1 # G\n0.5 0 0 1 # X\n")
        (case / "results/band_kpath_info").write_text("4 4 1 2\n0 0 0\n0.5 0 0\n")
        (case / "logs/librpa.out").write_text("Bands of occupation: 2\n")
        for method in generator.METHODS:
            coords = "0.4" if bad_path else "0.5"
            high = "40 55" if method == "EXX" else "2 4"
            e1, e2 = high.split()
            (case / f"results/{method}_band_spin_1.dat").write_text(
                f"1 0 0 0 {occupations} -4 {occupations} -1 0 {e1} 0 {e2}\n"
                f"2 {coords} 0 0 {occupations} -3 {occupations} -2 0 {e1} 0 {e2}\n")
        (case / "figures/band_comparison.svg").write_text("original svg bytes\n")
        (case / "figures/band_comparison.json").write_text("{\"original\":true}\n")
        files = {}
        for role in ("inputs", "results", "logs", "figures"):
            files[role] = [{"role": role, "path": p.relative_to(root).as_posix(),
                            "sha256": generator.sha256(p), "size_bytes": p.stat().st_size}
                           for p in sorted((case / role).iterdir())]
        record = {"id": "test", "material": "Test", "dimension": "3d", "files": files,
                  "species": [{"set_id": "preserve-me"}], "summary": {"gw_gap_ev": 123},
                  "properties": [{"key": "band_gap", "method": "G0W0", "value": 123, "status": "reported"}]}
        (case / "record.json").write_text(json.dumps(record))
        return case / "record.json"

    def test_custom_root_explicit_write_preserves_original_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root)
            original = path.read_bytes()
            old_images = {p: p.read_bytes() for p in (path.parent / "figures").iterdir()}
            report = generator.generate_record(path, root)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(report["generated_methods"], ["KS", "EXX", "GW"])
            report = generator.generate_record(path, root, write=True)
            self.assertEqual(len(report["added_properties"]), 2)
            record = json.loads(path.read_text())
            self.assertEqual(record["summary"]["gw_gap_ev"], 123)
            self.assertEqual(record["species"][0]["set_id"], "preserve-me")
            for p, content in old_images.items():
                self.assertEqual(p.read_bytes(), content)
            self.assertEqual(len(record["files"]["figures"]), 6)
            self.assertEqual(record["files"]["figures"][-1]["display_priority"], "secondary")
            metadata = json.loads((path.parent / "figures/band_frontier_metadata.json").read_text())
            self.assertEqual(metadata["methods"]["EXX"]["y_limits_ev"], [-20.5, 61.5])
            for prop in record["properties"][1:]:
                self.assertEqual(prop["label"], "Sampled path band gap")
                self.assertEqual(len(prop["evidence"]), 2)
            snapshot = {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()}
            generator.generate_record(path, root, write=True)
            self.assertEqual(snapshot, {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()})

    def test_path_mismatch_and_raw_hash_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root, bad_path=True)
            result = generator.generate_record(path, root)
            self.assertEqual(result["generated_methods"], [])
            self.assertIn("differs from KPT", result["rejected"]["KS"])
            (path.parent / "results/KS_band_spin_1.dat").write_text("changed\n")
            self.assertIn("SHA-256", generator.generate_record(path, root)["rejected"]["KS"])

    def test_spin2_refused_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root)
            (path.parent / "results/KS_band_spin_2.dat").write_text("spin2\n")
            result = generator.generate_record(path, root)
            self.assertEqual(result["generated_methods"], [])
            self.assertIn("spin2", result["rejected"]["all"])

    def test_zero_export_occupations_use_explicit_unique_logged_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root, occupations="0")
            report = generator.generate_record(path, root, write=True)
            self.assertEqual(len(report["added_properties"]), 2)
            metadata = json.loads((path.parent / "figures/band_frontier_metadata.json").read_text())
            analysis = metadata["methods"]["KS"]
            self.assertEqual(analysis["occupation_audit"]["kind"], "explicit_logged_raw_boundary")
            self.assertEqual(analysis["raw_occupations"], [[0] * 4] * 2)
            self.assertEqual(analysis["gap_status"], "reported")
            self.assertEqual(analysis["sampled_path_gap_ev"], 3)

    def test_zero_export_without_unique_log_boundary_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root, occupations="0")
            log = path.parent / "logs/librpa.out"
            log.write_text("Bands of occupation: 2\nBands of occupation: 1\n")
            record = json.loads(path.read_text())
            record["files"]["logs"][0]["sha256"] = generator.sha256(log)
            path.write_text(json.dumps(record))
            result = generator.generate_record(path, root)
            self.assertEqual(result["generated_methods"], [])
            self.assertEqual(result["added_properties"], [])

    def test_2d_record_skipped_even_with_explicit_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root)
            record = json.loads(path.read_text())
            record["dimension"] = "2d"
            path.write_text(json.dumps(record))
            snapshot = {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()}
            result = generator.generate_record(path, root, write=True)
            self.assertEqual(result["generated_methods"], [])
            self.assertEqual(snapshot, {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()})

    def test_generator_nonfinite_raw_occupation_writes_strict_json_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root, occupations="nan")
            result = generator.generate_record(path, root, write=True)
            self.assertEqual(result["added_properties"], [])
            self.assertEqual(result["generated_methods"], ["KS", "EXX", "GW"])
            text = (path.parent / "figures/band_frontier_metadata.json").read_text()
            self.assertNotIn("NaN", text)
            metadata = json.loads(text)
            for analysis in metadata["methods"].values():
                self.assertIsNone(analysis["raw_occupations"][0][0])
                self.assertEqual(analysis["nonfinite_raw_occupations"][0]["raw_band_index"], 1)
                self.assertEqual(analysis["gap_status"], "rejected")

    def test_existing_failed_or_validated_properties_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root)
            record = json.loads(path.read_text())
            record["properties"] += [{"key": "band_gap", "method": "PBE", "value": None, "status": "failed"},
                                     {"key": "band_gap", "method": "EXX", "value": 999, "status": "validated"}]
            properties = record["properties"][:]
            path.write_text(json.dumps(record))
            generator.generate_record(path, root, write=True)
            self.assertEqual(json.loads(path.read_text())["properties"], properties)

    def test_actual_line_kpt_alternative_passes_after_other_candidates_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root)
            kpt = path.parent / "inputs/KPT"
            native = kpt.read_text()
            kpt.write_text("K_POINTS\n0\nGamma\n1 1 1 0 0 0\n")
            alternative = path.parent / "inputs/KPT_band"
            alternative.write_text(native)
            record = json.loads(path.read_text())
            record["files"]["inputs"][0]["sha256"] = generator.sha256(kpt)
            record["files"]["inputs"].append({"path": alternative.relative_to(root).as_posix(),
                                                "sha256": generator.sha256(alternative)})
            path.write_text(json.dumps(record))
            result = generator.generate_record(path, root, write=True)
            self.assertEqual(result["generated_methods"], ["KS", "EXX", "GW"])
            metadata = json.loads((path.parent / "figures/band_frontier_metadata.json").read_text())
            audit = metadata["methods"]["KS"]["kpath_audit"]
            self.assertTrue(audit["source_path"].endswith("KPT_band"))
            self.assertEqual(len(audit["rejected_candidates"]), 1)

    def test_five_missing_pairs_independently_recomputed_from_raw_extrema(self):
        expected = {"AlP": (8, 1.60680, 7.39451), "BAs": (4, 1.18591, 6.49227),
                    "BP": (4, 1.28967, 7.13040), "CaO": (8, 3.55481, 14.26462),
                    "NaCl": (8, 5.08771, 13.36155)}
        for material, (occupied, ks, exx) in expected.items():
            path = next(ROOT.glob(f"data/calculations/3d/{material}/*/record.json"))
            export_count = int((path.parent / "results/band_kpath_info").read_text().splitlines()[0].split()[1])
            for method, gap in (("KS", ks), ("EXX", exx)):
                with self.subTest(material=material, method=method):
                    rows = [[float(value) for value in line.split()[5::2]][:export_count]
                            for line in (path.parent / f"results/{method}_band_spin_1.dat").read_text().splitlines()
                            if line.strip()]
                    vbm = max(value for row in rows for value in row[:occupied])
                    cbm = min(value for row in rows for value in row[occupied:])
                    self.assertAlmostEqual(cbm - vbm, gap, places=5)
                    table = generator.plot_bands.parse_abacus_band_table(path.parent / f"results/{method}_band_spin_1.dat")
                    contract = {"kind": "logged_raw_boundary", "occupied_band_count": occupied, "evidence": ["same.log"]}
                    if all(value == 0 for row in table.occupations for value in row[:export_count]):
                        analysis = generator.plot_bands.analyze_frontier(table, occupation_contract=contract,
                                                                        declared_export_band_count=export_count)
                    else:
                        contract = {"kind": "uniform_k_weighted", "occupied_band_count": occupied,
                                    "kpoint_count": len(rows), "evidence": ["same.log"]}
                        analysis = generator.plot_bands.analyze_frontier(table, occupation_contract=contract,
                                                                        declared_export_band_count=export_count)
                    self.assertEqual(analysis["gap_status"], "reported")
                    self.assertAlmostEqual(analysis["sampled_path_gap_ev"], gap, places=5)

    def test_actual_alp_full_tail_is_preserved_diagnosed_and_never_selected(self):
        path = next(ROOT.glob("data/calculations/3d/AlP/*/record.json"))
        for method in generator.METHODS:
            table = generator.plot_bands.parse_abacus_band_table(path.parent / f"results/{method}_band_spin_1.dat")
            tail = generator._tail_diagnostics(table, 44)
            self.assertEqual(tail["rejected_raw_band_indices"], list(range(45, 57)))
            if method == "KS":
                self.assertEqual(tail["next_k_head_exact_match_rows"], list(range(1, 121)))
            if method == "EXX":
                self.assertEqual(tail["nonfinite_state_count"], 6)
                self.assertLess(tail["finite_minimum_ev"], -874)
            if method == "GW":
                self.assertEqual(tail["zero_state_count"], 121 * 12)
        metadata_path = path.parent / "figures/band_frontier_metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            self.assertEqual(metadata["methods"]["GW"]["gap_status"], "rejected")

    def test_actual_cao_nacl_gw_negative_full_gap_keeps_fixed_low_window(self):
        for material in ("CaO", "NaCl"):
            path = next(ROOT.glob(f"data/calculations/3d/{material}/*/record.json"))
            table = generator.plot_bands.parse_abacus_band_table(path.parent / "results/GW_band_spin_1.dat")
            contract = {"kind": "logged_raw_boundary", "occupied_band_count": 8, "evidence": ["same.log"]}
            if any(value != 0 for row in table.occupations for value in row):
                contract = {"kind": "uniform_k_weighted", "occupied_band_count": 8,
                            "kpoint_count": len(table.x), "evidence": ["same.log"]}
            analysis = generator.plot_bands.analyze_frontier(table, occupation_contract=contract)
            self.assertLess(analysis["raw_audit"]["sampled_path_gap_ev"], 0)
            self.assertEqual(analysis["gap_status"], "rejected")
            self.assertEqual(analysis["raw_selected_empty_bands"], list(range(9, 13)))
            self.assertGreater(analysis["diagnostic_selected_window_gap_ev"], 0)
            self.assertTrue(all(max(row) == 12 for row in analysis["mapping_one_based"]))
            self.assertEqual(analysis["figure_status"], "renderable")

    def test_actual_near_gap_viewport_and_rejected_gw_svg_references(self):
        declared = 0
        for path in ROOT.glob("data/calculations/3d/*/*/record.json"):
            metadata_path = path.parent / "figures/band_frontier_metadata.json"
            if not metadata_path.exists():
                continue
            record = json.loads(path.read_text())
            metadata = json.loads(metadata_path.read_text())
            references = {entry["path"] for entry in record["files"]["figures"]}
            for method, analysis in metadata["methods"].items():
                svg = (path.parent / f"figures/{method.lower()}_frontier.svg").relative_to(ROOT).as_posix()
                self.assertEqual(len(analysis["raw_selected_occupied_bands"]), 3)
                self.assertEqual(len(analysis["raw_selected_empty_bands"]), 4)
                if analysis["original_frontier_admission_audit"]["sampled_path_gap_ev"] <= 0:
                    self.assertEqual(record["material"] in {"GaAs", "GaP"}, True)
                    self.assertEqual(method, "GW")
                    self.assertEqual(analysis["figure_status"], "rejected")
                    self.assertNotIn(svg, references)
                    self.assertIn("nonpositive", analysis["figure_rejection_reason"])
                    continue
                declared += 1
                self.assertIn(svg, references)
                gap = analysis["selected_window_path_gap_ev"]
                self.assertEqual(analysis["y_limits_ev"], [-max(2.5, 0.5 * gap), gap + max(3, 0.5 * gap)])
                self.assertTrue(analysis["viewport"]["selected_raw_window_frozen_before_sorting"])
                if record["material"] == "AlP" and method == "EXX":
                    self.assertAlmostEqual(analysis["y_limits_ev"][0], -3.697255)
                    self.assertAlmostEqual(analysis["y_limits_ev"][1], 11.091765)
        if declared:
            self.assertEqual(declared, 49)

    def test_nonpositive_selected_gap_unreferences_previous_svg_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root)
            generator.generate_record(path, root, write=True)
            svg = path.parent / "figures/gw_frontier.svg"
            original_svg = svg.read_bytes()
            table = path.parent / "results/GW_band_spin_1.dat"
            table.write_text(table.read_text().replace("0 2", "0 -2"))
            record = json.loads(path.read_text())
            for entry in record["files"]["results"]:
                if entry["path"].endswith("GW_band_spin_1.dat"):
                    entry["sha256"] = generator.sha256(table)
            path.write_text(json.dumps(record))
            report = generator.generate_record(path, root, write=True)
            self.assertEqual(report["generated_methods"], ["KS", "EXX"])
            self.assertEqual(svg.read_bytes(), original_svg)
            record = json.loads(path.read_text())
            self.assertNotIn(svg.relative_to(root).as_posix(), {entry["path"] for entry in record["files"]["figures"]})
            metadata = json.loads((path.parent / "figures/band_frontier_metadata.json").read_text())
            self.assertEqual(metadata["methods"]["GW"]["figure_status"], "rejected")
            self.assertTrue(metadata["methods"]["GW"]["mapping_one_based"])

    def test_actual_svg_markers_are_hollow_at_saved_raw_extrema(self):
        ns = {"s": "http://www.w3.org/2000/svg"}
        for path in ROOT.glob("data/calculations/3d/*/*/figures/band_frontier_metadata.json"):
            metadata = json.loads(path.read_text())
            for method, analysis in metadata["methods"].items():
                if analysis["figure_status"] == "rejected":
                    continue
                with self.subTest(calculation=metadata["calculation_id"], method=method):
                    svg = ET.parse(path.parent / f"{method.lower()}_frontier.svg").getroot()
                    self.assertEqual(len(svg.findall("s:path", ns)),
                                     len(analysis["raw_selected_occupied_bands"] + analysis["raw_selected_empty_bands"]))
                    lower, upper = analysis["y_limits_ev"]
                    xmin, xmax = analysis["native_x"][0], analysis["native_x"][-1]
                    for edge in ("vbm", "cbm"):
                        seen = set()
                        for number, point in enumerate(analysis[f"{edge}_endpoints"]):
                            pair = (point["x"], point["aligned_energy_ev"])
                            if pair in seen:
                                continue
                            seen.add(pair)
                            marker = svg.find(f".//*[@id='{method}-{edge.upper()}-{number+1}']")
                            self.assertIsNotNone(marker)
                            self.assertEqual(marker.get("fill"), "none")
                            x = 105 + (pair[0] - xmin) / (xmax - xmin) * 940
                            y = 88 + (upper - pair[1]) / (upper - lower) * 548
                            actual_x = float(marker.get("cx")) if edge == "vbm" else float(marker.get("x")) + 6.5
                            actual_y = float(marker.get("cy")) if edge == "vbm" else float(marker.get("y")) + 6.5
                            self.assertAlmostEqual(actual_x, x, delta=0.00051)
                            self.assertAlmostEqual(actual_y, y, delta=0.00051)

    def test_nonuniform_path_ticks_are_native_and_gamma_is_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "KPT"
            path.write_text("K_POINTS\n3\nLine\n0 0 0 2 # G\n0.5 0 0 1 # X\n0.5 0.5 0 1 # M\n")
            table = generator.plot_bands.BandTable([4, 8, 9, 13], [[-1, 1]] * 4,
                                                   [[2, 0]] * 4, [4, 8, 9, 13],
                                                   [[0, 0, 0], [0.25, 0, 0], [0.5, 0, 0], [0.5, 0.5, 0]])
            audit = generator.audit_kpath(table, path)
            self.assertEqual([tick["x"] for tick in audit["ticks"]], [4, 9, 13])
            self.assertEqual(audit["ticks"][0]["label"], "Γ")
            self.assertFalse(audit["reciprocal_metric_available"])


if __name__ == "__main__":
    unittest.main()
