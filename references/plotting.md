# Reference band and radial-orbital plotting

## Original radial orbitals: one chart per angular momentum

The Basis page and `scripts/plot_radial.mjs` share the parser and SVG renderer
in `database/radial.mjs`. They support the original ABACUS block format:
`Element`, `Lmax`, angular-momentum counts, `Mesh`, `dr`, and `Type L N`.
N retains its original zero-based index. NAO, ABF, and for_aux are displayed
separately; auxiliary-generation orbitals are not treated as physical NAOs.

```bash
node scripts/plot_radial.mjs /path/to/physical.orb /new/output/directory
node scripts/plot_radial.mjs /path/to/auxiliary.abfs /new/tail/directory --tail --derivative
```

Each l with data produces one SVG and a JSON audit named using the same SHA
and mode. The audit includes the source SHA-256, declared and actual
angular-momentum counts, original grid, and endpoint and derivative metrics
for every N. Output files are created exclusively; existing files with the
same names are never overwritten. By default, the CLI rejects files whose
header counts disagree with the actual blocks. Only an explicit
`--diagnostic-header` permits an unchanged diagnostic display, with the
anomaly marked in both the figure and audit. The website likewise displays a
prominent warning and retains all original blocks.

- R(r) polylines use every original sample, without smoothing, interpolation,
  reordering, or renormalization.
- dR/dr uses second-order central differences in the interior and second-order
  one-sided differences at the boundaries. It is a numerical diagnostic, not
  an analytic derivative supplied by the original generator. The tail option
  displays the final 20% of the original grid.
- Each original N within the same l can be toggled independently. Visible
  channels determine the y-axis range. Natural nodes or oscillations are not
  automatically classified as defects, and endpoint metrics have no arbitrary
  pass threshold.
- Rendering follows source SHA verification. An anomalous header does not
  change the original bytes or scientific acceptance status.
- Radial smoothness does not replace periodic physical-overlap tests, local RI
  conditioning, Coulomb/EXX/GW accuracy checks, or convergence acceptance.

## Reference band plotting

`scripts/plot_bands.py` defines the database plotting input: one data row per
k-path point, with the first column as the cumulative path coordinate and every
remaining column as one band. The order of the energy columns is preserved.
Blank lines and lines beginning with `#` are ignored.

```text
# x  band_1  band_2  band_3
0.0  -2.1     1.4     3.8
0.5  -1.9     1.2     3.7
1.0  -2.0     1.3     3.9
```

Optional high-symmetry labels use JSON:

```json
{"ticks": [{"x": 0.0, "label": "Γ"}, {"x": 1.0, "label": "M"}]}
```

The command writes the figure and a same-stem JSON sidecar containing the
calculation ID, input/table SHA-256 values, and labels. Matplotlib is optional
for static validation; the parser and sidecar writer use only the Python
standard library.

```bash
python3 scripts/plot_bands.py bands.dat \
  --output figures/si-gw.png \
  --calculation-id si-paper-all_kpath \
  --input-sha256 <sha256-of-the-input-bundle> \
  --labels kpath.json
```

## Native ABACUS frontier figures and scientific boundaries

The generic table interface preserves the original column order and does not
infer occupations. Archive generation uses tables in the form
`index kx ky kz occupation_1 energy_1 ...`, retaining the native k indices,
fractional coordinates, occupations, and source SHA-256 values in full.

```bash
python3 -B scripts/generate_band_figures.py --audit --allow-weighted-occupations
python3 -B scripts/generate_band_figures.py --write --allow-weighted-occupations
python3 -B -m unittest discover -s tests -p 'test*band*.py'
```

The default mode and `--audit` are read-only; only `--write` writes files.
Ordinary generation is restricted to 3D and does not modify 2D records.
The replacement hBN paper record has a separate entry point, which must not
be applied to other two-dimensional records:

```bash
python3 -B scripts/generate_band_figures.py --replacement-hbn
python3 -B scripts/generate_band_figures.py --replacement-hbn --write
```

