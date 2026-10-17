#!/usr/bin/env python3
"""Login-node audit; use the complete serial producer V, never response-local V."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--compute', type=Path, required=True)
    parser.add_argument('--v-sha', required=True)
    parser.add_argument('--naux', type=int, required=True)
    parser.add_argument('--nfreq', type=int, required=True)
    parser.add_argument('--nocc', type=int, required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite analysis')
    directory = args.directory
    record = summary(directory / 'RESULT_SUMMARY.txt')
    for key, value in {'status': 'success', 'all_converged': 'yes', 'naux': str(args.naux),
                       'nfreq': str(args.nfreq), 'solved_equations': str(args.naux * args.nfreq * args.nocc),
                       'response_matrices': str(args.nfreq), 'real_failure_marker_count': '0',
                       'common_basis_aux_byte_identical': 'yes',
                       'grid_Q_potential': 'isolated_charge_multipole_tail'}.items():
        if record.get(key) != value:
            raise ValueError('failed response contract: ' + key)
    status_files = list(directory.glob('OUT.*/STERNHEIMER_CHI0.dat'))
    if len(status_files) != 1:
        raise ValueError('missing/ambiguous status')
    fields = dict(line.split(None, 1) for line in status_files[0].read_text().splitlines()
                  if len(line.split(None, 1)) == 2)
    if (float(fields['max_solver_relative_residual']) > 1e-6
            or fields.get('sternheimer_molecular_coulomb') != 'isolated_ri'
            or fields.get('analytic_ao_residual') != 'hybrid_ao_qspace_equations'):
        raise ValueError('solver/method contract mismatch')
    vfile = directory / 'reference/v1_coulomb_full_iq_1_rank0.dat'
    if digest(vfile) != args.v_sha:
        raise ValueError('wrong complete producer V')
    if (directory / 'basis_aux_out').read_bytes() != (directory / 'reference/basis_aux_out').read_bytes():
        raise ValueError('basis metadata mismatch')
    spec = importlib.util.spec_from_file_location('molecular_compute', str(args.compute))
    compute = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compute)
    v = compute.read_coulomb_v1(str(vfile))
    diagonal = np.diag(v['matrix']).real
    if np.any(diagonal <= 0) or not np.isfinite(v['matrix']).all():
        raise ValueError('invalid producer metric')
    scale = diagonal ** -0.5
    v['matrix'] = scale[:, None] * v['matrix'] * scale[None, :]
    paths = sorted(directory.glob('v1_sternheimer_chi0_iq_1_ifreq_*_rank*.dat'))
    data = sorted((compute.read_st_m_v1(str(p)) for p in paths), key=lambda item: item['ifreq'])
    if [r['ifreq'] for r in data] != list(range(1, args.nfreq + 1)):
        raise ValueError('missing or repeated response frequency')
    frequency = [line.split() for line in (directory / 'fixed_frequency_grid.dat').read_text().splitlines()
                 if line.strip() and not line.startswith('#')]
    comparisons = []
    reference_data = []
    for response, expected in zip(data, frequency):
        if response['naux'] != args.naux or not np.isfinite(response['matrix']).all():
            raise ValueError('invalid response matrix')
        if response['omega'] != float(expected[1]) or response['weight'] != float(expected[2]):
            raise ValueError('frequency/weight changed')
        if args.reference:
            candidates = list(args.reference.glob('v1_sternheimer_chi0_iq_1_ifreq_{}_rank*.dat'.format(response['ifreq'])))
            if len(candidates) != 1:
                raise ValueError('missing/ambiguous endpoint reference')
            ref = compute.read_st_m_v1(str(candidates[0]))
            for key in ('ifreq', 'iq', 'naux', 'atom_naux', 'omega', 'weight'):
                if ref[key] != response[key]:
                    raise ValueError('reference metadata mismatch: ' + key)
            difference = response['matrix'] - ref['matrix']
            comparisons.append({'ifreq': response['ifreq'], 'reference_sha256': digest(candidates[0]),
                                'relative_frobenius': float(np.linalg.norm(difference) / np.linalg.norm(ref['matrix'])),
                                'max_abs': float(np.max(np.abs(difference)))})
            ref['matrix'] = scale[:, None] * ref['matrix'] * scale[None, :]
            reference_data.append(ref)
        response['matrix'] = scale[:, None] * response['matrix'] * scale[None, :]
    if len(frequency) != args.nfreq:
        raise ValueError('wrong frequency file length')
    prod = summary(directory / 'reference/PRODUCER_RESULT_SUMMARY.txt')
    e0 = float(prod['pbe_total_eV']) / 27.211386245988 - float(prod['pbe_xc_Ha']) + float(prod['ri_exx_Ha'])
    result = {'directory': str(directory), 'summary': record, 'E0_Ha': e0,
              'congruence': 'same diagonal on-site unit-Coulomb scaling on V and B',
              'unscaled_V_diagonal_min_max': [float(diagonal.min()), float(diagonal.max())],
              'producer_v_sha256': digest(vfile), 'compute_sha256': digest(args.compute),
              'analyzer_sha256': digest(Path(__file__)),
              'matrix_sha256': {p.name: digest(p) for p in paths},
              'endpoint_matrix_comparison': comparisons, 'energies': {}}
    for threshold in (1e-4, 1e-5, 1e-6, 0.0):
        rows = [compute.compute_single_frequency_energy(v, r, threshold) for r in data]
        ec = sum(r['energy_ha'] for r in rows)
        if not math.isfinite(ec) or ec >= 0:
            raise ValueError('nonphysical/nonfinite Ec')
        if threshold == 1e-4 and max(r['lambda_max'] for r in rows) > 1e-6:
            raise ValueError('positive primary response mode')
        values = {'Ec_Ha': ec, 'E_RPA_Ha': e0 + ec, 'frequency_results': rows}
        if reference_data:
            old = sum(compute.compute_single_frequency_energy(v, r, threshold)['energy_ha'] for r in reference_data)
            values['difference_from_endpoint_Ec_Ha'] = ec - old
            values['difference_from_endpoint_Ec_kcal_mol'] = (ec - old) * 627.5094740631
        result['energies'][str(threshold)] = values
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({k: {name: val for name, val in v.items() if name != 'frequency_results'}
                      for k, v in result['energies'].items()}, indent=2))


if __name__ == '__main__':
    main()
