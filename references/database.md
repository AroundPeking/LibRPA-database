# Public basis and calculation database

The repository is both a reusable skill and a small provenance database. It
stores the actual public payloads, not only download links. The database is
deliberately append-oriented: a changed PP, NAO, ABF, generator input, or
runtime protocol receives a new record and a new immutable set ID.

## Directory layout

```text
data/
  elements/<Element>/
    pseudopotentials/<sha256>.upf
    orbitals/<sha256>.orb
    for_aux/<sha256>.orb
    auxiliary/<sha256>.abfs
    sets/<set-id>/set.json
  calculations/
    2d/<material>/<case-id>/
    3d/<material>/<case-id>/
      inputs/
      results/
      logs/
      figures/
      record.json
database/data.json
```

The generated `data/log-index.json` records one owner for each retained log.
Rebuild it with `python3 scripts/build_indexes.py --write` and use `--check`
in CI.

The public basis library in `database/data.json` catalogues ABACUS basis
records only: pseudopotentials, physical numerical orbitals, and auxiliary
basis functions. FHI-aims species defaults (FHI-aims' own tier
classification, for example `intermediate_gw`) remain in the per-element
set registries as byte-exact binding evidence for FHI-aims calculations;
they are inlined in each calculation's archived `control.in` and are not
published as basis-library records.

`set.json` binds one element's PP, physical NAO, optional auxiliary-generation
orbital, and ABF. It may also contain portable generation evidence. A
calculation `record.json` binds the exact set IDs used by that case when the
source audit proves the association. A historical band archive whose exact
production files are not yet proven remains in the database with an empty
`species` list and an explicit `missing` explanation; it must not be silently
treated as a matched benchmark.

When a material has useful but not yet exact evidence, use `basis_candidates`
with an element, set ID, and a short `scope` such as `contextual candidate;
exact production binding pending`. The database UI displays these separately
from the exact `species` linkage. This keeps reusable files discoverable while
preventing a historical result from being misrepresented as a matched test.
For a controlled basis comparison, an optional `basis_comparison` object may
record accepted and failed candidates and a concise evidence-based conclusion.

## Basis-set record

The important fields are:

- `id`: immutable public set ID. Include the element and a short family label,
  then a content-derived suffix.
- `element`, `family`: chemical element and PP/orbital family.
- `validation_scope`: the strongest evidence actually completed, for example
  `generation_only`, `pbe_only`, `historical_producer_use`, or
  `near_gap_GW_only`.
- `files`: entries with `role` (`pp`, `nao`, `for_aux`, `abf`, or evidence),
  repository-relative `path`, lowercase `sha256`, `original_sha256`, byte
  size, and a `transformation` note.
- `source`: public collection or release information. Never put a local path,
  hostname, scheduler ID, or private repository URL here.
- `generation_provenance`: generator version and commit when the evidence
  contains them. Use `null` plus a reason when it does not.

The payload hash is the hash of the file committed here. `original_sha256`
lets a reviewer verify that a text evidence file was redacted without changing
the scientific payload. Binary PP/NAO/ABF files are copied byte-for-byte when
redistribution is permitted.

## Display names and downloads

The catalog generator adds name metadata without renaming any payload:
`display_name`, `download_name`, `name_source`, and `original_names`. Names
come from safe file labels or a unique role in an exact `species.asset_aliases`
binding; matching SHA-256 and role may share that naming evidence. A candidate
binding cannot prove a production filename.

If no original filename is documented, `name_source: descriptive_alias` marks
an explicitly generated, readable name including the element, family, role,
and short hash. Such names must not be described as recovered originals. A
non-basis evidence file may use its archived basename (`archive_name`). The UI
always retains access to the immutable path, full hash, and transformation
note. Identically named files with different hashes remain distinct assets.

Calculation inputs are listed separately from result tables and basis files.
A `files.inputs` entry has a text preview and direct download. An empty input
list is shown as **Inputs not archived**, even if a result or candidate basis
is available. Repeated input names from different stages preserve their
archive basename on download. No missing input or geometry is synthesized.

## Calculation record

Every calculation record has `dimension` (`2d` or `3d`), `material`, `software`,
`summary`, `files`, and `missing`. There is deliberately no record-level
scientific `status` field: the database indexes complete calculations with
their evidence and does not judge whether a result is scientifically correct.
Correctness claims belong in the underlying papers or in per-property
provenance (`properties[].status`), not in a record classification. The
validator rejects a record that reintroduces a top-level `status` field.

`software.abacus.commit` and `software.librpa.commit` must be full immutable
IDs or `null`. A shortened ID may be kept as `abbreviated_commit`, together
with a note that the full identity was not recorded. A full ID resolved from a
unique local object is still marked as historical resolution when the original
log printed only a prefix.

The public catalog adds a derived `spin_orbit` flag per calculation (not part
of the record schema): the catalog build marks a record `true` only when an
archived input file explicitly enables spin-orbit coupling — `lspinorb 1` in
an ABACUS `INPUT`, or `include_spin_orbit` in an FHI-aims `control.in`.
Noncollinear or spin-polarized channel settings alone (`noncolin`, `nspin`,
`spin collinear`) do not enable the mark. The site shows a SOC label in the
methods list of matching records.

A record that archives an unambiguous structure input (`STRU` for ABACUS,
`geometry.in` for FHI-aims) carries `structure_identity`: a digest over the
canonicalized cell and atomic sites (`cell-sites-v1`, 1e-5 Angstrom grid),
pointing at that archived input as evidence. Two records with the same digest
used the same structure and the site compares them directly. Records that
cover the same material with the other frontend but a different structure
(independently relaxed or differently sized cells) are shown as cross-frontend
reference points instead, and are never presented as identical-structure
comparisons.

