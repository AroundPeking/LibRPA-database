#!/bin/bash
#SBATCH --job-name=si8_grid_q
#SBATCH --partition=normal
#SBATCH --nodes=12
#SBATCH --ntasks=12
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=30
#SBATCH --mem=110610M
#SBATCH --time=1-00:00:00
#SBATCH --output=/HPC/si-solid-grid-fd8-final-20260823/logs/response-%A_%a.out
#SBATCH --error=/HPC/si-solid-grid-fd8-final-20260823/logs/response-%A_%a.err

set -euo pipefail
source /HPC/app/src/env_60_245_intel2021.sh

stage=/HPC/si-solid-grid-fd8-final-20260823
reference=$stage/materials/si/solid
artifact=/HPC/delta-st-periodic-fd8-20260822/artifacts/current-e5ef
exe=$artifact/abacus_3p
expected_sha=c1eb5003b374f97980ef1423260cfbb483f95b17ee290681182e640bdfa7a8b1
expected_commit=e5ef955dbc5b06f59a9d335348cb05634cd9d1d3
validator=$stage/jobs/validate_abacus_scf_output.sh
coulomb_audit=$stage/jobs/audit_coulomb_v1_hermiticity.py
python_exe=/HPC/.conda/envs/ds092/bin/python
ecut=${ECUT:-40}
grid_n=${GRID_N:?missing GRID_N}
iq=${SLURM_ARRAY_TASK_ID:?missing q index}
metric_only=${METRIC_ONLY:-0}
kpoint_groups=${KPOINT_GROUPS:-1}
channel_mpi=${CHANNEL_MPI:-0}
response_namespace=${RESPONSE_NAMESPACE:-response}
test "$ecut" -eq 40
case "$grid_n" in 15|24|30|35) ;; *) echo "unsupported GRID_N=$grid_n" >&2; exit 2;; esac
case "$iq" in 1|2|3|6|7|8|11|22|23|24|27|28|43) ;; *) echo "unsupported canonical q=$iq" >&2; exit 2;; esac
case "$metric_only" in 0|1) ;; *) echo "METRIC_ONLY must be 0 or 1" >&2; exit 2;; esac
case "$kpoint_groups" in 1|2|4|8) ;; *) echo "KPOINT_GROUPS must be 1, 2, 4, or 8" >&2; exit 2;; esac
case "$channel_mpi" in 0|1) ;; *) echo "CHANNEL_MPI must be 0 or 1" >&2; exit 2;; esac
case "$response_namespace" in response|runtime_ab_*) ;; *) echo "invalid RESPONSE_NAMESPACE=$response_namespace" >&2; exit 2;; esac

kind=response
nfreq=12
exx_rmesh=1
if test "$metric_only" -eq 1; then
  kind=metric
  nfreq=1
  exx_rmesh=2
  kpoint_groups=1
  channel_mpi=0
  response_namespace=response
fi
case_tag=g${grid_n}_fd8
if test "$metric_only" -eq 1; then
  root=$stage/runs/${case_tag}/solid/$kind
else
  root=$stage/runs/${case_tag}/solid/$response_namespace
fi
case_dir=$root/q${iq}-job${SLURM_ARRAY_JOB_ID}_${iq}
fingerprint=$(readlink -f "$stage/grid_fingerprints/latest_g${grid_n}")

test "$SLURM_JOB_PARTITION" = normal
test -x "$exe"
test "$(sha256sum "$exe" | awk '{print $1}')" = "$expected_sha"
grep -q "^commit=$expected_commit$" /HPC/delta-st-periodic-fd8-20260822/SOURCE_MANIFEST_e5ef955db.txt
grep -q '^status=success$' "$fingerprint/GRID_FINGERPRINT.txt"
grep -q "^ecut_ry=$ecut$" "$fingerprint/GRID_FINGERPRINT.txt"
grep -q "^requested_grid=$grid_n,$grid_n,$grid_n$" "$fingerprint/GRID_FINGERPRINT.txt"
grep -q '^finite_difference_order=8$' "$fingerprint/GRID_FINGERPRINT.txt"
if test "$metric_only" -eq 1; then
  test "$iq" -eq 1
  test "$SLURM_NTASKS" -eq 1
  test "$SLURM_NTASKS_PER_NODE" -eq 1
  test "$SLURM_CPUS_PER_TASK" -eq 30
