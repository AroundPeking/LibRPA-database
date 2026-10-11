# Search and Extensible Properties Implementation Plan

> **For agentic workers:** Execute this plan inline in the isolated `codex/search-properties` worktree. Mark each step as it is completed and run its verification before continuing.

**Goal:** Fix catalog search across material and basis records, and provide a validated, contributor-friendly property model and detail-page interface for electronic, topological, optical, magnetic, structural, and future results.

**Architecture:** A small browser/Node-compatible search module normalizes and tokenizes queries, then matches all tokens across public record metadata. Calculation records gain a `properties` array with evidence paths checked against their declared files; existing gap summaries migrate into this array. The static detail page renders category tabs from a small registry plus any contributed categories.

**Tech Stack:** Plain JavaScript ES modules, Python 3 standard library, `node:test`, and existing `unittest` CI.

---

## File Map

- Create `database/search.mjs` for Unicode/punctuation normalization and shared record matching.
- Create `tests/test_search.mjs` for matching behavior using Node's built-in test runner.
- Modify `scripts/library.py` to validate property records and same-record evidence ownership.
- Modify `tests/test_library.py` to cover accepted and rejected property entries.
- Create `scripts/migrate_properties.py` as an idempotent, explicit migration from legacy summary gaps.
- Create `tests/test_property_migration.py` for legacy-summary mapping and duplicate suppression.
- Modify the 33 calculation `record.json` files and regenerate `database/data.json` with the migration script.
- Create `database/properties.mjs` for category metadata and property-section rendering.
- Modify `database/app.js` to use shared search and render interactive property categories on material details.
- Create `tests/test_properties_ui.mjs` to test category rendering and empty states without a browser dependency.
- Modify `references/database.md`, `CONTRIBUTING.md`, and `README.md` to document the property contribution contract and HTTP-only local preview.

## Task 1: Shared Search

**Files:** `database/search.mjs`, `tests/test_search.mjs`, `database/app.js`

- [ ] **Step 1: Add failing Node tests** for punctuation-insensitive multi-token matching, Unicode formula subscripts, and searching method/commit/file/property fields.
- [ ] **Step 2: Run `node --test tests/test_search.mjs`** and confirm the new tests fail because the module does not yet exist.
- [ ] **Step 3: Implement the shared matcher** with this contract:

```js
export function normalizeSearchText(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase("en-US")
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

export function matchesSearch(record, query) {
  const tokens = normalizeSearchText(query).split(/\s+/u).filter(Boolean);
  if (!tokens.length) return true;
  const values = [];
  const visit = value => {
    if (typeof value === "string" || typeof value === "number") values.push(value);
    else if (Array.isArray(value)) value.forEach(visit);
    else if (value && typeof value === "object") Object.values(value).forEach(visit);
  };
  visit(record);
  const corpus = normalizeSearchText(values.join(" "));
  return tokens.every(token => corpus.includes(token));
}
```

- [ ] **Step 4: Use the matcher in both catalog views.** For a basis set, match one combined object containing the set and its linked calculations. Keep dimension/publication filters independent and conjunctive with search.
- [ ] **Step 5: Run `node --test tests/test_search.mjs`** and require all search tests to pass.

## Task 2: Property Validation and Migration

**Files:** `scripts/library.py`, `scripts/migrate_properties.py`, `tests/test_library.py`, `tests/test_property_migration.py`, calculation `record.json` files, `database/data.json`

