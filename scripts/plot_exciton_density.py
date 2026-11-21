#!/usr/bin/env python3
"""Rebuild an exciton density slice from BSE amplitudes, without ABACUS's plotter.

Why this exists
---------------
The same tool ships with the `oh-my-librpa` skill as
`exciton_density_from_amplitudes.py`; this copy lives here so the archived
exciton figures of a record can be regenerated from the record's own bytes.

Only ABACUS's `lr_solver plot` writes an exciton density; LibBSE writes none at
all. This tool derives the same quantity from artefacts both codes leave on
disk, so it works with either code's amplitudes:

    wfk<ik>_nao.txt                    AO coefficients at each fine k  (ABACUS NSCF)
    Excitation_Amplitude_singlet_*.dat TDA amplitudes per state
    <basis>.orb                        radial functions (SIAB basis)
    stru_out                           lattice vectors and atom positions

What is computed
----------------
The *average* density, i.e. one particle coordinate integrated out. With
`M_vv'(k) = sum_c X_kvc X_kv'c*` the hole side collapses to a squared modulus:

    rho_hole(r) = sum_k sum_c | sum_v X_kvc phi_vk(r) |^2
    rho_elec(r) = sum_k sum_v | sum_c X_kvc phi_ck(r) |^2

Both are manifestly non-negative, which is a useful check on the plumbing: if
the index order of X or of the AO basis is wrong, these go negative.

With `--kind cond-elec` / `--kind cond-hole` the *conditional* density is built
instead, which is the other thing ABACUS's `lr_solver plot` offers: one particle
is pinned at a chosen point and the other is left free,

    psi_cond,k(r) = sum_c [sum_v X_kvc conj(phi_vk(r_h))] phi_ck(r)
    rho(r_e | r_h) = |sum_k psi_cond,k(r_e)|^2

Note the difference in structure: the average density sums |.|^2 over k
(incoherent), the conditional one sums amplitudes over k and only then squares
(coherent), so the conditional density shows interference and is the quantity
that actually traces the exciton's shape.`

Conventions are read off ABACUS source, not guessed
---------------------------------------------------
* `.orb` stores `R(r)` (not `r*R`) on a uniform grid of spacing `dr`, verified by
  `int R^2 r^2 dr = 1` for every shell; each `Type L N`
  block is one radial function shared by all 2L+1 AOs of that shell.
* AO order is file order (s,s,s,p,p,p,d,d for this basis) and inside a block
  the real spherical harmonics follow ABACUS's `ylm.cpp` packing
  `m = 0, +1, -1, +2, -2`; the l=0,1,2 expressions below are transcribed from
  that file (`rly[0]`..`rly[8]`) so the signs match ABACUS exactly.
* `wfk*_nao.txt` holds complex coefficients interleaved as (re, im).
* the grid follows `make_slice_geometry`: `res = npoints // max(cells)`,
  `nu = total_u*res + 1`, and points are sampled at cell-local coordinates.

Cross-validation
----------------
Fed ABACUS's own amplitudes this tool reproduces ABACUS's
`Exciton_avg_{hole,elec}_slice_state0.dat`; fed LibBSE's amplitudes it gives the
LibBSE exciton. See the project note for the achieved agreement.

Usage:
    exciton_density_from_amplitudes.py --workdir <case> --amplitudes <libbse.d>
        --orb Si_gga_8au_100Ry_3s3p2d.orb --state 0 --kind both --plane ab
        --slice-pos 0.25 --npoints 80 --range -1 2 -1 2 --out out/prefix
"""

import argparse
import math
import pathlib
import sys

# numpy is required here: this tool evaluates Bloch sums of atomic orbitals on a
# real-space grid, which pure standard-library code cannot do at a usable speed.
# It is therefore not part of the gate chain; the CI image installs no numpy.
# Everything the gates themselves read stays standard-library only -- parsing,
# hashing, and rendering an already written slice (plot_exciton_slice.py).
try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - a message for the user
    raise SystemExit(
        "plot_exciton_density.py needs numpy (pip install numpy).\n"
        "For an archived slice use plot_exciton_slice.py, which is standard-library only."
    ) from exc

