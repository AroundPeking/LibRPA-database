<!--
Data pull request: fill in every section below.
Code, website, or documentation pull request: describe the change and the
checks you ran, and delete the data sections.
-->

## What this pull request adds

- [ ] A calculation record: `data/calculations/<2d|3d>/<Material>/<case-id>/`
- [ ] A basis set or a calculated property
- [ ] Code, website, or documentation

## Candidate summary (data)

- **Source run and task:**
- **Record type:** `band` / `large_system_gw` / `rpa_energy` / `reader_conversion`
- **Observable and its exact scope:** <!-- e.g. sampled band-path G0W0 gap; not a global fundamental gap -->
- **Finite-result checks:** <!-- complete table, expected states/q-points/frequencies present; nonfinite solver outputs kept visible -->
- **Software identity:** <!-- front end and LibRPA: full 40-hex commit or executable SHA-256 each -->
- **Basis bindings:** <!-- element -> set id for every species -->
- **Missing evidence and limitations:**

## Evidence checklist (data)

- [ ] Original inputs archived (`INPUT`/`KPT`/`STRU`/`librpa.in`, or `control.in`) with SHA-256
- [ ] Program output with its own completion marker (not scheduler state alone)
- [ ] Private paths, hostnames, and scheduler identifiers sanitized before hashing
- [ ] Generated files rebuilt with the scripts, not edited by hand
- [ ] Changed test pins explained here, one line each

## Gates run locally

- [ ] `python3 scripts/library.py --check-catalog`
- [ ] `python3 scripts/build_indexes.py --check`
- [ ] `python3 scripts/public_scan.py .`
- [ ] `python3 -m unittest discover -s tests`
- [ ] `node --test tests/*.mjs`
