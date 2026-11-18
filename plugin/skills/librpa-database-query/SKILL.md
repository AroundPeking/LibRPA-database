---
name: librpa-database-query
description: Use when reading, searching, comparing, or downloading data from the LibRPA materials database (GW/RPA band gaps, band structures, RPA energies, basis sets) — which MCP tool answers which question, how to quote gap values with their scope, and the plain-HTTP fallback (catalog structure, search semantics, hash-verified downloads, band-table parsing, record schema) for runtimes without the MCP server.
---

# LibRPA Database Query

## With the MCP server (preferred)

If the `librpa-database` MCP server is connected (installed by the
`librpa-database` plugin, or registered from `plugin/mcp/server.py`), use its
read-only tools instead of fetching JSON by hand:

| Question | Tool |
|---|---|
| What is in the database? | `database_overview` |
| Which records match a material, element set, method, front end, or GW-gap range? | `search_materials` (`elements` + `element_mode: "only"` for an exact chemical system) |
| How do PBE/KS, EXX, and GW gaps compare across codes? | `compare_gaps` |
| Everything about one record | `get_material` (its `derived` block holds the values the website shows) |
| Which files does a record archive? / read one | `list_files`, then `read_file` (SHA-256 verified) |
| Band energies along the archived k-path | `get_band_table` (ABACUS exports) |
| Which basis did a calculation use? | `get_material` → `species`, then `get_basis_set` |

The server never writes. To add data, follow the `librpa-database-intake`
skill (pull request) or call `contribution_guide`.

## Quoting values correctly

- Quote `summary.observable` and `summary.gap_definition` next to any gap. Many
  gaps are sampled band-path or sampled-Γ observables, not global fundamental
  gaps; `compare_gaps` labels each row `band`, `path`, or `sampled`.
- Compare values across front ends only when their definitions agree;
  same-structure records share a `structure_identity` fingerprint.
- Report the record id and its `page_url` so a reader can check the evidence.

## Without MCP (plain HTTP)

The sections below read the same data with `curl` and the Python standard
library.

## What you are reading

- Catalog: `https://aroundpeking.github.io/LibRPA-database/database/data.json`
  (~4 MB) — every calculation record with all properties, software identity,
  species bindings, and declared files. One fetch serves most questions.
  Lighter views without file lists: `database/catalog/calculations.json`,
  `database/catalog/basis-sets.json`, and `database/catalog/index.json`.
- One record: `https://aroundpeking.github.io/LibRPA-database/data/calculations/<2d|3d>/<Material>/<id>/record.json`.
- Payload bytes: declared files with `tier: "referenced"` live in the
  HuggingFace dataset `AroundPeking/LibRPA-database`; each entry carries
  `external_url` (primary), `external_url_backup` (mirror), `size_bytes`, and
  `sha256`. Files without a tier are served from the Pages deploy at
  `https://aroundpeking.github.io/LibRPA-database/<path>` (basis library
  payloads).
- Human view of the same data: `https://aroundpeking.github.io/LibRPA-database/database/`

## Quick start

```bash
curl -s https://aroundpeking.github.io/LibRPA-database/database/data.json -o data.json
python3 - <<'PY'
import json
catalog = json.load(open("data.json"))
for r in catalog["calculations"]:
    if r["material"] == "Si" and r["dimension"] == "3d":
        print(r["id"], r["record_type"], r.get("functional"), r["summary"]["observable"])
PY
```

## Search semantics

Match tokens against `material`, `formula`, `id`, `dimension`,
`record_type`, method chips, and property keys. Method chips come from
`functional` (PBE/LDA/...), property `method` values (EXX, GW, RPA, ...),
`spin_orbit` → SOC, `spin_polarized` → SPIN. `record_type` is one of `band`,
`large_system_gw`, `rpa_energy`, `reader_conversion`.

## Downloading and verifying a payload

```bash
python3 - <<'PY'
import json, hashlib, urllib.request
catalog = json.load(open("data.json"))
record = next(r for r in catalog["calculations"] if r["id"] == "si-paper-all_kpath")
entry = next(f for g in record["files"].values() for f in g
             if f["path"].endswith("GW_band_spin_1.dat"))
url = entry.get("external_url") or ("https://aroundpeking.github.io/LibRPA-database/" + entry["path"])
data = urllib.request.urlopen(url).read()
assert hashlib.sha256(data).hexdigest() == entry["sha256"], "hash mismatch"
open("GW_band_spin_1.dat", "wb").write(data)
PY
```

Always verify the SHA-256. If the primary URL is unreachable, retry with
`external_url_backup` (a public mirror). Networks behind a proxy should export
`HTTPS_PROXY`; the mirror is also reachable from mainland China without one.
Text payloads can be large — the website previews only the first 64 KB.

## Band table format (ABACUS exports)

One line per k-point, whitespace-separated:

```
<k_index> <kx> <ky> <kz> <occ_1> <E_1> <occ_2> <E_2> ...
```

`k_index` is a 1-based integer, `kx/ky/kz` are fractional coordinates, and the
remaining columns are occupation/energy pairs (occupations at even offsets,
energies at odd offsets, in eV). All rows carry the same number of bands;
comment lines start with `#`. This is the exact layout the repository's own
parser (`scripts/plot_bands.py`) enforces.

## Record schema essentials

- `files` groups: `inputs` (control files: INPUT/KPT/STRU or control.in,
  job scripts), `results` (numerical outputs, receipts), `logs` (program and
  scheduler logs), `figures` (generated figures and sidecar metadata).
- `software`: per-code identity — a 40-hex source `commit` or an
  `executable_sha256`, plus `source_url`.
- `species`: exact basis bindings (`element` + `set_id`); resolve against
  `catalog["basis_sets"]` for pseudopotential / physical NAO / auxiliary basis
  payload URLs.
- `summary.observable` states what the number is; `gap_definition`/scope notes
  state what it is NOT (e.g. a sampled path gap is not a global fundamental
  gap). Read them before quoting a value.
- `properties[]`: keyed observables with `method`, `value`, `unit`, `status`,
  and `evidence` (declared file paths).
- `archive_completeness`: gate status plus any remaining evidence issues.

## Machine access via MCP

The read-only server in `plugin/mcp/server.py` exposes these operations as
tools, resources (`librpa://record/{record_id}`, `librpa://basis/{set_id}`),
and prompts. Install it with the plugin (`/plugin marketplace add
AroundPeking/LibRPA-database`, then `/plugin install librpa-database@librpa`)
or register the single file with any MCP client — see `plugin/README.md`.
