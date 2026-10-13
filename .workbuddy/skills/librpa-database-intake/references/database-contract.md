# Database record and import contract

## Record types

### `band`

Require portable same-record INPUT/KPT/STRU/LibRPA controls, exact basis bindings, immutable file hashes, numerical band data, a visible provenance-linked band figure, and one finite scoped eV property per archived method.

### `large_system_gw`

Require `record_type: "large_system_gw"`, a regular-grid workflow without a band path, positive atom/AO/state counts, a complete finite QP table, sampled-grid PBE and G0W0 properties, program completion, resources, and explicit auxiliary-basis provenance. A missing `band_kpath_info` is acceptable only when the regular-grid QP task completes and no band-path claim is made.

### `rpa_energy`

Require complete q/frequency aggregation, a finite correlation energy with unit and definition, program completion, exact controls, basis provenance, and resources. A single frequency or partial q-point output is not complete.

### `reader_conversion`

Use only for a verified reader-format conversion that is useful as provenance but is not an RPA/GW scientific result. Require the converter SHA-256, conversion job/runtime receipt, validated binary header and matrix dimensions, and an explicit `scientific_result_available: false` contract. Do not attach a gap, correlation energy, QP table, or RPA/GW completion claim. Keep this record type separate from `large_system_gw`.

## Generated auxiliary basis

Record `auxiliary_basis.mode = "pca_generated"`, a positive finite threshold, and same-record INPUT evidence. Require exactly one matching `exx_pca_threshold` in the production INPUT and no active `ABFS_ORBITAL` declaration. Continue to require exact PP and physical NAO bindings.

## Software identity

Prefer a full 40-character Git commit or supported immutable 64-character revision. If a historical commit cannot be recovered, retain `commit: null`, record executable SHA-256 and evidence, and keep the record below strict publishable status. Never substitute a current checkout for the historical executable.

## Approved import plan

Use plan JSON with `schema_version: 1`, `candidate_sha256`, `copies`, `json_writes`, and optional expected issues. Every update to an existing JSON target must include its pre-write `expected_sha256`; create-only JSON may use null. Use a separate approval receipt with `schema_version: 1`, `approved: true`, the exact candidate digest, and a non-empty verbatim user statement. Refuse absolute/traversal targets, symlink sources, changed source bytes, stale JSON targets, and immutable evidence collisions.
