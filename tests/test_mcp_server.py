"""Streaming, integrity, tool, protocol, and packaging regressions for the
read-only MCP server and the plugin that ships it."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("librpa_mcp_server", ROOT / "plugin/mcp/server.py")
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class ChunkedResponse:
    """A response that rejects unbounded read() calls."""

    def __init__(self, payload: bytes):
        self.stream = io.BytesIO(payload)
        self.read_sizes = []

    def read(self, size=-1):
        if size is None or size <= 0:
            raise AssertionError("payload response was read without a bounded chunk size")
        self.read_sizes.append(size)
        return self.stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stream.close()


class PayloadStreamingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"LIBRPA_DB_CACHE_DIR": str(self.root / "cache")})
        self.env.start()
        self.payload = ("header\n" + "αβγδεζηθ\n" * 1000).encode()
        self.file = {
            "path": "data/calculations/3d/Si/test/logs/librpa.out",
            "sha256": hashlib.sha256(self.payload).hexdigest(),
            "size_bytes": len(self.payload),
            "tier": "referenced",
            "external_url": "https://huggingface.co/datasets/x/y/resolve/" + "a" * 40 + "/payload",
            "external_url_backup": "https://hf-mirror.com/datasets/x/y/resolve/" + "a" * 40 + "/payload",
        }

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
        server._catalog_cache.update(data=None, fetched=0.0)

    def test_primary_hash_mismatch_streams_to_mirror_and_atomically_caches(self):
        responses = []

        def fetch(request, timeout):
            payload = b"wrong primary bytes" if request.full_url == self.file["external_url"] else self.payload
            response = ChunkedResponse(payload)
            responses.append(response)
            return response

        with mock.patch.object(server.urllib.request, "urlopen", side_effect=fetch), \
                mock.patch.object(server.time, "sleep"), \
                mock.patch.object(server, "_fetch", side_effect=AssertionError("unbounded payload fetch")):
            cached = server._payload_path(self.file)
        self.assertEqual(cached.read_bytes(), self.payload)
        self.assertEqual(len(responses), 4)  # three bad-primary attempts, then one valid mirror
        self.assertTrue(all(response.read_sizes for response in responses))
        self.assertEqual(list(cached.parent.glob("*.part")), [])

    def test_corrupt_cache_is_replaced_by_verified_bytes(self):
        cache = server._cache_path(self.file)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"poisoned cache")
        with mock.patch.object(server.urllib.request, "urlopen",
                               return_value=ChunkedResponse(self.payload)):
            self.assertEqual(server._payload_path(self.file), cache)
        self.assertEqual(cache.read_bytes(), self.payload)

    def _declare_record(self, file):
        record = {"id": "test", "files": {"logs": [file]}}
        server._catalog_cache.update(data={"calculations": [record]}, fetched=server.time.time())
        return record

    def test_text_preview_uses_verified_cache_and_bounded_character_prefix(self):
        self._declare_record(self.file)
        cache = server._cache_path(self.file)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(self.payload)
        with mock.patch.object(server, "_payload_bytes", side_effect=AssertionError("whole-payload read")), \
                mock.patch.object(server.urllib.request, "urlopen", side_effect=AssertionError("network")):
            result = server.tool_read_file({"record_id": "test", "path": self.file["path"], "max_bytes": 12})
        expected = self.payload.decode()[:12]
        self.assertEqual(result["content"], expected)
        self.assertTrue(result["truncated"])
        self.assertTrue(result["sha256_verified"])
        self.assertEqual(result["size_bytes"], len(self.payload))

    def test_binary_preview_returns_verified_cache_location_not_text(self):
        payload = b"abc\x00def" * 100
        self.file.update(sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload))
        self._declare_record(self.file)
        cache = server._cache_path(self.file)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(payload)
        result = server.tool_read_file({"record_id": "test", "path": self.file["path"], "max_bytes": 1})
        self.assertTrue(result["binary"])
        self.assertNotIn("content", result)
        self.assertEqual(result["cached_at"], str(cache))
        self.assertEqual(result["size_bytes"], len(payload))


class FileUrlTests(unittest.TestCase):
    def test_local_payload_url_percent_encodes_each_path_segment(self):
        file = {"path": "data/calculations/3d/Si/x/logs/α β%#1.dat"}
        with mock.patch.dict(os.environ, {"LIBRPA_DB_SITE_ROOT": "https://example.org/db"}):
            self.assertEqual(
                server._file_url(file),
                "https://example.org/db/data/calculations/3d/Si/x/logs/"
                "%CE%B1%20%CE%B2%25%231.dat")


def _band(material, record_id, frontend="abacus", ks=None, gw=None, **extra):
    properties = []
    for method, value in (("PBE", ks), ("GW", gw)):
        if value is not None:
            properties.append({"category": "electronic", "key": "band_gap", "method": method,
                               "value": value, "unit": "eV", "status": "reported"})
    workflow = {"frontend": frontend, "task": "gw"} if frontend == "fhi_aims" else {"frontend": frontend}
    record = {"id": record_id, "material": material, "formula": material, "dimension": "3d",
              "workflow": workflow, "properties": properties, "summary": {"observable": "GW gap"},
              "files": {"inputs": [], "results": [], "logs": [], "figures": []}}
    record.update(extra)
    return record


FIXTURE = {
    "calculations": [
        _band("GaAs", "gaas-a", ks=0.5, gw=1.4, spin_orbit=True,
              species=[{"element": "Ga", "set_id": "Ga-set"}, {"element": "As", "set_id": "As-set"}],
              files={"inputs": [{"path": "data/calculations/3d/GaAs/gaas-a/inputs/INPUT"}],
                     "results": [], "logs": [], "figures": []}),
        _band("GaAs", "gaas-b", frontend="fhi_aims", gw=1.3),
        _band("GaN", "gan-a", ks=1.9, gw=3.2),
        _band("Si", "si-a", ks=0.6, gw=1.1),
        {"id": "si-rpa", "material": "Si", "formula": "Si", "dimension": "3d", "record_type": "rpa_energy",
         "workflow": {"frontend": "abacus", "response": "delta_sternheimer"},
         "properties": [{"key": "rpa_cohesive_energy", "label": "RPA cohesive energy", "method": "RPA",
                         "value": 4.4, "unit": "eV/atom", "status": "reported"}], "files": {}},
    ],
    "basis_sets": [
        {"id": "Ga-set", "element": "Ga", "family": "Test family",
         "label": {"sentence": "13 valence electrons", "valence_electrons": 13,
                   "orbital": {"shells": "2s2p2d", "dimension_per_atom": 18}, "auxiliary": None, "uses": []},
         "files": [{"role": "pp", "name": "Ga.upf", "path": "data/elements/Ga/pseudopotentials/x.upf",
                    "sha256": "a" * 64, "size_bytes": 1}]},
        {"id": "As-set", "element": "As", "files": []},
    ],
}


class ToolTests(unittest.TestCase):
    def setUp(self):
        server._catalog_cache.update(data=json.loads(json.dumps(FIXTURE)), fetched=server.time.time())

    def tearDown(self):
        server._catalog_cache.update(data=None, fetched=0.0)

    def ids(self, result):
        return [record["id"] for record in result["records"]]

    def test_search_lists_everything_without_a_query(self):
        result = server.tool_search_materials({})
        self.assertEqual(result["total"], 5)
        self.assertEqual(self.ids(result), ["gaas-a", "gaas-b", "gan-a", "si-a", "si-rpa"])

    def test_search_filters_compose(self):
        only = server.tool_search_materials({"elements": ["Ga", "As"], "element_mode": "only"})
        self.assertEqual(self.ids(only), ["gaas-a", "gaas-b"])
        self.assertEqual(self.ids(server.tool_search_materials({"elements": ["Ga"]})), ["gaas-a", "gaas-b", "gan-a"])
        self.assertEqual(self.ids(server.tool_search_materials({"methods": ["SOC"]})), ["gaas-a"])
        self.assertEqual(self.ids(server.tool_search_materials({"methods": ["Delta-ST"]})), ["si-rpa"])
        self.assertEqual(self.ids(server.tool_search_materials({"frontend": "fhi_aims"})), ["gaas-b"])
        self.assertEqual(self.ids(server.tool_search_materials({"record_type": "rpa_energy"})), ["si-rpa"])
        self.assertEqual(self.ids(server.tool_search_materials({"gw_gap_min": 1.2, "gw_gap_max": 2})), ["gaas-a", "gaas-b"])
        self.assertEqual(self.ids(server.tool_search_materials({"has_inputs": True})), ["gaas-a"])
        self.assertEqual(self.ids(server.tool_search_materials({"query": "gaas soc"})), ["gaas-a"])

    def test_search_sorts_with_missing_values_last_and_pages(self):
        result = server.tool_search_materials({"sort": "-gw_gap"})
        self.assertEqual(self.ids(result), ["gan-a", "gaas-a", "gaas-b", "si-a", "si-rpa"])
        ascending = server.tool_search_materials({"sort": "ks_gap"})
        self.assertEqual(self.ids(ascending)[:3], ["gaas-a", "si-a", "gan-a"])
        page = server.tool_search_materials({"sort": "-gw_gap", "limit": 2, "offset": 1})
        self.assertEqual((page["total"], page["count"], self.ids(page)), (5, 2, ["gaas-a", "gaas-b"]))

    def test_search_rejects_unknown_symbols_and_modes(self):
        for arguments in ({"elements": ["Xx"]}, {"element_mode": "some"}, {"sort": "mass"}, {"gw_gap_min": "a"}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                server.tool_search_materials(arguments)

    def test_summaries_carry_gaps_headline_and_urls(self):
        record = server.tool_search_materials({"query": "gaas-a"})["records"][0]
        self.assertEqual(record["gaps"], {"ks_ev": 0.5, "exx_ev": None, "gw_ev": 1.4, "scope": "band"})
        self.assertEqual(record["primary_result"]["label"], "GW gap")
        self.assertEqual(record["methods"], ["PBE", "GW", "SOC"])
        self.assertEqual(record["elements"], ["As", "Ga"])
        self.assertTrue(record["page_url"].endswith("/database/#/material/gaas-a"))
        self.assertTrue(record["record_json_url"].endswith("/data/calculations/3d/GaAs/gaas-a/record.json"))
        rpa = server.tool_search_materials({"query": "si-rpa"})["records"][0]
        self.assertEqual(rpa["primary_result"]["value"], 4.4)
        self.assertEqual(rpa["workflow"], "ABACUS Delta-Sternheimer + LibRPA")

    def test_compare_gaps_keeps_scope_and_skips_gapless_records(self):
        result = server.tool_compare_gaps({"material": "gaas"})
        self.assertEqual([row["record_id"] for row in result["rows"]], ["gaas-a", "gaas-b"])
        self.assertEqual(result["rows"][1]["ks_gap_ev"], None)
        self.assertIn("sampled", result["scope_legend"])
        everything = server.tool_compare_gaps({})
        self.assertNotIn("si-rpa", [row["record_id"] for row in everything["rows"]])
        self.assertEqual(everything["rows"][0]["record_id"], "gan-a")
        by_name = server.tool_compare_gaps({"sort": "material", "elements": ["Si"]})
        self.assertEqual([row["record_id"] for row in by_name["rows"]], ["si-a"])

    def test_basis_tools_link_calculations(self):
        listing = server.tool_list_basis_sets({"element": "Ga"})
        self.assertEqual(listing["basis_sets"][0]["label"]["valence_electrons"], 13)
        detail = server.tool_get_basis_set({"set_id": "Ga-set"})
        self.assertEqual([item["record_id"] for item in detail["linked_calculations"]], ["gaas-a"])
        self.assertEqual(detail["files"][0]["sha256"], "a" * 64)
        with self.assertRaises(KeyError):
            server.tool_get_basis_set({"set_id": "missing"})

    def test_overview_and_contribution_guide(self):
        overview = server.tool_database_overview({})
        self.assertEqual((overview["calculations"], overview["materials"], overview["basis_sets"]), (5, 3, 2))
        self.assertEqual(overview["elements"], {"As": 2, "Ga": 3, "N": 1, "Si": 2})
        self.assertEqual(overview["frontends"], {"abacus": 4, "fhi_aims": 1})
        guide = server.tool_contribution_guide({})
        self.assertTrue(any("pull request" in step for step in guide["steps"]))
        self.assertTrue(guide["links"]["intake_skill"].endswith("librpa-database-intake/SKILL.md"))
        material = server.tool_get_material({"record_id": "gaas-a"})
        self.assertEqual(material["derived"]["gaps"]["gw_ev"], 1.4)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        server._catalog_cache.update(data=json.loads(json.dumps(FIXTURE)), fetched=server.time.time())

    def tearDown(self):
        server._catalog_cache.update(data=None, fetched=0.0)

    def exchange(self, message):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            server._handle(message)
        return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]

    def test_initialize_announces_tools_resources_and_prompts(self):
        [reply] = self.exchange({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(reply["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(set(reply["result"]["capabilities"]), {"tools", "resources", "prompts"})
        self.assertIn("pull request", reply["result"]["instructions"])

    def test_every_tool_is_listed_read_only_and_callable(self):
        [reply] = self.exchange({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = reply["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], list(server.TOOL_FUNCTIONS))
        for tool in tools:
            self.assertTrue(tool["annotations"]["readOnlyHint"], tool["name"])
            self.assertFalse(tool["annotations"]["destructiveHint"], tool["name"])
            self.assertEqual(tool["inputSchema"]["type"], "object", tool["name"])
        [call] = self.exchange({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                "params": {"name": "compare_gaps", "arguments": {"material": "Si"}}})
        self.assertFalse(call["result"]["isError"])
        self.assertEqual(json.loads(call["result"]["content"][0]["text"])["count"], 1)
        [failure] = self.exchange({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                   "params": {"name": "get_material", "arguments": {"record_id": "nope"}}})
        self.assertTrue(failure["result"]["isError"])

    def test_resources_and_prompts(self):
        [listing] = self.exchange({"jsonrpc": "2.0", "id": 5, "method": "resources/list"})
        self.assertIn("librpa://overview", [item["uri"] for item in listing["result"]["resources"]])
        [templates] = self.exchange({"jsonrpc": "2.0", "id": 6, "method": "resources/templates/list"})
        self.assertIn("librpa://record/{record_id}",
                      [item["uriTemplate"] for item in templates["result"]["resourceTemplates"]])
        [record] = self.exchange({"jsonrpc": "2.0", "id": 7, "method": "resources/read",
                                  "params": {"uri": "librpa://record/si-a"}})
        self.assertEqual(json.loads(record["result"]["contents"][0]["text"])["id"], "si-a")
        [missing] = self.exchange({"jsonrpc": "2.0", "id": 8, "method": "resources/read",
                                   "params": {"uri": "librpa://record/none"}})
        self.assertEqual(missing["error"]["code"], -32002)
        [prompt] = self.exchange({"jsonrpc": "2.0", "id": 9, "method": "prompts/get",
                                  "params": {"name": "investigate-material", "arguments": {"material": "GaAs"}}})
        self.assertIn("compare_gaps", prompt["result"]["messages"][0]["content"]["text"])
        [contribute] = self.exchange({"jsonrpc": "2.0", "id": 10, "method": "prompts/get",
                                      "params": {"name": "contribute-calculation", "arguments": {}}})
        self.assertIn("approval", contribute["result"]["messages"][0]["content"]["text"])

    def test_unknown_methods_error_and_notifications_stay_silent(self):
        [reply] = self.exchange({"jsonrpc": "2.0", "id": 11, "method": "no/such"})
        self.assertEqual(reply["error"]["code"], -32601)
        self.assertEqual(self.exchange({"jsonrpc": "2.0", "method": "notifications/initialized"}), [])
        self.assertEqual(self.exchange({"jsonrpc": "2.0", "method": "no/such"}), [])


PARITY_SCRIPT = """
import { readFileSync } from "node:fs";
import { recordFacts } from "./database/explorer.mjs";
const catalog = JSON.parse(readFileSync("database/data.json", "utf8"));
process.stdout.write(JSON.stringify(catalog.calculations.map(record => {
  const facts = recordFacts(record);
  return { id: record.id, methods: facts.methods, elements: facts.elements, ks: facts.ks, exx: facts.exx,
           gw: facts.gw, scope: facts.gapScope, workflow: facts.workflow, frontend: facts.frontend,
           primary: facts.primary, atoms: facts.atoms };
})));
"""


@unittest.skipUnless(shutil.which("node"), "node is needed to run the website's readers")
class ReaderParityTests(unittest.TestCase):
    """The server's Python readers must agree with database/*.mjs on every record."""

    def test_python_and_website_readers_agree_on_the_whole_catalog(self):
        output = subprocess.run(["node", "--input-type=module", "-e", PARITY_SCRIPT], cwd=ROOT, check=True,
                                capture_output=True, text=True, encoding="utf-8").stdout
        website = {row["id"]: row for row in json.loads(output)}
        catalog = json.loads((ROOT / "database/data.json").read_text(encoding="utf-8"))
        self.assertEqual(len(website), len(catalog["calculations"]))
        for record in catalog["calculations"]:
            gaps = server._gap_overview(record) or {}
            mine = {"methods": server._method_chips(record), "elements": server._record_elements(record),
                    "ks": gaps.get("ks"), "exx": gaps.get("exx"), "gw": gaps.get("gw"), "scope": gaps.get("scope"),
                    "workflow": server._workflow_label(record), "frontend": server._frontend(record),
                    "primary": server._primary_result(record), "atoms": server._atom_count(record)}
            theirs = website[record["id"]]
            for key, value in mine.items():
                self.assertEqual(value, theirs[key], f"{record['id']}: {key}")


