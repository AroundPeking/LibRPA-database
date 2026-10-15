# LibRPA materials database

## [Open web database](https://aroundpeking.github.io/LibRPA-database/database/)

**[Browse materials](https://aroundpeking.github.io/LibRPA-database/database/)** · **[Browse basis files](https://aroundpeking.github.io/LibRPA-database/database/#/basis)**

Click the link above to search materials, view calculation details, and preview or
download archived inputs and basis files. No installation, GitHub sign-in, or
local server is needed. The files below are the source repository, not the live UI.

This repository is an open data archive for LibRPA materials calculations. It can host results produced through both ABACUS + LibRPA and FHI-aims + LibRPA workflows, while retaining each calculation's code-specific inputs, basis data, provenance, and validation scope. The existing [ABACUS + LibRPA GW basis skill](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill) remains a companion for the ABACUS/NAO subset; it does not define the scope of the database.

The catalog is split into `2d` and `3d`. Each element has its own directory under `data/elements/<Element>/`, and each calculation is under `data/calculations/2d/` or `data/calculations/3d/`. The searchable static catalog is in [`database/index.html`](database/index.html); its machine-readable source is [`database/data.json`](database/data.json).

The current snapshot contains 109 calculation records across 2D and 3D (band, large-system GW, RPA-energy, and reader-conversion records) and a public basis library of 123 ABACUS pseudopotential / physical-orbital / auxiliary-basis records. FHI-aims species defaults are kept as per-calculation binding evidence inlined in each archived `control.in`, not as basis-library entries. These are historical and reference records with explicit scope. The database does not declare a universal best PP/NAO/ABF: use the exact set IDs, hashes, producer commits, observable, and passed gates before reusing a file.

The generated [`data/log-index.json`](data/log-index.json) gives every retained
log exactly one calculation owner.

## Use

Open the [live web database](https://aroundpeking.github.io/LibRPA-database/database/) to browse without installing anything. For development, serve the repository as a static site, or read `database/data.json` directly. A record's `species` entries are exact production bindings only when the source audit proved them. `basis_candidates` are useful follow-up files whose exact production binding remains unproven. Failed and anomalous candidates stay in the database as evidence.

The catalog has separate Materials and Basis sets views. Search matches
all query words across names, formulas, elements, basis links, properties,
methods, commits, and public file names; formula subscripts and punctuation are
normalized. The dimension filter keeps 2D and 3D records visibly separate. The
material list stays compact and opens a detail page for each record. That page
contains DFT/EXX/GW figures, raw band files, provenance, and a category-based
properties table. Reader-format provenance uses a separate record type and does not
become an RPA/GW result record. It may link a bounded audit of a separate completed
historical GW run; when frontier rows were not retained, the site shows completion and
`gap unavailable` rather than turning a Fermi energy into a gap. Electronic results are migrated from the recorded summaries;
Topology, Optical, Magnetic, Structural, and Other remain ready for evidence-
linked contributions without implying those results already exist.

For a local preview, run `python3 -m http.server 8765 --bind 127.0.0.1` from the
repository root and open `http://127.0.0.1:8765/database/`. The catalog uses
`fetch` and cannot reliably load its JSON when opened as a local file.

### Inputs and readable asset names

Open a calculation and choose **View inputs** or **Input files**. Every archived
input has a read-only text preview and a download link; nested calculation
stages retain their archive names to avoid overwriting same-named files. The
current archive has input files for **all 35 records** (305 files), including
the C2048 reader-conversion record's 8 archived input files.
Nine records include **89 partial stage controls**, with stage-input receipts
and explicit incomplete-run warnings; these attachments do not certify a full
production chain, exact basis linkage, or a self-contained rerun bundle.
Seven of those calculations now have a separate producer-assets receipt binding
17 species and 51 PP/NAO/ABF roles to original STRU declarations and payload
hashes. This separate recovery is not a complete immutable runtime seal; the
original stage-input receipt retains its narrower, unchanged scope.

The **Pseudopotentials & basis** section links exact species bindings to their
PP, physical NAO, optional `for_aux`, and ABF files. The Basis library also has
its own detail pages, including generation-only and unbound records. Candidate
links are labelled separately from exact production bindings.

Each Basis detail page also plots the original **NAO, ABF, and optional for_aux
radial functions**, with **one chart per angular momentum l** and individually
selectable original N indices. Switch between R(r) and finite-difference dR/dr,
or magnify the final 20% of the original grid to inspect the cutoff tail.
Source SHA-256 is checked before rendering; the curves are not smoothed,
interpolated, reordered, or renormalized. SVG downloads preserve this display.
Header/count mismatches are visibly marked as diagnostics, not repaired files
or accepted bases. Radial appearance alone does not validate periodic overlap,
RI conditioning, or EXX/GW accuracy.

Hash-addressed storage is intentional and unchanged. The generated catalog
adds `display_name`, `download_name`, `name_source`, and `original_names`:
recorded labels or exact calculation aliases are preferred. Otherwise a unique
`element_family_role_short-hash.ext` descriptive alias is displayed with an
explicit original-name-missing warning. Immutable paths and full SHA-256
values remain recorded in each record's data for integrity verification; the
web pages show readable filenames and sizes, and aliases do not invent
original filenames.

### Deploy with GitHub Pages

1. In the repository's **Settings → Pages**, select **GitHub Actions** as the
   source. This repository-level setting is required once; adding a workflow
   alone does not enable Pages. A `404` or “Ensure GitHub Pages has been enabled”
   at the deployment step is not a Python build or data-validation failure.
2. Push to `main`, or run **Actions → Publish database → Run workflow**.
   The workflow checks Pages configuration, validates the data and indexes,
   runs Python/JavaScript tests, and builds a restricted `_site` artifact.
   It does not publish design drafts, private Git state, tests, or caches.
   Pages publishes the formal browsable archive after schema/hash validation,
   catalog/index checks, public scanning, and software tests pass. Internal
   completeness reports remain repository-side validation artifacts and are not
   included in the deployed website.
3. Check the deployment job's returned URL and `build-info.json`. The latter
   records the deployed source commit and `source_dirty` state; a local build
   with uncommitted changes is not represented as an exact commit build. A
   successful local build is not proof that the site is online. Set the repository's **About → Website** to the
   confirmed deployment URL, not to a guessed or placeholder address.

To inspect the exact deployable output locally, use a new or empty target:

```bash
python3 scripts/build_site.py --output _site
python3 -m http.server 8766 --bind 127.0.0.1 --directory _site
```

The builder refuses a non-empty output directory or any target containing
source files. Choose a new output path for another build; it never deletes
an existing directory automatically.

For archived 3D ABACUS band tables, the checked-in SVG figures can be rebuilt
with `python3 scripts/generate_band_figures.py --write --allow-weighted-occupations`
(`--audit` is read-only). All 17 band-structure 3D records have been rechecked: 49 valid or
explicitly diagnostic single-method SVGs; GaAs/GaP GW near-gap figures remain
rejected because their frozen raw windows are pathological. The script preserves the raw
tables and records source paths and SHA-256 hashes in each figure sidecar.
The shared renderer now expands only the viewport to show the full finite
extent of already frozen bands: 3 occupied + 4 empty for 3D, the original
4 + 4 for new hBN, and the exact original-sidecar selections and mappings
for the other 15 2D records. Each method retains its original VBM or documented
reference energy. Padding is `max(0.5, 0.05 * (selected_max - selected_min))`
eV, previous limits never shrink, and sidecars retain
`previous_near_gap_limits_ev`. No extra bands are selected. Source hashes,
raw energies, mappings, the original 5/6-window admission audit, path-gap
values, and scientific statuses remain unchanged. GeTe/SnSe EXX stay labelled
as pathological diagnostics; original NPZ sources and existing transformed
DAT assets remain separate. See [`references/plotting.md`](references/plotting.md)
for the complete display and evidence contract.

The generation protocol, validation ladder, and ABACUS-to-LibRPA handoff are documented in the companion skill, especially [`references/database.md`](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill/blob/main/references/database.md), [`SKILL.md`](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill/blob/main/SKILL.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Validate

Data checks use the Python standard library; frontend unit tests use Node.js
22 or newer. These checks do not compile ABACUS or LibRPA.

```bash
python3 scripts/library.py --write-catalog
python3 scripts/build_indexes.py --write
python3 scripts/public_scan.py .
python3 -m unittest discover -s tests -v
node --test tests/*.mjs
```

The completeness report keeps unresolved historical software-identity facts visible.
CI accepts only the exact pre-existing calculation/software pairs frozen in
`data/historical-software-identity-exceptions.json`. New material must provide a full
source commit or the SHA-256 of the exact executable for each executing code; new
identity gaps, all non-software evidence gaps, and unknown/duplicate/stale baseline
entries remain blocking.

An optional real-browser regression is available as `node tests/browser_smoke.cjs`
when Playwright is installed in the caller's environment. It defaults to the
local preview above; set `CATALOG_URL` to an actual deployed catalog URL to
repeat the same checks online. It verifies search, property tabs, file
previews, native downloads, mobile layout, error states, and every archived
input's HTTP content against its SHA-256. It is not a scientific acceptance test.

When adding a record, preserve the original and published SHA-256 values,
record any redaction, use repository-relative paths, and verify redistribution
terms for every third-party payload. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

The scripts, schema notes, and catalog UI are MIT licensed. Third-party software and scientific data retain their own licenses and reuse conditions; check the source record before redistributing a payload.
