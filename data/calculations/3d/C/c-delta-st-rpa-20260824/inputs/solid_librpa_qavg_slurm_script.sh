#!/bin/bash
#SBATCH --job-name=c8_grid_lr
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=30
#SBATCH --mem=110610M
#SBATCH --time=04:00:00
#SBATCH --output=/HPC/c-solid-grid-fd8-final-20260823/logs/librpa-%j.out
#SBATCH --error=/HPC/c-solid-grid-fd8-final-20260823/logs/librpa-%j.err

set -euo pipefail
trap 'status=$?; echo "C_GRID_LIBRPA_FAILED line=$LINENO command=$BASH_COMMAND status=$status" >&2; exit $status' ERR
source /HPC/app/src/env_60_245_intel2021.sh

stage=/HPC/c-solid-grid-fd8-final-20260823
python_exe=/HPC/.conda/envs/ds092/bin/python
merge_script=$stage/jobs/merge_sternheimer_symmetry_manifests.py
librpa_artifact=$stage/artifacts/librpa-headwing-998eeb9c
librpa_exe=$librpa_artifact/rpa
expected_librpa_sha=6023c1b28df9fa3d24bbd55cd71ed0bd7731e474f67e3e8dc7e7de4300535436
expected_librpa_commit=998eeb9c6191ff0c2731622fcc4a5c9d5a2e53c8
expected_abacus_commit=e5ef955dbc5b06f59a9d335348cb05634cd9d1d3
expected_abacus_sha=c1eb5003b374f97980ef1423260cfbb483f95b17ee290681182e640bdfa7a8b1
ecut=${ECUT:-45}
grid_n=${GRID_N:?missing GRID_N}
test "$ecut" -eq 45
case "$grid_n" in 15|20|24|30) ;; *) echo "unsupported GRID_N=$grid_n" >&2; exit 2;; esac

case_tag=g${grid_n}_fd8
response_root=$stage/runs/${case_tag}/solid/response
metric_dir=$(readlink -f "$stage/runs/${case_tag}/solid/metric/latest_q1")
headinput=$(readlink -f "$stage/runs/${case_tag}/solid/headwing_input/latest")
q1=$(readlink -f "$response_root/latest_q1")
root=$stage/runs/${case_tag}/solid/librpa_qavg
work=$root/job${SLURM_JOBID}
fingerprint=$(readlink -f "$stage/grid_fingerprints/latest_g${grid_n}")

test "$SLURM_JOB_PARTITION" = normal
test "$SLURM_NTASKS" -eq 1
test "$SLURM_CPUS_PER_TASK" -eq 30
test -x "$librpa_exe"
test "$(sha256sum "$librpa_exe" | awk '{print $1}')" = "$expected_librpa_sha"
grep -q "^librpa_git_head=$expected_librpa_commit$" "$librpa_artifact/provenance.txt"
test -x "$python_exe"
test -s "$merge_script"
test -d "$metric_dir"
grep -q '^status=success$' "$metric_dir/RUN_PROVENANCE.txt"
grep -q '^coulomb_metric_complete=yes$' "$metric_dir/RUN_PROVENANCE.txt"
grep -q "^ecut_ry=$ecut$" "$metric_dir/RUN_PROVENANCE.txt"
grep -q '^finite_difference_order=8$' "$metric_dir/RUN_PROVENANCE.txt"
test -d "$headinput"
grep -q '^status=success$' "$headinput/RUN_PROVENANCE.txt"
grep -q "^ecut_ry=$ecut$" "$headinput/RUN_PROVENANCE.txt"
grep -q '^finite_difference_order=8$' "$headinput/RUN_PROVENANCE.txt"
test -s "$headinput/pyatb_librpa_df/velocity_matrix"
test -d "$q1"
grep -q '^status=success$' "$q1/RUN_PROVENANCE.txt"
grep -q "^ecut_ry=$ecut$" "$q1/RUN_PROVENANCE.txt"
grep -q '^finite_difference_order=8$' "$q1/RUN_PROVENANCE.txt"

report=$(find "$q1" -path '*/OUT.*/STERNHEIMER_CHI0.dat' -type f -print -quit)
test -n "$report"
mapfile -t q_representatives < <(awk '$1=="sternheimer_canonical_q_indices" {for(i=2;i<=NF;i++) print $i}' "$report")
test "${#q_representatives[@]}" -gt 0
test ! -e "$work"
mkdir -p "$work/input" "$root"

run_dirs=()
channels=""
for iq in "${q_representatives[@]}"; do
  run_dir=$(readlink -f "$response_root/latest_q${iq}")
  test -d "$run_dir"
  grep -q '^status=success$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^abacus_complete=yes$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^nfreq=12$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^kmesh=4x4x4$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^pca_threshold=1e-6$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q "^ecut_ry=$ecut$" "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^finite_difference_order=8$' "$run_dir/RUN_PROVENANCE.txt"
  current=$(awk -F= '$1=="abfs_channels" {print $2}' "$run_dir/RUN_PROVENANCE.txt")
  test -n "$current"
  if test -z "$channels"; then channels=$current; else test "$channels" = "$current"; fi
  run_dirs+=("$run_dir")
done

"$python_exe" "$merge_script" --output-dir "$work/input" "${run_dirs[@]}" > "$work/merge.out"
for name in stru_out bz_sampling_out basis_out basis_wfc_out basis_aux_out; do
  test -s "$q1/$name"
  test -s "$metric_dir/$name"
  cmp -s "$q1/$name" "$metric_dir/$name"
  ln -s "$q1/$name" "$work/input/$name"
done
test -s "$q1/band_out"
ln -s "$q1/band_out" "$work/input/band_out"

