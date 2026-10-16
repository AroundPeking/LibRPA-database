#!/bin/bash
#SBATCH -p formal-6226R
#SBATCH -N 16
#SBATCH --cpus-per-task=32
#SBATCH --ntasks-per-node=1
#SBATCH -J BiSe_abacus
#SBATCH --mem=256000
##SBATCH --dependency=afterok:528530

#ABACUS_test=~/software/abacus-build/bin/abacus
abacus_work=/HPC/app/abacus/fix_nspin2/abacus-develop/build/abacus
librpa_work=/HPC/app/librpa/ewald_exx/LibRPA/build_fixout/chi0_main.exe
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

echo Begin Time: `date`
echo Working directory is $PWD
echo This job runs on the following nodes:
echo $SLURM_JOB_NODELIST
echo This job has allocated $SLURM_JOB_CPUS_PER_NODE cpu cores.
echo cpus per task: $SLURM_CPUS_PER_TASK, this should be OMP_NUM_THREADS: $OMP_NUM_THREADS

cp KPT_scf KPT
cp INPUT_scf INPUT
mpirun -np 16 $abacus_work >> abacus.${SLURM_JOBID}.out
cp -a OUT.ABACUS/vxc_out.dat vxc_out
sh perform.sh

cp KPT_nscf KPT
cp INPUT_nscf INPUT
mpirun -np 16 $abacus_work >> nscf.${SLURM_JOBID}.out
python preprocess_abacus_for_librpa_band.py

OMP_NUM_THREADS=32 mpirun -np 16 $librpa_work >> LibRPA.${SLURM_JOBID}.out


echo End Time: `date`
