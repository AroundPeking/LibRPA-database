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


class TableEvidenceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.root = base / "repo"
        self.source = base / "project/inputs/paper_materials"
        self.raw = base / "raw"
        self.raw.mkdir()
        self.relative = "data/calculations/2d/Test/test-table-gw"
        self.record_path = self.root / self.relative / "record.json"
        self.record_path.parent.mkdir(parents=True)
        self.source_path = self.source / "test/provenance/table_band_source.json"
        self.source_path.parent.mkdir(parents=True)
        self.native = [[0, 0, 0], [0.5, 0, 0]]
        self.methods = {}
        results, figures, outputs = [], [], {}
        for method, gap in (("KS", 2), ("EXX", 4), ("GW", 3)):
            data = f"1 0 0 0 1 -2 1 -1 0 {gap - 1} 0 {gap + 1}\n2 0.5 0 0 1 -3 1 -2 0 {gap} 0 {gap + 2}\n".encode()
            raw_path = self.raw / f"{method}_band_spin_1.dat"
            raw_path.write_bytes(data)
            path = f"{self.relative}/results/{method}_bands.dat"
            self._write_repo(path, data)
            results.append(self._item(path, data))
            self.methods[method] = {"occupied_states": 2, "raw_band_count": 4, "npoints": 2,
                                    "frozen_raw_window_one_based": [2, 3], "path_gap_ev": gap,
                                    "source": {"original_path": str(raw_path), "sha256": MIGRATOR._digest(data), "shape": [2, 4]}}
            outputs[method] = {}
            for extension in ("png", "pdf"):
                name = f"test_{method.lower()}.{extension}"
                data = f"original figure {name}".encode()
                path = f"{self.relative}/figures/{name}"
                self._write_repo(path, data)
                figures.append(self._item(path, data))
                outputs[method][extension] = f"figures/table_material_bands/{name}"
                original = self.source.parents[1] / outputs[method][extension]
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(data)
        self.provenance = {"native_kpath_fractional": self.native, "methods": self.methods, "figure_outputs": outputs}
        self.source_path.write_text(json.dumps(self.provenance), encoding="utf-8")
        digest = MIGRATOR._digest(self.source_path.read_bytes())
        self.sidecar_relative = f"{self.relative}/results/band_window_and_provenance.json"
        self._write_repo(self.sidecar_relative, self.source_path.read_bytes())
        sidecar_item = self._item(self.sidecar_relative, self.source_path.read_bytes())
        sidecar_item["original_sha256"] = digest
        results.append(sidecar_item)
        self.record = {"id": "test-table-gw", "dimension": "2d", "status": "gw_diagnostic",
                       "summary": {"value": 789, "unit": "eV"}, "source": {"original_sidecar_sha256": digest},
                       "properties": [{"key": "manual", "category": "optical", "method": "handwritten", "value": 456}],
                       "files": {"inputs": [], "results": results, "figures": figures, "logs": []}}
        self._save_record()
        self.original_repo = self._snapshot(self.root)
        self.original_source = self._snapshot(self.source.parents[1])
        self.original_raw = self._snapshot(self.raw)

    def _write_repo(self, path, data):
        full = self.root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)

    @staticmethod
    def _item(path, data):
        return {"path": path, "sha256": MIGRATOR._digest(data), "original_sha256": MIGRATOR._digest(data), "size_bytes": len(data)}

    @staticmethod
    def _snapshot(root):
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def _save_record(self):
        self.record_path.write_text(json.dumps(self.record), encoding="utf-8")

    def _rebind(self):
        self.source_path.write_text(json.dumps(self.provenance), encoding="utf-8")
        digest = MIGRATOR._digest(self.source_path.read_bytes())
        self.record["source"]["original_sidecar_sha256"] = digest
        self._write_repo(self.sidecar_relative, self.source_path.read_bytes())
        item = next(item for item in self.record["files"]["results"] if item["path"] == self.sidecar_relative)
        item.update(self._item(self.sidecar_relative, self.source_path.read_bytes()))
        self._save_record()

    def test_dry_run_no_mutation_then_atomic_write_and_idempotence(self):
        stats = MIGRATOR.recover_table_evidence(self.root, self.source)
        self.assertEqual(stats["properties_added"], 2)
        self.assertEqual(stats["figure_links_added"], 6)
        self.assertEqual(self.original_repo, self._snapshot(self.root))
        MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        first = self._snapshot(self.root)
        stats = MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        self.assertEqual(stats["records_changed"], 0)
        self.assertEqual(first, self._snapshot(self.root))
        self.assertEqual(self.original_source, self._snapshot(self.source.parents[1]))
        self.assertEqual(self.original_raw, self._snapshot(self.raw))
        for path, data in self.original_repo.items():
            if path != self.record_path.relative_to(self.root).as_posix():
                self.assertEqual(first[path], data)
        record = json.loads(self.record_path.read_bytes())
        self.assertEqual(record["properties"][0], self.record["properties"][0])
        self.assertEqual(record["summary"], self.record["summary"])
        self.assertEqual(record["status"], self.record["status"])
        for figure in record["files"]["figures"]:
            self.assertEqual(len(figure["source_paths"]), 2)
            self.assertIn(figure["method"], ("KS", "EXX", "GW"))

    def test_existing_manual_gap_alias_is_preserved_not_duplicated(self):
        for method in ("PBE", "DFT", "KS"):
            with self.subTest(method=method):
                prop = {"key": "band_gap", "method": method, "value": 999, "status": "validated", "evidence": ["manual"]}
                self.record["properties"] = [self.record["properties"][0], prop]
                updated, stats = MIGRATOR.recover_table_record(self.root, self.source, self.source_path, self.record)
                self.assertEqual(stats["properties_added"], 1)
                self.assertEqual(updated["properties"][1], prop)
                self.assertFalse(any(item.get("key") == "sampled_path_gap_ev" and item.get("method") == "PBE" for item in updated["properties"]))

    def test_owned_sampled_value_or_unit_conflict_blocks_without_mutation(self):
        for value, unit in ((999, "eV"), (2, "Ha")):
            with self.subTest(value=value, unit=unit):
                self.record["properties"] = [{"key": "sampled_path_gap_ev", "method": "PBE", "value": value,
                                              "unit": unit, "source_sidecar_key": "methods.KS.path_gap_ev"}]
                self._save_record()
                before = self._snapshot(self.root)
                with self.assertRaisesRegex(ValueError, "数值/单位冲突"):
                    MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
                self.assertEqual(before, self._snapshot(self.root))

    def test_owned_matching_sampled_property_is_unchanged(self):
        prop = {"key": "sampled_path_gap_ev", "method": "PBE", "value": 2, "unit": "eV",
                "status": "reported", "source_sidecar_key": "methods.KS.path_gap_ev", "evidence": ["manual"]}
        self.record["properties"].append(prop)
        updated, stats = MIGRATOR.recover_table_record(self.root, self.source, self.source_path, self.record)
        self.assertEqual(stats["properties_added"], 1)
        self.assertEqual(updated["properties"][1], prop)

    def _npz_source(self):
        original = self.raw / "pbe_bands.npz"
        original.write_bytes(b"independent original NPZ identity")
        archive = "results/table_material_bands/raw/test_KS.dat"
        table = (self.raw / "KS_band_spin_1.dat").read_bytes()
        converted = self.source.parents[1] / archive
        converted.parent.mkdir(parents=True, exist_ok=True)
        converted.write_bytes(table)
        self.methods["KS"]["source"].update({"original_path": str(original), "archive_path": archive, "format": "dat"})
        self._rebind()
        return original, converted

    def test_npz_identity_and_archived_dat_hash_are_separate_and_idempotent(self):
        original, converted = self._npz_source()
        before = self._snapshot(self.source.parents[1])
        MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        saved = json.loads(self.record_path.read_bytes())
        spectrum = next(item for item in saved["files"]["results"] if item["path"].endswith("/KS_bands.dat"))
        identity = spectrum["source_identity"]
        self.assertEqual(identity["source_format"], "archived_dat_converted_from_npz")
        self.assertEqual(identity["production_source_sha256"], MIGRATOR._digest(original.read_bytes()))
        self.assertEqual(identity["archived_table_sha256"], MIGRATOR._digest(converted.read_bytes()))
        self.assertNotEqual(identity["production_source_sha256"], identity["archived_table_sha256"])
        self.assertFalse(identity["conversion_independently_verified"])
        self.assertNotIn(str(self.raw), json.dumps(saved))
        self.assertIn("conversion not independently verified", saved["properties"][1]["definition"])
        first = self._snapshot(self.root)
        self.assertEqual(MIGRATOR.recover_table_evidence(self.root, self.source, write=True)["records_changed"], 0)
        self.assertEqual(first, self._snapshot(self.root))
        self.assertEqual(before, self._snapshot(self.source.parents[1]))

    def test_npz_archived_dat_tampering_rejected(self):
        _, converted = self._npz_source()
        converted.write_bytes(b"wrong converted DAT")
        before = self._snapshot(self.root)
        with self.assertRaisesRegex(ValueError, "hash不匹配"):
            MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        self.assertEqual(before, self._snapshot(self.root))

    def test_npz_without_archived_dat_contract_is_rejected(self):
        self._npz_source()
        self.methods["KS"]["source"].pop("archive_path")
        self._rebind()
        with self.assertRaisesRegex(ValueError, "转换DAT合同"):
            MIGRATOR.recover_table_evidence(self.root, self.source, write=True)

    def test_bad_raw_hash_stops_all_records_without_mutation(self):
        (self.raw / "EXX_band_spin_1.dat").write_bytes(b"bad raw hash")
        with self.assertRaisesRegex(ValueError, "hash不匹配"):
            MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        self.assertEqual(self.original_repo, self._snapshot(self.root))

    def test_later_bad_source_prevents_earlier_record_writes(self):
        other = self.source / "zzz/provenance/table_band_source.json"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "未匹配"):
            MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        self.assertEqual(self.original_repo, self._snapshot(self.root))

    def test_bad_source_hash_and_bad_figure_hash_rejected(self):
        self.source_path.write_bytes(self.source_path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "未匹配"):
            MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        self.assertEqual(self.original_repo, self._snapshot(self.root))
        self.source_path.write_text(json.dumps(self.provenance), encoding="utf-8")
        original = self.source.parents[1] / self.provenance["figure_outputs"]["GW"]["png"]
        original.write_bytes(b"wrong original figure")
        with self.assertRaisesRegex(ValueError, "原图字节/hash"):
            MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        self.assertEqual(self.original_repo, self._snapshot(self.root))

    def test_negative_raw_and_selected_mismatch_is_explicit_blocked_diagnostic(self):
        method = self.methods["EXX"]
        data = b"1 0 0 0 1 -2 1 -1 0 -71 0 -1000001\n2 0.5 0 0 1 -3 1 -2 0 -70 0 1\n"
        raw = self.raw / "EXX_band_spin_1.dat"
        raw.write_bytes(data)
        path = f"{self.relative}/results/EXX_bands.dat"
        self._write_repo(path, data)
        item = next(item for item in self.record["files"]["results"] if item["path"] == path)
        item.update(self._item(path, data))
        method["source"]["sha256"] = MIGRATOR._digest(data)
        method["path_gap_ev"] = -70
        self._rebind()
        stats = MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        self.assertEqual(stats["diagnostics"], 1)
        self.assertEqual(stats["properties_added"], 1)
        record = json.loads(self.record_path.read_bytes())
        self.assertIsInstance(record["method_diagnostics"], list)
        diagnostic = record["method_diagnostics"][0]
        self.assertEqual(diagnostic["method"], "EXX")
        self.assertEqual(diagnostic["full_raw_path_gap_ev"], -1000000)
        self.assertEqual(diagnostic["selected_window_path_gap_ev"], -70)
        self.assertEqual(diagnostic["frozen_window_path_gap_ev"], -70)
        self.assertEqual(diagnostic["status"], "rejected")
        self.assertFalse(any(prop.get("method") == "EXX" for prop in record["properties"]))
        self.assertEqual(record["status"], "gw_diagnostic")
        self.assertTrue(all(figure["scientific_status"] == "archived_diagnostic" for figure in record["files"]["figures"] if figure["method"] == "EXX"))
        self.assertEqual(MIGRATOR.recover_table_evidence(self.root, self.source, write=True)["records_changed"], 0)

    def test_selected_gap_mismatch_blocks_positive_raw(self):
        method = self.methods["EXX"]
        method["path_gap_ev"] = -1
        self._rebind()
        before = self._snapshot(self.root)
        with self.assertRaisesRegex(ValueError, "选窗不匹配"):
            MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        self.assertEqual(before, self._snapshot(self.root))

    def test_anomalous_negative_raw_preserves_sidecar_disagreement(self):
        data = b"1 0 0 0 1 -2 1 -1 0 -71 0 -1000001\n2 0.5 0 0 1 -3 1 -2 0 -70 0 1\n"
        path = f"{self.relative}/results/EXX_bands.dat"
        (self.raw / "EXX_band_spin_1.dat").write_bytes(data)
        self._write_repo(path, data)
        next(item for item in self.record["files"]["results"] if item["path"] == path).update(self._item(path, data))
        self.methods["EXX"]["source"]["sha256"] = MIGRATOR._digest(data)
        self.methods["EXX"]["path_gap_ev"] = -20
        self._rebind()
        updated, stats = MIGRATOR.recover_table_record(self.root, self.source, self.source_path, self.record)
        self.assertEqual(stats["diagnostics"], 1)
        diagnostic = updated["method_diagnostics"][0]
        self.assertEqual(diagnostic["frozen_window_path_gap_ev"], -70)
        self.assertEqual(diagnostic["sidecar_path_gap_ev"], -20)
        self.assertFalse(diagnostic["sidecar_selected_window_matches"])
        self.assertIn("differs", diagnostic["message"])
        self.assertFalse(any(item.get("method") == "EXX" for item in updated["properties"]))

    def test_positive_full_gap_mismatch_is_not_silently_accepted(self):
        data = b"1 0 0 0 1 -2 1 -1 0 3 0 0\n2 0.5 0 0 1 -3 1 -2 0 4 0 1\n"
        raw = self.raw / "EXX_band_spin_1.dat"
        raw.write_bytes(data)
        path = f"{self.relative}/results/EXX_bands.dat"
        self._write_repo(path, data)
        next(item for item in self.record["files"]["results"] if item["path"] == path).update(self._item(path, data))
        self.methods["EXX"]["source"]["sha256"] = MIGRATOR._digest(data)
        self._rebind()
        before = self._snapshot(self.root)
        with self.assertRaisesRegex(ValueError, "正全谱gap"):
            MIGRATOR.recover_table_evidence(self.root, self.source, write=True)
        self.assertEqual(before, self._snapshot(self.root))

    def test_native_xyz_and_occupation_boundary_must_be_verified(self):
        metrics = self.methods["KS"]
        data = (self.raw / "KS_band_spin_1.dat").read_bytes()
        with self.assertRaisesRegex(ValueError, "xyz路径"):
            MIGRATOR._native_table(data, metrics, [[0, 0, 0], [0.6, 0, 0]])
        with self.assertRaisesRegex(ValueError, "occupied/零empty"):
            MIGRATOR._native_table(data.replace(b"1 -1 0 1", b"1 -1 1 1"), metrics, self.native)
        with self.assertRaisesRegex(ValueError, "固定正值"):
            MIGRATOR._native_table(data.replace(b"1 -2 1 -1", b"2 -2 1 -1"), metrics, self.native)


if __name__ == "__main__":
    unittest.main()
