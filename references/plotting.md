# Reference band plotting

`scripts/plot_bands.py` defines the database plotting input: one data row per
k-path point, with the first column as the cumulative path coordinate and every
remaining column as one band. The order of the energy columns is preserved.
Blank lines and lines beginning with `#` are ignored.

```text
# x  band_1  band_2  band_3
0.0  -2.1     1.4     3.8
0.5  -1.9     1.2     3.7
1.0  -2.0     1.3     3.9
```

Optional high-symmetry labels use JSON:

```json
{"ticks": [{"x": 0.0, "label": "Γ"}, {"x": 1.0, "label": "M"}]}
```

The command writes the figure and a same-stem JSON sidecar containing the
calculation ID, input/table SHA-256 values, and labels. Matplotlib is optional
for static validation; the parser and sidecar writer use only the Python
standard library.

```bash
python3 scripts/plot_bands.py bands.dat \
  --output figures/si-gw.png \
  --calculation-id si-paper-all_kpath \
  --input-sha256 <sha256-of-the-input-bundle> \
  --labels kpath.json
```

The plot is a display aid. It does not reorder bands across occupations or
decide whether a gap, RPA energy, or GW result is physically accepted.
