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
STATUSES = {
    "gw_validated", "gw_diagnostic", "path_diagnostic", "pbe_only",
    "generation_only", "failed", "pending",
}
GROUPS = {"inputs", "results", "logs", "figures"}
PRIVATE_PATH = re.compile(
    r"(?:/" + r"Users/|/" + r"home/[A-Za-z0-9_.-]+|/work[0-9]/|/scratch/|/private/var/|file:" + r"//|ssh:" + r"//)"
)
PUBLICATION_STATES = {"database_only", "review", "publishable", "superseded", "legacy_incomplete"}
INTERMEDIATE_PATH = re.compile(
    r"(?:^|/)(?:tmp|temp|scratch|restart|intermediate|out_wfc|out_chg)(?:/|$)|"
    r"(?:\.tmp|\.part|\.bak|\.wfc|\.cube)$",
    re.IGNORECASE,
)
PROPERTY_CATEGORY = re.compile(r"^[a-z][a-z0-9_]*$")
PROPERTY_STATUSES = {"reported", "validated", "provisional", "failed"}


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


def _publication(item: dict, label: str) -> dict:
    value = item.get("publication", {})
    if value is None:
        value = {}
    if not isinstance(value, dict):
        _fail(f"{label}.publication: expected an object")
    status = value.get("status", "database_only")
    if status not in PUBLICATION_STATES:
        _fail(f"{label}.publication.status: unsupported status {status!r}")
    return value


def _require_public_source(item: dict, label: str) -> None:
    source = item.get("source")
    if not isinstance(source, dict):
        _fail(f"{label}: publishable basis requires source metadata")
    url = source.get("url")
    if not isinstance(url, str) or not re.match(r"^https?://\S+$", url):
        _fail(f"{label}: publishable basis requires a public source URL")
    if not isinstance(source.get("license"), str) or not source["license"].strip():
        _fail(f"{label}: publishable basis requires a license")
    if source.get("redistribution") != "permitted":
        _fail(f"{label}: redistribution must be explicitly permitted")


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
    set_publications = {}
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
        if not roles.intersection({"pp", "nao", "abf"}):
            _fail(f"{label}: no basis payload is registered")
        publication = _publication(item, label)
        set_publications[set_id] = publication
        if publication.get("status") == "publishable":
            if not {"pp", "nao", "abf"}.issubset(roles):
                _fail(f"{label}: publishable basis requires PP, physical NAO, and ABF files")
            _require_public_source(item, label)
            linked_cases = publication.get("calculation_ids")
            if not isinstance(linked_cases, list) or not linked_cases:
                _fail(f"{label}: publishable basis requires linked calculations")
        by_id[set_id] = item

    all_case_ids = {case.get("id") for case in cases if isinstance(case.get("id"), str)}
    case_ids = set()
    case_publications = {}
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        check_private_paths(case, label)
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            _fail(f"{label}: missing or duplicate id")
        case_ids.add(case_id)
        publication = _publication(case, label)
        case_publications[case_id] = publication
        if case.get("dimension") not in {"2d", "3d"}:
            _fail(f"{label}: dimension must be 2d or 3d")
        if case.get("status") not in STATUSES:
            _fail(f"{label}: unsupported status")
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
        for name in ("abacus", "librpa"):
            app = software.get(name)
            if not isinstance(app, dict):
                _fail(f"{label}: software.{name} must be an object")
            commit = app.get("commit")
            if commit is not None and (not isinstance(commit, str) or not COMMIT.fullmatch(commit)):
                _fail(f"{label}: software.{name}.commit must be a full commit or null")
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
                if publication.get("status") == "publishable" and INTERMEDIATE_PATH.search(file_item["path"]):
                    _fail(f"{label}: publishable case contains an intermediate file")

        _validate_properties(case, label, declared_paths)
        _validate_paper_values(root, case, label)

        if publication.get("status") == "publishable":
            if case.get("status") != "gw_validated":
                _fail(f"{label}: publishable case must be gw_validated")
            for name in ("abacus", "librpa"):
                commit = software[name].get("commit")
                if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
                    _fail(f"{label}: publishable case requires a full {name} commit")
            if not files.get("inputs"):
                _fail(f"{label}: publishable case requires at least one input file")
            if not files.get("results"):
                _fail(f"{label}: publishable case requires at least one final result file")
            linked_sets = publication.get("basis_set_ids")
            if not isinstance(linked_sets, list) or not linked_sets:
                _fail(f"{label}: publishable case requires linked basis sets")
            exact_sets = {entry.get("set_id") for entry in species if entry.get("set_id")}
            if not set(linked_sets).issubset(exact_sets):
                _fail(f"{label}: publishable basis links must match exact species bindings")
            for set_id in linked_sets:
                if set_id not in by_id:
                    _fail(f"{label}: unknown publishable basis set {set_id}")
                if set_publications[set_id].get("status") != "publishable":
                    _fail(f"{label}: linked basis set {set_id} is not publishable")
        recommendation = case.get("recommendation")
        if recommendation is not None:
            if case.get("status") != "gw_validated":
                _fail(f"{label}: recommendation requires a GW-validated case")
            if not recommendation.get("scope") or not recommendation.get("evidence_case_ids"):
                _fail(f"{label}: recommendation needs a narrow scope and evidence")
            if any(ref not in all_case_ids for ref in recommendation["evidence_case_ids"]):
                _fail(f"{label}: recommendation references an unknown case")

    for set_id, publication in set_publications.items():
        if publication.get("status") != "publishable":
            continue
        for case_id in publication["calculation_ids"]:
            if case_id not in case_publications:
                _fail(f"basis set {set_id}: unknown linked calculation {case_id}")
            case_publication = case_publications[case_id]
            if case_publication.get("status") != "publishable" or set_id not in case_publication.get("basis_set_ids", []):
                _fail(f"basis set {set_id}: calculation link is not reciprocal")



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
    if name == "librpa.in":
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


