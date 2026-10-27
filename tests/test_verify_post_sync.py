import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_unicode_record_paths_are_not_hidden_by_git_quoting(self):
        git(self.root, "commit", "-q", "--allow-empty", "-m", "base")
        relative = "data/calculations/3d/Si/案例/record.json"
        self._commit({relative: "{}"})
        self.assertEqual(verify_post_sync.changed_record_paths(self.root, "HEAD~1"),
                         [relative])
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


class RequiredLivePathTests(unittest.TestCase):
    SITE = "https://example.org/LibRPA-database"

    def setUp(self):
        self.entries = [
            {"path": "data/calculations/a.log"},
            {"path": "data/calculations/b.log", "tier": "referenced",
             "external_url": "https://huggingface.co/datasets/x/y/resolve/" + "a" * 40 + "/b.log",
             "external_url_backup": "https://hf-mirror.com/datasets/x/y/resolve/" + "a" * 40 + "/b.log"},
            {"path": "data/calculations/c.log"},
        ]
        self.catalog = json.dumps({"calculations": [{"files": {"logs": self.entries}}]}).encode()

    def test_changed_paths_are_mandatory_and_deduplicated_against_sample(self):
        with mock.patch.object(verify_post_sync, "fetch", return_value=self.catalog), \
                mock.patch.object(verify_post_sync.random, "sample", return_value=[self.entries[0]]), \
                mock.patch.object(verify_post_sync, "head_status", return_value=200) as head:
            self.assertTrue(verify_post_sync.verify_live(self.SITE, 1, False,
                                                         ["data/calculations/a.log", "data/calculations/b.log"]))
        checked_urls = {call.args[0] for call in head.call_args_list}
        self.assertEqual(checked_urls, {
            "https://example.org/LibRPA-database/data/calculations/a.log",
            self.entries[1]["external_url"],
        })

    def test_missing_changed_path_fails_instead_of_passing_random_sample(self):
        with mock.patch.object(verify_post_sync, "fetch", return_value=self.catalog), \
                mock.patch.object(verify_post_sync, "head_status") as head:
            self.assertFalse(verify_post_sync.verify_live(self.SITE, 40, False,
                                                          ["data/calculations/missing.log"]))
        head.assert_not_called()

    def test_required_referenced_path_uses_mirror_when_primary_fails(self):
        statuses = {self.entries[1]["external_url"]: 503,
                    self.entries[1]["external_url_backup"]: 200}
        with mock.patch.object(verify_post_sync, "fetch", return_value=self.catalog), \
                mock.patch.object(verify_post_sync, "head_status", side_effect=lambda url: statuses[url]) as head:
            self.assertTrue(verify_post_sync.verify_live(self.SITE, 0, False, ["data/calculations/b.log"]))
        self.assertEqual(head.call_count, 2)