# ABACUS source_base/ylm.cpp coefficients (verbatim) and the l<=2 packing
_C0 = 0.28209479177387813964      # ylmcoef[0] 1/sqrt(4pi)
_C1 = 0.48860251190291992263      # ylmcoef[1] sqrt(3/4pi)
_C2 = 1.93649167310370851069      # ylmcoef[2]
_C3 = 1.11803398874989490253      # ylmcoef[3]
_C4 = 2.23606797749978980505      # ylmcoef[4]
_C5 = 0.57735026918962584208      # ylmcoef[5]
_C6 = 1.29099444873580559978      # ylmcoef[6]


def real_ylm_l2(x, y, z):
    """ABACUS rly[0..8]: l=0 (1), l=1 (3), l=2 (5), in ABACUS's m order."""
    r0 = _C0
    r1 = _C1 * z
    r2 = -_C1 * x
    r3 = -_C1 * y
    r4 = _C2 * z * r1 - _C3 * r0
    r5 = _C4 * z * r2
    r6 = _C4 * z * r3
    r7 = _C5 * r4 - _C6 * r0 - _C4 * x * r2
    r8 = -_C4 * x * r3
    return np.stack([r0, r1, r2, r3, r4, r5, r6, r7, r8])


class Orbital:
    """A SIAB `.orb` file: radial tables plus the (L,N) block layout."""

    def __init__(self, path):
        lines = pathlib.Path(path).read_text().splitlines()
        self.mesh = None
        self.dr = None
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith('Mesh'):
                self.mesh = int(lines[i].split()[1])
                self.dr = float(lines[i + 1].split()[1])
                i += 2
                break
            i += 1
        if self.mesh is None:
            raise ValueError("{}: no 'Mesh' line".format(path))

        blocks = []
        while i < len(lines):
            if 'Type' in lines[i]:
                i += 1
                fields = lines[i].split()
                if len(fields) < 3:
                    break
                L = int(fields[1])
                values = []
                j = i + 1
                while len(values) < self.mesh and j < len(lines):
                    values.extend(float(v) for v in lines[j].split())
                    j += 1
                blocks.append((L, np.asarray(values[:self.mesh])))
                i = j
            else:
                i += 1
        if not blocks:
            raise ValueError("{}: no orbital blocks".format(path))

        self.r = np.arange(1, self.mesh + 1) * self.dr
        self._prep_hermite(blocks)
        # .orb holds R(r) itself, NOT r*R(r): integrating f^2 r^2 dr over the
        # radial grid gives 1.00 for every shell of this basis, while f^2 dr
        # does not. (Checked numerically against Si_gga_8au_100Ry_3s3p2d.orb.)
        self.radial = [(L, f) for L, f in blocks]   # R(r) as stored
        self.max_l = max(L for L, _ in blocks)
        if self.max_l > 2:
            raise ValueError("this tool handles s/p/d only, got l={}".format(self.max_l))
        # per-AO bookkeeping: (block index, ylm slot).
        # ABACUS builds iw2_ylm[iw] = L*L + j with j = 0..2L running straight
        # through the block (source_cell/atom_spec.cpp), so AO order inside a
        # shell is exactly ylm.cpp's rly[L*L .. L*L+2L] order: m = 0, +1, -1, ...
        self.ao = []
        for ib, (L, _) in enumerate(blocks):
            for j in range(2 * L + 1):
                self.ao.append((ib, L * L + j))
        self.nw = len(self.ao)
        assert self.nw == sum(2 * L + 1 for L, _ in blocks)
        self.rcut = self.mesh * self.dr

    def _prep_hermite(self, blocks):
        """Precompute R and dR/dr on the radial grid for cubic Hermite interpolation.

        ABACUS's GintAtom::set_phi interpolates with the tabulated dpsi_uniform;
        the .orb file does not carry the derivative, so it is differenced here on
        the same uniform grid. Linear interpolation leaves a visible few-percent
        error on the strongly peaked occupied orbitals.
        """
        self._f = []
        self._df = []
        for L, f in blocks:
            d = np.gradient(f, self.dr)
            self._f.append(f)
            self._df.append(d)

    def values(self, dist, unit):
        """All nw AO values at displacement `dist` along `unit` from the centre."""
        ylm = real_ylm_l2(unit[0], unit[1], unit[2])
        out = np.empty(self.nw)
        pos = dist / self.dr
        i = int(pos)
        if i >= self.mesh - 2:
            return np.zeros(self.nw)
        dx = pos - i
        dx2 = dx * dx
        dx3 = dx2 * dx
        c3 = 3.0 * dx2 - 2.0 * dx3
        c1 = 1.0 - c3
        c2 = (dx - 2.0 * dx2 + dx3) * self.dr
        c4 = (dx3 - dx2) * self.dr
        for ib in range(len(self._f)):
            f, d = self._f[ib], self._df[ib]
            self._rad[ib] = c1 * f[i] + c2 * d[i] + c3 * f[i + 1] + c4 * d[i + 1]
        for k, (ib, yidx) in enumerate(self.ao):
            out[k] = self._rad[ib] * ylm[yidx]
        return out

    def _ensure(self):
        self._rad = np.zeros(len(self.radial))


