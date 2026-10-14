#!/bin/bash
#SBATCH -J C2048_abacus225_v1_r5
#SBATCH -p normal
#SBATCH -N 225
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=30
#SBATCH --mem=110000
#SBATCH -o slurm-%j.out
#SBATCH -e slurm-%j.err

set -euo pipefail
source /HPC/app/src/env_60_245_intel2021.sh
abacus_work=/HPC/app/src/abacus-v1-commonkeys-old-libri-20260605/build-v1-commonkeys-20260605/abacus_3p
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-30}
export MKL_NUM_THREADS=${OMP_NUM_THREADS}
export MKL_DYNAMIC=FALSE
export OPENBLAS_NUM_THREADS=1
export I_MPI_FABRICS=shm:ofi
export I_MPI_HYDRA_BRANCH_COUNT=0
export I_MPI_ADJUST_REDUCE=3
export I_MPI_ADJUST_BCAST=1
export I_MPI_PIN_DOMAIN=omp
export I_MPI_PIN_CELL=core
export OMP_PROC_BIND=spread
export OMP_PLACES=cores
export ABACUS_MPI=${SLURM_NTASKS:-225}
export RANKS_PER_NODE=${SLURM_NTASKS_PER_NODE:-1}

echo "date_start=$(date)"
echo "pwd=$PWD"
echo "exe=$abacus_work"
echo "nodes=$SLURM_JOB_NODELIST"
echo "cpus=$SLURM_JOB_CPUS_PER_NODE"
echo "ABACUS_MPI=$ABACUS_MPI RANKS_PER_NODE=$RANKS_PER_NODE"
stat -c 'ABACUS stat: %y %s %n' "$abacus_work"
grep -Ei '^(\s*)(exx_ewald_lambda|exx_ccp_rmesh_times|rpa_ccp_rmesh_times|exx_real_number|out_librpa_reader_version|nbands|symmetry|rpa)' INPUT || true
rm -rf OUT.ABACUS
rm -f abacus.${SLURM_JOBID}.out slurm-output-check.${SLURM_JOBID}.txt validate_v1.${SLURM_JOBID}.log
rm -f vxc_out vxc_out.dat band_out stru_out k_path_info basis_out KS_eigenvector_*.dat
rm -f v1_coulomb_full_iq_*.dat v1_coulomb_cut_iq_*.dat v1_Cs_data_*.txt
rm -f coulomb_mat_*.txt coulomb_cut_*.txt Cs_data_*.txt Cs_LRI*.txt
mpirun -ppn "$RANKS_PER_NODE" -np "$ABACUS_MPI" "$abacus_work" > "abacus.${SLURM_JOBID}.out" 2>&1
if [[ -f OUT.ABACUS/vxc_out.dat && ! -f vxc_out ]]; then
  cp -f OUT.ABACUS/vxc_out.dat vxc_out
fi
echo "date_end=$(date)"
find . -maxdepth 1 -type f \( -name 'v1_coulomb_full_iq_*' -o -name 'v1_coulomb_cut_iq_*' -o -name 'v1_Cs_data_*' -o -name 'basis_out' -o -name 'stru_out' -o -name 'band_out' -o -name 'vxc_out' -o -name 'KS_eigenvector_*.dat' \) -printf '%f %s\n' | sort | tee "slurm-output-check.${SLURM_JOBID}.txt"
python3 /HPC/app/src/abacus-v1-commonkeys-old-libri-20260605/tools/validate_librpa_v1_output.py . --coul-prefix v1_coulomb_full_iq_ --coul-prefix v1_coulomb_cut_iq_ --cs-prefix v1_Cs_data_ | tee validate_v1.${SLURM_JOBID}.log
