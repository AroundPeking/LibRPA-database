"""Integrity regressions for contributed scientific records."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = ROOT / "scripts/library.py"
        assert script.exists(), "missing library integrity validator"
        spec = importlib.util.spec_from_file_location("library", script)
        cls.lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.lib)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        path = self.root / "elements/Si/pseudopotentials/test.upf"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"scientific payload\n")
        self.file = {"path": path.relative_to(self.root).as_posix(),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "role": "pp"}
        self.set = {"id": "Si-test", "element": "Si", "files": [self.file]}
        self.case = {"id": "si-control", "dimension": "3d", "material": "Si",
                     "status": "path_diagnostic", "species": [{"element": "Si", "set_id": "Si-test"}],
                     "software": {"abacus": {"commit": None}, "librpa": {"commit": None}},
                     "files": {}, "recommendation": None}

    def tearDown(self):
        self.tmp.cleanup()

    def test_unknown_commits_are_explicitly_allowed(self):
        self.lib.validate(self.root, [self.set], [self.case])

    def test_contextual_basis_candidate_must_exist_and_have_scope(self):
        self.case["basis_candidates"] = [{"element": "Si", "set_id": "Si-test", "scope": "contextual"}]
        self.lib.validate(self.root, [self.set], [self.case])
        self.case["basis_candidates"][0]["set_id"] = "C-missing"
        with self.assertRaisesRegex(ValueError, "unknown candidate"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_unlinked_historical_case_requires_missing_evidence(self):
        self.case["species"] = []
        self.case["missing"] = ["exact production basis binding pending"]
        self.lib.validate(self.root, [self.set], [self.case])
        self.case["missing"] = []
        with self.assertRaisesRegex(ValueError, "empty species"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_changed_scientific_payload_is_rejected(self):
        (self.root / self.file["path"]).write_bytes(b"wrong pseudopotential")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_cross_element_pairing_is_rejected(self):
        self.case["species"][0]["element"] = "C"
        with self.assertRaisesRegex(ValueError, "element"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_path_escape_is_rejected(self):
        self.file["path"] = "../outside.upf"
        with self.assertRaisesRegex(ValueError, "portable"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_unproven_recommendation_is_rejected(self):
        self.case["recommendation"] = {"scope": "all GW", "evidence": []}
        with self.assertRaisesRegex(ValueError, "recommendation"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_short_commit_is_rejected(self):
        self.case["software"]["abacus"]["commit"] = "123abcd"
        with self.assertRaisesRegex(ValueError, "commit"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_local_absolute_paths_are_rejected_from_public_records(self):
        self.case["notes"] = "source was /" + "Users/private/run"
        with self.assertRaisesRegex(ValueError, "private path"):
            self.lib.validate(self.root, [self.set], [self.case])

    def _make_publishable(self):
        self.set["files"] = [
            self.file,
            self._add_file("elements/Si/orbitals/test.orb", b"physical nao\n", "nao"),
            self._add_file("elements/Si/auxiliary/test.abfs", b"auxiliary basis\n", "abf"),
        ]
        self.set["source"] = {
            "url": "https://example.org/si-basis",
            "license": "CC0-1.0",
            "redistribution": "permitted",
        }
        self.set["publication"] = {
            "status": "publishable",
            "calculation_ids": ["si-control"],
        }
        self.case["status"] = "gw_validated"
        self.case["software"] = {
            "abacus": {"commit": "a" * 40},
            "librpa": {"commit": "b" * 40},
        }
        self.case["files"] = {
            "inputs": [self._add_file("calculations/si/INPUT", b"input\n", "inputs")],
            "results": [self._add_file("calculations/si/GW_band.dat", b"bands\n", "results")],
        }
        self.case["publication"] = {
            "status": "publishable",
            "basis_set_ids": ["Si-test"],
        }

    def _add_file(self, relative_path, contents, role):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return {
            "path": path.relative_to(self.root).as_posix(),
            "sha256": hashlib.sha256(contents).hexdigest(),
            "role": role,
        }

    def test_complete_publishable_case_and_basis_are_accepted(self):
        self._make_publishable()
        self.lib.validate(self.root, [self.set], [self.case])

    def test_publishable_case_requires_exact_full_commits(self):
        self._make_publishable()
        self.case["software"]["librpa"]["commit"] = None
        with self.assertRaisesRegex(ValueError, "publishable.*full.*commit"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_publishable_case_requires_inputs_and_final_results(self):
        self._make_publishable()
        self.case["files"]["inputs"] = []
        with self.assertRaisesRegex(ValueError, "publishable.*input"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_publishable_case_rejects_intermediate_files(self):
        self._make_publishable()
        self.case["files"]["results"].append(
            self._add_file("calculations/si/restart/WFC_restart.wfc", b"scratch\n", "results")
        )
        with self.assertRaisesRegex(ValueError, "intermediate"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_publishable_basis_requires_explicit_redistribution_terms(self):
        self._make_publishable()
        self.set["source"]["redistribution"] = "unknown"
        with self.assertRaisesRegex(ValueError, "redistribution"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_publishable_case_requires_gw_validation_and_linked_sets(self):
        self._make_publishable()
        self.case["status"] = "gw_diagnostic"
        with self.assertRaisesRegex(ValueError, "gw_validated"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_generated_catalog_check_detects_stale_output(self):
        catalog = {"schema_version": 1, "basis_sets": [], "calculations": []}
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            self.lib.sync_catalog(self.root, catalog, write=False)
        self.lib.sync_catalog(self.root, catalog, write=True)
        self.lib.sync_catalog(self.root, catalog, write=False)
        (self.root / "database/data.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            self.lib.sync_catalog(self.root, catalog, write=False)


if __name__ == "__main__":
    unittest.main()
