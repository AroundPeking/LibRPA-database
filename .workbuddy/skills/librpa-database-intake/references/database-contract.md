# Database record and import contract

## Record types

### `band`

Require portable same-record INPUT/KPT/STRU/LibRPA controls, exact basis bindings, immutable file hashes, numerical band data, a visible provenance-linked band figure, and one finite scoped eV property per archived method.

### `large_system_gw`

Require `record_type: "large_system_gw"`, a regular-grid workflow without a band path, positive atom/AO/state counts, a complete finite QP table, sampled-grid PBE and G0W0 properties, program completion, resources, and explicit auxiliary-basis provenance. A missing `band_kpath_info` is acceptable only when the regular-grid QP task completes and no band-path claim is made.

### `rpa_energy`

Require complete q/frequency aggregation, a finite correlation energy with unit and definition, program completion, exact controls, basis provenance, and resources. A single frequency or partial q-point output is not complete.

### `reader_conversion`

Use only for a verified reader-format conversion that is useful as provenance but is not itself an RPA/GW scientific result. Require the converter SHA-256, conversion job/runtime receipt, validated binary header and matrix dimensions, and an explicit `scientific_result_available: false` contract. Do not attach a gap, correlation energy, or QP table. A bounded `associated_gw_run` audit may record a separate historical run's completion only when program completion markers and scheduler accounting were retained; it must state whether the band path was skipped and whether frontier rows are available. If frontier rows are absent, display completion plus `gap unavailable`, never a Fermi energy or unrelated QP state as a gap. Keep this record type separate from `large_system_gw`.

## Generated auxiliary basis

Record `auxiliary_basis.mode = "pca_generated"`, a positive finite threshold, and same-record INPUT evidence. Require exactly one matching `exx_pca_threshold` in the production INPUT and no active `ABFS_ORBITAL` declaration. Continue to require exact PP and physical NAO bindings.

## Software identity

Every new material must preserve an immutable identity for each executing code: prefer a full 40-character Git commit (or supported immutable 64-character revision), otherwise retain the SHA-256 of the exact executable and its evidence. A new record with neither identity must fail intake and CI. The fixed `data/historical-software-identity-exceptions.json` baseline accepts only the exact pre-existing calculation/software pairs listed there; it is not a template for new records, cannot waive non-software issues, and must reject unknown, duplicate, or stale entries. Never substitute a current checkout for the historical executable.

## Approved import plan

Use plan JSON with `schema_version: 1`, `candidate_sha256`, `copies`, `json_writes`, and optional expected issues. Every update to an existing JSON target must include its pre-write `expected_sha256`; create-only JSON may use null. Use a separate approval receipt with `schema_version: 1`, `approved: true`, the exact candidate digest, and a non-empty verbatim user statement. Refuse absolute/traversal targets, symlink sources, changed source bytes, stale JSON targets, and immutable evidence collisions.

## Performance and cluster fields (required since 2026-10-14)

Every new calculation must record computational resources:

- `cluster_label`: cluster name (e.g., `"df_dcu"`, `"df_iopcas_ghj"`)
- `accelerators`: `{type, per_node, total}` (e.g., `{"type": "DCU", "per_node": 4, "total": 1024}`)
- `accelerator_label`: human-readable summary (e.g., `"DCU x4/node (1024 total)"`)
- `nodes`: node count
- `cpus`: total CPU cores
- `elapsed_seconds`: wall time in seconds
- `workflow.frontend`: `"abacus"` or `"fhi_aims"`
- `structure_identity`: SHA-256 fingerprint for same-structure comparison

These appear in the detail page "Computational scale & performance" section and the result strip. The `structure_identity` hash enables same-structure comparison across different frontends/workflows.

## Display layer contract

The database separates data (record.json, immutable) from display (JavaScript rendering, user-facing). Technical fields kept in record.json but NOT rendered to users:

- File SHA-256, Document SHA-256, Converter SHA-256, Executable SHA-256, Original SHA-256
- Reader-v1 header numeric values
- Internal data paths (e.g., `data/calculations/3d/C/c2048...`)
- `archive_commit`, `archive_directory`
- Raw 40-character commit hashes (replaced with "Source code" link)
- `GW job_id`

What IS shown to users: file names, roles, sizes, View/Download, calculation ID, collection, repository link, software name + source link, band gaps, energies, wall time, nodes, CPUs, cluster, accelerators, atoms, matrix dimensions, state counts.

When building a new record, include ALL technical fields in record.json for data integrity — they just will not appear in the rendered page.

## Path sanitization

The `public_scan.py` CI gate rejects files containing:

- `/Users/<username>` — replace with `/HPC/`
- `/home/<username>` — replace with `/HPC/`
- `/work<N>/<username>` — replace with `/HPC/`
- `SLURM_JOB_ID` (with underscore) — replace with `SLURM_JOBID`
- `ssh://` — remove or redact

Use `/HPC/` as the replacement (not `/home/USER/`) because the scanner regex matches any `/home/<username>/` pattern. After sanitization, recompute SHA-256 values since file content changed.
