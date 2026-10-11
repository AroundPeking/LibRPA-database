# Search and Extensible Properties Design

## Goal

Make material and basis search reliable for ordinary, multi-word, and formula
queries, and give calculation records one consistent way to publish additional
DFT/GW-derived properties. The current catalog has electronic-structure
results; topology and other property categories must be visible as supported
slots without implying that results already exist.

## Current behavior and failure modes

The material search currently lowercases the query and tests whether that whole
string occurs as one substring in a small hand-built set of fields. It does
not split multi-word queries, normalize punctuation or Unicode formula
subscripts, or search all recorded property and provenance values. Basis search
has a separate implementation, so its behavior can diverge.

The static page loads `database/data.json` with `fetch`. It must be served over
HTTP(S). Opening `database/index.html` with a `file://` URL prevents browsers
from loading the JSON data reliably, and the local preview URL is unavailable
when its development server is stopped.

## Search behavior

Use one shared search normalizer and matcher for materials and basis records.
Normalize Unicode compatibility forms, case, whitespace, and punctuation;
split the query into tokens; and require every token to match at least one
value in the record's searchable corpus. The corpus includes material name,
formula, element and basis links, record ID, dimension, observable, numerical
properties, methods, software commit IDs, and public file labels/paths. Apply
the same rules to basis IDs, element, family, scope, linked calculations, and
asset labels.

An empty query matches all records. Dimension and publication filters remain
independent and combine with search using AND semantics. Formula subscripts
such as `MoS₂` should match ASCII `MoS2`; punctuation differences such as
`MoS2-WS2` versus `MoS2 WS2` should not prevent a match.

## Property record contract

Each calculation `record.json` may include a `properties` array. Each entry is
one reported observable and has this shape:

```json
{
  "key": "band_gap",
  "category": "electronic",
  "label": "Band gap",
  "method": "G0W0",
  "value": 2.86,
  "unit": "eV",
  "status": "reported",
  "definition": "Selected band-path quasiparticle gap",
  "evidence": [
    "data/calculations/3d/GaN/gan-paper-pca1e-6/results/GW_band_spin_1.dat"
  ]
}
```

`key`, `category`, `label`, `method`, `value`, `unit`, `status`, and a
non-empty `evidence` list are required. `value` may be a JSON scalar, array, or
object so topological invariants and tensor-like properties can use the same
contract. `definition`, `uncertainty`, and `conditions` are optional. Status
is one of `reported`, `validated`, `provisional`, or `failed`; it describes
the evidence for this property and does not inherit internal record status
labels. Evidence paths must resolve to files already declared under the same
record's `files` groups; every such file continues to be checked against its
SHA-256 hash. Categories use stable lowercase slugs and remain open to future
contributions.

Existing `summary.dft_gap_ev`, `summary.exx_gap_ev`, `summary.gw_gap_ev`, or
`summary.value` values are migrated into `properties` with their original
values, methods, and matching result-file evidence. A `summary.value` that
duplicates `summary.gw_gap_ev` produces one property row. Imported records use
`reported` unless existing evidence explicitly establishes a stronger
property-level status. No RPA correlation-energy value exists in the current
records, so that value is not fabricated; the category remains available for
future contributions. The existing `summary` fields remain during this phase
for backward compatibility and existing plots are unchanged.

## Detail page

Add a property section to each material detail page. Its category navigation
includes Electronic structure, Topology, Optical, Magnetic, Structural, and
Other. A category with records displays a compact table of property, method,
value, unit, status, and evidence links. A category without records displays a
clear “No results reported” state and a link to the contribution instructions.
The empty state is not a numerical placeholder and must not be indexed as a
result.

Electronic band figures remain in their existing band-structure section.
Property categories are data-driven: a newly contributed category can be
displayed using the same table without a page-specific component. The initial
empty categories are supplied by a small UI registry so visitors can see the
extension points before any topology or optical records are contributed.

## Validation and tests

Extend the standard-library validator to accept an absent `properties` field
for older records and validate each present entry's required fields and
evidence links. Reject empty evidence, invalid category slugs, non-JSON values,
and evidence paths that are absent from the same calculation record.

Add automated tests for token matching, case and punctuation normalization,
Unicode formula subscripts, multi-token AND matching, basis search parity, and
property validation/evidence ownership. Regenerate `database/data.json` from
record files and require the catalog check to pass. Verify that existing
summary values are faithfully represented in the generated property arrays,
and that empty Topology/Optical categories render without invented values.

The site remains static and GitHub Pages compatible; this change adds no
server, account system, job submission, or claim that the existing archived
GW values have passed new physical validation.
