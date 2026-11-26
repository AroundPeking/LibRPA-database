#!/usr/bin/env python3
"""Exciton density as one two-panel figure, matching the archive style.

The Si record stores `exciton_avg_777.png` and `exciton_conditional_777.png`:
one file per density family, with the hole on the left and the electron on the
right. The first MoS2 record shipped four separate files instead, which is why
the two pages looked different.
"""
from __future__ import annotations

import argparse
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

STYLE = {
    "font.family": "serif",
    "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 10.0,
    "axes.linewidth": 1.1,
    "pdf.fonttype": 42,
}


def read_slice(path):
    header, rows = [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                body = line[1:].strip()
                if body:
                    header.append(body)
                continue
            rows.append([float(v) for v in line.split()])
    return header, np.asarray(rows)


def header_value(header, key, default=None):
    for body in header:
        tok = body.split()
        if key in tok:
            i = tok.index(key)
            if i + 1 < len(tok):
                return tok[i + 1]
    return default


def grid_meta(header):
    for body in header:
        tok = body.split()
        if tok and tok[0] == "grid":
            return (float(tok[tok.index("u_range") + 1]), float(tok[tok.index("u_range") + 2]),
                    float(tok[tok.index("v_range") + 1]), float(tok[tok.index("v_range") + 2]))
    raise ValueError("no grid header")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hole")
    ap.add_argument("elec")
    ap.add_argument("--output", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args()

    panels = []
    for path in (args.hole, args.elec):
        header, dense = read_slice(path)
        panels.append((header, dense, grid_meta(header)))

    (h_hdr, h_dense, extent), (e_hdr, e_dense, _) = panels
    kind = header_value(h_hdr, "density_kind", "")
    z = header_value(h_hdr, "slice_pos_bohr", "0")
    fixed = [t for t in h_hdr if "fixed_particle" in t]

    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.3), constrained_layout=True)
        for ax, (hdr, dense, ext), name in zip(
                axes, [(h_hdr, h_dense, extent), (e_hdr, e_dense, extent)],
                ("hole", "electron")):
            data = dense
            if args.log:
                pos = data[data > 0]
                floor = pos.min() * 1e-3 if pos.size else 1e-30
                data = np.log10(np.maximum(data, floor))
            im = ax.imshow(data, origin="lower", extent=ext, cmap="inferno",
                           interpolation="bilinear")
            cb = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
            cb.set_label(r"$\log_{10}\rho$" if args.log else r"$\rho$")

            poly = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]], dtype=float)
            ax.plot(poly[:, 0], poly[:, 1], color="#7fd4ff", linewidth=1.1,
                    linestyle=(0, (4, 2)), zorder=5)
            if fixed:
                fx, fy, _fz = (float(v) for v in fixed[0].split()[-3:])
                # the pinned particle sits at a real-space point; express it in
                # the same fractional frame as the axes
                ax.plot(0.0, 0.0, marker="o", markersize=9, markerfacecolor="none",
                        markeredgecolor="white", markeredgewidth=1.6, zorder=6)
            ax.set_xlim(ext[0], ext[1])
            ax.set_ylim(ext[2], ext[3])
            ax.set_aspect("equal")
            ax.set_xlabel(r"$u$ along $a$ (fractional)")
            if name == "hole":
                ax.set_ylabel(r"$v$ along $b$ (fractional)")
            ax.tick_params(which="both", direction="in", top=True, right=True)
            ax.set_title(name, loc="left", fontweight="bold", pad=5.0)

        if args.title:
            fig.suptitle(args.title, fontweight="bold", x=0.01, ha="left")
        note = "%s   z = %s bohr" % (kind.replace("_", " "), z)
        fig.text(0.99, 0.005, note, ha="right", va="bottom", fontsize=8.0,
                 color="#666666")

        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=400, bbox_inches="tight", facecolor="white")
        plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    main()
