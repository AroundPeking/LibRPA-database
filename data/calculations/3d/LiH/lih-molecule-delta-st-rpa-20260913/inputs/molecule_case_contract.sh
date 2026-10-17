#!/bin/bash
case_id=${1:?case required}
case "$case_id" in n2_mol|n_atom|lih_mol|h_lmax2_atom) ;; *) return 2 ;; esac
source /HPC/sternheimer_tests/molecular_isolated_ri_20260906/case_contract.sh "$case_id"
root=/HPC/sternheimer_tests/paper_molecular_grid_20260913
producer_job_id=3295368
producer=$root/validated_producers/$case_id
case "$case_id" in
  n2_mol|lih_mol) grid=160 ;;
  n_atom) grid=120 ;;
  h_lmax2_atom) grid=144 ;;
esac
/usr/bin/python3 - "$producer" "$ao_sha" "$v_sha" "$basis_sha" "$grid" <<'PY'
import hashlib
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
gate = json.loads((p / 'AO_GATE.json').read_text())
c = json.loads((p / 'contract.json').read_text())
audit = json.loads((p / 'SOURCE_AUDIT.json').read_text())
assert gate['status'] == 'success' and gate['baseline_ao_byte_identical'] is True
assert [gate[k] for k in ('ao_sha', 'v_sha', 'basis_sha')] == sys.argv[2:5]
assert gate['grid'] == c['grid'] == int(sys.argv[5])
assert audit['raw_files_modified'] is False and audit['scf_recomputed'] is False
for name, key in [('contract.json', 'accepted_contract_sha'), ('RESULT_SUMMARY.txt', 'summary_sha'), ('AO_GATE.json', 'ao_gate_sha')]:
    assert hashlib.sha256((p / name).read_bytes()).hexdigest() == audit[key]
PY
