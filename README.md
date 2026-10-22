<div align="center">

<img src="database/logo-emblem.png" width="200" alt="LibRPA materials database emblem">

# LibRPA materials database

**[Open the web database](https://aroundpeking.github.io/LibRPA-database/database/)**

</div>

An open archive of LibRPA materials calculations — band structures, large-system
GW, RPA energies, and reader conversions from both ABACUS and FHI-aims front
ends — each with its original inputs, exact basis bindings, software identity,
and validation scope. Nothing to install: the link above searches, inspects,
previews, and downloads every archived file. The companion
[ABACUS + LibRPA GW basis skill](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill)
covers the ABACUS/NAO workflow itself.

## Where the files live

| Layer | Location |
|---|---|
| Catalog, UI, validators, basis library | this repository |
| Calculation payload bytes (inputs, results, logs, figures) | external archive |

- Primary archive: <https://huggingface.co/datasets/AroundPeking/LibRPA-database>
- Mirror (reachable from mainland China): <https://hf-mirror.com/datasets/AroundPeking/LibRPA-database>

Every payload is declared in its `record.json` with the repository-relative
path as identity, `size_bytes`, `sha256` as the integrity anchor, and direct
plus mirror URLs (`tier: "referenced"`). Validation gates fetch the bytes and
verify the hash (`.external-cache/`, never committed), so acceptance strength
is the same as when the bytes sat in git. A merged data PR uploads its
payloads to the archive automatically; contributors never need a HuggingFace
account. Basis payloads (`data/elements`) and species bindings stay in git.

```
data/calculations/{2d,3d}/<Material>/<case-id>/   record.json + inputs/ + results/ + logs/ + figures/
data/elements/<Element>/                          basis library payloads
database/                                         catalog UI; data.json is the machine-readable catalog
data/log-index.json                               exactly one owner per retained log
```

## Programmatic access

```bash
curl -s https://aroundpeking.github.io/LibRPA-database/database/data.json -o data.json
```

Each declared file carries its hash and download URLs — verify the SHA-256
after downloading. For AI agents, the
[`plugin/` directory](https://github.com/AroundPeking/LibRPA-database/tree/main/plugin)
packages a zero-dependency read-only MCP server and two skills: contributing a
calculation as a pull request, and reading the data without MCP.

## Validate and deploy

Data checks use the Python standard library; frontend tests need Node.js 22+.

```bash
python3 scripts/library.py --write-catalog
python3 scripts/build_indexes.py --write
python3 scripts/public_scan.py .
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
```

CI accepts only the historical software-identity pairs frozen in
`data/historical-software-identity-exceptions.json`; a new record needs a full
source commit or the executable's SHA-256. Band figures are rebuilt with
`scripts/generate_band_figures.py` (display and evidence contract in
[`references/plotting.md`](references/plotting.md)). Contribution rules:
[`CONTRIBUTING.md`](CONTRIBUTING.md).

Pushing to `main` publishes through the *Publish database* workflow; the
deployed commit is recorded in `build-info.json`. To preview a build locally:

```bash
python3 scripts/build_site.py --output _site
python3 -m http.server 8766 --bind 127.0.0.1 --directory _site
```

## License

The scripts, schema notes, and catalog UI are MIT licensed. Third-party
software and scientific data retain their own licenses and reuse conditions;
check the source record before redistributing a payload.
