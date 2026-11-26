#!/usr/bin/env python3
"""Render the KS / EXX / G0W0 frontier figures for the new MoS2 14x14x1 run.

Reuses the archived table-material renderer unchanged (same frozen-window rule,
same occupation-separated reordering, same SCF-mesh dots, same colours), so the
new panels are directly comparable with the archived mos2-table-gw record. Only
the data root, the lattice and the mesh change.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path('/HPC/project
NEW = Path('/HPC/project
RAW = NEW / 'band_results'
OUT = NEW / 'figures'

spec = importlib.util.spec_from_file_location('rtm', ROOT / 'tools/render_table_material_bands.py')
rtm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rtm)

# The renderer reads RAW/<filename>; point it at this run's tables instead.
rtm.ROOT = NEW     # read_source records archive_path relative to this
rtm.RAW = RAW
rtm.OUT = OUT
OUT.mkdir(parents=True, exist_ok=True)

CONFIG = {
    'slug': 'mos2_14x14_20261123',
    'label': r'MoS$_2$',
    'status': 'PBE, 14x14x1 mesh, strict 2D Coulomb',
    'sources': {
        'KS': rtm.source('KS_band_spin_1.dat', 'ABACUS 14x14x1 SCF + 121-point path NSCF'),
        'EXX': rtm.source('EXX_band_spin_1.dat', 'LibRPA EXX@PBE on the same path'),
        'GW': rtm.source('GW_band_spin_1.dat', 'LibRPA G0W0@PBE, 2D strict head/wing'),
    },
    # a1 = 3.184 A along x, a2 = (-1.592, 2.7574248856) A; exact hexagonal.
    'lattice': ((3.184, 0.0, 0.0), (-1.592, 2.7574248856, 0.0), (0.0, 0.0, 30.0)),
    'kmesh': (14, 14, 1),
    'endpoints': (0, 40, 80, 120),
    'labels': (r'$\Gamma$', 'K', 'M', r'$\Gamma$'),
    'window_counts': (4, 4),
    'expected_gap': (1.66524, 2.39727),
}

sidecar = rtm.render_case(CONFIG)
print('figures:')
for method, paths in sidecar['figure_outputs'].items():
    print('  %-4s %s' % (method, paths['png']))
print()
print('edges (sampled path):')
for method, info in sidecar['methods'].items():
    print('  %-4s VBM %.5f  CBM %.5f  gap %.5f eV' % (
        method, info['vbm_reference_ev'], info['cbm_reference_ev'], info['path_gap_ev']))
print('  grid dots:', len(sidecar['grid_coincident_rows_one_based']))
(OUT / 'mos2_14x14_bands_sidecar.json').write_text(
    json.dumps(sidecar, indent=2, ensure_ascii=True) + '\n', encoding='ascii')
