#!/bin/bash
#SBATCH --job-name=paper_mol_grid
#SBATCH --partition=48cp2
#SBATCH --nodes=36
#SBATCH --ntasks=36
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=190000M
#SBATCH --time=0
#SBATCH --exclude=c20006,c20038,c20065,c20083,c20308,c20454,c20580,c20722
#SBATCH --output=/HPC/sternheimer_tests/paper_molecular_grid_20260913/logs/%x-%j.out

set -euo pipefail
trap 'rc=$?; echo "HN_ANALYTIC_AO_FAILED line=$LINENO command=$BASH_COMMAND rc=$rc" >&2; exit $rc' ERR
module purge
module load cmake/3.31.7
module load oneapi/2024.2

root=/HPC/sternheimer_tests/paper_molecular_grid_20260913
source "$root/case_contract.sh" "${CASE_ID:?case id required}"
mode=${MODE:?pilot or full required}
case "$mode" in
  pilot) nfreq=1 ;;
  full) ;;
  *) exit 2 ;;
esac
expected_sha=$expected_abacus_sha
expected_equations=$((nfreq * naux * nocc_total))
case_dir=$root/response_$mode/job$SLURM_JOBID/$case_id

case "$SLURM_JOB_PARTITION" in 48cp1|48cp2|48cp3) ;; *) exit 2 ;; esac
test "$SLURM_NNODES" -eq "$expected_nodes"
test "$SLURM_NTASKS" -eq "$expected_nodes"
test "$SLURM_CPUS_PER_TASK" -eq 48
test -x "$abacus"
test "$(sha256sum "$abacus" | awk '{print $1}')" = "$expected_sha"
grep -Fxq status=success "$artifact/provenance.txt"
grep -Fxq feature=analytic_ao_rhs_and_left_projection "$artifact/provenance.txt"
grep -Fxq feature=isolated_charge_multipole_tail "$artifact/provenance.txt"
grep -Fxq status=success "$producer/RESULT_SUMMARY.txt"
grep -Fxq "naux=$naux" "$producer/RESULT_SUMMARY.txt"
/usr/bin/python3 - "$producer" <<'PY'
import hashlib
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
for line in (root / 'INPUT').read_text().splitlines():
    fields = line.split()
    if fields and fields[0] in ('exx_rotate_abfs', 'exx_coul_moment'):
        if len(fields) < 2 or fields[1].lower() not in ('0', 'false'):
            raise SystemExit('unapproved rotated/moment basis')
for line in (root / 'RESULT_SUMMARY.txt').read_text().splitlines():
    fields = line.split()
    if len(fields) == 2 and len(fields[0]) == 64:
        path = root / fields[1]
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != fields[0]:
            raise SystemExit('producer hash mismatch: ' + str(path))
PY
grep -Fxq coulomb_method=center2_limits_free_space "$producer/RESULT_SUMMARY.txt"
test "$(sha256sum "$producer/v1_coulomb_full_iq_1_rank0.dat" | awk '{print $1}')" = \
  "$v_sha"
test "$(sha256sum "$producer/basis_aux_out" | awk '{print $1}')" = \
  "$basis_sha"
test "$(sha256sum "$ao_potentials" | awk '{print $1}')" = \
  "$ao_sha"
