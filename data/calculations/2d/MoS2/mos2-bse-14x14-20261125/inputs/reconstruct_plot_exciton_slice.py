#!/usr/bin/env python3
"""Plot an ABACUS_EXCITON_SLICE file as a PNG heat map with the cell outline.

The archived plot_exciton_slice.py only writes SVG and this workstation has no
SVG rasteriser, so the same data are drawn here with matplotlib. The values are
read out of the slice file unchanged; nothing is re-derived or rescaled.
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
    "font.size": 10.5,
    "axes.linewidth": 1.1,
    "pdf.fonttype": 42,
}


def read_slice(path):
    """Return (header dict, density array).

    Header lines carry several key/value pairs each, so the raw text is kept per
    line and the values are looked up by key name rather than by position.
    """
    meta, rows, header = {}, [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                body = line[1:].strip()
                if body:
                    header.append(body)
                    key, *rest = body.split()
                    meta[key] = rest
                continue
            rows.append([float(v) for v in line.split()])
    meta["_header"] = header
    return meta, np.asarray(rows)


def header_value(meta, key, default=None):
    """Find `<key> <value>` anywhere in the raw header lines."""
    for body in meta["_header"]:
        tok = body.split()
        if key in tok:
            i = tok.index(key)
            if i + 1 < len(tok):
                return tok[i + 1]
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slice")
    ap.add_argument("--output", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--log", action="store_true", help="plot log10 of the density")
    args = ap.parse_args()

    meta, dense = read_slice(args.slice)
    nu, nv = int(meta["grid"][0]), int(meta["grid"][1])
    # header is: grid <nu> <nv> u_range <u0> <u1> v_range <v0> <v1>
    g = meta["grid"]
    u0, u1 = float(g[g.index("u_range") + 1]), float(g[g.index("u_range") + 2])
    v0, v1 = float(g[g.index("v_range") + 1]), float(g[g.index("v_range") + 2])
    a = np.array([float(x) for x in meta["a"]])
    b = np.array([float(x) for x in meta["b"]])
    kind = header_value(meta, "density_kind", "") or ""
    pos = float(header_value(meta, "slice_pos_bohr", "0"))

    data = np.log10(np.maximum(dense, dense[dense > 0].min() * 1e-3)) if args.log else dense

    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(5.6, 4.9), constrained_layout=True)
        extent = (u0, u1, v0, v1)
        im = ax.imshow(data, origin="lower", extent=extent, cmap="inferno",
                       interpolation="bilinear")
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label(r"$\log_{10}\rho$" if args.log else r"$\rho$ (arb.)")

        # primitive-cell outline in the (a, b) plane
        poly = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]])
        ax.plot(poly[:, 0], poly[:, 1], color="#7fd4ff", linewidth=1.15,
                linestyle=(0, (4, 2)), zorder=5)

        ax.set_xlim(u0, u1)
        ax.set_ylim(v0, v1)
        ax.set_aspect("equal")
        ax.set_xlabel(r"$u$ along $a$  (fractional)")
        ax.set_ylabel(r"$v$ along $b$  (fractional)")
        ax.tick_params(which="both", direction="in", top=True, right=True)
        if args.title:
            ax.set_title(args.title, loc="left", fontweight="bold", pad=7.0)
        ax.text(0.985, 0.015, "%s   z = %.2f bohr" % (kind.replace("_", " "), pos),
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8.2, color="#dddddd")

        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=400, bbox_inches="tight", facecolor="white")
        plt.close(fig)
    print("wrote", out)
    print("  grid %dx%d  range %.3e .. %.3e" % (nu, nv, dense.min(), dense.max()))


if __name__ == "__main__":
    main()
