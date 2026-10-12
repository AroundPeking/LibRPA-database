# Contributing to the ABACUS + LibRPA GW database

Use the companion [basis skill](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill) for the generation and validation method. This repository is the data layer: it receives immutable element-set and calculation records.

## Before adding files

Confirm that the PP, NAO, and ABF may be redistributed. Keep the source URL, release or archive commit, license status, original SHA-256, and any redaction note. Do not add private paths, hostnames, scheduler output, credentials, or binaries whose redistribution is not authorized.

## Add an element set

1. Put byte-preserved payloads in `data/elements/<Element>/pseudopotentials/`, `orbitals/`, `for_aux/`, or `auxiliary/`, using the SHA-256 as the filename stem.
2. Create `sets/<set-id>/set.json` with exact roles, hashes, dimensions, generation evidence, validation scope, and source information.
3. Use a new immutable set ID whenever a payload or PP/NAO/ABF binding changes.

## Add a calculation

Create `data/calculations/2d/<material>/<case-id>/` or `data/calculations/3d/<material>/<case-id>/`. Keep portable `inputs`, `results`, `logs`, and `figures` files. Bind exact set IDs in `species` only when the production association is proven. Otherwise leave `species` empty and explain the missing linkage in `missing`.

Use `basis_candidates` for useful follow-up sets whose exact production binding is not proven. Use `gw_validated` only when the stated observable and physical gates passed; retain completed but incomplete or anomalous work as `gw_diagnostic`, `path_diagnostic`, or `failed`.

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
```

## Checks

```bash
python3 scripts/library.py --write-catalog
python3 scripts/build_indexes.py --write
python3 scripts/public_scan.py .
python3 -m unittest discover -s tests -v
git diff --check
```

These checks do not compile ABACUS or LibRPA. Review the exact PP/NAO/ABF association, software commit identity, and physical gate evidence before calling a record validated.

The generated log index is a bijection: every retained file under a case's
`logs/` directory must appear exactly once in `data/log-index.json`. A basis
set enters `data/release-index.json` only when both the set and its linked case
are explicitly `publishable`; the basis-skill mirror then validates those
same IDs and hashes before accepting a copy.
