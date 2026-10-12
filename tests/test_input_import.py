"""原输入导入必须先验证、显式写入，并拒绝跨运行或哈希冲突。"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/import_verified_inputs.py"
SPEC = importlib.util.spec_from_file_location("verified_inputs", SCRIPT)
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)


class InputImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        parent = Path(self.temporary.name)
        self.repo, self.source, self.raw = (parent / name for name in ("repo", "source", "raw"))
        self.case = "mos2-table-gw"
        self.relative = f"data/calculations/2d/MoS2/{self.case}"
        self.record_path = self.repo / self.relative / "record.json"
        self.source_case = self.source / "mos2/input_cases/paper_table_k20"
        self.run = self.raw / "MoS2/convg_test/k/20"
        self.source_case.mkdir(parents=True)
        self.run.mkdir(parents=True)
        files = {name: (name + "\n").encode() for name in IMPORTER.CONTROLS}
        files["STRU"] = b"ATOMIC_SPECIES\nMo 1 Mo.upf\nS 1 S.upf\nNUMERICAL_ORBITAL\nMo.orb\nS.orb\nABFS_ORBITAL\nMo.abfs\nS.abfs\nLATTICE_CONSTANT\n1\nATOMIC_POSITIONS\nDirect\nMo\n0\n1\n0 0 0\nS\n0\n1\n0.5 0.5 0\n"
        files["band_kpath_info"] = b"0 0 0\n"
        for element in ("Mo", "S"):
            for extension in ("upf", "orb", "abfs"):
                files[f"{element}.{extension}"] = f"{element} {extension} original payload\n".encode()
        for name, data in files.items():
            (self.source_case / name).write_bytes(data)
            (self.run / name).write_bytes(data)
        results, provenance_methods, sidecar_methods = [], {}, {}
        for method, gap in (("KS", 2), ("EXX", 4), ("GW", 3)):
            data = f"1 0 0 0 1 -1 0 {gap - 1}\n2 0.5 0 0 1 -2 0 {gap}\n".encode()
            raw_file = self.run / f"{method}_band_spin_1.dat"
            raw_file.write_bytes(data)
            path = f"{self.relative}/results/{method}_bands.dat"
            destination = self.repo / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            results.append(IMPORTER.file_item("results", path, data, f"{method}_bands.dat"))
            metrics = {"occupied_states": 1, "raw_band_count": 2, "npoints": 2, "path_gap_ev": gap}
            provenance_methods[method] = {**metrics, "source": {"original_path": str(raw_file), "sha256": IMPORTER.sha256(data)}}
            sidecar_methods[method] = {**metrics, "source": {"sha256": IMPORTER.sha256(data)}}
        sidecar_data = IMPORTER.json_bytes({"methods": sidecar_methods})
        sidecar_path = f"{self.relative}/results/band_window_and_provenance.json"
        (self.repo / sidecar_path).write_bytes(sidecar_data)
        results.append(IMPORTER.file_item("results", sidecar_path, sidecar_data, "sidecar"))
        self.provenance_path = self.source / "mos2/provenance/table_band_source.json"
        self.provenance_path.parent.mkdir(parents=True)
        self.provenance_path.write_bytes(IMPORTER.json_bytes({"methods": provenance_methods}))
        self.record = {"schema_version": 1, "id": self.case, "dimension": "2d", "material": "MoS2", "formula": "MoS2",
                       "species": [], "basis_candidates": [{"element": "Mo", "set_id": "old-candidate", "scope": "context only"}],
                       "software": {name: {"commit": None, "evidence": [], "missing_reason": "unknown full commit"} for name in ("abacus", "librpa")},
                       "status": "gw_diagnostic", "summary": {"value": 123, "unit": "eV"},
                       "missing": ["Exact production STRU/PP/NAO/ABF link pending source-case audit", "Full per-case ABACUS/LibRPA commits pending source-case audit"],
                       "files": {"inputs": [], "results": results, "logs": [], "figures": []},
                       "properties": [{"key": "gw_original", "method": "GW path", "value": 123}],
                       "source": {"original_sidecar_sha256": IMPORTER.sha256(self.provenance_path.read_bytes())}}
        self.record_path.write_bytes(IMPORTER.json_bytes(self.record))
        (self.run / "abacus.1.out").write_bytes(b"Commit: 1dd0199\n")
        (self.run / "LibRPA.1.out").write_bytes(b"unknown software identity\n")
        self.original_repo = self.snapshot(self.repo)
        self.original_source = self.snapshot(self.source)
        self.original_raw = self.snapshot(self.raw)

    @staticmethod
    def snapshot(root):
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def run_import(self, write=False):
        return IMPORTER.import_case(self.repo, self.source, self.raw, self.case, write=write)

    def test_dry_run_never_writes(self):
        result = self.run_import()
        self.assertEqual(result["input_file_count"], 15)
        self.assertEqual(result["control_file_count"], 8)
        self.assertEqual(self.original_repo, self.snapshot(self.repo))

    def test_cli_requires_explicit_write(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo-root", str(self.repo), "--source-root", str(self.source),
                                 "--raw-root", str(self.raw), "--case", self.case], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.original_repo, self.snapshot(self.repo))

    def test_write_is_idempotent_and_preserves_source_old_results_and_scientific_status(self):
        self.run_import(write=True)
        first = self.snapshot(self.repo)
        self.run_import(write=True)
        self.assertEqual(first, self.snapshot(self.repo))
        self.assertEqual(self.original_source, self.snapshot(self.source))
        self.assertEqual(self.original_raw, self.snapshot(self.raw))
        for path, data in self.original_repo.items():
            if path != self.record_path.relative_to(self.repo).as_posix():
                self.assertEqual(first[path], data)
        record = json.loads(self.record_path.read_bytes())
        for field in ("status", "summary", "software", "basis_candidates"):
            self.assertEqual(record[field], self.record[field])
        self.assertEqual(record["properties"][0], self.record["properties"][0])
        self.assertEqual(len(record["files"]["inputs"]), 8)
        self.assertEqual(len(record["species"]), 2)
        self.assertEqual({prop["method"] for prop in record["properties"][1:]}, {"PBE", "EXX"})
        self.assertIn("Full per-case ABACUS/LibRPA commits pending source-case audit", record["missing"])
        receipt = json.loads((self.repo / record["source"]["raw_input_receipt"]).read_bytes())
        self.assertEqual(receipt["input_file_count"], 15)
        self.assertEqual(len(receipt["files"]), 15)
        self.assertEqual(set(receipt["spectra"]), {"KS", "EXX", "GW"})
        self.assertEqual(receipt["source_run_relative"], "MoS2/convg_test/k/20")
        self.assertNotIn(str(self.temporary.name), json.dumps(receipt))
        for basis_file in self.repo.glob("data/elements/*/sets/*/set.json"):
            basis = json.loads(basis_file.read_bytes())
            self.assertEqual(basis["publication"]["status"], "database_only")
            self.assertEqual(basis["source"]["license"], "unknown")
            self.assertEqual(basis["source"]["redistribution"], "unknown")
            self.assertEqual({item["role"] for item in basis["files"]}, {"pp", "nao", "abf"})
        self.assertFalse(any(path.suffix in (".upf", ".orb", ".abfs") for path in (self.repo / self.relative / "inputs").iterdir()))

    def test_input_raw_mismatch_stops_without_writes(self):
        (self.run / "Mo.upf").write_bytes(b"different historical PP")
        with self.assertRaisesRegex(ValueError, "原字节不匹配"):
            self.run_import(write=True)
        self.assertEqual(self.original_repo, self.snapshot(self.repo))

    def test_foreign_run_rejected_even_with_identical_bands(self):
        provenance = json.loads(self.provenance_path.read_bytes())
        foreign = self.raw / "foreign/KS_band_spin_1.dat"
        foreign.parent.mkdir()
        foreign.write_bytes((self.run / "KS_band_spin_1.dat").read_bytes())
        provenance["methods"]["KS"]["source"]["original_path"] = str(foreign)
        self.provenance_path.write_bytes(IMPORTER.json_bytes(provenance))
        record = json.loads(self.record_path.read_bytes())
        record["source"]["original_sidecar_sha256"] = IMPORTER.sha256(self.provenance_path.read_bytes())
        self.record_path.write_bytes(IMPORTER.json_bytes(record))
        before = self.snapshot(self.repo)
        with self.assertRaisesRegex(ValueError, "foreign-run"):
            self.run_import(write=True)
        self.assertEqual(before, self.snapshot(self.repo))

    def test_provenance_must_match_existing_record_source_hash(self):
        self.provenance_path.write_bytes(self.provenance_path.read_bytes() + b" \n")
        with self.assertRaisesRegex(ValueError, "既有来源哈希"):
            self.run_import(write=True)
        self.assertEqual(self.original_repo, self.snapshot(self.repo))

    def test_record_spectrum_hash_mismatch_stops_without_writes(self):
        path = self.repo / self.relative / "results/GW_bands.dat"
        path.write_bytes(b"wrong GW spectrum\n")
        before = self.snapshot(self.repo)
        with self.assertRaisesRegex(ValueError, "哈希不匹配"):
            self.run_import(write=True)
        self.assertEqual(before, self.snapshot(self.repo))

    def test_sidecar_gap_must_match_finite_full_raw_spectrum(self):
        with self.assertRaisesRegex(ValueError, "path_gap_ev"):
            IMPORTER.verify_bands(b"1 0 0 0 1 -1 0 1\n", {"npoints": 1, "raw_band_count": 2, "occupied_states": 1, "path_gap_ev": 4})
        with self.assertRaisesRegex(ValueError, "非有限值"):
            IMPORTER.verify_bands(b"1 0 0 0 1 -1 0 nan\n", {"npoints": 1, "raw_band_count": 2, "occupied_states": 1, "path_gap_ev": 2})
        with self.assertRaisesRegex(ValueError, "占据边界"):
            IMPORTER.verify_bands(b"1 0 0 0 0 -1 1 1\n", {"npoints": 1, "raw_band_count": 2, "occupied_states": 1, "path_gap_ev": 2})

    def test_asset_reuse_and_immutable_conflict(self):
        plan = IMPORTER.prepare_case(self.repo, self.source, self.raw, self.case)
        payload_path = next(path for path in plan["writes"] if path.endswith(".upf"))
        destination = self.repo / payload_path
        destination.parent.mkdir(parents=True)
        destination.write_bytes(plan["writes"][payload_path])
        self.run_import(write=True)
        self.assertEqual(destination.read_bytes(), plan["writes"][payload_path])
        destination.write_bytes(b"immutable conflict")
        before = self.snapshot(self.repo)
        with self.assertRaisesRegex(ValueError, "不可变目标内容冲突"):
            self.run_import(write=True)
        self.assertEqual(before, self.snapshot(self.repo))

    def test_incomplete_source_collection_rejected(self):
        (self.source_case / "INPUT_scf").unlink()
        with self.assertRaisesRegex(ValueError, "完整15文件"):
            self.run_import(write=True)
        self.assertEqual(self.original_repo, self.snapshot(self.repo))

    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(ValueError, "非便携"):
            IMPORTER.portable_path(self.repo, "../outside")


if __name__ == "__main__":
    unittest.main()
