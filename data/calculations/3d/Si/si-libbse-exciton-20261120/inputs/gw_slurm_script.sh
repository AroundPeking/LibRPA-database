#!/bin/bash
#SBATCH -p amd_m9_768
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --cpus-per-task=32
#SBATCH --mem=120000
#SBATCH -t 24:00:00
#SBATCH -J si_bse_gw
#SBATCH -o gw-%j.out

# Stage 3: LibRPA G0W0 that produces everything LibBSE reads.
#
#  * RI and screening stay on the SPARSE grid (7x7x7): OUT.librpa there holds
#    Cs_data_*, coulomb_unshrinked_cut_* and velocity_matrix.
#  * QP energies and the band table are evaluated on the DENSE grid (14x14x14)
#    because preprocess_abacus_for_librpa_band.py wrote band_kpath_info plus the
#    per-k band files into OUT.librpa; the driver picks them up as band data.
#  * output_wc_rf + ifreq_output_wc_end 1 emit the compressed Wc(R) blocks that
#    LibBSE's screened_format librpa_wc consumes.
#
# One MPI rank: the compressed-Wc export path is only validated that way, and
# the remaining cores go to OpenMP instead.
source $HOME/ghj_ml_gw/bin/m9env.sh
W=$HOME/ghj_ml_gw/bse_si/si_case
O=/HPC/toolchain
SC=/HPC/toolchain
G=/HPC/toolchain
export LD_LIBRARY_PATH=$W/../elpa-prefix/lib:$SC/lib:$O/lib:$G/lib64:${LD_LIBRARY_PATH:-}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-32}
export OPENBLAS_NUM_THREADS=1 BLIS_NUM_THREADS=1 MKL_NUM_THREADS=1
unset OPAL_PREFIX
cd $W || exit 9
ulimit -s unlimited

echo "=== start $(date)  OMP_NUM_THREADS=$OMP_NUM_THREADS ==="
/usr/bin/time -f "WALL=%e MAXRSSKB=%M" \
  $O/bin/mpirun --bind-to none -np 1 \
  $HOME/ghj_ml_gw/bse_si/build_librpa/chi0_main.exe > librpa.log 2>&1
echo "librpa rc=$?"
echo "=== end $(date) ==="

echo "--- QP band tables ---"
ls -l GW_band_spin_1.dat KS_band_spin_1.dat EXX_band_spin_1.dat 2>/dev/null
echo "--- Wc(R) blocks ---"
echo "  Wc_Mu_*_ifreq_0.mtx : $(ls librpa.d/Wc_Mu_*_ifreq_0.mtx 2>/dev/null | wc -l)"
echo "--- energy_qp ---"
ls -l librpa.d/energy_qp 2>/dev/null || echo "  MISS"
echo "--- gap line ---"
grep -aE "Gap|gap|Band gap|Egap" librpa.log 2>/dev/null | tail -4
echo "--- log tail ---"
tail -8 librpa.log 2>/dev/null
sacct -j $JOB_ID -o State,Elapsed,MaxRSS,AllocCPUS -P 2>/dev/null | head -3
