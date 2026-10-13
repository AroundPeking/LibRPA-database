#!/bin/bash
#SBATCH -p 9242
#SBATCH -N 4
#SBATCH --cpus-per-task=96
#SBATCH --ntasks-per-node=1
#SBATCH -J C512_gw
#SBATCH --mem=380000

set -euo pipefail

module load cmake/3.31.7
module load oneapi/2024.2
export CC=mpiicx
export CXX=mpiicpx
export FC=mpiifx

CASE_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
ABACUS_EXEC="${ABACUS_EXEC:-<redacted-user-path>"
LIBRPA_EXEC="${LIBRPA_EXEC:-<redacted-user-path>"
PYTHON_EXEC="${PYTHON_EXEC:-<redacted-user-path>"
MPI_LAUNCHER="${MPI_LAUNCHER:-<redacted-app-path>"
ABACUS_MPI="${ABACUS_MPI:-${SLURM_JOB_NUM_NODES:-4}}"
LIBRPA_MPI="${LIBRPA_MPI:-${SLURM_JOB_NUM_NODES:-4}}"
PYATB_MPI="${PYATB_MPI:-1}"
JOB_TAG="${JOB_ID:-manual}"

cd "$CASE_DIR"

PYTHON_BINDIR="$(cd "$(dirname "$PYTHON_EXEC")" && pwd)"
PYTHON_PREFIX="$(cd "$PYTHON_BINDIR/.." && pwd)"
ONEAPI_LD_LIBRARY_PATH="<redacted-user-path>"
export LD_LIBRARY_PATH="$ONEAPI_LD_LIBRARY_PATH"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-96}"
export MKL_NUM_THREADS=1
export MKL_DYNAMIC=FALSE
export OMP_MAX_ACTIVE_LEVELS=1
export OMP_PLACES=cores
export OMP_PROC_BIND=close
export I_MPI_FABRICS=shm:ofi
export python3_exec="$PYTHON_EXEC"
export mpirun_exec="$MPI_LAUNCHER"
export pyatb_mpi_ranks="$PYATB_MPI"
export python_ld_library_path="$PYTHON_PREFIX/lib"
ulimit -s unlimited
unset LD_PRELOAD

run_and_log() {
    local logfile="$1"
    shift
    "$@" >> "$logfile" 2>&1
}


echo Begin Time: "$(date)"
echo Working directory is "$PWD"
echo This job runs on the following nodes:
echo "${SLURM_JOB_NODELIST:-local}"
echo This job has allocated "${SLURM_JOB_CPUS_PER_NODE:-unknown}" cpu cores.
echo cpus per task: "${SLURM_CPUS_PER_TASK:-unknown}", this should be OMP_NUM_THREADS: "$OMP_NUM_THREADS"
echo ABACUS_EXEC="$ABACUS_EXEC"
echo LIBRPA_EXEC="$LIBRPA_EXEC"
echo PYTHON_EXEC="$PYTHON_EXEC"
echo MPI_LAUNCHER="$MPI_LAUNCHER"

rm -rf OUT.ABACUS librpa.d
rm -f abacus."$JOB_TAG".out LibRPA."$JOB_TAG".out librpa_para_nprocs_*_myid_*.out
rm -f vxc_out coulomb_mat_*.txt coulomb_cut_*.txt Cs_data_*.txt Cs_LRI*.txt

cp -f KPT_scf KPT
cp -f INPUT_scf INPUT
run_and_log "abacus.${JOB_TAG}.out" "$MPI_LAUNCHER" -ppn 1 -np "$ABACUS_MPI" "$ABACUS_EXEC"

if [[ ! -f OUT.ABACUS/vxc_out.dat ]]; then
    echo "Missing OUT.ABACUS/vxc_out.dat after SCF" >&2
    exit 1
fi
cp -f OUT.ABACUS/vxc_out.dat vxc_out

if ! compgen -G 'coulomb_mat_*.txt' >/dev/null; then
    echo "Missing coulomb_mat_*.txt after SCF; LibRPA molecular GW input is incomplete" >&2
    exit 1
fi

run_and_log "LibRPA.${JOB_TAG}.out" "$MPI_LAUNCHER" -ppn 1 -np "$LIBRPA_MPI" "$LIBRPA_EXEC"

echo End Time: "$(date)"
