---
name: librpa-database-query
description: Use when reading, searching, or downloading data from the LibRPA materials database without the MCP server — catalog structure, search semantics, hash-verified payload downloads from the external archive, band-table parsing, and the record schema.
---

# LibRPA Database Query (plain HTTP)

## What you are reading

- Catalog: `https://aroundpeking.github.io/LibRPA-database/database/data.json`
  (~2.6 MB) — every calculation record with all properties, software identity,
  species bindings, and declared files. One fetch serves most questions.
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

If your runtime supports MCP, the read-only server in `plugin/mcp/server.py`
exposes the same operations as tools (search, get record, list files,
hash-verified read, band table parse) — see `plugin/README.md`.
