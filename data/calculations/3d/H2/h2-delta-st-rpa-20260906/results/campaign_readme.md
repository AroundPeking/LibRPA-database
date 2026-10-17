# Isolated molecular Delta-ST, 2026-09-06/07

## Definition

New molecular INPUT explicitly selects `sternheimer_molecular_coulomb isolated_ri`
and `sternheimer_ao_potential_file`. The global default stays `none`. SOS and
periodic solids retain their existing algorithms. The serial producer uses
`symmetry -1`, single Gamma, and free-space Center2 `exx_singularity_correction limits`.
Complete producer V and Cs generate the analytic AO tensor. The same AO vertices
enter the right source and conjugated left projection; grid Q-space is solved
again with the isolated potential. Exterior coefficients come from Simpson
moments of the actual finalized auxiliary charge, not from a potential endpoint.

The response residual certifies the mixed AO/grid equations. It is not proof
of continuum, box, NAO, RI or frequency convergence. The kernel remains 1/r.
On-site preorthogonalization is 1e-2, the primary global hard cutoff is 1e-4;
the same on-site unit-Coulomb congruence is applied to V and B. Archive 1e-5,
1e-6 and zero without redefining production to fit a reference.

## Compact comparison

All energies below are dissociation contributions in kcal/mol. Empty entries
mean the new complete molecular/fragment chain is not yet accepted. N atom
3267833 timed out on 2026-09-08; see the terminal audit below. Do not mix the
H2 effective 4s3p atomic reference with LiH's true 4s3p2d reference.

| system | R_A | ABACUS_Dtotal_kcal_mol | FHIaims_Dtotal_kcal_mol | ABACUS_Dc_kcal_mol | FHIaims_Dc_kcal_mol |
|---|---:|---:|---:|---:|---:|
| H2 | 0.7414 | 107.89952437928254 | 108.735029918 | 24.32400441305625 | 24.611166301 |
| N2 | 1.098393194601 | | 223.295810886 | | 112.322325879 |
| Li2 | 2.70 | 15.645514215810296 | 18.959810525 | 16.9067895549143 | 15.640686191 |
| LiH | 1.60 | 52.058781854340275 | 54.854728619 | 21.296447091006314 | 21.092381825 |

H2 differs from FHI-aims by -0.83550553871746 in Dtotal and -0.28716188794375
in Dc. These are not comparisons of pseudopotential and all-electron absolute
total energies. F is excluded; no new F calculations or deletions were made.
CO still lacks a complete accepted molecule/fragment response chain and is not
filled from its band comparison.

## Immutable calculations

Pushed normally to `origin/master_ghj` and verified by the remote ref:
`1dc96f149927915ce15ac30e9633d89c4c0ed73f`.
Author: Codex <codex@openai.com>; committer: AroundPeking <gonghuanjing@iphy.ac.cn>.
The committed method, exporter, tests and input documentation are in ABACUS.
Native source files in the final build archive were byte-compared against the
committed working tree (2340 files); documentation was supplemented after the
archive was built. No ABACUS/LibRPA native compilation was performed locally.

Build 3267624: COMPLETED/0:0, p1, one node/40 CPUs/190000M, 3:16; full abacus_3p
and seven focused CTests passed. Base commit fee8bbff0b7e0962d6ac350b2ca4bd2c18eda7a5.
Source archive SHA256 71bbc68d889069e677ea2ab01fb9c29e2e2dab0f092582916f0e89ae134138b2.
Binary SHA256 b32e9459ddc65dae9274bf6368292bb039a7553a80893b2aba7b1e4df83058f0.
The full test suite was not passed: upstream's separate ABFS perturbation test
references an absent stream-transform API. It was not edited; build 3267597
records that pre-existing failure, and the seven-target build excludes it.

Completed admission responses, all COMPLETED/0:0 with no real failure markers:
- H2 3267688: 32 frequencies, 164 auxiliaries, 5248 equations, residual 9.966697326824225e-7.
- H 3267690: 32 frequencies, 82 auxiliaries, 2624 equations, residual 9.983251640628531e-7.
- Li2 3267692: one frequency, 556 auxiliaries, 1668 equations, residual 9.990070304761807e-7.
- GTH-N2 3267694: one frequency, 532 auxiliaries, 2660 equations; see response summary for residual.

Compared with the immutable endpoint-tail controls, maximum B relative
Frobenius differences are H2 1.64644e-12, H 6.76355e-12, Li2 3.10685e-9,
N2 2.04663e-9. All energy changes are below 1e-7 Ha at all four cutoffs.
These comparisons use identical on-site scaling on both old and new V/B.
The tiny difference between earlier published decimals and these values also
includes making this near-unit diagonal normalization explicit.

