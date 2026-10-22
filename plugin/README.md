# LibRPA database plugin — skills + MCP for AI agents

Two ways for an AI agent (or a human with curl) to work with the
[LibRPA materials database](https://aroundpeking.github.io/LibRPA-database/database/):

- **Read data** — the MCP server (`mcp/server.py`) or the query skill.
- **Contribute calculations** — the intake skill walks an agent through
  validating a finished RPA/GW run, building the record, passing every
  repository gate, and submitting a pull request. After the PR merges, an
  automated workflow uploads the payload bytes to the external archive;
  contributors never need a HuggingFace account.

Everything here is read-only against published endpoints (or, for intake,
works inside a clone of this repository). No credentials are required.

## Layout

```
plugin/
  skills/librpa-database-intake/SKILL.md   # how to add a calculation (PR flow)
  skills/librpa-database-query/SKILL.md    # how to read data without MCP
  mcp/server.py                            # stdio MCP server, stdlib only
```

## Install the skills

Any agent that loads markdown skills (ZCode, Claude Code, and compatible
runtimes):

```bash
git clone https://github.com/AroundPeking/LibRPA-database.git
mkdir -p ~/.zcode/skills            # or ~/.claude/skills for Claude Code
cp -R LibRPA-database/plugin/skills/* ~/.zcode/skills/
```

The skills then trigger on their descriptions: intake when adding a
calculation, query when reading data.

## Install the MCP server

`mcp/server.py` is a single-file, zero-dependency (Python ≥ 3.9 standard
library) stdio server. Register it with your client:

ZCode (`~/.zcode/settings.json`, or the equivalent MCP configuration):

```json
{
  "mcpServers": {
    "librpa-database": {
      "command": "python3",
      "args": ["/absolute/path/to/LibRPA-database/plugin/mcp/server.py"]
    }
  }
}
```

Claude Desktop (`claude_desktop_config.json`) and Cursor use the same shape
under their own `mcpServers` keys. A single downloaded copy of `server.py`
also works — it does not need the rest of the repository.

Networks that require a proxy: export `HTTPS_PROXY` in the environment the
server inherits. The payload mirror (`external_url_backup`) is reachable from
mainland China without a proxy.

### Tools

| Tool | What it does |
|---|---|
| `search_materials` | AND-token search over material/formula/id/methods/properties |
| `get_material` | one full record (properties, software, species, files+URLs) |
| `list_files` | declared files of a record, with tier/size/primary+mirror URLs |
| `read_file` | fetch one payload, verify its SHA-256, return the text |
| `get_band_table` | parse a KS/EXX/GW band export into k-points/energies/occupations |
| `list_basis_sets` | pseudopotential / NAO / auxiliary basis payloads per element |

### Verify the install

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"hand","version":"0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 plugin/mcp/server.py
```

You should get an `initialize` result naming `librpa-database` and a
`tools/list` result with six tools.

### Environment variables (all optional)

- `LIBRPA_DB_CATALOG_URL` — catalog JSON location (default: the published
  `data.json`; accepts a local path for offline use)
- `LIBRPA_DB_SITE_ROOT` — root for repository-local file URLs
- `LIBRPA_DB_CACHE_DIR` — payload cache (default: system temp directory;
  payloads are cached content-addressed after hash verification)
- `LIBRPA_DB_TTL_SECONDS` — catalog cache lifetime (default 600)

## Intake in one paragraph

Clone this repository, create `data/calculations/<2d|3d>/<Material>/<case-id>/`
with `record.json` + `inputs/` + `results/` + `logs/` (+ `figures/`), following
`plugin/skills/librpa-database-intake/SKILL.md` for the schema, sanitization,
and evidence rules. Regenerate the generated artifacts with the repository
scripts, run the gate chain and both test suites, push a branch, and open a PR.
CI must pass; after merge the external-archive sync uploads the bytes and
rewrites the record automatically. The full procedure, prohibitions, and stop
conditions live in the skill.
