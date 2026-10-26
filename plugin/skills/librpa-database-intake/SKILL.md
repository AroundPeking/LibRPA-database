---
name: librpa-database-intake
description: Use when adding a completed ABACUS+LibRPA or FHI-aims+LibRPA calculation (band structure, large-system GW, RPA energy, or reader conversion) to the LibRPA materials database — validating the run scientifically, building the record, passing every repository gate, and submitting it as a pull request. Also covers catalog regeneration, evidence rules, and the post-merge external-archive sync.
---

# LibRPA Database Intake

## Purpose

Validate a completed RPA/GW result scientifically, present a read-only candidate
summary, and stop until the exact candidate is approved. After approval, import
immutable evidence, build the record, update the catalog, run every gate, and
submit — without weakening database validation.

## How the database is architected (read this first)

The repository and the bytes are deliberately separated:

- **GitHub repository** (`AroundPeking/LibRPA-database`): the catalog
  (`database/data.json`), one `record.json` per calculation, the basis library
  bytes (`data/elements`), the website, the validators, and the CI gates.
- **HuggingFace dataset** (`AroundPeking/LibRPA-database`): every calculation
  payload byte (inputs, results, logs, figures). Records declare these files
  with `tier: "referenced"`, a `size_bytes`, a `sha256`, and a primary plus
  mirror `external_url`.
- **Consequence for intake**: a new calculation is added with its payload files
  as ordinary repository-local files under `data/calculations/`. After the pull
  request merges, the *External archive sync* workflow uploads those bytes to
  the HuggingFace dataset (using a repository secret the maintainer has already
  configured), rewrites the record entries to the referenced tier, and removes
  the local bytes — all automatically. **Contributors never need a HuggingFace
  account, token, or upload step.**
- Basis payloads (`data/elements`) and species bindings always stay
  repository-local; only calculation-owned files are externalized.

## Two operating modes

**Mode A — repository owner's agent (push access).** Keep the non-bypassable
approval gate below: propose a candidate summary, stop, and wait until the user
explicitly approves that exact candidate digest before anything is written.

**Mode B — external contributor (pull request).** The pull request itself is
the approval artifact. Still produce the candidate summary in the PR
description, run every gate locally before pushing, and never push to `main`
directly — always a branch plus PR. CI enforces the same gates on the PR.

## Non-bypassable approval gate (Mode A)

1. Perform discovery and validation read-only.
2. Produce one candidate summary: source run and task, observable definition,
   finite-result checks, input/basis/software identity, missing evidence, file
   hashes, and the candidate SHA-256.
3. Ask: `是否将候选 <candidate_sha256> 收录到 LibRPA materials database？`
4. Stop unless the user explicitly approves that exact candidate.
5. Treat silence, earlier general permission, scheduler state, a directory name,
   a prior candidate, or an ambiguous "继续" as no approval.
6. Never copy evidence, create a record, update the catalog, commit, or push
   before approval.
7. If any source file or scientific value changes after approval, invalidate
   the approval and ask again with a new candidate digest.

## Phase A: discover and validate

Read `README.md` and `references/database.md` in the repository first.

For each candidate:

- Confirm the scientific program finished successfully **from its own output**.
  Never accept a scheduler `COMPLETED` state alone.
- Confirm the requested RPA/GW task reached its scientifically final stage.
- Parse the full result; reject truncated tables, missing expected
  states/q-points/frequencies, nonfinite values, duplicate rows, and
  inconsistent counts. Genuine nonfinite solver outputs are diagnostics — keep
  them visible, never delete or relabel them as zero.
- Preserve the exact observable scope: a Γ-point regular-grid gap is a sampled
  Γ gap; never call it a global fundamental gap or a band-path gap.
- Verify INPUT/KPT/STRU (or `control.in`) files, physical basis identity,
  auxiliary-basis mode, resource evidence, and immutable software identity for
  every executing code. A new calculation needs a full source commit (40-hex)
  or the SHA-256 of the exact executable, for the front end (ABACUS/FHI-aims)
  and for LibRPA.
