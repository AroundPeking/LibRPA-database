#!/bin/bash
#SBATCH -p amd_m9_768
#SBATCH -N 1
#SBATCH -n 8
#SBATCH --cpus-per-task=20
#SBATCH --mem=250000
#SBATCH -t 24:00:00
#SBATCH -J mos2_scf_clean
#SBATCH -o scf-%j.out
# Clean-room SCF for the MoS2 2D GW+BSE case (2026-11-23).
#
# Everything this run produces stays inside its own directory: no shared
# OUT.librpa, no reused eigenvectors, no hand-edited librpa.in. The earlier
# attempts mixed files across directories, which is why several isolation
# tests contradicted each other.
#
# Two settings differ from the first attempt on purpose:
#   symmetry 1     -> only 24 irreducible k points, and LibRPA's native
#                     velocity expands them to the full mesh itself.
#   out_mat_hs2/out_mat_r 1 16
#                  -> the default text precision is 8 significant digits, and
#                     LibRPA's |U^T S U - I| < 1e-6 gate rejects an 88-orbital
#                     basis at 1.1e-6. 16 digits put that residual near 1e-14.
source $HOME/ghj_ml_gw/bin/m9env.sh
export OMP_NUM_THREADS=20
O=/HPC/soft/openmpi/openmpi-4.1.8/install-new
cd $PWD || exit 9
cp ../assets/*.upf ../assets/*.orb ../assets/*.abfs . 2>/dev/null
cp INPUT_scf INPUT
cp KPT_scf KPT
echo "=== start $(date) ==="
echo "--- inputs actually used ---"
grep -E "^(symmetry|out_mat_hs2|out_mat_r|rpa |scf_thr|nbands|rpa_cut)" INPUT
echo "=== abacus ==="
/usr/bin/time -f "WALL=%e MAXRSSKB=%M" \
  $O/bin/mpirun --bind-to none -np $SLURM_NTASKS \
  $HOME/ghj_ml_gw/bin/abacus_std_para.rpacut > abacus_scf.log 2>&1
echo "abacus rc=$?"
grep -aE "SCF IS CONVERGED|FINAL_ETOT_IS" OUT.ABACUS/running_scf.log 2>/dev/null | tail -2
echo "--- precision actually used (must be 16) ---"
grep -aE "^out_hsr|^out_mat_r" OUT.ABACUS/INPUT.info 2>/dev/null
echo "--- k reduction (must be 24) ---"
grep -aE "nkstot now" OUT.ABACUS/running_scf.log 2>/dev/null | head -2
echo "--- CSR precision sample (must be ~16 digits) ---"
grep -a "CSR values" -A1 OUT.ABACUS/sr_nao.csr 2>/dev/null | tail -1 | cut -c1-90
echo "--- reader-v1 export ---"
ls OUT.librpa 2>/dev/null | wc -l
head -2 OUT.librpa/bz_sampling_out 2>/dev/null
du -sh OUT.ABACUS OUT.librpa 2>/dev/null
echo "=== end $(date) ==="
