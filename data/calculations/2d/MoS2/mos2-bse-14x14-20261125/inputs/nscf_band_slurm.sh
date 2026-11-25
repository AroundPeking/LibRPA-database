#!/bin/bash
#SBATCH -p amd_m9_768
#SBATCH -N 1
#SBATCH -n 4
#SBATCH --cpus-per-task=8
#SBATCH --mem=64000
#SBATCH -t 8:00:00
#SBATCH -J mos2_band
#SBATCH -o band-%j.out
# Band-path NSCF on Gamma-K-M-Gamma (121 points) for the database figures.
# Reads the converged density from ../scf/OUT.ABACUS.
source $HOME/ghj_ml_gw/bin/m9env.sh
export OMP_NUM_THREADS=8
O=/HPC/soft/openmpi/openmpi-4.1.8/install-new
cd $PWD || exit 9
cp ../assets/*.upf ../assets/*.orb ../assets/*.abfs ../scf/STRU . 2>/dev/null
cp INPUT_band INPUT
cp KPT_band KPT
echo "=== start $(date) ==="
/usr/bin/time -f "WALL=%e MAXRSSKB=%M" $O/bin/mpirun --bind-to none -np $SLURM_NTASKS \
  $HOME/ghj_ml_gw/bin/abacus_std_para.rpacut > abacus_band.log 2>&1
echo "rc=$?"
grep -aE "nkstot now" OUT.band/running_nscf.log 2>/dev/null | head -2
ls OUT.band/ 2>/dev/null | grep -c "wfk"
echo "=== end $(date) ==="
