#!/usr/bin/env python3
"""Reject common private workstation and scheduler identifiers in a public skill."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FORBIDDEN = re.compile(
    r"(?:/" + r"Users/|/home/" + r"[A-Za-z0-9_.-]+|ssh:" + r"//|SLURM_" + r"JOB_ID|/work" + r"[0-9]/)"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    failures = []
    for path in args.root.rglob("*"):
        # The scanner and its tests contain the patterns they detect.
        if not path.is_file() or any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".sqlite", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            if FORBIDDEN.search(line):
                failures.append(f"{path}:{line_number}: {line.strip()}")
    if failures:
        print("private content found:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"public scan OK: {args.root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
