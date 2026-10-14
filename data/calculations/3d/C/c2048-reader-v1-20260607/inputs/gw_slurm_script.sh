#!/bin/bash
#SBATCH -p normal
#SBATCH --exclude=k02r1n01,h06r4n12,h07r4n08,h07r4n10,h10r1n01,h10r1n02,k02r4n10,k02r4n11,k02r4n12,k02r4n13,k02r4n14,k02r4n15,k02r4n16,k02r4n17,k02r4n18,h16r3n08,h16r3n09,i04r2n10,i04r2n11,i04r2n12,i04r2n13,i04r2n14,i04r2n15,i04r2n16,i04r2n17,i04r3n06,i05r2n01,i05r2n10,j01r2n19,j02r3n02,j02r3n03,k02r2n04,k02r2n10,k02r3n05,k02r3n12,k02r3n13,k02r3n14,k02r3n15,k02r3n16,k03r4n07,k03r4n08,k03r4n09,k03r4n10,k03r4n11,k03r4n12,k03r4n13,k03r4n16,k03r4n17,k03r4n18,k03r4n19,i04r2n04,i04r2n05,i04r2n06,i04r2n07,i04r2n08,i06r4n01,j02r3n04,j02r3n05,j02r3n06,j02r3n07,j02r3n09,k01r4n03,k01r4n07,k01r4n08,k01r4n09,k01r4n10,k01r4n11,k02r3n01,k02r3n02,k02r3n17,k02r3n18,i11r1n00,i11r1n01,i06r4n02,i06r4n03,i06r4n04,i06r4n05,i10r4n19,h12r3n14,h12r4n04,k02r4n00,k02r4n01,k02r4n02,k02r1n06,k02r1n07,k02r1n08,k02r1n09,k02r1n18,j01r2n04,j01r2n05,j01r2n06,j01r2n07,j01r2n08,j01r2n09,k03r3n14,k03r3n18,k03r3n19,k03r4n00,k03r4n01,k03r4n02,k03r4n03,j02r4n09,k01r3n03,k01r3n02,i06r4n11,i06r4n12,i06r4n13,i06r4n14,i06r4n15,i04r3n03,h12r2n13,h16r1n14,h16r1n15,i04r4n14,h12r3n08,h16r3n00,j02r3n19,k02r2n11,k02r1n02,h09r4n13,h09r4n14,h10r1n04,f13r1n09  # exclude 107 nodes with < 110 GB initial memory
##SBATCH --nodelist gpu007
#SBATCH -J hip2048
##SBATCH -A xgren
#SBATCH --nodes=256
#SBATCH --gres=dcu:4
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=30
#SBATCH --output=./log_C_hip
#SBATCH --error=./err_C_hip
## --gres-flags=disable-binding
ulimit -s unlimited
ulimit -c unlimited

unset CPATH
module purge

export LD_LIBRARY_PATH=/opt/gridview/slurm/lib:/opt/gridview/slurm/lib64:/opt/gridview/munge/lib
export LIBRARY_PATH=/opt/gridview/slurm/lib:/opt/gridview/slurm/lib64:/opt/gridview/munge/lib

module load compiler/rocm/dtk/25.04.3
# export CPATH=$ROCM_PATH/include/rocrand:$CPATH
module load compiler/devtoolset/9.3.1
module load mpi/hpcx/2.13.1/gcc-9.3.1-wangxh

TOOL=/public/home/hbchen/app/LibRPA/260212/toolchain
INSTALL_DIR=$TOOL/install
SETUP_DIR=$TOOL/build
source $SETUP_DIR/setup_openblas_extern
source $SETUP_DIR/setup_scalapack_extern
source $SETUP_DIR/setup_cereal_extern

source /public/home/hbchen/app/elpa/260611/setup_elpa
source /public/home/hbchen/app/magma/260311/setup_magma

LibDDLA_PATH=/public/home/hbchen/app/LibDDLA/260603/LibDDLA_install
export CPATH=$LibDDLA_PATH/include:$CPATH
export LIBRARY_PATH=$LibDDLA_PATH/lib:$LIBRARY_PATH
export LD_LIBRARY_PATH=$LibDDLA_PATH/lib:$LD_LIBRARY_PATH

LibRPA_PATH=/public/home/hbchen/app/LibRPA/260531/librpa_hip
export PATH=$LibRPA_PATH/bin:$PATH
export LD_LIBRARY_PATH=$LibRPA_PATH/lib:$LibRPA_PATH/lib64:$LD_LIBRARY_PATH
export LIBRARY_PATH=$LibRPA_PATH/lib:$LibRPA_PATH/lib64:$LIBRARY_PATH

# 移除旧版 hpcx v2.7.4 的路径污染
export LD_LIBRARY_PATH=$(echo $LD_LIBRARY_PATH | tr ":" "\n" | grep -v "hpcx/v2.7.4" | paste -sd:)


echo "========================="
echo 'LD_LIBRARY_PATH:' $LD_LIBRARY_PATH
echo "========================="
echo 'PATH:' $PATH
echo "========================="
echo 'CPATH:' $CPATH
echo "========================="
echo 'C_INCLUDE_PATH:' $C_INCLUDE_PATH
echo "========================="
echo 'LIBRARY_PATH:' $LIBRARY_PATH
echo "========================="
echo 'CPLUS_INCLUDE_PATH:' $CPLUS_INCLUDE_PATH
echo "========================="


# export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
echo Working directory is $PWD
echo This job has allocated $SLURM_JOB_CPUS_PER_NODE cpu cores.
echo This job has allocated $SLURM_NNODES nodes.
echo Job id : $SLURM_JOB_ID
echo Begin Time: `date`
workdir=$(basename `pwd`)
### * * * Running the tasks * * * ###
np=$((SLURM_NTASKS_PER_NODE * SLURM_NNODES))
echo "任务运行节点列表: ${SLURM_NODELIST}"
echo "np: " $np
omp=${SLURM_CPUS_PER_TASK}

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

# mpirun -n $np \
#     --mca pml ob1 \
#     --bind-to hwthread \
#     --map-by slot:PE=$SLURM_CPUS_PER_TASK \
#     -x OMP_PLACES=cores \
#     --report-bindings \
#     $librpa_work 1e-12 > LibRPA_test.out_${np}_hip_elpa_libri

# mpirun -n $np \
#     --mca pml ob1 \
#     --bind-to none \
#     --report-bindings \
#     chi0_main.exe > LibRPA_${np}_hip
# --mca btl ^openib \

mpirun -n $np \
    --bind-to none \
    --report-bindings \
    chi0_main.exe > LibRPA_${np}_hip

echo End Time: `date`
