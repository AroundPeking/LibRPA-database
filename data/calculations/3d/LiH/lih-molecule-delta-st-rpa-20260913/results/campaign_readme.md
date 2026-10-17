# Remaining molecular paper grid checks (2026-09-13)

Scope: only the paper's H2, N2, Li2, LiH. No new F/CO chains, no Li2 or Li
recalculation. The user accepts the latest Li2 finite-grid comparison for the
table; its 2.06652 kcal/mol absolute Ec change is still not below 0.5.

New full responses: N2/N at actual 160^3/120^3 (12 unchanged frequencies),
LiH/true-d H at 160^3/144^3 (32 unchanged frequencies). LiH reuses completed
Li 144^3 response 3332455 with the identical Li/H common frequency file.
H2's separate small-basis H must not be replaced by the true-d fragment.

PP, NAO, product auxiliary basis, geometry, box, occupations, complete
free-space Center2 V, isolated_ri AO vertices and charge-moment tails,
onsite preorthogonalization 1e-2, primary hard threshold 1e-4, FD8 and binary
3267624 (b32e9459ddc65dae9274bf6368292bb039a7553a80893b2aba7b1e4df83058f0)
remain unchanged. Archive 1e-5/1e-6/0. Preconditioner fd_spectral with zero
regularization, global_equation, batch2, full bands and residual <=1e-6.

Ground and response meshes change together in this pinned molecular route;
independent dense-ground/coarse-response inputs are not implemented here.
Decompose changes into E0=PBE-XC+RI_EXX and Ec. Evaluate absolute molecular
and atomic Ec changes separately at the user-approved 0.5 kcal/mol criterion;
report Dc and total binding changes separately. Agreement with aims is not
the acceptance criterion and no threshold is tuned to the reference.

Serial producers 3295368 are reused without running SCF. The original N2
g1 requested 157^3 but ABACUS generated 160^3 and completed normally; the
original wrapper rejected the requested-grid contract. Its original files and
scheduler FAILED state remain unchanged. A separate validated_producers/n2_mol
contract explicitly accepts the observed 160^3 mesh, checks SCF, occupations,
all source/input hashes, V/Cs/basis identity, and freshly exports the AO tensor.
This is an actual-grid refinement, not a fixed nuclear fractional-grid-phase
test. All four cases have SOURCE_AUDIT.json and AO_GATE.json; no physical
producer is rerun and no old contract or output is overwritten.

Submission uses a case-specific exclusive ledger and hold-record-release-once.
Compare current CPU partitions before each submission. Use compatible 48-core
partitions at 1 MPI/node x48 OMP, 190000M/node, 36 molecular or 12 atomic
nodes; MKL/BLAS remain single-threaded inside channel OpenMP as in the baseline.
All jobs have UNLIMITED time, not a 24-hour cap. Resource changes do not change
the equation definition; make no speedup claim before observing throughput.
Completion requires exact nfreq*naux*nocc equations: N2 31920, N 15960,
LiH 31680, H 6944; all matrices, residual and finite-spectrum checks, matching
producer basis, complete producer V and the same congruence applied to V/B.

Postprocess on the login node using the existing analyze_response.py and
compute_st_ecrpa.py, not a new Slurm task. Keep molecule/fragment frequency and
energy-grid provenance explicit before updating the six-column paper table.
