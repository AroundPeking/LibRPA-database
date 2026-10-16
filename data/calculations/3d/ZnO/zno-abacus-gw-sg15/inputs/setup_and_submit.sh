#!/bin/bash

set -euo pipefail

HOST=df_iopcas_ghj
REMOTE_PARENT=/HPC/gw/ZnO
REMOTE_ROOT=${REMOTE_PARENT}/sg15_k8_fig2_path_20260802
SOURCE_ROOT=${REMOTE_PARENT}/sg15_k8_sym_shrink_20260730
HERE=$(cd "$(dirname "$0")" && pwd)

ssh "${HOST}" "test ! -e '${REMOTE_ROOT}'"
ssh "${HOST}" "mkdir -p '${REMOTE_PARENT}'"
scp -r "${HERE}" "${HOST}:${REMOTE_PARENT}/"

ssh "${HOST}" bash -s -- "${REMOTE_ROOT}" "${SOURCE_ROOT}" <<'REMOTE'
set -euo pipefail
root=$1
source_root=$2

for name in Zn_ONCV_PBE-1.0.upf O_ONCV_PBE-1.0.upf \
    Zn_gga_10au_100Ry_6s3p3d2f.orb O_gga_8au_100Ry_3s3p2d.orb; do
    test -s "${source_root}/producer_scf/${name}"
    if test -e "${root}/${name}"; then
        cmp -s "${source_root}/producer_scf/${name}" "${root}/${name}"
    else
        ln -s "${source_root}/producer_scf/${name}" "${root}/${name}"
    fi
done
for name in STRU Zn_6s3p3d2f1g_pca1e-6.abfs O_3s3p2d1f1g_pca1e-6.abfs; do
    test -s "${root}/${name}"
done
test ! -e "${root}/OUT.ABACUS"
test ! -e "${root}/input_librpa"
sha256sum "${root}"/INPUT "${root}"/KPT "${root}"/STRU \
    "${root}"/*.abfs "${root}"/librpa/librpa.in \
    > "${root}/staged_input_sha256.txt"
REMOTE

band_job=$(ssh "${HOST}" "cd '${REMOTE_ROOT}' && sbatch --parsable run_abacus.sh")
gw_job=$(ssh "${HOST}" "cd '${REMOTE_ROOT}/librpa' && sbatch --parsable --dependency=afterok:${band_job} run_librpa.slurm")

printf 'band_nscf=%s\ngw=%s\n' "${band_job}" "${gw_job}" \
    | tee "${HERE}/submitted_jobs.txt"
scp "${HERE}/submitted_jobs.txt" "${HOST}:${REMOTE_ROOT}/submitted_jobs.txt"