def _basis_payload(data: bytes, item: dict, element: str, *, generic_auxiliary: bool = False) -> bool:
    text = data.decode("utf-8", errors="replace")
    suffix = PurePosixPath(item.get("path", "")).suffix.lower()
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

    inputs = {}
    for name in ("INPUT", "KPT", "STRU", "librpa.in"):
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
        for role in ("pp", "nao", "abf"):
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
    for role in ("nao", "abf"):
        if inputs["STRU"] and role not in declared_roles:
            issues.append(f"STRU: at least one production STRU must declare exact {role} payloads")

    for name in ("abacus", "librpa"):
        app = case.get("software", {}).get(name, {})
        if not isinstance(app.get("commit"), str) or not COMMIT.fullmatch(app["commit"]):
            issues.append(f"software.{name}.commit: full immutable commit is required")

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


def completeness_report(root: Path, sets: list[dict], cases: list[dict]) -> dict:
    """保留全部case和缺证分类；schema/hash错误也阻断门槛。"""
    integrity_issues = []
    try:
        validate(root, sets, cases)
    except ValueError as exc:
        integrity_issues.append(str(exc))
    records = []
    categories = {}
    issue_count = 0
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
        missing = {}
        for issue in issues:
            category = issue.split(":", 1)[0].split(" ", 1)[0].split(".", 1)[0].lower()
            category = {"input": "inputs", "stru": "basis_binding", "species": "basis_binding"}.get(category, category)
            missing.setdefault(category, []).append(issue)
        for category, values in missing.items():
            counts = categories.setdefault(category, {"cases": 0, "issues": 0})
            counts["cases"] += 1
            counts["issues"] += len(values)
        issue_count += len(issues)
        records.append({"id": case["id"], "material": case.get("material"),
                        "dimension": case.get("dimension"), "scientific_status": case.get("status"),
                        "status": "incomplete" if issues else "complete",
                        "issues": issues, "missing_categories": missing})
    incomplete = sum(record["status"] == "incomplete" for record in records)
    return {"schema_version": 1, "status": "blocked" if incomplete or integrity_issues else "complete",
            "integrity_issues": integrity_issues,
            "stats": {"total": len(records), "complete": len(records) - incomplete,
                      "incomplete": incomplete, "issue_count": issue_count,
                      "missing_categories": dict(sorted(categories.items()))},
            "cases": records}


def check_completeness(root: Path, sets: list[dict], cases: list[dict], report: dict | None = None) -> None:
    """报告全部不完整记录，不使用历史、科学状态或基线白名单。"""
    report = report if report is not None else completeness_report(root, sets, cases)
    if report["status"] == "blocked":
        details = "\n".join(f"{case['id']}:\n" + "\n".join(f"  - {issue}" for issue in case["issues"])
                            for case in report["cases"] if case["issues"])
        integrity = "\n".join(report["integrity_issues"])
        raise ValueError(f"archive completeness FAILED: {report['stats']['incomplete']}/{len(cases)} calculations incomplete\n"
                         + "\n".join(value for value in (integrity, details) if value))


def load_records(root: Path) -> tuple[list[dict], list[dict]]:
    sets, cases = [], []
    for path in sorted((root / "data/elements").glob("*/sets/*/set.json")):
        sets.append(json.loads(path.read_text(encoding="utf-8")))
    for path in sorted((root / "data/calculations").glob("*/*/*/record.json")):
        cases.append(json.loads(path.read_text(encoding="utf-8")))
    return sets, cases


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
        "basis_sets": sets,
        "calculations": catalog_cases,
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
        print(f"archive completeness OK: {len(cases)} calculations")
    catalog = build_catalog(args.root)
    if args.check_catalog:
        sync_catalog(args.root, catalog, write=False)
    if args.write_catalog:
        sync_catalog(args.root, catalog, write=True)
    print(f"library OK: {len(catalog['basis_sets'])} basis sets, {len(catalog['calculations'])} calculations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
