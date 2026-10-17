#!/bin/bash
#SBATCH --job-name=fd8_scr_atom
#SBATCH --partition=normal
#SBATCH --nodes=64
#SBATCH --ntasks=64
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=30
#SBATCH --mem=110610M
#SBATCH --time=1-00:00:00
#SBATCH --output=/HPC/solid-delta-fd8-screening-20260825/logs/atom-%j.out
#SBATCH --error=/HPC/solid-delta-fd8-screening-20260825/logs/atom-%j.err

set -euo pipefail
trap 'rc=$?; echo "FD8_SCREEN_ATOM_FAILED line=$LINENO command=$BASH_COMMAND rc=$rc" >&2; exit $rc' ERR
source /HPC/app/src/env_60_245_intel2021.sh

stage=/HPC/solid-delta-fd8-screening-20260825
element=${ELEMENT:?missing ELEMENT}
ocp_mode=${OCP_MODE:?missing OCP_MODE}
mixing_beta=${MIXING_BETA:?missing MIXING_BETA}
scf_gate=$(readlink -f "${SCF_GATE_DIR:?missing SCF_GATE_DIR}")
run_mode=${ATOM_RUN_MODE:-production}
mpi_ranks=${ATOM_MPI_RANKS:-$SLURM_NTASKS}
ranks_per_node=${ATOM_RANKS_PER_NODE:-1}
omp_threads=${ATOM_OMP_THREADS:-30}
pilot_seconds=${ATOM_PILOT_SECONDS:-3600}
case_tag=atom_box20_e30_nf16_pca1em6_fd8_merge
artifact=/HPC/delta-st-master-merge-20260823/artifacts/abacus-merge-current
exe=$artifact/abacus_3p
expected_commit=192a49e0ff78487480ac8ddd2cc83c196ec0f73d
expected_sha=86b5232b75f8be8a682ca45fefa6cc799719e42757004611cd091eacf11dfa21
reference=$stage/materials/$element/atom
validator=$stage/jobs/validate_abacus_scf_output.sh
occupation_audit=$stage/jobs/audit_atom_integer_occupations.py
coulomb_audit=$stage/jobs/audit_coulomb_v1_hermiticity.py
python_exe=/HPC/.conda/envs/ds092/bin/python
case "$run_mode" in
  production) root=$stage/runs/atoms/$element/$case_tag/response ;;
  runtime_pilot) root=$stage/runs/atoms/$element/$case_tag/runtime_pilots ;;
  *) echo "unsupported ATOM_RUN_MODE=$run_mode" >&2; exit 2 ;;
esac
work=$root/job$SLURM_JOBID
suffix=${element^^}_ATOM_FD8_MERGE

case "$element:$ocp_mode" in si:si_p2|ge:ge_p2) ;; *) echo "unsupported atom occupation contract" >&2; exit 2;; esac
case "$mixing_beta" in 0.3|0.1|0.05) ;; *) echo "unsupported MIXING_BETA=$mixing_beta" >&2; exit 2;; esac
case "$element" in
  si) scf_accept_thr=${SCF_ACCEPT_THR:-1e-6} ;;
  ge) scf_accept_thr=${SCF_ACCEPT_THR:-2e-6} ;;
esac
case "$element:$scf_accept_thr" in si:1e-6|ge:2e-6) ;; *) echo "unsupported SCF acceptance threshold" >&2; exit 2;; esac
case "$ranks_per_node:$omp_threads" in
  1:30|2:15) ;;
  *) echo "unsupported atom node layout: ranks_per_node=$ranks_per_node omp_threads=$omp_threads" >&2; exit 2 ;;
esac
if test "$run_mode" = production; then
  case "$element:$mpi_ranks:$ranks_per_node" in
    si:64:1|ge:64:1) ;;
    *) echo "unbenchmarked production atom MPI layout: element=$element ranks=$mpi_ranks ranks_per_node=$ranks_per_node" >&2; exit 2 ;;
  esac
else
  test "$element" = ge
  test "$ranks_per_node" -eq 2
  test "$SLURM_NNODES" -le 16
  test "$pilot_seconds" -ge 1800
  test "$pilot_seconds" -le 7200
