#!/bin/bash
#SBATCH --job-name=fd8_scr_lr
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=30
#SBATCH --mem=110610M
#SBATCH --time=04:00:00
#SBATCH --output=/HPC/solid-delta-fd8-screening-20260825/logs/librpa-%j.out
#SBATCH --error=/HPC/solid-delta-fd8-screening-20260825/logs/librpa-%j.err

set -euo pipefail
trap 'rc=$?; echo "FD8_SCREEN_LIBRPA_FAILED line=$LINENO command=$BASH_COMMAND rc=$rc" >&2; exit $rc' ERR
source /HPC/app/src/env_60_245_intel2021.sh

stage=/HPC/solid-delta-fd8-screening-20260825
material=${MATERIAL:?missing MATERIAL}
case_tag=${CASE_TAG:?missing CASE_TAG}
grid_n=${GRID_N:?missing GRID_N}
case "$material:$case_tag:$grid_n" in
  sic:sic_a4346_fd8_screen:24) lattice=4.346 ;;
  ge:ge_a5644_fd8_screen:27) lattice=5.644 ;;
  mgo:mgo_a4189_fd8_screen:20) lattice=4.189 ;;
  *) echo "unsupported material/case/grid: $material/$case_tag/$grid_n" >&2; exit 2 ;;
esac

merge_root=/HPC/delta-st-master-merge-20260823
artifact=$(readlink -f "$merge_root/artifacts/librpa-merge-current")
librpa=$artifact/rpa
expected_librpa_commit=6e49b04f1190da2b197fe5c63a10d68b3433af67
expected_librpa_sha=65d7718783deadb176f60f789c5080cbf513ac1ee0c447271fc6eafc7b45c4d3
expected_abacus_commit=192a49e0ff78487480ac8ddd2cc83c196ec0f73d
expected_abacus_sha=86b5232b75f8be8a682ca45fefa6cc799719e42757004611cd091eacf11dfa21
regression=$(readlink -f "$merge_root/physical-regression/c_atom_fd8_nf16/latest")
python=/HPC/.conda/envs/ds092/bin/python
merge_script=$stage/jobs/merge_sternheimer_symmetry_manifests.py
coulomb_audit=$stage/jobs/audit_coulomb_v1_hermiticity.py
response_root=$stage/runs/$material/$case_tag/solid/response
q1=$(readlink -f "$response_root/latest_q1")
headinput=$(readlink -f "$stage/runs/$material/$case_tag/solid/headwing_input/latest")
root=$stage/runs/$material/$case_tag/solid/librpa_qavg
work=$root/job${SLURM_JOBID}

test "$SLURM_JOB_PARTITION" = normal
test "$SLURM_NTASKS" -eq 1
test "$SLURM_CPUS_PER_TASK" -eq 30
test -x "$librpa"
test "$(sha256sum "$librpa" | awk '{print $1}')" = "$expected_librpa_sha"
grep -q "^commit=$expected_librpa_commit$" "$artifact/provenance.txt"
grep -q '^physical_regression=pass$' "$regression/RESULT_SUMMARY.txt"
test -x "$python"
test -s "$merge_script"
test -s "$coulomb_audit"
grep -q '^status=success$' "$headinput/RUN_PROVENANCE.txt"
grep -q '^finite_difference_order=8$' "$headinput/RUN_PROVENANCE.txt"
test -s "$headinput/pyatb_librpa_df/velocity_matrix"
grep -q '^status=success$' "$q1/RUN_PROVENANCE.txt"
grep -q '^finite_difference_order=8$' "$q1/RUN_PROVENANCE.txt"

report=$(find "$q1" -path '*/OUT.*/STERNHEIMER_CHI0.dat' -type f -print -quit)
test -n "$report"
mapfile -t q_reps < <(awk '$1=="sternheimer_canonical_q_indices" {for(i=2;i<=NF;i++) print $i}' "$report")
test "${#q_reps[@]}" -gt 0
test ! -e "$work"
mkdir -p "$work/input" "$root"

run_dirs=()
channels=""
for iq in "${q_reps[@]}"; do
  run_dir=$(readlink -f "$response_root/latest_q${iq}")
  test -d "$run_dir"
  grep -q '^status=success$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^all_converged=yes$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^finite_difference_order=8$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^nfreq=16$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^pca_threshold=1e-6$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^kmesh=4x4x4$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q '^qmesh=4x4x4$' "$run_dir/RUN_PROVENANCE.txt"
  grep -q "^abacus_commit=$expected_abacus_commit$" "$run_dir/RUN_PROVENANCE.txt"
  grep -q "^abacus_sha256=$expected_abacus_sha$" "$run_dir/RUN_PROVENANCE.txt"
  current=$(awk -F= '$1=="abfs_channels" {print $2}' "$run_dir/RUN_PROVENANCE.txt")
  test -n "$current"
  if test -z "$channels"; then channels=$current; else test "$channels" = "$current"; fi
  for name in stru_out bz_sampling_out basis_out basis_wfc_out basis_aux_out; do
    test -s "$run_dir/$name"
    cmp -s "$run_dir/$name" "$q1/$name"
  done
  run_dirs+=("$run_dir")
