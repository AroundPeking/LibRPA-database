#!/bin/bash
#SBATCH --job-name=fd8_scr_q
#SBATCH --partition=normal
#SBATCH --nodes=16
#SBATCH --ntasks=16
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=30
#SBATCH --mem=110610M
#SBATCH --time=1-00:00:00
#SBATCH --output=/HPC/solid-delta-fd8-screening-20260825/logs/solid-q-%A_%a.out
#SBATCH --error=/HPC/solid-delta-fd8-screening-20260825/logs/solid-q-%A_%a.err

set -euo pipefail
trap 'rc=$?; echo "FD8_SCREEN_SOLID_FAILED line=$LINENO command=$BASH_COMMAND rc=$rc" >&2; exit $rc' ERR
source /HPC/app/src/env_60_245_intel2021.sh

stage=/HPC/solid-delta-fd8-screening-20260825
material=${MATERIAL:?missing MATERIAL}
case_tag=${CASE_TAG:?missing CASE_TAG}
grid_n=${GRID_N:?missing GRID_N}
namespace=${RESPONSE_NAMESPACE:-pilot}
kpoint_groups=${KPOINT_GROUPS:-1}
iq=${SLURM_ARRAY_TASK_ID:?submit this script as a q-index array}

case "$material:$grid_n" in
  sic:24|ge:27|mgo:20) ;;
  *) echo "unsupported material/grid pair: $material/$grid_n" >&2; exit 2 ;;
esac
case "$iq" in
  1|2|3|6|7|8|11|22|23|24|27|28|43) ;;
  *) echo "unsupported canonical q index: $iq" >&2; exit 2 ;;
esac
case "$namespace" in pilot|response) ;; *) echo "invalid namespace=$namespace" >&2; exit 2;; esac
case "$kpoint_groups" in 1|4) ;; *) echo "invalid KPOINT_GROUPS=$kpoint_groups" >&2; exit 2;; esac

expected_ntasks=$((16 * kpoint_groups))

artifact=/HPC/delta-st-master-merge-20260823/artifacts/abacus-merge-current
exe=$artifact/abacus_3p
expected_commit=192a49e0ff78487480ac8ddd2cc83c196ec0f73d
expected_sha=86b5232b75f8be8a682ca45fefa6cc799719e42757004611cd091eacf11dfa21
reference=$stage/materials/$material/solid
validator=$stage/jobs/validate_abacus_scf_output.sh
root=$stage/runs/$material/$case_tag/solid/$namespace
work=$root/q${iq}-job${SLURM_ARRAY_JOB_ID}_${iq}

