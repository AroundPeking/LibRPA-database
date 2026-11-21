#!/bin/bash
#SBATCH -p amd_m9_768
#SBATCH -N 1
#SBATCH -n 8
#SBATCH --mem=120000
#SBATCH -t 12:00:00
#SBATCH -J si_bse_nscf
#SBATCH -o nscf-%j.out

# Stage 2: dense-grid (k14x14x14) NSCF states from the sparse SCF charge
# density.  This is the "fine" half of the dual grid: LibBSE keeps the
# RI/screening period at 7x7x7 (bse_use_fine_kgrid 1) and only the KS/QP
# states move to 14x14x14, giving 2744 * 4 * 4 = 43904.
source $HOME/ghj_ml_gw/bin/m9env.sh
export OMP_NUM_THREADS=3
W=$HOME/ghj_ml_gw/bse_si/si_case
O=/HPC/toolchain
cd $W || exit 9
cp INPUT_nscf INPUT
cp KPT_nscf KPT
echo "=== start $(date) ==="
/usr/bin/time -f "WALL=%e MAXRSSKB=%M" \
  $O/bin/mpirun --bind-to none -np $SLURM_NTASKS \
  $HOME/ghj_ml_gw/bin/abacus_std_para > abacus_nscf.log 2>&1
echo "abacus rc=$?"
echo "=== OUT.nscf 产物 ==="
for f in vxc_out.dat KPT.info INPUT.info; do
  [ -e "OUT.nscf/$f" ] && echo "  OK   $f" || echo "  MISS $f"
done
echo "  wfk files: $(ls OUT.nscf/wfk*_nao.txt 2>/dev/null | wc -l)  (expect 2744)"
du -sh OUT.nscf 2>/dev/null
echo "=== end $(date) ==="
sacct -j $JOB_ID -o State,Elapsed,MaxRSS,AllocCPUS -P 2>/dev/null | head -3
