#!/usr/bin/env python3
"""Bind reviewed producer assets, preserving stage names and scientific limitations."""
from __future__ import annotations

import argparse
import copy
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
import os
import tempfile

from import_stage_inputs import REVIEWED_SPEC, PRIVATE, import_stage_inputs
from import_verified_inputs import asset_header, checked_destination, file_item, json_bytes, sha256

CASES = {"mote2-table-gw", "inse-table-gw", "in2se3-table-gw", "mos2_ws2-table-gw",
         "tis3-table-gw", "gate-table-gw", "cuinp2se6-table-gw"}
ROLES = {"pp": ("pseudopotentials", ".upf"), "nao": ("orbitals", ".orb"), "abf": ("auxiliary", ".abfs")}


def prepare(repo: Path, spec_path: Path, expected_spec_sha256: str = REVIEWED_SPEC) -> tuple[dict, dict, dict]:
    repo, spec_path = repo.resolve(), spec_path.resolve()
    readset = {}

    def read(path: Path) -> bytes:
        path = path.absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("readset path contains a symlink")
        data = path.read_bytes()
        identity = (sha256(data), len(data))
        if path in readset and readset[path] != identity:
            raise ValueError("source changed during asset validation")
        readset[path] = identity
        return data

    source_data = read(spec_path)
    if sha256(source_data) != expected_spec_sha256:
        raise ValueError("recovery spec changed from explicitly reviewed version")
    spec = json.loads(source_data)
    if spec.get("database_root") != str(repo):
        raise ValueError("foreign database root")
    # Capture every dependency of the exact reviewed stage-input validation,
    # including the two cases whose assets are not being bound in this import.
    for case in spec["cases"]:
        path = Path(case["current_record"]["source_path"])
        baseline = json.loads(read(checked_destination(repo, path.relative_to(repo).as_posix())))
        for item in baseline["files"]["inputs"]:
            read(checked_destination(repo, item["path"]))
        receipt_key = baseline.get("source", {}).get("stage_input_receipt")
        if receipt_key:
            read(checked_destination(repo, receipt_key))
        record_directory = path.parent.relative_to(repo).as_posix()
        expected_receipt = checked_destination(repo, record_directory + "/results/stage_input_receipt.json")
        if expected_receipt.exists():
            read(expected_receipt)
        for spectrum in case["spectra"]:
            path = Path(spectrum["record_result"]["source_path"])
            read(checked_destination(repo, path.relative_to(repo).as_posix()))
        for stage in case["stages"]:
            stage_id = sha256(stage["source_directory"].encode())[:12]
            for entry in stage["original_controls"]:
                name = PurePosixPath(entry["source_path"]).name
                target = checked_destination(repo, record_directory + "/inputs/recovered/" + stage_id + "/" + name)
                if target.exists():
                    read(target)
                path = Path(entry["staged_path"])
                if not path.is_relative_to(spec_path.parent):
                    raise ValueError("stage control escapes owned source")
                read(path)
    import_stage_inputs(repo, spec_path, expected_spec_sha256=expected_spec_sha256)
    cases = [c for c in spec["cases"] if c["case_id"] in CASES]
    if len(cases) != len(CASES):
        raise ValueError("reviewed seven-case set incomplete")
    writes, report = {}, []

    def original(entry):
        path = Path(entry["staged_path"])
        if (not path.is_relative_to(spec_path.parent) or not path.resolve().is_relative_to(spec_path.parent)
                or any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(spec_path.parent))):
            raise ValueError("staged file escapes owned source")
        data = read(path)
        if sha256(data) != entry["sha256"] or len(data) != entry["size_bytes"] or not entry.get("original_bytes_copied"):
            raise ValueError("original asset/receipt SHA or size mismatch")
        return data

    for case in cases:
        record_path = Path(case["current_record"]["source_path"])
        relative = record_path.relative_to(repo).as_posix()
        checked_destination(repo, relative)
        before = read(record_path)
        record = json.loads(before)
        if record["id"] != case["case_id"] or record["species"]:
            raise ValueError("record identity changed or species already bound")
        receipt_key = record.get("source", {}).get("stage_input_receipt")
        if not receipt_key:
            raise ValueError("reviewed stage inputs must already be archived")
        receipt_data = read(checked_destination(repo, receipt_key))
        receipt = json.loads(receipt_data)
        receipt_item = next(f for f in record["files"]["results"] if f["path"] == receipt_key)
        if sha256(receipt_data) != receipt_item["sha256"] or receipt["record_before_sha256"] != case["current_record"]["sha256"]:
            raise ValueError("stage receipt identity mismatch")
        for item in record["files"]["inputs"]:
            public = read(checked_destination(repo, item["path"]))
            if sha256(public) != item["sha256"] or len(public) != item["size_bytes"]:
                raise ValueError("archived stage input SHA/size mismatch")
        prior = copy.deepcopy(record)
        prior["files"]["inputs"] = []
        prior["files"]["results"] = [f for f in prior["files"]["results"] if f["path"] != receipt_key]
        prior["source"].pop("stage_input_receipt")
        if sha256(json_bytes(prior)) != case["current_record"]["sha256"]:
            raise ValueError("record differs beyond reviewed stage input import")
        for spectrum in case["spectra"]:
            ref = spectrum["record_result"]
            path = Path(ref["source_path"])
            if not path.is_relative_to(record_path.parent):
                raise ValueError("foreign spectrum")
            expected = spectrum.get("expected_sha256", spectrum.get("table_expected_sha256"))
            item = next(f for f in record["files"]["results"] if repo / f["path"] == path)
            if sha256(read(checked_destination(repo, path.relative_to(repo).as_posix()))) != expected or item["sha256"] != expected:
                raise ValueError("selected spectrum identity changed")
        entries = {e["staged_path"]: e for e in case["original_files"]}
        sealed = []
        for entry in case["original_files"]:
            if PurePosixPath(entry["source_path"]).name not in {"MANIFEST.json", "INPUT_MANIFEST.sha256"}:
                continue
            data = original(entry)
            parent = PurePosixPath(entry["source_path"]).parent.as_posix()
            if entry["source_path"].endswith(".json"):
                manifest = json.loads(data)
                members = manifest.get("files", {})
                if not isinstance(members, dict):
                    continue
            else:
                members = {}
                for line in data.decode().splitlines():
                    match = re.fullmatch(r"([0-9a-f]{64})\s+(.+)", line)
                    if not match:
                        raise ValueError("malformed original input manifest")
                    if match[2] in members:
                        raise ValueError("duplicate input manifest member")
                    members[match[2]] = match[1]
            for member, digest in members.items():
                if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
                    sealed.append((posixpath.normpath(parent + "/" + member), digest,
                                   {"manifest_sha256": entry["sha256"], "member": member}))
        grouped, structures = {}, []
        for structure in case["structures"]:
            entry = entries[structure["staged_path"]]
            data = original(entry)
            if sha256(data) != structure["sha256"]:
                raise ValueError("original STRU SHA mismatch")
            public_stru = [f for f in record["files"]["inputs"] if PurePosixPath(f["path"]).name == "STRU" and f["sha256"] == structure["sha256"]]
            if not public_stru or any(read(checked_destination(repo, f["path"])) != data for f in public_stru):
                raise ValueError("production STRU does not match archived stage")
            sections = {}
            name = None
            for raw in data.decode().splitlines():
                line = raw.split("#", 1)[0].strip()
                if re.fullmatch(r"[A-Z][A-Z_]+", line):
                    name = line
                    sections[name] = []
                elif line and name:
                    sections[name].append(line.split())
            order = [row[0] for row in sections["ATOMIC_SPECIES"]]
            declarations = [("pp", [row[2] for row in sections["ATOMIC_SPECIES"]])]
            for role, section in (("nao", "NUMERICAL_ORBITAL"), ("abf", "ABFS_ORBITAL")):
                if section in sections:
                    declarations.append((role, [row[0] for row in sections[section]]))
            proof = []
            for role, names in declarations:
                if len(names) != len(order):
                    raise ValueError("STRU role/element order incomplete")
                for element, declared in zip(order, names):
                    refs = [r for r in structure["references"] if ("abf" if r["kind"] == "abfs" else r["kind"]) == role and r["declared_name"] == declared]
                    if len(refs) != 1 or not refs[0].get("exact_source_asset_copied"):
                        raise ValueError("ambiguous STRU exact asset reference")
                    ref = refs[0]
                    asset_entry = entries[ref["staged_path"]]
                    asset = original(asset_entry)
                    if sha256(asset) != ref["sha256"] or len(asset) != ref["size_bytes"]:
                        raise ValueError("STRU reference payload SHA mismatch")
                    asset_header(asset, element, role)
                    key = (element, role)
                    parent = PurePosixPath(structure["source_path"]).parent.as_posix()
                    stage = next(s for s in case["stages"] if s["source_directory"] == parent)
                    original_inputs = [e for e in stage["original_controls"] if PurePosixPath(e["source_path"]).name == "INPUT"]
                    if len(original_inputs) != 1:
                        raise ValueError("stage original INPUT unavailable for directory binding")
                    settings = {}
                    for raw in original(original_inputs[0]).decode().splitlines():
                        tokens = raw.split("#", 1)[0].split()
                        if len(tokens) >= 2:
                            settings[tokens[0]] = tokens[1]
                    declared_settings = stage.get("parsed_original_settings", {}).get("INPUT", {})
                    for field in ("pseudo_dir", "orbital_dir"):
                        if settings.get(field) != declared_settings.get(field):
                            raise ValueError("original INPUT directory differs from reviewed parsing")
                    directory = settings.get("pseudo_dir" if role == "pp" else "orbital_dir", ".") if role in {"pp", "nao"} else "."
                    source = posixpath.normpath(parent + "/" + directory + "/" + declared)
                    if source != posixpath.normpath(ref["source_path"]):
                        raise ValueError("foreign original asset association")
                    resolved = posixpath.normpath(ref.get("resolved_source_path", ref["source_path"]))
                    seals = [p for source_path, digest, p in sealed if source_path == resolved and digest == ref["sha256"]]
                    old = grouped.get(key)
                    if old and old["sha256"] != ref["sha256"]:
                        raise ValueError("stage assets differ; cannot collapse into one species binding")
                    if not old:
                        grouped[key] = {"sha256": ref["sha256"], "bytes": asset, "names": set(), "seals": []}
                    grouped[key]["names"].add(declared)
                    grouped[key]["seals"].extend(seals)
                    proof.append({"element": element, "role": role, "declared_name": declared, "sha256": ref["sha256"], "source_path_sha256": sha256(source.encode()), "resolved_source_path_sha256": sha256(resolved.encode()), "resolved_path_differs": source != resolved, "producer_seals": seals})
            structures.append({"sha256": structure["sha256"], "archived_stru_paths": [f["path"] for f in public_stru], "references": proof})
        species, sets = [], []
        for element in dict.fromkeys(p["element"] for s in structures for p in s["references"]):
            if any((element, role) not in grouped for role in ROLES):
                raise ValueError("missing exact PP/NAO/ABF role")
            if any(not grouped[element, role]["seals"] for role in ROLES):
                raise ValueError("no original producer manifest binding for each selected asset")
            identity = {role: {"sha256": grouped[element, role]["sha256"], "names": sorted(grouped[element, role]["names"])} for role in ROLES}
            digest = sha256(json_bytes({"element": element, "case_id": record["id"], "roles": identity}))
            set_id = element + "-producer-" + digest[:20]
            payloads, aliases = [], {}
            for role, (folder, suffix) in ROLES.items():
                asset = grouped[element, role]
                names = sorted(asset["names"])
                if len(names) > 2:
                    raise ValueError("more than two original stage names; additional proof model required")
                target = f"data/elements/{element}/{folder}/{asset['sha256']}{suffix}"
                writes[target] = asset["bytes"]
                item = file_item(role, target, asset["bytes"], names[0])
                item["original_name"] = names[-1]
                item["source_declarations"] = names
                aliases[role] = names[0]
                payloads.append(item)
            basis = {"schema_version": 1, "id": set_id, "element": element, "family": "Recovered producer-bound assets",
                     "validation_scope": "Original STRU and producer-manifest hash association; scientific acceptance and full runtime handoff not reassessed.",
                     "publication": {"status": "database_only"}, "source": {"collection": "Reviewed historical producer assets", "reviewed_spec_sha256": sha256(source_data)},
                     "files": payloads, "generation_provenance": {"status": "historical producer association verified; generation history not reassessed"}}
            writes[f"data/elements/{element}/sets/{set_id}/set.json"] = json_bytes(basis)
            sets.append(set_id)
            species.append({"element": element, "set_id": set_id, "missing_roles": [], "asset_aliases": aliases,
                            "binding_scope": "Original production STRU plus producer-manifest payload hashes; not full immutable runtime seal"})
        receipt_path = record_path.parent.relative_to(repo).as_posix() + "/results/producer_assets_receipt.json"
        public_receipt = {"schema_version": 1, "case_id": record["id"], "reviewed_spec_sha256": sha256(source_data),
                          "record_before_sha256": sha256(before), "structures": structures, "sets": sets,
                          "runtime_asset_seal_verified": False, "full_runtime_handoff_verified": False, "scientific_acceptance_reassessed": False,
                          "scope": "Exact copied asset bytes, original STRU role/name/element order and original producer manifest members verified. Source directory linkage is not complete runtime proof.",
                          "restrictions": case["production_chain_restrictions"]}
        receipt_bytes = json_bytes(public_receipt)
        writes[receipt_path] = receipt_bytes
        record["species"] = species
        record["files"]["results"].append(file_item("results", receipt_path, receipt_bytes, "producer_assets_receipt.json"))
        record["source"]["producer_assets_receipt"] = receipt_path
        writes[relative] = json_bytes(record)
        report.append({"case_id": record["id"], "species": len(species), "roles": len(grouped), "sets": sets})
    for relative, data in writes.items():
        destination = checked_destination(repo, relative)
        if relative.endswith("/record.json"):
            continue
        if destination.exists() and read(destination) != data:
            raise ValueError("immutable asset or set destination conflicts")
        if relative.endswith(".json") and PRIVATE.search(data.decode()):
            raise ValueError("private path in public asset metadata")
    return writes, {"cases": report, "role_bindings": sum(r["roles"] for r in report)}, readset


