#!/usr/bin/env python3
"""Archive reviewed partial stage controls without claiming complete production evidence."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

from import_verified_inputs import checked_destination, file_item, json_bytes, sha256

REVIEWED_SPEC = "cbb5b200659835c08856b081cd0c1dc366c3e4cb33b929f46ae16d919b041d25"
CASES = {"mote2-table-gw", "inse-table-gw", "in2se3-table-gw", "mos2_ws2-table-gw",
         "tis3-table-gw", "gate-table-gw", "cuinp2se6-table-gw", "mose2-table-gw", "ws2-table-gw"}
CONTROL = re.compile(r"^(?:INPUT(?:_scf|_nscf)?|KPT(?:_scf|_nscf)?|STRU|librpa\.in|band_kpath_info|geometry\.in)$")
PRIVATE = re.compile(r"(?:/" + r"Users/|/data/" + r"home/|/home/|/mnt/|/scratch/|file:" + r"//|ssh:" + r"//)")
SCOPE = ("Partial recovered stage controls linked to the archived KS/EXX/GW spectrum hashes; "
         "directory association is not an immutable full production chain or a self-contained rerun bundle. "
         "Basis bindings, software identities and scientific acceptance are not changed by this import.")


def public_control(data: bytes, case_id: str, name: str) -> tuple[bytes, str]:
    text = data.decode("utf-8", errors="strict")
    if case_id == "mos2_ws2-table-gw" and name == "librpa.in":
        text, count = re.subn(r"(?m)^(\s*input_dir\s*=\s*)/data/" + r"home/[^\s]+(\s*)$",
                             r"\1./input_librpa/\2", text)
        if count > 1:
            raise ValueError("ambiguous private input_dir declarations")
    else:
        count = 0
    if PRIVATE.search(text):
        raise ValueError("unreviewed private path in control")
    return text.encode("utf-8"), ("absolute server input_dir redacted to ./input_librpa/; not a rerun bundle" if count else "none")


def stage_label(stage: dict) -> str:
    settings = stage.get("parsed_original_settings", {})
    if "librpa.in" in settings:
        task = settings["librpa.in"].get("task", "unknown")
        return "EXX" if task == "exx_band" else "GW" if task.startswith("g0w0") else "LibRPA"
    if "INPUT_scf" in settings:
        return "Archived SCF/NSCF controls"
    if "INPUT" in settings:
        return "SCF" if settings["INPUT"].get("calculation") == "scf" else "NSCF"
    return "Path export"


def import_stage_inputs(repo: Path, spec_path: Path, *, write: bool = False,
                        expected_spec_sha256: str = REVIEWED_SPEC) -> dict:
    repo, spec_path = repo.resolve(), spec_path.resolve()
    staged_root = spec_path.parent
    readset, writes, originals, reports = {}, {}, {}, []

    def read(path: Path) -> bytes:
        data = path.read_bytes()
        digest = sha256(data)
        if path in readset and readset[path] != digest:
            raise ValueError("source changed during validation")
        readset[path] = digest
        return data

    def staged(entry: dict) -> bytes:
        relative = PurePosixPath(entry["staged_relative_path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("staged path escapes root")
        path = staged_root.joinpath(*relative.parts)
        if (not path.resolve().is_relative_to(staged_root)
                or any(p.is_symlink() for p in (path, *path.parents) if p != staged_root and p.is_relative_to(staged_root))):
            raise ValueError("staged path is not an owned original file")
        if str(path) != entry["staged_path"]:
            raise ValueError("staged absolute/relative path mismatch")
        data = read(path)
        if (not entry.get("original_bytes_copied") or sha256(data) != entry["sha256"]
                or sha256(data) != entry["staged_sha256"] or len(data) != entry["size_bytes"]
                or len(data) != entry["staged_size_bytes"]):
            raise ValueError("whole original control SHA/size mismatch")
        return data

    spec_data = read(spec_path)
    if sha256(spec_data) != expected_spec_sha256:
        raise ValueError("spec is not the explicitly reviewed immutable version")
    spec = json.loads(spec_data)
    if (spec.get("schema_version") != 1 or spec.get("database_root") != str(repo)
            or len(spec.get("cases", [])) != 9 or {c["case_id"] for c in spec["cases"]} != CASES):
        raise ValueError("reviewed nine-case database identity mismatch")
    for case in spec["cases"]:
        if case.get("automatic_import_candidate") is not False or case.get("complete_handoff") is not False:
            raise ValueError("partial-stage import refuses promoted/full-handoff claims")
        current = case["current_record"]
        record_path = Path(current["source_path"])
        if not record_path.is_relative_to(repo) or record_path.is_symlink():
            raise ValueError("record escapes database")
        record_relative = record_path.relative_to(repo).as_posix()
        if checked_destination(repo, record_relative) != record_path:
            raise ValueError("record destination mismatch")
        original = read(record_path)
        record = json.loads(original)
        case_id = case["case_id"]
        if record.get("id") != case_id or record.get("dimension") != "2d":
            raise ValueError("current record identity mismatch")
        relative = record_path.parent.relative_to(repo).as_posix()
        receipt_path = relative + "/results/stage_input_receipt.json"
        prefix = relative + "/inputs/recovered/"
        if ("stage_input_receipt" in record["source"]
                and record["source"]["stage_input_receipt"] != receipt_path):
            raise ValueError("existing stage receipt pointer conflicts")
        prior = copy.deepcopy(record)
        prior["files"]["inputs"] = [f for f in prior["files"]["inputs"] if not f["path"].startswith(prefix)]
        prior["files"]["results"] = [f for f in prior["files"]["results"] if f["path"] != receipt_path]
        prior["source"].pop("stage_input_receipt", None)
        restored = original if sha256(original) == current["sha256"] else json_bytes(prior)
        if sha256(restored) != current["sha256"] or len(restored) != current["size_bytes"]:
            raise ValueError("current record differs from reviewed source beyond this import")
        spectra = []
        if {s["method"] for s in case["spectra"]} != {"KS", "EXX", "GW"} or len(case["spectra"]) != 3:
            raise ValueError("reviewed spectrum methods incomplete")
        for spectrum in case["spectra"]:
            reference = spectrum["record_result"]
            path = Path(reference["source_path"])
            if not path.is_relative_to(record_path.parent):
                raise ValueError("foreign spectrum record")
            item = next(f for f in record["files"]["results"] if repo / f["path"] == path)
            data = read(path)
            expected = spectrum.get("expected_sha256", spectrum.get("table_expected_sha256"))
            if (sha256(data) != expected or sha256(data) != spectrum["sha256"]
                    or sha256(data) != item["sha256"] or len(data) != spectrum["size_bytes"]
                    or len(data) != item["size_bytes"]):
                raise ValueError("current three-spectrum association mismatch")
            spectra.append({"method": spectrum["method"], "path": item["path"], "sha256": expected,
                            "size_bytes": len(data)})
        stages, new_inputs, seen = [], [], set()
        registered = {f["staged_path"]: f for f in case["original_files"]}
        for stage in case["stages"]:
            source_directory = stage["source_directory"]
            stage_id = sha256(source_directory.encode())[:12]
            label = stage_label(stage)
            controls = []
            for entry in stage["original_controls"]:
                name = PurePosixPath(entry["source_path"]).name
                if not CONTROL.fullmatch(name) or PurePosixPath(entry["source_path"]).parent.as_posix() != source_directory:
                    raise ValueError("foreign/unsupported stage control")
                if registered.get(entry["staged_path"]) != entry:
                    raise ValueError("stage control is not the registered original")
                data = staged(entry)
                public, transformation = public_control(data, case_id, name)
                target = prefix + stage_id + "/" + name
                if target in seen:
                    raise ValueError("duplicate stage control target")
                seen.add(target)
                writes[target] = public
                item = file_item("inputs", target, public, name)
                item.update({"original_sha256": entry["sha256"], "original_size_bytes": len(data),
                             "label": f"{label} / {name} (partial stage {stage_id})",
                             "transformation": transformation, "stage_id": stage_id,
                             "evidence_scope": SCOPE})
                new_inputs.append(item)
                controls.append({"name": name, "repository_path": target, "sha256": item["sha256"],
                                 "original_sha256": entry["sha256"], "original_size_bytes": len(data),
                                 "source_path_sha256": sha256(entry["source_path"].encode()),
                                 "transformation": transformation})
            stages.append({"id": stage_id, "label": label,
                           "source_directory_sha256": sha256(source_directory.encode()), "controls": controls,
                           "complete_stage_execution_verified": False})
        if not new_inputs:
            raise ValueError("no reviewed controls")
        receipt = {"schema_version": 1, "case_id": case_id, "scope": SCOPE,
                   "reviewed_recovery_spec_sha256": sha256(spec_data),
                   "record_before_sha256": current["sha256"], "spectra": spectra, "stages": stages,
                   "control_count": len(new_inputs), "full_runtime_handoff_verified": False,
                   "runtime_asset_seal_verified": False, "scientific_acceptance_reassessed": False,
                   "automatic_import_candidate_promoted": False,
                   "restrictions": case["production_chain_restrictions"],
                   "additional_restrictions": ["MoSe2/WS2 historical controls lack a full immutable control seal and ABF binding.",
                                              "Original full logs and additional remote EXX spectra were not re-read by this importer.",
                                              "MoS2/WS2 heterostructure retains 405 dangling reader links; manifests do not prove payload survival."]}
        receipt_data = json_bytes(receipt)
        if PRIVATE.search(receipt_data.decode()):
            raise ValueError("private path in public receipt")
        writes[receipt_path] = receipt_data
        result_item = file_item("results", receipt_path, receipt_data, "stage_input_receipt.json")
        existing_inputs = [f for f in record["files"]["inputs"] if f["path"].startswith(prefix)]
        existing_receipts = [f for f in record["files"]["results"] if f["path"] == receipt_path]
        if existing_inputs or existing_receipts or "stage_input_receipt" in record["source"]:
            if (record["source"].get("stage_input_receipt") != receipt_path
                    or sorted(existing_inputs, key=lambda f: f["path"]) != sorted(new_inputs, key=lambda f: f["path"])
                    or existing_receipts != [result_item]):
                raise ValueError("existing stage declarations are not the exact reviewed increment")
        for group, incoming in (("inputs", new_inputs), ("results", [result_item])):
            for item in incoming:
                previous = next((f for f in record["files"][group] if f["path"] == item["path"]), None)
                if previous is not None and previous != item:
                    raise ValueError("existing immutable stage declaration conflicts")
                if previous is None:
                    record["files"][group].append(item)
        record["source"]["stage_input_receipt"] = receipt_path
        originals[record_relative] = original
        writes[record_relative] = json_bytes(record)
        reports.append({"case_id": case_id, "controls": len(new_inputs), "stages": len(stages), "receipt": receipt_path})
    for relative, data in writes.items():
        destination = checked_destination(repo, relative)
        if destination.exists() and relative not in originals and read(destination) != data:
            raise ValueError("immutable stage destination conflicts")
    if write:
        for path, digest in readset.items():
            if sha256(path.read_bytes()) != digest:
                raise ValueError("readset changed before writing")
        for relative, data in writes.items():
            destination = checked_destination(repo, relative)
            if relative in originals and destination.read_bytes() != originals[relative]:
                raise ValueError("record changed before writing")
            if relative not in originals and destination.exists() and destination.read_bytes() != data:
                raise ValueError("destination changed before writing")
        for relative, data in sorted(writes.items(), key=lambda p: p[0] in originals):
            destination = checked_destination(repo, relative)
            if destination.exists() and destination.read_bytes() == data:
                continue
            if not destination.parent.is_dir():
                destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if relative in originals:
                    if destination.read_bytes() != originals[relative]:
                        raise ValueError("record changed before atomic replacement")
                    os.replace(temporary, destination)
                else:
                    try:
                        os.link(temporary, destination)
                    except FileExistsError:
                        if destination.read_bytes() != data:
                            raise ValueError("immutable atomic creation conflict")
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
    return {"write": write, "mode": "partial_stage_controls", "cases": reports,
            "controls": sum(r["controls"] for r in reports), "full_runtime_handoff_verified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--recovery-spec", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        result = import_stage_inputs(args.repo_root, args.recovery_spec, write=args.write)
    except (ValueError, KeyError, StopIteration, OSError) as exc:
        parser.exit(1, f"partial-stage import stopped: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
