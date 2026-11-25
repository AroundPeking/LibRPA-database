#!/usr/bin/env python3
"""Absorption spectrum (eps2) and exciton ladder for the new MoS2 14x14x1 BSE run."""
from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
BSE = ROOT / "bse_results"
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)

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
    "ps.fonttype": 42,
}

spec = np.loadtxt(BSE / "eps2_singlet_tda.dat")
energies, eps2 = spec[:, 0], spec[:, 1]

# Only the states that carry real oscillator strength are physical excitons;
# the rest of the 3136-state window is numerically dark.
osc = np.loadtxt(BSE / "oscillator_strength_singlet_tda.dat")
states_e, states_f = osc[:, 1], osc[:, 5]
# Restrict to the plotted window first. One diagonalization root at 18.58 eV
# carries f = 1.67e3, sixty times anything below 5 eV; it is far outside the
# optical window, so a global relative threshold would flatten the real ladder.
window = (states_e >= 1.0) & (states_e <= 5.0)
bright = window & (states_f > 1.0e-3 * states_f[window].max())

with plt.rc_context(STYLE):
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(7.25, 5.6), sharex=True,
        gridspec_kw={"height_ratios": [2.4, 1.0], "hspace": 0.20},
    )

    ax1.plot(energies, eps2, color="#E64B35", linewidth=1.9, zorder=3)
    ax1.fill_between(energies, 0.0, eps2, color="#E64B35", alpha=0.16, zorder=2)
    ax1.set_ylabel(r"$\varepsilon_2(\omega)$")
    ax1.set_title(r"MoS$_2$ monolayer  |  BSE (TDA, singlet)",
                  loc="left", pad=7.0, fontweight="bold")
    ax1.text(0.012, 0.965, "14x14x1 mesh, 196 k, G0W0@PBE input",
             transform=ax1.transAxes, ha="left", va="top",
             fontsize=8.2, color="#555555")
    ax1.grid(axis="y", color="#D0D0D0", linewidth=0.55, alpha=0.75)
    ax1.set_xlim(1.0, 5.0)
    ax1.set_ylim(0.0, max(eps2) * 1.18)
    ax1.set_yticks([t for t in ax1.get_yticks() if t > 1e-9])

    # Exciton ladder: every state with non-negligible oscillator strength.
    bright_e = states_e[bright]
    bright_f = states_f[bright]
    markerline, stemlines, baseline = ax2.stem(
        bright_e, bright_f, linefmt="-", markerfmt="o", basefmt=" ")
    plt.setp(stemlines, color="#333333", linewidth=1.1)
    plt.setp(markerline, color="#333333", markersize=3.6)
    ax2.set_ylabel("oscillator strength (arb.)")
    ax2.set_xlabel("photon energy (eV)")
    ax2.grid(axis="y", color="#D0D0D0", linewidth=0.55, alpha=0.75)
    ax2.set_ylim(0.0, bright_f.max() * 1.22)
    ax2.yaxis.set_major_locator(plt.MaxNLocator(nbins=4))

    for axis in (ax1, ax2):
        axis.tick_params(which="both", direction="in", top=True, right=True)

    # The lowest bright state sets the optical onset; label it on both panels.
    lowest = bright_e[np.argmin(bright_e)]
    for axis in (ax1, ax2):
        axis.axvline(lowest, color="#00A6B4", linewidth=0.95, linestyle=(0, (4, 2)), zorder=1)
    ax1.annotate(r"lowest bright exciton  %.3f eV" % lowest,
                 xy=(lowest, eps2.max() * 0.55), xytext=(12, 0),
                 textcoords="offset points", fontsize=8.6, color="#00707a",
                 va="center",
                 arrowprops={"arrowstyle": "-", "color": "#00A6B4", "linewidth": 0.8})

    fig.savefig(OUT / "mos2_14x14_absorption.png", dpi=400,
                bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / "mos2_14x14_absorption.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)

print("lowest bright exciton: %.6f eV" % bright_e.min())
print("bright states: %d of %d" % (bright.sum(), len(bright)))
print("eps2 peak: %.3f at %.3f eV" % (eps2.max(), energies[np.argmax(eps2)]))
print("written:", OUT / "mos2_14x14_absorption.png")
