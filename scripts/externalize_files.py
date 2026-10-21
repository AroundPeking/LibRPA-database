#!/usr/bin/env python3
"""Move large archived evidence files to the external object store.

The repository keeps git + files + validator as the source of truth.  For
payloads that are too large for GitHub Pages, a file entry can switch to the
``referenced`` tier: the bytes live in an external store (Hugging Face
Datasets by default, with hf-mirror.com as the China backup), while
record.json keeps the repository path as identity plus the SHA-256 and byte
size as the integrity anchor.

Subcommands
-----------
plan     Identify candidate files (explicit paths or a size threshold) and
         write a conversion plan with record/group/index coordinates.
stage    Verify each file's declared SHA-256 against the local bytes and copy
         them into a staging tree that mirrors repository-relative paths.
apply    Rewrite the matching record.json entries to the referenced tier with
         direct URLs derived from --url-base (and --backup-base).  Working
         tree only; review with git diff before committing.
unapply  Restore the local-tier entry shape (removes tier/URL fields).
verify   Download each external URL and re-check SHA-256 of the served bytes;
         the go-live gate before any ``git rm`` of local copies.
upload   Push the staged tree to a Hugging Face dataset repository via
         huggingface_hub (requires the ``hf`` Python package and a token).

The local bytes are never removed by this script.  After ``verify`` passes,
removal is a reviewed ``git rm`` decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _load_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _dump_json(path: Path, value) -> None:
    # Record files use ensure_ascii=False + indent=2; keep that convention
    # so untouched keys re-serialize byte-identically.
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _record_for(repo_relative: str) -> Path:
    parts = PurePosixPath(repo_relative).parts
    # Record directory is always data/calculations/<dimension>/<material>/<id>;
    # payloads may nest below it (inputs/recovered/stage/..., logs/...).
    if len(parts) < 6 or parts[:2] != ("data", "calculations"):
        raise SystemExit(f"not a calculation payload path: {repo_relative}")
    record = ROOT.joinpath(*parts[:5], "record.json")
    if not record.is_file():
        raise SystemExit(f"owning record not found: {record}")
    return record


def _locate(record_path: Path, repo_relative: str, record=None):
    if record is None:
        record = _load_json(record_path)
    for group, entries in (record.get("files") or {}).items():
        for index, entry in enumerate(entries or []):
            if entry.get("path") == repo_relative:
                return record, group, index, entry
    raise SystemExit(f"{repo_relative} is not declared in {record_path}")


def _url(base: str, repo_relative: str) -> str:
    base = base.rstrip("/")
    segment = "/".join(urllib.parse.quote(part, safe="") for part in PurePosixPath(repo_relative).parts)
    return f"{base}/resolve/main/{segment}"


def build_plan(paths: list[str], min_size_mb: float, all_payloads: bool = False) -> list[dict]:
    # Calculation payload groups that may move to the referenced tier. Basis
    # payloads under data/elements are never scanned and species bindings are
    # never referenced; acceptance gates read referenced evidence through the
    # hash-verifying resolver in library.py, so evidence files may convert.
    convertible = {"inputs", "results", "logs", "figures"}
    candidates = []
    if paths:
        candidates = [ROOT / p for p in paths]
    elif all_payloads or min_size_mb > 0:
        threshold = 0 if all_payloads else int(min_size_mb * 1024 * 1024)
        root_data = ROOT / "data" / "calculations"
        # record.json files are the repository index, never payloads.
        candidates = [p for p in sorted(root_data.rglob("*"))
                      if p.is_file() and p.name != "record.json" and p.stat().st_size >= threshold]
    plan = []
    for full in candidates:
        repo_relative = full.relative_to(ROOT).as_posix()
        record_path = _record_for(repo_relative)
        record, group, index, entry = _locate(record_path, repo_relative)
        if group not in convertible:
            if paths:
                raise SystemExit(f"{repo_relative}: group '{group}' cannot move to the referenced tier")
            continue
        size = full.stat().st_size
        declared = entry.get("size_bytes")
        if declared is not None and declared != size:
            raise SystemExit(f"{repo_relative}: declared size_bytes {declared} != on-disk {size}")
        digest = _digest(full)
        if entry.get("sha256") != digest:
            raise SystemExit(f"{repo_relative}: declared sha256 does not match local bytes")
        plan.append({
            "path": repo_relative,
            "record": record_path.relative_to(ROOT).as_posix(),
            "group": group,
            "index": index,
            "sha256": digest,
            "size_bytes": size,
        })
    return plan


def read_plan(argument: str) -> list[dict]:
    if argument == "-":
        return json.load(sys.stdin)
    return _load_json(Path(argument))


def cmd_stage(plan: list[dict], dest: Path) -> int:
    for item in plan:
        full = ROOT / item["path"]
        if not full.is_file():
            raise SystemExit(f"missing local bytes: {item['path']}")
        digest = _digest(full)
        if digest != item["sha256"]:
            raise SystemExit(f"sha256 drift before staging: {item['path']}")
        target = dest / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(full, target)
        print(f"staged {item['path']} ({item['size_bytes']} bytes)")
    print(f"staged {len(plan)} file(s) into {dest}")
    return 0


def cmd_apply(plan: list[dict], url_base: str, backup_base: str | None) -> int:
    if not url_base.startswith("https://"):
        raise SystemExit("--url-base must be an https URL (publish gate rejects anything else)")
    # One in-memory snapshot per record file: _locate re-reads the record from
    # disk on every call, so per-item loads would silently drop the rewrite of
    # every later plan item that shares a record with an earlier one.
    records: dict[Path, dict] = {}
    for item in plan:
        record_path = ROOT / item["record"]
        record = records.get(record_path)
        if record is None:
            record = _load_json(record_path)
            records[record_path] = record
        _, group, index, entry = _locate(record_path, item["path"], record)
        if entry.get("sha256") != item["sha256"] or entry.get("size_bytes") != item["size_bytes"]:
            raise SystemExit(f"{item['path']}: record identity drifted from the plan; re-run plan")
        entry["tier"] = "referenced"
        entry["external_url"] = _url(url_base, item["path"])
        if backup_base:
            if not backup_base.startswith("https://"):
                raise SystemExit("--backup-base must be an https URL")
            entry["external_url_backup"] = _url(backup_base, item["path"])
        print(f"applied referenced tier: {item['path']}")
    for record_path, record in records.items():
        _dump_json(record_path, record)
    print(f"rewrote {len(records)} record file(s); review with git diff before committing")
    return 0


def cmd_unapply(paths: list[str]) -> int:
    for repo_relative in paths:
        record_path = _record_for(repo_relative)
        record, _group, _index, entry = _locate(record_path, repo_relative)
        if entry.pop("tier", None) is None and "external_url" not in entry:
            print(f"already local: {repo_relative}")
            continue
        entry.pop("external_url", None)
        entry.pop("external_url_backup", None)
        _dump_json(record_path, record)
        print(f"restored local tier: {repo_relative}")
    return 0


def _verify_one(url: str, expected: str) -> str:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "payload"
            with urllib.request.urlopen(url, timeout=180) as response, local.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            digest = _digest(local)
        return f"OK  {url}" if digest == expected else f"SHA-256 MISMATCH  {url}"
    except Exception as exc:  # noqa: BLE001 - report every URL, then fail
        return f"UNREACHABLE  {url}  ({exc})"


def cmd_verify(plan: list[dict], url_base: str, backup_base: str | None, workers: int = 1) -> int:
    jobs = []
    for item in plan:
        jobs.append((_url(url_base, item["path"]), item["sha256"]))
        if backup_base:
            jobs.append((_url(backup_base, item["path"]), item["sha256"]))
    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            lines = list(pool.map(lambda job: _verify_one(*job), jobs))
    else:
        lines = [_verify_one(*job) for job in jobs]
    failures = 0
    for line in lines:
        print(line, flush=True)
        if not line.startswith("OK"):
            failures += 1
    if failures:
        print(f"{failures} verification failure(s); do not remove local bytes", file=sys.stderr)
        return 1
    print(f"verified {len(plan)} file(s) at {url_base}")
    return 0


def cmd_upload(plan: list[dict], repo_id: str, bulk: bool = False) -> int:
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("huggingface_hub is not installed in this interpreter.", file=sys.stderr)
        print("Install it (pip install huggingface_hub) and log in (huggingface-cli login)", file=sys.stderr)
        print("or upload the staged tree with any S3-compatible client.", file=sys.stderr)
        return 2
    api = HfApi()
    who = api.whoami()
    if who.get("name") != repo_id.split("/")[0]:
        raise SystemExit(f"logged in as {who.get('name')!r}, but the dataset namespace is {repo_id.split('/')[0]!r}")
    api.create_repo(repo_id, repo_type="dataset", private=False, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "tree"
        cmd_stage(plan, dest)
        if bulk:
            # One folder upload = one dataset commit for the whole batch;
            # huggingface_hub parallelizes the small-file transfers itself.
            api.upload_folder(folder_path=str(dest),
                              repo_id=repo_id, repo_type="dataset",
                              commit_message=f"bulk externalize {len(plan)} payloads")
            print(f"uploaded {len(plan)} file(s) to dataset {repo_id} (bulk)")
            return 0
        for item in plan:
            # One upload per file preserves the exact repository-relative
            # path; each upload is resumable on its own.
            api.upload_file(path_or_fileobj=str(dest / item["path"]),
                            path_in_repo=item["path"],
                            repo_id=repo_id, repo_type="dataset")
            print(f"uploaded {item['path']}")
    print(f"uploaded {len(plan)} file(s) to dataset {repo_id}")
    return 0


def main() -> int:
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="list candidate files and write a conversion plan")
    plan_cmd.add_argument("--paths", nargs="*", default=[], help="explicit repository-relative file paths")
    plan_cmd.add_argument("--min-size-mb", type=float, default=0.0, help="collect every payload at or above this size")
    plan_cmd.add_argument("--all-payloads", action="store_true",
                          help="collect every local-tier calculation payload regardless of size")
    plan_cmd.add_argument("-o", "--output", default="-", help="plan file ('-' for stdout)")

    stage_cmd = sub.add_parser("stage", help="verify local bytes and copy them into a staging tree")
    stage_cmd.add_argument("--plan", required=True)
    stage_cmd.add_argument("--dest", type=Path, required=True)

    apply_cmd = sub.add_parser("apply", help="rewrite record entries to the referenced tier")
    apply_cmd.add_argument("--plan", required=True)
    apply_cmd.add_argument("--url-base", required=True, help="e.g. https://huggingface.co/datasets/<ns>/<name>")
    apply_cmd.add_argument("--backup-base", help="e.g. https://hf-mirror.com/datasets/<ns>/<name>")

    unapply_cmd = sub.add_parser("unapply", help="restore local-tier entry shape")
    unapply_cmd.add_argument("--paths", nargs="+", required=True)

    verify_cmd = sub.add_parser("verify", help="download external URLs and re-check SHA-256")
    verify_cmd.add_argument("--plan", required=True)
    verify_cmd.add_argument("--url-base", required=True)
    verify_cmd.add_argument("--backup-base")
    verify_cmd.add_argument("--workers", type=int, default=1,
                            help="parallel URL downloads (1 = sequential)")

    upload_cmd = sub.add_parser("upload", help="push staged files to a Hugging Face dataset")
    upload_cmd.add_argument("--plan", required=True)
    upload_cmd.add_argument("--repo-id", required=True, help="dataset namespace/name")
    upload_cmd.add_argument("--bulk", action="store_true",
                            help="push the staged tree as one folder upload instead of per-file commits")

    args = parser.parse_args()
    ROOT = args.root.resolve()

    if args.command == "plan":
        plan = build_plan(args.paths, args.min_size_mb, all_payloads=args.all_payloads)
        text = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
        if args.output == "-":
            sys.stdout.write(text)
        else:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"wrote plan for {len(plan)} file(s) to {args.output}")
        return 0
    if args.command == "stage":
        return cmd_stage(read_plan(args.plan), args.dest)
    if args.command == "apply":
        return cmd_apply(read_plan(args.plan), args.url_base, args.backup_base)
    if args.command == "unapply":
        return cmd_unapply(args.paths)
    if args.command == "verify":
        return cmd_verify(read_plan(args.plan), args.url_base, args.backup_base, workers=args.workers)
    if args.command == "upload":
        return cmd_upload(read_plan(args.plan), args.repo_id, bulk=args.bulk)
    return 2


if __name__ == "__main__":
    sys.exit(main())
