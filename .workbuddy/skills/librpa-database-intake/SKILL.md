---
name: librpa-database-intake
description: This skill should be used when discovering, validating, proposing, or importing completed RPA/GW calculations into the LibRPA materials database, especially for ABACUS+LibRPA or FHI-aims+LibRPA records, large-system GW runs without band figures, and evidence-preserving catalog updates.
agent_created: true
---

# LibRPA Database Intake

## Purpose

Validate a completed RPA/GW result scientifically, present a read-only candidate summary, and stop until the user explicitly approves that exact candidate. After approval, import immutable evidence, build the record, update the catalog, test, commit, and push without weakening database validation.

## Non-bypassable approval gate

1. Perform discovery and validation read-only.
2. Produce one candidate summary containing the source run, task, observable definition, finite-result checks, input/basis/software identity, missing evidence, file hashes, and candidate SHA-256.
3. Ask: `是否将候选 <candidate_sha256> 收录到 LibRPA materials database？`
4. Stop unless the user explicitly approves that exact candidate after seeing the summary.
5. Treat silence, earlier general permission, scheduler state, a directory name, a prior candidate, or an ambiguous "继续" as no approval.
6. Never copy evidence into the repository, create a record, update the catalog, commit, or push before approval.
7. If any source file or scientific value changes after approval, invalidate approval, issue a new candidate SHA-256, and ask again.

## Phase A: discover and validate

Read `references/scientific-validation.md` and `references/database-contract.md`.

For each candidate:

- Confirm the scientific program finished successfully from its own output. Never accept Slurm `COMPLETED` alone.
- Confirm the requested RPA/GW task reached its scientifically final stage.
- Parse the full result, reject truncated tables, missing expected states/q-points/frequencies, nonfinite values, duplicate rows, and inconsistent counts.
- Preserve the exact observable scope. Label a Γ-point regular-grid gap as sampled Γ; never call it a global fundamental gap or a band-path gap.
- Verify INPUT/KPT/STRU/control files, physical basis identity, auxiliary-basis mode, resource evidence, and immutable software identity for every executing code. A new candidate must retain a full source commit or a SHA-256 of the exact executable for the front end (ABACUS/FHI-aims) and LibRPA.
- Record known historical settings exactly. Do not replace them with current recommendations.
- Run `scripts/prepare_candidate.py` only on a local read-only snapshot when applicable. For remote sources, perform equivalent read-only checks remotely and calculate the same canonical receipt fields.
- Present missing immutable commits or basis evidence as limitations, not as reasons to fabricate substitutes. The repository's fixed historical software-identity baseline applies only to the exact pre-existing calculation/software pairs already listed there; never add a new intake candidate to that baseline.

## Phase B: import only after approval

After exact approval:

1. Re-read every approved source and verify its SHA-256, size, regular-file status, and absence of symlink substitution.
2. Build a plan containing the approved candidate digest, source-to-target mappings, expected hashes, final `record.json`, and expected validator issues.
3. Run `scripts/import_approved_candidate.py` with a separately stored approval receipt containing the user's approval statement and candidate digest.
4. Use exclusive creation for new evidence and atomic replacement for generated JSON. Refuse collisions with different bytes.
5. Express workflow type explicitly (see "Record types" below).
6. Preserve exact PP and physical NAO bindings. For PCA-generated auxiliary bases, record `auxiliary_basis.mode = pca_generated`, threshold, and input evidence; never bind a nonexistent `.abfs` file.
7. Sanitize all archived files before committing (see "Path sanitization" below).
8. Regenerate all generated files (see "Generated files to update" below).
9. Run ALL tests and checks (see "CI pipeline" below).
10. Inspect the diff and stage only intended paths. Exclude unrelated untracked files.
11. Commit and push only when requested/authorized, using repository attribution rules. Never bypass hooks or force-push.

## Record types

