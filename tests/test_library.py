"""Integrity regressions for contributed scientific records."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = ROOT / "scripts/library.py"
        assert script.exists(), "missing library integrity validator"
        sys.path.insert(0, str(script.parent))
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

    def test_paper_extract_is_independent_and_hash_bound_without_certifying_upload(self):
        import copy
        evidence = "data/calculations/3d/Si/si-control/results/paper_reported_values.json"
        paper = {"schema_version": 1, "evidence": evidence,
                 "source": {"title": "Paper", "document_sha256": "a" * 64, "pdf_page": 16, "table": "IV"},
                 "values": {method: {"value": value, "unit": "eV", "precision": 3,
                                    "column": "ABACUS" if method == "DFT" else "ABACUS+LibRPA",
                                    "scope": "Paper-reported, original path evidence separate"}
                            for method, value in (("DFT", 0.561), ("GW", 1.060))},
                 "notes": "EXX not reported in the main table"}
        original = copy.deepcopy(self.case)
        self.case["paper_values"] = paper
        data = json.dumps({"case_id": self.case["id"], "paper_values": paper}).encode()
        item = self._add_file(evidence, data, "results")
        self.case["files"] = {"results": [item]}
        self.lib.validate(self.root, [self.set], [self.case])
        self.assertEqual(self.case["status"], original["status"])
        issues = self.lib.completeness_issues(self.root, [self.set], self.case)
        self.assertTrue(any("software" in issue for issue in issues))
        self.assertTrue(any("band result" in issue for issue in issues))
        paper["values"]["GW"]["value"] = 2.0
        with self.assertRaisesRegex(ValueError, "extract and displayed"):
            self.lib.validate(self.root, [self.set], [self.case])
        paper["values"]["GW"]["value"] = 1.060
        paper["evidence"] = "another/case/results/paper_reported_values.json"
        with self.assertRaisesRegex(ValueError, "same-record"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_unknown_commits_are_explicitly_allowed(self):
        self.lib.validate(self.root, [self.set], [self.case])

    def test_contextual_basis_candidate_must_exist_and_have_scope(self):
        self.case["basis_candidates"] = [{"element": "Si", "set_id": "Si-test", "scope": "contextual"}]
        self.lib.validate(self.root, [self.set], [self.case])
        self.case["basis_candidates"][0]["set_id"] = "C-missing"
        with self.assertRaisesRegex(ValueError, "unknown candidate"):
            self.lib.validate(self.root, [self.set], [self.case])

    def _add_property_evidence(self):
        item = self._add_file("calculations/si/GW_bands.dat", b"gap\n", "results")
        self.case["files"] = {"results": [item]}
        return item["path"]

    def _property(self, evidence):
        return {
            "key": "band_gap", "category": "electronic", "label": "Band gap",
            "method": "G0W0", "value": 1.2, "unit": "eV", "status": "reported",
            "evidence": [evidence],
        }

    def test_evidence_linked_property_is_accepted(self):
        evidence = self._add_property_evidence()
        self.case["properties"] = [self._property(evidence)]
        self.lib.validate(self.root, [self.set], [self.case])

    def test_property_requires_evidence(self):
        self._add_property_evidence()
        self.case["properties"] = [self._property("data/calculations/si/missing.dat")]
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_property_category_must_be_a_slug(self):
        evidence = self._add_property_evidence()
        entry = self._property(evidence)
        entry["category"] = "Topological properties"
        self.case["properties"] = [entry]
        with self.assertRaisesRegex(ValueError, "category"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_property_evidence_must_belong_to_same_calculation(self):
        self._add_property_evidence()
        self.case["properties"] = [self._property("elements/Si/pseudopotentials/test.upf")]
        with self.assertRaisesRegex(ValueError, "declared"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_property_key_category_and_method_must_be_unique(self):
        evidence = self._add_property_evidence()
        self.case["properties"] = [self._property(evidence), self._property(evidence)]
        with self.assertRaisesRegex(ValueError, "duplicate property"):
            self.lib.validate(self.root, [self.set], [self.case])

    def test_property_values_accept_json_objects(self):
        evidence = self._add_property_evidence()
        entry = self._property(evidence)
        entry["key"] = "invariant"
        entry["category"] = "topological"
        entry["label"] = "Z2 invariant"
        entry["method"] = "Wilson loop"
        entry["value"] = {"spin_up": 1, "spin_down": 1}
        entry["unit"] = "dimensionless"
        self.case["properties"] = [entry]
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


class CompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        LibraryTests.setUpClass()
        cls.lib = LibraryTests.lib

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.prefix = "data/calculations/3d/Si/si-control/"
        self.basis = {
            "id": "Si-test", "element": "Si", "files": [
                self._add_file("data/elements/Si/test.upf", b'<UPF version="2.0.1"><PP_HEADER element="Si"/><PP_R>0 1</PP_R><PP_LOCAL>1 2</PP_LOCAL></UPF>', "pp"),
                self._add_file("data/elements/Si/test.orb", b"Element Si\nSUMMARY END\nMesh 2\ndr 0.1\nType L N\n0 0 0\n1.0 2.0\n", "nao"),
                self._add_file("data/elements/Si/test.abfs", b"Element Si\nSUMMARY END\nMesh 2\ndr 0.1\nType L N\n0 0 0\n2.0 3.0\n", "abf"),
            ],
        }
        self.case = {
            "id": "si-control", "dimension": "3d", "material": "Si", "formula": "Si",
            "status": "path_diagnostic", "publication": {"status": "legacy_incomplete"},
            "species": [{"element": "Si", "set_id": "Si-test", "asset_aliases": {
                "pp": "test.upf", "nao": "test.orb", "abf": "test.abfs"}}],
            "software": {"abacus": {"commit": "a" * 40}, "librpa": {"commit": "b" * 40}},
            "files": {"inputs": [
                self._input("scf__INPUT", b"INPUT_PARAMETERS\ncalculation scf\nntype 1\n"),
                self._input("KPT_nscf", b"K_POINTS\n2\nLine\n0 0 0 1\n1 0 0 1\n"),
                self._input("STRU", b"ATOMIC_SPECIES\nSi 28 test.upf\nNUMERICAL_ORBITAL\ntest.orb\nABFS_ORBITAL\ntest.abfs\nLATTICE_CONSTANT\n1\nATOMIC_POSITIONS\nDirect\nSi\n0\n1\n0 0 0\n"),
                self._input("gw__librpa.in", b"task = g0w0\nnfreq = 16\n"),
            ], "results": [], "figures": []},
            "properties": [],
        }
        self._add_method("KS", "PBE")
        self._add_method("EXX", "EXX")
        self._add_method("GW", "G0W0")
        source_paths = [item["path"] for item in self.case["files"]["results"]]
        figure = self._add_file(self.prefix + "figures/band_comparison.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><text x="1" y="10">Energy (eV); k-path; PBE EXX GW bands</text><path d="M 0 80 L 100 50 L 200 20" fill="none" stroke="black"/></svg>', "figures")
        figure["source_paths"] = source_paths
        self.case["files"]["figures"].append(figure)

    def tearDown(self):
        self.tmp.cleanup()

    _add_file = LibraryTests._add_file

    def _input(self, name, data):
        return self._add_file(self.prefix + "inputs/" + name, data, "inputs")

    def _add_method(self, stem, method):
        item = self._add_file(self.prefix + f"results/{stem}_bands.dat", b"0 -1.0 1.0\n1 -0.5 1.2\n", "results")
        self.case["files"]["results"].append(item)
        self.case["properties"].append({
            "key": "band_gap", "category": "electronic", "label": "Band gap",
            "method": method, "value": 1.5, "unit": "eV", "status": "reported",
            "evidence": [item["path"]], "definition": "sampled path gap, not a global fundamental gap",
        })

    def issues(self):
        return self.lib.completeness_issues(self.root, [self.basis], self.case)

    def test_complete_diagnostic_archive_is_accepted_without_changing_status(self):
        self.lib.validate(self.root, [self.basis], [self.case])
        self.assertEqual(self.issues(), [])
        self.lib.check_completeness(self.root, [self.basis], [self.case])
        self.assertEqual(self.case["status"], "path_diagnostic")

    def test_missing_history_and_candidates_cannot_waive_exact_species(self):
        self.case["species"] = []
        self.case["missing"] = ["historical exact binding unknown"]
        self.case["basis_candidates"] = [{"element": "Si", "set_id": "Si-test", "scope": "candidate"}]
        self.lib.validate(self.root, [self.basis], [self.case])
        self.assertTrue(any("species" in issue for issue in self.issues()))

    def test_null_set_id_is_rejected(self):
        self.case["species"][0]["set_id"] = None
        self.assertTrue(any("set_id" in issue for issue in self.issues()))

    def test_formula_elements_must_all_be_bound(self):
        self.case["formula"] = "SiC"
        self.assertTrue(any("C" in issue and "species" in issue for issue in self.issues()))

    def test_explicit_unreadable_formula_cannot_fall_back_to_material(self):
        self.case["formula"] = "unknown-formula"
        self.assertTrue(any("formula/material" in issue for issue in self.issues()))

    def test_missing_roles_and_for_aux_cannot_replace_physical_nao(self):
        self.case["species"][0]["missing_roles"] = ["abf"]
        self.basis["files"][1]["role"] = "for_aux"
        issues = self.issues()
        self.assertTrue(any("missing_roles" in issue for issue in issues))
        self.assertTrue(any("nao" in issue for issue in issues))

    def test_empty_and_wrong_format_assets_are_rejected(self):
        item = self.basis["files"][0]
        (self.root / item["path"]).write_bytes(b"not a pseudopotential")
        item["sha256"] = hashlib.sha256(b"not a pseudopotential").hexdigest()
        self.assertTrue(any("pp" in issue and "payload" in issue for issue in self.issues()))

    def test_stru_names_must_match_exact_payload_not_description(self):
        self.case["species"][0]["asset_aliases"]["nao"] = "different.orb"
        self.basis["files"][1]["display_name"] = "test.orb"
        self.assertTrue(any("STRU" in issue and "nao" in issue for issue in self.issues()))

    def test_original_name_is_accepted_but_cross_set_filename_is_not_proof(self):
        self.case["species"][0]["asset_aliases"] = {}
        for item in self.basis["files"]:
            item["original_name"] = Path(item["path"]).name
        self.assertEqual(self.issues(), [])
        self.basis["files"][1].pop("original_name")
        self.assertTrue(any("STRU" in issue and "nao" in issue for issue in self.issues()))

    def test_same_hash_original_alias_is_proof_but_different_hash_is_not(self):
        import copy
        other = copy.deepcopy(self.basis)
        other["id"] = "Si-same-hash"
        self.case["species"][0]["asset_aliases"] = {}
        for item in other["files"]:
            item["original_name"] = Path(item["path"]).name
        self.assertEqual(self.lib.completeness_issues(self.root, [self.basis, other], self.case), [])
        other["files"][1]["sha256"] = "f" * 64
        self.assertTrue(any("STRU" in issue and "nao" in issue for issue in
                            self.lib.completeness_issues(self.root, [self.basis, other], self.case)))

    def test_short_commits_block_strict_legacy_archive(self):
        self.case["software"]["abacus"]["commit"] = "abc1234"
        self.assertTrue(any("abacus" in issue and "commit" in issue for issue in self.issues()))

    def test_partial_inputs_and_manifest_only_are_rejected(self):
        self.case["files"]["inputs"] = [self._input("INPUT_MANIFEST.sha256", b"manifest\n")]
        issues = self.issues()
        for name in ("INPUT", "KPT", "STRU", "librpa.in"):
            self.assertTrue(any(f"input {name}" in issue for issue in issues), name)

    def test_empty_input_and_another_record_input_are_rejected(self):
        self.case["files"]["inputs"][0] = self._input("INPUT", b"")
        self.case["files"]["inputs"][1] = self._add_file("data/calculations/3d/Si/other/inputs/KPT", b"K_POINTS\n1\nGamma\n1 1 1 0 0 0\n", "inputs")
        issues = self.issues()
        self.assertTrue(any("input INPUT" in issue for issue in issues))
        self.assertTrue(any("same calculation" in issue for issue in issues))

    def test_full_commits_are_required_even_for_legacy_records(self):
        self.case["software"]["abacus"]["commit"] = None
        self.case["software"]["librpa"]["commit"] = None
        issues = self.issues()
        self.assertTrue(any("abacus" in issue and "commit" in issue for issue in issues))
        self.assertTrue(any("librpa" in issue and "commit" in issue for issue in issues))

    def test_existing_dft_and_exx_methods_cannot_omit_gaps(self):
        self.case["properties"] = self.case["properties"][2:]
        issues = self.issues()
        self.assertTrue(any("PBE" in issue and "band_gap" in issue for issue in issues))
        self.assertTrue(any("EXX" in issue and "band_gap" in issue for issue in issues))

    def test_only_actual_methods_require_gaps(self):
        self.case["files"]["results"] = self.case["files"]["results"][:1]
        self.case["properties"] = self.case["properties"][:1]
        self.case["files"]["figures"][0]["source_paths"] = [self.case["files"]["results"][0]["path"]]
        self.assertEqual(self.issues(), [])

    def test_nonfinite_failed_wrong_unit_and_wrong_method_evidence_are_rejected(self):
        for field, value in (("value", float("nan")), ("value", float("inf")), ("value", True), ("status", "failed"), ("unit", "Ha"), ("evidence", [self.case["files"]["results"][1]["path"]])):
            with self.subTest(field=field, value=value):
                entry = self.case["properties"][0]
                old = entry[field]
                entry[field] = value
                self.assertTrue(any("PBE" in issue and "band_gap" in issue for issue in self.issues()))
                entry[field] = old

    def test_missing_empty_corrupt_and_nonband_figures_are_rejected(self):
        figure = self.case["files"]["figures"][0]
        for data in (b"", b"not an svg", b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'):
            with self.subTest(data=data):
                (self.root / figure["path"]).write_bytes(data)
                figure["sha256"] = hashlib.sha256(data).hexdigest()
                self.assertTrue(any("band figure" in issue for issue in self.issues()))
        self.case["files"]["figures"] = []
        self.assertTrue(any("band figure" in issue for issue in self.issues()))

    def test_bands_must_contain_readable_equal_width_numeric_data(self):
        item = self.case["files"]["results"][0]
        for data in (b"bands\n", b"0 -1 1\n1 0\n", b"0 -1 1\n"):
            with self.subTest(data=data):
                (self.root / item["path"]).write_bytes(data)
                item["sha256"] = hashlib.sha256(data).hexdigest()
                self.assertTrue(any("PBE" in issue and "band data" in issue for issue in self.issues()))

    def test_nonfinite_raw_spectrum_is_archived_not_scientifically_promoted(self):
        item = self.case["files"]["results"][2]
        data = b"0 -1 1 nan\n1 -0.5 1.2 inf\n"
        (self.root / item["path"]).write_bytes(data)
        item["sha256"] = hashlib.sha256(data).hexdigest()
        entry = self.case["properties"][2]
        entry["key"] = "restricted_frontier_path_gap"
        entry["definition"] = "raw-band-2 restricted frontier path gap; not a global or complete-spectrum gap"
        self.case["status"] = "failed"
        self.assertEqual(self.issues(), [])
        self.lib.check_completeness(self.root, [self.basis], [self.case])
        self.assertEqual(self.case["status"], "failed")
        self.assertEqual(entry["key"], "restricted_frontier_path_gap")

    def test_figure_sources_may_include_owned_kpt_log_and_sidecar(self):
        figure = self.case["files"]["figures"][0]
        log = self._add_file(self.prefix + "logs/librpa.out", b"Bands of occupation: 1\n", "logs")
        sidecar = self._add_file(self.prefix + "figures/band_metadata.json", b'{"scope": "path"}\n', "figures")
        self.case["files"]["logs"] = [log]
        self.case["files"]["figures"].append(sidecar)
        figure["source_paths"] += [self.case["files"]["inputs"][1]["path"], log["path"], sidecar["path"]]
        self.assertEqual(self.issues(), [])

    def test_figure_sources_require_one_band_and_all_valid_same_record_evidence(self):
        figure = self.case["files"]["figures"][0]
        for sources in ([], [self.case["files"]["inputs"][1]["path"]],
                        [self.case["files"]["results"][0]["path"], "data/calculations/3d/Si/foreign/results/GW_bands.dat"],
                        [self.case["files"]["results"][0]["path"], "undeclared.json"]):
            with self.subTest(sources=sources):
                figure["source_paths"] = sources
                self.assertTrue(any("band figure" in issue for issue in self.issues()))

    def test_figure_source_hash_mismatch_is_rejected(self):
        item = self.case["files"]["inputs"][1]
        self.case["files"]["figures"][0]["source_paths"].append(item["path"])
        (self.root / item["path"]).write_bytes(b"changed KPT\n")
        issues = self.issues()
        self.assertTrue(any("SHA-256" in issue for issue in issues))
        self.assertTrue(any("band figure" in issue for issue in issues))

    def test_svg_band_semantics_cannot_replace_actual_curve(self):
        item = self.case["files"]["figures"][0]
        for data in (b'<svg><text>Energy eV k-path bands</text><path d="unreadable"/></svg>',
                     b'<svg><text>Energy eV k-path bands</text></svg>'):
            with self.subTest(data=data):
                (self.root / item["path"]).write_bytes(data)
                item["sha256"] = hashlib.sha256(data).hexdigest()
                self.assertTrue(any("band figure" in issue for issue in self.issues()))

    def test_svg_numeric_tokens_without_drawing_commands_are_rejected(self):
        item = self.case["files"]["figures"][0]
        for path_data in ("123 456 789 101", "M 0 0 M 10 10", "M 0 0 L 1e999 10"):
            with self.subTest(path_data=path_data):
                data = f'<svg><text>Energy eV k-path bands</text><path d="{path_data}" stroke="black"/></svg>'.encode()
                (self.root / item["path"]).write_bytes(data)
                item["sha256"] = hashlib.sha256(data).hexdigest()
                self.assertTrue(any("band figure" in issue for issue in self.issues()))

    def test_unused_svg_definitions_cannot_count_as_visible_curve(self):
        item = self.case["files"]["figures"][0]
        for tag in ("defs", "clipPath", "mask", "symbol", "marker", "pattern"):
            with self.subTest(tag=tag):
                data = f'<svg><text>Energy eV k-path bands</text><{tag}><path d="M 0 0 L 10 10" stroke="black"/></{tag}></svg>'.encode()
                (self.root / item["path"]).write_bytes(data)
                item["sha256"] = hashlib.sha256(data).hexdigest()
                self.assertTrue(any("band figure" in issue for issue in self.issues()))

    def test_invisible_svg_curves_cannot_pass_upload_gate(self):
        item = self.case["files"]["figures"][0]
        for attributes in ('stroke="none"', 'stroke="transparent"',
                           'stroke="black" stroke-width="0"', 'stroke="black" stroke-opacity="0"',
                           'stroke="black" opacity="0"', 'stroke="black" visibility="hidden"',
                           'stroke="black" display="none"', 'style="stroke:black;display:none"'):
            with self.subTest(attributes=attributes):
                data = ('<svg><text>Energy eV k-path bands</text><path d="M 0 0 L 10 10" '
                        + attributes + '/></svg>').encode()
                (self.root / item["path"]).write_bytes(data)
                item["sha256"] = hashlib.sha256(data).hexdigest()
                self.assertTrue(any("band figure" in issue for issue in self.issues()))

    def test_svg_curves_inherit_visible_group_styling(self):
        item = self.case["files"]["figures"][0]
        for style in ('stroke="black" stroke-width="1.5"', 'style="stroke:#00A6B4;stroke-width:2"'):
            with self.subTest(style=style):
                data = ('<svg><text>Energy eV k-path bands</text><g ' + style
                        + '><path d="M 0 0 L 10 10"/></g></svg>').encode()
                (self.root / item["path"]).write_bytes(data)
                item["sha256"] = hashlib.sha256(data).hexdigest()
                self.assertEqual(self.issues(), [])
        data = b'<svg><text>Energy eV k-path bands</text><g opacity="0"><path d="M 0 0 L 10 10" stroke="black"/></g></svg>'
        (self.root / item["path"]).write_bytes(data)
        item["sha256"] = hashlib.sha256(data).hexdigest()
        self.assertTrue(any("band figure" in issue for issue in self.issues()))

    def test_cross_record_symlink_cannot_supply_same_run_input(self):
        item = self.case["files"]["inputs"][0]
        foreign = self._add_file("data/calculations/3d/Si/foreign/inputs/INPUT", b"INPUT_PARAMETERS\ncalculation scf\n", "inputs")
        path = self.root / item["path"]
        path.unlink()
        path.symlink_to(self.root / foreign["path"])
        item["sha256"] = foreign["sha256"]
        self.lib.validate(self.root, [self.basis], [self.case])
        issues = self.issues()
        self.assertTrue(any("same calculation" in issue for issue in issues))
        self.assertTrue(any("input INPUT" in issue for issue in issues))

    def test_relative_stru_asset_path_requires_exact_bound_payload(self):
        import os
        item = self.case["files"]["inputs"][2]
        data = (self.root / item["path"]).read_bytes()
        reference = os.path.relpath(self.root / self.basis["files"][1]["path"], (self.root / item["path"]).parent)
        data = data.replace(b"test.orb", reference.encode())
        (self.root / item["path"]).write_bytes(data)
        item["sha256"] = hashlib.sha256(data).hexdigest()
        self.assertEqual(self.issues(), [])
        data = data.replace(reference.encode(), b"../assets/test.orb")
        (self.root / item["path"]).write_bytes(data)
        item["sha256"] = hashlib.sha256(data).hexdigest()
        self.assertTrue(any("STRU" in issue and "nao" in issue for issue in self.issues()))

    def test_relative_stru_alias_is_accepted_without_basename_guess(self):
        item = self.case["files"]["inputs"][2]
        data = (self.root / item["path"]).read_bytes().replace(b"test.orb", b"../assets/test.orb")
        (self.root / item["path"]).write_bytes(data)
        item["sha256"] = hashlib.sha256(data).hexdigest()
        self.case["species"][0]["asset_aliases"]["nao"] = "../assets/test.orb"
        self.assertEqual(self.issues(), [])

    def test_generic_auxiliary_element_label_needs_explicit_same_run_binding(self):
        auxiliary = self.basis["files"][2]
        data = (self.root / auxiliary["path"]).read_bytes().replace(b"Element Si", b"Element Ne")
        (self.root / auxiliary["path"]).write_bytes(data)
        auxiliary["sha256"] = hashlib.sha256(data).hexdigest()
        self.assertTrue(any("abf" in issue and "payload" in issue for issue in self.issues()))
        auxiliary["generic_auxiliary_binding_verified"] = True
        self.assertTrue(any("abf" in issue and "payload" in issue for issue in self.issues()))
        stru = self.case["files"]["inputs"][2]
        text = (self.root / stru["path"]).read_bytes().replace(b"test.abfs", b"ORBITAL_10U.abfs")
        (self.root / stru["path"]).write_bytes(text)
        stru["sha256"] = hashlib.sha256(text).hexdigest()
        self.case["species"][0]["asset_aliases"]["abf"] = "ORBITAL_10U.abfs"
        self.assertEqual(self.issues(), [])
        orbital = self.basis["files"][1]
        data = (self.root / orbital["path"]).read_bytes().replace(b"Element Si", b"Element Ne")
        (self.root / orbital["path"]).write_bytes(data)
        orbital["sha256"] = hashlib.sha256(data).hexdigest()
        self.assertTrue(any("nao" in issue and "payload" in issue for issue in self.issues()))

    def test_stru_requires_nao_and_abf_declarations_in_production_evidence(self):
        item = self.case["files"]["inputs"][2]
        data = (self.root / item["path"]).read_bytes().replace(b"ABFS_ORBITAL\ntest.abfs\n", b"")
        (self.root / item["path"]).write_bytes(data)
        item["sha256"] = hashlib.sha256(data).hexdigest()
        self.assertTrue(any("STRU" in issue and "abf" in issue for issue in self.issues()))

    def test_property_evidence_all_belongs_to_same_valid_record(self):
        self.case["properties"][0]["evidence"].append("data/calculations/3d/Si/foreign/logs/librpa.out")
        self.assertTrue(any("PBE" in issue and "band_gap" in issue for issue in self.issues()))

    def test_completeness_report_keeps_complete_and_incomplete_cases(self):
        import copy
        other = copy.deepcopy(self.case)
        other["id"] = "si-missing"
        other["species"] = []
        other["missing"] = ["exact assets unavailable"]
        other["files"] = {}
        other["properties"] = []
        report = self.lib.completeness_report(self.root, [self.basis], [self.case, other])
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["stats"]["total"], 2)
        self.assertEqual(report["stats"]["complete"], 1)
        self.assertEqual(report["stats"]["incomplete"], 1)
        self.assertEqual(report["cases"][0]["issues"], [])
        self.assertIn("inputs", report["cases"][1]["missing_categories"])
        self.assertIn("basis_binding", report["stats"]["missing_categories"])
        json.dumps(report, allow_nan=False)

    def test_report_schema_failure_blocks_and_keeps_case_evidence(self):
        self.case["software"]["abacus"]["commit"] = "abc1234"
        report = self.lib.completeness_report(self.root, [self.basis], [self.case])
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["stats"]["incomplete"], 1)
        self.assertTrue(report["integrity_issues"])
        self.assertIn("integrity", report["cases"][0]["missing_categories"])

    def test_cli_writes_complete_json_report_and_still_blocks(self):
        element_dir = self.root / "data/elements/Si/sets/Si-test"
        element_dir.mkdir(parents=True)
        (element_dir / "set.json").write_text(json.dumps(self.basis))
        self.case["software"]["librpa"]["commit"] = None
        (self.root / self.prefix / "record.json").write_text(json.dumps(self.case))
        output = self.root / "reports/completeness.json"
        result = subprocess.run([sys.executable, str(ROOT / "scripts/library.py"), "--root", str(self.root),
                                 "--check-completeness", "--completeness-report", str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("si-control", result.stdout)
        report = json.loads(output.read_text())
        self.assertEqual(report["stats"]["total"], 1)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("software", report["cases"][0]["missing_categories"])

    def test_explicit_sampled_path_gaps_are_not_misclassified_as_missing(self):
        for key in ("sampled_path_gap_ev", "path_gap"):
            with self.subTest(key=key):
                entry = self.case["properties"][0]
                entry["key"] = key
                entry["label"] = "Sampled path gap"
                self.assertEqual(self.issues(), [])
        entry = self.case["properties"][2]
        entry["key"] = "summary_value"
        entry["label"] = "Archived GW path gap"
        self.assertEqual(self.issues(), [])
        entry["label"] = "Unrelated observable"
        entry["definition"] = "GW reported quantity"
        self.assertTrue(any("GW" in issue and "band_gap" in issue for issue in self.issues()))

    def test_restricted_gw_observable_does_not_claim_global_gap(self):
        entry = self.case["properties"][2]
        entry["key"] = "restricted_frontier_path_gap"
        entry["definition"] = "raw-band-5 restricted frontier path gap; not a complete-spectrum fundamental gap"
        self.assertEqual(self.issues(), [])
        self.assertEqual(entry["key"], "restricted_frontier_path_gap")
        entry["key"] = "unscoped_observable"
        entry["definition"] = "GW observable"
        self.assertTrue(any("GW" in issue and "band_gap" in issue for issue in self.issues()))

    def test_hash_integrity_is_not_weakened_by_completeness(self):
        item = self.case["files"]["results"][0]
        (self.root / item["path"]).write_bytes(b"0 -2 2\n1 -1 3\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.lib.check_completeness(self.root, [self.basis], [self.case])

    def test_all_incomplete_case_ids_and_issues_are_reported(self):
        self.case["species"] = []
        self.case["missing"] = ["missing exact assets"]
        self.case["files"]["inputs"] = []
        with self.assertRaises(ValueError) as caught:
            self.lib.check_completeness(self.root, [self.basis], [self.case])
        self.assertIn("si-control", str(caught.exception))
        self.assertIn("species", str(caught.exception))
        self.assertIn("librpa.in", str(caught.exception))

    def test_workflows_require_strict_completeness_without_waivers(self):
        for name in ("validate.yml", "pages.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            self.assertIn("--check-completeness", text)
            self.assertNotIn("continue-on-error", text)


if __name__ == "__main__":
    unittest.main()
