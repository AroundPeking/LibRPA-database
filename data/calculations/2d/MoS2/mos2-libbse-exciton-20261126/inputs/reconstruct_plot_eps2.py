#!/usr/bin/env python3
"""eps2(w) as a single annotated panel, matching the archive's Si figure.

The Si record stores one `absorption_eps2.png`: eps2 against photon energy with
the main peak annotated. The first MoS2 record shipped a two-panel figure with
an oscillator-strength ladder underneath, which is why the two pages differ.
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
    "axes.labelsize": 11.0,
    "axes.linewidth": 1.3,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "pdf.fonttype": 42,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eps2")
    ap.add_argument("--output", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--emin", type=float, default=1.0)
    ap.add_argument("--emax", type=float, default=5.0)
    ap.add_argument("--onset", type=float, default=None,
                    help="lowest bright exciton energy, drawn as a dashed marker")
    args = ap.parse_args()

    data = np.loadtxt(args.eps2)
    e, y = data[:, 0], data[:, 1]
    keep = (e >= args.emin) & (e <= args.emax)
    e, y = e[keep], y[keep]

    ipk = int(np.argmax(y))
    e_pk, y_pk = float(e[ipk]), float(y[ipk])

    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(6.6, 4.4), constrained_layout=True)
        ax.plot(e, y, color="#E64B35", linewidth=1.9, zorder=3)
        ax.fill_between(e, 0.0, y, color="#E64B35", alpha=0.15, zorder=2)

        ax.annotate(r"$%.2f$ eV" % e_pk, xy=(e_pk, y_pk), xytext=(10, -6),
                    textcoords="offset points", fontsize=9.5, color="#8B1A0A")
        ax.plot([e_pk], [y_pk], marker="o", markersize=4.5, color="#8B1A0A",
                linestyle="None", zorder=5)

        if args.onset is not None:
            ax.axvline(args.onset, color="#00A6B4", linewidth=1.0,
                       linestyle=(0, (4, 2)), zorder=1)
            ax.annotate(r"onset $%.3f$ eV" % args.onset,
                        xy=(args.onset, y.max() * 0.45), xytext=(8, 0),
                        textcoords="offset points", fontsize=8.8, color="#00707a",
                        va="center")

        ax.set_xlim(args.emin, args.emax)
        ax.set_ylim(0.0, y.max() * 1.18)
        ax.set_xlabel("photon energy (eV)")
        ax.set_ylabel(r"$\varepsilon_2(\omega)$")
        ax.grid(axis="y", color="#D0D0D0", linewidth=0.55, alpha=0.75)
        ax.tick_params(which="both", direction="in", top=True, right=True)
        if args.title:
            ax.set_title(args.title, loc="left", fontweight="bold", pad=7.0)

        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=400, bbox_inches="tight", facecolor="white")
        plt.close(fig)
    print("wrote %s   peak %.3f at %.3f eV" % (out, y_pk, e_pk))


if __name__ == "__main__":
    main()
