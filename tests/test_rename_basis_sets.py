"""A set id must say what the basis is, and stay unique."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import rename_basis_sets as rename  # noqa: E402


UPF = '<UPF version="2.0.1">\n  z_valence="    4.00"\n</UPF>\n'
ORB = (
    "Lmax 2\n"
    "Number of Sorbital-->       3\n"
    "Number of Porbital-->       3\n"
    "Number of Dorbital-->       2\n"
    "SUMMARY  END\n"
)
ABF = (
    "Lmax 3\n"
    "Number of Sorbital-->       3\n"
    "Number of Porbital-->       2\n"
    "Number of Dorbital-->       1\n"
    "SUMMARY  END\n"
)


def write(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_set(
    root: pathlib.Path,
    element: str,
    set_id: str,
    family: str,
    *,
    upf: str = UPF,
    orb: str = ORB,
    abf: str | None = ABF,
) -> pathlib.Path:
    payloads = []
    for role, name, text, folder in (
        ("pp", "p.upf", upf, "pseudopotentials"),
        ("nao", "n.orb", orb, "orbitals"),
    ):
        path = write(root / "data" / "elements" / element / folder / f"{set_id}-{name}", text)
        payloads.append({"role": role, "path": str(path.relative_to(root)), "sha256": "0" * 64})
    if abf is not None:
        path = write(root / "data" / "elements" / element / "auxiliary" / f"{set_id}-a.abfs", abf)
        payloads.append({"role": "abf", "path": str(path.relative_to(root)), "sha256": "1" * 64})
    document = {
        "schema_version": 1,
        "id": set_id,
        "element": element,
        "family": family,
        "files": payloads,
    }
    path = root / "data" / "elements" / element / "sets" / set_id / "set.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def make_record(root: pathlib.Path, record_id: str, set_id: str) -> None:
    path = root / "data" / "calculations" / "3d" / "Si" / record_id / "record.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "id": record_id,
                "species": [{"element": "Si", "set_id": set_id}],
                "properties": [],
            }
        ),
        encoding="utf-8",
    )


class FactIdTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_the_id_states_the_valence_and_both_sizes(self) -> None:
        make_set(self.root, "Si", "Si-SG15-e11ce28", "SG15")
        mapping = rename.build_mapping(self.root)
        self.assertEqual(
            mapping["Si-SG15-e11ce28"]["new_id"], "Si-SG15-4e-3s3p2d-22-abf14"
        )

    def test_a_set_without_an_auxiliary_basis_says_so(self) -> None:
        make_set(self.root, "Si", "Si-ONCV-aaaa", "ONCV", abf=None)
        new_id = rename.build_mapping(self.root)["Si-ONCV-aaaa"]["new_id"]
        self.assertTrue(new_id.endswith("-noabf"), new_id)

    def test_a_species_defaults_fragment_is_named_by_species_and_tier(self) -> None:
        # No pp/nao means no sizes; what the file does declare is the species and
        # (sometimes) the FHI-aims tier, which is what separates two fragments.
        path = self.root / "data" / "elements" / "Si" / "sets" / "Si-aims-aaaa" / "set.json"
        path.parent.mkdir(parents=True)
        payload = write(
            self.root / "data" / "elements" / "Si" / "species_defaults" / "x.in",
            "#  Suggested \"intermediate\" defaults for Si atom\n  species        Si\n",
        )
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "Si-aims-aaaa",
                    "element": "Si",
                    "family": "FHI-aims species defaults (control.in inline)",
                    "files": [
                        {"role": "species_defaults", "path": str(payload.relative_to(self.root)), "sha256": "0" * 64}
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            rename.build_mapping(self.root)["Si-aims-aaaa"]["new_id"], "Si-aims-intermediate"
        )

    def test_a_fragment_for_another_element_says_which(self) -> None:
        path = self.root / "data" / "elements" / "Ga" / "sets" / "Ga-aims-bbbb" / "set.json"
        path.parent.mkdir(parents=True)
        payload = write(
            self.root / "data" / "elements" / "Ga" / "species_defaults" / "sb.in",
            "  species        Sb\n",
        )
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "Ga-aims-bbbb",
                    "element": "Ga",
                    "family": "FHI-aims species defaults (control.in inline)",
                    "files": [
                        {"role": "species_defaults", "path": str(payload.relative_to(self.root)), "sha256": "0" * 64}
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            rename.build_mapping(self.root)["Ga-aims-bbbb"]["new_id"], "Ga-aims-Sb"
        )

    def test_same_facts_different_bytes_get_a_content_suffix(self) -> None:
        # Same valence, same shells, same dimensions: the facts cannot separate
        # them, so the content hash does. The two fixtures differ only by the
        # recorded payload digest, which is exactly the situation in the real
        # library (Mo-GTH and Mo-SG15 both read 14e-6s3p3d2f-44).
        make_set(self.root, "Si", "Si-GTH-aaaa", "GTH", abf=None)
        make_set(self.root, "Si", "Si-SG15-bbbb", "SG15", abf=None)
        document_path = self.root / "data" / "elements" / "Si" / "sets" / "Si-GTH-aaaa" / "set.json"
        document = json.loads(document_path.read_text())
        for item in document["files"]:
            item["sha256"] = "a" * 64
        document["family"] = "SG15"
        document_path.write_text(json.dumps(document), encoding="utf-8")
        mapping = rename.build_mapping(self.root)
        new_ids = sorted(entry["new_id"] for entry in mapping.values())
        self.assertEqual(len(set(new_ids)), 2, new_ids)
        self.assertTrue(all(len(value.rsplit("-", 1)[-1]) == 8 for value in new_ids), new_ids)

    def test_byte_identical_records_nothing_used_must_be_merged(self) -> None:
        make_set(self.root, "Si", "Si-producer-aaaa", "Recovered producer-bound assets")
        make_set(self.root, "Si", "Si-producer-bbbb", "Recovered producer-bound assets")
        with self.assertRaisesRegex(rename.RenameError, "merge them into one set"):
            rename.build_mapping(self.root)

    def test_identical_bytes_are_told_apart_by_the_calculation_that_used_them(self) -> None:
        make_set(self.root, "Si", "Si-producer-aaaa", "Recovered producer-bound assets")
        make_set(self.root, "Si", "Si-producer-bbbb", "Recovered producer-bound assets")
        make_record(self.root, "first-case", "Si-producer-aaaa")
        make_record(self.root, "second-case", "Si-producer-bbbb")
        mapping = rename.build_mapping(self.root)
        self.assertTrue(mapping["Si-producer-aaaa"]["new_id"].endswith("first-case"))
        self.assertTrue(mapping["Si-producer-bbbb"]["new_id"].endswith("second-case"))

    def test_the_mapping_has_no_collisions_and_only_safe_characters(self) -> None:
        make_set(self.root, "Si", "Si-SG15-aaaa", "SG15")
        make_set(self.root, "Si", "Si-ONCV-bbbb", "ONCV", abf=None)
        mapping = rename.build_mapping(self.root)
        new_ids = [entry["new_id"] for entry in mapping.values()]
        self.assertEqual(len(new_ids), len(set(new_ids)))
        for value in new_ids:
            self.assertRegex(value, r"^[A-Za-z0-9-]+$")


class ApplyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_apply_moves_the_directory_and_rewrites_the_reference(self) -> None:
        make_set(self.root, "Si", "Si-SG15-aaaa", "SG15")
        make_record(self.root, "case", "Si-SG15-aaaa")
        mapping = rename.build_mapping(self.root)
        rename.apply_mapping(self.root, mapping)
        new_id = mapping["Si-SG15-aaaa"]["new_id"]
        self.assertTrue((self.root / "data" / "elements" / "Si" / "sets" / new_id).is_dir())
        self.assertFalse((self.root / "data" / "elements" / "Si" / "sets" / "Si-SG15-aaaa").exists())
        record = json.loads(
            (self.root / "data" / "calculations" / "3d" / "Si" / "case" / "record.json").read_text()
        )
        self.assertEqual(record["species"][0]["set_id"], new_id)
        document = json.loads(
            (self.root / "data" / "elements" / "Si" / "sets" / new_id / "set.json").read_text()
        )
        self.assertEqual(document["id"], new_id)
        self.assertEqual(document["previous_id"], "Si-SG15-aaaa")

    def test_an_existing_destination_is_refused(self) -> None:
        make_set(self.root, "Si", "Si-SG15-aaaa", "SG15")
        mapping = rename.build_mapping(self.root)
        target = self.root / "data" / "elements" / "Si" / "sets" / mapping["Si-SG15-aaaa"]["new_id"]
        target.mkdir(parents=True)
        with self.assertRaisesRegex(rename.RenameError, "already exists"):
            rename.apply_mapping(self.root, mapping)


if __name__ == "__main__":
    unittest.main()