fi
test "$SLURM_JOB_PARTITION" = normal
test "$SLURM_NTASKS" -eq "$mpi_ranks"
test "$SLURM_NTASKS" -eq "$((SLURM_NNODES * ranks_per_node))"
test "$SLURM_NTASKS_PER_NODE" -eq "$ranks_per_node"
test "$SLURM_CPUS_PER_TASK" -eq "$omp_threads"
test -x "$exe"
test "$(sha256sum "$exe" | awk '{print $1}')" = "$expected_sha"
grep -q "^commit=$expected_commit$" "$artifact/provenance.txt"
grep -q '^status=success$' "$scf_gate/RESULT_SUMMARY.txt"
grep -q '^scf_ok=yes$' "$scf_gate/RESULT_SUMMARY.txt"
grep -q '^integer_occupations=yes ' "$scf_gate/RESULT_SUMMARY.txt"
grep -q "^mixing_beta=$mixing_beta$" "$scf_gate/RESULT_SUMMARY.txt"
gate_out=$(find "$scf_gate" -maxdepth 1 -type d -name 'OUT.*' -print -quit)
test -n "$gate_out"
gate_restart=$(find "$gate_out" -maxdepth 1 -type f -name '*-CHARGE-DENSITY.restart' -print -quit)
test -s "$gate_restart"
if test -s "$scf_gate/wfk1s1_nao.txt" || test -s "$scf_gate/wfk1s2_nao.txt"; then
  test -s "$scf_gate/wfk1s1_nao.txt"
  test -s "$scf_gate/wfk1s2_nao.txt"
  reuse_wfc=yes
else
  reuse_wfc=no
