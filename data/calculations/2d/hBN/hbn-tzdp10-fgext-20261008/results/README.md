# h-BN 10-au f/g-extended GW frontier diagnostic

This case supplies the replacement h-BN row in the manuscript's PBE/GW gap
and GW effective-mass table. The previous manuscript snapshot remains in
`../2d_gw_prb_manuscript_archive_20261009`; this directory holds the new
calculation, its archived inputs and outputs, and the mass extraction.

## Result and status

- PBE raw-band-5 path gap: `4.688128 eV`, K-to-K.
- PBE valley ordering: `Ec(K)-Ec(Gamma) = -0.260216 eV`; this fails the
  same-pseudopotential plane-wave reference gate.
- GW raw-band-5 frontier path gap: `6.941830 eV`, with the VBM at K and the
  raw-band-5 CBM at Gamma. The reported Gamma and K direct gaps are `8.83292`
  and `7.41978 eV`.
- PBE effective-mass directional means: electron `0.885974 m0`, hole
  `0.623421 m0`.
- GW effective-mass directional means: electron `0.863241 m0`, hole
  `0.555319 m0`. These GW values are the manuscript table entries.
- Raw states 1--8 are finite, but higher-state intrusions below raw band 5
  remain in the spectrum audit. Therefore `6.941830 eV` is a frontier/path
  diagnostic, not a validated complete-spectrum fundamental gap.
- The Coulomb route is `direct_mixed_fourier`; the case is diagnostic and is
  not presented as a final strict-2D Ewald result.

## Inputs and method

- B and N use GTH-PBE q3/q5 pseudopotentials and the original 10-au
  `3s3p2d` numerical orbitals. There are no empty atoms; the wave-function
  basis has 44 functions.
- Only the auxiliary basis is extended: one smooth diffuse f and one g
  primitive are appended for each species, with PCA threshold `1e-4`. The
  raw/active auxiliary dimensions are `510/232`.
- The path has 91 points on Gamma--M--K--Gamma. The response mesh is
  `12x12x1`, with 19 response q points.
- The original ABACUS and LibRPA inputs, basis files, pseudopotentials,
  scheduler scripts, PBE path, PyATB response payload, run logs, final bands,
  self-energy output, and producer/GW handoff records are retained under
  `calculation/`. The original input manifests retain checksums and source
  paths for the complete producer/GW handoff.
- The large generated LibRPA reader payloads (`v1_Cs_data_0`,
  `v1_Cs_shrinked_data_0`, `v1_shrink_sinvS_0`, and per-q Coulomb matrices)
  are not duplicated into the local archive. Their hashes and original paths
  remain in `calculation/INPUT_MANIFEST.sha256` and
  `calculation/gw_k12_fgext_20261008/GW_INPUT_MANIFEST.sha256`. This is a
  provenance-complete record of the run's definitions and results, but not a
  fully self-contained offline rerun package for LibRPA; the generated
  producer payload must be restored from the recorded remote producer if a
  rerun is needed.
- `figures/` contains the VBM-aligned GW band plot and the physical-orbital,
  f/g auxiliary-channel, and cutoff-continuity figures associated with this
  case.
- `derived/effective_mass_config.json` records the path points, lattice,
  frontier raw bands, and fit windows. The analysis script fits
  `Delta E = a q^2 + b q^3` to the three nearest nonzero points on each side
  and evaluates `m*/m0 = 3.80998211615486/a`.
- The electron fit is centered at K for PBE and Gamma for GW. The hole fit is
  centered at K for both. Directional masses and the raw-band hashes are in
  `derived/effective_mass_results.csv` and
  `derived/effective_mass_results.json`.

## Recompute and verify

From this directory, run:

```sh
[private-path] derived/analyze_effective_masses.py
```

The script reads only the archived raw PBE/GW band files and rewrites the
derived JSON/CSV. The original run audit files are kept unchanged under
`calculation/`.
