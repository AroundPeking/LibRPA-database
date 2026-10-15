#!/usr/bin/env python3
"""Validate element assets and ABACUS + LibRPA calculation records."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path, PurePosixPath

from asset_names import enrich_catalog

SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
GROUPS = {"inputs", "results", "logs", "figures"}
PRIVATE_PATH = re.compile(
    r"(?:/" + r"Users/|/" + r"home/[A-Za-z0-9_.-]+|/work[0-9]/|/scratch/|/private/var/|file:" + r"//|ssh:" + r"//)"
)
PROPERTY_CATEGORY = re.compile(r"^[a-z][a-z0-9_]*$")
PROPERTY_STATUSES = {"reported", "validated", "provisional", "failed"}
RECORD_TYPES = {"band", "large_system_gw", "rpa_energy", "reader_conversion"}
SOFTWARE_NAMES = {"abacus", "fhi_aims", "librpa"}
SOFTWARE_IDENTITY_ISSUE = re.compile(
    r"^software\.(abacus|fhi_aims|librpa)\.identity: full immutable commit or executable SHA-256 is required$"
)
HISTORICAL_SOFTWARE_EXCEPTIONS = Path("data/historical-software-identity-exceptions.json")


def _fail(message: str) -> None:
    raise ValueError(message)


def _file(root: Path, item: dict, label: str) -> None:
    path_text = item.get("path")
    path = PurePosixPath(path_text) if isinstance(path_text, str) else None
    if path is None or path.is_absolute() or ".." in path.parts:
        _fail(f"{label}: expected a portable repository path")
    full = root.joinpath(*path.parts).resolve()
    try:
        full.relative_to(root.resolve())
    except ValueError:
        _fail(f"{label}: file is missing or escapes the repository")
    if not full.is_file():
        _fail(f"{label}: file is missing or escapes the repository")
    digest = item.get("sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        _fail(f"{label}: expected lowercase SHA-256")
    with full.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != actual:
        _fail(f"{label}: SHA-256 mismatch ({digest} != {actual})")


def _json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return value == value and abs(value) != float("inf")
    if isinstance(value, list):
        return all(_json_value(entry) for entry in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(entry) for key, entry in value.items())
    return False


def _validate_properties(case: dict, label: str, declared_paths: set[str]) -> None:
    properties = case.get("properties", [])
    if not isinstance(properties, list):
        _fail(f"{label}.properties: expected a list")
    seen = set()
    required_strings = ("key", "category", "label", "method", "unit", "status")
    for index, item in enumerate(properties):
        prop_label = f"{label}.properties[{index}]"
        if not isinstance(item, dict):
            _fail(f"{prop_label}: expected an object")
        for field in required_strings:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                _fail(f"{prop_label}.{field}: expected a non-empty string")
        if not PROPERTY_CATEGORY.fullmatch(item["category"]):
            _fail(f"{prop_label}.category: expected a lowercase slug")
        if item["status"] not in PROPERTY_STATUSES:
            _fail(f"{prop_label}.status: unsupported status {item['status']!r}")
        if "value" not in item or item["value"] is None or not _json_value(item["value"]):
            _fail(f"{prop_label}.value: expected a JSON scalar, array, or object")
        identity = (item["category"], item["key"], item["method"])
        if identity in seen:
            _fail(f"{prop_label}: duplicate property category/key/method")
        seen.add(identity)
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            _fail(f"{prop_label}.evidence: expected a non-empty list of declared files")
        for path in evidence:
            parsed = PurePosixPath(path) if isinstance(path, str) else None
            if (parsed is None or parsed.is_absolute() or ".." in parsed.parts
                    or path not in declared_paths):
                _fail(f"{prop_label}.evidence: path must be a file declared by this calculation")


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _immutable_software_identity(app: object) -> bool:
    if not isinstance(app, dict):
        return False
    return bool((isinstance(app.get("commit"), str) and COMMIT.fullmatch(app["commit"]))
                or (isinstance(app.get("executable_sha256"), str)
                    and SHA256.fullmatch(app["executable_sha256"])))


def _validate_workflow_contract(case: dict, label: str, declared_paths: set[str]) -> None:
    record_type = case.get("record_type", "band")
    if record_type not in RECORD_TYPES:
        _fail(f"{label}.record_type: unsupported record type {record_type!r}")

    auxiliary = case.get("auxiliary_basis")
    if auxiliary is not None:
        if not isinstance(auxiliary, dict) or auxiliary.get("mode") != "pca_generated":
            _fail(f"{label}.auxiliary_basis: only explicit pca_generated provenance is supported")
        threshold = auxiliary.get("threshold")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold <= 0:
            _fail(f"{label}.auxiliary_basis.threshold: a positive finite threshold is required")
        evidence = auxiliary.get("evidence")
        if (not isinstance(evidence, list) or not evidence
                or any(not isinstance(path, str) or path not in declared_paths for path in evidence)):
            _fail(f"{label}.auxiliary_basis.evidence: declared same-record evidence is required")

    performance = case.get("performance")
    if performance is not None:
        fields = ("wall_time_seconds", "nodes", "mpi_ranks", "omp_threads_per_rank")
        if not isinstance(performance, dict) or any(not _positive_int(performance.get(field)) for field in fields):
            _fail(f"{label}.performance: positive wall time, node, rank, and thread counts are required")
        evidence = performance.get("evidence")
        if (not isinstance(evidence, list) or not evidence
                or any(not isinstance(path, str) or path not in declared_paths for path in evidence)):
            _fail(f"{label}.performance.evidence: declared same-record evidence is required")
        for field in ("cluster_label", "accelerator_label"):
            if field in performance and (not isinstance(performance[field], str) or not performance[field].strip()):
                _fail(f"{label}.performance.{field}: expected a non-empty public label")
        if "accelerators" in performance and not _positive_int(performance["accelerators"]):
            _fail(f"{label}.performance.accelerators: expected a positive count")

    if record_type == "reader_conversion":
        workflow = case.get("workflow")
        scale = case.get("computational_scale")
        conversion = case.get("conversion")
        if (not isinstance(workflow, dict) or workflow.get("task") != "reader_v1_conversion"
                or workflow.get("scientific_result_available") is not False):
            _fail(f"{label}.workflow: reader conversion must explicitly disclaim a scientific result")
        if (not isinstance(scale, dict)
                or any(not _positive_int(scale.get(field)) for field in ("atom_count", "matrix_rows", "matrix_columns"))):
            _fail(f"{label}.computational_scale: reader conversion requires positive atom and matrix dimensions")
        evidence = conversion.get("evidence") if isinstance(conversion, dict) else None
        header = conversion.get("reader_header") if isinstance(conversion, dict) else None
        if (not isinstance(conversion, dict) or not _positive_int(conversion.get("elapsed_seconds"))
                or not isinstance(conversion.get("converter_sha256"), str)
                or not SHA256.fullmatch(conversion["converter_sha256"])
                or not isinstance(header, list) or len(header) != 6
                or header[-2:] != [scale["matrix_rows"], scale["matrix_columns"]]
                or not isinstance(evidence, list) or len(evidence) != 1
                or evidence[0] not in declared_paths):
            _fail(f"{label}.conversion: reader-v1 header, converter identity, runtime and same-record receipt are required")
        associated = case.get("associated_gw_run")
        if associated is not None:
            fermi = associated.get("fermi_energy") if isinstance(associated, dict) else None
            frontier = associated.get("frontier_states") if isinstance(associated, dict) else None
            gap = associated.get("gap") if isinstance(associated, dict) else None
            markers = associated.get("program_completion_markers") if isinstance(associated, dict) else None
            common_ok = (isinstance(associated, dict)
                    and associated.get("scheduler_state") == "COMPLETED"
                    and associated.get("exit_code") == "0:0"
                    and all(_positive_int(associated.get(field)) for field in ("elapsed_seconds", "nodes", "cpus"))
                    and isinstance(markers, list)
                    and "Solve quasi-particle equation" in markers
                    and "libRPA finished successfully" in markers
                    and isinstance(fermi, dict)
                    and not isinstance(fermi.get("value"), bool)
                    and isinstance(fermi.get("value"), (int, float))
                    and math.isfinite(fermi["value"])
                    and fermi.get("unit") == "Ha"
                    and re.search(r"not .*gap", str(fermi.get("role", "")), re.I)
                    and isinstance(frontier, dict)
                    and frontier.get("occupied_state") == 4096
                    and frontier.get("unoccupied_state") == 4097
                    and isinstance(gap, dict)
                    and isinstance(gap.get("reason"), str)
                    and gap["reason"].strip())
            frontier_retained = isinstance(frontier, dict) and frontier.get("retained") is True
            if frontier_retained:
                if not common_ok or frontier.get("retained") is not True:
                    _fail(f"{label}.associated_gw_run: completed QP provenance is required")
                for flag, val in (("ks_available", "ks_value"), ("g0w0_available", "g0w0_value")):
                    if (not isinstance(gap.get(flag), bool) or (gap[flag] and (
                            not isinstance(gap.get(val), (int, float)) or isinstance(gap.get(val), bool)
                            or not math.isfinite(gap[val]) or gap.get("unit") != "eV"))):
                        _fail(f"{label}.associated_gw_run: retained frontier requires finite eV gap values")
            elif not common_ok or frontier.get("retained") is not False or gap.get("ks_available") is not False or gap.get("g0w0_available") is not False:
                _fail(f"{label}.associated_gw_run: completed QP provenance and explicit unavailable-gap boundary are required")
            if frontier_retained and case.get("properties"):
                allowed = all(p.get("key") == "sampled_grid_gap_ev" and p.get("unit") == "eV"
                              and p.get("status") in {"reported", "validated", "provisional"}
                              and isinstance(p.get("value"), (int, float)) and not isinstance(p.get("value"), bool)
                              and math.isfinite(p["value"])
                              for p in case["properties"])
                if not allowed:
                    _fail(f"{label}.properties: retained-frontier reader conversion allows only finite sampled_grid_gap_ev properties")
            elif not frontier_retained and case.get("properties"):
                _fail(f"{label}.properties: conversion-only records cannot claim scientific properties")
        return

    if record_type == "rpa_energy":
        workflow = case.get("workflow")
        if (not isinstance(workflow, dict) or not isinstance(workflow.get("task"), str)
                or workflow["task"].strip() not in {"rpa", "rpa_correlation"}):
            _fail(f"{label}.workflow: rpa_energy requires task = rpa or rpa_correlation")
        if performance is None:
            _fail(f"{label}.performance: RPA energy requires recorded wall time and resources")
        return
    if record_type != "large_system_gw":
        return
    workflow = case.get("workflow")
    if (not isinstance(workflow, dict) or not isinstance(workflow.get("task"), str)
            or not workflow["task"].strip() or workflow.get("sampling") != "regular_grid"
            or workflow.get("band_path_available") is not False
            or workflow.get("k_point_count") != 1):
        _fail(f"{label}.workflow: large-system GW requires a one-k-point regular-grid contract without a band path")
    scale = case.get("computational_scale")
    required_scale = ("atom_count", "ao_count", "state_count", "occupied_states", "unoccupied_states")
    if not isinstance(scale, dict) or any(not _positive_int(scale.get(field)) for field in required_scale):
        _fail(f"{label}.computational_scale: positive atom/AO/state counts are required")
    if scale["occupied_states"] + scale["unoccupied_states"] != scale["state_count"]:
        _fail(f"{label}.computational_scale: occupied and unoccupied counts must sum to state_count")
    if performance is None:
        _fail(f"{label}.performance: large-system GW requires recorded wall time and resources")
    if not isinstance(auxiliary, dict):
        _fail(f"{label}.auxiliary_basis: large-system GW requires explicit pca_generated provenance")


def _validate_paper_values(root: Path, case: dict, label: str) -> None:
    paper = case.get("paper_values")
    if paper is None:
        return
    if not isinstance(paper, dict) or type(paper.get("schema_version")) is not int or paper["schema_version"] != 1:
        _fail(f"{label}.paper_values: invalid schema")
    source = paper.get("source", {})
    if (not isinstance(source, dict) or not isinstance(source.get("title"), str) or not source["title"].strip()
            or not isinstance(source.get("document_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", source["document_sha256"])
            or type(source.get("pdf_page")) is not int or source["pdf_page"] < 1
            or not isinstance(source.get("table"), str) or not source["table"].strip()):
        _fail(f"{label}.paper_values: title, document SHA, PDF page and table are required")
    evidence = paper.get("evidence")
    owned = [item for item in case.get("files", {}).get("results", []) if item.get("path") == evidence]
    if (not isinstance(evidence, str) or len(owned) != 1
            or not evidence.endswith("/results/paper_reported_values.json")
            or Path(owned[0]["path"]).parent.parent.name != case.get("id")):
        _fail(f"{label}.paper_values: a same-record declared extract is required")
    try:
        excerpt = json.loads(_payload_bytes(root, owned[0]))
    except (ValueError, OSError, UnicodeError) as exc:
        _fail(f"{label}.paper_values: unreadable extract: {exc}")
    if (not isinstance(excerpt, dict) or excerpt.get("case_id") != case.get("id") or excerpt.get("paper_values") != paper
            or json.dumps(excerpt.get("paper_values"), sort_keys=True, allow_nan=False)
            != json.dumps(paper, sort_keys=True, allow_nan=False)):
        _fail(f"{label}.paper_values: extract and displayed metadata do not match")
    values = paper.get("values")
    if not isinstance(values, dict) or set(values) != {"DFT", "GW"}:
        _fail(f"{label}.paper_values: these main tables report DFT and GW only, not EXX")
    for method, item in values.items():
        if (not isinstance(item, dict) or item.get("unit") != "eV"
                or isinstance(item.get("value"), bool) or not isinstance(item.get("value"), (int, float))
                or not math.isfinite(item["value"]) or type(item.get("precision")) is not int
                or not 0 <= item["precision"] <= 8
                or any(not isinstance(item.get(field), str) or not item[field].strip() for field in ("column", "scope"))):
            _fail(f"{label}.paper_values.{method}: finite eV value, precision, column and scope are required")


def validate(root: Path, sets: list[dict], cases: list[dict]) -> None:
    def check_private_paths(value: object, label: str) -> None:
        if isinstance(value, str) and PRIVATE_PATH.search(value):
            _fail(f"{label}: private path or host in public metadata")
        if isinstance(value, dict):
            for key, nested in value.items():
                check_private_paths(nested, f"{label}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                check_private_paths(nested, f"{label}[{index}]")

    by_id = {}
    for index, item in enumerate(sets):
        label = f"sets[{index}]"
        check_private_paths(item, label)
        set_id, element = item.get("id"), item.get("element")
        if not isinstance(set_id, str) or not set_id or set_id in by_id:
            _fail(f"{label}: missing or duplicate id")
        if not isinstance(element, str) or not element:
            _fail(f"{label}: missing element")
        if not isinstance(item.get("files"), list) or not item["files"]:
            _fail(f"{label}: files must be a non-empty list")
        roles = set()
        for n, file_item in enumerate(item["files"]):
            _file(root, file_item, f"{label}.files[{n}]")
            roles.add(file_item.get("role"))
        if not roles.intersection({"pp", "nao", "abf", "species_defaults"}):
            _fail(f"{label}: no basis payload is registered")
        by_id[set_id] = item

    all_case_ids = {case.get("id") for case in cases if isinstance(case.get("id"), str)}
    case_ids = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        check_private_paths(case, label)
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            _fail(f"{label}: missing or duplicate id")
        case_ids.add(case_id)
        if case.get("dimension") not in {"2d", "3d"}:
            _fail(f"{label}: dimension must be 2d or 3d")
        # Record-level scientific status labels were removed by design: the
        # database indexes complete calculations and does not judge whether a
        # result is correct.  A reintroduced top-level status field must fail
        # so the classification system cannot silently come back.
        if "status" in case:
            _fail(f"{label}: record-level status labels are removed; scientific acceptance is out of scope")
        species = case.get("species")
        if not isinstance(species, list):
            _fail(f"{label}: species must be a list")
        # A historical band record may be useful before its exact production
        # STRU/PP/NAO/ABF binding has been audited.  It must carry an explicit
        # missing-evidence note so an empty list cannot look like a complete
        # calculation record.
        if not species and not case.get("missing"):
            _fail(f"{label}: empty species requires an explicit missing-evidence note")
        for entry in species:
            set_id = entry.get("set_id")
            if set_id is None:
                continue
            if set_id not in by_id:
                _fail(f"{label}: unknown basis set {set_id}")
            if by_id[set_id]["element"] != entry.get("element"):
                _fail(f"{label}: element does not match basis set {set_id}")
        candidates = case.get("basis_candidates", [])
        if not isinstance(candidates, list):
            _fail(f"{label}: basis_candidates must be a list")
        for n, entry in enumerate(candidates):
            if not isinstance(entry, dict):
                _fail(f"{label}.basis_candidates[{n}]: expected an object")
            set_id = entry.get("set_id")
            if set_id not in by_id:
                _fail(f"{label}: unknown candidate basis set {set_id}")
            if by_id[set_id]["element"] != entry.get("element"):
                _fail(f"{label}: candidate element does not match basis set {set_id}")
            if not entry.get("scope"):
                _fail(f"{label}.basis_candidates[{n}]: scope is required")
        software = case.get("software", {})
        workflow_identity = case.get("workflow")
        frontend = workflow_identity.get("frontend", "abacus") if isinstance(workflow_identity, dict) else "abacus"
        if frontend not in {"abacus", "fhi_aims"}:
            _fail(f"{label}.workflow.frontend: expected abacus or fhi_aims")
        if frontend == "fhi_aims" and "abacus" in software:
            _fail(f"{label}.software: FHI-aims record cannot claim ABACUS as the executing frontend")
        # 纯 FHI-aims GW 记录没有运行 LibRPA；未参与的软件不必声明。
        identity_apps = [frontend]
        if not (frontend == "fhi_aims" and isinstance(workflow_identity, dict) and workflow_identity.get("task") == "gw"):
            identity_apps.append("librpa")
        for name in identity_apps:
            app = software.get(name)
            if not isinstance(app, dict):
                _fail(f"{label}: software.{name} must be an object")
            commit = app.get("commit")
            if commit is not None and (not isinstance(commit, str) or not COMMIT.fullmatch(commit)):
                _fail(f"{label}: software.{name}.commit must be a full commit or null")
            executable = app.get("executable_sha256")
            if executable is not None and (not isinstance(executable, str) or not SHA256.fullmatch(executable)):
                _fail(f"{label}: software.{name}.executable_sha256 must be a lowercase SHA-256 or null")
        files = case.get("files", {})
        if not isinstance(files, dict):
            _fail(f"{label}: files must be an object")
        declared_paths = set()
        for group in GROUPS:
            values = files.get(group, [])
            if not isinstance(values, list):
                _fail(f"{label}: files.{group} must be a list")
            for n, file_item in enumerate(values):
                _file(root, file_item, f"{label}.files.{group}[{n}]")
                declared_paths.add(file_item["path"])

        _validate_workflow_contract(case, label, declared_paths)
        _validate_structure_identity(root, case, declared_paths)
        _validate_properties(case, label, declared_paths)
        _validate_paper_values(root, case, label)

        recommendation = case.get("recommendation")
        if recommendation is not None:
            if not recommendation.get("scope") or not recommendation.get("evidence_case_ids"):
                _fail(f"{label}: recommendation needs a narrow scope and evidence")
            if any(ref not in all_case_ids for ref in recommendation["evidence_case_ids"]):
                _fail(f"{label}: recommendation references an unknown case")



ELEMENTS = set("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split())


def _formula_elements(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    # 材料名只做化学式解析；少数非化学式名称必须明确映射，不能拆成伪元素。
    value = {"hBN": "BN", "Phosphorene": "P"}.get(value, value)
    if not re.fullmatch(r"(?:[A-Z][a-z]?\d*(?:\.\d+)?|[-+()·\s])+", value):
        return set()
    symbols = set(re.findall(r"[A-Z][a-z]?", value))
    return symbols if symbols.issubset(ELEMENTS) else set()


def _payload_bytes(root: Path, item: dict, limit: int | None = None) -> bytes:
    path = PurePosixPath(item.get("path", ""))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return b""
    full = root.joinpath(*path.parts).resolve()
    if not full.is_relative_to(root.resolve()) or not full.is_file():
        return b""
    with full.open("rb") as stream:
        return stream.read(limit) if limit else stream.read()


def _input_name(item: dict, name: str) -> bool:
    basename = PurePosixPath(item.get("path", "")).name.split("__")[-1]
    if name in {"librpa.in", "control.in", "geometry.in"}:
        return basename == name
    return bool(re.fullmatch(re.escape(name) + r"(?:_(?:scf|nscf|band|band_path|path|df))?", basename))


def _stru_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for raw in text.splitlines():
        line = re.split(r"[#!]", raw, maxsplit=1)[0].strip()
        if not line:
            continue
        if re.fullmatch(r"[A-Z][A-Z_]+", line):
            current = line
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return sections


def _aims_species_blocks(text: str) -> dict[str, str]:
    """逐字节提取 control.in 内联的 FHI-aims 物种基组块；intake 与绑定证明共用同一函数。"""
    blocks: dict[str, str] = {}
    lines = text.splitlines()
    starts = [index for index, raw in enumerate(lines)
              if re.fullmatch(r"\s*species\s+([A-Z][a-z]?)\s*", raw)]
    for number, start in enumerate(starts):
        element = lines[start].split()[1]
        end = starts[number + 1] if number + 1 < len(starts) else len(lines)
        block = lines[start:end]
        while block and not block[-1].strip():
            block.pop()
        if element in blocks:
            _fail(f"control.in species block for {element} is declared more than once")
        blocks[element] = "\n".join(block) + "\n"
    return blocks


# Conservative structure identity: identical cells and atomic positions to 1e-5 Å.
# Distinct cell settings, origins, or periodic images remain separate until reviewed.
_STRUCTURE_ALGORITHM = "cell-sites-v1"
_BOHR_ANGSTROM = 0.529177210903


def _finite_xyz(tokens: list[str]) -> tuple[float, float, float]:
    if len(tokens) < 3:
        _fail("structure identity: expected three coordinates")
    try:
        xyz = tuple(float(value) for value in tokens[:3])
    except ValueError:
        _fail("structure identity: invalid coordinate")
    if not all(math.isfinite(value) for value in xyz):
        _fail("structure identity: nonfinite coordinate")
    return xyz


def _cell_sites(text: str, kind: str) -> tuple[list[tuple[float, float, float]], list[tuple[str, tuple[float, float, float]]]]:
    if kind == "STRU":
        sections = _stru_sections(text)
        try:
            scale = float(sections["LATTICE_CONSTANT"][0].split()[0]) * _BOHR_ANGSTROM
            lattice = [tuple(value * scale for value in _finite_xyz(line.split()))
                       for line in sections["LATTICE_VECTORS"][:3]]
            positions = sections["ATOMIC_POSITIONS"]
            mode = positions[0].lower()
        except (KeyError, IndexError, ValueError):
            _fail("structure identity: STRU requires a valid cell and atomic positions")
        if len(lattice) != 3 or not math.isfinite(scale) or scale <= 0 or mode not in {"direct", "cartesian", "cartesian_angstrom"}:
            _fail("structure identity: unsupported STRU cell or coordinate mode")
        sites = []
        index = 1
        while index < len(positions):
            element = positions[index].split()[0]
            if not re.fullmatch(r"[A-Z][a-z]?", element) or index + 2 >= len(positions):
                _fail("structure identity: malformed STRU species block")
            try:
                count = int(positions[index + 2].split()[0])
            except ValueError:
                _fail("structure identity: invalid STRU atom count")
            if count <= 0 or index + 3 + count > len(positions):
                _fail("structure identity: incomplete STRU coordinates")
            for line in positions[index + 3:index + 3 + count]:
                coords = _finite_xyz(line.split())
                if mode == "direct":
                    coords = tuple(sum(coords[j] * lattice[j][i] for j in range(3)) for i in range(3))
                elif mode == "cartesian":
                    coords = tuple(value * scale for value in coords)
                sites.append((element, coords))
            index += 3 + count
        return lattice, sites
    lattice = []
    sites = []
    for raw in text.splitlines():
        fields = raw.split("#", 1)[0].split()
        if not fields:
            continue
        if fields[0] == "lattice_vector":
            lattice.append(_finite_xyz(fields[1:]))
        elif fields[0] in {"atom", "atom_frac"}:
            if len(fields) < 5 or not re.fullmatch(r"[A-Z][a-z]?", fields[4]):
                _fail("structure identity: malformed geometry.in atom")
            sites.append((fields[4], fields[0], _finite_xyz(fields[1:4])))
    if len(lattice) != 3:
        _fail("structure identity: geometry.in requires three lattice vectors")
    return lattice, [(element, tuple(sum(coords[j] * lattice[j][i] for j in range(3)) for i in range(3))
                       if mode == "atom_frac" else coords) for element, mode, coords in sites]


def _structure_fingerprint(text: str, kind: str, dimension: str) -> tuple[str, int]:
    lattice, sites = _cell_sites(text, kind)
    if not sites or any(not math.isfinite(value) for row in lattice for value in row):
        _fail("structure identity: empty or nonfinite cell/sites")
    quantize = lambda xyz: [round(value * 100000) for value in xyz]
    payload = {"algorithm": _STRUCTURE_ALGORITHM, "dimension": dimension,
               "lattice_angstrom_1e5": [quantize(row) for row in lattice],
               "sites_angstrom_1e5": sorted([element, *quantize(xyz)] for element, xyz in sites)}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return digest, len(sites)


def _validate_structure_identity(root: Path, case: dict, declared_paths: set[str]) -> None:
    identity = case.get("structure_identity")
    if identity is None:
        return
    if not isinstance(identity, dict) or set(identity) != {"algorithm", "sha256", "evidence"} or identity.get("algorithm") != _STRUCTURE_ALGORITHM:
        _fail("structure_identity: unsupported canonicalization algorithm")
    digest = identity.get("sha256")
    evidence = identity.get("evidence")
    inputs = [item for item in case.get("files", {}).get("inputs", []) if item.get("path") == evidence]
    prefix = f"data/calculations/{case.get('dimension')}/{case.get('material')}/{case.get('id')}/inputs/"
    if (not isinstance(digest, str) or not SHA256.fullmatch(digest) or not isinstance(evidence, str)
            or not evidence.startswith(prefix) or evidence not in declared_paths or len(inputs) != 1
            or (root / evidence).is_symlink()):
        _fail("structure_identity: same-record, hash-verified structure input is required")
    item = inputs[0]
    kind = "STRU" if _input_name(item, "STRU") else "geometry.in" if PurePosixPath(evidence).name.split("__")[-1] == "geometry.in" else None
    if kind is None:
        _fail("structure_identity: evidence must be an archived STRU or geometry.in")
    actual, atom_count = _structure_fingerprint(_payload_bytes(root, item).decode("utf-8"), kind, case.get("dimension"))
    if digest != actual:
        _fail("structure_identity: canonical structure SHA-256 does not match the archived input")
    scale = case.get("computational_scale")
    if isinstance(scale, dict) and scale.get("atom_count") is not None and scale["atom_count"] != atom_count:
        _fail("structure_identity: atom count differs from the archived input")


def _basis_payload(data: bytes, item: dict, element: str, *, generic_auxiliary: bool = False) -> bool:
    text = data.decode("utf-8", errors="replace")
    suffix = PurePosixPath(item.get("path", "")).suffix.lower()
    if item.get("role") == "species_defaults":
        # FHI-aims 内联物种块必须是逐元素完整定义；角色即身份，扩展名不参与判断。
        return bool(re.search(r"(?m)^\s*species\s+" + re.escape(element) + r"\s*$", text)
                    and re.search(r"(?m)^\s*nucleus\s+\d+", text)
                    and re.search(r"(?m)^\s*(?:valence|ion_occ)\s+\d", text)
                    and re.search(r"(?m)^\s*(?:hydro|ionic|for_aux)\s", text)
                    and re.search(r"\d", text))
    if item.get("role") == "pp":
        # 同时支持 UPF v1 文本头和 v2 XML 属性；角色/扩展名自身不是payload证据。
        header = re.search(r"<PP_HEADER\b[^>]*>(.*?)</PP_HEADER>|<PP_HEADER\b[^>]*/?>", text, re.S)
        header_text = header.group(0) if header else ""
        declared_element = re.search(r'\belement\s*=\s*[\"\']\s*([A-Z][a-z]?)\s*[\"\']', header_text)
        if declared_element:
            matches_element = declared_element.group(1) == element
        else:
            matches_element = bool(re.search(r"(?m)^\s*" + re.escape(element) + r"\s+Element\b", header_text))
        return bool(suffix == ".upf" and header and matches_element and "<PP_" in text
                    and re.search(r"<PP_(?:LOCAL|R|NONLOCAL)\b", text)
                    and re.search(r"\d", text))
    declared = re.search(r"(?m)^\s*Element\s+([A-Z][a-z]?)\s*$", text)
    generic_abf = (item.get("role") == "abf" and generic_auxiliary
                   and declared is not None and declared.group(1) in ELEMENTS)
    return bool(suffix == {"nao": ".orb", "abf": ".abfs"}.get(item.get("role"))
                and (generic_abf or (declared is not None and declared.group(1) == element))
                and re.search(r"SUMMARY\s+END", text)
                and re.search(r"(?m)^\s*Mesh\s+[1-9]\d*", text)
                and re.search(r"\bType\s+L\s+N\b", text)
                and re.search(r"[-+]?\d+\.\d+(?:[Ee][-+]?\d+)?", text))


def _method(value: object) -> str | None:
    text = str(value or "").upper()
    if re.search(r"(?:G0W0|GW|QSGW|EVGW)", text):
        return "GW"
    if "EXX" in text or "EXACT EXCHANGE" in text:
        return "EXX"
    if re.search(r"(?:\b|_)(?:KS|PBE|DFT)(?:\b|_)", text):
        return "PBE"
    return None


def _band_method(item: dict) -> str | None:
    identity = PurePosixPath(item.get("path", "")).name
    if (not re.search(r"band", identity, re.I)
            or re.search(r"eigenvector|self_energy|kpath_info", identity, re.I)
            or PurePosixPath(identity).suffix.lower() not in {".dat", ".txt", ".csv"}):
        return None
    return _method(identity) or _method(item.get("method")) or _method(item.get("label"))


def _numeric_bands(data: bytes) -> bool:
    width = None
    count = 0
    for raw in data.decode("utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            values = [float(value) for value in line.replace(",", " ").split()]
        except ValueError:
            return False
        # 原始科学病态（NaN/Inf）不等于文件缺失；归档门槛只核验完整可读等宽表。
        if len(values) < 2:
            return False
        if width is not None and len(values) != width:
            return False
        width = len(values)
        count += 1
    return count >= 2


def _band_figure(data: bytes, item: dict, band_paths: set[str], evidence_paths: set[str]) -> bool:
    suffix = PurePosixPath(item.get("path", "")).suffix.lower()
    sources = item.get("source_paths", [])
    linked = (isinstance(sources, list) and bool(sources)
              and all(isinstance(path, str) and path in evidence_paths for path in sources)
              and bool(band_paths.intersection(sources)))
    if not linked:
        return False
    text = data.decode("utf-8", errors="replace")
    semantics = bool(re.search(r"Energy|eV", text, re.I)
                     and re.search(r"k.path|k.point|path.coordinate|bands?", text, re.I))
    if suffix == ".svg":
        try:
            svg = ET.fromstring(data)
        except ET.ParseError:
            return False
        def visible_curve(node: ET.Element, inherited: dict | None = None) -> bool:
            if node.tag.rsplit("}", 1)[-1] in {"defs", "clipPath", "mask", "symbol", "marker", "pattern"}:
                return False  # 未直接绘制的定义不能冒充页面中的可见能带曲线。
            presentation = dict(inherited or {})
            for key in ("stroke", "stroke-width", "stroke-opacity", "opacity", "display", "visibility"):
                if node.get(key) is not None:
                    presentation[key] = node.get(key)
            for declaration in node.get("style", "").split(";"):
                if ":" in declaration:
                    key, value = declaration.split(":", 1)
                    presentation[key.strip()] = value.strip()
            if presentation.get("display") == "none" or presentation.get("visibility") == "hidden":
                return False
            try:
                if float(presentation.get("opacity", "1")) <= 0:
                    return False
                visible_stroke = (presentation.get("stroke", "none") not in {"none", "transparent"}
                                  and float(presentation.get("stroke-width", "1")) > 0
                                  and float(presentation.get("stroke-opacity", "1")) > 0)
            except ValueError:
                visible_stroke = False
            tag = node.tag.rsplit("}", 1)[-1]
            coordinates = node.get("d") if tag == "path" else node.get("points")
            numbers = re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", coordinates or "")
            drawable = (tag == "path" and bool(re.match(r"\s*[Mm]\s*[-+.0-9]", coordinates or ""))
                        and bool(re.search(r"[LlHhVvCcSsQqTtAa]", coordinates or "")))
            if tag == "polyline":
                drawable = (len(numbers) >= 4 and len(numbers) % 2 == 0
                            and not re.sub(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[\s,]", "", coordinates or ""))
            curve = (tag in {"path", "polyline"} and visible_stroke and drawable
                     and len(numbers) >= 4 and all(math.isfinite(float(value)) for value in numbers))
            return curve or any(visible_curve(child, presentation) for child in node)
        drawn = visible_curve(svg)
        return svg.tag.rsplit("}", 1)[-1] == "svg" and drawn and semantics
    if suffix == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return False
        offset, pixels, dimensions, ended = 8, bytearray(), None, False
        try:
            while offset + 12 <= len(data):
                size = struct.unpack(">I", data[offset:offset + 4])[0]
                tag = data[offset + 4:offset + 8]
                payload = data[offset + 8:offset + 8 + size]
                checksum = data[offset + 8 + size:offset + 12 + size]
                if len(checksum) != 4 or struct.unpack(">I", checksum)[0] != zlib.crc32(tag + payload):
                    return False
                if tag == b"IHDR":
                    dimensions = struct.unpack(">IIBBBBB", payload)
                elif tag == b"IDAT":
                    pixels.extend(payload)
                elif tag == b"IEND":
                    ended = True
                    break
                offset += 12 + size
            if not dimensions or not ended:
                return False
            width, height, depth, color, _, _, interlace = dimensions
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
            if not channels or width < 100 or height < 100 or interlace != 0:
                return False
            row_size = (width * channels * depth + 7) // 8
            expected = height * (row_size + 1)
            if expected > 128 * 1024 * 1024:
                return False
            unpacker = zlib.decompressobj()
            decoded = unpacker.decompress(bytes(pixels), expected + 1)
            return bool(unpacker.eof and len(decoded) == expected
                        and len(set(decoded)) > 4)
        except (struct.error, zlib.error):
            return False
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
            return False
        # 页面和实际绘制流均须存在，且上面已核验同record真实能带图源。
        streams = []
        for match in re.finditer(rb"<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream", data, re.S):
            stream = match.group(2)
            if b"/FlateDecode" in match.group(1):
                try:
                    stream = zlib.decompress(stream)
                except zlib.error:
                    continue
            streams.append(stream)
        drawing = any(re.search(rb"\d\s+(?:m|l)\b", stream) for stream in streams)
        return bool(re.search(rb"/Type\s*/Page\b", data) and drawing)
    return False


def _qp_table_summary(data: bytes) -> dict | None:
    text = data.decode("utf-8", errors="replace")
    marker = text.find("Printing quasi-particle energy [unit: eV]")
    finished = text.find("libRPA finished successfully", marker + 1)
    if marker < 0 or finished < 0:
        return None
    body = text[marker:finished]
    if not re.search(r"spin\s+1,\s*k-point\s+1:\s*\(\s*0(?:\.0+)?\s*,\s*0(?:\.0+)?\s*,\s*0(?:\.0+)?\s*\)", body):
        return None
    rows = []
    for line in body.splitlines():
        parts = line.split()
        if len(parts) != 8 or not parts[0].isdigit():
            continue
        try:
            state = int(parts[0])
            values = [float(value) for value in parts[1:]]
        except ValueError:
            return None
        if not all(math.isfinite(value) for value in values):
            return None
        rows.append((state, *values))
    if not rows or [row[0] for row in rows] != list(range(1, len(rows) + 1)):
        return None
    occupied = [row for row in rows if row[1] > 0]
    unoccupied = [row for row in rows if row[1] <= 0]
    if not occupied or not unoccupied:
        return None
    return {
        "state_count": len(rows),
        "occupied_states": len(occupied),
        "unoccupied_states": len(unoccupied),
        "pbe_gap_ev": min(row[2] for row in unoccupied) - max(row[2] for row in occupied),
        "gw_gap_ev": min(row[7] for row in unoccupied) - max(row[7] for row in occupied),
    }


def _finite_property(case: dict, *, key: str, methods: set[str], unit: str, evidence_path: str) -> list[dict]:
    matches = []
    for prop in case.get("properties", []):
        value = prop.get("value")
        evidence = prop.get("evidence")
        if (prop.get("key") == key and str(prop.get("method", "")).upper() in methods
                and prop.get("unit") == unit and prop.get("status") in {"reported", "validated", "provisional"}
                and not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
                and isinstance(evidence, list) and evidence_path in evidence):
            matches.append(prop)
    return matches


def completeness_issues(root: Path, sets: list[dict], case: dict) -> list[str]:
    """完整上传门槛；历史记录、科学诊断状态和missing注释均不构成豁免。"""
    issues = []
    by_id = {item["id"]: item for item in sets}
    prefix = f"data/calculations/{case.get('dimension')}/{case.get('material')}/{case.get('id')}/"
    groups = case.get("files", {})
    owned = {}
    case_directory = root / prefix
    evidence_paths = set()
    for group in sorted(GROUPS):
        owned[group] = []
        for item in groups.get(group, []):
            path = item.get("path", "")
            if (not path.startswith(prefix)
                    or not (root / path).resolve().is_relative_to(case_directory.resolve())):
                issues.append(f"files.{group}: {path} must belong to the same calculation directory")
                continue
            try:
                _file(root, item, f"files.{group}: {path}")
            except ValueError as exc:
                issues.append(str(exc))
                continue
            owned[group].append(item)
            if _payload_bytes(root, item, 1):
                evidence_paths.add(path)

    record_type = case.get("record_type", "band")
    try:
        _validate_workflow_contract(case, "record", evidence_paths)
    except ValueError as exc:
        issues.append(str(exc))

    if record_type == "reader_conversion":
        receipts = [item for item in owned["results"] if item.get("scientific_role") == "reader_conversion_receipt"]
        if len(receipts) != 1:
            issues.append("results: reader conversion requires one declared conversion receipt")
        else:
            try:
                receipt = json.loads(_payload_bytes(root, receipts[0]))
            except (ValueError, UnicodeError):
                receipt = None
            conversion = case.get("conversion", {})
            if (not isinstance(receipt, dict) or receipt.get("record_id") != case.get("id")
                    or receipt.get("scope") != case.get("scientific_scope", {}).get("statement")
                    or receipt.get("conversion", {}).get("verified_header") != conversion.get("reader_header")
                    or receipt.get("scientific_result") != {
                        "rpa_completed": False, "gw_completed": False,
                        "qp_table_present": False, "observable": None,
                    }
                    or receipt.get("associated_gw_run") != case.get("associated_gw_run")):
                issues.append("results: conversion receipt does not match the record scope, reader-v1 header, and associated GW provenance")
        return issues

    inputs = {}
    workflow = case.get("workflow")
    frontend = workflow.get("frontend", "abacus") if isinstance(workflow, dict) else "abacus"
    if frontend == "fhi_aims":
        # FHI-aims 记录以 control.in/geometry.in 为生产输入；librpa.in 仅在
        # LibRPA 参与执行（task 不是纯 aims GW）时才是同记录生产输入。
        input_names = ("control.in", "geometry.in")
        if not (isinstance(workflow, dict) and workflow.get("task") == "gw"):
            input_names += ("librpa.in",)
    else:
        input_names = ("INPUT", "KPT", "STRU", "librpa.in")
    for name in input_names:
        valid = []
        for item in owned["inputs"]:
            if not _input_name(item, name):
                continue
            text = _payload_bytes(root, item).decode("utf-8", errors="replace")
            if name == "INPUT":
                readable = bool(re.search(r"(?m)^\s*INPUT_PARAMETERS\s*$", text)
                                and re.search(r"(?m)^\s*calculation\s+\S+", text))
            elif name == "KPT":
                readable = bool(re.search(r"(?m)^\s*K_POINTS\s*$", text)
                                and re.search(r"(?m)^\s*(?:Gamma|MP|Line|Direct|Cartesian)\s*$", text)
                                and re.search(r"\d", text))
            elif name == "STRU":
                sections = _stru_sections(text)
                readable = bool(sections.get("ATOMIC_SPECIES") and sections.get("ATOMIC_POSITIONS"))
            elif name == "control.in":
                readable = bool(re.search(r"(?m)^\s*xc\s+\S+", text)
                                and re.search(r"(?m)^\s*k_grid\s+\d", text)
                                and re.search(r"(?m)^\s*species\s+[A-Z][a-z]?\s*$", text))
            elif name == "geometry.in":
                readable = bool(len(re.findall(r"(?m)^\s*lattice_vector\b", text)) == 3
                                and re.search(r"(?m)^\s*atom(?:_frac)?\s", text))
            else:
                readable = bool(re.search(r"(?m)^\s*task\s*=\s*\S+", text))
            if readable:
                valid.append((item, text))
        if not valid:
            issues.append(f"input {name}: missing readable declared production input in this calculation")
        inputs[name] = valid

    species = case.get("species", [])
    actual = {entry.get("element") for entry in species}
    required = _formula_elements(case.get("formula") if case.get("formula") is not None else case.get("material"))
    if not required:
        issues.append("species: formula/material must identify chemical elements")
    if required and actual - required:
        issues.append("species: exact bindings contain elements absent from formula/material")
    for element in sorted(required - actual):
        issues.append(f"species: missing exact binding for formula element {element}")
    if not species:
        issues.append("species: exact production PP/physical NAO/ABF bindings are required; candidates and missing notes are not bindings")
    if len(actual) != len(species):
        issues.append("species: duplicate element bindings are ambiguous")
    auxiliary = case.get("auxiliary_basis", {})
    generated_auxiliary = (isinstance(auxiliary, dict)
                           and auxiliary.get("mode") == "pca_generated")
    if frontend == "fhi_aims":
        required_roles = ("species_defaults",)
    elif generated_auxiliary:
        required_roles = ("pp", "nao")
    else:
        required_roles = ("pp", "nao", "abf")
    payloads = {}
    for entry in species:
        element, set_id = entry.get("element"), entry.get("set_id")
        basis = by_id.get(set_id)
        if not set_id or basis is None or basis.get("element") != element:
            issues.append(f"species {element}: set_id must identify an exact same-element basis set")
            continue
        if entry.get("missing_roles"):
            issues.append(f"species {element}: missing_roles is not empty: {entry['missing_roles']}")
        payloads[element] = {}
        for role in required_roles:
            files = [item for item in basis["files"] if item.get("role") == role]
            if len(files) != 1:
                issues.append(f"species {element}: expected one unambiguous {role} payload, found {len(files)}")
                continue
            item = files[0]
            try:
                _file(root, item, f"species {element}: {role}")
            except ValueError as exc:
                issues.append(str(exc))
                continue
            payloads[element][role] = item
            generic_auxiliary = False
            if role == "abf":
                alias = entry.get("asset_aliases", {}).get("abf")
                if isinstance(alias, str) and re.fullmatch(r"ORBITAL_[0-9]+U\.abfs", alias):
                    for _, text in inputs["STRU"]:
                        sections = _stru_sections(text)
                        order = [line.split()[0] for line in sections.get("ATOMIC_SPECIES", [])]
                        auxiliaries = [line.split()[0] for line in sections.get("ABFS_ORBITAL", [])]
                        if (len(order) == len(auxiliaries) and order.count(element) == 1
                                and auxiliaries[order.index(element)] == alias):
                            generic_auxiliary = True
                            break
            if not _basis_payload(_payload_bytes(root, item, 128 * 1024), item, element,
                                  generic_auxiliary=generic_auxiliary):
                issues.append(f"species {element}: {role} payload is empty, unreadable, or does not identify its format/element")

    if frontend == "fhi_aims":
        # FHI-aims 绑定证明：geometry.in 原子标签与精确物种一致，且 control.in
        # 内联物种块与注册 payload 逐字节同哈希；不以文件名或目录猜测。
        for geo_item, text in inputs["geometry.in"]:
            labels = set(re.findall(r"(?m)^\s*atom(?:_frac)?\s+\S+\s+\S+\s+\S+\s+([A-Z][a-z]?)\s*$", text))
            if labels != actual:
                issues.append(f"geometry.in {geo_item['path']}: atom species labels do not match exact species")
        for element in sorted(actual):
            item = payloads.get(element, {}).get("species_defaults")
            if not item:
                continue
            payload_digest = item.get("sha256")
            matched = False
            for control_item, text in inputs["control.in"]:
                blocks = _aims_species_blocks(text)
                if (element in blocks
                        and hashlib.sha256(blocks[element].encode("utf-8")).hexdigest() == payload_digest):
                    matched = True
                    break
            if not matched:
                issues.append(f"control.in: {element} species defaults block does not hash-match the bound species_defaults payload")
    else:
        declared_roles = set()
        for stru_item, text in inputs["STRU"]:
            sections = _stru_sections(text)
            rows = [line.split() for line in sections.get("ATOMIC_SPECIES", [])]
            order = [row[0] for row in rows if row]
            if set(order) != actual:
                issues.append(f"STRU {stru_item['path']}: ATOMIC_SPECIES elements do not match exact species")
            declarations = {"pp": [row[2] if len(row) > 2 else "" for row in rows]}
            for role, section in (("nao", "NUMERICAL_ORBITAL"), ("abf", "ABFS_ORBITAL")):
                if section in sections:
                    declarations[role] = [line.split()[0] for line in sections[section]]
            declared_roles.update(declarations)
            if generated_auxiliary:
                threshold = auxiliary.get("threshold")
                evidence = set(auxiliary.get("evidence", []))
                values = []
                for input_item, input_text in inputs["INPUT"]:
                    if input_item["path"] not in evidence:
                        continue
                    values.extend(float(value) for value in re.findall(
                        r"(?im)^\s*exx_pca_threshold\s+(\S+)", input_text
                    ) if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", value))
                if len(values) != 1 or not math.isclose(values[0], threshold, rel_tol=1e-12, abs_tol=0.0):
                    issues.append("auxiliary_basis: exx_pca_threshold must be uniquely recorded in the evidence-targeted production INPUT and match provenance")
                if "ABFS_ORBITAL" in sections:
                    issues.append(f"STRU {stru_item['path']}: PCA-generated auxiliary provenance cannot also declare ABFS_ORBITAL")
            for role, names in declarations.items():
                if len(names) != len(order) or any(not name for name in names):
                    issues.append(f"STRU {stru_item['path']}: {role} declarations do not cover ATOMIC_SPECIES")
                for element, name in zip(order, names):
                    item = payloads.get(element, {}).get(role)
                    entry = next((entry for entry in species if entry.get("element") == element), {})
                    if not item:
                        continue
                    aliases = entry.get("asset_aliases", {})
                    proved = {aliases.get(role)} if isinstance(aliases, dict) else set()
                    # 仅原始记录的label/original_name能证明同哈希名称复用；描述性catalog别名不参与。
                    for basis in sets:
                        if basis.get("element") != element:
                            continue
                        for other in basis["files"]:
                            if other.get("role") == role and other.get("sha256") == item.get("sha256"):
                                proved.update(other.get(field) for field in ("label", "original_name"))
                    # 可移植相对路径也可直接指向已校验的精确资产；不以basename猜测。
                    reference = PurePosixPath(name)
                    exact_path = (not reference.is_absolute()
                                  and (root / stru_item["path"]).parent.joinpath(*reference.parts).resolve()
                                  == (root / item["path"]).resolve())
                    if name not in proved and not exact_path:
                        issues.append(f"STRU {stru_item['path']}: {element} {role} original name {name!r} is not proven for the bound payload hash")
        for role in required_roles:
            if role != "pp" and inputs["STRU"] and role not in declared_roles:
                issues.append(f"STRU: at least one production STRU must declare exact {role} payloads")

    workflow = case.get("workflow")
    frontend = workflow.get("frontend", "abacus") if isinstance(workflow, dict) else "abacus"
    # 纯 FHI-aims GW 记录没有运行 LibRPA；未参与的软件不做身份要求。
    apps = [frontend]
    if not (frontend == "fhi_aims" and isinstance(workflow, dict) and workflow.get("task") == "gw"):
        apps.append("librpa")
    for name in apps:
        app = case.get("software", {}).get(name, {})
        if not _immutable_software_identity(app):
            issues.append(
                f"software.{name}.identity: full immutable commit or executable SHA-256 is required"
            )

    if record_type == "large_system_gw":
        qp_tables = []
        for item in owned["results"] + owned["logs"]:
            summary = _qp_table_summary(_payload_bytes(root, item))
            if summary:
                qp_tables.append((item, summary))
        if len(qp_tables) != 1:
            issues.append("results: large-system GW requires one complete finite QP table followed by successful LibRPA completion")
        else:
            item, summary = qp_tables[0]
            scale = case.get("computational_scale", {})
            for field in ("state_count", "occupied_states", "unoccupied_states"):
                if scale.get(field) != summary[field]:
                    issues.append(f"computational_scale.{field}: does not match the complete QP table")
            for methods, expected, label in (({"PBE", "DFT", "KS"}, summary["pbe_gap_ev"], "PBE"),
                                             ({"G0W0", "GW"}, summary["gw_gap_ev"], "G0W0")):
                matches = _finite_property(case, key="sampled_grid_gap_ev", methods=methods,
                                           unit="eV", evidence_path=item["path"])
                if (len(matches) != 1 or not math.isclose(matches[0]["value"], expected,
                                                          rel_tol=0.0, abs_tol=5e-5)
                        or not re.search(r"(?:gamma|Γ).*regular.grid|regular.grid.*(?:gamma|Γ)",
                                         str(matches[0].get("definition", "")), re.I)):
                    issues.append(f"properties: {label} requires a finite sampled_grid_gap_ev matching the QP table and an explicit Γ regular-grid definition")
        if not owned["results"]:
            issues.append("results: large-system GW requires a declared final result file")
        if not owned["logs"]:
            issues.append("logs: large-system GW requires completion and resource logs")
    elif record_type == "rpa_energy":
        if not owned["results"]:
            issues.append("results: RPA energy requires a declared final result file")
        if not owned["logs"]:
            issues.append("logs: RPA energy requires completion and resource logs")
        rpa_matches = []
        for prop in case.get("properties", []):
            value = prop.get("value")
            evidence = prop.get("evidence", [])
            if (prop.get("key") == "rpa_correlation_energy"
                    and prop.get("status") in {"reported", "validated", "provisional"}
                    and prop.get("unit") == "Ha"
                    and not isinstance(value, bool) and isinstance(value, (int, float))
                    and math.isfinite(value)
                    and isinstance(evidence, list) and evidence
                    and all(isinstance(path, str) and path in evidence_paths for path in evidence)):
                rpa_matches.append(prop)
        if not rpa_matches:
            issues.append("properties: rpa_correlation_energy requires a finite Ha value with valid same-record evidence")
    else:
        methods = {}
        for item in owned["results"]:
            method = _band_method(item)
            if method:
                methods.setdefault(method, set())
                if _numeric_bands(_payload_bytes(root, item)):
                    methods[method].add(item["path"])
                else:
                    issues.append(f"results: {method} band data is empty, unreadable, or has inconsistent row widths: {item['path']}")
        if not methods:
            issues.append("results: at least one actual KS/PBE/DFT, EXX, or GW band result is required")
        band_paths = set().union(*methods.values()) if methods else set()
        if not any(_band_figure(_payload_bytes(root, item), item, band_paths, evidence_paths)
                   for item in owned["figures"]):
            issues.append("figures: a readable nonempty band figure (SVG/PNG/PDF) with valid same-record band provenance is required")

        for method, paths in sorted(methods.items()):
            valid = False
            for prop in case.get("properties", []):
                value = prop.get("value")
                evidence = prop.get("evidence", [])
                if (_method(prop.get("method")) != method or prop.get("status") not in {"reported", "validated", "provisional"}
                        or prop.get("unit") != "eV" or isinstance(value, bool)
                        or not isinstance(value, (int, float)) or not math.isfinite(value)
                        or not isinstance(evidence, list) or not paths.intersection(evidence)
                        or not all(isinstance(path, str) and path in evidence_paths for path in evidence)):
                    continue
                key = prop.get("key", "")
                definition = " ".join(str(prop.get(field, "")) for field in ("key", "label", "definition", "scope", "observable"))
                restricted = (re.search(r"gap", definition, re.I)
                              and re.search(r"restricted|raw.band|frontier", definition, re.I)
                              and re.search(r"path|selected", definition, re.I)
                              and isinstance(prop.get("definition") or prop.get("scope"), str)
                              and bool((prop.get("definition") or prop.get("scope")).strip()))
                sampled_path = (bool(re.search(r"gap", definition, re.I))
                                and bool(re.search(r"path|sampled", definition, re.I))
                                and (bool(re.fullmatch(r"(?:sampled_)?path_gap(?:_ev)?", key))
                                     or bool(re.search(r"(?:sampled|archived|restricted).*path.*gap|path.*band.*gap", definition, re.I))))
                if key == "band_gap" or restricted or sampled_path:
                    valid = True
                    break
            if not valid:
                issues.append(f"properties: {method} requires a nonfailed finite eV band_gap or explicitly restricted/path gap observable with valid same-method band evidence")
    return issues


def load_historical_software_exceptions(root: Path) -> set[tuple[str, str]]:
    """读取固定历史软件身份基线；缺失基线意味着不豁免任何记录。"""
    path = root / HISTORICAL_SOFTWARE_EXCEPTIONS
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(f"historical software exception baseline is unreadable: {exc}")
    records = data.get("records") if isinstance(data, dict) else None
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("policy") != "grandfathered_missing_software_identity"
            or not isinstance(records, list)):
        _fail("historical software exception baseline has an invalid schema or policy")
    pairs = set()
    for index, entry in enumerate(records):
        case_id = entry.get("id") if isinstance(entry, dict) else None
        software = entry.get("software") if isinstance(entry, dict) else None
        if (not isinstance(case_id, str) or not case_id.strip()
                or not isinstance(software, list) or not software):
            _fail(f"historical software exception baseline records[{index}] is invalid")
        for name in software:
            if name not in SOFTWARE_NAMES:
                _fail(f"historical software exception baseline records[{index}] has unknown software {name!r}")
            pair = (case_id, name)
            if pair in pairs:
                _fail(f"historical software exception baseline duplicates {case_id}/{name}")
            pairs.add(pair)
    if data.get("frozen_issue_count") != len(pairs):
        _fail("historical software exception baseline frozen_issue_count does not match its exact entries")
    return pairs


def _issue_categories(issues: list[str]) -> dict[str, list[str]]:
    missing = {}
    for issue in issues:
        category = issue.split(":", 1)[0].split(" ", 1)[0].split(".", 1)[0].lower()
        category = {"input": "inputs", "stru": "basis_binding", "species": "basis_binding"}.get(category, category)
        missing.setdefault(category, []).append(issue)
    return missing


def completeness_report(root: Path, sets: list[dict], cases: list[dict]) -> dict:
    """保留原始缺项，同时将固定历史软件身份基线与CI阻断结果分开。"""
    integrity_issues = []
    try:
        exceptions = load_historical_software_exceptions(root)
    except ValueError as exc:
        exceptions = set()
        integrity_issues.append(f"software exception baseline: {exc}")
    try:
        validate(root, sets, cases)
    except ValueError as exc:
        integrity_issues.append(str(exc))
    raw_records = []
    raw_pairs = set()
    case_ids = {case.get("id") for case in cases}
    for index, case in enumerate(cases):
        try:
            issues = completeness_issues(root, sets, case)
        except (KeyError, TypeError, AttributeError) as exc:
            if not integrity_issues:
                raise
            issues = [f"integrity: invalid schema prevents completeness audit: {exc}"]
        for issue in integrity_issues:
            if issue.startswith(f"cases[{index}]"):
                issues.insert(0, f"integrity: {issue}")
        for issue in issues:
            match = SOFTWARE_IDENTITY_ISSUE.fullmatch(issue)
            if match:
                raw_pairs.add((case.get("id"), match.group(1)))
        raw_records.append((case, issues))
    if not integrity_issues:
        for case_id, name in sorted(exceptions):
            if case_id not in case_ids:
                integrity_issues.append(
                    f"software exception baseline: unknown calculation {case_id}/{name}"
                )
            elif (case_id, name) not in raw_pairs:
                integrity_issues.append(
                    f"software exception baseline: stale entry {case_id}/{name}"
                )
    baseline_valid = not integrity_issues
    records = []
    categories = {}
    issue_count = 0
    accepted_count = 0
    blocking_count = 0
    for case, issues in raw_records:
        accepted, blocking = [], []
        for issue in issues:
            match = SOFTWARE_IDENTITY_ISSUE.fullmatch(issue)
            if baseline_valid and match and (case.get("id"), match.group(1)) in exceptions:
                accepted.append(issue)
            else:
                blocking.append(issue)
        missing = _issue_categories(issues)
        blocking_missing = _issue_categories(blocking)
        for category, values in missing.items():
            counts = categories.setdefault(category, {"cases": 0, "issues": 0})
            counts["cases"] += 1
            counts["issues"] += len(values)
        issue_count += len(issues)
        accepted_count += len(accepted)
        blocking_count += len(blocking)
        records.append({"id": case["id"], "material": case.get("material"),
                        "dimension": case.get("dimension"),
                        "status": "incomplete" if issues else "complete",
                        "gate_status": "blocked" if blocking else "accepted",
                        "issues": issues, "accepted_issues": accepted, "blocking_issues": blocking,
                        "missing_categories": missing, "blocking_categories": blocking_missing})
    incomplete = sum(record["status"] == "incomplete" for record in records)
    blocking_cases = sum(record["gate_status"] == "blocked" for record in records)
    gate_status = "blocked" if blocking_cases or integrity_issues else "complete"
    return {"schema_version": 2, "status": "blocked" if incomplete or integrity_issues else "complete",
            "gate_status": gate_status, "integrity_issues": integrity_issues,
            "software_exception_baseline": HISTORICAL_SOFTWARE_EXCEPTIONS.as_posix(),
            "stats": {"total": len(records), "complete": len(records) - incomplete,
                      "incomplete": incomplete, "issue_count": issue_count,
                      "accepted_exception_count": accepted_count,
                      "blocking_case_count": blocking_cases,
                      "blocking_issue_count": blocking_count,
                      "missing_categories": dict(sorted(categories.items()))},
            "cases": records}


def check_completeness(root: Path, sets: list[dict], cases: list[dict], report: dict | None = None) -> None:
    """仅固定历史软件身份缺项可被接受；所有新缺项继续阻断。"""
    report = report if report is not None else completeness_report(root, sets, cases)
    if report["gate_status"] == "blocked":
        details = "\n".join(
            f"{case['id']}:\n" + "\n".join(f"  - {issue}" for issue in case["blocking_issues"])
            for case in report["cases"] if case["blocking_issues"]
        )
        integrity = "\n".join(report["integrity_issues"])
        raise ValueError(
            f"archive CI gate FAILED: {report['stats']['blocking_case_count']}/{len(cases)} calculations have blocking issues\n"
            + "\n".join(value for value in (integrity, details) if value)
        )


def load_records(root: Path) -> tuple[list[dict], list[dict]]:
    sets, cases = [], []
    for path in sorted((root / "data/elements").glob("*/sets/*/set.json")):
        sets.append(json.loads(path.read_text(encoding="utf-8")))
    for path in sorted((root / "data/calculations").glob("*/*/*/record.json")):
        cases.append(json.loads(path.read_text(encoding="utf-8")))
    return sets, cases


def _is_aims_species_defaults(item: dict) -> bool:
    """FHI-aims 物种默认基（species_defaults 角色）是 aims 自身的分级体系
    （如 intermediate_gw）；注册表与哈希绑定校验照旧使用它们，但它们不进入
    公共基组库目录——公共目录只收录 ABACUS 的赝势/物理轨道/辅助基记录。"""
    return any(file_item.get("role") == "species_defaults" for file_item in item.get("files", []))


def _public_entry(item: dict) -> dict:
    """publication 字段随可发布性概念一并从公共目录移除；归档注册表原样保留。"""
    return {key: value for key, value in item.items() if key != "publication"}


def build_catalog(root: Path) -> dict:
    sets, cases = load_records(root)
    validate(root, sets, cases)
    catalog_cases = []
    for case in cases:
        issues = completeness_issues(root, sets, case)
        catalog_cases.append({**case, "archive_completeness": {
            "status": "incomplete" if issues else "complete",
            "issues": issues,
        }})
    return enrich_catalog({
        "schema_version": 1,
        "basis_sets": [_public_entry(item) for item in sets if not _is_aims_species_defaults(item)],
        "calculations": [_public_entry(case) for case in catalog_cases],
    })


def sync_catalog(root: Path, catalog: dict, write: bool = False) -> None:
    target = root / "database/data.json"
    expected = (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(expected)
        return
    if not target.is_file() or target.read_bytes() != expected:
        raise ValueError("database/data.json is missing or stale; run with --write-catalog")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write-catalog", action="store_true")
    parser.add_argument("--check-catalog", action="store_true")
    parser.add_argument("--check-completeness", action="store_true")
    parser.add_argument("--completeness-report", type=Path, help="将全部case、统计和缺证分类写入JSON；缺证仍非零退出")
    args = parser.parse_args()
    if args.check_catalog and args.write_catalog:
        parser.error("--write-catalog and --check-catalog are mutually exclusive")
    if args.check_completeness or args.completeness_report:
        sets, cases = load_records(args.root)
        report = completeness_report(args.root, sets, cases)
        if args.completeness_report:
            args.completeness_report.parent.mkdir(parents=True, exist_ok=True)
            args.completeness_report.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                                encoding="utf-8")
        try:
            check_completeness(args.root, sets, cases, report)
        except ValueError as exc:
            print(str(exc))
            return 1
        print(
            f"archive CI gate OK: {len(cases)} calculations; "
            f"{report['stats']['accepted_exception_count']} grandfathered software identity issues retained in raw report"
        )
    catalog = build_catalog(args.root)
    if args.check_catalog:
        sync_catalog(args.root, catalog, write=False)
    if args.write_catalog:
        sync_catalog(args.root, catalog, write=True)
    print(f"library OK: {len(catalog['basis_sets'])} basis sets, {len(catalog['calculations'])} calculations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