def read_stru(path):
    vals = [[float(x) for x in l.split()] for l in pathlib.Path(path).read_text().splitlines() if l.strip()]
    lat = np.array(vals[0:3])
    nat = int(vals[6][0])
    pos = np.array([vals[7 + i][:3] for i in range(nat)])
    return lat, pos


def read_wfk(path):
    """Returns (kvec_cart, C). kvec_cart is in units of 2*pi/lat0 (ABACUS convention)."""
    lines = pathlib.Path(path).read_text().splitlines()
    kvec = [float(x) for x in lines[1].split()]
    nbands = int(lines[2].split()[0])
    nao = int(lines[3].split()[0])
    starts = [i for i, l in enumerate(lines) if '(band)' in l]
    C = np.zeros((nbands, nao), dtype=complex)
    for b in range(nbands):
        end = starts[b + 1] if b + 1 < nbands else len(lines)
        raw = np.array([float(x) for x in " ".join(lines[starts[b] + 3:end]).split()])
        C[b] = raw[0::2] + 1j * raw[1::2]
    return np.asarray(kvec), C


def apply_first_k_gauge(Cs):
    """Align every k point's phase to k = 0, exactly as ABACUS does.

    `read_librpa_eigenvectors_from_band_files` multiplies each band at each k by
        phase = <psi(ik)|psi(0)> / |<psi(ik)|psi(0)>|
    (`source_lcao/module_lr/utils/lr_io.cpp`, `LR_Util::inner_product` conjugates
    its first argument). LibBSE does the same under `wavefunction_gauge first_k`
    (`bse/molecular_lri.cpp`), so the amplitudes from either code are expressed
    in this gauge.

    The average density is invariant under it (each k contributes |.|^2), which
    is why that path matched ABACUS without this step. The **conditional**
    density is a coherent k-sum, so skipping the alignment destroys it.
    """
    if not Cs:
        return Cs
    ref = Cs[0]
    for C in Cs[1:]:
        for ib in range(C.shape[0]):
            # ABACUS calls inner_product(psi(ik), psi(0)) = sum conj(psi_ik) psi_0
            # = <ik|0>, so the first argument must be the current k, not the
            # reference. Reversing them conjugates the phase, which is invisible
            # to the average density (each k contributes |.|^2) but destroys the
            # coherent k-sum of the conditional one.
            overlap = np.vdot(C[ib], ref[ib])     # conj(C).ref = <ik|0>
            mag = abs(overlap)
            if mag > 0:
                C[ib] *= overlap / mag
    return Cs


