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
5. Treat silence, earlier general permission, scheduler state, a directory name, a prior candidate, or an ambiguous “继续” as no approval.
6. Never copy evidence into the repository, create a record, update the catalog, commit, or push before approval.
7. If any source file or scientific value changes after approval, invalidate approval, issue a new candidate SHA-256, and ask again.

## Phase A: discover and validate

Read `references/scientific-validation.md` and `references/database-contract.md`.

For each candidate:

- Confirm the scientific program finished successfully from its own output. Never accept Slurm `COMPLETED` alone.
- Confirm the requested RPA/GW task reached its scientifically final stage.
- Parse the full result, reject truncated tables, missing expected states/q-points/frequencies, nonfinite values, duplicate rows, and inconsistent counts.
- Preserve the exact observable scope. Label a Γ-point regular-grid gap as sampled Γ; never call it a global fundamental gap or a band-path gap.
- Verify INPUT/KPT/STRU/control files, physical basis identity, auxiliary-basis mode, software identity, executable hash when commits are unavailable, and resource evidence.
- Record known historical settings exactly. Do not replace them with current recommendations.
- Run `scripts/prepare_candidate.py` only on a local read-only snapshot when applicable. For remote sources, perform equivalent read-only checks remotely and calculate the same canonical receipt fields.
- Present missing immutable commits or basis evidence as limitations, not as reasons to fabricate substitutes.

## Phase B: import only after approval

After exact approval:

1. Re-read every approved source and verify its SHA-256, size, regular-file status, and absence of symlink substitution.
2. Build a plan containing the approved candidate digest, source-to-target mappings, expected hashes, final `record.json`, and expected validator issues.
3. Run `scripts/import_approved_candidate.py` with a separately stored approval receipt containing the user's approval statement and candidate digest.
4. Use exclusive creation for new evidence and atomic replacement for generated JSON. Refuse collisions with different bytes.
5. Express workflow type explicitly:
   - `band`: require numerical band data, a provenance-linked figure, and scoped gap properties.
   - `large_system_gw`: require a complete finite QP table, sampled-grid observable, completion log, atom/state counts, runtime/resources, and explicit auxiliary-basis provenance; do not require or invent a band figure.
   - `rpa_energy`: require the complete q/frequency aggregation, finite correlation energy, and completion evidence.
   - `reader_conversion`: require separately approved conversion provenance, converter identity, runtime receipt, validated reader header and dimensions, and an explicit statement that no RPA/GW scientific result is claimed.
6. Preserve exact PP and physical NAO bindings. For PCA-generated auxiliary bases, record `auxiliary_basis.mode = pca_generated`, threshold, and input evidence; never bind a nonexistent `.abfs` file.
7. Regenerate the catalog with the repository scripts. Do not hand-edit generated catalog data.
8. Run Python, Node, browser, mobile, public-scan, and catalog checks required by the repository.
9. Inspect the diff and stage only intended paths. Exclude unrelated untracked files.
10. Commit and push only when requested/authorized, using repository attribution rules. Never bypass hooks or force-push.

## Failure and stop conditions

Stop and report without importing when any of these occurs:

- No exact user approval for the current candidate digest.
- Source readset changed after approval.
- Program output is partial, nonfinite, internally inconsistent, or lacks its own success marker.
- Only a scheduler completion or reader/converter success is available.
- Observable scope cannot be stated accurately.
- Input, physical basis, or auxiliary-basis provenance would require guessing.
- A target path already contains different bytes.
- Tests fail or the generated catalog is stale.

Keep unresolved scientific limitations visible in record metadata and internal validation. Do not expose internal CI or draft-status warnings in the formal website UI.