New complete responses, submitted once after terminal pilot, metadata/hash,
active-job/output checks and scheduler test-only validation:
- N2/N 3267832/3267833: 12 frequencies, 31920/15960 equations.
- Li2/Li 3267834/3267835: 32 frequencies, 53376/26688 equations.
- LiH/H(4s3p2d) 3267836/3267837: 32 frequencies, 31680/6944 equations.
All use p1, molecular/atomic 36/12 nodes, one MPI rank/node x40 OMP,
190000M/node, 24h, FD8, full LCAO bands, spectral preconditioner with zero
regularization, requested channel width 2. Existing formal jobs are not changed.

H(4s3p2d) job 3267837 has completed: COMPLETED/0:0, 27:57, latest equation
2026-09-07 00:46:48 +0800, all 6944 equations converged, 32 matrices and no
real failure markers. Ec=-0.020650262552464355 Ha and
E_RPA=-0.519378033555644 Ha are identical at all four archived cutoffs.
The accepted response summary and login-node analysis are collected under
`results/response_full/job3267837/` and `results/analysis/h_lmax2_full.json`.
This atomic result alone does not fill the new LiH dissociation row.

### Completed full responses, checked 2026-09-07 08:46 +0800

N2 3267832, Li2 3267834, Li 3267835 and LiH 3267836 are all
COMPLETED/0:0; their complete summaries, basis identity and response matrices
passed the login-node analyzer. Solved counts are 31920/53376/26688/31680,
with 12/32/32/32 matrices and maximum residuals
9.999098197539678e-7 / 9.995552818960175e-7 /
9.998936091885109e-7 / 9.999816560230443e-7. Latest equation timestamps
are 02:23:30 / 02:19:48 / 01:14:19 / 01:33:05 +0800, respectively.
All report all_converged=yes and no real NaN/OOM/fatal/unconverged markers.
Resources remain p1, molecular/atomic 36/12 nodes, one rank/node x40 OMP,
190000M/node. N atom 3267833 remains RUNNING/0:0, 14850/15960 equations,
latest equation 08:35:54 +0800, no real failure markers. Its unfinished
new response is not replaced with an older atomic response to fill N2.

Primary full Ec (Ha): N2 -0.643663198444797, Li2 -0.2496572826148928,
Li -0.11135729923714786, LiH -0.16594561049047504.
Li2 and LiH above use the same accepted Li atom response 3267835.
Relative to FHI-aims, Li2 Dtotal/Dc differences are
-3.3142963092/+1.2661033639 kcal/mol; LiH differences are
-2.7959467647/+0.2040652660 kcal/mol. Across 1e-4/1e-5/1e-6,
the largest primary-relative binding changes are 0.0055616118 (Li2)
and 0.0125183531 (LiH) kcal/mol. These are not occupied-basis convergence
claims; inherited PBE basis differences remain in the earlier audit.

The repeated Li calculation was an explicit experimental-to-production
regression, not a failure retry or a new PP/NAO training run. The serial
producer 3215260, complete V, AO tensor and frequency grid were reused.
The old endpoint-tail full responses 3249635/3249636 had already completed
before the new full responses were submitted. At identical on-site scaling,
Li atom Ec differs from its endpoint control by only 3.2356062273919406e-13 Ha
(2.0303735620260078e-10 kcal/mol); Li2 primary Ec differs by
6.830647159006276e-14 Ha. This verifies the promotion without invalidating
the prior corrected values. Subsequent identical production calculations
must reuse the accepted atomic response rather than repeat it for each
molecule. Historical response files are preserved.

Serial producers: H2/H/N2/N 3257190; Li2/Li 3215260; LiH/H(4s3p2d) 3267700.
The last producer preserves the old PP/NAO/ABFS/band/occupation definitions:
band deviations are below 7e-10 eV, occupations exactly unchanged, basis metadata
byte-identical. Producer V, basis, AO and frequency hashes are pinned per case
in `case_contract.sh`; additional identities are in the exporter JSON manifests.
The new exporter passed 17 Python tests and reproduced the old Li2 tensor to
relative Frobenius 3.12619e-15 (max absolute 3.55271e-15 Ha).

## Review guards

### N atom terminal audit, 2026-09-08

N atom 3267833 ended TIMEOUT/0:0 at 2026-09-08 00:19:19 +0800,
elapsed 24:00:24, p1, 12 nodes/480 CPUs, one MPI rank/node x40 OMP,
190000M/node. ExitCode 0:0 does not override the TIMEOUT state.
The last equation was written at 00:04:35 +0800. Only 15647/15960 equations
were recorded; no final RESULT_SUMMARY or complete reader-v1 response matrix
exists. This point cannot be recovered as a complete energy from progress logs.

