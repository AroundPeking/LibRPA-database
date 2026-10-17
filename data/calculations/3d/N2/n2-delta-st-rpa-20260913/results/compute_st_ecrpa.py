#!/usr/bin/env python
from __future__ import print_function

import argparse
import math
import struct
import sys

import numpy as np


COULOMB_V1_MARKER = -20129433
ST_CHI0_V1_MARKER = -41073291


def _pair_from_index(pair_index, natom):
    count = 0
    for iatom in range(natom):
        for jatom in range(iatom, natom):
            if count == pair_index:
                return iatom, jatom
            count += 1
    raise ValueError("invalid atom-pair index {0} for natom={1}".format(pair_index, natom))


def _offsets(atom_naux):
    starts = []
    total = 0
    for naux in atom_naux:
        starts.append(total)
        total += naux
    return starts, total


def _complex_payload(data, offset, end, value_flag):
    if value_flag == 1:
        if (end - offset) % 16 != 0:
            raise ValueError("complex payload is not aligned")
        payload = []
        for pos in range(offset, end, 16):
            re, im = struct.unpack_from("<dd", data, pos)
            payload.append(complex(re, im))
        return payload
    if value_flag == 0:
        if (end - offset) % 8 != 0:
            raise ValueError("real payload is not aligned")
        payload = []
        for pos in range(offset, end, 8):
            re = struct.unpack_from("<d", data, pos)[0]
            payload.append(complex(re, 0.0))
        return payload
    raise ValueError("unsupported value_flag {0}".format(value_flag))


def read_coulomb_v1(path):
    with open(path, "rb") as handle:
        data = handle.read()
    header_fmt = "<6i"
    marker, iq, naux, value_flag, natom, nblocks = struct.unpack_from(header_fmt, data, 0)
    if marker != COULOMB_V1_MARKER:
        raise ValueError("{0}: Coulomb marker {1} != {2}".format(path, marker, COULOMB_V1_MARKER))
    pos = struct.calcsize(header_fmt)
    atom_naux = list(struct.unpack_from("<" + "i" * natom, data, pos))
    pos += 4 * natom
    blocks = []
    for _ in range(nblocks):
        pair_index, offset = struct.unpack_from("<iq", data, pos)
        pos += 12
        blocks.append((pair_index, offset))

    starts, total_naux = _offsets(atom_naux)
    if total_naux != naux:
        raise ValueError("{0}: naux mismatch {1} != {2}".format(path, total_naux, naux))
    matrix = np.zeros((naux, naux), dtype=np.complex128)
    for iblock, (pair_index, offset) in enumerate(blocks):
        end = blocks[iblock + 1][1] if iblock + 1 < len(blocks) else len(data)
        iatom, jatom = _pair_from_index(pair_index, natom)
        nrow = atom_naux[iatom]
        ncol = atom_naux[jatom]
        payload = _complex_payload(data, offset, end, value_flag)
        if len(payload) != nrow * ncol:
            raise ValueError("{0}: block {1} payload length mismatch".format(path, pair_index))
        block = np.array(payload, dtype=np.complex128).reshape((nrow, ncol))
        i0 = starts[iatom]
        j0 = starts[jatom]
        matrix[i0:i0 + nrow, j0:j0 + ncol] = block
        if iatom != jatom:
            matrix[j0:j0 + ncol, i0:i0 + nrow] = block.conjugate().T
    return {
        "path": path,
        "iq": iq,
        "naux": naux,
        "value_flag": value_flag,
        "natom": natom,
        "nblocks": nblocks,
        "atom_naux": atom_naux,
        "matrix": matrix,
    }