def verify_readset(readset: dict) -> None:
    for path, identity in readset.items():
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("readset path changed to a symlink before asset write")
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ValueError("readset unavailable before asset write") from error
        if (sha256(data), len(data)) != identity:
            raise ValueError("readset changed before asset write")


def apply(repo: Path, writes: dict, expected_records: dict, readset: dict) -> None:
    repo = repo.resolve()
    verify_readset(readset)
    for relative, data in writes.items():
        destination = checked_destination(repo, relative)
        if relative in expected_records:
            if destination.read_bytes() != expected_records[relative]:
                raise ValueError("record changed before asset write")
        elif destination.exists() and destination.read_bytes() != data:
            raise ValueError("immutable destination changed before asset write")
    # No directories or files are created until all dependencies and targets
    # have passed preflight. This is a single-writer, per-file atomic importer,
    # not a claim of a multi-file transaction under arbitrary concurrent edits.
    verify_readset(readset)
    for relative, data in sorted(writes.items(), key=lambda item: item[0] in expected_records):
        destination = checked_destination(repo, relative)
        if destination.exists() and destination.read_bytes() == data:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False, suffix=".part") as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if relative in expected_records:
                if destination.read_bytes() != expected_records[relative]:
                    raise ValueError("record changed before atomic replacement")
                os.replace(temporary, destination)
            else:
                try:
                    os.link(temporary, destination)
                except FileExistsError:
                    if destination.read_bytes() != data:
                        raise ValueError("immutable creation conflict")
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--recovery-spec", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    before = {p.relative_to(args.repo_root).as_posix(): p.read_bytes() for p in args.repo_root.glob("data/calculations/2d/*/*/record.json")}
    try:
        writes, report, readset = prepare(args.repo_root, args.recovery_spec)
        if args.write:
            apply(args.repo_root, writes, {p: b for p, b in before.items() if p in writes}, readset)
    except (ValueError, OSError, KeyError, StopIteration) as error:
        parser.exit(1, f"Producer asset import stopped: {error}\n")
    report["dry_run"] = not args.write
    report["files"] = len(writes)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