test ! -e "$case_dir"
mkdir -p "$case_dir/reference"
cp "$producer/INPUT" "$producer/KPT" "$producer/STRU" "$producer"/*.orb "$producer"/*.upf "$case_dir/"
for abfs in "$producer"/*.abfs; do
    if [[ -f "$abfs" ]]; then cp "$abfs" "$case_dir/"; fi
done
cp "$producer/basis_aux_out" "$producer/v1_coulomb_full_iq_1_rank0.dat" "$case_dir/reference/"
if [[ -f "$ao_potentials.json" ]]; then
    cp "$ao_potentials.json" "$case_dir/reference/"
else
    cp "${ao_potentials%.dat}.json" "$case_dir/reference/"
fi
cp "$producer/RESULT_SUMMARY.txt" "$case_dir/reference/PRODUCER_RESULT_SUMMARY.txt"
cp "$producer/AO_GATE.json" "$producer/contract.json" "$producer/SOURCE_AUDIT.json" "$case_dir/reference/"
test "$(sha256sum "$frequency" | awk '{print $1}')" = "$frequency_sha"
if [[ "$mode" = pilot ]]; then
    awk '/^#/ {print; next} NF {print; exit}' "$frequency" > "$case_dir/fixed_frequency_grid.dat"
else
    cp "$frequency" "$case_dir/fixed_frequency_grid.dat"
fi
test "$(awk '!/^#/ && NF {n++} END {print n+0}' "$case_dir/fixed_frequency_grid.dat")" -eq "$nfreq"
cd "$case_dir"
set_input_key()
{
    local key=$1 value=$2
    sed -i -E "/^[[:space:]]*${key}[[:space:]]+/d" INPUT
    printf '%-38s %s\n' "$key" "$value" >> INPUT
}
suffix=${case_id}_LIMITS_ANALYTIC_AO_TAIL_${mode}_FD8
set_input_key suffix "$suffix"
set_input_key symmetry -1
set_input_key exx_singularity_correction limits
set_input_key out_sternheimer_librpa 1
set_input_key sternheimer_grid_diagnostics 1
set_input_key sternheimer_fd_order 8
set_input_key sternheimer_nfreq "$nfreq"
set_input_key sternheimer_frequency_grid_file fixed_frequency_grid.dat
set_input_key sternheimer_delta 1
set_input_key sternheimer_delta_virtual_source ks_bands
set_input_key sternheimer_delta_max_states 0
set_input_key sternheimer_delta_norm_tol 1e-10
set_input_key sternheimer_frequency_mpi 1
set_input_key sternheimer_channel_mpi 1
set_input_key sternheimer_mpi_layout global_equation
set_input_key rpa_abfs_preorth onsite_coulomb
set_input_key rpa_abfs_preorth_threshold 1e-2
test "$expected_equations" -eq "$((nfreq * naux * nocc_total))"

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export OMP_DYNAMIC=FALSE OMP_PROC_BIND=spread OMP_PLACES=cores OMP_STACKSIZE=2G
export OMP_MAX_ACTIVE_LEVELS=1 MKL_DYNAMIC=FALSE
export I_MPI_FABRICS=shm:ofi I_MPI_PIN=1 I_MPI_PIN_DOMAIN=omp
export ABACUS_STERNHEIMER_CHANNEL_THREADS=$OMP_NUM_THREADS
export ABACUS_STERNHEIMER_CHANNEL_BATCH_WIDTH=2
export ABACUS_STERNHEIMER_FD_ST_ORBITAL_DIR=$case_dir/
export ABACUS_STERNHEIMER_FD_ST_ORBITAL_FILES=$orbital_files
export ABACUS_STERNHEIMER_FD_ST_MAX_ITER=300
export ABACUS_STERNHEIMER_FD_ST_SOLVER_TOL=1e-6
export ABACUS_STERNHEIMER_FD_ST_SPECTRAL_PRECONDITIONER=true
export ABACUS_STERNHEIMER_FD_ST_SPECTRAL_PRECONDITIONER_REGULARIZATION=0
export ABACUS_STERNHEIMER_DELTA_A_BLOCK=reference_value_gradient
set_input_key sternheimer_molecular_coulomb isolated_ri
set_input_key sternheimer_ao_potential_file "$ao_potentials"
unset ABACUS_STERNHEIMER_ANALYTIC_AO_POTENTIALS ABACUS_STERNHEIMER_MOLECULAR_COULOMB_TAIL
export ABACUS_STERNHEIMER_LCAO_SOS_DIAG=false
unset ABACUS_STERNHEIMER_GLOBAL_COULOMB_WHITENING_THRESHOLD ABACUS_STERNHEIMER_GLOBAL_COULOMB_WHITENING_V1

{
    echo status=running
    echo scientific_status=isolated_ri_validation_pending
    echo build_job_id=$build_job_id
    echo producer_job_id=$producer_job_id
    echo frequency_job_id=$frequency_job_id
    echo nfreq=$nfreq
    echo naux=$naux
    echo expected_equations=$expected_equations
    echo source_contract=analytic_AO_rhs_and_left_grid_Q_rhs
    echo grid_Q_potential=isolated_charge_multipole_tail
    echo grid_level=paper_refinement_20260913
    echo actual_grid=$grid
    echo response_mode=$mode
    echo case_id=$case_id
    echo nocc_total=$nocc_total
    echo orbital_effective_configuration=$orbital_effective_configuration
    date -Is
    sha256sum "$abacus" "$ao_potentials" INPUT KPT STRU fixed_frequency_grid.dat reference/* ./*.upf ./*.orb
} > RUN_PROVENANCE.txt
date -Is
printf '%s\n' "$PWD" "$SLURM_JOB_NODELIST" "$SLURM_JOB_CPUS_PER_NODE"
ulimit -s unlimited
/usr/bin/time -v -o abacus.time mpirun -np "$SLURM_NTASKS" -ppn 1 "$abacus" > abacus.out 2>&1
/usr/bin/python3 - "$case_dir" "$grid" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, '/HPC/sternheimer_tests/li_grid_isolated_ri_20260908')
from grid_gate import actual_grid
p = Path(sys.argv[1])
logs = list(p.glob('OUT.*/running_scf.log'))
assert len(logs) == 1
actual_grid(logs[0].read_text(), int(sys.argv[2]))
PY
status=OUT.$suffix/STERNHEIMER_CHI0.dat
test -s "$status"
grep -Fxq 'status success' "$status"
grep -Fxq 'all_converged yes' "$status"
grep -Fxq "nfreq $nfreq" "$status"
grep -Fxq "abfs_channels $naux" "$status"
grep -Fxq "solved_equations $expected_equations" "$status"
grep -Fxq 'analytic_ao_coupling yes' "$status"
grep -Fxq 'analytic_ao_contract rhs_and_left_projection' "$status"
grep -Fxq 'analytic_ao_qspace re_solved_grid_rhs' "$status"
grep -Fxq 'molecular_coulomb_tail isolated_charge_multipole' "$status"
test -s STERNHEIMER_COULOMB_TAIL.dat
grep -Fxq 'sternheimer_preconditioner fd_spectral' "$status"
grep -Fxq 'sternheimer_preconditioner_regularization_Ry 0' "$status"
awk '$1 == "analytic_ao_reconstruction_max_relative_error" {if ($2 > 1e-8) exit 1; found=1} END {if (!found) exit 2}' "$status"
awk '$1 == "max_solver_relative_residual" {if ($2 > 1e-6) exit 1; found=1} END {if (!found) exit 2}' "$status"
cmp -s "$producer/basis_aux_out" basis_aux_out
test "$(find . -maxdepth 1 -type f -name 'v1_sternheimer_chi0_iq_1_ifreq_*_rank*.dat' | wc -l)" -eq "$nfreq"
test "$(find . -maxdepth 1 -type f -name 'v1_sternheimer_component_*_iq_1_ifreq_*_rank*.dat' | wc -l)" -eq "$((nfreq * 3))"
test "$(awk '/^equation / {n++} END {print n+0}' STERNHEIMER_CHI0_PROGRESS_rank*.dat)" -eq "$expected_equations"
failure_markers=$(grep -Eini '(^|[^[:alnum:]_])(nan|fatal)([^[:alnum:]_]|$)|out of memory|oom-kill|segmentation fault|program aborted|unconverged equation' abacus.out abacus.time "$status" 2>/dev/null | grep -Ev 'override_qpe_solver_nan[[:space:]]*=[[:space:]]*false' || true)
test -z "$failure_markers"
{
    echo status=success
    echo scientific_status=isolated_ri_validation_pending
    echo producer_job_id=$producer_job_id
    echo build_job_id=$build_job_id
    echo nfreq=$nfreq
    echo naux=$naux
    echo solved_equations=$expected_equations
    echo response_matrices=$nfreq
    echo all_converged=yes
    echo common_basis_aux_byte_identical=yes
    grep -E 'Elapsed \(wall clock\)|Maximum resident set size' abacus.time
    echo real_failure_marker_count=0
    echo grid_Q_potential=isolated_charge_multipole_tail
    echo grid_level=paper_refinement_20260913
    echo actual_grid=$grid
    echo response_mode=$mode
    echo case_id=$case_id
    echo nocc_total=$nocc_total
    echo orbital_effective_configuration=$orbital_effective_configuration
    grep -E '^(analytic_ao_|max_solver_relative_residual|max_equation_residual_norm)' "$status"
    sha256sum "$abacus" "$ao_potentials" basis_aux_out reference/v1_coulomb_full_iq_1_rank0.dat v1_sternheimer_chi0*rank*.dat v1_sternheimer_component*rank*.dat
} > RESULT_SUMMARY.txt
sed -i 's/^status=running$/status=success/' RUN_PROVENANCE.txt
echo HN_ANALYTIC_AO_TAIL_OK
