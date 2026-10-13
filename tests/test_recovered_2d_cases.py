"""Recovered 2D production inputs and exact basis bindings (2026-10-12 import)."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import import_recovered_2d_cases as importer  # noqa: E402
import library  # noqa: E402

CASE_IDS = ["gete-table-gw", "snse-table-gw", "phosphorene-table-gw"]


def load_case(case_id):
    matches = sorted((ROOT / "data/calculations/2d").glob(f"*/{case_id}/record.json"))
    assert len(matches) == 1
    return matches[0].parent, json.loads(matches[0].read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RecoveredCaseImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sets, cls.cases = library.load_records(ROOT)
        library.validate(ROOT, cls.sets, cls.cases)
        cls.by_id = {case["id"]: case for case in cls.cases}
        cls.set_by_id = {item["id"]: item for item in cls.sets}

    def test_prepare_refuses_reimport_after_apply(self):
        with self.assertRaises(ValueError):
            importer.prepare(ROOT)

    def test_verify_readset_rejects_tampering_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.txt"
            path.write_bytes(b"original")
            readset = {}
            importer.read_file(readset, path)
            path.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                importer.verify_readset(readset)
            path.write_bytes(b"original")
            importer.verify_readset(readset)
            path.unlink()
            with self.assertRaises(ValueError):
                importer.verify_readset(readset)

    def test_three_cases_have_only_expected_remaining_issues(self):
        for case_id, expected in importer.EXPECTED_ISSUES.items():
            issues = set(library.completeness_issues(ROOT, self.sets, self.by_id[case_id]))
            self.assertEqual(issues, expected, case_id)

    def test_inputs_are_readable_declared_production_controls(self):
        for case_id in CASE_IDS:
            directory, record = load_case(case_id)
            inputs = record["files"]["inputs"]
            self.assertGreaterEqual(len(inputs), 7, case_id)
            names = {item["path"].split("/")[-1] for item in inputs}
            for required in ("INPUT", "KPT", "STRU", "librpa.in"):
                self.assertTrue(any(name == required or name.startswith(required + "_") for name in names),
                                f"{case_id} missing {required}")
            for item in inputs:
                full = ROOT / item["path"]
                self.assertTrue(full.is_file() and not full.is_symlink(), item["path"])
                self.assertEqual(sha(full), item["sha256"], item["path"])
                self.assertEqual(item["transformation"], "none")
                self.assertTrue(str(full).startswith(str(directory)), item["path"])

    def test_archived_stru_declarations_match_species_aliases(self):
        for case_id in CASE_IDS:
            _, record = load_case(case_id)
            species = {entry["element"]: entry for entry in record["species"]}
            stru_items = [item for item in record["files"]["inputs"] if item["path"].endswith("/STRU")]
            self.assertTrue(stru_items, case_id)
            declared = set()
            for item in stru_items:
                sections = library._stru_sections((ROOT / item["path"]).read_text(encoding="utf-8"))
                rows = [line.split() for line in sections.get("ATOMIC_SPECIES", [])]
                order = [row[0] for row in rows if row]
                self.assertEqual(set(order), set(species), f"{case_id} {item['path']}")
                declarations = {"pp": [row[2] if len(row) > 2 else "" for row in rows]}
                for role, section in (("nao", "NUMERICAL_ORBITAL"), ("abf", "ABFS_ORBITAL")):
                    if section in sections:
                        declarations[role] = [line.split()[0] for line in sections[section]]
                declared.update(declarations)
                for role, names in declarations.items():
                    for element, name in zip(order, names):
                        if role in species[element]["asset_aliases"] and species[element]["asset_aliases"][role]:
                            self.assertEqual(name, species[element]["asset_aliases"][role],
                                             f"{case_id} {element} {role}")
            self.assertIn("nao", declared, case_id)
            self.assertIn("abf", declared, case_id)

    def test_bound_payloads_match_set_files_and_format(self):
        for case_id in CASE_IDS:
            _, record = load_case(case_id)
            for entry in record["species"]:
                basis = self.set_by_id[entry["set_id"]]
                self.assertEqual(basis["element"], entry["element"])
                self.assertEqual(basis["publication"]["status"], "database_only")
                for role in ("pp", "nao", "abf"):
                    files = [item for item in basis["files"] if item.get("role") == role]
                    if role in entry["missing_roles"]:
                        self.assertEqual(files, [], f"{case_id} {entry['element']} {role}")
                        continue
                    self.assertEqual(len(files), 1, f"{case_id} {entry['element']} {role}")
                    item = files[0]
                    self.assertEqual(sha(ROOT / item["path"]), item["sha256"])
                    data = (ROOT / item["path"]).read_bytes()
                    self.assertTrue(library._basis_payload(data, item, entry["element"]),
                                    f"{case_id} {entry['element']} {role}")

    def test_restricted_exx_properties_close_gate_without_ordinary_gap(self):
        for case_id, value in (("gete-table-gw", -1002817.14856), ("snse-table-gw", -1898024.7638299998)):
            _, record = load_case(case_id)
            props = [p for p in record["properties"] if p["key"] == "restricted_raw_band_frontier_path_gap"]
            self.assertEqual(len(props), 1, case_id)
            prop = props[0]
            self.assertEqual(prop["method"], "EXX")
            self.assertEqual(prop["status"], "provisional")
            self.assertEqual(prop["value"], value)
            self.assertEqual(prop["unit"], "eV")
            self.assertIn("Restricted raw-band frontier path gap", prop["definition"])
            evidence = prop["evidence"]
            self.assertEqual(len(evidence), 1)
            declared = {item["path"] for group in record["files"].values() for item in group}
            self.assertIn(evidence[0], declared)
            self.assertIn("EXX_bands.dat", evidence[0])

    def test_scientific_fields_and_existing_evidence_unchanged(self):
        expected = {
            "gete-table-gw": ("gw_diagnostic", 1.3807),
            "snse-table-gw": ("gw_diagnostic", 1.74577),
            "phosphorene-table-gw": ("gw_diagnostic", 1.93526),
        }
        for case_id, (status, gw_value) in expected.items():
            _, record = load_case(case_id)
            self.assertEqual(record["status"], status, case_id)
            gw = [p for p in record["properties"] if p.get("key") == "summary_value"]
            self.assertEqual(gw[0]["value"], gw_value, case_id)
            self.assertEqual(len(record["files"]["figures"]), 6, case_id)
            band_results = [item for item in record["files"]["results"] if "bands" in item["path"]]
            self.assertEqual(len(band_results), 3, case_id)
        _, gete = load_case("gete-table-gw")
        diagnostics = gete["method_diagnostics"][0]
        self.assertEqual(diagnostics["status"], "rejected")
        self.assertEqual(diagnostics["full_raw_path_gap_ev"], -1002817.14856)

    def test_receipts_document_provenance_and_remaining_gaps(self):
        for case_id in CASE_IDS:
            directory, record = load_case(case_id)
            receipt_path = record["source"]["producer_assets_receipt"]
            receipt = json.loads((ROOT / receipt_path).read_text(encoding="utf-8"))
            self.assertEqual(receipt["case_id"], case_id)
            self.assertEqual(len(receipt["inputs"]), len(record["files"]["inputs"]))
            self.assertTrue(receipt["structures"], case_id)
            self.assertTrue(receipt["remaining_gaps"], case_id)
            self.assertTrue(any("ABACUS/LibRPA commits" in gap for gap in receipt["remaining_gaps"]), case_id)
            declared = {item["path"] for item in record["files"]["results"]}
            self.assertIn(receipt_path, declared)


if __name__ == "__main__":
    unittest.main()
