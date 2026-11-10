# Basis labels: describing a set by what it contains

An element set is named by its facts:

    Si-SG15-4e-3s3p2d-22-abf397

element, family, valence electrons, orbital shells, orbital functions per atom,
auxiliary functions per atom. A reader can compare two of them without looking
anything up. The three facts that decide the choice, plus one history:

* how many electrons the pseudopotential keeps in the valence (Si: 4);
* how large the numerical orbital is (`3s3p2d`, 22 functions per atom);
* how large the auxiliary basis is (397 functions per atom);
* what the set has already produced (Si GW gap 1.06 eV; SiC GW gap 2.26 eV).

`scripts/basis_labels.py` derives those facts and `build_catalog` attaches them
to every basis set as a `label` block, so the website and any downstream tool
read one computed statement instead of interpreting an id.
`scripts/rename_basis_sets.py` puts the same facts into the id itself, which is
why `Si-SG15-4e-3s3p2d-22-abf397` and the label sentence for that set agree.

## The id rule, and when the facts are not enough

    <Element>-<Family>-<valence>e-<NAO shells>-<orbital functions>-abf<auxiliary functions>

or `-noabf` when the set has no auxiliary basis. A set with no `pp`/`nao`
payload (an FHI-aims species-defaults fragment) cannot be sized and keeps
`<Element>-<Family>` only.

Two different payloads can share every one of those numbers - `Mo-GTH` and
`Mo-SG15` both read `14e-6s3p3d2f-44` - so the id gains the first eight
characters of the role-to-SHA-256 map. When two records hold byte-identical
payloads, the suffix is the calculation that used the copy, because that is the
only difference left; if nothing used either, the script refuses and asks for
the two records to be merged rather than inventing a distinction.

## Derived, never stored by hand

Every field is recomputed from the archived payload bytes:

* the valence count is `z_valence` read from the UPF header;
* the orbital and auxiliary dimensions are `sum(count * (2l + 1))` over the
  per-l channels in the `.orb` / `.abfs` header;
* the results come from the calculation records, matched by
  `species[].set_id`, quoting a GW gap when the record has one and an RPA
  cohesive energy otherwise. A record with only a PBE gap has no headline: a
  DFT number presented next to GW results would mislead.

Nothing is hand-entered, so `python3 scripts/basis_labels.py --check` can prove
the catalog is in sync, and a payload change is picked up automatically.

## The file is the authority, not the index

The recorded `dimensions` disagree with the files for 60 auxiliary bases: they
omit the J and K channels their own header lists, so Si-SG15 is recorded as 365
while the file contains 397. The label counts what a calculation will open,
which is why the two numbers differ and why the derived value is the one shown.

## `used_by` is rebuilt from the records

`used_by` was maintained by hand at intake time and covers 30 of the 76 sets
that records actually reference. The label rebuilds it from the records, so the
two agree. A set with no linked record keeps whatever it had rather than losing
history the records cannot express.

## What the site shows

The basis table leads with "What it contains" (the three facts) and "What it
produced" (the linked results); the id stays in the detail header as
bookkeeping. The detail page repeats the facts in a panel above the provenance
notice, because that is the order a reader needs them in.

```bash
python3 scripts/basis_labels.py             # statistics only
python3 scripts/basis_labels.py --write     # refresh database/data.json in place
python3 scripts/basis_labels.py --check     # fail when the catalog is stale
```

Ordinary catalog regeneration computes the labels automatically:
`python3 scripts/library.py --write-catalog` then `scripts/build_catalog.py`.
