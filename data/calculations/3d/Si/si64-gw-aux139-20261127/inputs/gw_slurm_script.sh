#!/bin/bash
#SBATCH --job-name=si64_bnd_53
#SBATCH --partition=amd_m9_768
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=256
#SBATCH --mem=690G
#SBATCH --time=12:00:00
#SBATCH --output=opt53.out
W=$HOME/ghj_ml_gw
G=/publicfs10/fs10-share/soft/share-soft/gcc/gcc-14.2.0/install
O=/publicfs10/fs10-share/soft/share-soft/openmpi/openmpi-4.1.8/install-new
M=/publicfs10/fs10-share/soft/share-soft/oneAPI/2024.1.0.596/2024.1
export LD_LIBRARY_PATH=$W/goodlib:$M/lib/intel64:$M/lib:$O/lib:$G/lib64
export PATH=$G/bin:$O/bin:$PATH
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export MKL_NUM_THREADS=$OMP_NUM_THREADS
cd /HPC/ghj_ml_gw/case/si64_gwband_53 || exit 9
rm -rf librpa.d lib.log librpa_para_nprocs_*.out
mkdir -p librpa.d
echo "START $(date) option=53 (3D full head+wing with s-head), 139/atom, 4q, band"
/usr/bin/time -f "WALL=%e MAXRSSKB=%M" \
  $O/bin/mpirun --bind-to none -np 4 $W/build_lrmaster/chi0_main.exe > lib.log 2>err.txt
echo "END $(date) rc=$?"
grep -a "WALL=" err.txt | tail -1
grep -ac "libRPA finished successfully" lib.log
ls -l *_band_spin_1.dat 2>/dev/null
