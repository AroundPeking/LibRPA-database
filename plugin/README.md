# LibRPA database plugin — MCP server + skills for AI agents

One plugin gives an AI agent both halves of working with the
[LibRPA materials database](https://aroundpeking.github.io/LibRPA-database/database/):

| | How | What it can do |
|---|---|---|
| **Read** | `mcp/server.py`, a read-only MCP server | search, open records, read SHA-256-verified files, parse band tables, compare gaps, browse the basis library |
| **Write** | `skills/librpa-database-intake`, a pull-request procedure | validate a finished run, build the record, pass every repository gate, open a pull request |

The split is deliberate. The server holds no credentials and cannot change
anything, so a client can approve its tools without review. A contribution goes
through the agent's ordinary `git` and `gh` permissions, then through CI (*Validate
database*) and maintainer review. After merge, the *External archive sync* workflow
uploads the payload bytes, so contributors never need a Hugging Face account.

A third piece, `skills/librpa-database-query`, reads the same data over plain HTTPS
for runtimes without MCP.

## Layout

```
.claude-plugin/marketplace.json            # (repository root) makes the repo a plugin marketplace
plugin/
  .claude-plugin/plugin.json               # plugin manifest
  .mcp.json                                # registers mcp/server.py for the plugin
  mcp/server.py                            # stdio MCP server, Python standard library only
  skills/librpa-database-query/SKILL.md    # read without MCP (HTTP + JSON)
  skills/librpa-database-intake/SKILL.md   # contribute a calculation as a pull request
```

## Install in Claude Code

```text
/plugin marketplace add AroundPeking/LibRPA-database
/plugin install librpa-database@librpa
```

From a shell: `claude plugin marketplace add AroundPeking/LibRPA-database`, then
`claude plugin install librpa-database@librpa`. The MCP server appears in `/mcp` as
`plugin:librpa-database:librpa-database`, and the skills as
`/librpa-database:librpa-database-query` and `/librpa-database:librpa-database-intake`.

The server runs with `python3` by default. If your system names the interpreter
differently (on Windows usually `python` or `py`), set `LIBRPA_PYTHON` in the
environment Claude Code starts from, or in the `env` block of your Claude Code
settings:

```json
{ "env": { "LIBRPA_PYTHON": "python" } }
```

To try a local checkout without installing it: `claude --plugin-dir ./plugin`.

## Use the server from any other MCP client

`mcp/server.py` is a single file with no dependencies beyond Python ≥ 3.9. A
downloaded copy works on its own. Claude Desktop (`claude_desktop_config.json`),
Cursor, Codex, ZCode, and other clients use the same `mcpServers` shape:

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

Claude Code without the plugin: `claude mcp add librpa-database -- python3 /absolute/path/to/server.py`.

Networks that require a proxy: export `HTTPS_PROXY` in the environment the
server inherits. The payload mirror (`external_url_backup`) is reachable from
mainland China without a proxy.

### Tools

Every tool is annotated `readOnlyHint: true`.

| Tool | What it does |
|---|---|
| `database_overview` | counts per element, record type, front end, dimension, and method; where to start |
| `search_materials` | text plus filters: elements (`element_mode` `all` or `only`), dimension, front end, record type, methods, GW-gap range, inputs; sortable and paged |
| `get_material` | one full record (properties, software, species, files and URLs) plus the values the website derives |
| `list_files` | declared files of a record, with tier, size, and primary and mirror URLs |
| `read_file` | fetch one payload, verify its SHA-256, return the text |
| `get_band_table` | parse a KS/EXX/GW band export into k-points, energies, and occupations |
| `compare_gaps` | KS, EXX, and GW gaps side by side, each with its scope and definition |
| `list_basis_sets` | pseudopotential / NAO / auxiliary basis sets per element, with size labels |
| `get_basis_set` | one basis set: payloads with SHA-256, provenance, and the calculations that used it |
| `contribution_guide` | the pull-request workflow, local gates, and prohibitions |

Gap, method, element, and headline values come from Python ports of
`database/records.mjs` and `database/gaps.mjs`; `tests/test_mcp_server.py`
checks that both give identical results for every record in the catalog.

### Resources and prompts

- Resources: `librpa://overview`, `librpa://contributing`, and the templates
  `librpa://record/{record_id}` and `librpa://basis/{set_id}`.
- Prompts: `investigate-material` (survey one material with each value's scope)
  and `contribute-calculation` (prepare a finished run as a pull request).

### Verify the install

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"hand","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 plugin/mcp/server.py
```

You should get an `initialize` result naming `librpa-database` and a
`tools/list` result with ten tools.

### Environment variables (all optional)

- `LIBRPA_PYTHON` — interpreter the plugin uses to start the server (default `python3`)
- `LIBRPA_DB_CATALOG_URL` — catalog location (default: the published
  `data.json`; a local file path works for offline use)
- `LIBRPA_DB_SITE_ROOT` — root for repository-local file URLs
- `LIBRPA_DB_CACHE_DIR` — payload cache (default: system temp directory;
  payloads are cached content-addressed after hash verification)
- `LIBRPA_DB_TTL_SECONDS` — catalog cache lifetime (default 600)

## Install the skills elsewhere

Agents that load markdown skills without the plugin system can copy them:

```bash
git clone https://github.com/AroundPeking/LibRPA-database.git
mkdir -p ~/.zcode/skills            # or ~/.claude/skills, ~/.codex/skills, ...
cp -R LibRPA-database/plugin/skills/* ~/.zcode/skills/
```

## Intake in one paragraph

Fork the repository and create a branch `add/<case-id>`. Add
`data/calculations/<2d|3d>/<Material>/<case-id>/` with `record.json` and
`inputs/`, `results/`, `logs/` (and `figures/`), following
`skills/librpa-database-intake/SKILL.md` for the schema, sanitization, and
evidence rules. Regenerate the generated files with the repository scripts, run
the gate chain and both test suites, push the branch, and open a pull request;
the template asks for the candidate summary. CI must pass. After merge, the
external-archive sync uploads the bytes and rewrites the record automatically.
