"""静态部署打包的最小样例回归，不读取实际科研大文件。"""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_site", ROOT / "scripts/build_site.py")
SITE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SITE)


class SiteBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "repository"
        self.root.mkdir()
        self.output = self.root / "_site"
        self.write("index.html", '<a href="database/">Database</a>')
        self.write("database/index.html", '<link href="style.css" rel="stylesheet"><script type="module" src="app.js?v=1"></script><a href="../CONTRIBUTING.md">Contribute</a>')
        self.write("database/style.css", 'body { background: url("assets/background.svg"); }')
        self.write("database/assets/background.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.write("database/app.js", 'import { value } from "./search.mjs"; fetch("data.json");')
        self.write("database/search.mjs", "export const value = 1;")
        self.write("README.md", "[Database](database/index.html)")
        self.write("CONTRIBUTING.md", "[Guide](references/database.md)")
        self.write("LICENSE", "Example license")
        self.write("references/database.md", "Contribution guide")
        self.write("data/elements/Si/pseudopotentials/example.upf", b"preserved basis\n")
        self.write("data/calculations/3d/Si/si-test/results/bands.dat", b"0 1 2\n")
        self.write("data/calculations/3d/Si/si-test/logs/run.log", b"recorded output\n")
        self.basis = {"id": "Si-test", "element": "Si", "files": [self.payload("data/elements/Si/pseudopotentials/example.upf")]}
        self.case = {"id": "si-test", "dimension": "3d", "material": "Si", "files": {
            "results": [self.payload("data/calculations/3d/Si/si-test/results/bands.dat")],
            "logs": [self.payload("data/calculations/3d/Si/si-test/logs/run.log")],
        }}
        self.catalog = {"schema_version": 1, "basis_sets": [self.basis], "calculations": [self.case]}
        self.sync_catalog()
        self.write_json("data/elements/Si/sets/Si-test/set.json", self.basis)
        self.write_json("data/calculations/3d/Si/si-test/record.json", self.case)
        self.write_json("data/log-index.json", {"entries": self.case["files"]["logs"]})

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return path

    def write_json(self, relative, value):
        return self.write(relative, json.dumps(value))

    def payload(self, relative):
        return {"path": relative, "sha256": hashlib.sha256((self.root / relative).read_bytes()).hexdigest()}

    def sync_catalog(self):
        self.write_json("database/data.json", self.catalog)

    def test_keeps_site_data_metadata_and_exact_bytes(self):
        revision = "a1" * 20
        info = SITE.build_site(self.root, self.output, revision)
        self.assertEqual(info["source_commit"], revision)
        self.assertIsNone(info["source_dirty"])
        expected = {
            "index.html", "database/index.html", "database/style.css", "database/app.js", "database/search.mjs",
            "database/assets/background.svg", "database/data.json", "README.md", "CONTRIBUTING.md", "LICENSE",
            "references/database.md", "data/log-index.json",
            "data/elements/Si/sets/Si-test/set.json", "data/calculations/3d/Si/si-test/record.json",
            self.basis["files"][0]["path"], self.case["files"]["results"][0]["path"], self.case["files"]["logs"][0]["path"],
        }
        for relative in expected:
            with self.subTest(path=relative):
                self.assertEqual((self.output / relative).read_bytes(), (self.root / relative).read_bytes())
        self.assertTrue((self.output / ".nojekyll").is_file())
        self.assertEqual(json.loads((self.output / "build-info.json").read_text()), info)
        self.assertFalse((self.root / "build-info.json").exists())

    def test_does_not_publish_designs_caches_scripts_or_unlisted_data(self):
        excluded = ["docs/superpowers/plans/design.html", ".superpowers/design.html", ".git/config",
                    "scripts/tool.py", "tests/example.html", "database/cache/draft.json",
                    "database/__pycache__/cache.pyc", "database/draft.html.tmp", "database/.draft.html",
                    "database/archive-completeness.json", "database/missing-evidence.html",
                    "data/calculations/3d/Si/si-test/results/unlisted.dat", "references/draft.md"]
        for relative in excluded:
            self.write(relative, "not deployed")
        SITE.build_site(self.root, self.output, "b" * 40)
        for relative in excluded:
            with self.subTest(path=relative):
                self.assertFalse((self.output / relative).exists())

    def test_includes_only_referenced_shared_assets_and_json_dependencies(self):
        self.write("database/config.json", json.dumps({"icon": {"path": "assets/icon.svg"}}))
        self.write("assets/icon.svg", '<svg><image href="image.png"/></svg>')
        self.write("assets/image.png", b"image")
        self.write("assets/unreferenced.png", b"not deployed")
        self.write("database/style.css", '@import "theme.css"; body { font-family: Example; }')
        self.write("database/theme.css", '@font-face { font-family: Example; src: url("../fonts/example.woff2"); }')
        self.write("fonts/example.woff2", b"font")
        SITE.build_site(self.root, self.output)
        for relative in ("assets/icon.svg", "assets/image.png", "fonts/example.woff2", "database/theme.css"):
            self.assertTrue((self.output / relative).is_file())
        self.assertFalse((self.output / "assets/unreferenced.png").exists())

    def test_accepts_empty_output_and_preserves_existing_nojekyll(self):
        self.output.mkdir()
        self.write(".nojekyll", "")
        SITE.build_site(self.root, self.output)
        self.assertEqual((self.output / ".nojekyll").read_bytes(), b"")

    def test_nonempty_output_is_not_overwritten(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("keep")
        with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
            SITE.build_site(self.root, self.output)
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(list(self.output.iterdir()), [marker])

    def test_rejects_repository_ancestors_and_source_subdirectories(self):
        for target in (self.root, self.root.parent, self.root.parent.parent, self.root / "data/new",
                       self.root / "database/new", self.root / "references/new"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "源"):
                SITE.build_site(self.root, target)
        self.assertFalse(self.output.exists())

    def test_rejects_catalog_path_escape_and_excluded_paths(self):
        for relative in ("../outside.dat", "/outside.dat", "data/../../outside.dat",
                         "data/%2e%2e/%2e%2e/outside.dat", "data\\outside.dat", "docs/superpowers/design.html"):
            self.basis["files"][0]["path"] = relative
            self.sync_catalog()
            with self.subTest(path=relative), self.assertRaises(ValueError):
                SITE.build_site(self.root, self.output)
            self.assertFalse(self.output.exists())

    def test_rejects_record_identifier_escape(self):
        self.basis["id"] = "../../outside"
        self.sync_catalog()
        with self.assertRaisesRegex(ValueError, "目录名"):
            SITE.build_site(self.root, self.output)

    def test_rejects_missing_payload_before_writing(self):
        self.basis["files"][0]["path"] = "data/elements/Si/missing.upf"
        self.sync_catalog()
        with self.assertRaisesRegex(ValueError, "缺失"):
            SITE.build_site(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_missing_static_reference_before_writing(self):
        self.write("database/style.css", 'body { background: url("assets/missing.svg"); }')
        with self.assertRaisesRegex(ValueError, "缺失"):
            SITE.build_site(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_html_escape_and_excluded_dependency(self):
        for href in ("../../outside.html", "../docs/superpowers/design.html"):
            self.write("database/index.html", f'<a href="{href}">invalid</a>')
            with self.subTest(href=href), self.assertRaises(ValueError):
                SITE.build_site(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_json_index_or_property_escape(self):
        self.write_json("data/log-index.json", {"entries": [{"path": "../outside.dat"}]})
        with self.assertRaises(ValueError):
            SITE.build_site(self.root, self.output)
        self.write_json("data/log-index.json", {"entries": []})
        self.case["properties"] = [{"evidence": ["../outside.dat"]}]
        self.sync_catalog()
        with self.assertRaises(ValueError):
            SITE.build_site(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_unlisted_property_or_index_file(self):
        relative = "data/calculations/3d/Si/si-test/results/unlisted.dat"
        self.write(relative, "unlisted")
        self.write_json("data/log-index.json", {"entries": [{"path": relative}]})
        with self.assertRaisesRegex(ValueError, "未发布"):
            SITE.build_site(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_symlink_payload_and_static_directory(self):
        payload = self.root / self.basis["files"][0]["path"]
        outside = self.root.parent / "outside.dat"
        outside.write_bytes(payload.read_bytes())
        payload.unlink()
        payload.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "符号链接"):
            SITE.build_site(self.root, self.output)
        payload.unlink()
        payload.write_bytes(outside.read_bytes())
        (self.root / "database/external").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "符号链接"):
            SITE.build_site(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_output_symlink(self):
        elsewhere = self.root.parent / "elsewhere"
        elsewhere.mkdir()
        self.output.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "符号链接"):
            SITE.build_site(self.root, self.output)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_rejects_output_parent_symlink(self):
        elsewhere = self.root.parent / "elsewhere"
        elsewhere.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "符号链接"):
            SITE.build_site(self.root, alias / "new")
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_checks_payload_hash_without_whole_file_reads(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("禁止整文件读取")):
            SITE.build_site(self.root, self.output)
        other = self.root / "_bad_hash"
        self.write(self.basis["files"][0]["path"], b"changed")
        with self.assertRaisesRegex(ValueError, "SHA-256不一致"):
            SITE.build_site(self.root, other)
        self.assertFalse((other / "build-info.json").exists())

    def test_exact_commit_or_explicit_null(self):
        self.assertIsNone(SITE.source_commit(self.root, None))
        self.assertEqual(SITE.source_commit(self.root, "c" * 64), "c" * 64)
        for commit in ("main", "abcdef0", "c" * 39, "g" * 40, "d" * 40 + "\n"):
            with self.subTest(commit=commit), self.assertRaisesRegex(ValueError, "完整"):
                SITE.source_commit(self.root, commit)
        (self.root / ".git").mkdir()
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "e" * 40 + "\n", "")):
            self.assertEqual(SITE.source_commit(self.root, None), "e" * 40)
        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(SITE.source_commit(self.root, None))

    def test_cli_defaults_to_site_and_reports_invalid_commit(self):
        command = [sys.executable, str(ROOT / "scripts/build_site.py"), "--root", str(self.root)]
        result = subprocess.run(command + ["--commit", "abbreviated"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(json.loads((self.output / "build-info.json").read_text())["source_commit"])


if __name__ == "__main__":
    unittest.main()