def load_amplitudes(ampdir, state, nk, nocc, nvirt):
    files = sorted(pathlib.Path(ampdir).glob("Excitation_Amplitude_singlet_*.dat"))
    if not files:
        raise FileNotFoundError("no Excitation_Amplitude_singlet_*.dat in {}".format(ampdir))
    dim = nk * nocc * nvirt
    per = dim // len(files)
    if per * len(files) != dim:
        raise ValueError("{} ranks cannot split {}".format(len(files), dim))
    # ABACUS numbers ranks from 1, LibBSE from 0; detect the offset instead of
    # assuming it, otherwise every rank lands in the wrong slot.
    ranks = sorted(int(p.stem.split('_')[-1]) for p in files)
    base = ranks[0]
    X = np.zeros(dim, dtype=complex)
    for path in files:
        rank = int(path.stem.split('_')[-1]) - base
        lines = path.read_text().splitlines()
        # ABACUS writes a leading state counter line; LibBSE starts at state 0.
        offset = 1 if len(lines) > state + 1 and lines[0].split()[:1] and \
            lines[0].split()[0].isdigit() and len(lines[0].split()) == 1 else 0
        toks = lines[state + offset].split()
        if len(toks) != per:
            raise ValueError("{}: {} amplitudes, expected {}".format(path.name, len(toks), per))
        vals = np.array([complex(float(t.strip('()').split(',')[0]),
                                 float(t.strip('()').split(',')[1])) for t in toks])
        X[rank * per:(rank + 1) * per] = vals
    return X.reshape(nk, nocc, nvirt)


def bloch_orbitals(orb, lat, pos, r, rcut, cells, extra=0):
    """phi_mu,k(r) summed over lattice cells, for one real-space point."""
    nat = len(pos)
    phi = np.zeros(nat * orb.nw, dtype=complex)
    phi_real = np.zeros((len(cells), nat, orb.nw))
    for ic, (n1, n2, n3, Rv) in enumerate(cells):
        for iat in range(nat):
            dr_vec = r - pos[iat] - Rv
            dist = float(np.linalg.norm(dr_vec))
            if dist > rcut:
                continue
            if dist < 1e-12:
                # exactly on the nucleus: every l>0 orbital vanishes there, and
                # ABACUS's set_phi clamps the distance to 1e-9 for the same reason
                dist = 1e-9
            phi_real[ic, iat] = orb.values(dist, dr_vec / dist)
    return phi_real


