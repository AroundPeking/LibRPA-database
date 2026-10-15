"""缺证导出的原始issue、转义、路径及只读默认回归。"""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("export_missing_evidence", ROOT / "scripts/export_missing_evidence.py")
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class MissingEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data/elements").mkdir(parents=True)
        (self.root / "database").mkdir()
        self.case = {
            "id": "si-history", "dimension": "3d", "material": "Si", "formula": "Si",
            "species": [], "missing": ["Historical binding pending audit"],
            "software": {"abacus": {"commit": None}, "librpa": {"commit": None}},
            "files": {}, "properties": [],
        }
        self._save(self.case)
        self.other = copy.deepcopy(self.case)
        self.other.update({"id": "gete-table-gw", "material": "GeTe", "formula": "GeTe", "dimension": "2d"})
        self._save(self.other)

    def tearDown(self):
        self.tmp.cleanup()

    def _save(self, case):
        directory = self.root / f"data/calculations/{case['dimension']}/{case['material']}/{case['id']}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "record.json").write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")

    def test_fixture_preserves_every_original_issue_and_count_without_waiver(self):
        sets, cases = EXPORT.library.load_records(self.root)
        expected = EXPORT.library.completeness_report(self.root, sets, cases)
        report, export = EXPORT.build_export(self.root)
        self.assertEqual(report, expected)
        self.assertEqual(export["stats"], expected["stats"])
        self.assertEqual(export["status"], "blocked")
        self.assertEqual(export["stats"]["total"], 2)
        self.assertEqual(export["stats"]["incomplete"], 2)
        count = sum(len(case["issues"]) for case in expected["cases"])
        self.assertEqual(export["stats"]["issue_count"], count)
        for raw, enriched in zip(expected["cases"], export["cases"]):
            self.assertEqual(raw["issues"], enriched["issues"])
            self.assertEqual(raw["missing_categories"], enriched["missing_categories"])
        text = EXPORT.render_text(export)
        self.assertEqual(sum(1 for line in text.splitlines() if line.startswith("  [")), count)
        for case in expected["cases"]:
            for issue in case["issues"]:
                self.assertIn(issue, text)
        self.assertEqual(export["supplementary_not_counted_in_strict"], [])

    def test_fixture_lists_exact_inputs_roles_and_software_by_case(self):
        _, export = EXPORT.build_export(self.root)
        record = next(case for case in export["cases"] if case["id"] == "gete-table-gw")
        collection = record["collection"]
        self.assertEqual(collection["missing_inputs"], ["INPUT", "KPT", "STRU", "librpa.in"])
        self.assertEqual(collection["basis_binding_request"]["elements"], [
            {"element": "Ge", "required_roles": ["pp", "nao", "abf"]},
            {"element": "Te", "required_roles": ["pp", "nao", "abf"]},
        ])
        self.assertEqual([request["software"] for request in collection["software_requests"]], ["ABACUS", "LibRPA"])
        self.assertTrue(all(any("SHA-256" in requirement for requirement in request["requirements"])
                            for request in collection["software_requests"]))

    def test_partial_stru_keeps_original_names_and_never_guesses_abf(self):
        import hashlib
        case = copy.deepcopy(self.other)
        case.update({"id": "mose2-table-gw", "material": "MoSe2", "formula": "MoSe2"})
        prefix = "data/calculations/2d/MoSe2/mose2-table-gw/inputs/recovered/control-stage/"
        path = self.root / (prefix + "STRU")
        path.parent.mkdir(parents=True)
        payload = ("ATOMIC_SPECIES\nMo 1 Mo.upf\nSe 1 Se.upf\nNUMERICAL_ORBITAL\n"
                   "Mo.orb\nSe.orb\nATOMIC_POSITIONS\nDirect\nMo\n0\n1\n0 0 0\n").encode()
        path.write_bytes(payload)
        case["files"] = {"inputs": [{"path": prefix + "STRU", "sha256": hashlib.sha256(payload).hexdigest(),
                                     "stage_id": "control-stage", "label": "NSCF / STRU"}]}
        self._save(case)
        _, export = EXPORT.build_export(self.root)
        collection = next(item["collection"] for item in export["cases"] if item["id"] == case["id"])
        binding = collection["basis_binding_request"]
        self.assertFalse(binding["production_stru_declarations"][0]["has_abfs_orbital"])
        self.assertEqual(binding["production_stru_declarations"][0]["elements"][0]["original_names"],
                         {"pp": "Mo.upf", "nao": "Mo.orb", "abf": None})
        self.assertIn("do not guess the ABF", binding["note"])
        requests = {item["software"]: item for item in collection["software_requests"]}
        self.assertEqual(requests["ABACUS"]["stages_to_bind"], ["NSCF [control-stage]"])
        self.assertEqual(requests["LibRPA"]["stages_to_bind"], ["EXX/GW (LibRPA)"])

    def test_dangling_links_and_runtime_seal_remain_outside_strict_count(self):
        import hashlib
        case = copy.deepcopy(self.other)
        case.update({"id": "mos2_ws2-table-gw", "material": "MoS2-WS2", "formula": "MoS2-WS2"})
        prefix = "data/calculations/2d/MoS2-WS2/mos2_ws2-table-gw/results/"
        path = self.root / (prefix + "stage_input_receipt.json")
        path.parent.mkdir(parents=True)
        payload = json.dumps({"full_runtime_handoff_verified": False, "runtime_asset_seal_verified": False,
                              "restrictions": ["405 dangling reader links"]}).encode()
        path.write_bytes(payload)
        case["files"] = {"results": [{"path": prefix + "stage_input_receipt.json",
                                      "sha256": hashlib.sha256(payload).hexdigest()}]}
        self._save(case)
        report, export = EXPORT.build_export(self.root)
        supplementary = export["supplementary_not_counted_in_strict"]
        self.assertEqual([item["kind"] for item in supplementary], ["full_runtime_seal", "dangling_reader_links"])
        self.assertTrue(all(item["counted_in_strict_issues"] is False for item in supplementary))
        self.assertEqual(supplementary[1]["reported_link_count"], 405)
        self.assertEqual(export["stats"], report["stats"])
        self.assertEqual(export["stats"]["issue_count"], sum(len(item["issues"]) for item in export["cases"]))

    def test_generated_html_text_and_json_are_english_without_cjk(self):
        report, export = EXPORT.build_export(self.root)
        output = EXPORT.render_html(export)
        self.assertIn('<html lang="en">', output)
        self.assertIn("Search material / case ID / dimension", output)
        self.assertIn("Showing all 2 records", output)
        self.assertIn("Supplementary items: excluded from strict counts", output)
        for content in (output, EXPORT.render_text(export), json.dumps(export, ensure_ascii=False),
                        json.dumps(report, ensure_ascii=False)):
            with self.subTest(content=content[:80]):
                self.assertNotRegex(content, r"[\u3400-\u9fff\uf900-\ufaff]")

    def test_chinese_display_labels_use_proven_filenames_without_changing_evidence(self):
        import hashlib
        case = copy.deepcopy(self.case)
        prefix = "data/calculations/3d/Si/si-history/inputs/"
        payload = b"INPUT_PARAMETERS\nbasis_type lcao\n"
        path = self.root / (prefix + "INPUT")
        path.parent.mkdir(parents=True)
        path.write_bytes(payload)
        item = {"path": prefix + "INPUT", "sha256": hashlib.sha256(payload).hexdigest(),
                "stage_id": "historical-scf", "label": "SCF / 原始输入"}
        case["files"] = {"inputs": [item]}
        self._save(case)
        record_path = self.root / prefix.rsplit("inputs/", 1)[0] / "record.json"
        before = record_path.read_bytes()
        _, export = EXPORT.build_export(self.root)
        record = next(value for value in export["cases"] if value["id"] == case["id"])
        stage = record["collection"]["existing_stage_controls"][0]
        self.assertEqual(stage["label"], "SCF")
        self.assertEqual(stage["controls"][0], {**item, "label": "SCF / INPUT"})
        self.assertEqual(EXPORT._file_view({**item, "label": "原始输入"})["label"], "INPUT")
        self.assertNotRegex(EXPORT.render_html(export), r"[\u3400-\u9fff\uf900-\ufaff]")
        self.assertNotRegex(json.dumps(export, ensure_ascii=False), r"[\u3400-\u9fff\uf900-\ufaff]")
        self.assertEqual(path.read_bytes(), payload)
        self.assertEqual(record_path.read_bytes(), before)

    def test_html_escapes_issue_material_and_attribute_without_inline_data(self):
        _, export = EXPORT.build_export(self.root)
        malicious = '<img src=x onerror="alert(1)">'
        case = export["cases"][0]
        case["material"] = malicious
        case["id"] = 'case" onclick="alert(1)'
        case["issues"].append("properties: " + malicious)
        export["stats"]["issue_count"] += 1
        output = EXPORT.render_html(export)
        self.assertNotIn(malicious, output)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", output)
        self.assertNotIn('data-search="' + malicious, output)
        self.assertNotIn("innerHTML", output)
        self.assertIn("textContent", output)
        self.assertIn("type=\"search\"", output)

    def test_private_paths_and_nonportable_public_paths_are_rejected(self):
        for value in (
            {"issues": ["evidence /" + "Users/owner/private-run"]},
            {"path": "/opt/private-run/log"},
            {"issues": ["historical source: /mnt/private-run/log"]},
            {"existing_identity_evidence": ["../outside/identity.json"]},
            {"path": "../outside/log"},
            {"source_paths": ["data/ok", "file:" + "//private-run"]},
            {"path": "https://example.invalid/remote.json"},
            {"evidence": ["C:\\private\\run"]},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                EXPORT.assert_public(value)
        EXPORT.assert_public({"record_path": "data/calculations/3d/Si/si-history/record.json",
                              "issues": ["software.abacus.identity: full immutable commit or executable SHA-256 is required"]})

    def test_private_record_is_rejected_before_any_public_write(self):
        self.case["notes"] = "/" + "Users/owner/private"
        self._save(self.case)
        with self.assertRaisesRegex(ValueError, "private path"):
            EXPORT.build_export(self.root)
        self.assertEqual(list((self.root / "database").iterdir()), [])

    def test_render_rejects_tampered_issue_count(self):
        _, export = EXPORT.build_export(self.root)
        export["stats"]["issue_count"] += 1
        with self.assertRaisesRegex(ValueError, "itemized issue count do not match"):
            EXPORT.render_text(export)

    def test_default_cli_and_output_directory_are_read_only_until_write(self):
        output = self.root / "outputs"
        result = subprocess.run([sys.executable, str(ROOT / "scripts/export_missing_evidence.py"),
                                 "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("original issues in total", result.stdout)
        rejected = subprocess.run([sys.executable, str(ROOT / "scripts/export_missing_evidence.py"),
                                   "--root", str(self.root), "--output-dir", "outputs"],
                                  capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse(output.exists())
        self.assertEqual(list((self.root / "database").iterdir()), [])
        output.mkdir()
        written = subprocess.run([sys.executable, str(ROOT / "scripts/export_missing_evidence.py"),
                                  "--root", str(self.root), "--write", "--output-dir", "outputs"],
                                 capture_output=True, text=True)
        self.assertEqual(written.returncode, 0, written.stderr)
        self.assertEqual(len(list(output.iterdir())), 4)
        raw = json.loads((self.root / "database/archive-completeness.json").read_text())
        enriched = json.loads((output / "missing-evidence.json").read_text())
        self.assertEqual(raw["stats"], enriched["stats"])
        self.assertEqual(raw["status"], "blocked")
        self.assertNotIn(str(self.root), (output / "missing-evidence.json").read_text())

    def test_report_output_only_writes_requested_raw_report_and_rejects_public_target(self):
        command = [sys.executable, str(ROOT / "scripts/export_missing_evidence.py"), "--root", str(self.root)]
        output = self.root.resolve() / "requested-report.json"
        result = subprocess.run(command + ["--report-output", str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected, _ = EXPORT.build_export(self.root)
        self.assertEqual(json.loads(output.read_text()), expected)
        self.assertIn("report written", result.stdout)
        self.assertNotRegex(result.stdout, r"[\u3400-\u9fff\uf900-\ufaff]")
        self.assertEqual(list((self.root / "database").iterdir()), [])
        for filename in ("archive-completeness.json", "missing-evidence.html"):
            with self.subTest(filename=filename):
                rejected = subprocess.run(command + ["--report-output", str(self.root / "database" / filename)],
                                          capture_output=True, text=True)
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn("report-output must not replace a public check target", rejected.stdout)
                self.assertEqual(list((self.root / "database").iterdir()), [])

    def test_check_detects_stale_reports_and_symlink_target_is_rejected(self):
        command = [sys.executable, str(ROOT / "scripts/export_missing_evidence.py"), "--root", str(self.root)]
        written = subprocess.run(command + ["--write"], capture_output=True, text=True)
        self.assertEqual(written.returncode, 0, written.stderr)
        checked = subprocess.run(command + ["--check"], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        target = self.root / "database/archive-completeness.json"
        target.write_text("{}\n")
        stale = subprocess.run(command + ["--check"], capture_output=True, text=True)
        self.assertNotEqual(stale.returncode, 0)
        symlink = self.root / "output-link"
        symlink.symlink_to(self.root / "database", target_is_directory=True)
        before = target.read_bytes()
        rejected = subprocess.run(command + ["--write", "--output-dir", str(symlink)], capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(target.read_bytes(), before)

    def test_missing_output_parent_causes_no_partial_write(self):
        for path in ("missing-parent/nested", str(self.root.parent / "outside-report-missing-parent" / "nested")):
            with self.subTest(path=path):
                result = subprocess.run([sys.executable, str(ROOT / "scripts/export_missing_evidence.py"),
                                         "--root", str(self.root), "--write", "--output-dir", path],
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(list((self.root / "database").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