test "$SLURM_JOB_PARTITION" = normal
test "$SLURM_NNODES" -eq "$expected_ntasks"
test "$SLURM_NTASKS" -eq "$expected_ntasks"
test "$SLURM_NTASKS_PER_NODE" -eq 1
test "$SLURM_CPUS_PER_TASK" -eq 30
test -x "$exe"
test "$(sha256sum "$exe" | awk '{print $1}')" = "$expected_sha"
grep -q "^commit=$expected_commit$" "$artifact/provenance.txt"
test -x "$validator"
test ! -e "$work"
mkdir -p "$work" "$root"
install -m 0644 "$reference"/* "$work/"
cd "$work"

set_input_key() {
  local key=$1 value=$2
  if awk -v key="$key" '$1 == key {found=1} END {exit !found}' INPUT; then
    sed -i -E "s|^[[:space:]]*${key}[[:space:]]+.*|${key} ${value}|" INPUT
  else
    printf '%-31s %s\n' "$key" "$value" >> INPUT
  fi
}

sed -i -E 's|^[[:space:]]*[0-9]+[[:space:]]+[0-9]+[[:space:]]+[0-9]+[[:space:]]+0[[:space:]]+0[[:space:]]+0[[:space:]]*$|4 4 4 0 0 0|' KPT
set_input_key suffix "${material^^}_FD8_SCREEN_Q${iq}"
set_input_key ecutwfc 30
set_input_key nx "$grid_n"
set_input_key ny "$grid_n"
set_input_key nz "$grid_n"
set_input_key symmetry 1
set_input_key kpar "$kpoint_groups"
set_input_key sternheimer_nfreq 16
set_input_key sternheimer_frequency_mpi 1
set_input_key sternheimer_channel_mpi 0
set_input_key sternheimer_mpi_layout frequency_grouped
sed -i -E '/^[[:space:]]*sternheimer_frequency_grid_file[[:space:]]+/d' INPUT
set_input_key sternheimer_q_index "$iq"
set_input_key sternheimer_delta 1
set_input_key sternheimer_fd_order 8
set_input_key exx_pca_threshold 1e-6
set_input_key exx_ccp_rmesh_times 2
set_input_key rpa_ccp_rmesh_times 2

export LD_LIBRARY_PATH="$artifact:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_DYNAMIC=FALSE
export OMP_DYNAMIC=FALSE OMP_PROC_BIND=spread OMP_PLACES=cores OMP_STACKSIZE=2G
export OMP_MAX_ACTIVE_LEVELS=1
export I_MPI_PIN=1 I_MPI_PIN_DOMAIN=omp I_MPI_FABRICS=shm:ofi
export ABACUS_STERNHEIMER_CHANNEL_THREADS=$OMP_NUM_THREADS
export ABACUS_STERNHEIMER_FD_ST_SOLVER_TOL=1e-8
export ABACUS_STERNHEIMER_FD_ST_MAX_ITER=300
export ABACUS_STERNHEIMER_FD_SOLVER_MAX_ITER=300
export ABACUS_STERNHEIMER_DELTA_A_BLOCK=reference_value_gradient

{
  echo status=running
  echo scientific_status=SCREENING_NOT_CONVERGED
  echo server=df_dcu
  echo storage_root=$stage
  echo material=$material
  echo case_tag=$case_tag
  echo namespace=$namespace
  echo q_index=$iq
  echo lattice_and_structure=from_frozen_material_assets
  echo ecut_ry=30
  echo explicit_grid=${grid_n}x${grid_n}x${grid_n}
  echo finite_difference_order=8
  echo nfreq=16
  echo frequency_grid=greenx_minimax
  echo pca_threshold=1e-6
  echo kmesh=4x4x4
  echo qmesh=4x4x4
  echo full_coulomb=yes_generated_in_same_q_run
  echo q0_included=yes
  echo headwing_postprocess=qavg_body_start_1
  echo exx_ccp_rmesh_times=2
  echo rpa_ccp_rmesh_times=2
  echo mpi_layout=frequency_grouped
  echo kpoint_groups=$kpoint_groups
  echo mpi_ranks=$expected_ntasks
  echo mpi_ranks_per_node=1
  echo omp_threads=30
  echo abacus_commit=$expected_commit
  echo abacus_sha256=$expected_sha
  sha256sum INPUT KPT STRU ./*.upf ./*.orb
} > RUN_PROVENANCE.txt

ulimit -s unlimited
/usr/bin/time -v -o abacus.time \
  mpirun -np "$SLURM_NTASKS" -ppn 1 "$exe" > abacus.out 2>&1

"$validator" abacus.out 1e-8 >/dev/null
report=$(find . -path './OUT.*/STERNHEIMER_CHI0.dat' -type f -print -quit)
test -n "$report"
grep -q '^status success$' "$report"
grep -q '^format v1_partial$' "$report"
grep -q '^frequency_grid_source greenx_minimax$' "$report"
grep -q '^nfreq 16$' "$report"
grep -q '^periodic_kmesh 4 4 4$' "$report"
grep -q '^sternheimer_mode delta$' "$report"
grep -q '^sternheimer_fd_order 8$' "$report"
grep -q '^sternheimer_frequency_groups 16$' "$report"
grep -q "^sternheimer_kpoint_groups $kpoint_groups$" "$report"
case "$kpoint_groups" in
  1) grep -q '^sternheimer_kpoint_mpi no$' "$report" ;;
  4) grep -q '^sternheimer_kpoint_mpi yes$' "$report" ;;
esac
grep -q "^mpi_ranks $expected_ntasks$" "$report"
grep -q '^all_converged yes$' "$report"
awk -v iq="$iq" '$1=="sternheimer_canonical_q_indices" {for(i=2;i<=NF;i++) if($i==iq) found=1} END {exit !found}' "$report"
actual_grid=$(awk '$1=="grid" {print $2 "x" $3 "x" $4}' "$report")
test "$actual_grid" = "${grid_n}x${grid_n}x${grid_n}"
test -s "v1_sternheimer_partial_manifest_iq_${iq}.dat"
test -s "v1_sternheimer_symmetry_routes_iq_${iq}.dat"
test -s "v1_sternheimer_qstar_routes_iq_${iq}.dat"
channels=$(awk '$1=="abfs_channels" {print $2}' "$report")
test -n "$channels"

{
  echo status=success
  echo scheduler_exit_expected=0:0
  echo all_converged=yes
  echo actual_grid=$actual_grid
  echo abfs_channels=$channels
  grep -E '^data_files |^transition_window_Ha |^occupied_bands_total |^solved_equations |^max_' "$report"
  sed -n 's/^[[:space:]]*Elapsed (wall clock) time (h:mm:ss or m:ss):[[:space:]]*/wall_clock=/p' abacus.time
} >> RUN_PROVENANCE.txt
ln -sfn "$work" "$root/latest_q${iq}"
echo "FD8_SCREEN_SOLID_OK material=$material q=$iq grid=$actual_grid work=$work"
