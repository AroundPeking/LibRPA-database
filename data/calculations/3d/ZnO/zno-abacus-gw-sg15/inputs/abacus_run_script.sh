#!/bin/bash
#SBATCH -p 48cp1,48cp2,48cp3
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=190000
#SBATCH --time=06:00:00
#SBATCH -J zno_sg15_k8_fig2_band

set -euo pipefail
module load cmake/3.31.7
module load oneapi/2024.2
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK}"
export MKL_NUM_THREADS=1
ulimit -s unlimited

ABACUS_EXEC=/HPC/app/abacus/abacus-stru-units-20260723/build/abacus_3p.stru-units
EXPECTED_BINARY_SHA=102309d9d93bc0e43bd3bd203d98f113c360f4493b3c66fb2f304ca8d81286c5
SOURCE_ROOT=/HPC/gw/ZnO/sg15_k8_sym_shrink_20260730
PRODUCER=${SOURCE_ROOT}/producer_scf
PYTHON=/HPC/app/miniconda3/envs/pyatb/bin/python

cd "${SLURM_SUBMIT_DIR}"
test "$(sha256sum "${ABACUS_EXEC}" | awk '{print $1}')" = "${EXPECTED_BINARY_SHA}"
grep -q 'Finish Time' "${PRODUCER}/OUT.ABACUS/running_scf.log"
test -s "${PRODUCER}/OUT.ABACUS/ABACUS-CHARGE-DENSITY.restart"
test ! -e OUT.ABACUS
mkdir OUT.ABACUS
ln -s "$(readlink -f "${PRODUCER}/OUT.ABACUS/ABACUS-CHARGE-DENSITY.restart")" \
    OUT.ABACUS/ABACUS-CHARGE-DENSITY.restart
mpirun -np 1 "${ABACUS_EXEC}" > "abacus.${SLURM_JOBID}.out" 2>&1

grep -q 'Finish Time' OUT.ABACUS/running_nscf.log
grep -Eq 'Total[[:space:]]+Time' OUT.ABACUS/running_nscf.log
test -s OUT.ABACUS/vxc_out.dat
"${PYTHON}" preprocess_abacus_for_librpa_band.py
test "$(find . -maxdepth 1 -name 'band_KS_eigenvalue_k_*.txt' | wc -l)" -eq 161
test "$(find . -maxdepth 1 -name 'band_KS_eigenvector_k_*.txt' | wc -l)" -eq 161
test "$(find . -maxdepth 1 -name 'band_vxc_k_*.txt' | wc -l)" -eq 161
test -s band_kpath_info
awk 'NR == 1 { exit !($4 == 161) }' band_kpath_info
{
    echo "end=$(date --iso-8601=seconds)"
    echo "source_mesh=8x8x8"
    echo "reused_producer=${PRODUCER}"
    echo "path=W-L-Lambda-Gamma-Delta-X-Z-W-K"
    echo "band_kpoints=161"
    sha256sum "${ABACUS_EXEC}" INPUT KPT STRU band_kpath_info OUT.ABACUS/vxc_out.dat
} > provenance.txt
