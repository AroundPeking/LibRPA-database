#!/bin/bash
#SBATCH -p amd_m9_768
#SBATCH -N 1
#SBATCH -n 1
#SBATCH --cpus-per-task=32
#SBATCH --mem=88000
#SBATCH -t 24:00:00
#SBATCH -J mos2_gw30
#SBATCH -o gw30-%j.out
source $HOME/ghj_ml_gw/bin/m9env.sh
O=/HPC/soft/openmpi/openmpi-4.1.8/install-new
SC=/HPC/soft/scalapack/2.2.0-gcc-14.2
G14=/HPC/soft/gcc/gcc-14.2.0/install
export LD_LIBRARY_PATH=$HOME/ghj_ml_gw/bse_si/elpa-openmp/lib:$SC/lib:$O/lib:$G14/lib64:${LD_LIBRARY_PATH:-}
export OMP_NUM_THREADS=32
export OPENBLAS_NUM_THREADS=1 BLIS_NUM_THREADS=1 MKL_NUM_THREADS=1
unset OPAL_PREFIX
cd $PWD || exit 9
ulimit -s unlimited
echo "=== start $(date) ==="
/usr/bin/time -f "WALL=%e MAXRSSKB=%M" $O/bin/mpirun --bind-to none -np 1 \
  $HOME/ghj_ml_gw/bse_si/build_librpa_native/chi0_main.exe > librpa_30x30.log 2>&1
echo "rc=$?"
grep -aiE "^Error|Localized" librpa_30x30.log | head -3
ls -l GW_band_spin_1.dat 2>/dev/null | awk '{print "  GW_band:", $5, "字节"}'
echo "=== end $(date) ==="
