"""资产名称证据、目录不可变性及推荐引用的轻量回归测试。"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from asset_names import enrich_catalog
import library


def asset(role="pp", digest="a" * 64, label="payload", suffix=None):
    suffix = suffix if suffix is not None else {"pp": ".upf", "nao": ".orb", "for_aux": ".orb", "abf": ".abfs"}[role]
    return {"role": role, "path": f"data/elements/Si/assets/{digest}{suffix}",
            "sha256": digest, "label": label}


def basis(set_id="Si-test", files=None):
    return {"id": set_id, "element": "Si", "family": "GTH", "files": files or [asset()]}


def calculation(case_id="si-control", set_id="Si-test", aliases=None):
    return {
        "id": case_id, "dimension": "3d", "status": "gw_validated",
        "species": [{"element": "Si", "set_id": set_id, "asset_aliases": aliases or {}}],
        "software": {"abacus": {"commit": None}, "librpa": {"commit": None}},
        "files": {},
    }


class AssetNameTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"schema_version": 1, "basis_sets": [basis()],
                        "calculations": [calculation()]}

    def enriched_file(self, index=0):
        return enrich_catalog(self.catalog)["basis_sets"][0]["files"][index]

    def aliases(self, value):
        self.catalog["calculations"][0]["species"][0]["asset_aliases"] = value

    def test_recorded_label_is_preferred_and_all_aliases_are_retained(self):
        self.catalog["basis_sets"][0]["files"][0]["label"] = "Si_original.upf"
        self.aliases({"pp": "Si_alternative.upf"})
        item = self.enriched_file()
        self.assertEqual(item["display_name"], "Si_original.upf")
        self.assertEqual(item["download_name"], "Si_original.upf")
        self.assertEqual(item["original_names"], ["Si_alternative.upf", "Si_original.upf"])
        self.assertEqual(item["name_source"], "recorded")

    def test_exact_calculation_aliases_restore_each_basis_role(self):
        roles = {"pp": "Si.upf", "nao": "Si_physical.orb", "for_aux": "Si_for_aux.orb", "abf": "Si.abfs"}
        self.catalog["basis_sets"][0]["files"] = [asset(role) for role in roles]
        self.aliases(roles)
        for item in enrich_catalog(self.catalog)["basis_sets"][0]["files"]:
            self.assertEqual(item["display_name"], roles[item["role"]])
            self.assertEqual(item["original_names"], [roles[item["role"]]])
            self.assertEqual(item["name_source"], "recorded")
            self.assertEqual(item["label"], "payload")

    def test_abf_uses_abf_key_not_abfs_key(self):
        self.catalog["basis_sets"][0]["files"] = [asset("abf")]
        self.aliases({"abfs": "unbound.abfs"})
        self.assertEqual(self.enriched_file()["original_names"], [])
        self.aliases({"abf": "bound.abfs"})
        self.assertEqual(self.enriched_file()["display_name"], "bound.abfs")

    def test_unsafe_placeholder_hash_and_wrong_suffix_names_are_ignored(self):
        bad_names = [None, 42, [], {}, "", ".", "..", "payload", "payload.upf", "hash.upf",
                     "a" * 64 + ".upf", "ABCDEF123456.upf", "Si.orb", "Si",
                     "../Si.upf", "sub/Si.upf", "sub\\Si.upf", "C:Si.upf", "Si..upf",
                     "Si\x00.upf", "Si\n.upf", "Si\x7f.upf", "Si\u202e.upf", " Si.upf "]
        for name in bad_names:
            with self.subTest(name=name):
                self.catalog["basis_sets"][0]["files"][0]["label"] = name
                self.aliases({"pp": name})
                item = self.enriched_file()
                self.assertEqual(item["name_source"], "descriptive_alias")
                self.assertEqual(item["original_names"], [])
                self.assertEqual(item["download_name"], "Si_GTH_pp_aaaaaaaaaaaa.upf")

    def test_malformed_alias_container_is_ignored(self):
        for aliases in (None, "Si.upf", ["Si.upf"]):
            with self.subTest(aliases=aliases):
                self.aliases(aliases)
                self.assertEqual(self.enriched_file()["original_names"], [])

    def test_candidate_alias_is_not_evidence_of_actual_use(self):
        case = self.catalog["calculations"][0]
        case["species"] = []
        case["basis_candidates"] = [{"element": "Si", "set_id": "Si-test", "scope": "contextual",
                                     "asset_aliases": {"pp": "candidate.upf"}}]
        self.assertEqual(self.enriched_file()["original_names"], [])
        self.assertEqual(self.enriched_file()["name_source"], "descriptive_alias")

    def test_missing_or_cross_element_species_binding_supplies_no_evidence(self):
        self.aliases({"pp": "Si.upf"})
        species = self.catalog["calculations"][0]["species"][0]
        species["set_id"] = "missing"
        self.assertEqual(self.enriched_file()["original_names"], [])
        species.update({"set_id": "Si-test", "element": "C"})
        self.assertEqual(self.enriched_file()["original_names"], [])

    def test_shared_hash_and_role_share_names_not_calculation_bindings(self):
        self.catalog["basis_sets"].append(basis("Si-shared"))
        self.aliases({"pp": "Si.upf"})
        original_cases = deepcopy(self.catalog["calculations"])
        result = enrich_catalog(self.catalog)
        self.assertEqual(result["basis_sets"][1]["files"][0]["original_names"], ["Si.upf"])
        self.assertEqual(result["calculations"], original_cases)
        self.assertNotIn("used_by", result["basis_sets"][1])

    def test_shared_hash_does_not_share_names_across_roles_or_suffixes(self):
        self.catalog["basis_sets"][0]["files"] = [
            asset("nao", label="Si_physical.orb"), asset("for_aux"),
        ]
        self.assertEqual(self.enriched_file(1)["original_names"], [])
        self.catalog["basis_sets"].append(basis("Si-other-suffix", [asset("nao", suffix=".txt")]))
        other = enrich_catalog(self.catalog)["basis_sets"][1]["files"][0]
        self.assertEqual(other["original_names"], [])

    def test_multiple_exact_aliases_are_deduplicated_and_deterministic(self):
        self.catalog["calculations"] = [
            calculation("one", aliases={"pp": "Si_z.upf"}),
            calculation("two", aliases={"pp": "Si_a.upf"}),
            calculation("three", aliases={"pp": "Si_z.upf"}),
        ]
        item = self.enriched_file()
        self.assertEqual(item["original_names"], ["Si_a.upf", "Si_z.upf"])
        self.assertEqual(item["display_name"], "Si_a.upf")
        self.catalog["calculations"].reverse()
        self.assertEqual(self.enriched_file(), item)

    def test_ambiguous_role_does_not_bind_alias_even_for_duplicate_hash(self):
        self.aliases({"pp": "Si.upf"})
        for digest in ("a" * 64, "b" * 64):
            with self.subTest(digest=digest):
                self.catalog["basis_sets"][0]["files"] = [asset(), asset(digest=digest)]
                for item in enrich_catalog(self.catalog)["basis_sets"][0]["files"]:
                    self.assertEqual(item["original_names"], [])
                    self.assertEqual(item["name_source"], "descriptive_alias")

    def test_same_basename_for_different_hashes_never_merges_asset_identity(self):
        self.catalog["basis_sets"][0]["files"] = [asset(label="Si.upf")]
        self.catalog["basis_sets"].append(basis("Si-second", [asset(digest="b" * 64, label="Si.upf")]))
        self.aliases({"pp": "Si_first_only.upf"})
        result = enrich_catalog(self.catalog)["basis_sets"]
        first, second = (entry["files"][0] for entry in result)
        self.assertEqual(first["display_name"], second["display_name"])
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assertNotEqual(first["path"], second["path"])
        self.assertEqual(second["original_names"], ["Si.upf"])

    def test_unknown_names_are_unique_descriptive_aliases_with_actual_suffix(self):
        self.catalog["basis_sets"][0]["files"] = [asset(suffix=".UPF"), asset(digest="b" * 64)]
        first, second = enrich_catalog(self.catalog)["basis_sets"][0]["files"]
        self.assertEqual(first["display_name"], "Si_GTH_pp_aaaaaaaaaaaa.UPF")
        self.assertEqual(second["display_name"], "Si_GTH_pp_bbbbbbbbbbbb.upf")
        self.assertEqual(first["original_names"], [])
        self.assertEqual(first["name_source"], "descriptive_alias")
        self.catalog["basis_sets"][0].pop("family")
        self.assertIn("unknown-family", self.enriched_file()["display_name"])

    def test_descriptive_components_cannot_inject_paths(self):
        self.catalog["basis_sets"][0]["family"] = "../GTH\\bad\nname"
        item = self.enriched_file()
        self.assertEqual(item["display_name"], "Si_GTH-bad-name_pp_aaaaaaaaaaaa.upf")

    def test_generation_evidence_uses_archive_basename_not_inferred_original(self):
        item = asset("generation_evidence", suffix=".json", label="original.json")
        item["path"] = "data/elements/Si/evidence/evidence-0_manifest.json"
        self.catalog["basis_sets"][0]["files"].append(item)
        result = self.enriched_file(1)
        self.assertEqual(result["display_name"], "evidence-0_manifest.json")
        self.assertEqual(result["name_source"], "archive_name")
        self.assertEqual(result["original_names"], [])
        item["path"] = "data/elements/Si/evidence/evidence-1_INPUT"
        self.assertEqual(self.enriched_file(1)["display_name"], "evidence-1_INPUT")

    def test_hash_generation_evidence_uses_descriptive_alias(self):
        self.catalog["basis_sets"][0]["files"].append(asset("generation_evidence", suffix=".json"))
        self.assertEqual(self.enriched_file(1)["name_source"], "descriptive_alias")

    def test_enrichment_is_deeply_immutable_and_idempotent(self):
        self.aliases({"pp": "Si.upf"})
        before = deepcopy(self.catalog)
        result = enrich_catalog(self.catalog)
        self.assertEqual(self.catalog, before)
        self.assertEqual(enrich_catalog(result), result)
        self.assertEqual(result["basis_sets"][0]["files"][0]["path"], before["basis_sets"][0]["files"][0]["path"])
        self.assertEqual(result["basis_sets"][0]["files"][0]["sha256"], "a" * 64)
        result["calculations"][0]["species"][0]["asset_aliases"]["pp"] = "changed.upf"
        result["basis_sets"][0]["files"][0]["label"] = "changed.upf"
        self.assertEqual(self.catalog, before)


class CatalogIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.payload = b"small scientific payload\n"
        item = asset(digest=hashlib.sha256(self.payload).hexdigest())
        self.payload_path = self.root / item["path"]
        self.payload_path.parent.mkdir(parents=True)
        self.payload_path.write_bytes(self.payload)
        self.set = basis(files=[item])
        self.case = calculation(aliases={"pp": "Si.upf"})

    def test_build_validates_then_enriches_without_mutating_loaded_records(self):
        before = deepcopy(([self.set], [self.case]))
        with patch.object(library, "load_records", return_value=([self.set], [self.case])):
            result = library.build_catalog(self.root)
        self.assertEqual(([self.set], [self.case]), before)
        self.assertEqual(result["basis_sets"][0]["files"][0]["display_name"], "Si.upf")
        self.payload_path.write_bytes(b"changed payload")
        with patch.object(library, "load_records", return_value=([self.set], [self.case])), \
                patch.object(library, "enrich_catalog") as enrich:
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                library.build_catalog(self.root)
            enrich.assert_not_called()

    def test_asset_hashing_does_not_load_full_payload_with_read_bytes(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("必须流式读取")):
            library.validate(self.root, [self.set], [self.case])

    def test_build_keeps_source_json_and_payload_bytes_unchanged(self):
        paths = [self.root / "data/elements/Si/sets/Si-test/set.json",
                 self.root / "data/calculations/3d/Si/si-control/record.json"]
        for path, record in zip(paths, (self.set, self.case)):
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(record), encoding="utf-8")
        snapshots = [path.read_bytes() for path in paths]
        result = library.build_catalog(self.root)
        self.assertEqual(result["basis_sets"][0]["files"][0]["name_source"], "recorded")
        self.assertEqual([path.read_bytes() for path in paths], snapshots)
        self.assertEqual(self.payload_path.read_bytes(), self.payload)

    def test_recommendation_can_reference_later_case(self):
        self.case["recommendation"] = {"scope": "Si fixture only", "evidence_case_ids": ["later"]}
        later = calculation("later")
        library.validate(self.root, [self.set], [self.case, later])
        library.validate(self.root, [self.set], [later, self.case])

    def test_unknown_recommendation_case_is_rejected(self):
        self.case["recommendation"] = {"scope": "Si fixture only", "evidence_case_ids": ["missing"]}
        with self.assertRaisesRegex(ValueError, "unknown case"):
            library.validate(self.root, [self.set], [self.case])

    def test_precollected_ids_do_not_hide_duplicate_or_invalid_ids(self):
        self.case["recommendation"] = {"scope": "Si fixture only", "evidence_case_ids": ["si-control"]}
        with self.assertRaisesRegex(ValueError, "duplicate id"):
            library.validate(self.root, [self.set], [self.case, deepcopy(self.case)])
        invalid = calculation()
        invalid["id"] = []
        with self.assertRaisesRegex(ValueError, "missing or duplicate id"):
            library.validate(self.root, [self.set], [self.case, invalid])


if __name__ == "__main__":
    unittest.main()