fi
test ! -e "$work"
mkdir -p "$work" "$root"
install -m 0644 "$reference"/* "$work/"
if test "$reuse_wfc" = yes; then
  install -m 0644 "$scf_gate/wfk1s1_nao.txt" "$scf_gate/wfk1s2_nao.txt" "$work/"
fi
install -m 0644 "$gate_restart" "$work/$suffix-CHARGE-DENSITY.restart"
cd "$work"

set_input_key() {
  local key=$1 value=$2
  if awk -v key="$key" '$1 == key {found=1} END {exit !found}' INPUT; then
    sed -i -E "s|^[[:space:]]*${key}[[:space:]]+.*|${key} ${value}|" INPUT
  else
    printf '%-31s %s\n' "$key" "$value" >> INPUT
  fi
}

set_input_key suffix "$suffix"
set_input_key ecutwfc 30
if test "$reuse_wfc" = yes; then
  set_input_key init_wfc file
else
  sed -i -E '/^[[:space:]]*init_wfc[[:space:]]+/d' INPUT
fi
set_input_key init_chg file
set_input_key read_file_dir ./
set_input_key sternheimer_nfreq 16
set_input_key sternheimer_frequency_mpi 1
set_input_key sternheimer_channel_mpi 1
set_input_key sternheimer_mpi_layout global_equation
sed -i -E '/^[[:space:]]*sternheimer_frequency_grid_file[[:space:]]+/d' INPUT
set_input_key sternheimer_delta 1
set_input_key sternheimer_fd_order 8
set_input_key exx_pca_threshold 1e-6
set_input_key exx_ccp_rmesh_times 1
set_input_key rpa_ccp_rmesh_times 1
set_input_key smearing_method fixed
set_input_key scf_thr "$scf_accept_thr"
set_input_key scf_nmax 300
set_input_key mixing_beta "$mixing_beta"
set_input_key mixing_beta_mag "$mixing_beta"
set_input_key mixing_gg0 0.0
set_input_key mixing_gg0_mag 0.0
set_input_key ocp 1
case "$ocp_mode" in
  si_p2)
    test "$(awk '$1=="nelec" {print $2}' INPUT)" = 4
    test "$(awk '$1=="nbands" {print $2}' INPUT)" = 22
    set_input_key ocp_set '3*1 19*0 1*1 21*0'
    ;;
  ge_p2)
    test "$(awk '$1=="nelec" {print $2}' INPUT)" = 14
    test "$(awk '$1=="nbands" {print $2}' INPUT)" = 25
    set_input_key ocp_set '8*1 17*0 6*1 19*0'
    ;;
esac

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
  echo scientific_status=SCREENING_NOT_CONVERGED_ATOMIC_REFERENCE
  echo server=df_dcu
  echo storage_root=$stage
  echo element=$element
  echo case_tag=$case_tag
  echo box_angstrom=20
  echo ecut_ry=30
  echo finite_difference_order=8
  echo nfreq=16
  echo pca_threshold=1e-6
  echo integer_occupation_contract=$ocp_mode
  echo mixing_beta=$mixing_beta
  echo scf_gate=$scf_gate
  echo scf_thr=$scf_accept_thr
  echo scf_acceptance_threshold=$scf_accept_thr
  echo scf_restart_reused=yes
  echo restart_wavefunctions_reused=$reuse_wfc
  echo exx_ccp_rmesh_times=1
  echo rpa_ccp_rmesh_times=1
  echo headwing=no_atom_gamma_only
  echo run_mode=$run_mode
  echo mpi_layout=global_equation
  echo mpi_ranks=$mpi_ranks
  echo mpi_ranks_per_node=$ranks_per_node
  echo omp_threads=$omp_threads
  if test "$run_mode" = runtime_pilot; then echo pilot_seconds=$pilot_seconds; fi
  echo abacus_commit=$expected_commit
  echo abacus_sha256=$expected_sha
  sha256sum INPUT KPT STRU ./*.upf ./*.orb "$suffix-CHARGE-DENSITY.restart"
  if test "$reuse_wfc" = yes; then sha256sum wfk1s1_nao.txt wfk1s2_nao.txt; fi
} > RUN_PROVENANCE.txt

ulimit -s unlimited
if test "$run_mode" = runtime_pilot; then
  if /usr/bin/time -v -o abacus.time \
    timeout --signal=TERM --kill-after=120s "${pilot_seconds}s" \
    mpirun -np "$SLURM_NTASKS" -ppn "$ranks_per_node" "$exe" > abacus.out 2>&1; then
    pilot_rc=0
  else
    pilot_rc=$?
  fi
  if test "$pilot_rc" -ne 0 && test "$pilot_rc" -ne 124 && test "$pilot_rc" -ne 137; then
    echo "unexpected runtime pilot exit code: $pilot_rc" >&2
    exit "$pilot_rc"
  fi
  if test "$pilot_rc" -ne 0; then
    solved=$(awk '$1=="equation" {last[FILENAME]=$7} END {for (f in last) sum+=last[f]; print sum+0}' STERNHEIMER_CHI0_PROGRESS_rank*.dat)
    equation_lines=$(awk '$1=="equation" {n++} END {print n+0}' STERNHEIMER_CHI0_PROGRESS_rank*.dat)
    max_elapsed=$(awk '$1=="equation" && $12>max {max=$12} END {print max+0}' STERNHEIMER_CHI0_PROGRESS_rank*.dat)
    {
      echo status=pilot_complete
      echo expected_timeout=yes
      echo pilot_exit_code=$pilot_rc
      echo solved_equations=$solved
      echo equation_lines=$equation_lines
      echo max_equation_elapsed_s=$max_elapsed
    } >> RUN_PROVENANCE.txt
    echo "FD8_SCREEN_ATOM_RUNTIME_PILOT_OK element=$element work=$work solved=$solved"
    exit 0
  fi
else
  /usr/bin/time -v -o abacus.time \
    mpirun -np "$SLURM_NTASKS" -ppn "$ranks_per_node" "$exe" > abacus.out 2>&1
fi

"$validator" abacus.out "$scf_accept_thr" >/dev/null
eig_occ=$(find . -path './OUT.*/eig_occ.txt' -type f -print -quit)
test -n "$eig_occ"
"$python_exe" "$occupation_audit" "$eig_occ" INPUT > ATOM_OCCUPATION_AUDIT.txt
report=$(find . -path './OUT.*/STERNHEIMER_CHI0.dat' -type f -print -quit)
test -n "$report"
grep -q '^status success$' "$report"
grep -q '^format librpa_v1$' "$report"
grep -q '^nfreq 16$' "$report"
grep -q '^sternheimer_fd_order 8$' "$report"
grep -q '^sternheimer_mpi_layout global_equation$' "$report"
grep -q "^mpi_ranks $mpi_ranks$" "$report"
grep -q '^all_converged yes$' "$report"
test "$(find . -maxdepth 1 -type f -name 'v1_sternheimer_chi0_iq_1_ifreq_*.dat' | wc -l)" -eq 16
"$python_exe" "$coulomb_audit" . > COULOMB_HERMITICITY.txt
awk 'NR > 1 && $5 > 1e-10 {bad=1} END {exit bad}' COULOMB_HERMITICITY.txt
channels=$(awk '$1=="abfs_channels" {print $2}' "$report")
test -n "$channels"

{
  echo status=success
  echo all_converged=yes
  cat ATOM_OCCUPATION_AUDIT.txt
  echo abfs_channels=$channels
  grep -E '^grid |^transition_window_Ha |^occupied_bands |^solved_equations |^max_' "$report"
  sed -n 's/^[[:space:]]*Elapsed (wall clock) time (h:mm:ss or m:ss):[[:space:]]*/wall_clock=/p' abacus.time
} >> RUN_PROVENANCE.txt
ln -sfn "$work" "$root/latest"
echo "FD8_SCREEN_ATOM_OK element=$element work=$work"