- [ ] **Step 1: Add failing validator tests** for a valid property, missing evidence, malformed category slug, and evidence not listed in the same record's `files` groups.
- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_library.py' -v`** and confirm the property-validation tests fail for the expected reason.
- [ ] **Step 3: Validate each property**: `key`, `category`, `label`, `method`, `value`, `unit`, and `status` are required; category matches `^[a-z][a-z0-9_]*$`; status is one of `reported`, `validated`, `provisional`, or `failed`; evidence is a non-empty list of repository paths declared by that calculation. Enforce uniqueness of `(category, key, method)` within one record. Accept JSON scalar, list, or object values.
- [ ] **Step 4: Add failing migration tests** proving `dft_gap_ev`, `exx_gap_ev`, `gw_gap_ev`, and a non-duplicate `summary.value` map to evidence-backed properties, while a duplicate summary value creates no duplicate GW row.
- [ ] **Step 5: Implement `scripts/migrate_properties.py`** as an idempotent command with `--root` and explicit `--write`; map DFT to `PBE`, EXX to `EXX`, standard GW gaps to `G0W0`, and archived path gaps to `GW path`. Link each item to the matching declared KS/EXX/GW result file. Imported entries use `reported` unless the calculation is already explicitly `gw_validated`. Preserve every legacy `summary` field.
- [ ] **Step 6: Run migration tests and write the 33 source records**, then run `python3 scripts/library.py --write-catalog` and `python3 scripts/library.py --check-catalog`.
- [ ] **Step 7: Run `python3 -m unittest discover -s tests -p 'test_library.py' -v` and `python3 -m unittest discover -s tests -p 'test_property_migration.py' -v`** and require all validator and migration tests to pass.

## Task 3: Property Detail Interface

**Files:** `database/properties.mjs`, `database/app.js`, `tests/test_properties_ui.mjs`

- [ ] **Step 1: Add failing UI-model tests** for the six initial categories, a numeric electronic property row with its evidence link, a future unknown category, and an empty Topology state without numeric values.
- [ ] **Step 2: Run `node --test tests/test_properties_ui.mjs`** and confirm the tests fail before the module exists.
- [ ] **Step 3: Implement the category registry** with Electronic structure (`electronic`), Topology (`topological`), Optical (`optical`), Magnetic (`magnetic`), Structural (`structural`), and Other (`other`). Add contributed categories to the visible list using their slug as a fallback label.
- [ ] **Step 4: Render a property tablist and compact result table.** Show label, method, value, unit, readable status, and evidence links. Render scalar values directly and arrays/objects as escaped JSON. Empty categories show “No results reported” and a link to `CONTRIBUTING.md`.
- [ ] **Step 5: Wire category buttons** so selecting one updates `aria-selected` and only the property section, leaving material details and band figures intact.
- [ ] **Step 6: Run `node --test tests/test_properties_ui.mjs`** and require all property rendering tests to pass.

## Task 4: Documentation and Full Verification

**Files:** `references/database.md`, `CONTRIBUTING.md`, `README.md`, `database/index.html`, generated `database/data.json`

- [ ] **Step 1: Document a complete property example** with all required fields, status meanings, evidence-path requirements, and instructions for adding a new category without changing the UI code.
- [ ] **Step 2: Document local preview over HTTP** and explain that opening the HTML through `file://` does not load the JSON catalog.
- [ ] **Step 3: Add the Node tests to CI** using `node --test tests/test_search.mjs tests/test_properties_ui.mjs`.
- [ ] **Step 4: Run full verification:**

```bash
node --check database/app.js
node --test tests/test_search.mjs tests/test_properties_ui.mjs
python3 -m unittest discover -s tests -v
python3 scripts/library.py --check-catalog
python3 scripts/build_indexes.py --check
python3 scripts/public_scan.py .
git diff --check
```

- [ ] **Step 5: Verify migration fidelity** by comparing all 33 source records with `database/data.json`, confirming 33 records have evidence-linked electronic gap properties and no RPA/topology value was invented.
- [ ] **Step 6: Serve the catalog over HTTP**, verify a material query, a multi-token query, a basis query, an electronic property, and an empty topology panel. Capture a desktop and narrow viewport screenshot if the browser runtime can reach the local server.
- [ ] **Step 7: Review the full diff and commit only intended files** with the repository's required commit attribution. Preserve unrelated untracked user files.
