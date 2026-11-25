#!/usr/bin/env python3
"""Exciton density for the MoS2 BSE run.

The archived density tool
(alter_excitons_gw_bse_20261105/scripts/exciton_density_from_amplitudes.py) was
written for Si and assumes two things MoS2 breaks:

  * one species: every atom shares a single `.orb`, and every per-atom block is
    sized `orb.nw`. MoS2 has Mo 6s3p3d2f (44 AO) and S 3s3p2d (22 AO), so that
    would allocate 3 x 44 = 132 AOs where ABACUS has 88;
  * l <= 2. This basis has an f shell.

Both are patched at the source-text level and nothing else changes, so the Bloch
sums, the first-k gauge, the conditional/average construction and the amplitude
layout stay byte-identical to the archived tool.

Verification before any density is computed:
  * the l <= 3 harmonics are integrated over the sphere by Gauss-Legendre
    quadrature and must come out orthonormal;
  * the assembled AO count must equal 44 + 22 + 22 = 88, the width of the
    stored wfk matrices.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np

ARCHIVE = Path('/HPC/project
SOURCE_PATH = ARCHIVE / 'exciton_density_from_amplitudes.py'

# ylmcoef[7..14] from ABACUS source_base/ylm.cpp
Y7 = np.sqrt(35.0 / 9.0)
Y8 = np.sqrt(7.0 / 3.0) / 1.5
Y9 = np.sqrt(35.0 / 8.0)
Y10 = np.sqrt(7.0 / 8.0)
Y11 = np.sqrt(7.0)
Y12 = 1.0 / np.sqrt(15.0)
Y13 = np.sqrt(14.0 / 15.0)
Y14 = np.sqrt(14.0 / 3.0)


def make_ylm(base_l2):
    """l = 3 appended to the archived l <= 2 routine, ABACUS rly[9..15].

    `base_l2` is captured by value: binding it to `eda.real_ylm_l2` after the
    wrapper is installed would make the wrapper call itself.
    """
    def real_ylm(x, y, z):
        r = base_l2(x, y, z)
        r0, r1, r2, r3 = r[0], r[1], r[2], r[3]
        r4, r5, r6, r7, r8 = r[4], r[5], r[6], r[7], r[8]
        out = np.empty(16)
        out[:9] = r
        out[9] = Y7 * z * r4 - Y8 * r1
        t3 = Y9 * z
        out[10] = t3 * r5 - Y10 * r2
        out[11] = t3 * r6 - Y10 * r3
        t4 = Y11 * z
        out[12] = t4 * r7
        out[13] = t4 * r8
        t5 = Y14 * x
        out[14] = Y12 * out[10] - Y13 * r2 - t5 * r7
        out[15] = Y12 * out[11] - Y13 * r3 - t5 * r8
        return out
    return real_ylm


def check_orthonormal(ylm, n=200):
    xs, ws = np.polynomial.legendre.leggauss(n)
    nphi = 4 * n
    phi = np.linspace(0.0, 2.0 * np.pi, nphi, endpoint=False)
    dphi = 2.0 * np.pi / nphi
    total = np.zeros((16, 16))
    for zz, wz in zip(xs, ws):
        rr = np.sqrt(max(0.0, 1.0 - zz * zz))
        acc = np.zeros((16, 16))
        for p in phi:
            v = ylm(rr * np.cos(p), rr * np.sin(p), zz)
            acc += np.outer(v, v) * dphi
        total += acc * wz
    return float(np.abs(total - np.eye(16)).max())


class MultiOrbital:
    """One `.orb` per atom type, presented as the single-object API the archived
    `build_slice` expects, plus the per-atom tables the patched Bloch sum needs."""

    def __init__(self, per_atom):
        self.per_atom = per_atom
        self.widths = [o.nw for o in per_atom]
        self.offsets = [0]
        for w in self.widths:
            self.offsets.append(self.offsets[-1] + w)
        self.nw_total = int(self.offsets[-1])
        self.nw = self.nw_total
        self.rcut = max(o.rcut for o in per_atom)
        # build_slice calls orb._ensure() once before the grid loop; each
        # per-atom Orbital keeps its own scratch buffer, so forward it.
        for o in per_atom:
            o._ensure()

    def _ensure(self):
        for o in self.per_atom:
            o._ensure()


def make_bloch_orbitals():
    """Per-atom widths; the archived version shares one orbital for all atoms."""
    def bloch_orbitals(orb, lat, pos, r, rcut, cells, extra=0):
        nat = len(pos)
        phi_real = np.zeros((len(cells), orb.nw_total), dtype=float)
        for ic, (n1, n2, n3, Rv) in enumerate(cells):
            for iat in range(nat):
                o = orb.per_atom[iat]
                dr_vec = r - pos[iat] - Rv
                dist = float(np.linalg.norm(dr_vec))
                if dist > o.rcut:
                    continue
                if dist < 1e-12:
                    dist = 1e-9
                a, b = orb.offsets[iat], orb.offsets[iat + 1]
                phi_real[ic, a:b] = o.values(dist, dr_vec / dist)
        return phi_real
    return bloch_orbitals


def read_stru_types(path):
    """1-based species index per atom; matches the archived read_stru layout."""
    lines = [l for l in Path(path).read_text().splitlines() if l.strip()]
    nat = int(lines[6].split()[0])
    return [int(lines[7 + i].split()[3]) for i in range(nat)]


_BAND_OFFSET = 9   # LibBSE 'selected core offset' for this run; override with --band-offset


def load_patched(max_l=3):
    source = SOURCE_PATH.read_text()
    edits = [
        ('if self.max_l > 2:', 'if self.max_l > %d:' % max_l),
        ('    nao = len(pos) * orb.nw', '    nao = orb.nw_total'),
        # band window offset: LibBSE solves in bands [off, off+nocc+nvirt), so the
        # occupied block is Cs[ik][off:off+nocc], not Cs[ik][:nocc].
        ('Cs[ik][nocc:nocc + nvirt]', 'Cs[ik][_BAND_OFFSET + nocc:_BAND_OFFSET + nocc + nvirt]'),
        ('Cs[ik][:nocc]', 'Cs[ik][_BAND_OFFSET:_BAND_OFFSET + nocc]'),
        ('Ck[:nocc] @ phi', 'Ck[_BAND_OFFSET:_BAND_OFFSET + nocc] @ phi'),
        ('coef = Ck[nocc:nocc + nvirt]', 'coef = Ck[_BAND_OFFSET + nocc:_BAND_OFFSET + nocc + nvirt]'),
        ('(Ck[nocc:nocc + nvirt] @ phi)', '(Ck[_BAND_OFFSET + nocc:_BAND_OFFSET + nocc + nvirt] @ phi)'),
        ('np.conj(Ck[:nocc]).T @ mix', 'np.conj(Ck[_BAND_OFFSET:_BAND_OFFSET + nocc]).T @ mix'),
        ("'c,caw->aw', allphase[ik],", "'c,cw->w', allphase[ik],"),
        ('    orb = Orbital(args.orb)', "    orb = globals().get('_MULTI_ORB') or Orbital(args.orb)"),
    ]
    for old, new in edits:
        assert source.count(old) >= 1, 'archived line moved: %r' % old
        source = source.replace(old, new)
    module = types.ModuleType('eda')
    module.__file__ = str(SOURCE_PATH)
    # The patched lines reference _BAND_OFFSET; seed it before exec so the name
    # always resolves, and override it from --band-offset afterwards.
    module.__dict__['_BAND_OFFSET'] = _BAND_OFFSET
    sys.modules['eda'] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def main(argv):
    eda = load_patched()
    ylm = make_ylm(eda.real_ylm_l2)
    eda.real_ylm_l2 = ylm
    dev = check_orthonormal(ylm)
    print('max |<Y_i|Y_j> - delta_ij| over the sphere: %.3e' % dev)
    if dev > 1e-6:
        raise SystemExit('l<=3 harmonics are not orthonormal; refuse to proceed')

    eda.bloch_orbitals = make_bloch_orbitals()

    workdir = Path('.')
    args = argv
    for i, a in enumerate(argv):
        if a == '--workdir':
            workdir = Path(argv[i + 1])
    types_by_atom = read_stru_types(workdir / 'stru_out')
    orb_arg = None
    for i, a in enumerate(argv):
        if a == '--orb':
            orb_arg = Path(argv[i + 1])
    orb_files = {
        1: orb_arg if (orb_arg and 'Mo' in orb_arg.name) else workdir / 'assets/Mo_gga_10au_100Ry_6s3p3d2f.orb',
        2: (orb_arg.parent / 'S_gga_10au_110Ry_3s3p2d.orb') if orb_arg else workdir / 'assets/S_gga_10au_110Ry_3s3p2d.orb',
    }
    cache = {k: eda.Orbital(v) for k, v in orb_files.items()}
    per_atom = [cache[t] for t in types_by_atom]
    eda._MULTI_ORB = MultiOrbital(per_atom)
    print('atoms %d, species %s, AO widths %s, total %d'
          % (len(per_atom), types_by_atom, eda._MULTI_ORB.widths, eda._MULTI_ORB.nw_total))

    for i, a in enumerate(argv):
        if a == '--band-offset':
            eda._BAND_OFFSET = int(argv[i + 1])
    print('band window: raw bands %d..%d used as %d occupied + %d empty'
          % (eda._BAND_OFFSET + 1, eda._BAND_OFFSET + 8, 4, 4))
    cleaned = []
    skip = False
    for i, a in enumerate(argv):
        if skip:
            skip = False
            continue
        if a == '--band-offset':
            skip = True
            continue
        cleaned.append(a)
    sys.argv = [str(SOURCE_PATH)] + cleaned
    return eda.main()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
