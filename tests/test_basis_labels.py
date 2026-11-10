"""The basis label is derived from the payload bytes, not from the index."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import basis_labels as labels  # noqa: E402


UPF = '<UPF version="2.0.1">\n  z_valence="    4.00"\n</UPF>\n'
ORB = (
    "Lmax 2\n"
    "Number of Sorbital-->       3\n"
    "Number of Porbital-->       3\n"
    "Number of Dorbital-->       2\n"
    "SUMMARY  END\n"
)
ABF = (
    "Lmax 8\n"
    "Number of Sorbital-->       12\n"
    "Number of Porbital-->       12\n"
    "Number of Dorbital-->       11\n"
    "Number of Forbital-->       9\n"
    "Number of Gorbital-->       9\n"
    "Number of Horbital-->       6\n"
    "Number of Iorbital-->       4\n"
    "Number of Jorbital-->       1\n"
    "Number of Korbital-->       1\n"
    "SUMMARY  END\n"
)


def payload(root, role, name, text):
    directory = root / role
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")
    return f"{role}/{name}"


def basis(root, set_id="Si-test"):
    return {
        "id": set_id,
        "element": "Si",
        "family": "SG15",
        "files": [
            {"role": "pp", "path": payload(root, "pp", "Si.upf", UPF), "sha256": "0" * 64},
            {"role": "nao", "path": payload(root, "nao", "Si.orb", ORB), "sha256": "1" * 64},
            {"role": "abf", "path": payload(root, "abf", "Si.abfs", ABF), "sha256": "2" * 64},
        ],
    }


class LabelFactsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valence_comes_from_the_pseudopotential(self):
        path = self.root / "Si.upf"
        path.write_text(UPF, encoding="utf-8")
        self.assertEqual(labels.valence_electrons(path), 4)

    def test_a_pseudopotential_without_z_valence_reports_none(self):
        path = self.root / "odd.upf"
        path.write_text("<UPF version='2.0.1'></UPF>", encoding="utf-8")
        self.assertIsNone(labels.valence_electrons(path))

    def test_orbital_dimension_is_count_times_degeneracy(self):
        path = self.root / "Si.orb"
        path.write_text(ORB, encoding="utf-8")
        counts = labels.channels(path)
        self.assertEqual(counts, {"S": 3, "P": 3, "D": 2})
        self.assertEqual(labels.shells(counts), "3s3p2d")
        self.assertEqual(labels.dimension(counts), 22)

    def test_auxiliary_keeps_channels_the_index_dropped(self):
        # 60 archived auxiliary bases record 365 while the file has 397; the
        # label must describe the file.
        path = self.root / "Si.abfs"
        path.write_text(ABF, encoding="utf-8")
        counts = labels.channels(path)
        self.assertEqual(labels.dimension(counts), 397)
        self.assertTrue(labels.shells(counts).endswith("1j1k"))

    def test_a_zero_channel_is_not_a_shell(self):
        # Headers list every l up to Lmax, so "Forbital--> 0" is common; showing
        # it would claim f functions the set does not have.
        path = self.root / "zero.orb"
        path.write_text(
            "Number of Sorbital-->       3\n"
            "Number of Porbital-->       3\n"
            "Number of Dorbital-->       2\n"
            "Number of Forbital-->       0\n",
            encoding="utf-8",
        )
        counts = labels.channels(path)
        self.assertEqual(counts, {"S": 3, "P": 3, "D": 2})
        self.assertEqual(labels.shells(counts), "3s3p2d")

    def test_an_unreadable_orbital_raises(self):
        path = self.root / "bad.orb"
        path.write_text("nothing here\n", encoding="utf-8")
        with self.assertRaisesRegex(labels.LabelError, "no angular-momentum"):
            labels.channels(path)


class LabelSentenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, rid, material, formula, *, gap=None, method="G0W0", rpa=None, set_id="Si-test"):
        properties = []
        if gap is not None:
            properties.append({"key": "band_gap", "method": method, "value": gap, "unit": "eV"})
        if rpa is not None:
            properties.append(
                {"key": "rpa_cohesive_energy", "method": "RPA", "value": rpa, "unit": "eV/atom"}
            )
        return {
            "id": rid,
            "material": material,
            "formula": formula,
            "dimension": "3d",
            "species": [{"element": "Si", "set_id": set_id}],
            "properties": properties,
        }

    def test_the_sentence_names_the_three_facts_and_the_results(self):
        b = basis(self.root)
        uses = labels.uses_by_set([self.record("si", "Si", "Si", gap=1.0596)])["Si-test"]
        block = labels.label_for_set(self.root, b, uses)
        text = block["sentence"]
        self.assertIn("4 valence electrons", text)
        self.assertIn("22 functions per atom", text)
        self.assertIn("397 auxiliary functions per atom", text)
        self.assertIn("Si GW gap 1.06 eV", text)
        self.assertNotIn("Si-test", text)

    def test_an_rpa_record_is_quoted_by_its_cohesive_energy(self):
        uses = labels.uses_by_set([self.record("si-rpa", "Si", "Si2", rpa=4.4349)])["Si-test"]
        self.assertIn("RPA cohesive energy 4.43 eV/atom", uses[0]["result"])

    def test_a_pbe_gap_is_not_quoted_as_a_gw_result(self):
        uses = labels.uses_by_set([self.record("dft", "Si", "Si", gap=0.56, method="PBE")])["Si-test"]
        self.assertIsNone(uses[0]["result"])

    def test_a_missing_valence_count_is_stated_not_omitted(self):
        # Otherwise the reader sees no valence line and reads it as zero.
        text = labels.sentence(
            "Si", None, {"shells": "3s3p2d", "dimension_per_atom": 22}, None, []
        )
        self.assertIn("not declared", text)

    def test_an_unused_set_says_so(self):
        b = basis(self.root)
        block = labels.label_for_set(self.root, b, [])
        self.assertIn("No calculation", block["sentence"])

    def test_build_labels_labels_every_usable_set_and_rebuilds_used_by(self):
        catalog = {
            "basis_sets": [basis(self.root)],
            "calculations": [self.record("si", "Si", "Si", gap=1.06)],
        }
        result = labels.build_labels(catalog, self.root)
        block = result["basis_sets"][0]["label"]
        self.assertEqual(block["valence_electrons"], 4)
        self.assertEqual(block["orbital"]["dimension_per_atom"], 22)
        self.assertEqual(block["auxiliary"]["dimension_per_atom"], 397)
        # used_by was hand-maintained and covered 30 of 76 sets; the records win
        self.assertEqual(result["basis_sets"][0]["used_by"], ["si"])

    def test_a_set_with_no_payload_is_left_unlabelled(self):
        catalog = {
            "basis_sets": [
                {"id": "Si-aims", "element": "Si", "family": "aims", "files": [
                    {"role": "species_defaults", "path": "x", "sha256": "0" * 64}
                ]}
            ],
            "calculations": [],
        }
        result = labels.build_labels(catalog, self.root)
        self.assertNotIn("label", result["basis_sets"][0])


if __name__ == "__main__":
    unittest.main()
