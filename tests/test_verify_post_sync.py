import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_post_sync  # noqa: E402


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


class TreeInvariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "t")
        git(self.root, "config", "user.email", "t@example.org")

    def tearDown(self):
        self.tmp.cleanup()

    def _commit(self, paths: dict[str, str]):
        for relative, content in paths.items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "wip")

    def test_manifest_only_tree_passes(self):
        self._commit({"data/calculations/3d/Si/x/record.json": "{}"})
        self.assertEqual(verify_post_sync.tree_offenders(self.root), [])

    def test_payload_bytes_under_calculations_are_offenders(self):
        self._commit({
            "data/calculations/3d/Si/x/record.json": "{}",
            "data/calculations/3d/Si/x/logs/keep.log": "bytes",
        })
        offenders = verify_post_sync.tree_offenders(self.root)
        self.assertEqual(offenders, ["data/calculations/3d/Si/x/logs/keep.log"])

    def test_basis_payloads_outside_calculations_do_not_offend(self):
        self._commit({
            "data/calculations/3d/Si/x/record.json": "{}",
            "data/elements/Si/sets/s/set.json": "{}",
        })
        self.assertEqual(verify_post_sync.tree_offenders(self.root), [])

    def test_changed_record_paths_filters_the_calculations_glob(self):
        self._commit({
            "data/calculations/3d/Si/x/record.json": "{}",
            "data/elements/Si/sets/s/set.json": "{}",
            "README.md": "x",
        })
        git(self.root, "commit", "-q", "--allow-empty", "-m", "second")
        changed = verify_post_sync.changed_record_paths(self.root, "HEAD~1")
        self.assertEqual(changed, [])
        (self.root / "data/calculations/3d/Si/x/record.json").write_text('{"id": 1}', encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "third")
        changed = verify_post_sync.changed_record_paths(self.root, "HEAD~1")
        self.assertEqual(changed, ["data/calculations/3d/Si/x/record.json"])


class LiveUrlResolutionTests(unittest.TestCase):
    SITE = "https://example.org/LibRPA-database"

    def test_referenced_entry_uses_external_url(self):
        item = {"path": "data/calculations/3d/Si/x/logs/a.log", "tier": "referenced",
                "external_url": "https://huggingface.co/datasets/x/resolve/main/data/a.log"}
        self.assertEqual(verify_post_sync.live_entry_url(self.SITE, item),
                         "https://huggingface.co/datasets/x/resolve/main/data/a.log")

    def test_local_entry_uses_deployed_site_path(self):
        item = {"path": "data/calculations/3d/Si/x/logs/a.log"}
        self.assertEqual(verify_post_sync.live_entry_url(self.SITE, item),
                         "https://example.org/LibRPA-database/data/calculations/3d/Si/x/logs/a.log")

    def test_trailing_slash_site_root_is_normalized(self):
        item = {"path": "p.log"}
        self.assertEqual(verify_post_sync.live_entry_url(self.SITE + "/", item),
                         "https://example.org/LibRPA-database/p.log")


class EntryIterationTests(unittest.TestCase):
    def test_all_calculation_groups_are_iterated(self):
        record = {"files": {group: [{"path": f"{group}/f"}] for group in
                            ("inputs", "results", "logs", "figures")}}
        paths = [item["path"] for item in verify_post_sync.iter_entries(record)]
        self.assertEqual(sorted(paths), ["figures/f", "inputs/f", "logs/f", "results/f"])


if __name__ == "__main__":
    unittest.main()
