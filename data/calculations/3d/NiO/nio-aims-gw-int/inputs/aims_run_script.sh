#!/bin/bash
#SBATCH -p formal-6226R
#SBATCH -N 9
#SBATCH --cpus-per-task=1
#SBATCH --ntasks-per-node=32
#SBATCH -J NiOaims
#SBATCH --mem=256000

#ABACUS_test=~/software/abacus-build/bin/abacus
aims_work=/HPC/app/FHI-aims/FHIaims/build/aims.241109.scalapack.mpi.x
#aims_work=/mnt/sg001/HPC/ghj/app/FHI-aims/FHIaims/build/
#ABACUS_test=/mnt/sg001/HPC/guanzq/abacus-develop/build/abacus
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

echo Begin Time is `date`
echo Directory is $PWD
echo This job runs on the following nodes:
echo $SLURM_JOB_NODELIST
echo This job has allocated $SLURM_JOB_CPUS_PER_NODE cpu cores.
echo cpus per task: $SLURM_CPUS_PER_TASK, this should be OMP_NUM_THREADS: $OMP_NUM_THREADS

mpirun -np 288 $aims_work >> aims.${SLURM_JOBID}.out

echo End Time is `date`
