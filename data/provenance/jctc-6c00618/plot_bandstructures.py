#!/usr/bin/env python3
"""Plot FHI-aims and LibRPA GW bands for the materials in this directory."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
import numpy as np

from mushroom.aims.analyse import get_chemical_potential, get_recp_latt_from_geometry
from mushroom.aims.band import read_band_output
from mushroom.aims.input import get_path_ksymbols, read_control
from mushroom.aims.stdout import StdOut
from mushroom.core.kpoints import KPathLinearizer
from mushroom.librpa import read_quasi_particle_energies_stdout


ROOT = Path(__file__).resolve().parent
MARKER_SIZE = 60
BAND_WINDOW = (-15, 40)


def apply_style():
    """Apply the style used by deliver/_paper_overleaf/figures."""
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "mathtext.fontset": "cm",
        "font.size": 16,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "legend.frameon": True,
        "legend.fancybox": True,
        "legend.framealpha": 1.0,
        "savefig.dpi": 300,
        "savefig.transparent": False,
    })


def energy_reference(bands, ref):
    if ref == "vbm":
        return bands.vbm
    if ref == "cbm":
        return bands.cbm
    return bands.vbm_sp_kp[0, 0]  # VBM at the first k-point


def bands_in_window(bands, vbm):
    relative = bands.eigen[0] - vbm
    finite = np.isfinite(relative)
    inside = (~finite) | (
        (relative >= BAND_WINDOW[0]) & (relative <= BAND_WINDOW[1])
    )
    return np.flatnonzero(np.any(finite, axis=0) & np.all(inside, axis=0))


def grid_points(kpath, grid_bands, grid_kpoints, ref, band_indices):
    x, y = [], []
    for ik_grid, band_positions in enumerate(kpath.locate(grid_kpoints)):
        for band_x in band_positions or []:
            x.extend([band_x] * len(band_indices))
            y.extend(grid_bands.eigen[0, ik_grid, band_indices] - ref)
    return np.asarray(x), np.asarray(y)


def plot_aims(ax, reciprocal_lattice, directory, ref):
    band_files = sorted(directory.glob("GW_band10*.out"))
    if not band_files:
        raise FileNotFoundError(f"no GW_band10*.out files in {directory}")
    bands, kpoints = read_band_output(*band_files, unit="eV")
    bands += get_chemical_potential(directory / "aims.out")
    kpath = KPathLinearizer(kpoints, reciprocal_lattice)

    grid_bands, grid_kpoints = StdOut(directory / "aims.out").get_QP_bandstructure()
    zero = energy_reference(grid_bands, ref)
    for plotted, ib in enumerate(bands_in_window(bands, grid_bands.vbm)):
        ax.plot(kpath.x, bands.eigen[0, :, ib] - zero,
                color="k", ls="--", label="FHI-aims" if plotted == 0 else None)
    grid_indices = bands_in_window(grid_bands, grid_bands.vbm)
    ax.scatter(*grid_points(kpath, grid_bands, grid_kpoints, zero, grid_indices),
               color="k", marker=".", s=MARKER_SIZE)
    return kpath


def plot_librpa(ax, reciprocal_lattice, directory, ref):
    bands, kpoints = read_band_output(directory / "GW_band_spin_1.dat", unit="eV")
    kpath = KPathLinearizer(kpoints, reciprocal_lattice)
    grid_bands, grid_kpoints = read_quasi_particle_energies_stdout(directory / "LibRPA.out")
    zero = energy_reference(grid_bands, ref)
    color = (0.8, 0, 0)
    for plotted, ib in enumerate(bands_in_window(bands, grid_bands.vbm)):
        ax.plot(kpath.x, bands.eigen[0, :, ib] - zero,
                color=color, label="LibRPA" if plotted == 0 else None)
    grid_indices = bands_in_window(grid_bands, grid_bands.vbm)
    ax.scatter(*grid_points(kpath, grid_bands, grid_kpoints, zero, grid_indices),
               color=color, marker=".", s=MARKER_SIZE)
    return kpath


def aims_directory(material_dir):
    standard = material_dir / "aims"
    if list(standard.glob("GW_band10*.out")):
        return standard
    candidates = sorted(
        (d for d in material_dir.glob("aims*") if len(list(d.glob("GW_band10*.out"))) > 1),
        key=lambda d: len(list(d.glob("GW_band10*.out"))),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"no complete FHI-aims band output in {material_dir}")
    return candidates[0]


def plot_material(material_dir, frequency, ref, emin, emax, output_name):
    aims_dir = aims_directory(material_dir)
    librpa_dir = material_dir / f"librpa-{frequency}"
    reciprocal_lattice = get_recp_latt_from_geometry(aims_dir / "geometry.in")
    control = read_control(aims_dir / "control.in")
    symbols = get_path_ksymbols(control.get_output("band"))
    symbols = [r"$\Gamma$" if symbol == "G" else symbol for symbol in symbols]

    fig, ax = plt.subplots(figsize=(8, 7))
    kpath = plot_aims(ax, reciprocal_lattice, aims_dir, ref)
    plot_librpa(ax, reciprocal_lattice, librpa_dir, ref)
    ax.set_xlim(kpath.x[0], kpath.x[-1])
    ax.set_ylim(emin, emax)
    ax.set_xticks(kpath.special_x, labels=symbols)
    ax.set_ylabel("Energy [eV]")
    ax.set_title(material_dir.name)
    ax.axhline(0, color="k", ls=":")
    ax.xaxis.grid(color="k")
    ax.xaxis.set_tick_params(which="minor", bottom=False)
    ax.yaxis.set_minor_locator(MultipleLocator(1))
    ax.set_axisbelow(True)
    ax.legend(loc="best")
    fig.savefig(material_dir / output_name, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(material_dir / output_name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materials", nargs="*", help="materials to plot (default: all)")
    parser.add_argument("--frequency", choices=(16, 32), default=32, type=int,
                        help="LibRPA frequency grid (default: 32)")
    parser.add_argument("--ref", choices=("vbm", "vbm_0", "cbm"), default="vbm",
                        help="energy zero (default: vbm)")
    parser.add_argument("--emin", default=-15, type=float)
    parser.add_argument("--emax", default=30, type=float)
    parser.add_argument("--output", default="bandstructure.pdf",
                        help="output filename within each material folder")
    args = parser.parse_args()

    apply_style()
    names = args.materials or sorted(d.name for d in ROOT.iterdir() if d.is_dir())
    for name in names:
        material_dir = ROOT / name
        if not material_dir.is_dir():
            parser.error(f"unknown material: {name}")
        plot_material(material_dir, args.frequency, args.ref,
                      args.emin, args.emax, args.output)


if __name__ == "__main__":
    main()
