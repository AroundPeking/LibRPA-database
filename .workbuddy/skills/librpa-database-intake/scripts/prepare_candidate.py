#!/usr/bin/env python3
"""Build a read-only, hash-bound candidate receipt from a local LibRPA run."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_file(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
        raise ValueError(f"not a regular file inside source directory: {value}")
    return path


def parse_qp(data: bytes) -> dict:
    text = data.decode("utf-8", errors="replace")
    start = text.find("Printing quasi-particle energy [unit: eV]")
    end = text.find("libRPA finished successfully", start + 1)
    if start < 0 or end < 0:
        raise ValueError("complete QP table followed by LibRPA success marker not found")
    body = text[start:end]
    kpoint = re.search(r"spin\s+\d+,\s*k-point\s+\d+:\s*\(([^)]+)\)", body)
    if not kpoint:
        raise ValueError("QP k-point not found")
    rows = []
    for line in body.splitlines():
        parts = line.split()
        if len(parts) != 8 or not parts[0].isdigit():
            continue
        values = [float(value) for value in parts[1:]]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("nonfinite QP value")
        rows.append((int(parts[0]), *values))
    if not rows or [row[0] for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("QP states are empty, duplicated, or nonconsecutive")
    occupied = [row for row in rows if row[1] > 0]
    unoccupied = [row for row in rows if row[1] <= 0]
    if not occupied or not unoccupied:
        raise ValueError("QP occupations do not define occupied and unoccupied states")
    return {
        "k_point": [float(value.strip()) for value in kpoint.group(1).split(",")],
        "state_count": len(rows),
        "occupied_states": len(occupied),
        "unoccupied_states": len(unoccupied),
        "pbe_sampled_gap_ev": round(min(row[2] for row in unoccupied) - max(row[2] for row in occupied), 8),
        "g0w0_sampled_gap_ev": round(min(row[7] for row in unoccupied) - max(row[7] for row in occupied), 8),
        "program_finished_successfully": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--qp-log", required=True, help="Path relative to source-dir")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--atom-count", type=int, required=True)
    parser.add_argument("--nodes", type=int, required=True)
    parser.add_argument("--mpi-ranks", type=int, required=True)
    parser.add_argument("--omp-threads", type=int, required=True)
    parser.add_argument("--wall-time-seconds", type=int, required=True)
    parser.add_argument("--file", action="append", default=[], help="Additional evidence path relative to source-dir")
    args = parser.parse_args()
    root = Path(args.source_dir).resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("source-dir must be a real directory")
    qp_path = regular_file(root, args.qp_log)
    selected = sorted(set([args.qp_log, *args.file]))
    files = []
    for value in selected:
        path = regular_file(root, value)
        data = path.read_bytes()
        files.append({"path": value, "size_bytes": len(data), "sha256": digest(data)})
    candidate = {
        "schema_version": 1,
        "job_id": args.job_id,
        "qp_result": parse_qp(qp_path.read_bytes()),
        "performance": {
            "wall_time_seconds": args.wall_time_seconds,
            "nodes": args.nodes,
            "mpi_ranks": args.mpi_ranks,
            "omp_threads_per_rank": args.omp_threads,
        },
        "computational_scale": {"atom_count": args.atom_count},
        "files": files,
    }
    canonical = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    candidate["candidate_sha256"] = digest(canonical)
    print(json.dumps(candidate, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
