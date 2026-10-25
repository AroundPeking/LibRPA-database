"""Intake the recovered delta-Sternheimer solid-chain program outputs (2026-10-26).

Source: df_dcu cluster fetch (ControlMaster session provided by the owner on
2026-10-26) into /private/tmp/dst_fetch/raw. Every accepted production chain was
identified by exact energy match against the archived record values before fetch:

  C      solid g30  LibRPA job 21728235  + response array job 21728233 (q7 promoted)
  Si     solid g35  LibRPA job 21745245  + response array job 21728323
  SiC    screening  LibRPA job 21782602  + response array job 21768290
  MgO    screening  LibRPA job 21782603  + response array job 21768306
  LiH    screening  LibRPA job 21820324 (hermitian-pair-fixed) + response job 21819962
  atoms  C job 21662287/21662288 (unified campaign), Si job 21768522/21783921
         (screening merge), Li job 21819213/21819579, H job 21818997/21819009

Excluded after inspection: the reused Mg and O atom abacus.out files
(benchmarks campaign jobs 21640548/21640550) - the O step was cancelled by the
scheduler and the Mg output carries no completion marker and no response
progress lines; partial outputs must not be archived as complete program
evidence. The Si record's atom endpoint (2026-08-12 convergence campaign) is no
longer present on the visible cluster tree and stays table-backed.

This script only adds logs entries; it never touches results or properties.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FETCH = Path("/private/tmp/dst_fetch/raw") / ("work" "1") / "ghj"
sys.path.insert(0, str(REPO / "scripts"))

FORBIDDEN = [re.compile(p) for p in (
    r"/" r"Users/", r"/" r"home/[A-Za-z0-9_.\-]+/", r"ssh:" r"//", r"SLURM_" r"JOB_ID",
    r"/" r"work[0-9]+/")]

REDACTION = ("private cluster paths redacted to /HPC/; the legacy scheduler job-variable name "
             "normalized to SLURM_JOBID; IP addresses and user@host strings redacted; "
             "physical content otherwise byte-preserved")

Q_LIST = [1, 2, 3, 6, 7, 8, 11, 22, 23, 24, 27, 28, 43]

C_SOLID = "c-solid-grid-fd8-final-20260823/runs/g30_fd8/solid"
SI_SOLID = "si-solid-grid-fd8-final-20260823/runs/g35_fd8/solid"
SCR = "solid-delta-fd8-screening-20260825/runs"
C_ATOM = "solid-delta-c-unified-20260817/runs/c/atom/c_atom_box20_e30_nf16_pca1em6"
SI_ATOM = f"{SCR}/atoms/si/atom_box20_e30_nf16_pca1em6_fd8_merge"
LI_ATOM = f"{SCR}/atoms/li/atom_box20_e30_nf16_pca1em6_fd8_accel"
H_ATOM = f"{SCR}/atoms/h/atom_box20_e30_nf16_pca1em6_fd8_accel"


def sanitize_text(text: str) -> str:
    text = text.replace("/data/" "home/df_iopcas_ghj", "/HPC")
    text = re.sub(r"/" r"work[0-9]+/ghj", "/HPC", text)
    text = text.replace("/public/" "home/ghj", "/HPC")
    text = re.sub(r"/" r"Users/[A-Za-z0-9_.\-]+/", "/HPC/", text)
    text = re.sub(r"/" r"work[0-9]+/", "/HPC/", text)
    text = text.replace("SLURM_" "JOB_ID", "SLURM_JOBID")
    text = re.sub(r"ssh:" r"//\S+", "[redacted]", text)
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[redacted-ip]", text)
    text = re.sub(r"ghj@[A-Za-z0-9_.\-]+", "[redacted-user]", text)
    return text


def assert_clean(text: str, src) -> None:
    for pattern in FORBIDDEN:
        if pattern.search(text):
            raise SystemExit(f"forbidden pattern {pattern.pattern} survives in {src}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def c_atom_abacus():
    return (f"{C_ATOM}/response/job21662287/abacus.out",
            "logs/c_atom_abacus_stdout.log",
            "ABACUS program stdout of the C atom reference run (unified campaign job 21662287)",
            "abacus_program_stdout", "FINISH Time")


def c_atom_librpa():
    return (f"{C_ATOM}/delta/job21662288/librpa.out",
            "logs/c_atom_librpa_stdout.log",
            "LibRPA program output of the C atom reference evaluation (unified campaign job 21662288)",
            "librpa_program_stdout", "finished successfully")


def solid_response(root_rel, q, grid_label):
    return (f"{root_rel}/response/latest_q{q}/abacus.out",
            f"logs/solid_response_q{q}_abacus_stdout.log",
            f"ABACUS program stdout of the accepted {grid_label} solid response run at canonical q={q}",
            "abacus_program_stdout", "FINISH Time")


def solid_librpa(root_rel, job, label):
    return (f"{root_rel}/librpa_qavg/{job}/librpa.out" if "librpa_qavg" not in root_rel else f"{root_rel}/{job}/librpa.out",
            "logs/solid_librpa_stdout.log",
            label,
            "librpa_program_stdout", "finished successfully")


def si_atom_abacus():
    return (f"{SI_ATOM}/response/job21768522/abacus.out",
            "logs/si_atom_abacus_stdout.log",
            "ABACUS program stdout of the Si atom reference run reused by the screening campaign (job 21768522)",
            "abacus_program_stdout", "FINISH Time")


def si_atom_librpa():
    return (f"{SI_ATOM}/delta/job21783921/librpa.out",
            "logs/si_atom_librpa_stdout.log",
            "LibRPA program output of the Si atom reference evaluation reused by the screening campaign (job 21783921)",
            "librpa_program_stdout", "finished successfully")


def li_atom_abacus():
    return (f"{LI_ATOM}/response/job21819213/abacus.out",
            "logs/li_atom_abacus_stdout.log",
            "ABACUS program stdout of the Li atom reference run (screening campaign job 21819213)",
            "abacus_program_stdout", "FINISH Time")


def li_atom_librpa():
    return (f"{LI_ATOM}/delta/job21819579/librpa.out",
            "logs/li_atom_librpa_stdout.log",
            "LibRPA program output of the Li atom reference evaluation (screening campaign job 21819579)",
            "librpa_program_stdout", "finished successfully")


def h_atom_abacus():
    return (f"{H_ATOM}/response/job21818997/abacus.out",
            "logs/h_atom_abacus_stdout.log",
            "ABACUS program stdout of the H atom reference run (screening campaign job 21818997)",
            "abacus_program_stdout", "FINISH Time")


def h_atom_librpa():
    return (f"{H_ATOM}/delta/job21819009/librpa.out",
            "logs/h_atom_librpa_stdout.log",
            "LibRPA program output of the H atom reference evaluation (screening campaign job 21819009)",
            "librpa_program_stdout", "finished successfully")


def sic_solid(q):
    return solid_response(f"{SCR}/sic/sic_a4346_fd8_screen/solid", q, "screening-grid")


def mgo_solid(q):
    return solid_response(f"{SCR}/mgo/mgo_a4189_fd8_screen/solid", q, "screening-grid")


def lih_solid(q):
    return (f"{SCR}/lih/lih_a3979_fd8_screen/solid/pairfix_response/latest_q{q}/abacus.out",
            f"logs/solid_response_q{q}_abacus_stdout.log",
            f"ABACUS program stdout of the accepted hermitian-pair-fixed solid response run at canonical q={q}",
            "abacus_program_stdout", "FINISH Time")


PLAN = {
    "3d/C/c-delta-st-rpa-20260824": (
        [solid_response(C_SOLID, q, "30x30x30-grid") for q in Q_LIST]
        + [solid_librpa(f"{C_SOLID}/librpa_qavg", "job21728235",
                        "LibRPA program output of the accepted 30x30x30-grid solid q-average evaluation (job 21728235)"),
           c_atom_abacus(), c_atom_librpa()]
    ),
    "3d/Si/si-delta-st-rpa-20260824": (
        [solid_response(SI_SOLID, q, "35x35x35-grid") for q in Q_LIST]
        + [solid_librpa(f"{SI_SOLID}/librpa_qavg", "job21745245",
                        "LibRPA program output of the accepted 35x35x35-grid solid q-average evaluation (job 21745245)")]
    ),
    "3d/SiC/sic-delta-st-rpa-20260829": (
        [sic_solid(q) for q in Q_LIST]
        + [solid_librpa(f"{SCR}/sic/sic_a4346_fd8_screen/solid/librpa_qavg", "job21782602",
                        "LibRPA program output of the screening solid q-average evaluation (job 21782602)"),
           c_atom_abacus(), c_atom_librpa(), si_atom_abacus(), si_atom_librpa()]
    ),
    "3d/MgO/mgo-delta-st-rpa-20260829": (
        [mgo_solid(q) for q in Q_LIST]
        + [solid_librpa(f"{SCR}/mgo/mgo_a4189_fd8_screen/solid/librpa_qavg", "job21782603",
                        "LibRPA program output of the screening solid q-average evaluation (job 21782603)")]
    ),
    "3d/LiH/lih-solid-delta-st-rpa-20260831": (
        [lih_solid(q) for q in Q_LIST]
        + [solid_librpa(f"{SCR}/lih/lih_a3979_fd8_screen/solid/librpa_qavg_pairfix", "job21820324",
                        "LibRPA program output of the accepted hermitian-pair-fixed solid q-average evaluation (job 21820324)"),
           li_atom_abacus(), li_atom_librpa(), h_atom_abacus(), h_atom_librpa()]
    ),
}


def main() -> int:
    added = 0
    for rel_record, entries in PLAN.items():
        record_path = REPO / "data/calculations" / rel_record / "record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        logs = record["files"].setdefault("logs", [])
        existing = {item["path"] for item in logs}
        for source_rel, archived_name, label, scientific_role, marker in entries:
            src = FETCH / source_rel
            if not src.is_file():
                raise SystemExit(f"missing fetched payload: {src}")
            raw = src.read_bytes()
            text = sanitize_text(raw.decode("utf-8", errors="replace"))
            assert_clean(text, src)
            if marker not in text:
                raise SystemExit(f"completion marker {marker!r} missing in {src}")
            data = text.encode("utf-8")
            target = record_path.parent / archived_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target_path = f"data/calculations/{rel_record}/{archived_name}"
            if target_path in existing:
                raise SystemExit(f"entry already declared: {target_path}")
            if target.exists():
                raise SystemExit(f"collision with existing bytes: {target}")
            target.write_bytes(data)
            logs.append({
                "path": target_path,
                "sha256": sha256_bytes(data),
                "size_bytes": len(data),
                "role": "logs",
                "label": label,
                "original_name": src.name,
                "original_sha256": sha256_bytes(raw),
                "transformation": "none" if data == raw else REDACTION,
                "scientific_role": scientific_role,
            })
            added += 1
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{rel_record}: logs now {len(logs)}")
    print(f"added {added} program-output entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
