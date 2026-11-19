"""Synthetic record fixtures for optional, explicitly sourced experimental gaps."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import library


class ExperimentalGapTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.case = {"id": "test", "material": "Si", "dimension": "3d",
                     "species": [{"element": "Si"}], "software": {"abacus": {}, "librpa": {}}}
        self.gap = {"value": 0, "unit": "eV", "definition": "Synthetic measured transition",
                    "source": {"citation": "Fixture", "locator": "Table A", "doi": "10.9999/test-only"}}

    def validate(self):
        library.validate(self.root, [], [self.case])

    def reject(self, target, key, values):
        for value in values:
            with self.subTest(key=key, value=value):
                original = target.copy()
                target[key] = value
                try:
                    with self.assertRaisesRegex(ValueError, r"experimental_gap"):
                        self.validate()
                finally:
                    target.clear()
                    target.update(original)

    def test_absent_null_and_unpaired_measurements(self):
        self.validate()
        self.case["experimental_gap"] = None
        self.validate()
        self.case["experimental_gap"] = self.gap
        self.validate()
        self.assertNotIn("compatibility", self.gap)
        for compatibility in (None, {}, {"methods": {"exx": {"compatible": False}}}):
            self.gap["compatibility"] = compatibility
            self.validate()

    def test_catalog_exposes_null_for_older_sources_and_preserves_measurements(self):
        record = self.root / "data/calculations/3d/Si/test/record.json"
        record.parent.mkdir(parents=True)
        for fields in ({}, {"experimental_gap": None}, {"experimental_gap": self.gap}):
            source = {**self.case, **fields}
            record.write_text(json.dumps(source), encoding="utf-8")
            catalog = library.build_catalog(self.root)
            self.assertEqual(catalog["calculations"][0]["experimental_gap"], fields.get("experimental_gap"))
            self.assertEqual(json.loads(record.read_text(encoding="utf-8")), source)

    def test_core_fields_are_required(self):
        self.reject(self.case, "experimental_gap", [[], 0, "", {}])
        self.case["experimental_gap"] = self.gap
        self.reject(self.gap, "value", [None, False, "0", -0.01, float("nan"), float("inf")])
        self.reject(self.gap, "unit", [None, "Ha", ""])
        self.reject(self.gap, "definition", [None, "   ", 12])
        self.reject(self.gap, "source", [None, {}, []])

    def test_citation_locator_and_resolvable_identifier(self):
        self.case["experimental_gap"] = self.gap
        source = self.gap["source"]
        for field in ("citation", "locator"):
            self.reject(source, field, [None, 1, " "])
        self.reject(source, "doi", [None, True, "10.bad/source", "10.1234/", "10.1234/w h"])
        del source["doi"]
        source["url"] = "https://example.invalid/paper#table-1"
        self.validate()
        self.reject(source, "url", [None, "http://example.org", "https:///path", "not a URL",
                                    "https://user:secret@example.invalid", "https://example.invalid:bad/"])

    def test_sample_values_can_be_partial_null_or_complete(self):
        self.case["experimental_gap"] = self.gap
        for sample in (None, {}, {"phase": None, "space_group": None, "lattice_angstrom": None,
                                  "angles_deg": {"alpha": None, "gamma": 89.9}},
                       {"phase": "test phase", "space_group": "fixture group", "lattice_angstrom": {"a": 4.2},
                        "angles_deg": {"alpha": 70, "beta": 90, "gamma": 130}}):
            self.gap["sample_structure"] = sample
            self.validate()
        for conditions in (None, {}, {"temperature_K": None, "note": None},
                           {"temperature_K": 0, "note": "Synthetic reference condition"}):
            self.gap["conditions"] = conditions
            self.validate()

    def test_sample_field_types_and_bounds(self):
        self.case["experimental_gap"] = self.gap
        self.reject(self.gap, "sample_structure", [[], 5])
        sample = self.gap["sample_structure"] = {}
        for field in ("phase", "space_group"):
            self.reject(sample, field, [1, " "])
        for field, axes in (("lattice_angstrom", ("a", "b", "c")), ("angles_deg", ("alpha", "beta", "gamma"))):
            self.reject(sample, field, [[], "", {"typo": 1.0}])
            coordinates = sample[field] = {}
            for axis in axes:
                bad = [True, "90", -1, 0, float("inf"), float("nan")]
                self.reject(coordinates, axis, bad + ([180, 181] if field == "angles_deg" else []))
        self.reject(self.gap, "conditions", [[], False])
        conditions = self.gap["conditions"] = {}
        self.reject(conditions, "temperature_K", [False, -0.1, "300", float("inf"), float("nan")])
        self.reject(conditions, "note", [5, " \t"])

    def test_malformed_attestation_containers_and_nonboolean_flags(self):
        self.case["experimental_gap"] = self.gap
        self.reject(self.gap, "compatibility", [[], 0])
        compatibility = self.gap["compatibility"] = {}
        self.reject(compatibility, "methods", [[], False])
        methods = compatibility["methods"] = {}
        self.reject(methods, "g0w0", [None, [], {}, {"compatible": "true"}, {"compatible": 1}])

    def test_approved_methods_bind_to_verified_structure_and_record(self):
        geometry = "lattice_vector 1 0 0\nlattice_vector 0 1 0\nlattice_vector 0 0 1\natom 0 0 0 Si\n"
        evidence = "data/calculations/3d/Si/test/inputs/geometry.in"
        path = self.root / evidence
        path.parent.mkdir(parents=True)
        path.write_bytes(geometry.encode())
        result = path.parent.parent / "results/gap.txt"
        result.parent.mkdir()
        result.write_bytes(b"1.0\n")
        result_path = result.relative_to(self.root).as_posix()
        self.case["files"] = {"inputs": [{"path": evidence, "sha256": hashlib.sha256(geometry.encode()).hexdigest()}],
                              "results": [{"path": result_path, "sha256": hashlib.sha256(result.read_bytes()).hexdigest()}]}
        self.case["properties"] = [{"key": "band_gap", "category": "electronic", "method": "G0W0", "label": "Gap",
                                    "value": 1.0, "unit": "eV", "definition": "Fixture gap", "status": "reported",
                                    "evidence": [result_path]}]
        fingerprint, _ = library._structure_fingerprint(geometry, "geometry.in", "3d")
        self.case["structure_identity"] = {"algorithm": "cell-sites-v1", "sha256": fingerprint, "evidence": evidence}
        self.case["experimental_gap"] = self.gap
        match = {"compatible": True, "observable": "property:band_gap:G0W0", "reason": "Reviewed test observable"}
        compatibility = self.gap["compatibility"] = {"record_id": "test", "structure_sha256": fingerprint,
                                                    "structure_note": "Reviewed test geometry", "methods": {"g0w0": match}}
        self.validate()
        self.reject(compatibility, "record_id", [None, "another-id"])
        self.reject(compatibility, "structure_sha256", [None, "a" * 64])
        self.reject(compatibility, "structure_note", [None, " "])
        self.reject(self.case, "structure_identity", [None])
        self.reject(match, "observable", [None, " "])
        self.reject(match, "reason", [None, " "])
        second = match.copy()
        second.pop("reason")
        self.reject(compatibility["methods"], "gw", [second])
        self.case["structure_identity"]["algorithm"] = "unverified"
        with self.assertRaisesRegex(ValueError, "structure_identity"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
