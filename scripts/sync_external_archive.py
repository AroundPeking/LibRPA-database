#!/usr/bin/env python3
"""Convert newly pushed large payloads to the external archive in CI.

Intended to run on GitHub Actions after the validation workflows accept a
push to ``main``. The loop mirrors the reviewed manual go-live procedure:

1. ``plan`` every local-tier calculation payload - inputs, results, logs,
   and figures alike, regardless of size. Basis payloads and species
   bindings are never scanned, so the basis library stays in git.
2. ``upload`` the staged bytes to the Hugging Face dataset (token from the
   ``HF_TOKEN`` environment variable / Actions secret).
3. ``verify`` every URL (primary and mirror) before anything is rewritten.
4. ``apply`` the referenced tier and regenerate the catalog, indexes, and
   evidence reports, then print a marker so the calling workflow can commit.

Exit code 0 with ``nothing to do`` means no payload crossed the threshold;
the workflow then skips committing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO = "AroundPeking/LibRPA-database"
CONVERTIBLE_GROUPS = ("inputs", "results", "logs", "figures")


def _run(script: str, *arguments: str) -> str:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *arguments],
                            capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=8,
                        help="parallel URL downloads for the verify pass")
    parser.add_argument("--repo-id", default=DEFAULT_REPO)
    parser.add_argument("--paths-output", type=Path, default=None,
                        help="write the converted repository-relative paths here, one per line")
    args = parser.parse_args()

    url_base = f"https://huggingface.co/datasets/{args.repo_id}"
    backup_base = f"https://hf-mirror.com/datasets/{args.repo_id}"

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw-plan.json"
        plan_path = Path(tmp) / "plan.json"
        _run("externalize_files.py", "plan", "--all-payloads", "-o", str(raw))
        items = [item for item in json.loads(raw.read_text())
                 if item["group"] in CONVERTIBLE_GROUPS]
        if not items:
            print("external-archive sync: nothing to do")
            if args.paths_output:
                args.paths_output.write_text("")
            return 0
        print(f"external-archive sync: {len(items)} payload(s), "
              f"{sum(item['size_bytes'] for item in items) / 1e6:.1f} MB")
        plan_path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
        _run("externalize_files.py", "upload", "--plan", str(plan_path), "--repo-id", args.repo_id)
        _run("externalize_files.py", "verify", "--plan", str(plan_path),
             "--url-base", url_base, "--backup-base", backup_base,
             "--workers", str(args.workers))
        _run("externalize_files.py", "apply", "--plan", str(plan_path),
             "--url-base", url_base, "--backup-base", backup_base)

    _run("library.py", "--write-catalog")
    _run("build_indexes.py", "--write")
    _run("export_missing_evidence.py", "--write")
    shutil.copyfile(ROOT / "database" / "archive-completeness.json",
                    ROOT / "archive-completeness.json")
    print("external-archive-sync-committed")
    for item in items:
        print(f"converted {item['path']}")
    if args.paths_output:
        args.paths_output.write_text("".join(item["path"] + "\n" for item in items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
