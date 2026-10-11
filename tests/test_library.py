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


if __name__ == "__main__":
    unittest.main()
