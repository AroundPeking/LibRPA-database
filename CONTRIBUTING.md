# Contributing to the LibRPA materials database

This repository is the data layer for LibRPA calculations produced with supported electronic-structure front ends, including ABACUS and FHI-aims. For the ABACUS/NAO subset, use the companion [basis skill](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill) for generation and validation guidance. Each contribution must retain its code-specific basis representation, immutable calculation records, and exact provenance.

## Before adding files

Confirm that the PP, NAO, and ABF may be redistributed. Keep the source URL, release or archive commit, license status, original SHA-256, and any redaction note. Do not add private paths, hostnames, scheduler output, credentials, or binaries whose redistribution is not authorized.

## Add an element set

1. Put byte-preserved payloads in `data/elements/<Element>/pseudopotentials/`, `orbitals/`, `for_aux/`, or `auxiliary/`, using the SHA-256 as the filename stem.
2. Create `sets/<set-id>/set.json` with exact roles, hashes, dimensions, generation evidence, validation scope, and source information.
3. Use a new immutable set ID whenever a payload or PP/NAO/ABF binding changes.

## Add a calculation

Archive portable `inputs`, `results`, `logs`, and `figures` from the same
calculation under `data/calculations/2d/<material>/<case-id>/` or
`data/calculations/3d/<material>/<case-id>/`. Bind `species` only to exact set
IDs supported by production-linkage evidence. The basic schema/hash validator
can still read historical evidence. Where linkage is genuinely missing,
retain an empty `species` list and a `missing` explanation; **this is not a
complete upload and cannot pass strict Validate CI**. As explicitly approved
on 2026-10-12, Pages may first publish the browsable archive and every missing
evidence item. Website publication does not establish a complete upload or
scientific acceptance. Schema/hash, catalog, index, public-scan, and software
test checks remain blocking. A candidate set, descriptive alias, missing note,
or historical allowlist must not make an incomplete record appear complete.

`basis_candidates` identify follow-up candidates whose production binding is
unproven. Calculation records carry no record-level scientific status label:
the database indexes complete calculations with their evidence and does not
certify whether a result is correct. Scientific claims stay with the
underlying papers and per-property provenance (`properties[].status`).
Archive completeness is not scientific validation, and a scientific
limitation does not waive missing archive evidence.

Current automated checks verify same-record directories, declared files,
full SHAs, original STRU filenames, and exact role bindings. Same-record
ownership does not automatically establish that every stage came from one
production run. Cross-stage spectrum/input provenance requires separate,
reviewable original evidence. The current MoS2/WSe2 importer additionally
checks three spectra and 15 original inputs byte for byte against independent
original-run sources; this does not establish that other historical records
have passed the same audit. When the original STRU lacks an ABFS declaration,
the current check still blocks acceptance. No receipt/manifest replacement
contract validated against real cases has been implemented; a self-declared
Boolean flag cannot bypass this requirement.

### Strict complete-upload requirements

- Real, readable, declared `INPUT`, `KPT`, `STRU`, and `librpa.in` files with
  SHA-256 values in the same record and case directory. Explicit stage names
  such as `scf__INPUT` and `INPUT_scf` are permitted. A manifest, `INPUT.info`,
  `STRU.cif`, or another calculation directory cannot stand in for original
  inputs.
- `species` covers every element in the formula/material, and every `set_id`
  is non-null. Each exact set has an identifiable PP, **physical NAO**, and
  ABF payload. `for_aux` cannot replace the physical NAO, and `missing_roles`
  must be empty.
- Establish bindings for original filenames in every STRU's `ATOMIC_SPECIES`,
  `NUMERICAL_ORBITAL`, and `ABFS_ORBITAL` using exact-species `asset_aliases`
  or trustworthy `label`/`original_name` evidence for files with the same role
  and full SHA-256. At least one production STRU must declare the physical
  NAO and ABF. An ordinary SCF stage may omit ABF, but not every stage may skip
  ABF linkage. Portable relative paths, including `../assets/`, must match a
  proven alias exactly or actually resolve to the bound asset with the same
  hash; basename guessing is not permitted. Descriptive catalog aliases,
  matching elements, and coincidentally identical filenames do not prove
  production linkage.
