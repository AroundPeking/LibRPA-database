"""Migrations from legacy gap summaries to evidence-linked properties."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/migrate_properties.py"
SPEC = importlib.util.spec_from_file_location("migrate_properties", SCRIPT)
MIGRATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATOR)


class PropertyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "id": "si-test",
            "status": "gw_diagnostic",
            "summary": {
                "observable": "G0W0 gap",
                "value": 1.4,
                "unit": "eV",
                "dft_gap_ev": 0.6,
                "exx_gap_ev": 5.0,
                "gw_gap_ev": 1.4,
            },
            "files": {"results": [
                {"path": "data/si-test-gw/KS_bands.dat", "label": "KS_bands.dat"},
                {"path": "data/si-test-gw/EXX_bands.dat", "label": "EXX_bands.dat"},
                {"path": "data/si-test-gw/GW_bands.dat", "label": "GW_bands.dat"},
            ]},
        }

    def test_maps_legacy_gaps_to_matching_result_evidence(self):
        migrated = MIGRATOR.migrate_record(self.record)
        rows = {item["method"]: item for item in migrated["properties"]}
        self.assertEqual(set(rows), {"PBE", "EXX", "G0W0"})
        self.assertEqual(rows["PBE"]["value"], 0.6)
        self.assertEqual(rows["PBE"]["source_summary_key"], "dft_gap_ev")
        self.assertEqual(rows["EXX"]["evidence"], ["data/si-test-gw/EXX_bands.dat"])
        self.assertEqual(rows["G0W0"]["evidence"], ["data/si-test-gw/GW_bands.dat"])
        self.assertEqual(rows["G0W0"]["source_summary_key"], "gw_gap_ev")
        self.assertEqual(rows["G0W0"]["status"], "reported")

    def test_archived_path_gap_uses_path_method(self):
        self.record["summary"]["observable"] = "Archived GW path gap"
        migrated = MIGRATOR.migrate_record(self.record)
        self.assertIn("GW path", {item["method"] for item in migrated["properties"]})

    def test_maps_legacy_pbe_gap_field(self):
        self.record["summary"].pop("dft_gap_ev")
        self.record["summary"]["pbe_gap_ev"] = 0.7
        migrated = MIGRATOR.migrate_record(self.record)
        pbe = next(item for item in migrated["properties"] if item["method"] == "PBE")
        self.assertEqual(pbe["value"], 0.7)
        self.assertEqual(pbe["evidence"], ["data/si-test-gw/KS_bands.dat"])

    def test_summary_value_does_not_duplicate_equal_gw_gap_and_migration_is_idempotent(self):
        first = MIGRATOR.migrate_record(self.record)
        second = MIGRATOR.migrate_record(first)
        self.assertEqual(first["properties"], second["properties"])
        self.assertEqual(sum(item["method"] == "G0W0" for item in first["properties"]), 1)
        self.assertEqual(first["summary"], self.record["summary"])

    def test_refreshes_imported_property_without_legacy_summary_description(self):
        first = MIGRATOR.migrate_record(self.record)
        gw = next(item for item in first["properties"] if item["method"] == "G0W0")
        gw["evidence"] = ["data/si-test-gw/EXX_bands.dat"]
        gw["definition"] = self.record["summary"]["observable"]
        second = MIGRATOR.migrate_record(first)
        refreshed = next(item for item in second["properties"] if item["method"] == "G0W0")
        self.assertNotIn("definition", refreshed)
        self.assertEqual(refreshed["evidence"], ["data/si-test-gw/GW_bands.dat"])

    def test_unmarked_contributed_row_is_never_claimed_by_value_match(self):
        first = MIGRATOR.migrate_record(self.record)
        gw = next(item for item in first["properties"] if item["method"] == "G0W0")
        gw.pop("source_summary_key")
        gw["evidence"] = ["data/si-test-gw/EXX_bands.dat"]
        gw.pop("definition", None)
        second = MIGRATOR.migrate_record(first)
        refreshed = next(item for item in second["properties"] if item["method"] == "G0W0")
        self.assertEqual(refreshed["evidence"], ["data/si-test-gw/EXX_bands.dat"])
        self.assertNotIn("source_summary_key", refreshed)

    def test_reviewed_status_is_not_reset_by_migration(self):
        for status in ("failed", "validated", "provisional"):
            first = MIGRATOR.migrate_record(self.record)
            gw = next(item for item in first["properties"] if item["method"] == "G0W0")
            gw["status"] = status
            gw["definition"] = "Reviewed definition"
            second = MIGRATOR.migrate_record(first)
            refreshed = next(item for item in second["properties"] if item["method"] == "G0W0")
            self.assertEqual(refreshed, gw)

    def test_root_migration_previews_then_writes_idempotently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record_path = root / "data/calculations/3d/Si/si-test/record.json"
            record_path.parent.mkdir(parents=True)
            record_path.write_text(json.dumps(self.record), encoding="utf-8")
            before = record_path.read_bytes()
            self.assertEqual(MIGRATOR.migrate(root, write=False), 1)
            self.assertEqual(record_path.read_bytes(), before)
            self.assertEqual(MIGRATOR.migrate(root, write=True), 1)
            saved = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["properties"][0]["source_summary_key"], "dft_gap_ev")
            self.assertEqual(MIGRATOR.migrate(root, write=False), 0)

    def test_non_gw_summary_is_not_invented_as_an_electronic_property(self):
        self.record["summary"] = {"observable": "RPA correlation energy", "value": -2.0, "unit": "Ha"}
        migrated = MIGRATOR.migrate_record(self.record)
        self.assertEqual(migrated["properties"], [])
        self.assertEqual(migrated["summary"], self.record["summary"])

    def test_distinct_summary_value_is_preserved_as_its_own_property(self):
        self.record["summary"]["value"] = 1.5
        migrated = MIGRATOR.migrate_record(self.record)
        rows = [item for item in migrated["properties"] if item["method"] == "G0W0"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(item["key"] == "summary_value" and item["value"] == 1.5 for item in rows))


if __name__ == "__main__":
    unittest.main()
