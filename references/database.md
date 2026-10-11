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

## Calculation record

Every calculation record has `dimension` (`2d` or `3d`), `material`, `status`,
`software`, `summary`, `files`, and `missing`. The allowed statuses are:

| Status | Meaning |
| --- | --- |
| `gw_validated` | The documented target observable passed the stated physical gates for this exact protocol. |
| `gw_diagnostic` | A completed GW result is retained, but at least one physical or provenance gate is incomplete. |
| `path_diagnostic` | A band-path or frontier diagnostic is retained; it is not a complete fundamental-gap claim. |
| `pbe_only` | Only the PBE/KS or matching screen was accepted. |
| `generation_only` | Atomic generation and file/radial checks only. |
| `failed` | A recorded gate failed; keep the files for diagnosis. |
| `pending` | Inputs or required outputs are not yet complete. |

`software.abacus.commit` and `software.librpa.commit` must be full immutable
IDs or `null`. A shortened ID may be kept as `abbreviated_commit`, together
with a note that the full identity was not recorded. A full ID resolved from a
unique local object is still marked as historical resolution when the original
log printed only a prefix.

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