- A generic auxiliary basis `ORBITAL_<R>U.abfs` may have a template element in
  its internal `Element` header only when the same-run original STRU explicitly
  declares that filename and both the exact `asset_aliases` and payload
  SHA-256 bindings are proven. This exception applies only to ABF; it does not
  relax PP/physical-NAO element matching or rewrite original headers.
- Record full immutable commits for both ABACUS and LibRPA. An unknown identity
  must remain explicit and block complete-upload acceptance; never guess it.
- At least one actual KS/PBE/DFT, EXX, or GW band result. Original tables must
  be readable, non-empty, and have consistent row widths. Genuine retained
  NaN/Inf entries are scientific diagnostics, not missing files; they must not
  be deleted or used to claim scientific acceptance.
- Every method **actually present** requires a non-failed, finite `band_gap`
  in eV or an explicitly restricted/path-gap observable. Evidence includes
  that method's original band file in the same record, and every evidence
  path must be validly declared in the record. Three methods are not required
  by default for every record. A failed property alone cannot replace a
  finite observable.
- At least one readable SVG/PNG/PDF band figure. Empty files, damaged images,
  and non-band images fail. SVG curves require visible strokes; hidden,
  fully transparent, or zero-width paths cannot replace an actual figure.
  Every format declares `source_paths` containing at least one readable band
  file in the same record. Same-record KPT, logs, and sidecars may also be
  included, but all figure sources must exist, be non-empty, and pass hash
  checks. SVG energy/k-path semantics and actual curve paths must be
  recognizable. Cross-case symlinks cannot impersonate an archive of the
  same run.
- For restricted observables, explicitly record the restricted/raw-band
  frontier **path observable**, original state indices, definition, and
  evidence. Never fabricate an ordinary gap or relabel a path/finite-state
  result as a global fundamental gap. Completeness checks do not infer or
  recompute gaps or upgrade original scientific statuses.

## Add a calculated property

Append one entry to the calculation's `properties` array. A property needs a
stable key, an open lowercase category slug, a label, method, value, unit,
status, and at least one evidence path that is already listed in the same
record's `files` groups. The evidence file must have its SHA-256 recorded
there. Values may be numbers, text, arrays, or objects; use arrays or objects
for vector/tensor values and multi-part invariants.

```json
{
  "key": "z2_invariant",
  "category": "topological",
  "label": "Z2 invariant",
  "method": "Wilson loop",
  "value": {"spin_up": 1, "spin_down": 1},
  "unit": "dimensionless",
  "status": "reported",
  "definition": "Invariant from the occupied subspace on the stated k mesh",
  "evidence": [
    "data/calculations/2d/Material/case/results/wilson_loop.json"
  ]
}
```

Use `reported` when the result is recorded but has not passed a dedicated
validation gate, `validated` only when that gate is documented, `provisional`
for an explicitly incomplete analysis, and `failed` when the property test
failed. Existing categories include `electronic`, `topological`, `optical`,
`magnetic`, `structural`, and `other`; new lowercase slugs appear in the same
detail-page table automatically. Empty categories show no value until evidence
is contributed. Do not add a placeholder number.

The record validator checks required fields, category/status values, unique
`(category, key, method)` identities, and same-record evidence ownership. The
catalog is generated from calculation records:

```bash
python3 scripts/library.py --write-catalog
python3 scripts/library.py --check-catalog
python3 scripts/library.py --check-completeness
# Optional complete machine-readable report; genuine missing evidence still returns nonzero.
python3 scripts/library.py --check-completeness --completeness-report /tmp/archive-completeness.json
```

## Checks

```bash
python3 scripts/library.py --check-completeness
python3 scripts/library.py --write-catalog
python3 scripts/library.py --check-catalog
python3 scripts/build_indexes.py --write
python3 scripts/public_scan.py .
python3 -m unittest discover -s tests -v
git diff --check
```