- `band`: require numerical band data, a provenance-linked figure, and scoped gap properties.
- `large_system_gw`: require a complete finite QP table, sampled-grid observable, completion log, atom/state counts, runtime/resources, and explicit auxiliary-basis provenance; do not require or invent a band figure.
- `rpa_energy`: require the complete q/frequency aggregation, finite correlation energy, and completion evidence.
- `reader_conversion`: require separately approved conversion provenance, converter identity, runtime receipt, validated reader header and dimensions, and an explicit statement that no RPA/GW scientific result is claimed. Keep this record type separate from `large_system_gw`.

## Required record fields for new calculations

Every new calculation record must include:

- `id`: unique case identifier (e.g., `c2048-reader-v1-20260607`)
- `material`: element or compound name (e.g., `C`, `MoS2`)
- `formula`: chemical formula (e.g., `C2048`, `MoS2`)
- `dimension`: `"2d"` or `"3d"`
- `status`: one of `gw_validated`, `gw_diagnostic`, `path_diagnostic`, `pbe_only`, `failed`, `pending`, `generation_only`
- `record_type`: one of `band`, `large_system_gw`, `rpa_energy`, `reader_conversion`
- `files`: object with `inputs`, `results`, `logs`, `figures` arrays (each entry has `path`, `sha256`, `size_bytes`, `role`, `label`, `original_name`, `original_sha256`, `transformation`, `scientific_role`)
- `software`: object with `abacus` (or `fhi_aims`) and `librpa` entries, each with `commit` (40-char hex) or `executable_sha256`, and `source_url`
- `workflow.frontend`: `"abacus"` or `"fhi_aims"`
- `computational_scale`: `atom_count`, `ao_count`, `matrix_rows`, `matrix_columns`, `state_count`, `occupied_states`, `unoccupied_states` (as applicable)
- `species`: array of `{element, set_id}` bindings (exact, production-linked)
- `summary`: `observable`, `value`, `unit`, `gap_definition` (as applicable)
- `source`: `collection`, `repository` (optional)

### Performance and cluster fields (required since 2026-10-14)

- `cluster_label`: cluster name (e.g., `"df_dcu"`)
- `accelerators`: `{type, per_node, total}` (if applicable)
- `nodes`, `cpus`, `elapsed_seconds`: resource evidence
- `accelerator_label`: human-readable summary (e.g., `"DCU x4/node (1024 total)"`)
- `structure_identity`: SHA-256 fingerprint for same-structure comparison across records

## Path sanitization — CRITICAL

The `public_scan.py` CI gate rejects files containing these patterns:

| Pattern | Replace with | Reason |
|---|---|---|
| `/Users/<username>` | `/HPC/` | Private workstation path |
| `/home/<username>` | `/HPC/` | Private HPC home path |
| `/work<N>/<username>` | `/HPC/` | Private HPC work directory |
| `SLURM_JOB_ID` | `SLURM_JOBID` | Scheduler internal variable |
| `ssh://` | (remove line or redact) | Private connection string |

Sanitize ALL files before committing. Use `/HPC/` (not `/home/USER/`) because the scanner regex still matches `/home/<any-username>/`. After sanitization, recompute SHA-256 values in `record.json` since file content changed.

## Display layer contract — what users see vs what stays internal

The database has two layers: **data** (record.json, immutable) and **display** (JavaScript rendering, user-facing). Technical fields that are NOT shown to users:

- SHA-256 hashes of files, documents, converters, executables — kept in record.json, NOT rendered in detail pages
- Reader-v1 header numeric values — kept in record.json, NOT shown
- Internal data paths (e.g., `data/calculations/3d/C/c2048...`) — kept in record.json for file access, NOT displayed
- `archive_commit`, `archive_directory` — NOT shown in source info
- Raw commit hashes (40-char hex) — replaced with "Source code" link to GitHub
- `GW job_id` — NOT shown in detail page metric grid

What IS shown to users:
- File name, role, size, View/Download buttons
- Calculation ID, collection, source repository link, observable
- Software name + "Source code" link (if GitHub URL available)
- Band gaps, QP energies, RPA correlation energy, wall time, nodes, CPUs
- Atoms, matrix dimensions, state counts, cluster label, accelerator info