Eleven ranks completed their 1330 equations each by 2026-09-07 03:37:54.
Rank 10 alone recorded only 1017/1330, leaving 313 missing. Its recorded elapsed
time was 75623.476 seconds versus 1971.810--2022.531 seconds for completed ranks.
All recorded equations converged: the mean iteration count was about 6 on
every rank (maximum 7), and the largest recorded residual was
9.999704433026182e-7. No genuine NaN/OOM/fatal/unconverged-equation marker
was found. Slurm explicitly reports cancellation due to the time limit.
This isolates the observed slowdown to one MPI rank, but does not by itself
identify a faulty node, threading issue, or implementation root cause.

All other seven full responses are COMPLETED/0:0. H2, Li2 and LiH complete
molecule/fragment pairs remain valid under their recorded definitions; N2's
new pair stays blank. No replacement N task was submitted during this check;
the existing job name has no active queued/running task. Diagnose the slow
rank before preparing a bounded replacement. Do not rerun completed pairs.

### N-only retry and paper update, 2026-09-08

After the terminal-state and duplicate checks, N-only retry 3284003 was
submitted once. It started at 10:59:47 +0800 and was RUNNING/0:0 at the
11:10 check, p1, 12 nodes/480 CPUs, one MPI rank/node x40 OMP,
190000M/node, 24 hours. The binary and all physical input fingerprints
are unchanged. The entire previous allocation is excluded as a bounded
precaution, not as proof that every old node or a particular node is faulty.
I_MPI_DEBUG=4 adds rank-mapping telemetry only. Submission fingerprints
and the immutable job ID are in results/n_atom_retry1_submission/.

At 11:10:41 +0800, 2394/15960 equations were present. All recorded equations
converged, maximum relative residual 9.985440663780914e-7; no genuine
NaN/OOM/fatal/unconverged marker was found. The twelve ranks had comparable
progress, unlike the previous terminal run. No final atomic energy is
available yet. Do not submit an equivalent task while this retry exists.

The publication paper now contains the completed charge-moment H2, Li2 and
LiH rows. N2 retains the independently completed endpoint-tail pair until
the new N atom passes; no old/new fragment energies are mixed. The six
analysis JSON files and historical table snapshot are archived under
publication_paper/provenance/molecular_isolated_ri_20260906. The documentation
verifier passed, main.pdf compiled to 22 pages, and the changed table/text
and appendix pages were visually checked. Cutoff stability is not a claim
that the remaining cross-code or basis errors vanish.

### Final input and Gram guards

N retry 3284003 subsequently completed at 2026-09-08 11:39:05 +0800,
COMPLETED/0:0, 39:18. All 15960 equations and 12 matrices passed, with no
real failure markers. Login-node analysis n_atom_retry1_full.json gives
Ec=-0.23265686787790682 Ha at all four thresholds. The complete new N2/N
pair gives Dtotal=218.17358142869833 and Dc=111.91597753140044 kcal/mol;
both differ from the endpoint pair by less than 3e-8 kcal/mol. The compact
CSV and paper now use this complete new pair, not mixed old/new fragments.
No further N calculation is needed for this implementation regression.

Independent review identified silent non-response input acceptance and an
ill-conditioned sampled AO Gram matrix loophole. Native red test 3267914 proves
the old Gram check accepts a nearly dependent basis with unreliable coordinates.
The final guard rejects eigenvalue ratio below 1e-8 without truncating the AO
space or changing the solve for admitted inputs. Reader checks reject an orphan
AO file, missing Delta-ST/output, or missing AO file. Build 3267940 failed only
because macOS AppleDouble metadata entered the archive and was selected as C++
source. It provides no physics evidence. Metadata-free final build 3267969 is
COMPLETED/0:0 (3:14), full executable and all seven focused tests passed.
Final source archive SHA256 5c1981f1fae5c3567a8ba637dead7699c0f8526db7d6dc92fef476093520a950.
Final binary SHA256 e06c37bfd706bb4a835c826679eda6b5674455c6add75a646641943332ce15b7.
The six active full responses keep the original b32e... binary; no running
artifact or input was replaced. Guard-only H2 pilot 3268100 uses the final
binary after the earlier H2 full response reached its terminal state.
This final-artifact pilot is COMPLETED/0:0, p1, 36 nodes/1440 CPUs,
190000M/node, 2:41, ending 2026-09-07 00:38:34 +0800. All 164 equations
converged, one matrix, residual 8.740295253893655e-7, sampled Gram eigenvalue
ratio 0.000387251883103437, no real failure markers. Relative to the matching
frequency of H2 job 3267688, primary Ec changed by -4.750160768202116e-18 Ha;
the largest absolute change across all four cutoffs is 4.195184781161099e-17 Ha.
Thus the new admission guards leave this admitted molecular calculation
unchanged. They do not retroactively certify Gram conditioning in other jobs.

Lightweight postprocessing runs on the login node, not as a Slurm job. Preserve
all historical Ewald/grid-only and endpoint-tail data. Li basis PBE differences
remain in the audit; do not describe this implementation regression as occupied
basis convergence or declare the whole paper complete from a finite result.