These checks do not compile or run ABACUS/LibRPA. `--check-completeness`
reports all incomplete case IDs and missing evidence in one run and exits
nonzero. **Validate database** always runs this gate explicitly, without
`continue-on-error`, diff-only checks, or historical waivers. Genuine missing
evidence in the historical database must fail strict acceptance; rules must
not be weakened merely to obtain a green check.

As confirmed on 2026-10-12, website updates are separate from strict
acceptance. **Publish database** uses
`scripts/export_missing_evidence.py --check --report-output ...` to validate
and publish the true complete report. Schema/hash errors and stale reports
still fail. Once the other checks pass, the workflow may publish incomplete
archives. The homepage, every record, and `database/missing-evidence.html`
explicitly disclose that strict acceptance has not passed. Pages success is
not Validate success, does not waive any record's requirements, and does not
upgrade scientific status.

Basic `validate()` and catalog generation retain historical schema/hash
readability. The catalog's `archive_completeness.status/issues` honestly
shows complete and missing evidence, but cannot replace strict checks.
`--completeness-report <path>` includes every case, including complete records,
original scientific statuses, missing evidence, classifications, and aggregate
statistics. CI retains this JSON artifact even after failure, without waiving
the strict step's failure. Archive completeness and full-spectrum
finiteness/physical acceptance are audited separately. An archived anomalous
numerical table must not be presented as scientifically accepted.

For band figures, see [`references/plotting.md`](references/plotting.md),
`scripts/plot_bands.py`, and `scripts/generate_band_figures.py`. The generic
script provides table parsing, rendering, and provenance. The native archive
generator audits original spectra and freezes raw selections according to
occupation evidence before rendering. The 3D selection remains 3 occupied
and 4 empty bands; new hBN retains 4/4; the other 15 2D records retain their
exact original-sidecar frozen indices and mappings, not a common 3/4 rule.
Each method keeps its own original VBM or documented reference energy. Only
the viewport expands to show all finite selected energies, using
`max(0.5, 0.05 * (selected_max - selected_min))` eV padding without shrinking
the old limits. Sidecars retain `previous_near_gap_limits_ev`; no additional
bands are selected. The original 5/6-window admission audit and rejected
GaAs/GaP GW figures remain unchanged. GeTe/SnSe EXX remain explicitly
pathological diagnostics, not fabricated positive gaps; original NPZ sources
and existing transformed DAT assets retain separate identities and hashes.

Run `python3 scripts/plot_bands.py --help` or
`python3 scripts/generate_band_figures.py --help` for command details. Preserve
original band order, occupation evidence, and input/figure-source hashes.
Band-path tables report sampled/path gaps. A global/fundamental gap requires
adequate full-k-space coverage and corresponding physical validation.
Archive completeness, process completion, numerical reliability, and
scientific acceptance are four distinct claims.

Paper primary values remain separate from archived-run values. `paper_values`
records the paper title, PDF SHA-256, page, table, primary-author column, and
reported precision, citing the same-record
`results/paper_reported_values.json`. The excerpt must agree with display
metadata and pass file-hash checks. Lists and detail headlines keep the
established database PBE/GW values and show one primary value per method,
without a repeated paper/archive comparison table. Overview retains a
collapsed reference and source-evidence panel. Original `properties`,
`summary`, spectra, and scientific statuses remain unchanged; original
archive/path values remain accessible in the evidence-linked properties
and downloadable result files. Do not fabricate paper EXX values when the main
table has no EXX column; existing EXX values retain their archive attribution.
A finite paper value cannot replace the same-method original-spectrum evidence
required by strict upload checks or remove completeness blockers. The old hBN
record does not use values from the new-basis table row.

The generated log index is a bijection: every retained file under a case's
`logs/` directory must appear exactly once in `data/log-index.json`. The
public basis library catalogues ABACUS basis records only; FHI-aims species
defaults (FHI-aims' own tier classification) stay in the per-element set
registries as byte-exact binding evidence and are inlined in each
calculation's archived `control.in`.
