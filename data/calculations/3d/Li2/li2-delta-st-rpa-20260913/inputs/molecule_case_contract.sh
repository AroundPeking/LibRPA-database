#!/bin/bash
case_id=${1:?case id required}
case "$case_id" in li2_mol|li_atom) ;; *) return 2 ;; esac
source /HPC/sternheimer_tests/molecular_isolated_ri_20260906/case_contract.sh "$case_id"
case "$case_id" in li2_mol) grid=160 ;; li_atom) grid=144 ;; esac
root=/HPC/sternheimer_tests/li_grid_isolated_ri_20260908
producer_job_id=${GRID_PRODUCER_JOB_ID:?validated grid producer required}
test "$producer_job_id" = 3295368
producer=$root/energy_producer/job$producer_job_id/$case_id/g2
/usr/bin/python3 - "$producer" "$ao_sha" "$v_sha" "$basis_sha" "$grid" <<'PY'
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
gate = json.loads((p / 'AO_GATE.json').read_text())
contract = json.loads((p / 'contract.json').read_text())
assert gate['status'] == 'success' and gate['baseline_ao_byte_identical'] is True
assert [gate[k] for k in ('ao_sha', 'v_sha', 'basis_sha')] == sys.argv[2:5]
assert gate['grid'] == contract['grid'] == int(sys.argv[5])
assert contract['level'] == 'g2'
PY
