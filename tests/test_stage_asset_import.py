"""Atomic asset writes preserve originals and reject target conflicts."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("stage_assets", ROOT / "scripts/import_stage_assets.py")
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)

class StageAssetWriteTests(unittest.TestCase):
    def test_immutable_creation_and_same_bytes_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            writes = {"data/asset.orb": b"original samples\n"}
            IMPORTER.apply(root, writes, {}, {})
            IMPORTER.apply(root, writes, {}, {})
            self.assertEqual((root / "data/asset.orb").read_bytes(), writes["data/asset.orb"])

    def test_conflict_prevents_other_creations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "existing.orb").write_bytes(b"existing")
            with self.assertRaisesRegex(ValueError, "immutable"):
                IMPORTER.apply(root, {"new.orb": b"new", "existing.orb": b"wrong"}, {}, {})
            self.assertFalse((root / "new.orb").exists())
            self.assertEqual((root / "existing.orb").read_bytes(), b"existing")

    def test_record_changed_rejects_before_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "record.json").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "record changed"):
                IMPORTER.apply(root, {"new.orb": b"new", "record.json": b"replacement"}, {"record.json": b"original"}, {})
            self.assertFalse((root / "new.orb").exists())
            self.assertEqual((root / "record.json").read_bytes(), b"changed")

    def test_changed_dependency_prevents_all_writes(self):
        for name in ("spec.json", "STRU", "KS_bands.dat", "receipt.json", "physical.orb"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                source = root / name
                source.write_bytes(b"reviewed bytes")
                readset = {source: (IMPORTER.sha256(b"reviewed bytes"), len(b"reviewed bytes"))}
                source.write_bytes(b"changed bytes")
                with self.assertRaisesRegex(ValueError, "readset changed"):
                    IMPORTER.apply(root, {"new/asset.orb": b"new"}, {}, readset)
                self.assertFalse((root / "new").exists())

    def test_missing_dependency_prevents_all_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "missing"
            with self.assertRaisesRegex(ValueError, "readset unavailable"):
                IMPORTER.apply(root, {"new.orb": b"new"}, {}, {source: (IMPORTER.sha256(b"old"), 3)})
            self.assertFalse((root / "new.orb").exists())

    def test_symlink_dependency_even_same_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "source"
            source.write_bytes(b"same")
            alias = root / "alias"
            alias.symlink_to(source)
            with self.assertRaisesRegex(ValueError, "symlink"):
                IMPORTER.apply(root, {"new.orb": b"new"}, {}, {alias: (IMPORTER.sha256(b"same"), 4)})
            self.assertFalse((root / "new.orb").exists())

    def test_verified_dependency_allows_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "source"
            source.write_bytes(b"same")
            IMPORTER.apply(root, {"new.orb": b"new"}, {}, {source: (IMPORTER.sha256(b"same"), 4)})
            self.assertEqual((root / "new.orb").read_bytes(), b"new")

    def test_unreviewed_spec_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            spec = root / "spec.json"
            spec.write_bytes(b"{}")
            with self.assertRaisesRegex(ValueError, "reviewed version"):
                IMPORTER.prepare(root, spec)

if __name__ == "__main__":
    unittest.main()