When building a new record, include ALL technical fields in record.json (SHA-256, paths, headers, etc.) for data integrity — they just won't appear in the rendered page.

## Generated files to update after data changes

After adding or modifying any calculation data:

```bash
# 1. Regenerate the catalog (database/data.json)
python3 scripts/library.py --write-catalog

# 2. Regenerate the log index (data/log-index.json) — required when adding log files
python3 scripts/build_indexes.py --write

# 3. Regenerate the missing-evidence report (database/missing-evidence.html)
python3 scripts/export_missing_evidence.py --write

# 4. Verify all three
python3 scripts/library.py --check-catalog
python3 scripts/build_indexes.py --check
python3 scripts/export_missing_evidence.py --check
```

Never hand-edit `database/data.json`, `data/log-index.json`, or `database/missing-evidence.html`. Always use the scripts.

## CI pipeline — ALL must pass

Two GitHub Actions workflows run on every push:

### Validate database (runs on push + PR)

```
node --check database/app.js
node --test tests/*.mjs              ← runs ALL .mjs test files, not just one
python scripts/library.py --check-completeness --completeness-report ...
python scripts/library.py --check-catalog
python scripts/build_indexes.py --check
python scripts/public_scan.py .
python -m unittest discover -s tests -v
```

### Publish database (runs on push to main)

Runs the same checks plus:
```
python scripts/export_missing_evidence.py --check --report-output ...
python scripts/build_site.py --output _site
```

If any check fails, the site is NOT deployed. The last successful deployment remains live.

**Critical**: `node --test tests/*.mjs` runs ALL test files in the `tests/` directory. There are currently 4 files: `test_records.mjs`, `test_radial.mjs`, `test_properties_ui.mjs`, `test_search.mjs`. When updating rendering code, verify ALL tests pass, not just the file you think is relevant.

## What to add

- Real, readable INPUT/KPT/STRU/librpa.in/slurm script files with exact SHA-256
- Program output files (stdout, stderr) that contain completion markers
- Band data files (KS_bands.dat, GW_bands.dat, EXX_bands.dat) for `band` records
- QP table output for `large_system_gw` records
- Reader conversion receipt and log for `reader_conversion` records
- Band figures (SVG/PNG/PDF) generated by `scripts/generate_band_figures.py`
- Full software identity: 40-char Git commit (preferred) or executable SHA-256
- Cluster, node, CPU, accelerator, wall-time evidence
- Descriptive file names (e.g., `abacus_INPUT`, `librpa_gw.in`, `gw_slurm_script.sh`) in `path` field; keep `original_name` for the source filename
- `transformation: "none"` for byte-preserved files; describe any redaction otherwise

## What NOT to add — explicit prohibitions

### Data integrity

- **No private paths**: `/home/<user>`, `/work<N>/<user>`, `/Users/<user>`, `ssh://` — CI will reject these
- **No `SLURM_JOB_ID`** (with underscore) — use `SLURM_JOBID` (no underscore)
- **No credentials, hostnames, or IP addresses** in archived files
- **No binaries** whose redistribution is not authorized (executables, `.so`, `.a` libraries)
- **No symlinks** as evidence — copy real bytes, record the SHA-256 of the actual content
- **No fabricated values**: do not invent gaps, QP energies, or correlation energies
- **No relabeling**: a path-resolved or sampled-Γ gap is not a fundamental gap; a raw-band result is not a validated GW gap
- **No descriptive aliases as production bindings**: `basis_candidates` are follow-up candidates, not exact bindings
- **No hand-editing** of generated files (`data.json`, `log-index.json`, `missing-evidence.html`)

### Scientific scope

