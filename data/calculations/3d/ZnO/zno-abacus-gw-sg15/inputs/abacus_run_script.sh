#!/bin/bash
#SBATCH -p formal-6226R
#SBATCH -N 4
##SBATCH --nodelist=cn399
#SBATCH --cpus-per-task=32
#SBATCH --ntasks-per-node=1
#SBATCH -J ZnO
#SBATCH --mem=256000
##SBATCH --dependency=afterok:528530

#ABACUS_test=~/software/abacus-build/bin/abacus
abacus_work=/HPC/app/abacus/mpi_full_Coul/abacus-develop-enable_soc/build/abacus
librpa_work='/HPC/app/librpa/merge/wing/LibRPA/build/chi0_main.exe'
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

echo Begin Time: `date`
echo Working directory is $PWD
echo This job runs on the following nodes:
echo $SLURM_JOB_NODELIST
echo This job has allocated $SLURM_JOB_CPUS_PER_NODE cpu cores.
echo cpus per task: $SLURM_CPUS_PER_TASK, this should be OMP_NUM_THREADS: $OMP_NUM_THREADS

#cp KPT_scf KPT
#cp INPUT_scf INPUT
#mpirun -np 2 $abacus_work >> abacus.${SLURM_JOBID}.out
cp -a OUT.ABACUS/vxc_out.dat vxc_out
cp OUT.ABACUS/data-rR-sparse.csr OUT.ABACUS/data-pR-sparse_SPIN0.csr
seq 1 512 >> stru_out
awk 'NR==1{v=$2/2; printf "2\n0.000000     0.000000     0.000000  1\n%.6f     %.6f     %.6f  1\n", v, v, v; exit}' stru_out | sed '6r /dev/stdin' stru_out > temp && mv temp stru_out
sh perform.sh

cp KPT_nscf KPT
cp INPUT_nscf INPUT
mpirun -np 1 $abacus_work >> nscf.${SLURM_JOBID}.out
python preprocess_abacus_for_librpa_band.py

OMP_NUM_THREADS=32 mpirun -np 4 $librpa_work >> LibRPA.${SLURM_JOBID}.out


echo End Time: `date`