This entry point requires a same-record PBE receipt, full and consistent
source commits for SCF and NSCF, 91 points/44 bands/4 occupied bands, and
single-spin `2/nk` occupations. It checks the original KPT point by point.
Raw occupied bands 1–4 and empty bands 5–8 are frozen before display. Each of
the three methods uses its own alignment and viewport; the complete finite
extent of those same frozen bands is shown without selecting additional
bands. All 44 bands, non-finite locations, and intrusions remain in
`hbn_frontier_audit.json`. The KS/EXX path values are 4.68813/11.01971 eV.
The paper GW primary value of 6.94183 eV remains a restricted-path diagnostic,
not a full-spectrum fundamental gap. Original inputs, spectra, and logs are
unchanged.

The fact that the runtime log did not print the LibRPA commit is retained
separately from the source identity subsequently recovered through the
hash-bound `librpa_build_identity_receipt.json`. Recovering that identity does
not establish a clean source tree, compatibility with the current version,
or scientific acceptance.

The new `ks_frontier.svg`, `exx_frontier.svg`, `gw_frontier.svg`, and
`band_frontier_metadata.json` are registered as primary. The original
`band_comparison.svg/json` become secondary, but their bytes and all original
spectral bytes remain unchanged. Repeated generation must be byte-idempotent.

### Occupations, exported dimensions, and paths

- Physical integer occupations must form a fixed occupied prefix and empty
  suffix. `--allow-weighted-occupations` accepts only a uniform weighted
  contract with same-record logged occupation-count evidence, complete path
  verification, and explicit five-decimal `2/nk` values. Arbitrary fractional
  occupations are not treated as integers.
- Finite, all-zero exported occupations do not mean that every state is empty.
  A unique, consistent `Bands of occupation` entry in the same archived
  `librpa.out` may establish an explicit raw occupied/empty boundary. The
  boundary is never guessed from a chemical formula, sorting, GW gap, or visual
  shape. Original zeros and log hashes are retained. An ambiguous boundary is
  rejected. Non-finite occupations permit only an explicitly restricted
  low-energy diagnostic, not an ordinary gap report.
- The first line of `band_kpath_info` means **nbasis, nbands, nspins, nkpts**;
  nbasis is not the number of exported states. This schema was cross-checked
  against independently read LibRPA `driver/read_data.cpp:2078–2089`, the
  `band_kpath_info` section of `docs/develop/dataset_format.md`, and the output
  order in `preprocess_abacus_for_librpa_band.py:103–157`. These newer sources
  establish the format only; **they do not identify the historical AlP
  producer commit**.
- The actual same-record archived `KPT_nscf`, `KPT`, and other `KPT*` files are
  candidates. A Line path is used only after verifying fractional coordinates
  point by point, every sampling count, and `band_kpath_info`. Failed
  candidates and the selected path are retained; endpoints are never spaced
  uniformly across the horizontal axis. The current x coordinate is the
  native k-point index, with no reciprocal-space metric. It must not be called
  Å⁻¹ or cumulative reciprocal-space distance.

### Freeze first, sort second, then render

The full unsorted spectrum is audited first, including every non-finite
location, each raw band's range, negative gaps, unselected-state intrusions,
the declared export window, and rejected tail bands. Selection is frozen
before sorting or rendering:

- For 3D records, retain the nearest 3 occupied and 4 empty raw bands on either
  side of the occupation boundary, or the available number if fewer exist.
- For the new hBN record, retain its original 4 occupied and 4 empty raw bands.
- For the other 15 2D records, retain the exact frozen raw indices and mappings
  from each original sidecar. Do not replace these selections with a common
  3/4 rule or choose new bands from the expanded viewport.