else
  expected_ntasks=$((nfreq * kpoint_groups))
  test "$SLURM_NTASKS" -eq "$expected_ntasks"
  case "$SLURM_CPUS_PER_TASK" in 15|30) ;; *) echo "response cpus-per-task must be 15 or 30" >&2; exit 2;; esac
fi
test ! -e "$case_dir"
mkdir -p "$case_dir" "$root"
install -m 0644 "$reference"/* "$case_dir/"
cd "$case_dir"

set_input_key() {
  local key=$1 value=$2
  if awk -v key="$key" '$1 == key {found=1} END {exit !found}' INPUT; then
    sed -i -E "s|^[[:space:]]*${key}[[:space:]]+.*|${key} ${value}|" INPUT
  else
    printf '%-31s %s\n' "$key" "$value" >> INPUT
  fi
}

sed -i -E 's|^[[:space:]]*[0-9]+[[:space:]]+[0-9]+[[:space:]]+[0-9]+[[:space:]]+0[[:space:]]+0[[:space:]]+0[[:space:]]*$|4 4 4 0 0 0|' KPT
set_input_key suffix "SI_GRID_${case_tag^^}_NF${nfreq}_Q${iq}"
set_input_key ecutwfc "$ecut"
set_input_key nx "$grid_n"
set_input_key ny "$grid_n"
set_input_key nz "$grid_n"
set_input_key symmetry 1
set_input_key kpar "$kpoint_groups"
set_input_key sternheimer_nfreq "$nfreq"
set_input_key sternheimer_frequency_mpi 1
set_input_key sternheimer_channel_mpi "$channel_mpi"
set_input_key sternheimer_mpi_layout frequency_grouped
sed -i -E '/^[[:space:]]*sternheimer_frequency_grid_file[[:space:]]+/d' INPUT
set_input_key sternheimer_q_index "$iq"
set_input_key sternheimer_delta 1
set_input_key sternheimer_fd_order 8
set_input_key exx_pca_threshold 1e-6
set_input_key exx_ccp_rmesh_times "$exx_rmesh"
set_input_key rpa_ccp_rmesh_times 2

export LD_LIBRARY_PATH="$artifact:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export OMP_DYNAMIC=FALSE OMP_PROC_BIND=spread OMP_PLACES=cores MKL_DYNAMIC=FALSE OMP_STACKSIZE=2G
export I_MPI_PIN=1 I_MPI_PIN_DOMAIN=omp I_MPI_FABRICS=shm:ofi
export ABACUS_STERNHEIMER_CHANNEL_THREADS=$OMP_NUM_THREADS
export ABACUS_STERNHEIMER_FD_ST_SOLVER_TOL=1e-8
export ABACUS_STERNHEIMER_FD_ST_MAX_ITER=300
export ABACUS_STERNHEIMER_DELTA_A_BLOCK=reference_value_gradient

{
  echo status=running
  echo job_id=$SLURM_JOBID
  echo array_job_id=$SLURM_ARRAY_JOB_ID
  echo server=df_dcu
  echo storage_root=$stage
  echo purpose=si_solid_fixed_40Ry_fd8_grid_convergence
  echo ecut_ry=$ecut
  echo explicit_grid_n=$grid_n
  echo case_tag=$case_tag
  echo q_index=$iq
  echo finite_difference_order=8
  echo nfreq=$nfreq
  echo frequency_grid=greenx_minimax
  echo sternheimer_mpi_layout=frequency_grouped
  echo sternheimer_kpoint_groups=$kpoint_groups
  echo sternheimer_channel_mpi=$channel_mpi
  echo mpi_ranks=$SLURM_NTASKS
  echo cpus_per_task=$SLURM_CPUS_PER_TASK
  echo response_namespace=$response_namespace
  echo kmesh=4x4x4
  echo qmesh=4x4x4
  echo pca_threshold=1e-6
  echo exx_ccp_rmesh_times=$exx_rmesh
  echo rpa_ccp_rmesh_times=2
  echo metric_only=$metric_only
  echo abacus_commit=$expected_commit
  echo abacus_sha256=$expected_sha
  sha256sum "$0"
  cat "$fingerprint/GRID_FINGERPRINT.txt"
  sha256sum INPUT KPT STRU ./*.upf ./*.orb
} > RUN_PROVENANCE.txt

ulimit -s unlimited
set +e
/usr/bin/time -v -o abacus.time mpirun -np "$SLURM_NTASKS" -ppn "$SLURM_NTASKS_PER_NODE" "$exe" > abacus.out 2>&1
abacus_rc=$?
set -e

if test "$metric_only" -eq 1; then
  report=$(find . -path './OUT.*/STERNHEIMER_CHI0.dat' -type f -print -quit)
  test -n "$report"
  grep -q '^status failed$' "$report"
  grep -q '^reason GreenX minimax frequency-grid generation failed with ierr=1\.$' "$report"
  "$python_exe" "$coulomb_audit" . > COULOMB_HERMITICITY.txt
  awk 'NR > 1 && $5 > 1e-10 {bad=1} END {exit bad}' COULOMB_HERMITICITY.txt
  {
    echo status=success
    echo abacus_complete=no_metric_only_expected_greenx_exit
    echo coulomb_metric_complete=yes
    sed -n 's/^[[:space:]]*Elapsed (wall clock) time (h:mm:ss or m:ss):[[:space:]]*/wall_clock=/p' abacus.time
  } >> RUN_PROVENANCE.txt
  ln -sfn "$case_dir" "$root/latest_q${iq}"
  echo "SI_GRID_FD8_METRIC_OK ecut=$ecut grid_n=$grid_n work=$case_dir"
  exit 0