def read_st_m_v1(path):
    with open(path, "rb") as handle:
        data = handle.read()
    header_fmt = "<6i2di"
    marker, iq, ifreq, naux, value_flag, natom, omega, weight, nblocks = struct.unpack_from(header_fmt, data, 0)
    if marker != ST_CHI0_V1_MARKER:
        raise ValueError("{0}: ST marker {1} != {2}".format(path, marker, ST_CHI0_V1_MARKER))
    pos = struct.calcsize(header_fmt)
    atom_naux = list(struct.unpack_from("<" + "i" * natom, data, pos))
    pos += 4 * natom
    blocks = []
    for _ in range(nblocks):
        pair_index, offset = struct.unpack_from("<iq", data, pos)
        pos += 12
        blocks.append((pair_index, offset))

    starts, total_naux = _offsets(atom_naux)
    if total_naux != naux:
        raise ValueError("{0}: naux mismatch {1} != {2}".format(path, total_naux, naux))
    matrix = np.zeros((naux, naux), dtype=np.complex128)
    for iblock, (pair_index, offset) in enumerate(blocks):
        end = blocks[iblock + 1][1] if iblock + 1 < len(blocks) else len(data)
        iatom, jatom = _pair_from_index(pair_index, natom)
        nrow = atom_naux[iatom]
        ncol = atom_naux[jatom]
        payload = _complex_payload(data, offset, end, value_flag)
        if len(payload) != nrow * ncol:
            raise ValueError("{0}: block {1} payload length mismatch".format(path, pair_index))
        block = np.array(payload, dtype=np.complex128).reshape((nrow, ncol))
        i0 = starts[iatom]
        j0 = starts[jatom]
        matrix[i0:i0 + nrow, j0:j0 + ncol] = block
        if iatom != jatom:
            matrix[j0:j0 + ncol, i0:i0 + nrow] = block.conjugate().T
    return {
        "path": path,
        "iq": iq,
        "ifreq": ifreq,
        "omega": omega,
        "weight": weight,
        "naux": naux,
        "value_flag": value_flag,
        "natom": natom,
        "nblocks": nblocks,
        "atom_naux": atom_naux,
        "matrix": matrix,
    }


def hermitize(matrix):
    return 0.5 * (matrix + matrix.conjugate().T)


def coulomb_inverse_sqrt_weights(eigenvalues, threshold, regularization="hard"):
    """Return V^(-1/2) spectral weights and the represented Coulomb modes.

    The smooth mode is the positive square root of the Tikhonov inverse
    lambda / (lambda^2 + threshold^2). Non-positive Coulomb modes remain
    outside the represented metric space in both modes.
    """
    if threshold < 0.0:
        raise ValueError("Coulomb regularization threshold must be non-negative")
    eigenvalues = np.asarray(eigenvalues, dtype=float)
    if regularization == "hard":
        keep = eigenvalues > threshold
        return 1.0 / np.sqrt(eigenvalues[keep]), keep
    if regularization == "smooth":
        keep = eigenvalues > 0.0
        positive = eigenvalues[keep]
        return np.sqrt(positive / (positive * positive + threshold * threshold)), keep
    raise ValueError("unsupported Coulomb regularization {0}".format(regularization))


def compute_single_frequency_energy(coulomb, response_m, threshold, regularization="hard"):
    if coulomb["atom_naux"] != response_m["atom_naux"]:
        raise ValueError("atom_naux mismatch between Coulomb and ST response")
    vmat = hermitize(coulomb["matrix"])
    mmat = hermitize(response_m["matrix"])

    v_eigs, v_vecs = np.linalg.eigh(vmat)
    inverse_sqrt, keep = coulomb_inverse_sqrt_weights(v_eigs, threshold, regularization)
    if int(np.count_nonzero(keep)) == 0:
        raise ValueError("no represented Coulomb eigenvalues for threshold {0}".format(threshold))
    v_pos = v_eigs[keep]
    u_pos = v_vecs[:, keep]
    m_in_v_basis = np.dot(u_pos.conjugate().T, np.dot(mmat, u_pos))
    pi = (inverse_sqrt[:, None] * m_in_v_basis) * inverse_sqrt[None, :]
    pi = hermitize(pi)
    lambdas = np.real_if_close(np.linalg.eigvalsh(pi), tol=1000).real
    one_minus = 1.0 - lambdas
    min_one_minus = float(np.min(one_minus))
    if min_one_minus <= 0.0:
        raise ValueError("trace-log has non-positive 1-lambda minimum {0}".format(min_one_minus))
    integrand = float(np.sum(np.log(one_minus) + lambdas))
    energy = integrand * response_m["weight"] / (2.0 * math.pi)
    return {
        "naux": response_m["naux"],
        "n_v_pos": int(np.count_nonzero(keep)),
        "n_v_drop": int(len(v_eigs) - np.count_nonzero(keep)),
        "regularization": regularization,
        "v_min": float(np.min(v_eigs)),
        "v_max": float(np.max(v_eigs)),
        "v_pos_min": float(np.min(v_pos)),
        "v_pos_max": float(np.max(v_pos)),
        "inverse_sqrt_max": float(np.max(inverse_sqrt)),
        "inverse_sqrt_frobenius": float(np.linalg.norm(inverse_sqrt)),
        "lambda_min": float(np.min(lambdas)),
        "lambda_max": float(np.max(lambdas)),
        "trace_pi": float(np.sum(lambdas)),
        "integrand": integrand,
        "omega": response_m["omega"],
        "weight": response_m["weight"],
        "energy_ha": energy,
        "hermitian_error_v": float(np.linalg.norm(coulomb["matrix"] - coulomb["matrix"].conjugate().T)),
        "hermitian_error_m": float(np.linalg.norm(response_m["matrix"] - response_m["matrix"].conjugate().T)),
    }