## Extensible calculated properties

Put each result that should be searchable and displayed on a material detail
page in a `properties` array. The same schema covers electronic, topological,
optical, magnetic, structural, and future contributed results:

```json
{
  "key": "band_gap",
  "category": "electronic",
  "label": "Band gap",
  "method": "G0W0",
  "value": 2.86,
  "unit": "eV",
  "status": "reported",
  "definition": "Selected band-path quasiparticle gap",
  "evidence": [
    "data/calculations/3d/GaN/gan-paper-pca1e-6/results/GW_band_spin_1.dat"
  ]
}
```

`key`, `category`, `label`, `method`, `value`, `unit`, `status`, and non-empty
`evidence` are required. `value` may be a JSON scalar, array, or object.
Categories are lowercase slugs; the six standard detail-page categories are
always shown and any other contributed slug is added automatically. Status is
property-specific: use `reported`, `validated`, `provisional`, or `failed`.
Evidence must name a file declared in the same calculation record's `files`
groups, where the path and SHA-256 are checked. See `CONTRIBUTING.md` for the
status meanings and contribution steps.

The importer maps existing `summary.dft_gap_ev`, `summary.pbe_gap_ev`,
`summary.exx_gap_ev`, `summary.gw_gap_ev`, and `summary.value` into properties
only when it can identify matching KS/PBE, EXX, or GW result evidence. A
duplicate summary value does not create a duplicate row. Original `summary`
fields remain for compatibility. No RPA-correlation or topological value is
created when the record contains no such result. Migration updates only a
`reported` row explicitly marked with its `source_summary_key`; an unmarked
contribution or a reviewed `failed`, `validated`, or `provisional` status is
never overwritten merely because its value matches an old summary.

A record whose `summary.observable` explicitly describes a restricted
raw-band/frontier observable is not ranked or labelled as an ordinary GW
band gap. Its original value and definition remain visible in the overview
and properties, alongside the recorded failed gates or other limitations.

## Local preview

The site loads `database/data.json` with `fetch`, so preview it over HTTP from
the repository root:

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8765/database/`. Opening `database/index.html`
directly using a `file://` URL will not reliably load the catalog JSON.

As explicitly approved on 2026-10-12, the Pages browsable preview is independent
of strict **Validate database** acceptance. Publishing still requires passing
schema/hash, catalog/index, public-scan, software-test, and current complete
missing-evidence-report checks. The homepage, each record, and
`database/missing-evidence.html` disclose unresolved evidence. Strict
`--check-completeness` remains blocking, without historical waivers; a
successful Pages deployment does not establish complete-upload or scientific
acceptance, and does not change what the public basis library catalogues.

Band displays preserve the original frozen selections and mappings: 3 occupied
and 4 empty bands for 3D, the original 4/4 for the new hBN record, and the exact
original-sidecar indices for the other 15 2D records. Each method retains its
own original VBM or documented reference energy. Only the viewport expands to
include the full finite selected extent, with
`max(0.5, 0.05 * (selected_max - selected_min))` eV padding; previous limits
never shrink and are retained as `previous_near_gap_limits_ev`. No additional
bands are selected, and source hashes, path observables, pathological
rejections, and scientific statuses remain unchanged. See
[`plotting.md`](plotting.md) for the full rendering and evidence contract.

## How to generate a new set

1. Freeze the PP family, XC, valence/semicore configuration, relativistic mode,
   SOC choice, and target observable. Record the PP SHA before generating any
   orbital.
2. Generate the physical NAO with the exact PP. With SIAB, keep the generator
   input, radial cutoffs, angular channels, level, and training set. Inspect
   radial normalization and spillage; an atomic pass does not prove periodic
   GW quality.
3. Generate an auxiliary-only orbital when additional angular channels are
   needed for products. Mark it `for_aux`; never use it as the physical KS
   orbital unless it has independently passed the physical-NAO tests.
4. Generate the ABF from products of the same physical NAO and PP. Record the
   Gaussian/radial recipe, angular channels, PCA threshold, retained dimension,
   overlap/Coulomb condition diagnostics, and any runtime shrink threshold.
   Generation and LibRPA runtime thresholds are separate parameters.
5. Run the ladder in a fixed producer chain: file/header and hash checks,
   atomic radial checks, periodic PBE and overlap, RI residual and Coulomb
   conditioning, EXX controls, then RPA/GW. For strict 2D, keep the Coulomb
   convention, Gamma head/wing treatment, q mesh, and full-grid response
   preparation explicit.
6. Compare basis candidates one variable at a time. Freeze geometry, PP,
   physical NAO, ABF, executable commits, k/q mesh, empty-state window, and
   observable while changing the one candidate under test. Preserve failed
   candidates because an unstable large basis is useful diagnostic evidence.
7. Copy only permitted public assets into `data/elements/<Element>/`, create a
   new `set.json`, and put portable inputs, logs, results, and figures under the
   matching `data/calculations/2d/` or `data/calculations/3d/` case directory.
   Run `python3 scripts/library.py --write-catalog` and the public scan before
   opening a pull request.

The database intentionally does not assign a universal “best” basis. A set can
be the current contextual choice for one material and only a generation
candidate for another. The `validation_scope`, exact set IDs, hashes, and gate
notes are the decision record.