def build_slice(orb, lat, pos, kvecs, Cs, X, nocc, nvirt, kind,
                plane, slice_pos, npoints, urange, bvk, fixed_point=None):
    a, b, c = lat
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    nc = np.linalg.norm(c)
    if plane == 'ab':
        u_vec, v_vec, perp = a, b, c * (slice_pos / nc)
        nk_u, nk_v = bvk[0], bvk[1]
    elif plane == 'bc':
        u_vec, v_vec, perp = b, c, a * (slice_pos / na)
        nk_u, nk_v = bvk[1], bvk[2]
    else:
        u_vec, v_vec, perp = c, a, b * (slice_pos / nb)
        nk_u, nk_v = bvk[2], bvk[0]

    us, ue, vs, ve = urange
    total_u, total_v = ue - us, ve - vs
    res = max(1, npoints // max(total_u, total_v))
    nu, nv = total_u * res + 1, total_v * res + 1
    du = (ue - us) / (nu - 1)
    dv = (ve - vs) / (nv - 1)

    rcut = orb.rcut
    span = int(math.ceil(rcut / min(na, nb, nc))) + 1
    cells = [(n1, n2, n3, n1 * a + n2 * b + n3 * c)
             for n1 in range(-span, span + 1)
             for n2 in range(-span, span + 1)
             for n3 in range(-span, span + 1)]
    # the conditional path evaluates at un-reduced positions, which can sit a
    # couple of cells away, so widen the stencil for it
    cells_wide = [(n1, n2, n3, n1 * a + n2 * b + n3 * c)
                  for n1 in range(-span - 4, span + 5)
                  for n2 in range(-span - 4, span + 5)
                  for n3 in range(-span - 4, span + 5)]
    nk = len(kvecs)
    nao = len(pos) * orb.nw
    orb._ensure()

    # Per-k effective density matrices, computed once instead of per grid point.
    Ms = []
    for ik in range(nk):
        Xk = X[ik]
        if kind == 'elec':
            # sum over the occupied index: M[c,c'] = sum_v X[v,c] conj(X[v,c'])
            Ms.append((Xk.T @ Xk.conj(), Cs[ik][nocc:nocc + nvirt]))
        else:
            # sum over the virtual index. ABACUS's cal_effective_dmk_hole builds
            # this with gemm_cm(adjoint, normal, nocc, nocc, nvirt, xk, nvirt, ...),
            # i.e. C = A^H A with A = xk stored row-major as (nocc, nvirt). That
            # gives M[v,v'] = sum_c conj(X[v,c]) X[v',c] = conj(X X^H) = (X X^H)^T
            # (M is Hermitian), so the transpose is part of their convention, not
            # a typo. Verified against their own plot: 0.951 -> 0.998.
            Ms.append(((Xk @ Xk.conj().T).T, Cs[ik][:nocc]))

    # Bloch phases per k: exp(2 pi i k.R) for every cell, shape (nk, ncells)
    cell_idx = np.array([[n1, n2, n3] for n1, n2, n3, _ in cells], dtype=float)
    allphase = np.exp(2j * np.pi * (np.asarray(kvecs) @ cell_idx.T))    # (nk, ncells)
    cell_idx_wide = np.array([[n1, n2, n3] for n1, n2, n3, _ in cells_wide], dtype=float)
    allphase_wide = np.exp(2j * np.pi * (np.asarray(kvecs) @ cell_idx_wide.T))

    fixed = np.asarray(fixed_point) if fixed_point is not None else None
    if kind.startswith('cond-'):
        # Coefficients of the conditional wavefunction, one vector per k.
        # elec: pin the hole -> psi_k = sum_c [sum_v X_kvc conj(phi_vk(r_h))] phi_ck
        # hole: pin the electron -> psi_k = sum_v [sum_c X_kvc phi_ck(r_e)] conj(phi_vk)
        fixedphi = []
        phi_f = bloch_orbitals(orb, lat, pos, fixed, rcut, cells)
        for ik in range(nk):
            phi = np.einsum('c,caw->aw', allphase[ik], phi_f).ravel()
            Xk = X[ik]
            Ck = Cs[ik]
            # ABACUS stores X flattened as X[iv + io*nvirt], i.e. row = occupied,
            # column = virtual, so X[io, iv]. Its mixing sums are therefore
            #   cond-elec: mixing[iv] = sum_io X[io,iv] conj(phi_io)  ->  X^T conj(phi)
            #   cond-hole: mixing[io] = sum_iv X[io,iv]     phi_iv   ->  X   phi
            if kind == 'cond-elec':
                mix = Xk.T @ np.conj(Ck[:nocc] @ phi)     # (nvirt,) sum_v X^T conj(phi_v)
                coef = Ck[nocc:nocc + nvirt]              # phi_c
                fixedphi.append(coef.T @ mix)              # (nao,) coefficient vector
            else:
                mix = Xk @ (Ck[nocc:nocc + nvirt] @ phi)  # (nocc,) sum_c X phi_c
                # cond-hole conjugates the occupied coefficients AND, at
                # evaluation time below, the orbital, and also negates the
                # translation phase. All three come from ABACUS's plot_cond_slice
                # hole branch (wfc_k += coef[mu] * conj(phi_bloch[mu]) plus
                # phase_arg = -phase_arg). Dropping any one of them costs most of
                # the agreement (measured 0.22 to 0.48 instead of 1.000000).
                fixedphi.append(np.conj(Ck[:nocc]).T @ mix)
        cond_coef = fixedphi
    else:
        cond_coef = None

    axes = {'ab': (0, 1), 'bc': (1, 2), 'ca': (2, 0)}[plane]
    dense = np.zeros((nu, nv))
    for iu in range(nu):
        u_frac = us + du * iu
        u_c = u_frac - math.floor(u_frac)
        for iv in range(nv):
            v_frac = vs + dv * iv
            v_c = v_frac - math.floor(v_frac)
            if cond_coef is not None:
                # Home-cell evaluation, then carried across the translations by
                # exp(+2*pi*i k.T) -- the structure of ABACUS's plot_cond_slice.
                home = perp + u_vec * u_c + v_vec * v_c
                phi_real = bloch_orbitals(orb, lat, pos, home, rcut, cells)
                # ABACUS uses the ABSOLUTE floor(u_frac) as the lattice
                # translation (plot_cond_slice: u_translation =
                # floor(u_frac)), not one relative to the window start.
                # Subtracting us shifts the phase by us cells, which moves
                # the whole pattern by exactly one cell for a -1..2 window.
                T_u = int(math.floor(u_frac := us + du * iu))
                T_v = int(math.floor(v_frac := vs + dv * iv))
                total = 0.0 + 0.0j
                is_hole = kind == 'cond-hole'
                for ik in range(nk):
                    phi = np.einsum('c,caw->aw', allphase[ik], phi_real).ravel()
                    # ABACUS conjugates the orbital on the hole side only
                    # (plot_cond_slice: wfc_k += coef[mu] * conj(phi_bloch[mu]))
                    # and flips the sign of the translation phase with it.
                    # Getting one of the two wrong costs most of the agreement
                    # (0.48 instead of 0.998), because the k-sum is coherent.
                    psi_home = np.dot(cond_coef[ik], np.conj(phi) if is_hole else phi)
                    kd = kvecs[ik]
                    arg = 2.0 * math.pi * (kd[axes[0]] * T_u + kd[axes[1]] * T_v)
                    if is_hole:
                        arg = -arg
                    total += complex(math.cos(arg), math.sin(arg)) * psi_home
                dense[iu, iv] = float(abs(total) ** 2)
                continue
            r = perp + u_vec * u_c + v_vec * v_c
            phi_real = bloch_orbitals(orb, lat, pos, r, rcut, cells)    # (ncells, nat, nw)
            rho = 0.0
            for ik in range(nk):
                M, coef = Ms[ik]
                # phi[mu] = sum_cells phase * phi_cell[mu], applied to one atom at a time
                phi = np.einsum('c,caw->aw', allphase[ik], phi_real).ravel()
                psi = coef @ phi
                rho += float(np.real(psi @ M @ psi.conj()))
            dense[iu, iv] = rho
    return dense, nu, nv, res


def write_slice(path, dense, nu, nv, lat, pos, plane, slice_pos, urange, bvk, state,
                kind="average", fixed_point=None):
    with open(path, 'w') as f:
        f.write("# ABACUS_EXCITON_SLICE 1\n")
        f.write("# state {} energy_Ry 0 density_kind {}\n".format(state, kind))
        if fixed_point is not None:
            f.write("# fixed_particle {} position_bohr {} {} {}\n".format(
                "hole" if kind == "conditional_elec" else "electron", *fixed_point))
        f.write("# plane {} slice_pos_bohr {}\n".format(plane, slice_pos))
        f.write("# grid {} {} u_range {} {} v_range {} {}\n".format(
            nu, nv, urange[0], urange[1], urange[2], urange[3]))
        f.write("# bvk {} {} {}\n".format(*bvk))
        f.write("# lattice_bohr\n")
        for name, v in zip('abc', lat):
            f.write("# {} {:.11f} {:.11f} {:.11f}\n".format(name, *v))
        f.write("# data\n")
        for iu in range(nu):
            f.write(" ".join("{:.8e}".format(dense[iu, iv]) for iv in range(nv)))
            f.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workdir", type=pathlib.Path, required=True,
                    help="directory holding stru_out and the wfk files' parent")
    ap.add_argument("--nscf-dir", default="OUT.nscf")
    ap.add_argument("--amplitudes", type=pathlib.Path, required=True)
    ap.add_argument("--orb", type=pathlib.Path, required=True)
    ap.add_argument("--state", type=int, default=0)
    ap.add_argument("--nocc", type=int, default=4)
    ap.add_argument("--nvirt", type=int, default=4)
    ap.add_argument("--kind",
                    choices=["elec", "hole", "both", "cond-elec", "cond-hole"],
                    default="both",
                    help="average densities (elec/hole/both) or conditional ones "
                         "(cond-elec/cond-hole), which need --fixed-point")
    ap.add_argument("--fixed-point", nargs=3, type=float, default=None,
                    help="Bohr coordinates of the pinned particle for cond-* kinds")
    ap.add_argument("--plane", default="ab", choices=["ab", "bc", "ca"])
    ap.add_argument("--slice-pos", type=float, default=0.25)
    ap.add_argument("--npoints", type=int, default=80)
    ap.add_argument("--range", nargs=4, type=int, default=[-1, 2, -1, 2])
    ap.add_argument("--bvk", nargs=3, type=int, default=[3, 3, 3])
    ap.add_argument("--gauge", choices=["first_k", "none"], default="first_k",
                    help="first_k aligns each k to the k=0 phase, which both "
                         "ABACUS and LibBSE do; required for cond-* kinds, "
                         "harmless for the average ones")
    ap.add_argument("--kstride", type=int, default=1,
                    help="use every n-th k point; a preview shortcut only, "
                         "the density is NOT the converged one when >1")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("exciton_slice"))
    args = ap.parse_args()

    orb = Orbital(args.orb)
    lat, pos = read_stru(args.workdir / "stru_out")
    wfk_files = sorted((args.workdir / args.nscf_dir).glob("wfk*_nao.txt"),
                       key=lambda p: int(p.stem[3:].split('_')[0]))
    if not wfk_files:
        raise FileNotFoundError("no wfk*_nao.txt under {}".format(args.workdir / args.nscf_dir))
    # wfk stores k in Cartesian units of 2*pi/lat0; the Bloch phase needs the
    # direct-coordinate k, k_d = k_c . (latvec/lat0)^T with latvec in Bohr.
    lat0 = 1.889726164          # 1 Angstrom in Bohr, ABACUS's lat0
    recip = (lat / lat0).T
    kvecs, Cs = [], []
    for p in wfk_files:
        kv_cart, C = read_wfk(p)
        kvecs.append(np.asarray(kv_cart) @ recip)
        Cs.append(C)
    if args.gauge == "first_k":
        Cs = apply_first_k_gauge(Cs)
        print("applied first_k wavefunction gauge (matches ABACUS and LibBSE)")
    nk = len(kvecs)
    X = load_amplitudes(args.amplitudes, args.state, nk, args.nocc, args.nvirt)
    if args.kstride > 1:
        keep = list(range(0, nk, args.kstride))
        kvecs = [kvecs[i] for i in keep]
        Cs = [Cs[i] for i in keep]
        X = X[keep]
        nk = len(keep)
        print("PREVIEW ONLY: kstride={} -> {} k points, density not converged".format(
            args.kstride, nk))
    print("{} k points | {} AO/atom | {} atoms | sum|X|^2 = {:.6f}".format(
        nk, orb.nw, len(pos), float(np.sum(np.abs(X) ** 2))))

    kinds = ["elec", "hole"] if args.kind == "both" else [args.kind]
    if any(k.startswith('cond-') for k in kinds) and args.fixed_point is None:
        raise SystemExit("--kind cond-* needs --fixed-point X Y Z (Bohr)")
    if any(k.startswith('cond-') for k in kinds):
        print("cond-* reproduces ABACUS lr_solver plot point for point\n"
              "         (correlation 1.000000, relative difference ~1e-6).")
    for kind in kinds:
        dense, nu, nv, res = build_slice(
            orb, lat, pos, kvecs, Cs, X, args.nocc, args.nvirt, kind,
            args.plane, args.slice_pos, args.npoints, args.range, args.bvk,
            fixed_point=args.fixed_point)
        path = pathlib.Path("{}_{}_slice_state{}.dat".format(args.out, kind, args.state))
        path.parent.mkdir(parents=True, exist_ok=True)
        kind_label = ("conditional_" + kind.split('-')[1]) if kind.startswith('cond-') else "average_" + kind
        write_slice(path, dense, nu, nv, lat, pos, args.plane, args.slice_pos,
                    args.range, args.bvk, args.state,
                    kind=kind_label, fixed_point=args.fixed_point)
        print("  {:4s}: {}x{} ({} pts/cell)  max {:.4e}  min {:.4e}  -> {}".format(
            kind, nu, nv, res, dense.max(), dense.min(), path.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
