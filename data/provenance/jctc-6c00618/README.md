# FHI-aims and LibRPA band-structure data

This directory contains the collected input and output files for 24 materials.
Each material folder contains an FHI-aims calculation (`aims/`) and LibRPA
calculations using 16- and 32-point frequency grids (`librpa-16/` and
`librpa-32/`).

The main files are:

- `geometry.in` and `control.in`: FHI-aims input files.
- `aims.out` and `GW_band10*.out`: FHI-aims GW output on the regular k-grid and
  band path.
- `librpa.in`: LibRPA input file.
- `LibRPA.out` and `GW_band_spin_1.dat`: LibRPA GW output on the regular k-grid
  and band path.
- `EXX_band_spin_1.dat` (and, where present, `KS_band_spin_1.dat`): additional
  LibRPA band data.

A few notes:

- For GaAs, the QP solver had convergence issue for the CBM at the Gamma point in Pade-16; you may notice this artifact in the band structure. This solved by increasing the number of Pade poles to 32 as in shown `aims-32ac/`.
- LibRPA results were computed using version 0.4.0, which has some bugs in the QPE solver, resulting `NaN` in the band structure output.
- LibRPA adopts Fourier interpolation scheme to compute band structures.

## Dataset generation

Each material's `dataset/` contains the original FHI-aims `control.in`,
`geometry.in`, and `aims.out` used to generate the LibRPA input dataset.
The sources are under `benchmark/bandstructure/` in the original project;
`BN` corresponds to `cBN` there. `dataset_sources.tsv` records the source
path, associated LibRPA frequency grid, and SHA-256 checksum of every copied file.
Source calculations were identified by exact matches to the archived
`librpa-16/LibRPA.out` and `librpa-32/LibRPA.out` and their original input paths.

For AlP, BN, BP, C, GaN, GaP, MgO, NaCl, Si, and SiC, the two LibRPA results
trace to different dataset-generation runs. Their input files are identical,
but the 16-point results trace to FHI-aims 241121 and the 32-point results to
FHI-aims 250507. Both records are retained in `dataset/for_librpa-16/` and
`dataset/for_librpa-32/`. These labels identify the associated LibRPA result,
not the frequency setting of the dataset-generation run. For the other 14
materials, one run supplies both results and its three files are directly
under `dataset/`.

All 34 collected outputs show SCF convergence and normal termination, and
their echoed active inputs match the copied input files. The `df_only` runs
and the generated matrix/data files are not included. Existing LibRPA input
paths are preserved as historical records.

## Plotting

The plotting script requires Python 3, NumPy, Matplotlib, and
[`mushroom`](https://github.com/minyez/mushroom). From this directory, run:

```bash
python3 plot_bandstructures.py
```

This compares FHI-aims with the 32-point LibRPA results, aligns each result to
its valence-band maximum, and writes `bandstructure.pdf` inside every material
folder. Only bands whose complete dispersion lies between VBM - 15 eV and
VBM + 40 eV are plotted. To plot selected materials or use the 16-point LibRPA
data:

```bash
python3 plot_bandstructures.py Si MgO
python3 plot_bandstructures.py --frequency 16
```

Use `python3 plot_bandstructures.py --help` for energy-window, reference-energy,
and output-name options.