For the 3D and replacement-hBN generation protocols, energies are sorted
independently within the occupied and empty manifolds at each k, connecting
equal energy ranks. Sorting never crosses the occupation boundary or expands
the frozen selection. Curves are not smoothed, and equal-rank connection is
not wavefunction-character tracking. The complete one-based raw mapping
verifies energy reconstruction and preservation of the energy multiset.
The existing mappings for the other 2D records remain unchanged. Ordinary
neighboring-band intrusion is reported without rejecting a gap from a
credible export window. Pathological high empty states that fall into the
low-energy region must not be sorted into the frozen window to hide a defect.

Each method retains its own original occupied sampled-path VBM or documented
reference energy. The shared renderer changes **only the viewport**, showing
the full finite extent of all already selected bands, not additional bands or
the full unselected spectrum. For aligned selected finite energies, compute
`selected_min` and `selected_max` across all selected bands and k points, with
`padding = max(0.5, 0.05 * (selected_max - selected_min))` eV. Expand the old
limits using:

```text
lower = min(old_lower, selected_min - padding)
upper = max(old_upper, selected_max + padding)
```

The old viewport must not shrink. This supersedes the former near-gap
clipping formula:
`lower=-max(2.5,0.5*selectedgap)` and
`upper=selectedgap+max(3,0.5*selectedgap)`.
The previous limits are retained in the sidecar as
`previous_near_gap_limits_ev`. Existing clipping evidence remains historical
provenance; the expanded viewport does not alter frozen energies, raw indices,
mappings, source hashes, the full-table audit, or path-gap definitions.
Non-finite selected samples remain disclosed rather than repaired.

The original 5/6-window admission audit must remain intact. Reducing the
number of displayed bands or expanding the viewport cannot remove a
pathological rejection. The original GaAs/GaP GW admission windows have
gap<=0; excluding the intruding states from the newer 3/4 display selection
does not repair this. Their new figures remain rejected, with the new SVG
references removed from the records. Old files are not deleted; sidecars
retain the full spectra, mappings, and rejection reasons, and original GW
summaries remain unchanged. The current valid declarations comprise 49 new
single-method SVGs and 17 audit sidecars; two unreferenced old derived SVGs
are not counted as delivered figures.

Figures use a white background, black axes, and large serif labels: cyan
dashed KS, black dash-dot EXX, and vermilion solid GW. Hollow VBM/CBM markers
come from unsorted raw extrema; their raw band/k indices and tied points are
retained in the sidecar. For VBM-aligned figures, the vertical axis is
E − E_VBM, **not the Fermi level**.

### Recoverable properties are not full-spectrum numerical acceptance

Only missing KS/PBE and EXX `band_gap` properties are added. Their fixed
definition is **declared finite export window path gap**: raw CBM(empty) −
VBM(occupied) across all declared valid, finite nbands on the actual sampled
path. This is not a global BZ gap, convergence validation, PP/NAO
recommendation, or historical source-identity certification. Existing
failed/validated/reported properties are never overwritten; GW properties,
summaries, and record statuses are not upgraded.

AlP's `56 44 1 121` declares only raw bands 1–44 as valid. Original bands
45–56 are retained in full but rejected. The complete tail audit must disclose
that, in the first 120 KS rows, the final 12 entries equal the next k point's
first 12 entries; the EXX tail contains 6 NaNs and anomalous values below
−874 eV; and the GW tail contains 121×12 zeros. Figures must disclose tail
rejection. Finite declared-window KS/EXX path values remain reportable.
GW figures for CaO/NaCl and other negative-full-spectrum-gap cases are only
fixed low-energy-window diagnostics. Do not expand the selected state set
using the minimum of all empty states, replace the original GW summary, or
raise acceptance status. The viewport may expand to display the existing
frozen selection in full; this does not expand the scientific selection.
Non-finite raw occupations are encoded as JSON null, with their original raw
values and k/band/source-column locations stored separately. JSON uses strict
`allow_nan=False`; original source bytes remain unchanged.

