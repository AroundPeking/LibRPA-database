"""Partial-stage archiving must not promote science or overwrite reviewed evidence."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("stage_inputs", ROOT / "scripts/import_stage_inputs.py")
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)


class StageInputImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo, self.stage = self.root / "repo", self.root / "stage"
        self.repo.mkdir()
        self.stage.mkdir()
        self.spec_path = self.stage / "recovery-spec.json"
        self.cases = []
        for index, case_id in enumerate(sorted(IMPORTER.CASES)):
            relative = f"data/calculations/2d/M{index}/{case_id}"
            directory = self.repo / relative
            directory.mkdir(parents=True)
            results, spectra = [], []
            for method in ("KS", "EXX", "GW"):
                path = relative + f"/results/{method}_bands.dat"
                data = b"1 0 0 0 1 -1 0 2\n"
                (self.repo / path).parent.mkdir(exist_ok=True)
                (self.repo / path).write_bytes(data)
                results.append(IMPORTER.file_item("results", path, data, method))
                spectra.append({"method": method, "sha256": IMPORTER.sha256(data), "expected_sha256": IMPORTER.sha256(data),
                                "size_bytes": len(data), "record_result": {"source_path": str(self.repo / path)}})
            record = {"schema_version": 1, "id": case_id, "dimension": "2d", "material": f"M{index}",
                      "status": "gw_diagnostic", "summary": {"value": 7}, "species": [],
                      "software": {"librpa": {"commit": None}}, "paper_values": {"value": 6.9},
                      "files": {"inputs": [], "results": results, "logs": [], "figures": []}, "source": {},
                      "missing": ["full chain unverified"]}
            record_data = IMPORTER.json_bytes(record)
            record_path = directory / "record.json"
            record_path.write_bytes(record_data)
            stage_relative = f"case-{index}"
            (self.stage / stage_relative).mkdir()
            source_dir = f"/historical/case-{index}/run"
            entries = []
            for name, data in (("INPUT", b"INPUT_PARAMETERS\ncalculation scf\n"),
                               ("KPT", b"K_POINTS\n0\nGamma\n1 1 1 0 0 0\n"),
                               ("STRU", b"ATOMIC_SPECIES\nMo 1 Mo.upf\nATOMIC_POSITIONS\nDirect\n"),
                               ("librpa.in", b"task = g0w0\n")):
                target = self.stage / stage_relative / name
                target.write_bytes(data)
                entries.append({"source_path": source_dir + "/" + name, "staged_path": str(target),
                                "staged_relative_path": stage_relative + "/" + name,
                                "sha256": IMPORTER.sha256(data), "staged_sha256": IMPORTER.sha256(data),
                                "size_bytes": len(data), "staged_size_bytes": len(data), "original_bytes_copied": True})
            self.cases.append({"case_id": case_id, "automatic_import_candidate": False, "complete_handoff": False,
                               "current_record": {"source_path": str(record_path), "sha256": IMPORTER.sha256(record_data),
                                                  "size_bytes": len(record_data)}, "spectra": spectra,
                               "original_files": entries,
                               "stages": [{"source_directory": source_dir, "original_controls": copy.deepcopy(entries),
                                           "parsed_original_settings": {"INPUT": {"calculation": "scf"}}}],
                               "production_chain_restrictions": ["full runtime payload absent"]})
        self.spec = {"schema_version": 1, "database_root": str(self.repo), "cases": self.cases}
        self.save_spec()
        self.original = self.snapshot(self.repo)
        self.original_stage = self.snapshot(self.stage)

    def save_spec(self):
        data = IMPORTER.json_bytes(self.spec)
        self.spec_path.write_bytes(data)
        self.digest = IMPORTER.sha256(data)

    @staticmethod
    def snapshot(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def run_import(self, write=False):
        return IMPORTER.import_stage_inputs(self.repo, self.spec_path, write=write, expected_spec_sha256=self.digest)

    def test_dry_run_does_not_write(self):
        self.assertEqual(self.run_import()["controls"], 36)
        self.assertEqual(self.original, self.snapshot(self.repo))
        self.assertEqual(self.original_stage, self.snapshot(self.stage))

    def test_write_idempotent_preserves_scientific_fields_and_all_old_payloads(self):
        self.run_import(write=True)
        first = self.snapshot(self.repo)
        self.run_import(write=True)
        self.assertEqual(first, self.snapshot(self.repo))
        self.assertEqual(self.original_stage, self.snapshot(self.stage))
        for name, data in self.original.items():
            if name.endswith("/record.json"):
                old, new = json.loads(data), json.loads(first[name])
                for field in ("species", "software", "paper_values", "summary", "status", "missing"):
                    self.assertEqual(old[field], new[field])
                receipt = json.loads(first[new["source"]["stage_input_receipt"]])
                self.assertFalse(receipt["full_runtime_handoff_verified"])
                self.assertFalse(receipt["automatic_import_candidate_promoted"])
            else:
                self.assertEqual(data, first[name])

    def test_pinned_spec_change_rejects_without_writes(self):
        self.spec_path.write_bytes(self.spec_path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "immutable version"):
            self.run_import(write=True)
        self.assertEqual(self.original, self.snapshot(self.repo))

    def test_wrong_control_hash_rejects_before_writes(self):
        Path(self.cases[-1]["original_files"][0]["staged_path"]).write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "SHA/size"):
            self.run_import(write=True)
        self.assertEqual(self.original, self.snapshot(self.repo))

    def test_foreign_stage_source_rejects(self):
        self.cases[0]["stages"][0]["source_directory"] = "/foreign/run"
        self.save_spec()
        with self.assertRaisesRegex(ValueError, "foreign"):
            self.run_import(write=True)
        self.assertEqual(self.original, self.snapshot(self.repo))

    def test_spectrum_mismatch_rejects_without_writes(self):
        Path(self.cases[0]["spectra"][0]["record_result"]["source_path"]).write_bytes(b"different")
        before = self.snapshot(self.repo)
        with self.assertRaisesRegex(ValueError, "spectrum"):
            self.run_import(write=True)
        self.assertEqual(before, self.snapshot(self.repo))

    def test_same_target_with_different_bytes_rejects(self):
        self.run_import(write=True)
        path = next(self.repo.glob("data/calculations/2d/*/*/inputs/recovered/*/INPUT"))
        path.write_bytes(b"conflicting existing input")
        before = self.snapshot(self.repo)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.run_import(write=True)
        self.assertEqual(before, self.snapshot(self.repo))

    def test_readset_mutation_rejects_before_any_write(self):
        original = IMPORTER.public_control
        target = Path(self.cases[0]["original_files"][0]["staged_path"])
        def mutate(data, case_id, name):
            result = original(data, case_id, name)
            if case_id == self.cases[-1]["case_id"]:
                target.write_bytes(b"changed after initial validation")
            return result
        with mock.patch.object(IMPORTER, "public_control", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "readset"):
                self.run_import(write=True)
        self.assertEqual(self.original, self.snapshot(self.repo))

    def test_extra_recovered_declaration_rejects_without_writes(self):
        self.run_import(write=True)
        path = Path(self.cases[0]["current_record"]["source_path"])
        record = json.loads(path.read_bytes())
        extra = copy.deepcopy(record["files"]["inputs"][0])
        extra["path"] = extra["path"].rsplit("/", 1)[0] + "/foreign.in"
        record["files"]["inputs"].append(extra)
        path.write_bytes(IMPORTER.json_bytes(record))
        before = self.snapshot(self.repo)
        with self.assertRaisesRegex(ValueError, "exact reviewed increment"):
            self.run_import(write=True)
        self.assertEqual(before, self.snapshot(self.repo))

    def test_foreign_receipt_pointer_rejects_without_writes(self):
        self.run_import(write=True)
        path = Path(self.cases[0]["current_record"]["source_path"])
        record = json.loads(path.read_bytes())
        record["source"]["stage_input_receipt"] = "data/foreign/receipt.json"
        path.write_bytes(IMPORTER.json_bytes(record))
        before = self.snapshot(self.repo)
        with self.assertRaisesRegex(ValueError, "pointer conflicts"):
            self.run_import(write=True)
        self.assertEqual(before, self.snapshot(self.repo))

    def test_staged_symlink_rejects_without_repository_writes(self):
        target = Path(self.cases[0]["original_files"][0]["staged_path"])
        saved = target.with_name("saved-original")
        target.rename(saved)
        target.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, "owned original"):
            self.run_import(write=True)
        self.assertEqual(self.original, self.snapshot(self.repo))

    def test_target_directory_conflict_rejects_before_writes(self):
        case = self.cases[0]
        relative = Path(case["current_record"]["source_path"]).parent
        stage_id = IMPORTER.sha256(case["stages"][0]["source_directory"].encode())[:12]
        (relative / "inputs/recovered" / stage_id / "INPUT").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "目标路径冲突"):
            self.run_import(write=True)
        self.assertEqual(self.original, self.snapshot(self.repo))

    def test_record_mutation_rejects_before_any_import_write(self):
        original = IMPORTER.public_control
        target = Path(self.cases[0]["current_record"]["source_path"])
        mutated = self.original[target.relative_to(self.repo).as_posix()] + b" "
        def mutate(data, case_id, name):
            result = original(data, case_id, name)
            if case_id == self.cases[-1]["case_id"]:
                target.write_bytes(mutated)
            return result
        with mock.patch.object(IMPORTER, "public_control", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "readset"):
                self.run_import(write=True)
        expected = dict(self.original)
        expected[target.relative_to(self.repo).as_posix()] = mutated
        self.assertEqual(expected, self.snapshot(self.repo))

    def test_redaction_preserves_original_bytes_and_rejects_unreviewed_private_path(self):
        original = b"task = g0w0_band\ninput_dir = /data/" + b"home/private/run/input_librpa/\n"
        result, transformation = IMPORTER.public_control(original, "mos2_ws2-table-gw", "librpa.in")
        self.assertEqual(result, b"task = g0w0_band\ninput_dir = ./input_librpa/\n")
        self.assertIn("redacted", transformation)
        self.assertIn(b"private", original)
        with self.assertRaisesRegex(ValueError, "private path"):
            IMPORTER.public_control(original, "mote2-table-gw", "librpa.in")


if __name__ == "__main__":
    unittest.main()
