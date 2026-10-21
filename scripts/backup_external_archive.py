#!/usr/bin/env python3
"""Snapshot the external archive and stage it for an off-site backup.

Downloads the whole Hugging Face dataset into a temporary directory,
cross-checks every referenced payload declared by the repository records
(path present in the snapshot, SHA-256 identical), and writes a dated
tarball plus manifest into the target directory. The intended routine is
to run this periodically and store the tarball on an independent service
(for example Baidu netdisk); the repository's git history is not a
substitute for an off-site backup of the archive.

Exit code is nonzero if any declared payload is missing from the snapshot
or fails its hash check, so a silently truncated backup never looks
successful.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
except ImportError:  # the caller needs an interpreter with huggingface_hub
    snapshot_download = None

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO = "AroundPeking/LibRPA-database"


def _referenced_entries() -> list[dict]:
    entries = []
    for record_path in sorted((ROOT / "data" / "calculations").rglob("record.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        for group, items in (record.get("files") or {}).items():
            for item in items or []:
                if item.get("tier") == "referenced":
                    entries.append({"path": item["path"], "sha256": item.get("sha256"),
                                    "size_bytes": item.get("size_bytes"),
                                    "record": record_path.relative_to(ROOT).as_posix()})
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-id", default=DEFAULT_REPO)
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "Downloads",
                        help="where the dated tarball and manifest are written")
    parser.add_argument("--verify-only", action="store_true",
                        help="skip the tarball; only download and hash-check")
    args = parser.parse_args()

    if snapshot_download is None:
        print("huggingface_hub is not installed in this interpreter.", file=sys.stderr)
        print("Run with an environment that has it, e.g. the project venv.", file=sys.stderr)
        return 2
    entries = _referenced_entries()
    if not entries:
        print("no referenced payloads are declared; nothing to back up")
        return 0

    with tempfile.TemporaryDirectory(prefix="librpa-backup-") as tmp:
        snapshot = Path(tmp) / "snapshot"
        print(f"downloading {args.repo_id} ({len(entries)} declared payloads) ...")
        snapshot_download(repo_id=args.repo_id, repo_type="dataset", local_dir=str(snapshot))
        failures = 0
        for entry in entries:
            local = snapshot / entry["path"]
            if not local.is_file():
                print(f"MISSING   {entry['path']}")
                failures += 1
                continue
            digest = hashlib.sha256(local.read_bytes()).hexdigest()
            if digest != entry["sha256"]:
                print(f"MISMATCH  {entry['path']}")
                failures += 1
        if failures:
            print(f"{failures} declared payload(s) missing or corrupted in the snapshot; "
                  "the archive backup is NOT complete", file=sys.stderr)
            return 1
        print(f"snapshot verified: {len(entries)}/{len(entries)} declared payloads hash-match")

        manifest = {
            "backup_date": datetime.date.today().isoformat(),
            "repo_id": args.repo_id,
            "payloads": len(entries),
            "total_bytes": sum(entry["size_bytes"] or 0 for entry in entries),
            "entries": entries,
        }
        if args.verify_only:
            return 0
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.date.today().strftime("%Y%m%d")
        manifest_path = args.output_dir / f"librpa-external-backup-{stamp}.manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        tarball = args.output_dir / f"librpa-external-backup-{stamp}.tar.gz"
        subprocess.run(["tar", "-czf", str(tarball), "-C", str(snapshot), "data"], check=True)
        size = tarball.stat().st_size
        print(f"backup ready: {tarball} ({size / 1e6:.1f} MB)")
        print(f"manifest:     {manifest_path}")
        print("store the tarball on an independent service (e.g. Baidu netdisk); "
              "verify the SHA-256 recorded in the manifest after any restore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
