# Scientific validation checklist

## Universal checks

- Identify the actual requested task from the program input, not the directory name.
- Require the scientific program's own successful completion marker.
- Treat scheduler state as resource evidence only.
- Count expected and parsed rows/q-points/frequencies; reject truncation and duplicates.
- Reject NaN, Inf, malformed numeric rows, inconsistent dimensions, and unexplained missing states.
- Bind each reported property to declared same-record evidence.
- Preserve spin, k-point, path, frequency, unit, reference energy, and occupation definitions.
- Verify INPUT/KPT/STRU/task controls and exact physical-basis association.
- Record executable and input hashes before proposing import.

## GW QP tables

- Locate the final `Printing quasi-particle energy [unit: eV]` block.
- Parse state index, occupation, mean-field energy, exchange-correlation terms, self-energy terms, and QP energy.
- Require consecutive state indices and finite columns.
- Derive occupied/unoccupied counts from recorded occupation.
- Derive the sampled gap from `min(unoccupied) - max(occupied)` separately for mean-field and QP energies.
- State the sampled k-point. For one regular-grid Γ point, label the value `sampled Γ` or `Γ-point regular-grid`; never use `fundamental gap` without global evidence.
- Require the LibRPA success marker after the parsed table.

## RPA correlation energies

- Verify the complete q-point and frequency integration expected by the task.
- Require final aggregation and finite correlation energy.
- Record whether the energy is total, per atom, per cell, or an energy difference.
- Reject intermediate single-frequency, single-q, or convergence-probe values as final results.

## Large systems without band figures

- Do not fabricate a band path or figure.
- Require atom count, AO/state count, occupied/unoccupied count, runtime, nodes, ranks, threads, and evidence.
- Display result files and completion evidence under `Results & evidence`.
- Display resources under `Computational scale & performance`.

## Candidate summary minimum fields

Include candidate digest, source run/job, workflow type, program success evidence, parsed completeness counts, primary observable and definition, inputs, PP/NAO/auxiliary provenance, software commit or executable hash, resources (cluster, nodes, CPUs, accelerators, wall time), `workflow.frontend` (abacus or fhi_aims), immutable file hashes, path sanitization status, limitations, and the exact yes/no approval question.

## Path sanitization check

Before proposing a candidate, scan all source files for private patterns:
- `/Users/<username>`, `/home/<username>`, `/work<N>/<username>` — must be replaced with `/HPC/`
- `SLURM_JOB_ID` — must be replaced with `SLURM_JOBID`
- `ssh://`, hostnames, IP addresses — must be removed or redacted

Report the sanitization status in the candidate summary. After sanitization, recompute file SHA-256 values and update the record accordingly.
