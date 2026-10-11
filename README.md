# ABACUS + LibRPA GW database

This repository is the data companion to the [ABACUS + LibRPA GW basis skill](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill). It stores the hash-addressed PP, physical NAO, optional `for_aux` orbital, ABF, inputs, logs, figures, and KS/EXX/GW results collected for ABACUS + LibRPA workflows.

The catalog is split into `2d` and `3d`. Each element has its own directory under `data/elements/<Element>/`, and each calculation is under `data/calculations/2d/` or `data/calculations/3d/`. The searchable static catalog is in [`database/index.html`](database/index.html); its machine-readable source is [`database/data.json`](database/data.json).

The current snapshot contains 86 immutable basis-set records covering 27 elements and 33 calculation records (16 two-dimensional and 17 three-dimensional). These are historical and diagnostic records with explicit scope. The database does not declare a universal best PP/NAO/ABF: use the exact set IDs, hashes, producer commits, observable, and passed gates before reusing a file.

## Use

Serve the repository as a static site to open the catalog, or read `database/data.json` directly. A record's `species` entries are exact production bindings only when the source audit proved them. `basis_candidates` are useful follow-up files whose exact production binding remains unproven. Failed and anomalous candidates stay in the database as evidence.

The generation protocol, validation ladder, and ABACUS-to-LibRPA handoff are documented in the companion skill, especially [`references/database.md`](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill/blob/main/references/database.md), [`SKILL.md`](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill/blob/main/SKILL.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Validate

All checks are static and use the Python standard library; they do not compile ABACUS or LibRPA.

```bash
python3 scripts/library.py --write-catalog
python3 scripts/public_scan.py .
python3 -m unittest discover -s tests -v
```

When adding a record, preserve the original and published SHA-256 values, record any redaction, use repository-relative paths, and verify redistribution terms for every third-party payload. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

The scripts, schema notes, and catalog UI are MIT licensed. Third-party software and scientific data retain their own licenses and reuse conditions; check the source record before redistributing a payload.