done

"$python" "$merge_script" --output-dir "$work/input" "${run_dirs[@]}" > "$work/merge.out"
for name in stru_out bz_sampling_out basis_out basis_wfc_out basis_aux_out band_out; do
  test -s "$q1/$name"
  ln -s "$q1/$name" "$work/input/$name"
done
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

expected_nq=$(awk 'NR==2 {print $1}' "$q1/bz_sampling_out")
test "$expected_nq" -gt 0
"$python" "$coulomb_audit" "$q1" --prefix v1_coulomb_full_iq_ > "$work/COULOMB_HERMITICITY.txt"
test "$(tail -n +2 "$work/COULOMB_HERMITICITY.txt" | wc -l)" -eq "$expected_nq"
awk 'NR > 1 && ($4 > 1e-10 || $5 > 1e-10 || $6 > 1e-10) {bad=1} END {exit bad}' "$work/COULOMB_HERMITICITY.txt"
shards_per_iq=$(find "$q1" -maxdepth 1 -type f -name 'v1_coulomb_full_iq_1_rank*.dat' | wc -l)
test "$shards_per_iq" -gt 0
for iq in $(seq 1 "$expected_nq"); do
  shard_count=$(find "$q1" -maxdepth 1 -type f -name "v1_coulomb_full_iq_${iq}_rank*.dat" | wc -l)
  test "$shard_count" -eq "$shards_per_iq"
done
coul_count=0
for source in "$q1"/v1_coulomb_full_iq_*_rank*.dat; do
  test -s "$source"
  suffix=${source##*v1_coulomb_full_iq_}
  ln -s "$source" "$work/input/v1_coulomb_exx2serial_full_iq_${suffix}"
  coul_count=$((coul_count + 1))
done
test "$coul_count" -eq "$((expected_nq * shards_per_iq))"

cat > "$work/librpa.in" <<EOF
task = sternheimer_rpa
input_dir = $work/input/
version_coul_reader = 1
version_lri_reader = 1
prefix_lri_coeff = v1_Cs_data_
nfreq = 16
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
/usr/bin/time -v -o librpa.time mpirun -np 1 -ppn 1 "$librpa" > librpa.out 2>&1
grep -q 'libRPA finished successfully' librpa.out
grep -q 'Head/wing uses the external Sternheimer response frequency grid: nfreq=16' librpa.out
grep -q 'Reading head/wing input from' librpa.out
grep -q 'replace_w_head = true' librpa.out
grep -q 'rpa_headwing_mode = qavg' librpa.out

corr=$(awk '/Total Sternheimer EcRPA:/ {value=$(NF-1)} END {print value}' librpa.out)
reference=$(awk -F: 'index($0,"Etot_without_rpa(Ha)") {value=$2} END {gsub(/ /,"",value); print value}' "$q1/abacus.out")
test -n "$corr"
test -n "$reference"
grid=$(awk '$1=="grid" {print $2 "x" $3 "x" $4; exit}' "$report")
test "$grid" = "${grid_n}x${grid_n}x${grid_n}"
{
  echo status=success
  echo scientific_status=SCREENING_CONSERVATIVE_POINT_NOT_INDEPENDENTLY_CONVERGED
  echo side=solid
  echo material=$material
  echo case_tag=$case_tag
  echo lattice_constant_angstrom=$lattice
  echo ecut_ry=30
  echo explicit_grid=$grid
  echo finite_difference_order=8
  echo kmesh=4x4x4
  echo qmesh=4x4x4
  echo nfreq=16
  echo pca_threshold=1e-6
  echo abfs_channels=$channels
  echo exx_ccp_rmesh_times=2
  echo rpa_ccp_rmesh_times=2
  echo sqrt_coulomb_threshold=1e-5
  echo full_coulomb=yes
  echo q0_included=yes
  echo headwing=yes
  echo headwing_mode=qavg
  echo rpa_headwing_body_start=1
  echo coulomb_irreducible_q_count=$expected_nq
  echo coulomb_shards_per_iq=$shards_per_iq
  echo abacus_commit=$expected_abacus_commit
  echo abacus_sha256=$expected_abacus_sha
  echo librpa_commit=$expected_librpa_commit
  echo librpa_sha256=$expected_librpa_sha
  printf 'reference_ha=%.16e\n' "$reference"
  printf 'ecrpa_ha=%.16e\n' "$corr"
  awk -v e0="$reference" -v ec="$corr" 'BEGIN {printf "rpa_total_ha=%.16e\n",e0+ec}'
  sed -n 's/^[[:space:]]*Elapsed (wall clock) time (h:mm:ss or m:ss):[[:space:]]*/librpa_wall_clock=/p' librpa.time
} > RESULT_SUMMARY.txt
ln -sfn "$work" "$root/latest"
echo "FD8_SCREEN_LIBRPA_OK material=$material work=$work"