- Record known historical settings exactly; do not replace them with current
  recommendations.
- Present missing immutable commits or basis evidence as limitations, never as
  reasons to fabricate substitutes. The fixed historical software-identity
  baseline (`data/historical-software-identity-exceptions.json`) applies only
  to the pre-existing pairs already listed there; never extend it.

## Phase B: build the record and submit

There is no generic importer script — records are authored by hand against the
schema, and the repository validators are the safety net. After approval (or
when preparing a contributor PR):

1. Re-read every approved source file; verify SHA-256, size, regular-file
   status, and absence of symlink substitution.
2. Create `data/calculations/<2d|3d>/<Material>/<case-id>/` with the directory
   structure below. Copy the evidence bytes in (sanitized first, see below).
3. Author `record.json` following "Required record fields". File entries carry
   `path` (repository-relative, forward slashes), `sha256`, `size_bytes`, plus
   the descriptive-name and provenance fields. Use `transformation: "none"`
   for byte-preserved files and describe any redaction otherwise.
4. Regenerate every generated artifact with the scripts (never hand-edit):
   `library.py --write-catalog`, `build_indexes.py --write`,
   `export_missing_evidence.py --write`, then copy
   `database/archive-completeness.json` to the repository root.
5. Run the full local gate chain (see "CI pipeline") — all must pass.
6. Inspect the diff; stage only intended paths.
7. Submit: Mode A commits and pushes on request with the repository
   attribution; Mode B pushes a branch (`add/<case-id>`) and opens a pull
   request titled `Add <case-id> (<record_type>)` whose description carries the
   candidate summary: source, observable with scope, evidence checklist, and
   any limitations. Never bypass hooks, never force-push.

After merge, CI publishes the site and the *External archive sync* workflow
externalizes the new payloads automatically. Nothing else is required.

## Record types

- `band`: numerical band data, a provenance-linked figure, scoped gap properties.
- `large_system_gw`: complete finite QP table, sampled-grid observable,
  completion log, atom/state counts, runtime/resources, explicit
  auxiliary-basis provenance; no band figure required or invented.
- `rpa_energy`: complete q/frequency aggregation, finite correlation energy,
  completion evidence.
- `reader_conversion`: separately approved conversion provenance, converter
  identity, runtime receipt, validated reader header/dimensions, and an
  explicit statement that no RPA/GW scientific result is claimed. Keep this
  type separate from `large_system_gw`.

## Required record fields for new calculations

- `id`: unique case identifier (e.g. `c2048-reader-v1-20260607`)
- `material`, `formula`, `dimension` (`"2d"` / `"3d"`)
- **No record-level `status` field** — scientific classification labels were
  removed; the validator fails any record that reintroduces a top-level one.
- `record_type`: one of the four types above
- `files`: object with `inputs`, `results`, `logs`, `figures` arrays
- `software`: entries for the front end and LibRPA, each with `commit`
  (40-hex) or `executable_sha256`, plus `source_url`
- `workflow.frontend`: `"abacus"` or `"fhi_aims"`
- `computational_scale`: `atom_count`, `ao_count`, `matrix_rows`,
  `matrix_columns`, `state_count`, `occupied_states`, `unoccupied_states` as
  applicable
- `species`: array of `{element, set_id}` bindings (exact, production-linked)
- `summary`: `observable`, `value`, `unit`, `gap_definition` as applicable
- `source`: `collection`, optional `repository`

Performance and cluster fields: `cluster_label`, `accelerators`
(`{type, per_node, total}`), `nodes`, `cpus`, `elapsed_seconds`,
`accelerator_label`, and `structure_identity` (SHA-256 fingerprint used for
same-structure comparison across records).

## Path sanitization — critical

The `public_scan.py` CI gate rejects files that contain private paths or
scheduler-internal identifiers. Sanitize **before** computing hashes:

- Private workstation or HPC home paths (macOS home directories, Linux home
  directories, numbered work directories) → replace with `/HPC/`.
- The scheduler job variable spelled with an underscore → use the underscore
  free spelling (`SLURM_JOBID`).