def _print_frequency_result(result):
    print("{0:6d} {1:.16e} {2:.16e} {3:6d} {4:6d} {5:.16e} {6:.16e} {7:.16e} {8:.16e}".format(
        result["ifreq"], result["omega"], result["weight"],
        result["n_v_pos"], result["n_v_drop"],
        result["lambda_min"], result["lambda_max"],
        result["integrand"], result["energy_ha"]))


def main(argv):
    parser = argparse.ArgumentParser(description="Compute frequency-summed RPA trace-log energy from ABACUS ST M=V chi0 V.")
    parser.add_argument("--coulomb", required=True, help="v1_coulomb_cut/full_iq_*.dat")
    parser.add_argument("--st", required=True, nargs="+", help="one or more v1_sternheimer_chi0_iq_*_ifreq_*_rank*.dat files")
    parser.add_argument("--threshold", type=float, default=0.0, help="Coulomb eigenvalue threshold")
    parser.add_argument("--regularization", choices=("hard", "smooth"), default="hard",
                        help="hard spectral cutoff or smooth Tikhonov inverse square root")
    args = parser.parse_args(argv)

    coulomb = read_coulomb_v1(args.coulomb)
    print("coulomb={0}".format(args.coulomb))
    print("threshold={0:.16e}".format(args.threshold))
    print("regularization={0}".format(args.regularization))

    results = []
    for st_path in args.st:
        response_m = read_st_m_v1(st_path)
        result = compute_single_frequency_energy(coulomb,
                                                 response_m,
                                                 args.threshold,
                                                 args.regularization)
        result["ifreq"] = response_m["ifreq"]
        result["st_path"] = st_path
        results.append(result)
    results.sort(key=lambda item: item["ifreq"])

    if len(results) != len(set(result["ifreq"] for result in results)):
        raise ValueError("duplicated ifreq in ST response files")

    first = results[0]
    print("naux={0} nfreq={1} threshold={2:.16e}".format(first["naux"], len(results), args.threshold))
    print("v_eig_min={0:.16e} v_eig_max={1:.16e}".format(first["v_min"], first["v_max"]))
    print("v_pos_min={0:.16e} v_pos_max={1:.16e}".format(first["v_pos_min"], first["v_pos_max"]))
    print("inverse_sqrt_max={0:.16e} inverse_sqrt_frobenius={1:.16e}".format(
        first["inverse_sqrt_max"], first["inverse_sqrt_frobenius"]))
    print("hermitian_error_v={0:.16e}".format(first["hermitian_error_v"]))
    print(" ifreq omega_Ha weight_Ha n_v_pos n_v_drop lambda_min lambda_max integrand Ec_contribution_Ha")
    total = 0.0
    max_hermitian_error_m = 0.0
    for result in results:
        _print_frequency_result(result)
        total += result["energy_ha"]
        max_hermitian_error_m = max(max_hermitian_error_m, result["hermitian_error_m"])
    print("max_hermitian_error_m={0:.16e}".format(max_hermitian_error_m))
    if len(results) == 1:
        print("single_frequency_EcRPA_Ha={0:.16e}".format(total))
    print("frequency_sum_EcRPA_Ha={0:.16e}".format(total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
