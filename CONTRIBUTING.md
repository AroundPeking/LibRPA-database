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

## Checks

```bash
python3 scripts/library.py --write-catalog
python3 scripts/public_scan.py .
python3 -m unittest discover -s tests -v
git diff --check
```

These checks do not compile ABACUS or LibRPA. Review the exact PP/NAO/ABF association, software commit identity, and physical gate evidence before calling a record validated.