fi

test "$abacus_rc" -eq 0
"$validator" abacus.out 1e-8 >/dev/null
report=$(find . -path './OUT.*/STERNHEIMER_CHI0.dat' -type f -print -quit)
test -n "$report"
grep -q '^status success$' "$report"
grep -q '^format v1_partial$' "$report"
grep -q '^frequency_grid_source greenx_minimax$' "$report"
grep -q '^nfreq 12$' "$report"
grep -q '^periodic_kmesh 4 4 4$' "$report"
grep -q '^sternheimer_mode delta$' "$report"
grep -q '^sternheimer_fd_order 8$' "$report"
grep -q '^sternheimer_frequency_groups 12$' "$report"
grep -q "^sternheimer_kpoint_groups $kpoint_groups$" "$report"
grep -q "^mpi_ranks $expected_ntasks$" "$report"
grep -q '^all_converged yes$' "$report"
awk -v iq="$iq" '$1=="sternheimer_canonical_q_indices" {for(i=2;i<=NF;i++) if($i==iq) found=1} END {exit !found}' "$report"
expected_grid=$(awk -F= '$1=="charge_grid" {gsub(/,/," ",$2); print $2}' "$fingerprint/GRID_FINGERPRINT.txt")
actual_grid=$(awk '$1=="grid" {print $2, $3, $4}' "$report")
test "$actual_grid" = "$expected_grid"
test -s "v1_sternheimer_partial_manifest_iq_${iq}.dat"
test -s "v1_sternheimer_symmetry_routes_iq_${iq}.dat"
test -s "v1_sternheimer_qstar_routes_iq_${iq}.dat"
channels=$(awk '$1=="abfs_channels" {print $2}' "$report")
test -n "$channels"

{
  echo status=success
  echo abacus_complete=yes
  echo response_coulomb_audit=authoritative_metric_job_separate
  echo abfs_channels=$channels
  grep -E '^status |^format |^data_files |^grid |^nfreq |^frequency_grid_source |^transition_window_Ha |^periodic_kmesh |^sternheimer_(mode|fd_order|canonical_q_indices) |^occupied_bands_total |^solved_equations |^all_converged |^max_' "$report"
  sed -n 's/^[[:space:]]*Elapsed (wall clock) time (h:mm:ss or m:ss):[[:space:]]*/wall_clock=/p' abacus.time
} >> RUN_PROVENANCE.txt
ln -sfn "$case_dir" "$root/latest_q${iq}"
echo "SI_GRID_FD8_RESPONSE_OK ecut=$ecut grid_n=$grid_n q=$iq grid=$actual_grid channels=$channels work=$case_dir"