- Private connection strings using the ssh scheme → remove or redact the line.

After sanitization, recompute the SHA-256 values in `record.json`, because the
file bytes changed.

## Method labels derived from archived inputs

Every new record must light up the method labels it qualifies for — SOC, SPIN,
the concrete mean-field functional (e.g. PBE), EXX, GW. The catalog build
derives them automatically (reading declared inputs through the external byte
resolver when they are referenced), so the intake duty is to archive the
evidence they read:

- `spin_orbit` — the real ABACUS `INPUT` with `lspinorb 1`, or aims
  `control.in` with `include_spin_orbit`.
- `spin_polarized` — ABACUS `INPUT` with `nspin 2`, or aims `control.in` with
  `spin collinear`.
- `functional` — the `xc` / `dft_functional` line in the archived ABACUS
  `INPUT` series, or `xc` in aims `control.in`; all archived control files must
  agree on one known functional (pbe/lda/gga/pbesol/scan/hse).
- EXX/GW chips — record properties and result tables under their real method
  names; also give the DFT-level property the actual functional as its method,
  not a generic label.

Sanitized or paraphrased control files are NOT valid label evidence — only the
archived declared inputs count. After intake, regenerate the catalog and
refresh pinned expectations in `tests/test_records.mjs` (spin flag lists,
functional/EXX/GW chip counts) and `tests/test_library.py` if derivation rules
changed.

## Generated files to update after data changes

```bash
python3 scripts/library.py --write-catalog          # database/data.json
python3 scripts/build_indexes.py --write            # data/log-index.json
python3 scripts/export_missing_evidence.py --write  # database/missing-evidence.html
cp database/archive-completeness.json archive-completeness.json
python3 scripts/library.py --check-catalog
python3 scripts/build_indexes.py --check
```

Never hand-edit `database/data.json`, `data/log-index.json`, or
`database/missing-evidence.html`.

## CI pipeline — all must pass

Three workflows run per push (and PR):

1. **Validate database** — `node --check database/app.js`;
   `node --test tests/*.mjs`; catalog/completeness/index checks (referenced
   payloads are fetched from the external archive into a CI cache and
   hash-verified, so the gates read real bytes); `public_scan.py`;
   `python -m unittest discover -s tests`.
2. **Publish database** (push to main) — the same checks plus the
   missing-evidence report check and the static site build; the site only
   deploys when everything passes.
3. **External archive sync** (after a successful publish) — converts every
   calculation payload still stored locally to the referenced tier, uploads the
   bytes to the HuggingFace dataset, regenerates the catalog, and removes the
   local bytes in an automated commit. Every sync then runs the post-sync
   triple check (`scripts/verify_post_sync.py --base HEAD~1`): the newly
   referenced entries are fetched over HTTPS and byte-checked against their
   declared SHA-256/size, and the tracked tree under `data/calculations` must
   contain `record.json` manifests only. A failed check turns the sync red.
   The verifier checks HTTP status explicitly and paces/retries per host
   (`--delay`): the hf-mirror backup answers rapid request sequences with
   429 error pages that curl still reports as a completed transfer, and those
   error pages must never be mistaken for payload bytes.

After each sync the owner additionally verifies the deployed site with
`python3 scripts/verify_post_sync.py --live <site-root>` (default 40-entry
sample; `--live-all` for the full sweep): every entry in the deployed
`database/data.json` must resolve over HTTPS — referenced entries at their
external URL, local-tier entries at the deployed site path. Transmission,
repository state, and public accessibility are three separate facts; verify
all three after every upload.

Locally, run the same scripts plus `python3 -m unittest discover -s tests` and
`node --test tests/*.mjs` before submitting. The test suite includes pinned
counts (record totals, chip counts, spin lists); a new record changes them —
update the pins deliberately, never by weakening assertions.

## What to add

- Real, readable INPUT/KPT/STRU/librpa.in (or aims `control.in`) files with
  exact SHA-256
