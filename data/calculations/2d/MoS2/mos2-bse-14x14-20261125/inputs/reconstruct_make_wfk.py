#!/usr/bin/env python3
"""Write ABACUS-format wfk*_nao.txt for the 196-k BSE grid from LibRPA's binary.

The BSE ran on the 14x14x1 mesh (196 k). Only the 121-point band path has ABACUS
text wavefunctions, so the dense-grid eigenvectors are exported from the same
SCF's reader-v1 binary. Conventions were verified against a wfk file that ABACUS
itself wrote in this run:

  * the binary block is (band, ao): element b*nbasis + a
  * kvec = k_frac @ inv(lattice).T with the lattice in Angstrom (no 2*pi factor)
  * band_out.txt writes four columns per band: index, weight, energy in Ha,
    energy in eV. LibRPA consumes the Ha column; the wfk file wants Ry.
"""
from __future__ import annotations

import pathlib
import struct

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "wfk_src"
DEST = ROOT / "wfk_196k"
DEST.mkdir(exist_ok=True)

LAT = np.array([[3.184, 0.0, 0.0],
                [-1.592, 2.7574248856, 0.0],
                [0.0, 0.0, 30.0]])
RECIP_NO_2PI = np.linalg.inv(LAT).T
HA2EV = 27.211386245988
EV2RY = 1.0 / 13.605693122994

frac = []
for line in (SRC / "bz_sampling_out").read_text().splitlines()[2:]:
    f = line.split()
    if len(f) >= 5:
        frac.append([float(f[2]), float(f[3]), float(f[4])])
frac = np.array(frac)

toks = (SRC / "band_out.txt").read_text().split()
nk_s, nspin_s, nst_s, nbas_s = (int(toks[i]) for i in range(4))
pos = 5
band_e = np.zeros((nk_s, nst_s))
band_w = np.zeros((nk_s, nst_s))
for ik in range(nk_s):
    pos += 2                        # "<k index> <spin index>"
    for ib in range(nst_s):
        ib_read = int(toks[pos])
        w = float(toks[pos + 1])
        e_ha = float(toks[pos + 2])     # 3rd column is Hartree
        e_ev = float(toks[pos + 3])     # 4th column is the same value in eV
        pos += 4
        assert abs(e_ha * HA2EV - e_ev) < 1e-6 * max(1.0, abs(e_ev))
        band_e[ik, ib_read - 1] = e_ev
        band_w[ik, ib_read - 1] = w

blob = (SRC / "KS_eigenvector_0.dat").read_bytes()
marker, kind, nk, nspin, nstates, nbasis = struct.unpack("<6i", blob[:24])
assert (nk, nstates, nbasis) == (nk_s, nst_s, nbas_s), (nk, nstates, nbasis)

offsets = {}
for i in range(nk):
    ik, off = struct.unpack("<iq", blob[24 + i * 12:24 + i * 12 + 12])
    offsets[ik - 1] = off

for ik in range(nk):
    raw = blob[offsets[ik]:offsets[ik] + nstates * nbasis * 16]
    v = np.frombuffer(raw, dtype=np.complex128).reshape(nstates, nbasis)
    kv = frac[ik] @ RECIP_NO_2PI
    lines = ["1 (index of k points)",
             "%.10f %.10f %.10f" % (kv[0], kv[1], kv[2]),
             "%d (number of bands)" % nstates,
             "%d (number of orbitals)" % nbasis]
    for ib in range(nstates):
        lines.append("%d (band)" % (ib + 1))
        lines.append("%.8e (Ry)" % (band_e[ik, ib] * EV2RY))
        lines.append("%.8e (Occupations)" % band_w[ik, ib])
        lines.extend("%.8e %.8e" % (z.real, z.imag) for z in v[ib])
    (DEST / ("wfk%d_nao.txt" % (ik + 1))).write_text("\n".join(lines) + "\n")

print("wrote %d wfk files to %s" % (nk, DEST))
print("  k range (no 2pi): %s .. %s" % (frac[0] @ RECIP_NO_2PI, frac[-1] @ RECIP_NO_2PI))
print("  E range: %.4f .. %.4f eV" % (band_e.min(), band_e.max()))
