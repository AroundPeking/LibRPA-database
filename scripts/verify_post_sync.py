#!/usr/bin/env python3
"""Post-sync triple verification: HF bytes, clean git tree, live accessibility.

Owner-directed standing check (2026-10-26): every external-archive sync must be
followed by three verifications,

  1. HF really received the data - every referenced entry in record.json files
     changed since --base is fetched over HTTPS (main URL, then the backup
     mirror) and its bytes are checked against the declared SHA-256 and size.
  2. GitHub keeps no payload bytes - the tracked tree under data/calculations
     contains record.json manifests only (payloads live in the HF dataset).
  3. The website can access the data (--live) - entries in the deployed
     database/data.json resolve over HTTPS: referenced entries at their
     external URL, local-tier entries at the deployed site path.

Checks 1 and 2 run on every invocation; the external-archive-sync workflow
runs them after each externalization commit. Check 3 runs when --live is
given (after a Pages deploy). Exit code is non-zero if any check fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GROUPS = ("inputs", "results", "logs", "figures")
UA = "Mozilla/5.0 (compatible; LibRPA-database-post-sync-verify/1.0)"

# Network engine: curl subprocess. A hard --max-time wall clock is the only
# reliable cap on this workstation's network (urllib can lose its timeout on
# redirect chains and park a connect in SYN_SENT forever; some hosts are
# reachable only via the proxy while others only directly - curl inherits the
# environment proxy settings and follows the CDN redirects). curl's exit code
# alone says nothing about HTTP status: the backup mirror answers sustained
# request sequences with HTTP 429 error pages that transfer "successfully",
# so only an explicit 200 counts as payload bytes. 429 answers back off
# exponentially and never count toward the host
# circuit breaker - they mean "slow down", not "host down". Transport
# failures (curl rc != 0) do count: three of them skip the host for the rest
# of the run, and the other candidate URL serves the same dataset bytes.
HOST_FAILURES: dict[str, int] = {}
MAX_HOST_FAILURES = 3
LAST_HIT: dict[str, float] = {}
REQUEST_DELAY = 1.0
RETRY_SLEEPS = (5.0, 15.0, 45.0, 90.0)
RATE_LIMITED_OUT = False


def _host(url: str) -> str:
    return urllib.request.urlparse(url).hostname or ""


def _host_dead(host: str) -> bool:
    return HOST_FAILURES.get(host, 0) >= MAX_HOST_FAILURES


def _pace(host: str) -> None:
    wait = REQUEST_DELAY - (time.monotonic() - LAST_HIT.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    LAST_HIT[host] = time.monotonic()


def _parse_code(text: str) -> int:
    try:
        return int(text.strip()[-3:])
    except ValueError:
        return 0


def _curl(url: str, max_time: int, extra: list[str]):
    """One paced curl run; returns (exit_code, http_code)."""
    host = _host(url)
    _pace(host)
    result = subprocess.run(["curl", "-sS", "-L", "--max-time", str(max_time),
                             "-A", UA, "-w", "%{http_code}", *extra, url],
                            capture_output=True, text=True)
    return result.returncode, _parse_code(result.stdout or "")


def _backoff(attempt: int) -> None:
    if attempt < len(RETRY_SLEEPS):
        time.sleep(RETRY_SLEEPS[attempt])


def fetch(url: str, max_time: int = 90):
    """Return the HTTP 200 response bytes or None; never raises."""
    global RATE_LIMITED_OUT
    host = _host(url)
    last = "no attempt"
    for attempt in range(1 + len(RETRY_SLEEPS)):
        if _host_dead(host):
            return None
        with tempfile.NamedTemporaryFile(prefix="librpa-verify-", delete=False) as handle:
            scratch = Path(handle.name)
        try:
            rc, code = _curl(url, max_time, ["-o", str(scratch)])
            body = scratch.read_bytes() if rc == 0 else None
        finally:
            scratch.unlink(missing_ok=True)
        if rc == 0 and code == 200 and body is not None:
            HOST_FAILURES[host] = 0
            return body
        last = f"curl rc={rc}, http={code}"
        if rc == 0 and code == 429:
            print(f"  rate limited (http 429), backing off: {url}", flush=True)
            _backoff(attempt)
            continue
        if rc != 0:
            HOST_FAILURES[host] = HOST_FAILURES.get(host, 0) + 1
        if attempt < len(RETRY_SLEEPS):
            time.sleep(RETRY_SLEEPS[attempt])
    if "http=429" in last:
        RATE_LIMITED_OUT = True
    print(f"  fetch failed ({last}): {url}")
    return None


def head_status(url: str, max_time: int = 45) -> int:
    host = _host(url)
    code = 0
    for attempt in range(1 + len(RETRY_SLEEPS)):
        if _host_dead(host):
            return 0
        rc, code = _curl(url, max_time, ["-I", "-o", "/dev/null"])
        if rc == 0 and code == 429:
            _backoff(attempt)
            continue
        if rc == 0 and code:
            if code == 200:
                HOST_FAILURES[host] = 0
            return code
        if rc != 0:
            HOST_FAILURES[host] = HOST_FAILURES.get(host, 0) + 1
        if attempt < len(RETRY_SLEEPS):
            time.sleep(RETRY_SLEEPS[attempt])
    return code


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], check=True,
                            capture_output=True, text=True)
    return result.stdout


def changed_record_paths(root: Path, base: str) -> list[str]:
    out = git(root, "diff", "--name-only", f"{base}..HEAD")
    return [line.strip() for line in out.splitlines()
            if line.strip().startswith("data/calculations/")
            and line.strip().endswith("/record.json")]


def iter_entries(record: dict):
    files = record.get("files", {})
    for group in GROUPS:
        for item in files.get(group, []):
            yield item


def verify_hashes(root: Path, base: str) -> bool:
    paths = changed_record_paths(root, base)
    checked = failed = 0
    for relative in paths:
        if RATE_LIMITED_OUT:
            print("hash check ABORTED: the mirror answered every rate-limit backoff with 429;")
            print("rerun once its quota refills, or from a network that reaches huggingface.co directly")
            return False
        record = json.loads((root / relative).read_text(encoding="utf-8"))
        for item in iter_entries(record):
            if item.get("tier") != "referenced":
                continue
            data, source = None, None
            for candidate in (item.get("external_url"), item.get("external_url_backup")):
                if not candidate:
                    continue
                data = fetch(candidate)
                if data is not None:
                    source = candidate
                    break
            if data is None:
                print(f"HASH FAIL (unreachable): {item.get('path')}")
                failed += 1
                continue
            if (hashlib.sha256(data).hexdigest() != item.get("sha256")
                    or len(data) != item.get("size_bytes")):
                print(f"HASH FAIL: {item.get('path')} via {source}")
                failed += 1
            else:
                checked += 1
            if (checked + failed) % 25 == 0:
                print(f"  ... {checked + failed} entries checked ({failed} failed so far)")
    if checked == 0 and failed == 0:
        print(f"hash check: no referenced entries in records changed since {base}; nothing to verify")
        return True
    verdict = "OK" if failed == 0 else "FAILED"
    print(f"hash check {verdict}: {checked} referenced entries byte-verified"
          + (f", {failed} failed" if failed else ""))
    return failed == 0


def tree_offenders(root: Path) -> list[str]:
    out = git(root, "ls-files", "--", "data/calculations")
    return [line.strip() for line in out.splitlines()
            if line.strip() and not line.strip().endswith("/record.json")]


def verify_tree(root: Path) -> bool:
    offenders = tree_offenders(root)
    if offenders:
        print("tree check FAILED: payload bytes tracked under data/calculations:")
        for path in offenders[:20]:
            print(f"  {path}")
        if len(offenders) > 20:
            print(f"  ... and {len(offenders) - 20} more")
        return False
    print("tree check OK: data/calculations tracks record.json manifests only")
    return True


def live_entry_url(site: str, item: dict) -> str:
    if item.get("tier") == "referenced":
        return item.get("external_url") or ""
    return f"{site.rstrip('/')}/{item.get('path', '')}"


def verify_live(site: str, sample: int | None, full: bool) -> bool:
    payload = fetch(f"{site.rstrip('/')}/database/data.json")
    if payload is None:
        print("live check FAILED: deployed data.json is unreachable")
        return False
    data = json.loads(payload)
    entries = [item for record in data.get("calculations", [])
               for item in iter_entries(record)]
    if not entries:
        print("live check FAILED: deployed data.json has no file entries")
        return False
    selected = entries if full else random.sample(entries, min(sample or 40, len(entries)))
    failed = []
    for item in selected:
        url = live_entry_url(site, item)
        status = head_status(url)
        if status != 200 and item.get("tier") == "referenced":
            backup = item.get("external_url_backup")
            if backup:
                status = head_status(backup)
        if status != 200:
            failed.append((item.get("path"), status, url))
    mode = "all" if full else f"sample of {len(selected)}/{len(entries)}"
    if failed:
        print(f"live check FAILED ({mode}): {len(failed)} entries unreachable:")
        for path, status, url in failed[:20]:
            print(f"  {status} {path} -> {url}")
        return False
    print(f"live check OK ({mode}): every checked entry resolves over HTTPS")
    return True


def main() -> int:
    global REQUEST_DELAY
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--base", default="HEAD~1",
                        help="git range base for the hash check (default HEAD~1, "
                             "i.e. the pushed data commit when HEAD is the sync commit)")
    parser.add_argument("--skip-hash", action="store_true")
    parser.add_argument("--live", metavar="SITE_ROOT",
                        help="also verify the deployed site, e.g. https://.../LibRPA-database")
    parser.add_argument("--live-sample", type=int, default=40)
    parser.add_argument("--live-all", action="store_true")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY,
                        help="minimum seconds between requests to one host "
                             "(the backup mirror rate-limits rapid sequences)")
    args = parser.parse_args()

    REQUEST_DELAY = max(0.0, args.delay)

    root = args.root.resolve()
    results = []
    if not args.skip_hash:
        results.append(("hash", verify_hashes(root, args.base)))
    results.append(("tree", verify_tree(root)))
    if args.live:
        results.append(("live", verify_live(args.live, args.live_sample, args.live_all)))
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
