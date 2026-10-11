# 2D materials: published basis bundles

This repository contains the imported 2D payloads under
[`data/elements`](../data/elements) and the result records under
[`data/calculations/2d`](../data/calculations/2d). The material table below is
the historical band-result index. An exact material-to-set binding is shown in
the database only when the source audit proves it; otherwise the record keeps
the result and lists contextual candidate sets separately.

## MoS2/WS2

The published [MoS2/WS2 case](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/tree/main/FIG/Fig_10_MoS2_WS2)
contains producer and band inputs, GTH-PBE pseudopotentials, physical `.orb`
files, exported `.abfs` files, `librpa.in`/`librpa.out`, and final
`KS_band_spin_1.dat`, `EXX_band_spin_1.dat`, and `GW_band_spin_1.dat` files.
Treat the linked `librpa.in` as a reference: its `input_dir` is host-specific,
and this archive does not include the matching LibRPA reader-data directory.
The archived inputs and outputs alone are not a turnkey LibRPA rerun. To
reproduce the calculation, run the matching ABACUS producer to generate reader
data, or obtain the exact matching producer outputs separately, then set
`input_dir` to that reader-data directory. This skill does not copy the
host-specific path.

| Element | Physical NAO | Pseudopotential | Exported ABF |
| --- | --- | --- | --- |
| Mo | `4s2p2d1f` | [GTH-PBE Mo](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/blob/main/FIG/Fig_10_MoS2_WS2/ABACUS_producer_input/assets/Mo-GTH-PBE-q14-cp2k-default-grid.upf) | [foraux, PCA 1e-5, 319 functions](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/blob/main/FIG/Fig_10_MoS2_WS2/ABACUS_producer_input/assets/Mo_GTH-PBE_foraux_1g_pca1e-5_naux319.abfs) |
| S | `2s2p2d1f` | [GTH-PBE S](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/blob/main/FIG/Fig_10_MoS2_WS2/ABACUS_producer_input/assets/S-GTH-PBE-q6-cp2k-default-grid.upf) | [foraux, PCA 1e-5, 328 functions](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/blob/main/FIG/Fig_10_MoS2_WS2/ABACUS_producer_input/assets/S_GTH-PBE_foraux_1g_pca1e-5_naux328.abfs) |
| W | `6s3p3d2f` | [GTH-PBE W](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/blob/main/FIG/Fig_10_MoS2_WS2/ABACUS_producer_input/assets/W-GTH-PBE-q14-cp2k-default-grid.upf) | [foraux, PCA 1e-5, 584 functions](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/blob/main/FIG/Fig_10_MoS2_WS2/ABACUS_producer_input/assets/W_GTH-PBE_foraux_1g_pca1e-5_naux584.abfs) |

The matched physical orbitals are [Mo](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/blob/main/FIG/Fig_10_MoS2_WS2/ABACUS_producer_input/assets/Mo_gga_10au_100Ry_4s2p2d1f.orb), [S](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/blob/main/FIG/Fig_10_MoS2_WS2/ABACUS_producer_input/assets/S_gga_10au_100Ry_2s2p2d1f.orb), and [W](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks/blob/main/FIG/Fig_10_MoS2_WS2/ABACUS_producer_input/assets/W_gga_10au_100Ry_6s3p3d2f.orb). GW outputs are in the case's `LibRPA_GW` folder. The same public files are imported into this repository when their redistribution status permits it; use the local set records and hashes as the canonical lookup. The labels and dimensions identify these published files; they are not defaults for new materials or code versions.

## Imported 2D element sets

The current import includes reusable element directories for Cu, Ga, Ge, In,
Mo, Na, P, S, Se, Sn, Te, Ti, and W. Examples with attached PP/NAO/ABF or
generation evidence include the Mo/S GTH heterostructure sets, the W/Se WSe2
sets, the Ge/Te GeTe pair, the Sn/Se SnSe pair, the MoTe2 stringent candidate,
and atomic-generation sets for Cu, Ga, In, P, S, and Ti. Each set's
`validation_scope` and `notes` state whether it is a producer-used bundle,
PBE-only screen, generation-only candidate, or a failed/pending gate.

The hBN extension record is the one exact 2D calculation-to-set binding in the
current import: `hbn-tzdp10-fgext-20261008` uses
`B-GTH-e07d6fb55c4a` and `N-GTH-f896bb84c70f`. Its PBE raw-5 gap is 4.688128 eV
and its K-to-Gamma conduction ordering fails the same-PP PBE gate, so its GW
path gap is retained as `path_diagnostic`, not as a complete fundamental-gap
acceptance. The other material records keep their band data and figures, and
their candidate sets are explicitly contextual until exact production linkage
is audited.

## Adding another 2D contribution

Add each material to this 2D list only after its source files are online and
downloadable. Record the material and structure source; dimensionality and
vacuum/Coulomb treatment; PP family, version, file hash, and reuse terms; the
matched physical NAO and its generation provenance; the ABF and generation
settings; and links to inputs, logs, and outputs.

State validation stage explicitly: same-PP PBE, physical-NAO overlap and band
window, ABF/Coulomb conditioning, EXX/RPA control, and GW output/convergence.
Mark a stage as passed only when its evidence is linked. Do not describe a PBE
screen, generated file, or near-gap GW run as a fully validated 2D GW basis.
