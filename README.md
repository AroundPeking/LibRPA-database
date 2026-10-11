# ABACUS + LibRPA GW database

This repository is the data companion to the [ABACUS + LibRPA GW basis skill](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill). It stores the hash-addressed PP, physical NAO, optional `for_aux` orbital, ABF, inputs, logs, figures, and KS/EXX/GW results collected for ABACUS + LibRPA workflows.

The catalog is split into `2d` and `3d`. Each element has its own directory under `data/elements/<Element>/`, and each calculation is under `data/calculations/2d/` or `data/calculations/3d/`. The searchable static catalog is in [`database/index.html`](database/index.html); its machine-readable source is [`database/data.json`](database/data.json).

The current snapshot contains 86 immutable basis-set records covering 27 elements and 33 calculation records (16 two-dimensional and 17 three-dimensional). These are historical and diagnostic records with explicit scope. The database does not declare a universal best PP/NAO/ABF: use the exact set IDs, hashes, producer commits, observable, and passed gates before reusing a file.

The generated [`data/log-index.json`](data/log-index.json) gives every retained
log exactly one calculation owner. [`data/release-index.json`](data/release-index.json)
contains only basis sets explicitly marked `publishable`; it is currently
empty because the imported historical records still lack complete public
release evidence. The companion basis-skill repository mirrors only this
release index.

## Use

Serve the repository as a static site to open the catalog, or read `database/data.json` directly. A record's `species` entries are exact production bindings only when the source audit proved them. `basis_candidates` are useful follow-up files whose exact production binding remains unproven. Failed and anomalous candidates stay in the database as evidence.

The local catalog has separate Materials and Basis sets views. Search accepts a
material, formula, element, set ID, or calculation ID; the dimension filter
keeps 2D and 3D records visibly separate. The material list stays compact and
opens a dedicated detail page for each record. That page contains the DFT/EXX/GW
figures, raw band files, RPA fields when recorded, validation gates, input
files, logs, and ABACUS/LibRPA commits. Figures are deliberately kept off the
list so the catalog remains usable when more materials are added.

For archived 3D ABACUS band tables, the checked-in SVG figures can be rebuilt
with `python3 scripts/generate_band_figures.py`. The script preserves the raw
tables and records source paths and SHA-256 hashes in each figure sidecar.

The generation protocol, validation ladder, and ABACUS-to-LibRPA handoff are documented in the companion skill, especially [`references/database.md`](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill/blob/main/references/database.md), [`SKILL.md`](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill/blob/main/SKILL.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Validate

All checks are static and use the Python standard library; they do not compile ABACUS or LibRPA.

```bash
python3 scripts/library.py --write-catalog
python3 scripts/build_indexes.py --write
python3 scripts/public_scan.py .
python3 -m unittest discover -s tests -v
```

When adding a record, preserve the original and published SHA-256 values, record any redaction, use repository-relative paths, and verify redistribution terms for every third-party payload. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

The scripts, schema notes, and catalog UI are MIT licensed. Third-party software and scientific data retain their own licenses and reuse conditions; check the source record before redistributing a payload.
