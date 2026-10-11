"""Regressions for deterministic calculation and basis release indexes."""

import importlib.util
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_indexes.py"


class IndexBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert SCRIPT.exists(), "missing calculation and release index builder"
        sys.path.insert(0, str(SCRIPT.parent))
        spec = importlib.util.spec_from_file_location("build_indexes", SCRIPT)
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_path = "data/calculations/3d/Si/si-control/logs/librpa.out"
        path = self.root / self.log_path
        path.parent.mkdir(parents=True)
        payload = b"GW gap = 1.1 eV\n"
        path.write_bytes(payload)
        self.log = {
            "path": self.log_path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "label": "librpa.out",
        }
        self.case = {"id": "si-control", "files": {"logs": [self.log]}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_log_index_entry_has_one_calculation_id(self):
        result = self.builder.build_log_index(self.root, [self.case])
        self.assertEqual(result["entries"], [{
            "calculation_id": "si-control",
            "path": self.log_path,
            "sha256": self.log["sha256"],
            "label": "librpa.out",
        }])

    def test_duplicate_log_ownership_is_rejected(self):
        other = {"id": "si-second", "files": {"logs": [self.log]}}
        with self.assertRaisesRegex(ValueError, "multiple calculations"):
            self.builder.build_log_index(self.root, [self.case, other])

    def test_unindexed_log_file_is_rejected(self):
        orphan = self.root / "data/calculations/3d/Si/si-control/logs/orphan.out"
        orphan.write_text("unindexed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not indexed"):
            self.builder.build_log_index(self.root, [self.case])

    def test_release_index_contains_only_explicitly_publishable_sets(self):
        sets = [
            {"id": "Si-pending", "element": "Si", "files": [], "publication": {"status": "review"}},
            {"id": "Si-release", "element": "Si", "files": [{"role": "pp", "path": "pp.upf", "sha256": "b" * 64}],
             "publication": {"status": "publishable", "calculation_ids": ["si-control"]}},
        ]
        result = self.builder.build_release_index(sets)
        self.assertEqual([entry["set_id"] for entry in result["sets"]], ["Si-release"])
        self.assertEqual(result["sets"][0]["calculation_ids"], ["si-control"])


if __name__ == "__main__":
    unittest.main()
