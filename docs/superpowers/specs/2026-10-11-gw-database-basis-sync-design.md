# ABACUS + LibRPA GW database and basis mirror

## Goal

Provide one public, auditable source for ABACUS + LibRPA GW/RPA basis and
calculation evidence, plus a smaller companion repository that distributes
only basis sets that have a corresponding database calculation record. The
database must support element and material lookup for both 2D and 3D records.
The website is a static, GitHub Pages compatible catalog; it does not run
calculations or expose private paths.

## Repository boundaries

`abacus-librpa-gw-database` is the canonical evidence repository. It keeps all
historical candidates, including failed or incomplete diagnostics, under
separate `2d` and `3d` calculation trees. A basis set remains immutable once
published: changing any PP, physical NAO, `for_aux` orbital, or ABF creates a
new `set_id` and new hashes. Each calculation has one immutable `calculation_id`.

`abacus-librpa-gw-basis-skill` is the direct-use mirror. It copies only sets
whose database record explicitly marks them `publishable` and links them to at
least one database calculation. The mirror contains the payload files, a
portable manifest, SHA-256 hashes, and the source `set_id`/`calculation_id`;
failed candidates and database-only evidence stay in the database repository.
The skill documentation explains how to download and bind a published set but
does not duplicate private paths or scheduler state.

## Database record contract

Every new calculation record contains:

- `id`, `dimension` (`2d` or `3d`), material/formula, structure metadata, and
  a short description;
- exact species-to-`set_id` bindings, candidate sets, observable definitions,
  k/q meshes, Coulomb convention, and gate results;
- `software.abacus.commit` and `software.librpa.commit` as full immutable SHAs;
- `files.inputs`, `files.results`, `files.logs`, and `files.figures`, each with
  a repository-relative path, role, and SHA-256 digest;
- `publication` with `status`, `basis_set_ids`, `source_database_commit`, and
  an optional `supersedes` link.

New publishable cases require at least one input and one final output, full
ABACUS and LibRPA commits, and a basis link. Intermediate scratch files,
temporary restart files, scheduler output, and unreviewed raw working trees
are rejected. Existing historical records may remain `legacy_incomplete` when
the source evidence is unavailable, but they cannot be mirrored or marked as
publishable. Every log entry is keyed by exactly one `calculation_id`; a
generated log index rejects orphan or duplicate entries.

## Validation and CI

The database validator remains standard-library only and gains strict checks
for the new publication contract, required final artifacts, full commits,
intermediate-file exclusions, private-path scans, and log-to-record bijection.
The catalog generator is deterministic, so CI fails if `database/data.json` is
stale. A fixture test covers a valid new case and each rejection condition.

The basis-skill CI validates every mirror manifest against a checked-out,
pinned database revision. It fails if a `set_id` or `calculation_id` is absent,
the source record is not publishable, a copied hash differs, or a payload is
missing. The two repositories therefore remain independently downloadable but
cannot silently diverge. No CI job compiles ABACUS or LibRPA.

## Static website information architecture

The landing page follows the C2DB-style information architecture without
copying its CC BY-NC implementation: a global search accepts either an element,
material name, formula, or record ID; dimension and evidence filters remain
visible; and a basis-first browse view lists published sets by element and
family. Selecting a set shows its linked 2D/3D calculations. Selecting a
material opens a detail view with a compact summary and accordion sections:

1. structure and provenance;
2. PP / physical NAO / `for_aux` / ABF bindings;
3. DFT and EXX bands;
4. GW bands and gap/shift values;
5. RPA correlation energy and convergence/gate notes;
6. input, final-output, log, figure, and source-commit links.

The detail view uses stored figures when available and never invents a result
for a missing observable. 2D and 3D records remain visibly separate. The
catalog is generated from `database/data.json`, so the site works from a local
static server and GitHub Pages without a backend.

## Plotting contract

The database repository provides one reference `plot_bands.py` script and a
small documented input format. It produces the same publication style used by
the skill: explicit high-symmetry path labels, energy reference, raw band
indices, and separate occupied/low-conduction handling. The script records
the source calculation ID and input hash in the figure metadata. Parsing and
provenance tests run in CI; rendering is optional when Matplotlib is available.

## Contribution flow

1. Add immutable element assets and a database calculation bundle.
2. Run the local validator, catalog generator, public-path scan, and tests.
3. Add one log-index entry with the same `calculation_id` as the record.
4. Mark a set publishable only after the linked calculation and required gates
   are reviewed.
5. Copy that exact set into the skill mirror using its manifest and source
   database commit.

The database is the input/evidence side; the skill mirror is the reusable
distribution side. A later, better controlled calculation adds a new record
and can promote a new set without rewriting old evidence.

## Non-goals

This phase does not implement a server-side API, user accounts, online job
submission, automatic scientific ranking, or automatic replacement of a basis
based only on a smaller gap difference. Physical acceptance remains tied to
the recorded observable, producer provenance, and validation gates.