class HashFallbackTests(unittest.TestCase):
    PRIMARY = "https://huggingface.co/datasets/x/y/resolve/" + "a" * 40
    BACKUP = "https://hf-mirror.com/datasets/x/y/resolve/" + "a" * 40

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "t")
        git(self.root, "config", "user.email", "t@example.org")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "base")
        self._reset_network()

    def tearDown(self):
        self._reset_network()
        self.tmp.cleanup()

    def _reset_network(self):
        verify_post_sync.HOST_FAILURES.clear()
        verify_post_sync.LAST_HIT.clear()
        limited = verify_post_sync.RATE_LIMITED_OUT
        if hasattr(limited, "clear"):
            limited.clear()
        else:
            verify_post_sync.RATE_LIMITED_OUT = False

    def _item(self, case, payload):
        path = f"data/calculations/3d/Si/{case}/logs/run.log"
        return {
            "path": path,
            "tier": "referenced",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "external_url": f"{self.PRIMARY}/{case}/run.log",
            "external_url_backup": f"{self.BACKUP}/{case}/run.log",
        }

    def _commit_records(self, records):
        for case, entries in records.items():
            target = self.root / f"data/calculations/3d/Si/{case}/record.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"files": {"logs": entries}}), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "records")

    def test_primary_hash_mismatch_tries_mirror_before_failing(self):
        payload = b"expected archived bytes"
        item = self._item("case-a", payload)
        self._commit_records({"case-a": [item]})
        responses = {item["external_url"]: b"wrong primary bytes",
                     item["external_url_backup"]: payload}
        with mock.patch.object(verify_post_sync, "fetch",
                               side_effect=lambda url: responses[url]) as fetch:
            self.assertTrue(verify_post_sync.verify_hashes(self.root, "HEAD~1"))
        self.assertEqual([call.args[0] for call in fetch.call_args_list],
                         [item["external_url"], item["external_url_backup"]])

    def test_primary_rate_limit_does_not_abort_after_mirror_success(self):
        payload = b"expected archived bytes"
        first = self._item("case-a", payload)
        second = self._item("case-b", payload)
        self._commit_records({"case-a": [first], "case-b": [second]})
        responses = {first["external_url_backup"]: payload,
                     second["external_url_backup"]: payload}
        calls = []

        def curl(url, max_time, extra):
            calls.append(url)
            if url.startswith("https://huggingface.co/"):
                return 0, 429
            output = Path(extra[extra.index("-o") + 1])
            output.write_bytes(responses[url])
            return 0, 200

        with mock.patch.object(verify_post_sync, "_curl", side_effect=curl), \
                mock.patch.object(verify_post_sync, "_backoff"), \
                mock.patch.object(verify_post_sync.time, "sleep"):
            self.assertTrue(verify_post_sync.verify_hashes(self.root, "HEAD~1"))
        attempts = 1 + len(verify_post_sync.RETRY_SLEEPS)
        self.assertEqual(calls.count(first["external_url"]), attempts)
        self.assertNotIn(second["external_url"], calls)
        self.assertEqual(calls.count(first["external_url_backup"]), 1)
        self.assertEqual(calls.count(second["external_url_backup"]), 1)

    def test_live_head_rate_limit_is_remembered_per_host(self):
        first = self._item("case-a", b"first")
        second = self._item("case-b", b"second")
        catalog = json.dumps({"calculations": [{"files": {"logs": [first, second]}}]}).encode()
        calls = []

        def curl(url, max_time, extra):
            calls.append(url)
            return (0, 429) if url.startswith("https://huggingface.co/") else (0, 200)

        with mock.patch.object(verify_post_sync, "fetch", return_value=catalog), \
                mock.patch.object(verify_post_sync, "_curl", side_effect=curl), \
                mock.patch.object(verify_post_sync, "_backoff"), \
                mock.patch.object(verify_post_sync.time, "sleep"):
            self.assertTrue(verify_post_sync.verify_live(
                "https://example.org/db", 0, False, [first["path"], second["path"]]))
        attempts = 1 + len(verify_post_sync.RETRY_SLEEPS)
        self.assertEqual(calls.count(first["external_url"]), attempts)
        self.assertNotIn(second["external_url"], calls)
        self.assertEqual(calls.count(first["external_url_backup"]), 1)
        self.assertEqual(calls.count(second["external_url_backup"]), 1)


class ChangedLivePathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "t")
        git(self.root, "config", "user.email", "t@example.org")

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_changed_paths_declared_by_target_catalog_are_required(self):
        case = "data/calculations/3d/Si/case"
        initial = {
            f"{case}/logs/remove.log": "remove",
            f"{case}/logs/external.log": "external",
            f"{case}/logs/modify.log": "old",
            f"{case}/logs/stable.log": "stable",
            f"{case}/record.json": "{}",
            "database/data.json": '{"calculations": []}',
        }
        for relative, content in initial.items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")

        (self.root / f"{case}/logs/remove.log").unlink()
        (self.root / f"{case}/logs/external.log").unlink()
        (self.root / f"{case}/logs/modify.log").write_text("new", encoding="utf-8")
        added = f"{case}/logs/新增 file.log"
        (self.root / added).write_text("added", encoding="utf-8")
        entries = [{"path": added},
                   {"path": f"{case}/logs/external.log", "tier": "referenced"},
                   {"path": f"{case}/logs/modify.log"},
                   {"path": f"{case}/logs/stable.log"}]
        catalog = {"calculations": [{"files": {"logs": entries}}]}
        (self.root / "database/data.json").write_text(json.dumps(catalog), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "target")

        changed = verify_post_sync.changed_live_paths(self.root, "HEAD")
        self.assertEqual(set(changed), {added, f"{case}/logs/external.log",
                                       f"{case}/logs/modify.log"})
        self.assertNotIn(f"{case}/logs/remove.log", changed)
        self.assertNotIn(f"{case}/logs/stable.log", changed)

    def test_explicit_base_covers_every_commit_in_one_push(self):
        case = "data/calculations/3d/Si/case"
        record = self.root / f"{case}/record.json"
        record.parent.mkdir(parents=True)
        record.write_text("{}", encoding="utf-8")
        catalog = self.root / "database/data.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text('{"calculations": []}', encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        first = f"{case}/logs/first.log"
        second = f"{case}/logs/second.log"
        for path, entries, message in ((first, [first], "first"),
                                       (second, [first, second], "second")):
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text(message, encoding="utf-8")
            value = {"calculations": [{"files": {"logs": [{"path": entry}
                                                         for entry in entries]}}]}
            catalog.write_text(json.dumps(value), encoding="utf-8")
            git(self.root, "add", "-A")
            git(self.root, "commit", "-q", "-m", message)
        changed = verify_post_sync.changed_live_paths(self.root, "HEAD", "HEAD~2")
        self.assertEqual(set(changed), {first, second})

    def test_rename_checks_the_new_path_not_the_removed_old_path(self):
        case = "data/calculations/3d/Si/case"
        old = f"{case}/logs/old.log"
        new = f"{case}/logs/new.log"
        target = self.root / old
        target.parent.mkdir(parents=True)
        target.write_text("same bytes", encoding="utf-8")
        catalog = self.root / "database/data.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({"calculations": [{"files": {"logs": [{"path": old}]}}]}),
                           encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        git(self.root, "mv", old, new)
        catalog.write_text(json.dumps({"calculations": [{"files": {"logs": [{"path": new}]}}]}),
                           encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "rename")
        changed = verify_post_sync.changed_live_paths(self.root, "HEAD")
        self.assertEqual(changed, [new])


class LiveDeploymentIdentityTests(unittest.TestCase):
    SITE = "https://example.org/LibRPA-database"
    COMMIT = "a" * 40

    def setUp(self):
        self.entries = [{"path": "data/calculations/a.log"}]
        self.catalog = json.dumps({"calculations": [{"files": {"logs": self.entries}}]}).encode()

    def _info(self, commit=COMMIT, dirty=False):
        return json.dumps({"schema_version": 1, "source_commit": commit,
                           "source_dirty": dirty}).encode()

    def test_matching_deployed_revision_runs_entry_checks(self):
        def fetch(url):
            if url.endswith("/build-info.json"):
                return self._info()
            if url.endswith("/database/data.json"):
                return self.catalog
            raise AssertionError(url)

        with mock.patch.object(verify_post_sync, "fetch", side_effect=fetch), \
                mock.patch.object(verify_post_sync, "head_status", return_value=200) as head:
            self.assertTrue(verify_post_sync.verify_live(
                self.SITE, 0, False, ["data/calculations/a.log"], expected_commit=self.COMMIT))
        head.assert_called_once()

    def test_wrong_deployed_revision_fails_before_entry_checks(self):
        with mock.patch.object(verify_post_sync, "fetch", return_value=self._info("b" * 40)), \
                mock.patch.object(verify_post_sync, "head_status") as head:
            self.assertFalse(verify_post_sync.verify_live(
                self.SITE, 0, False, expected_commit=self.COMMIT))
        head.assert_not_called()


class LocalUrlEncodingTests(unittest.TestCase):
    def test_spaces_unicode_and_url_delimiters_are_percent_encoded(self):
        item = {"path": "data/calculations/3d/Si/x/logs/α β%#1.dat"}
        self.assertEqual(
            verify_post_sync.live_entry_url("https://example.org/db", item),
            "https://example.org/db/data/calculations/3d/Si/x/logs/"
            "%CE%B1%20%CE%B2%25%231.dat")


if __name__ == "__main__":
    unittest.main()