class PluginPackagingTests(unittest.TestCase):
    def load(self, relative):
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def test_marketplace_plugin_and_server_versions_agree(self):
        marketplace = self.load(".claude-plugin/marketplace.json")
        manifest = self.load("plugin/.claude-plugin/plugin.json")
        [entry] = marketplace["plugins"]
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["source"], "./plugin")
        self.assertEqual(entry["version"], manifest["version"])
        self.assertEqual(manifest["version"], server.SERVER_VERSION)
        self.assertRegex(marketplace["name"], r"^[a-z0-9][a-z0-9-]*$")

    def test_plugin_mcp_config_starts_this_server(self):
        config = self.load("plugin/.mcp.json")["mcpServers"][server.SERVER_NAME]
        self.assertEqual(config["command"], "${LIBRPA_PYTHON:-python3}")
        [entry] = config["args"]
        self.assertTrue(entry.startswith("${CLAUDE_PLUGIN_ROOT}/"))
        self.assertTrue((ROOT / "plugin" / entry.split("/", 1)[1]).is_file())

    def test_skills_are_discoverable_with_matching_names(self):
        skills = sorted((ROOT / "plugin/skills").glob("*/SKILL.md"))
        self.assertEqual([path.parent.name for path in skills], ["librpa-database-intake", "librpa-database-query"])
        for path in skills:
            front = path.read_text(encoding="utf-8").split("---")[1]
            self.assertRegex(front, rf"\nname: {path.parent.name}\n")
            self.assertRegex(front, r"\ndescription: \S")

    def test_documentation_lists_every_tool(self):
        agents_page = (ROOT / "database/index.html").read_text(encoding="utf-8")
        readme = (ROOT / "plugin/README.md").read_text(encoding="utf-8")
        for name in server.TOOL_FUNCTIONS:
            self.assertIn(f"<code>{name}</code>", agents_page, name)
            self.assertIn(f"`{name}`", readme, name)
        self.assertEqual(len(re.findall(r"^\| `[a-z_]+` \|", readme, re.M)), len(server.TOOL_FUNCTIONS))


if __name__ == "__main__":
    unittest.main()
