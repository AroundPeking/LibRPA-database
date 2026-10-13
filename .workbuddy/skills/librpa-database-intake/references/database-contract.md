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
