"""Migrations from legacy gap summaries to evidence-linked properties."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

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


class PaperValueImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "repo"
        self.audit_path = self.base / "private-audit.json"
        self.documents = []
        sources = {}
        for dimension in ("3d", "2d"):
            document = self.base / f"private-paper-{dimension}.pdf"
            document.write_bytes(f"已核验论文PDF {dimension}".encode())
            self.documents.append(document)
            sources[f"paper_{dimension}"] = {
                "path": str(document), "sha256": MIGRATOR._digest(document.read_bytes()),
                "title": f"Test {dimension} paper", "text_path": str(self.base / "private-paper.txt"),
                "main_pbe_column": "PBE / ABACUS" if dimension == "3d" else "Eg(PBE)",
                "main_gw_column": "G0W0@PBE / ABACUS+LibRPA" if dimension == "3d" else "Eg(G0W0)",
                "reported_decimal_places": 3, "doi": "10.test/3d-only",
                "method_and_basis": {"hbn_main_table": "10-au 3s3p2d、1f1g-extended ABF、无empty atoms；PBE valley ordering错误、高态侵入、raw-band-5 path diagnostic，非完整谱基本带隙。"},
            }
        rows_3d = [{"material": formula, "pbe_abacus_ev": 1.234, "gw_abacus_librpa_ev": 2.345,
                    "pbe_fhi_aims_ev": 9.111, "gw_fhi_aims_ev": 9.222, "exx_ev": None,
                    "source_line": 1096 + index, "private_path": str(self.base / "private-source.pdf")}
                   for index, formula in enumerate(("AlAs", "AlP", "AlSb", "BAs", "BN", "BP", "C", "Si", "SiC",
                                                    "GaAs", "GaN", "GaP", "MgO", "NaCl", "CdS", "CaO", "LiF"))]
        formulas_2d = ("MoS2", "MoSe2", "WS2", "WSe2", "h-BN", "phosphorene", "MoS2/WS2", "GeTe", "SnSe",
                       "MoTe2", "InSe", "In2Se3", "GaTe", "TiS3", "CuInP2Se6")
        rows_2d = []
        self.paths = {}
        self.originals = {}
        for index, formula in enumerate(formulas_2d):
            case_id = ("hbn-tzdp10-fgext-20261008" if formula == "h-BN" else
                       formula.lower().replace("/", "_") + "-table-gw")
            rows_2d.append({"material": formula, "database_case_id": case_id, "pbe_ev": 1.23456,
                            "gw_ev": 2.345 if index in (1, 2, 3) else 2.34567,
                            "pbe_precision": 5, "gw_precision": 3 if index in (1, 2, 3) else 5,
                            "exx_ev": None, "path": "K–Γ path", "source_line": index + 930,
                            "tex_line": index + 1239, "scope_note": "rejected diagnostic" if formula in ("GaTe", "TiS3") else "near-gap path，不是全谱验收",
                            "footnote_source_lines": str(self.base / "private-footnote"), "local_path": str(self.base / "private-source")})
        self.audit = {"schema_version": 1, "sources": sources, "values_3d_table_iv": rows_3d,
                      "values_2d_table_i": rows_2d, "explicit_2d_exx_values": {"exx_gap_ev": 6.25292}}
        for dimension, rows in (("3d", rows_3d), ("2d", rows_2d)):
            for row in rows:
                formula = MIGRATOR._paper_formula(row["material"])
                case_id = row.get("database_case_id", formula.lower() + "-paper-test")
                self._add_record(dimension, formula, case_id)
        self._add_record("2d", "hBN", "hbn-table-gw")
        self._save_audit()
        self.original_repo = self._snapshot(self.root)
        self.original_inputs = self._snapshot(self.base)

    def _add_record(self, dimension, formula, case_id):
        relative = f"data/calculations/{dimension}/{formula}/{case_id}"
        path = self.root / relative / "record.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        spectrum = path.parent / "results/EXX_bands.dat"
        spectrum.parent.mkdir(exist_ok=True)
        spectrum.write_bytes(b"original archived spectrum\n")
        record = {"schema_version": 1, "id": case_id, "dimension": dimension, "material": formula, "formula": formula,
                  "status": "gw_diagnostic", "summary": {"value": 999, "unit": "eV"}, "notes": "人工审阅备注",
                  "properties": [{"key": "band_gap", "method": "PBE", "value": 777, "evidence": ["manual"]}],
                  "files": {"results": [{"role": "results", "path": f"{relative}/results/EXX_bands.dat",
                                         "sha256": MIGRATOR._digest(spectrum.read_bytes()), "size_bytes": spectrum.stat().st_size,
                                         "label": "EXX_bands.dat", "manual_metadata": "保留"}], "inputs": [], "logs": [], "figures": []}}
        path.write_text(json.dumps(record), encoding="utf-8")
        self.paths[case_id] = path
        self.originals[case_id] = record
        return path

    @staticmethod
    def _snapshot(root):
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def _save_audit(self):
        self.audit_path.write_text(json.dumps(self.audit), encoding="utf-8")

    def _assert_blocked(self, pattern):
        before = self._snapshot(self.root)
        with self.assertRaisesRegex(ValueError, pattern):
            MIGRATOR.import_paper_values(self.root, self.audit_path, write=True)
        self.assertEqual(before, self._snapshot(self.root))

    def test_dryrun_then_second_write_byte_idempotence_no_summary_or_spectrum_mutation(self):
        stats = MIGRATOR.import_paper_values(self.root, self.audit_path)
        self.assertEqual(stats["records_verified"], 32)
        self.assertEqual(stats["records_changed"], 32)
        self.assertEqual(stats["paper_values_added"], 32)
        self.assertEqual(stats["evidence_added"], 32)
        self.assertEqual(self.original_repo, self._snapshot(self.root))
        MIGRATOR.import_paper_values(self.root, self.audit_path, write=True)
        first = self._snapshot(self.root)
        for case_id, path in self.paths.items():
            original = self.originals[case_id]
            saved = json.loads(path.read_bytes())
            if case_id == "hbn-table-gw":
                self.assertEqual(saved, original)
                self.assertEqual(path.read_bytes(), self.original_repo[path.relative_to(self.root).as_posix()])
                continue
            for key in ("properties", "summary", "status", "material", "formula"):
                self.assertEqual(saved[key], original[key])
            self.assertEqual(saved["files"]["results"][:-1], original["files"]["results"])
            self.assertEqual(saved["notes"], original["notes"])
            self.assertIn("EXX仍为historical archive/path", saved["paper_values"]["notes"])
            paper = saved["paper_values"]
            declaration = saved["files"]["results"][-1]
            self.assertEqual(declaration["role"], "results")
            self.assertEqual(paper["evidence"], declaration["path"])
            evidence = (self.root / declaration["path"]).read_bytes()
            self.assertEqual(MIGRATOR._digest(evidence), declaration["sha256"])
            self.assertEqual(len(evidence), declaration["size_bytes"])
            excerpt = json.loads(evidence)
            self.assertEqual(excerpt["paper_values"], paper)
            self.assertEqual(set(paper["values"]), {"DFT", "GW"})
            if saved["dimension"] == "3d":
                self.assertEqual(paper["source"]["pdf_page"], 16)
                self.assertEqual(paper["source"]["table"], "IV")
                self.assertEqual(paper["values"]["DFT"]["value"], 1.234)
                self.assertEqual(paper["values"]["GW"]["value"], 2.345)
                self.assertEqual(paper["values"]["DFT"]["precision"], 3)
                self.assertIn("doi", paper["source"])
            else:
                self.assertEqual(paper["source"]["pdf_page"], 12)
                self.assertEqual(paper["source"]["table"], "I")
                self.assertNotIn("doi", paper["source"])
                self.assertIn("ABACUS", paper["values"]["DFT"]["column"])
        for relative, before in self.original_repo.items():
            if not relative.endswith("record.json"):
                self.assertEqual(first[relative], before)
        stats = MIGRATOR.import_paper_values(self.root, self.audit_path, write=True)
        self.assertEqual(stats["records_changed"], 0)
        self.assertEqual(stats["evidence_added"], 0)
        self.assertEqual(stats["paper_values_added"], 0)
        self.assertEqual(first, self._snapshot(self.root))
        for document in self.documents:
            self.assertEqual(document.read_bytes(), self.original_inputs[document.relative_to(self.base).as_posix()])
        self.assertEqual(self.audit_path.read_bytes(), self.original_inputs[self.audit_path.relative_to(self.base).as_posix()])

    def test_private_paths_and_internal_line_numbers_do_not_leak(self):
        MIGRATOR.import_paper_values(self.root, self.audit_path, write=True)
        for path in self.root.rglob("paper_reported_values.json"):
            text = path.read_text(encoding="utf-8")
            for private in ("/" + "Users/", "/" + "home/", str(self.base), "source_line", "tex_line", "text_path", "local_path", "private_path"):
                self.assertNotIn(private, text)

    def test_hbn_mapping_and_rejected_scope_retained_without_status_upgrade(self):
        MIGRATOR.import_paper_values(self.root, self.audit_path, write=True)
        hbn = json.loads(self.paths["hbn-tzdp10-fgext-20261008"].read_bytes())
        scope = hbn["paper_values"]["values"]["GW"]["scope"]
        for marker in ("valley ordering", "raw-band-5", "高态侵入", "path", "10-au", "3s3p2d"):
            self.assertIn(marker, scope)
        for case_id in ("gate-table-gw", "tis3-table-gw"):
            record = json.loads(self.paths[case_id].read_bytes())
            self.assertIn("rejected diagnostic", record["paper_values"]["values"]["GW"]["scope"])
            self.assertEqual(record["status"], "gw_diagnostic")
        mos2 = json.loads(self.paths["mos2-table-gw"].read_bytes())
        self.assertIn("6.25292 eV不是本case", mos2["paper_values"]["notes"])
        self.assertNotIn("EXX", mos2["paper_values"]["values"])

    def test_both_pdf_actual_hashes_checked_before_any_write(self):
        for document in self.documents:
            with self.subTest(document=document.name):
                before = document.read_bytes()
                document.write_bytes(before + b"tampered")
                self._assert_blocked("PDF实际sha256")
                document.write_bytes(before)

    def test_late_invalid_value_blocks_entire_plan(self):
        row = self.audit["values_2d_table_i"][-1]
        for value in (True, False, float("nan"), float("inf"), float("-inf"), "1.79705", None):
            with self.subTest(value=value):
                row["gw_ev"] = value
                self._save_audit()
                self._assert_blocked("有限非boolean")

    def test_reported_precision_is_validated(self):
        row = self.audit["values_2d_table_i"][-1]
        for precision in (True, 4, "5", None):
            with self.subTest(precision=precision):
                row["gw_precision"] = precision
                self._save_audit()
                self._assert_blocked("reported precision")
        row["gw_precision"] = 3
        self._save_audit()
        self._assert_blocked("超过声明")
        row["gw_precision"] = 5
        self.audit["sources"]["paper_3d"]["reported_decimal_places"] = 5
        self._save_audit()
        self._assert_blocked("三维论文reported precision")

    def test_row_counts_and_duplicate_materials_rejected(self):
        original = copy.deepcopy(self.audit)
        for table in ("values_3d_table_iv", "values_2d_table_i"):
            with self.subTest(table=table):
                self.audit = copy.deepcopy(original)
                self.audit[table].pop()
                self._save_audit()
                self._assert_blocked("论文行数")
                self.audit = copy.deepcopy(original)
                self.audit[table][-1] = copy.deepcopy(self.audit[table][0])
                self._save_audit()
                self._assert_blocked("重复")

    def test_wrong_formula_or_old_hbn_case_never_falls_back(self):
        hbn_row = next(row for row in self.audit["values_2d_table_i"] if row["material"] == "h-BN")
        hbn_row["database_case_id"] = "hbn-table-gw"
        self._save_audit()
        self._assert_blocked("h-BN新版主表")
        hbn_row["database_case_id"] = "hbn-tzdp10-fgext-20261008"
        self.audit["values_2d_table_i"][-1]["database_case_id"] = "mos2-table-gw"
        self._save_audit()
        self._assert_blocked("case_id/formula/dimension")

    def test_duplicate_record_id_and_ambiguous_3d_formula_rejected(self):
        other_path = self._add_record("2d", "Other", "mos2-table-gw")
        self._assert_blocked("record case_id映射重复")
        other_path.unlink()
        self._add_record("3d", "Si", "second-si-test")
        self._assert_blocked("三维case_id/formula映射不唯一")

    def test_existing_paper_values_metadata_conflict_is_never_overwritten(self):
        record = copy.deepcopy(self.originals["cuinp2se6-table-gw"])
        record["paper_values"] = {"schema_version": 1, "manual_review": "不要覆盖"}
        self.paths[record["id"]].write_text(json.dumps(record), encoding="utf-8")
        self._assert_blocked("paper_values人工metadata冲突")

    def test_boolean_existing_schema_metadata_is_a_conflict(self):
        MIGRATOR.import_paper_values(self.root, self.audit_path, write=True)
        path = self.paths["cuinp2se6-table-gw"]
        record = json.loads(path.read_bytes())
        record["paper_values"]["schema_version"] = True
        path.write_text(json.dumps(record), encoding="utf-8")
        self._assert_blocked("paper_values人工metadata冲突")

    def test_late_nonserializable_record_is_prevalidated_before_writes(self):
        path = self.paths["cuinp2se6-table-gw"]
        record = json.loads(path.read_bytes())
        record["summary"]["value"] = float("nan")
        path.write_text(json.dumps(record), encoding="utf-8")
        self._assert_blocked("Out of range float")

    def test_existing_excerpt_content_and_declaration_hash_conflicts_rejected(self):
        MIGRATOR.import_paper_values(self.root, self.audit_path, write=True)
        path = self.paths["cuinp2se6-table-gw"]
        record = json.loads(path.read_bytes())
        declaration = record["files"]["results"][-1]
        excerpt = self.root / declaration["path"]
        before = excerpt.read_bytes()
        excerpt.write_bytes(before + b" ")
        self._assert_blocked("摘录内容/hash冲突")
        excerpt.write_bytes(before)
        declaration["sha256"] = "0" * 64
        path.write_text(json.dumps(record), encoding="utf-8")
        self._assert_blocked("files.results声明/hash冲突")

    def test_reference_columns_and_other_series_exx_rejected(self):
        original = copy.deepcopy(self.audit)
        self.audit["sources"]["paper_3d"]["main_gw_column"] = "G0W0@PBE / FHI-aims"
        self._save_audit()
        self._assert_blocked("禁止参考列")
        self.audit = original
        self.audit["values_2d_table_i"][0]["exx_ev"] = 6.25292
        self._save_audit()
        self._assert_blocked("禁止填入其他系列")

    def test_private_path_in_allowed_text_is_rejected(self):
        self.audit["values_2d_table_i"][-1]["scope_note"] = "记录于 /" + "Users/private/source.pdf"
        self._save_audit()
        self._assert_blocked("私有路径")

    def test_symlinked_excerpt_is_rejected_without_mutation(self):
        MIGRATOR.import_paper_values(self.root, self.audit_path, write=True)
        path = self.paths["cuinp2se6-table-gw"].parent / "results/paper_reported_values.json"
        outside = self.base / "manual-paper-values.json"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        self._assert_blocked("逃逸根目录|符号链接")

    def test_cli_import_is_independent_from_legacy_and_recovery_modes(self):
        argv = [str(SCRIPT), "--root", str(self.root), "--import-paper-values", str(self.audit_path)]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(MIGRATOR, "migrate") as legacy, \
                mock.patch.object(MIGRATOR, "recover_table_evidence") as recover, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(MIGRATOR.main(), 0)
            legacy.assert_not_called()
            recover.assert_not_called()
            self.assertFalse(json.loads(output.getvalue())["write"])
        self.assertEqual(self.original_repo, self._snapshot(self.root))
        with mock.patch.object(sys, "argv", argv + ["--recover-table-evidence"]), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                MIGRATOR.main()
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