Five independently checked raw-extrema KS/EXX path values (eV) are
AlP 1.60680/7.39451 (nocc=8), BAs 1.18591/6.49227 (4),
BP 1.28967/7.13040 (4), CaO 3.55481/14.26462 (8), and
NaCl 5.08771/13.36155 (8). None is a global BZ gap.

## Evidence recovery from original 2D tables and existing figures

`scripts/migrate_properties.py --recover-table-evidence` recovers only
PBE/EXX sampled-path properties already present in the original tables and
`source_paths` for existing PNG/PDF figures. It does not run physical
calculations or regenerate basis sets or band figures. The default is audit
only; writing requires all sources to pass and an explicit option:

```bash
python3 -B scripts/migrate_properties.py --recover-table-evidence \
  --source-root /path/to/paper_materials
python3 -B scripts/migrate_properties.py --recover-table-evidence \
  --source-root /path/to/paper_materials --write
```

The original `table_band_source.json` SHA must match the original sidecar SHA
retained in the record. The archived table, current sidecar, and original
table source are checked separately for hashes, dimensions, native k indices
and fractional coordinates, fixed occupied/empty boundaries, and frozen-window
path values. Ordinary source DAT files must match byte for byte.

For GeTe/SnSe KS, the original source is NPZ and the archived table is an
existing transformed DAT; they are not the same byte asset. Archive identity
is checked using the original sidecar's `archive_path` and the DAT's full
SHA. The actual original NPZ SHA and transformed-table SHA are retained
separately, without claiming that NPZ→DAT was independently repeated or
validated. These properties are explicitly limited to sampled-path gaps of
the archived transformed tables.

Existing manually recorded gaps are not overwritten, and method aliases do
not create ambiguous duplicates. A recovered path value that conflicts with
the verified original table is rejected on write. Anomalies in the full
original table cannot be repaired through a smaller frozen selection or a
larger viewport. GeTe/SnSe EXX full-raw and frozen-window negative values are
stored separately in the `method_diagnostics` list. No ordinary positive gap
is fabricated; the original diagnostic figures remain downloadable and
explicitly labelled.

Further independent recomputation found that both EXX original-sidecar path
values also differ from their frozen raw windows: GeTe's original sidecar is
−70.88803 eV and the recomputed frozen window is −153.68881 eV; SnSe's original
sidecar is −553.74944 eV and the recomputed frozen window is −1108.09860 eV.
Original sidecar values are not overwritten. Diagnostics retain the
recomputed full-raw, recomputed frozen-window, and original-sidecar values,
together with a conflict flag. None of these anomalous values is presented
as an accepted gap. Associations are added only after byte-for-byte checks
of the original figures against their specified sources. Original figures
and spectra, software identities, summaries, scientific statuses, and set
release statuses remain unchanged.

## Paper-reported values and archived path values

Values explicitly reported in the papers use a separate `paper_values`
layer; original spectra and path properties are not rewritten. For 3D, use
the ABACUS PBE / ABACUS+LibRPA G0W0@PBE columns in Table IV (PDF page 16).
For 2D, use this work's PBE / G0W0 columns in Table I (PDF page 12), retaining
diagnostic scope and the distinction between the old and new hBN bases.
Neither paper's main table supplies an EXX column. Archived EXX values must
not be labelled as paper primary values.

```bash
python3 -B scripts/migrate_properties.py --import-paper-values /path/to/paper-values-audit.json
python3 -B scripts/migrate_properties.py --import-paper-values /path/to/paper-values-audit.json --write
```

The importer verifies the actual SHA of both PDFs, unique mappings for all
32 rows, finite values, and reported precision. Same-record excerpts are
added only after the complete audit. The default is read-only, repeated
writes are idempotent, and conflicting existing excerpts or manually recorded
metadata are never overwritten. This primary-value layer does not prove
original production spectra or exact input binding. Band figures still use
the archived spectra and their original frozen selections. Their expanded
viewports show those selections in full without changing the data. When
figure-derived and paper values differ, the Overview displays them in
separate columns; figures are not modified to simulate agreement.
