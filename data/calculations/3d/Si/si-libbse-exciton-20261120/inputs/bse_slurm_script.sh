#!/bin/bash
#SBATCH -p amd_m9_768
#SBATCH -N 1
#SBATCH -n 32
# Memory scales with the rank count: LibBSE replicates the Wc/Vs/Cs dataset on
# every rank (distribute_lri is off for `librpa_wc`) while the matrix is split
# across ranks, so sacct peaks at 17.4 GB/rank with 8 ranks but 10.4 GB/rank
# with 32.  Budget ranks x 18 GB: 8 ranks fit in 200 GB, 32 need 600 GB
# (a 32-rank job at 240 GB was OOM-killed 32 min in).
#SBATCH --mem=600000
#SBATCH -t 24:00:00
#SBATCH -J si_bse_bse
#SBATCH -o bse-%j.out

# Stage 4: LibBSE static TDA on the dense grid (14x14x14) with the sparse
# (7x7x7) RI and screening.  bse_use_fine_kgrid 1 selects that split; the
# transition space is 2744 * nocc * nvirt = 2744 * 4 * 4 = 43904.
source $HOME/ghj_ml_gw/bin/m9env.sh
W=$HOME/ghj_ml_gw/bse_si/si_case
O=/HPC/toolchain
SC=/HPC/toolchain
G=/HPC/toolchain
export LD_LIBRARY_PATH=$W/../elpa-openmp/lib:$SC/lib:$O/lib:$G/lib64:${LD_LIBRARY_PATH:-}
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
unset OPAL_PREFIX
cd $W || exit 9
ulimit -s unlimited

# energy_qp_fine: dense-grid QP table, built from the LibRPA band writer.
python3 band_to_energy_qp.py librpa . energy_qp_fine || exit 8

echo "=== start $(date) ==="
/usr/bin/time -f "WALL=%e MAXRSSKB=%M" \
  $O/bin/mpirun --bind-to none -np $SLURM_NTASKS \
  $HOME/ghj_ml_gw/bse_si/build_libbse_omp/LibBSE > libbse.log 2>&1
echo "libbse rc=$?"
echo "=== end $(date) ==="
ls -l libbse.d/ 2>/dev/null | head -12
echo "--- log tail ---"
tail -18 libbse.log 2>/dev/null
sacct -j $JOB_ID -o State,Elapsed,MaxRSS,AllocCPUS -P 2>/dev/null | head -3
