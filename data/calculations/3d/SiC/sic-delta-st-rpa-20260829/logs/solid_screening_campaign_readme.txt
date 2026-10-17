# FD8 screening of additional solids on df_dcu

This campaign computes one conservative Delta-ST point for SiC, Ge, and MgO. It is not a parameter-by-parameter convergence scan.

- Lattices: SiC `4.346 Angstrom`, Ge `5.644 Angstrom`, and MgO `4.189 Angstrom`, using the ZPAE-corrected experimental values in Harl, Schimka, and Kresse, PRB 81, 115126 (2010), Table V.

- Solid: FD8, 30 Ry, explicit old 30 Ry grid, 16 GreenX frequencies, PCA `1e-6`, common k/q `4x4x4`, solid rmesh 2, full Coulomb, q=0, q-average head/wing with body start 1.
- Atom: FD8, 20 Angstrom, 30 Ry, 16 frequencies, PCA `1e-6`, integer occupations, atom rmesh 1, no head/wing.
- Runtime lane: 64 MPI ranks, one rank per node, 30 OpenMP threads, `kpar=4` for solids and `global_equation` for atoms.
- Full q arrays are blocked until the slow q=7 pilot has `all_converged=yes` and a conservative 24-hour projection no greater than 18 hours.
- Existing exact FD8 C, Mg, and O atom results are reused. Completed rmesh-2 metrics at the older `4.342/5.640/4.184 Angstrom` lattices are retained only as legacy provenance and must not be reused; the corrected structures require new metrics. For Si and Ge, the converged integer-occupation zero-order states from jobs `21640544` and `21640546` are reused after exact KPT/STRU/PP/orbital identity checks; only the incomplete 16-frequency responses are recomputed with the merged ABACUS executable.
- All results remain labeled `SCREENING_NOT_CONVERGED` until an independent adjacent confirmation point is run.

Pinned binaries:

- ABACUS commit `192a49e0ff78487480ac8ddd2cc83c196ec0f73d`, SHA256 `86b5232b75f8be8a682ca45fefa6cc799719e42757004611cd091eacf11dfa21`.
- LibRPA commit `6e49b04f1190da2b197fe5c63a10d68b3433af67`, SHA256 `65d7718783deadb176f60f789c5080cbf513ac1ee0c447271fc6eafc7b45c4d3`.