- Program outputs (stdout/stderr) that contain completion markers
- Delta-Sternheimer (`workflow.response = "delta_sternheimer"`) records must
  archive the production chain's ABACUS program stdout (`scientific_role
  abacus_program_stdout`); when the LibRPA executable evaluated the RPA energy
  (`rpa_evaluation` is not `archived_campaign_script`), the LibRPA program
  output (`scientific_role librpa_program_stdout` or `librpa_program_output`)
  is required too. Aggregation tables are supplements, never substitutes.
  Partial or scheduler-cancelled outputs must not be archived as complete
  program evidence. The five solid cases that lacked outputs at intake were
  grandfathered in `data/historical-program-output-exceptions.json` and all
  retired on 2026-10-26 after the outputs were recovered from the production
  cluster; the mechanism (exact frozen pairs, stale entries block integrity)
  remains available for genuinely unrecoverable historical gaps
- Band data files (`KS/EXX/GW_band_spin_1.dat`) for `band` records; QP tables
  for `large_system_gw`; aggregation outputs for `rpa_energy`
- Band figures generated by `scripts/generate_band_figures.py`
- Full software identity, cluster/resource/wall-time evidence
- Descriptive archived names (see the naming table) with `original_name` kept

## What NOT to add — explicit prohibitions

- No private paths, hostnames, IPs, or credentials in archived files (see
  sanitization)
- No binaries whose redistribution is not authorized; no symlinks as evidence
- No fabricated values: never invent gaps, QP energies, or correlation energies
- No relabeling: a sampled-Γ gap is not a fundamental gap; a raw-band result is
  not a validated GW gap
- No descriptive aliases as production bindings (`basis_candidates` are
  follow-up candidates, not bindings)
- No hand-editing of generated files; no weakening of pinned test expectations
- No scheduler-only acceptance; no guessing software identity — an unknown
  commit stays unknown and fails intake rather than being filled with HEAD
- No mixing record types; no hiding nonfinite values
- No hook bypass, no force-push, no unrelated files in commits
- Repository attribution for owner commits: `AroundPeking
  <gonghuanjing@iphy.ac.cn>`; contributors commit under their own identity

## File naming conventions

| Source file | Archived path | original_name |
|---|---|---|
| `INPUT` | `inputs/abacus_INPUT` | `INPUT` |
| `KPT` | `inputs/abacus_KPT` | `KPT` |
| `STRU` | `inputs/abacus_STRU` (canonical `inputs/STRU` when the record carries `structure_identity`) | `STRU` |
| `librpa.in` (GW) | `inputs/librpa_gw.in` | `librpa.in` |
| `librpa.in` (RPA) | `inputs/librpa_rpa.in` | `librpa.in` |
| Slurm script (GW) | `inputs/gw_slurm_script.sh` | original |
| Slurm script (RPA) | `inputs/rpa_slurm_script.sh` | original |
| Program stdout | `logs/<task>_stdout.log` | original |
| Program stderr | `logs/<task>_stderr.log` | original |
| Slurm log | `logs/<task>_slurm_stdout.log` | original |

## Directory structure

```
data/calculations/{2d,3d}/<Material>/<case-id>/
  record.json
  inputs/    abacus_INPUT, abacus_KPT, abacus_STRU, librpa_gw.in, *_slurm_script.sh, ...
  results/   gw_output_rank0.out, KS/EXX/GW_band_spin_1.dat, conversion receipts, ...
  figures/   generated band figures and sidecar metadata
  logs/      *_stdout.log, *_stderr.log, *_slurm_stdout.log, ...
```

## Failure and stop conditions

Stop and report without submitting when any of these occurs:

- No exact approval for the current candidate (Mode A)
- Source readset changed after approval
- Program output partial, nonfinite in a disqualifying way, internally
  inconsistent, or lacking its own success marker
- Observable scope cannot be stated accurately
- Input, physical basis, or auxiliary-basis provenance would require guessing
- A new material lacks full source commits and exact executable hashes
- A target path already contains different bytes
- Tests fail or the generated catalog is stale
- Private paths or scheduler identifiers remain after sanitization

Keep unresolved scientific limitations visible in record metadata; never
expose internal CI or draft-status warnings in the public website UI.
