#!/bin/bash
#SBATCH -p 9242
#SBATCH -N 18
#SBATCH --ntasks-per-node=2
#SBATCH --cpus-per-task=48
#SBATCH -J C1024_librpa36_18n
#SBATCH --mem=380000

set -euo pipefail

module load cmake/3.31.7
module load oneapi/2024.2
export CC=mpiicx
export CXX=mpiicpx
export FC=mpiifx

CASE_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
LIBRPA_EXEC="${LIBRPA_EXEC:-<redacted-user-path>"
MPI_LAUNCHER="${MPI_LAUNCHER:-<redacted-app-path>"
LIBRPA_MPI="${LIBRPA_MPI:-36}"
RANKS_PER_NODE="${RANKS_PER_NODE:-2}"
JOB_TAG="${JOB_ID:-manual}"

cd "$CASE_DIR"

ONEAPI_LD_LIBRARY_PATH="<redacted-user-path>"
export LD_LIBRARY_PATH="$ONEAPI_LD_LIBRARY_PATH"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-48}"
export MKL_NUM_THREADS=1
export MKL_DYNAMIC=FALSE
export OMP_MAX_ACTIVE_LEVELS=1
export OMP_PLACES=cores
export OMP_PROC_BIND=close
export I_MPI_FABRICS=shm:ofi
export I_MPI_PIN=1
export I_MPI_PIN_DOMAIN=omp
ulimit -s unlimited
unset LD_PRELOAD

echo Begin Time: "$(date)"
echo Working directory is "$PWD"
echo This job runs on the following nodes:
echo "${SLURM_JOB_NODELIST:-local}"
echo This job has allocated "${SLURM_JOB_CPUS_PER_NODE:-unknown}" cpu cores.
echo ntasks per node: "${SLURM_NTASKS_PER_NODE:-unknown}"
echo cpus per task: "${SLURM_CPUS_PER_TASK:-unknown}", OMP_NUM_THREADS: "$OMP_NUM_THREADS"
echo LIBRPA_EXEC="$LIBRPA_EXEC"
echo MPI_LAUNCHER="$MPI_LAUNCHER"
echo LIBRPA_MPI="$LIBRPA_MPI"
echo RANKS_PER_NODE="$RANKS_PER_NODE"

for required in librpa.in vxc_out; do
    if [[ ! -s "$required" ]]; then
        echo "Missing required LibRPA input: $required" >&2
        exit 1
    fi
done
if ! compgen -G "KS_eigenvector*" >/dev/null; then
    echo "Missing KS_eigenvector* files; cannot run LibRPA" >&2
    exit 1
fi
if ! compgen -G 'coulomb_mat_*.txt' >/dev/null; then
    echo "Missing coulomb_mat_*.txt; cannot run LibRPA" >&2
    exit 1
fi
if ! compgen -G 'Cs_data_*.txt' >/dev/null; then
    echo "Missing Cs_data_*.txt; cannot run LibRPA" >&2
    exit 1
fi
if [[ -f OUT.ABACUS/vxc_out.dat ]]; then
    cp -f OUT.ABACUS/vxc_out.dat vxc_out
fi

if [[ -d librpa.d ]]; then
    mv librpa.d "librpa.d.before_librpa36.${JOB_TAG}"
fi
rm -f "LibRPA.${JOB_TAG}.out" librpa_para_nprocs_${LIBRPA_MPI}_myid_*.out

"$MPI_LAUNCHER" -ppn "$RANKS_PER_NODE" -np "$LIBRPA_MPI" "$LIBRPA_EXEC" >> "LibRPA.${JOB_TAG}.out" 2>&1

echo End Time: "$(date)"
