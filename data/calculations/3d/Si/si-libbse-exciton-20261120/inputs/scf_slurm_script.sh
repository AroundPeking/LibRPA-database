#!/bin/bash
#SBATCH -p amd_m9_768
#SBATCH -N 1
#SBATCH -n 8
#SBATCH --mem=150000
#SBATCH -t 12:00:00
#SBATCH -J si_bse_scf
#SBATCH -o scf-%j.out

# Stage 1: ABACUS ground state on the SPARSE grid (k7x7x7) plus the complete
# LibRPA interface export.
source $HOME/ghj_ml_gw/bin/m9env.sh
export OMP_NUM_THREADS=3
W=$HOME/ghj_ml_gw/bse_si/si_case
O=/HPC/toolchain
cd $W || exit 9
cp INPUT_scf INPUT
cp KPT_scf KPT
echo "=== start $(date) ==="
/usr/bin/time -f "WALL=%e MAXRSSKB=%M" \
  $O/bin/mpirun --bind-to none -np $SLURM_NTASKS \
  $HOME/ghj_ml_gw/bin/abacus_std_para > abacus_scf.log 2>&1
echo "abacus rc=$?"
grep -aE "SCF IS CONVERGED|FINAL_ETOT_IS" OUT.scf/running_scf.log 2>/dev/null | tail -2

# ---------------------------------------------------------------------------
# Reshape the reader-v1 export into the legacy names LibBSE resolves.
#
#   stru_out / band_out          : ABACUS appends `.txt`
#   Cs_data_N / Cs_shrinked_data_N : reader-v1 prefixes them with `v1_`
#   coulomb_unshrinked_cut_*     : the cut Coulomb only exists as
#                                  `v1_coulomb_cut_iq_<iq>_rank<r>.dat`
#
# The symlinks are name-only: each target keeps its reader-v1 binary payload,
# and the reader sniffs the leading marker to pick the v1 parser.
# ---------------------------------------------------------------------------
python3 - <<'PY'
import os, pathlib, re
d = pathlib.Path("OUT.librpa")
if not d.is_dir():
    raise SystemExit("no OUT.librpa")
made = []

def link(alias, target):
    alias, target = d / alias, d / target
    if target.exists():
        if alias.is_symlink() or alias.exists():
            alias.unlink()
        os.symlink(target.name, alias)
        made.append(alias.name)

link("stru_out", "stru_out.txt")
link("band_out", "band_out.txt")

for name in sorted(os.listdir(d)):
    m = re.match(r"v1_(Cs_(?:shrinked_)?data)_(\d+)\.txt$", name)
    if m:
        link("{}_{}.txt".format(m.group(1), m.group(2)), name)

# The cut Coulomb is NOT symlinked: `out_unshrinked_v 1` makes ABACUS write
# coulomb_unshrinked_cut_* itself, in the large basis LibBSE pairs with
# basis_aux_out.  The v1_coulomb_cut_iq_* files are shrink-basis (334) and would
# be rejected.  Verify that both sides really are the same size below.

# v1_shrink_sinvS_N.txt -> shrink_sinvS_N.txt (LibRPA driver prefix_shrink_sinvS)
for name in sorted(os.listdir(d)):
    m = re.match(r"v1_(shrink_sinvS)_(\d+)\.txt$", name)
    if m:
        link("{}_{}.txt".format(m.group(1), m.group(2)), name)

print("symlinks:", len(made))
PY

cd $W
echo "--- required by LibBSE ---"
for pat in "OUT.librpa/velocity_matrix" "OUT.librpa/basis_aux_out" "OUT.librpa/basis_wfc_out" \
           "OUT.librpa/stru_out" "OUT.librpa/band_out" "OUT.librpa/Cs_data_0.txt" \
           "OUT.librpa/Cs_shrinked_data_0.txt" "OUT.librpa/coulomb_unshrinked_cut_1.txt"; do
  [ -e "$pat" ] && echo "  OK   $(basename $pat)" || echo "  MISS $(basename $pat)"
done
echo "--- basis sizes must agree ---"
echo "  basis_aux_out          : $(head -1 OUT.librpa/basis_aux_out)"
echo "  basis_aux_shrink_out   : $(head -1 OUT.librpa/basis_aux_shrink_out)"
echo "  coulomb_unshrinked Naux: $(head -1 OUT.librpa/coulomb_unshrinked_cut_1.txt 2>/dev/null)"
du -sh OUT.librpa 2>/dev/null
echo "=== end $(date) ==="
sacct -j $JOB_ID -o State,Elapsed,MaxRSS,AllocCPUS -P 2>/dev/null | head -3
