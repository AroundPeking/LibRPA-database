# In Dojo-stringent TZDP generation plan, retry 1

The first candidate job `3348753` is retained as a failed provenance record:
its staged PP was truncated during download and failed XML parsing in ABACUS.
This retry uses the complete upstream PP with SHA256
`de14d1ba51dba2ff7db0ef8c933749ad0520b4318996e1f3880710c54aa41fc6`.

This is a single missing-element generation candidate for the In2Se3/InSe
application intake. Se is reused from the completed Dojo-stringent q24 asset
under `missing_se_stringent_20260906`; no Se generation is repeated.

- PP source: AroundPeking/ABACUS-orbitals `Dojo-NC-SR/Pseudopotential/In.upf`
- upstream repository snapshot: `ABACUS-orbitals` main, commit `3b634f1618f5c56baa97084a41ae17e801d46ab9`
- scalar PBE, 10 bohr radial cutoff, 150 Ry training cutoff
- physical channels: `3s3p3d2f`
- training geometry and Level1/2/3 definitions are retained from the upstream
  In_TZDP recipe; only the training cutoff and remote project paths are adapted
- this is a generation candidate only; radial completion does not imply PBE,
  head, RI, EXX, or GW acceptance
- scheduler shape: one 48-core node, 20 MPI tasks, one thread per task, normal
  QoS, with the live-compatible 48-core partition selected immediately before
  submission
- the 20-rank shape follows the already completed Se SIAB generation contract;
  SIAB launches the small PW references explicitly with 20 MPI ranks, so this
  is not a one-rank-per-node ABACUS or LibRPA production layout
