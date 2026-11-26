#!/bin/bash
#SBATCH -p amd_m9_768
#SBATCH -N 1
#SBATCH -n 8
#SBATCH --cpus-per-task=8
#SBATCH --mem=120000
#SBATCH -t 12:00:00
#SBATCH -J mos2_30x30
#SBATCH -o dense30-%j.out
# 30x30x1 NSCF on the SCF density. 900 full-BZ k points (symmetry -1), which is
# the dense grid the BSE fine channel needs. The 121-point path case showed the
# wavefunction export dominates, so this only writes what LibRPA reads.
source $HOME/ghj_ml_gw/bin/m9env.sh
export OMP_NUM_THREADS=8
O=/HPC/soft/openmpi/openmpi-4.1.8/install-new
cd $PWD || exit 9
cp ../assets/*.upf ../assets/*.orb ../assets/*.abfs . 2>/dev/null
cp ../scf/STRU .
cp INPUT_dense30 INPUT
cp KPT_30x30 KPT
echo "=== start $(date) ==="
/usr/bin/time -f "WALL=%e MAXRSSKB=%M" $O/bin/mpirun --bind-to none -np $SLURM_NTASKS \
  $HOME/ghj_ml_gw/bin/abacus_std_para.rpacut > abacus_dense30.log 2>&1
echo "rc=$?"
grep -a "nkstot now" OUT.dense30/running_nscf.log 2>/dev/null | head -2
echo "wfk 数: $(ls OUT.dense30 2>/dev/null | grep -c wfk)"
echo "=== end $(date) ==="