- **No scheduler-only acceptance**: Slurm `COMPLETED` does not prove scientific success — require the program's own completion marker
- **No truncated results**: reject partial QP tables, single-frequency RPA, or missing states
- **No guessing software identity**: an unknown commit must remain unknown and block CI, not be filled with HEAD or a branch name
- **No expanding the historical exception baseline**: `data/historical-software-identity-exceptions.json` is a fixed list; new records must provide their own identity
- **No mixing record types**: a `reader_conversion` record cannot attach a GW gap as its own result
- **No NaN/Inf hiding**: genuine nonfinite values are diagnostics; keep them, do not delete or relabel as zero

### Process

- **No import before approval**: never copy files or create records until the user approves the exact candidate
- **No commit/push without authorization**: commit only when the user explicitly requests it
- **No hook bypass**: never use `--no-verify` or `--no-gpg-sign`
- **No force-push**: never `--force` to the main branch
- **No unrelated files in commits**: stage only intended paths, exclude untracked artifacts
- **No Codex/OpenAI co-authored-by**: repository attribution is AroundPeking `<gonghuanjing@iphy.ac.cn>`

## File naming conventions

Archived files use descriptive names in the `path` field while preserving `original_name`:

| Source file | Archived path | original_name |
|---|---|---|
| `INPUT` | `inputs/abacus_INPUT` | `INPUT` |
| `KPT` | `inputs/abacus_KPT` | `KPT` |
| `STRU` | `inputs/abacus_STRU` | `STRU` |
| `run_abacus.sh` | `inputs/abacus_run_script.sh` | `run_abacus.sh` |
| `librpa.in` (GW) | `inputs/librpa_gw.in` | `librpa.in` |
| `librpa.in` (RPA) | `inputs/librpa_rpa.in` | `librpa.in` |
| `cal_abacus_hip.sh` (GW) | `inputs/gw_slurm_script.sh` | `cal_abacus_hip.sh` |
| `cal_abacus_hip.sh` (RPA) | `inputs/rpa_slurm_script.sh` | `cal_abacus_hip.sh` |
| Program stdout | `logs/<task>_stdout.log` | original filename |
| Program stderr | `logs/<task>_stderr.log` | original filename |
| Slurm log | `logs/<task>_slurm_stdout.log` | `slurm-<jobid>.out` |

## Directory structure

```
data/calculations/{2d,3d}/<Material>/<case-id>/
  record.json
  inputs/
    abacus_INPUT, abacus_KPT, abacus_STRU, ...
    librpa_gw.in, librpa_rpa.in, ...
    *_slurm_script.sh
  results/
    gw_output_rank0.out, rpa_output_rank0.out, ...
    reader_v1_conversion_receipt.json, ...
    KS_bands.dat, GW_bands.dat, EXX_bands.dat (for band records)
    *.svg, *.png, *.pdf (figures)
  logs/
    *_slurm_stdout.log, *_slurm_stderr.log, ...
    abacus_stdout.log, reader_v1_conversion_log.out, ...
```

## Failure and stop conditions

Stop and report without importing when any of these occurs:

- No exact user approval for the current candidate digest.
- Source readset changed after approval.
- Program output is partial, nonfinite, internally inconsistent, or lacks its own success marker.
- Only a scheduler completion or reader/converter success is available.
- Observable scope cannot be stated accurately.
- Input, physical basis, or auxiliary-basis provenance would require guessing.
- A new material lacks a full source commit and also lacks the exact executable SHA-256 for any executing front end or LibRPA; this must fail intake and CI rather than expanding the historical exception baseline.
- A target path already contains different bytes.
- Tests fail or the generated catalog is stale.
- Private paths or scheduler identifiers remain in archived files after sanitization.

Keep unresolved scientific limitations visible in record metadata and internal validation. Do not expose internal CI or draft-status warnings in the formal website UI.

## Approval receipt format

```json
{
  "schema_version": 1,
  "approved": true,
  "candidate_sha256": "<64-char hex>",
  "user_statement": "<verbatim user approval text>",
  "timestamp": "<ISO 8601>"
}
```

The user statement must be the exact words the user said when approving, not a paraphrase. If the user said "可以，收录吧", that is the statement — do not translate or expand it.