eig_count=0
for source in "$q1"/KS_eigenvector_*.dat; do
  test -s "$source"
  ln -s "$source" "$work/input/${source##*/}"
  eig_count=$((eig_count + 1))
done
test "$eig_count" -gt 0

cs_count=0
for source in "$q1"/v1_Cs_data_*.txt; do
  test -s "$source"
  ln -s "$source" "$work/input/${source##*/}"
  cs_count=$((cs_count + 1))
done
test "$cs_count" -gt 0
ln -s "$headinput/pyatb_librpa_df" "$work/input/pyatb_librpa_df"

coul_count=0
for source in "$metric_dir"/v1_coulomb_full_iq_*_rank*.dat; do
  test -s "$source"
  suffix=${source##*v1_coulomb_full_iq_}
  ln -s "$source" "$work/input/v1_coulomb_exx2serial_full_iq_${suffix}"
  coul_count=$((coul_count + 1))
done
test "$coul_count" -gt 0

cat > "$work/librpa.in" <<EOF
task = sternheimer_rpa
input_dir = $work/input/
version_coul_reader = 1
version_lri_reader = 1
prefix_lri_coeff = v1_Cs_data_
nfreq = 12
sqrt_coulomb_threshold = 1e-5
prefix_coul_full = v1_coulomb_exx2serial_full_iq_
fn_sternheimer_qpoints = v1_sternheimer_qpoints.dat
fn_sternheimer_partial_manifest = v1_sternheimer_partial_manifest.dat
fn_sternheimer_symmetry_routes = v1_sternheimer_symmetry_routes.dat
fn_sternheimer_qstar_routes = v1_sternheimer_qstar_routes.dat
use_rpa_gamma = true
replace_w_head = true
option_dielect_func = 3
rpa_headwing_mode = qavg
rpa_headwing_body_start = 1
parallel_routing = libri
use_symmetry_rpa = true
use_kpara_scf_eigvec = true
EOF

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK MKL_NUM_THREADS=$SLURM_CPUS_PER_TASK OPENBLAS_NUM_THREADS=1
export OMP_DYNAMIC=FALSE OMP_PROC_BIND=spread OMP_PLACES=cores MKL_DYNAMIC=FALSE
cd "$work"
/usr/bin/time -v -o librpa.time mpirun -np 1 -ppn 1 "$librpa_exe" > librpa.out 2>&1
grep -q 'libRPA finished successfully' librpa.out
grep -q 'Reading head/wing input from' librpa.out
grep -q 'replace_w_head = true' librpa.out
grep -q 'rpa_headwing_mode = qavg' librpa.out

corr=$(awk '/Total Sternheimer EcRPA:/ {value=$(NF-1)} END {print value}' librpa.out)
reference=$(awk -F: 'index($0,"Etot_without_rpa(Ha)") {value=$2} END {gsub(/ /,"",value); print value}' "$metric_dir/abacus.out")
metric_channels=$(awk 'NR==1 {print $2}' "$metric_dir/basis_aux_out")
test -n "$corr"
test -n "$reference"
test "$channels" = "$metric_channels"
grid=$(awk '$1=="grid" {print $2","$3","$4; exit}' "$report")
n_grid=$(awk '$1=="grid" {print $6; exit}' "$report")
dvol=$(awk '$1=="grid" {print $8; exit}' "$report")
test "$grid" = "$(awk -F= '$1=="charge_grid" {print $2}' "$fingerprint/GRID_FINGERPRINT.txt")"

"$python_exe" - "$ecut" "$grid_n" "$channels" "$grid" "$n_grid" "$dvol" "$reference" "$corr" <<'PY' | tee GRID_RESULT_SUMMARY.txt
import sys
ecut, explicit_grid_n, channels = map(int, sys.argv[1:4])
grid, ngrid, dvol = sys.argv[4], int(sys.argv[5]), float(sys.argv[6])
e0, ec = map(float, sys.argv[7:9])
print("status=success")
print("side=solid")
print("material=diamond_c")
print("lattice_constant_angstrom=3.57")
print(f"ecut_ry={ecut}")
print(f"explicit_grid_n={explicit_grid_n}")
print("finite_difference_order=8")
print("kmesh=4x4x4")
print("qmesh=4x4x4")
print("nfreq=12")
print("pca_threshold=1e-6")
print(f"abfs_channels={channels}")
print("exx_ccp_rmesh_times=2")
print("rpa_ccp_rmesh_times=2")
print("sqrt_coulomb_threshold=1e-5")
print("full_coulomb=yes")
print("q0_included=yes")
print("headwing=yes")
print("headwing_mode=qavg")
print("rpa_headwing_body_start=1")
print(f"grid={grid}")
print(f"n_grid={ngrid}")
print(f"dvol_bohr3={dvol:.16e}")
print("abacus_commit=e5ef955dbc5b06f59a9d335348cb05634cd9d1d3")
print("abacus_sha256=c1eb5003b374f97980ef1423260cfbb483f95b17ee290681182e640bdfa7a8b1")
print("librpa_commit=998eeb9c6191ff0c2731622fcc4a5c9d5a2e53c8")
print("librpa_sha256=6023c1b28df9fa3d24bbd55cd71ed0bd7731e474f67e3e8dc7e7de4300535436")
print(f"reference_ha={e0:.16e}")
print(f"ecrpa_ha={ec:.16e}")
print(f"rpa_total_ha={e0+ec:.16e}")
PY
ln -sfn "$work" "$root/latest"
echo "C_GRID_FD8_LIBRPA_OK ecut=$ecut grid_n=$grid_n grid=$grid ngrid=$n_grid work=$work"
