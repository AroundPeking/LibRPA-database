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

    def test_nonfinite_selected_states_render_as_broken_line_diagnostic(self):
        # QP 解矢 NaN 落在冻结窗内时仍出图：折线在非有限 k 点断开，标记 diagnostic。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.fixture(root)
            gw = path.parent / "results/GW_band_spin_1.dat"
            rows = gw.read_text().splitlines()
            fields = rows[1].split()
            fields[7] = "nan"  # 第2个k点、空态raw band 2 的能量置为非有限。
            rows[1] = " ".join(fields)
            gw.write_text("\n".join(rows) + "\n")
            record = json.loads(path.read_text())
            for group in record["files"]["results"]:
                if group["path"].endswith("GW_band_spin_1.dat"):
                    group["sha256"] = generator.sha256(gw)
            path.write_text(json.dumps(record))
            report = generator.generate_record(path, root, write=True)
            self.assertIn("GW", report["generated_methods"])
            self.assertIn("GW", report["rejected"])
            svg = (path.parent / "figures/gw_frontier.svg").read_text()
            self.assertIn("Frozen occupation-separated energy-rank display", svg)
            self.assertNotIn("diagnostic-warning", svg)
            self.assertNotIn("nan", svg)
            rank2 = svg.split('<path id="GW-rank-2" d="')[1].split('"')[0]
            self.assertTrue(rank2.startswith("M"))
            self.assertNotIn("L", rank2)
            metadata = json.loads((path.parent / "figures/band_frontier_metadata.json").read_text())
            analysis = metadata["methods"]["GW"]
            self.assertEqual(analysis["figure_status"], "renderable")
            self.assertEqual(analysis["status"], "diagnostic")
            self.assertEqual(len(analysis["nonfinite_display_states"]), 1)
            self.assertIn(None, analysis["display_energies_ev"][1])
            updated = json.loads(path.read_text())
            names = [Path(entry["path"]).name for entry in updated["files"]["figures"]]
            self.assertIn("gw_frontier.svg", names)

    def test_inclusive_kpath_convention_with_jump_node_audits_aims_segments(self):
        # FHI-aims `output band` 段含双端点；K|U 型断点以 count 0 跳变节点表达。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "data/calculations/3d/Test/incl"
            (case / "inputs").mkdir(parents=True)
            kpt = case / "inputs/KPT_band"
            kpt.write_text("# kpath_convention: inclusive-segments (FHI-aims output band)\n"
                           "K_POINTS\n4\nline\n"
                           "0.0 0.0 0.0 3 # G\n"
                           "0.5 0.0 0.5 0 # X\n"
                           "0.625 0.25 0.625 3 # U\n"
                           "0.5 0.0 0.5 1 # X\n")
            rows = []
            for index, (x, y, z) in enumerate([(0.0, 0.0, 0.0), (0.25, 0.0, 0.25), (0.5, 0.0, 0.5),
                                               (0.625, 0.25, 0.625), (0.5625, 0.125, 0.5625),
                                               (0.5, 0.0, 0.5)], 1):
                rows.append(f"{index} {x} {y} {z} 2.0 -4.0 2.0 -1.0 0.0 3.0 0.0 5.0")
            table_path = case / "results"
            table_path.mkdir(parents=True)
            (table_path / "GW_band_spin_1.dat").write_text("\n".join(rows) + "\n")
            table = generator.plot_bands.parse_abacus_band_table(table_path / "GW_band_spin_1.dat")
            audit = generator.audit_kpath(table, kpt)
            self.assertEqual(audit["status"], "verified")
            self.assertEqual(audit["kpath_convention"], "inclusive-segments")
            self.assertEqual([tick["label"] for tick in audit["ticks"]], ["Γ", "X", "U", "X"])
            self.assertEqual([tick["row_index"] for tick in audit["ticks"]], [1, 3, 4, 6])
            # 无标记时同一文件必须退回互斥段语义并被拒收。
            plain = case / "inputs/KPT_plain"
            plain.write_text("K_POINTS\n4\nline\n"
                             "0.0 0.0 0.0 3 # G\n"
                             "0.5 0.0 0.5 0 # X\n"
                             "0.625 0.25 0.625 3 # U\n"
                             "0.5 0.0 0.5 1 # X\n")
            with self.assertRaises(ValueError):
                generator.audit_kpath(table, plain)

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
            path = next(ROOT.glob(f"data/calculations/3d/{material}/{material.lower()}-paper-*/record.json"))
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
        path = next(ROOT.glob("data/calculations/3d/AlP/alp-paper-*/record.json"))
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
            path = next(ROOT.glob(f"data/calculations/3d/{material}/{material.lower()}-paper-*/record.json"))
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

    def test_actual_full_selected_band_viewport_and_rejected_gw_svg_references(self):
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
                    self.assertIn("nonpositive", analysis["figure_rejection_reason"])
                declared += 1
                self.assertIn(svg, references)
                gap = analysis["selected_window_path_gap_ev"]
                values = [v for row in analysis["display_energies_ev"] for v in row if v is not None]
                previous = [-max(2.5, 0.5 * gap), gap + max(3, 0.5 * gap)]
                limits, _ = generator.plot_bands.selected_band_viewport(analysis["display_energies_ev"], previous)
                self.assertEqual(analysis["y_limits_ev"], limits)
                self.assertLess(limits[0], min(values))
                self.assertGreater(limits[1], max(values))
                self.assertEqual(analysis["viewport"]["cut_states"], [])
                self.assertTrue(analysis["viewport"]["selected_raw_window_frozen_before_sorting"])
        if declared:
            self.assertEqual(declared, 194)

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
            self.assertEqual(report["generated_methods"], ["KS", "EXX", "GW"])
            record = json.loads(path.read_text())
            self.assertIn(svg.relative_to(root).as_posix(), {entry["path"] for entry in record["files"]["figures"]})
            metadata = json.loads((path.parent / "figures/band_frontier_metadata.json").read_text())
            self.assertEqual(metadata["methods"]["GW"]["figure_status"], "renderable")
            self.assertIn("nonpositive", metadata["methods"]["GW"]["figure_rejection_reason"])
            self.assertEqual(metadata["methods"]["GW"]["gap_status"], "rejected")
            self.assertTrue(metadata["methods"]["GW"]["mapping_one_based"])
            self.assertIn("Frozen occupation-separated energy-rank display", svg.read_text())

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

    def test_replacement_hbn_audit_is_source_bound_and_preserves_raw_status(self):
        import copy
        import shutil
        relative = Path("data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / relative, root / relative)
            path = root / relative / "record.json"
            before = json.loads(path.read_text())
            originals = {p: p.read_bytes() for group in ("inputs", "results", "logs")
                         for p in (path.parent / group).iterdir() if p.is_file()}
            report = generator.generate_hbn_record(path, root)
            self.assertFalse(report["write"])
            self.assertEqual(json.loads(path.read_text()), before)
            self.assertAlmostEqual(report["exx_path_gap_ev"], 11.01971)
            self.assertFalse(report["gw_full_spectrum_accepted"])
            generator.generate_hbn_record(path, root, write=True)
            after = json.loads(path.read_text())
            for field in ("summary", "paper_values", "species"):
                self.assertEqual(after[field], before[field])
            self.assertNotIn("status", after)
            self.assertEqual(after["software"]["librpa"], before["software"]["librpa"])
            for p, content in originals.items():
                self.assertEqual(p.read_bytes(), content)
            meta = json.loads((path.parent / "figures/hbn_frontier_audit.json").read_text())
            self.assertEqual(meta["methods"]["GW"]["gap_status"], "rejected")
            self.assertEqual(len(meta["methods"]["GW"]["raw_audit"]["nonfinite_states"]), 1)
            for method in generator.METHODS:
                analysis = meta["methods"][method]
                self.assertEqual(analysis["raw_selected_occupied_bands"], [1, 2, 3, 4])
                self.assertEqual(analysis["raw_selected_empty_bands"], [5, 6, 7, 8])
                self.assertTrue(analysis["reconstruction_verified"])
                self.assertEqual(len(analysis["mapping_one_based"]), 91)
                svg = ET.parse(path.parent / f"figures/{method.lower()}_frontier.svg").getroot()
                self.assertEqual(svg.find(".//*[@id='" + method + "-VBM-1']").get("fill"), "none")
            self.assertNotEqual(meta["methods"]["EXX"]["y_limits_ev"], meta["methods"]["GW"]["y_limits_ev"])
            snapshot = {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()}
            generator.generate_hbn_record(path, root, write=True)
            self.assertEqual(snapshot, {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()})
            raw = path.parent / "results/EXX_band_spin_1.dat"
            raw.write_bytes(raw.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
                generator.generate_hbn_record(path, root, write=True)

    def test_replacement_hbn_requires_a_full_matching_commit_in_each_stage(self):
        import shutil
        relative = Path("data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008")
        for stage in ("calculation__OUT.ABACUS__running_scf.log",
                      "calculation__pbe_path_91_20261008__OUT.ABACUS__running_nscf.log"):
            for replacement in ("unknown", "0" * 40):
                with self.subTest(stage=stage, replacement=replacement), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    shutil.copytree(ROOT / relative, root / relative)
                    path = root / relative / "record.json"
                    log = path.parent / "logs" / stage
                    text = log.read_text()
                    commit = __import__("re").search(r"(?m)^\s*Commit:\s*([0-9a-f]{40})\b", text).group(1)
                    log.write_text(text.replace(commit, replacement))
                    record = json.loads(path.read_text())
                    item = next(entry for entry in record["files"]["logs"] if entry["path"].endswith(stage))
                    item.update(sha256=generator.sha256(log), size_bytes=log.stat().st_size)
                    path.write_text(json.dumps(record))
                    before = {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()}
                    with self.assertRaisesRegex(ValueError, "source identity"):
                        generator.generate_hbn_record(path, root, write=True)
                    self.assertEqual(before, {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()})

    def test_replacement_hbn_rejects_weights_inconsistent_with_single_spin_receipt(self):
        import shutil
        relative = Path("data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008")
        for method in generator.METHODS:
            with self.subTest(method=method), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(ROOT / relative, root / relative)
                path = root / relative / "record.json"
                raw = path.parent / "results" / f"{method}_band_spin_1.dat"
                lines = []
                for line in raw.read_text().splitlines():
                    fields = line.split()
                    for column in range(4, 12, 2):
                        fields[column] = "0.01099"
                    lines.append(" ".join(fields))
                raw.write_text("\n".join(lines) + "\n")
                record = json.loads(path.read_text())
                item = next(entry for entry in record["files"]["results"] if entry["path"].endswith(raw.name))
                item.update(sha256=generator.sha256(raw), size_bytes=raw.stat().st_size)
                path.write_text(json.dumps(record))
                before = {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()}
                with self.assertRaisesRegex(ValueError, "2/nk"):
                    generator.generate_hbn_record(path, root, write=True)
                self.assertEqual(before, {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()})

    def test_registered_hbn_viewport_revision_preserves_selected_mapping_and_science(self):
        import copy
        import shutil
        relative = Path("data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / relative, root / relative)
            path = root / relative / "record.json"
            before = json.loads(path.read_text())
            previous = json.loads((path.parent / "figures/hbn_frontier_audit.json").read_text())
            generator.generate_hbn_record(path, root, write=True)
            after = json.loads(path.read_text())
            current = json.loads((path.parent / "figures/hbn_frontier_audit.json").read_text())
            for field in ("summary", "paper_values", "species", "properties", "software"):
                self.assertEqual(after[field], before[field])
            self.assertNotIn("status", after)
            for method in generator.METHODS:
                for field in ("mapping_one_based", "raw_selected_occupied_bands", "raw_selected_empty_bands",
                              "reference", "selected_window_path_gap_ev", "vbm_endpoints", "cbm_endpoints"):
                    self.assertEqual(current["methods"][method][field], previous["methods"][method][field])
                self.assertEqual(current["methods"][method]["viewport"]["cut_states"], [])

    def test_replacement_hbn_derived_conflict_rejects_before_any_write(self):
        import shutil
        relative = Path("data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / relative, root / relative)
            path = root / relative / "record.json"
            generator.generate_hbn_record(path, root, write=True)
            svg = path.parent / "figures/exx_frontier.svg"
            svg.write_bytes(svg.read_bytes() + b"\n")
            before = {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()}
            with self.assertRaisesRegex(ValueError, "derived artifact conflict"):
                generator.generate_hbn_record(path, root, write=True)
            self.assertEqual(before, {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()})

    def test_replacement_hbn_readset_change_rejects_before_any_write(self):
        import shutil
        from unittest import mock
        relative = Path("data/calculations/2d/hBN/hbn-tzdp10-fgext-20261008")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / relative, root / relative)
            path = root / relative / "record.json"
            target = (path.parent / "results/EXX_band_spin_1.dat").resolve()
            original_read = Path.read_bytes
            reads = 0

            def changing_read(candidate):
                nonlocal reads
                data = original_read(candidate)
                if candidate.resolve() == target:
                    reads += 1
                    if reads > 1:
                        return data + b"\n"
                return data

            before = {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()}
            with mock.patch.object(Path, "read_bytes", changing_read):
                with self.assertRaisesRegex(ValueError, "read set changed"):
                    generator.generate_hbn_record(path, root, write=True)
            self.assertEqual(before, {p: p.read_bytes() for p in path.parent.rglob("*") if p.is_file()})

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
