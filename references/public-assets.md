# Public sources and redistribution

Use the official release or repository for software and the publisher's page for
third-party PP/NAO data. Verify the URL and license at the time of use; links and
branch names can change.

## Software

- [ABACUS](https://github.com/abacusmodeling/abacus-develop) — plane-wave and
  numerical-orbital electronic-structure code.
- [ABACUS documentation](https://abacus.deepmodeling.com/) — current input and
  file-format documentation.
- [ABACUS-orbitals](https://github.com/abacusmodeling/ABACUS-orbitals) — public
  orbital library with generation metadata and DeltaDFT references.
- [ABACUS-orbitals SIAB example](https://github.com/abacusmodeling/ABACUS-orbitals/tree/main/SIAB/example_Si)
  — public input and run-script shape for SIAB; replace site-specific
  environment settings with those of the approved execution system.
- [LibRPA](https://github.com/AESM-Group/LibRPA) — public LibRPA source and
  documentation; pin an immutable commit for a calculation.
- [LibRI](https://github.com/abacusmodeling/LibRI) and
  [LibComm](https://github.com/abacusmodeling/LibComm) — public dependencies
  used by supported LibRPA builds.
- [ABACUS auxiliary-basis generator](https://github.com/AroundPeking/abacus_abf_gen/tree/806cde132cbf98c25809e1a6f51a700ca97ce10c)
  — public source for the explicit ABFS export route documented here; it is
  branch-specific and should be checked for compatibility before use.
- [Published ABACUS + LibRPA GW calculation data](https://github.com/AESM-Group/abacus-librpa-g0w0-nao-pp-benchmarks)
  — paper calculation data with inputs, PP/NAO/ABF assets, main logs, and
  KS/EXX/GW band data where present. Browse the cases in
  [references/tested-public-bundles.md](tested-public-bundles.md). The data
  repository currently has no declared GitHub license, so link to it and check
  its terms before redistributing files elsewhere.

## Pseudopotentials and orbital methods

- [ABACUS PP and orbital portal](https://abacus.ustc.edu.cn/pseudo/list.htm) —
  ABACUS-distributed files; preserve the downloaded file hash.
- [SG15/ONCV distribution](http://www.quantum-simulation.org/potentials/sg15_oncv/)
  — norm-conserving SG15 files and metadata.
- [PseudoDojo](https://www.pseudo-dojo.org/) — PseudoDojo/Dojo-NC data and tests.
- [SSSP](https://www.materialscloud.org/sssp) — a tested pseudopotential
  library for plane-wave controls; use only a format and XC combination that
  the ABACUS route supports.
- [ABACUS PP/NAO documentation](https://github.com/abacusmodeling/abacus-develop/blob/develop/docs/advanced/pp_orb.md)
  — supported formats and orbital-generation background.

Do not redistribute third-party binaries merely because they are downloadable.
Check the license and cite the publisher. If redistribution is not permitted,
put only the public download URL, version, filename, and SHA-256 in the manifest.
