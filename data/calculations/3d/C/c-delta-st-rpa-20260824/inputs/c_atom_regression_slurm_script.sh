#!/bin/bash
#SBATCH -J c8_atom_e5ef_reg
#SBATCH -p normal
#SBATCH -N 8
#SBATCH --ntasks=8
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=30
#SBATCH --mem=110610M
#SBATCH -t 02:00:00
#SBATCH -o /HPC/c-solid-grid-fd8-final-20260823/logs/regress-c-atom.%j.out
#SBATCH -e /HPC/c-solid-grid-fd8-final-20260823/logs/regress-c-atom.%j.err

set -euo pipefail

root=/HPC/c-solid-grid-fd8-final-20260823
legacy_root=/HPC/delta-st-unified-abacus-20260817
input_dir=$legacy_root/regression-inputs/c_atom
run_root=$root/atom_regression/e5ef_vs_556/job${SLURM_JOBID}
old_exe=$legacy_root/artifacts/current/abacus_3p
new_artifact=$(readlink -f /HPC/delta-st-periodic-fd8-20260822/artifacts/current-e5ef)
new_exe=$new_artifact/abacus_3p
compare=$legacy_root/jobs/compare_chi0_v1.py
frequency_grid=$legacy_root/regression-inputs/si_atom_ecut20_nfreq6.dat
python_exe=/HPC/.conda/envs/ds092/bin/python

source /HPC/app/src/env_60_245_intel2021.sh

test -x "$old_exe"
test -x "$new_exe"
test "$(sha256sum "$old_exe" | awk '{print $1}')" = 6663de9c4857cf7d012aae06d06572ae5bbc79ca5236ac80d057d325175b1366
test "$(sha256sum "$new_exe" | awk '{print $1}')" = c1eb5003b374f97980ef1423260cfbb483f95b17ee290681182e640bdfa7a8b1
grep -q '^commit=e5ef955dbc5b06f59a9d335348cb05634cd9d1d3$' /HPC/delta-st-periodic-fd8-20260822/SOURCE_MANIFEST_e5ef955db.txt
test -x "$compare"
test -s "$frequency_grid"
test ! -e "$run_root"
mkdir -p "$run_root"

set_input_key() {
  local file=$1 key=$2 value=$3
  if awk -v key="$key" '$1 == key {found=1} END {exit !found}' "$file"; then
    sed -i -E "s|^[[:space:]]*${key}[[:space:]]+.*|${key} ${value}|" "$file"
  else
    printf '%-31s %s\n' "$key" "$value" >> "$file"
  fi
}

run_case() {
  local label=$1 exe=$2
  local work=$run_root/$label
  mkdir -p "$work"
  install -m 0644 "$input_dir"/* "$work/"
  install -m 0644 "$frequency_grid" "$work/fixed_frequency_grid.dat"
  set_input_key "$work/INPUT" suffix "C_ATOM_UNIFIED_REGRESSION_${label^^}"
  set_input_key "$work/INPUT" ecutwfc 8
  set_input_key "$work/INPUT" sternheimer_nfreq 6
  set_input_key "$work/INPUT" sternheimer_frequency_grid_file fixed_frequency_grid.dat
  set_input_key "$work/INPUT" sternheimer_frequency_mpi 1
  set_input_key "$work/INPUT" sternheimer_channel_mpi 1
  set_input_key "$work/INPUT" sternheimer_mpi_layout global_equation
  set_input_key "$work/INPUT" sternheimer_delta 1
  set_input_key "$work/INPUT" sternheimer_fd_order 8
  set_input_key "$work/INPUT" exx_pca_threshold 1e-4
  set_input_key "$work/INPUT" exx_ccp_rmesh_times 1
  set_input_key "$work/INPUT" rpa_ccp_rmesh_times 1
  set_input_key "$work/INPUT" ocp 1
  set_input_key "$work/INPUT" ocp_set '3*1 19*0 1*1 21*0'
  (
    cd "$work"
    export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
    export OMP_DYNAMIC=FALSE OMP_PROC_BIND=spread OMP_PLACES=cores MKL_DYNAMIC=FALSE OMP_STACKSIZE=2G
    export OMP_MAX_ACTIVE_LEVELS=1 I_MPI_PIN=1 I_MPI_PIN_DOMAIN=omp I_MPI_FABRICS=shm:ofi
    export ABACUS_STERNHEIMER_CHANNEL_THREADS=$OMP_NUM_THREADS
    export ABACUS_STERNHEIMER_FD_ST_SOLVER_TOL=1e-8
    export ABACUS_STERNHEIMER_FD_ST_MAX_ITER=300
    export ABACUS_STERNHEIMER_FD_SOLVER_MAX_ITER=300
    export ABACUS_STERNHEIMER_DELTA_A_BLOCK=reference_value_gradient
    /usr/bin/time -v -o abacus.time mpirun -np "$SLURM_NTASKS" -ppn 1 "$exe" > abacus.out 2>&1
    report=$(find . -path './OUT.*/STERNHEIMER_CHI0.dat' -type f -print -quit)
    test -n "$report"
    grep -q '^status success$' "$report"
    grep -q '^sternheimer_fd_order 8$' "$report"
    grep -q '^sternheimer_channel_mpi yes$' "$report"
    grep -q '^sternheimer_mpi_layout global_equation$' "$report"
    grep -q '^all_converged yes$' "$report"
    test "$(find . -maxdepth 1 -name 'v1_sternheimer_chi0_iq_1_ifreq_*.dat' -type f | wc -l)" -eq 6
  )
}

run_case unified_556 "$old_exe"
run_case unified_e5ef "$new_exe"
"$python_exe" "$compare" "$run_root/unified_556" "$run_root/unified_e5ef" \
  --pattern 'v1_sternheimer_chi0_iq_1_ifreq_*.dat' \
  --atol 2e-9 --rtol 2e-9 > "$run_root/CHI0_COMPARISON.txt"

{
  echo 'status=success'
  echo 'case=c_atom_fd8_global_equation_e5ef_vs_556'
  echo 'box_angstrom=20'
  echo 'ecut_ry=8'
  echo 'nfreq=6'
  echo 'old_label=unified_556'
  echo 'new_label=unified_e5ef'
  echo 'new_commit=e5ef955dbc5b06f59a9d335348cb05634cd9d1d3'
  echo "old_sha256=$(sha256sum "$old_exe" | awk '{print $1}')"
  echo "new_sha256=$(sha256sum "$new_exe" | awk '{print $1}')"
  echo 'response_gate_atol=2e-9'
  echo 'response_gate_rtol=2e-9'
  cat "$run_root/CHI0_COMPARISON.txt"
} > "$run_root/REGRESSION_SUMMARY.txt"

echo "UNIFIED_C_ATOM_REGRESSION_OK work=$run_root"
