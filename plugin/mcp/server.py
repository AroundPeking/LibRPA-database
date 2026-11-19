#!/usr/bin/env python3
"""Read-only MCP server for the LibRPA materials database.

Serves the public catalog and every archived payload byte over plain HTTPS,
so it needs no credentials, no clone of the repository, and no third-party
Python packages -- only the standard library.

Reading is all this server does. New calculations reach the database only as
reviewed GitHub pull requests; the ``contribution_guide`` tool and the
``contribute-calculation`` prompt describe that path, and the intake skill in
``plugin/skills/librpa-database-intake`` carries the full procedure.

Endpoints (all overridable through environment variables):
  LIBRPA_DB_CATALOG_URL  catalog JSON   (default: the published data.json;
                                         a local file path also works)
  LIBRPA_DB_SITE_ROOT    site root      (default: the GitHub Pages deploy)
  LIBRPA_DB_CACHE_DIR    payload cache  (default: system temp dir)
  LIBRPA_DB_TTL_SECONDS  catalog cache  (default: 600)

Referenced-tier payloads live in the HuggingFace dataset and carry a mirror
URL; both are tried and every byte is verified against the declared SHA-256
before it is returned. Networks that need a proxy should export HTTPS_PROXY
(the standard library honors it automatically).

Run:  python3 server.py      (speaks MCP over stdio, one JSON message per line)
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

SERVER_NAME = "librpa-database"
SERVER_VERSION = "1.1.0"
DEFAULT_CATALOG_URL = "https://aroundpeking.github.io/LibRPA-database/database/data.json"
DEFAULT_SITE_ROOT = "https://aroundpeking.github.io/LibRPA-database"
REPOSITORY_URL = "https://github.com/AroundPeking/LibRPA-database"
USER_AGENT = "librpa-database-mcp/1.1"
TEXT_LIMIT_DEFAULT = 65536
TEXT_LIMIT_MAX = 4 * 1024 * 1024

_catalog_cache = {"data": None, "fetched": 0.0}


def _catalog_url() -> str:
    return os.environ.get("LIBRPA_DB_CATALOG_URL", DEFAULT_CATALOG_URL)


def _site_root() -> str:
    return os.environ.get("LIBRPA_DB_SITE_ROOT", DEFAULT_SITE_ROOT).rstrip("/")


def _cache_dir() -> Path:
    return Path(os.environ.get("LIBRPA_DB_CACHE_DIR",
                               Path(tempfile.gettempdir()) / "librpa-db-payloads"))


def _fetch(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as error:  # noqa: BLE001 - retried, then raised
            last_error = error
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"unreachable: {url} ({last_error})")


def _load_catalog() -> dict:
    ttl = float(os.environ.get("LIBRPA_DB_TTL_SECONDS", "600"))
    now = time.time()
    if _catalog_cache["data"] is not None and now - _catalog_cache["fetched"] < ttl:
        return _catalog_cache["data"]
    location = _catalog_url()
    if location.startswith(("https://", "http://")):
        data = json.loads(_fetch(location).decode("utf-8"))
    else:
        path = Path(location[7:] if location.startswith("file://") else location)
        data = json.loads(path.read_text(encoding="utf-8"))
    _catalog_cache["data"] = data
    _catalog_cache["fetched"] = now
    return data


def _records() -> list:
    return _load_catalog().get("calculations", [])


def _basis_sets() -> list:
    return _load_catalog().get("basis_sets", [])


def _find_record(record_id: str) -> dict:
    for record in _records():
        if record.get("id") == record_id:
            return record
    known = ", ".join(record.get("id", "?") for record in _records()[:8])
    raise KeyError(f"unknown record id {record_id!r} (catalog starts with: {known} ...); "
                   "use search_materials to find ids")


def _find_basis_set(set_id: str) -> dict:
    for entry in _basis_sets():
        if entry.get("id") == set_id:
            return entry
    raise KeyError(f"unknown basis set id {set_id!r}; use list_basis_sets to find ids")


def _file_url(file: dict) -> str:
    url = file.get("external_url")
    if isinstance(url, str) and url.startswith("https://"):
        return url
    path = quote(str(file.get("path", "")), safe="/")
    return f"{_site_root()}/{path}"


def _file_urls(file: dict) -> list:
    urls = [_file_url(file)]
    backup = file.get("external_url_backup")
    if isinstance(backup, str) and backup.startswith("https://"):
        urls.append(backup)
    return urls


def _cache_path(file: dict) -> Path:
    digest = file.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("payload requires a lowercase SHA-256 digest")
    return _cache_dir() / digest[:2] / digest


def _download_verified(url: str, file: dict, cache: Path) -> Path:
    """Stream one URL into a temporary file and atomically cache valid bytes."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    expected = file["sha256"]
    expected_size = file.get("size_bytes")
    cache.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(3):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix=cache.name + ".", suffix=".part",
                                             dir=cache.parent, delete=False) as handle:
                temporary = Path(handle.name)
            digest = hashlib.sha256()
            size = 0
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as stream:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                    stream.write(chunk)
            if digest.hexdigest() != expected:
                raise RuntimeError(f"SHA-256 mismatch at {url}")
            if isinstance(expected_size, int) and not isinstance(expected_size, bool) and size != expected_size:
                raise RuntimeError(f"size mismatch at {url}: {size} != {expected_size}")
            temporary.replace(cache)
            return cache
        except Exception as error:  # noqa: BLE001 - retry and then try the mirror
            last_error = error
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    raise RuntimeError(f"no verified payload at {url} ({last_error})")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_path(file: dict) -> Path:
    """Return exact verified bytes without reading the whole payload into RAM."""
    cache = _cache_path(file)
    expected_size = file.get("size_bytes")
    if cache.is_file():
        valid = _sha256_of(cache) == file["sha256"]
        if valid and isinstance(expected_size, int) and not isinstance(expected_size, bool):
            valid = cache.stat().st_size == expected_size
        if valid:
            return cache
        cache.unlink(missing_ok=True)
    last_error = None
    for url in _file_urls(file):
        try:
            return _download_verified(url, file, cache)
        except RuntimeError as error:
            last_error = error
    raise RuntimeError(f"could not fetch {file.get('path', '?')} with a matching hash "
                       f"({last_error})")


def _payload_bytes(file: dict) -> bytes:
    # Band-table parsing genuinely needs the complete table. Text previews use
    # _payload_path directly and stay bounded by their requested prefix instead.
    return _payload_path(file).read_bytes()


# ---------------------------------------------------------------------------
# Record interpretation. These readers mirror database/records.mjs and
# database/gaps.mjs line for line, so an agent sees the same chips, gaps, and
# headline values as the website; tests/test_mcp_server.py compares both
# implementations over the whole catalog.
# ---------------------------------------------------------------------------

ELEMENT_SYMBOLS = frozenset((
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr "
    "Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu "
    "Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr "
    "Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og").split())
RECORD_TYPES = ("band", "large_system_gw", "rpa_energy", "reader_conversion")
MEAN_FIELD_FUNCTIONALS = ("PBE", "LDA", "GGA", "PBEsol", "SCAN", "HSE")
METHOD_FACETS = ("GW", "EXX", "RPA", "Delta-ST", "SPIN", "SOC")
GAP_SCOPES = {
    "band": "band-structure record; the value keeps the record's own gap definition "
            "(often a sampled k-path observable, not a global fundamental gap)",
    "path": "restricted raw-band or frontier path observable",
    "sampled": "sampled Gamma-point observable on a regular grid",
}


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _integer(value) -> bool:
    # JavaScript's Number.isInteger also accepts integral floats such as 2.0.
    return _number(value) and float(value).is_integer()


def _files_of(record: dict, group: str) -> list:
    files = (record.get("files") or {}).get(group)
    return files if isinstance(files, list) else []


def _record_type(record: dict) -> str:
    kind = record.get("record_type")
    return kind if kind in RECORD_TYPES else "band"


def _frontend(record: dict) -> str:
    return "fhi_aims" if (record.get("workflow") or {}).get("frontend") == "fhi_aims" else "abacus"


def _workflow_label(record: dict) -> str:
    workflow = record.get("workflow") or {}
    label = "FHI-aims" if _frontend(record) == "fhi_aims" else "ABACUS"
    if _frontend(record) == "fhi_aims" and workflow.get("task") == "gw":
        return label
    if workflow.get("response") == "delta_sternheimer":
        if workflow.get("rpa_evaluation") == "archived_campaign_script":
            return f"{label} Delta-Sternheimer"
        return f"{label} Delta-Sternheimer + LibRPA"
    return f"{label} + LibRPA"


def _record_elements(record: dict) -> list:
    elements = {item.get("element") for item in
                [*(record.get("species") or []), *(record.get("basis_candidates") or [])]
                if isinstance(item, dict) and item.get("element")}
    formula = str(record.get("formula") or record.get("material") or "")
    elements.update(symbol for symbol in re.findall(r"[A-Z][a-z]?", formula) if symbol in ELEMENT_SYMBOLS)
    return sorted(elements)


def _method_names(record: dict) -> list:
    # `${undefined}` renders as "undefined" in the JavaScript reader; keep the
    # same corpus so both readers light exactly the same chips.
    corpus = " ".join(f"{entry.get('label') or ''} {'undefined' if entry.get('path') is None else str(entry['path']).split('/')[-1]}"
                      for entry in [*_files_of(record, "results"), *_files_of(record, "logs")])
    active = [item for item in record.get("properties") or []
              if item.get("category") == "electronic" and item.get("status") != "failed"]
    props = " ".join(str(item.get("method") or "") for item in active)
    run = record.get("associated_gw_run") or {}
    associated = (run.get("task") or "G0W0") if run.get("scheduler_state") == "COMPLETED" else ""
    declared = record.get("functional") if record.get("functional") in MEAN_FIELD_FUNCTIONALS else None
    from_properties = {item.get("method") for item in active if item.get("method") in MEAN_FIELD_FUNCTIONALS}
    functional = declared or (next(iter(from_properties)) if len(from_properties) == 1 else None)
    evidence = f"{corpus} {props} {associated}"
    methods = []
    if declared or re.search(r"(?:^|[^a-z])(?:KS|PBEsol|PBE|SCAN|HSE|LDA|GGA|DFT)(?:[^a-z]|$)", evidence, re.I):
        methods.append(functional or "DFT")
    if re.search(r"(?:^|[^a-z])EXX(?:[^a-z]|$)", evidence, re.I):
        methods.append("EXX")
    if re.search(r"(?:^|[^a-z])(?:GW|G0W0)(?:[^a-z]|$)", evidence, re.I):
        methods.append("GW")
    if _record_type(record) == "rpa_energy" or any(
            item.get("method") == "RPA" and item.get("status") != "failed" for item in record.get("properties") or []):
        methods.append("RPA")
    if (record.get("workflow") or {}).get("response") == "delta_sternheimer":
        methods.append("Delta-ST")
    return methods


def _method_chips(record: dict) -> list:
    chips = list(_method_names(record))
    if record.get("spin_polarized") is True:
        chips.append("SPIN")
    if record.get("spin_orbit") is True:
        chips.append("SOC")
    return list(dict.fromkeys(chips))


def _paper_gap(record: dict, method: str):
    paper = record.get("paper_values")
    if not isinstance(paper, dict):
        return None
    value = (paper.get("values") or {}).get(method)
    source = paper.get("source")
    if not isinstance(value, dict) or not isinstance(source, dict):
        return None
    if (not re.fullmatch(r"[0-9a-f]{64}", str(source.get("document_sha256") or ""), re.I)
            or not _integer(source.get("pdf_page")) or source["pdf_page"] < 1 or not source.get("table")
            or not any(entry.get("path") == paper.get("evidence")
                       and re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256") or ""), re.I)
                       for entry in _files_of(record, "results"))
            or not value or value.get("unit") != "eV" or not _number(value.get("value"))
            or not _integer(value.get("precision")) or not 0 <= value["precision"] <= 8 or not value.get("column")):
        return None
    return value


def _archived_band_gap(record: dict, method: str):
    matches = [item for item in record.get("properties") or []
               if item.get("category") == "electronic"
               and re.fullmatch(r"(?:band_gap|sampled_path_gap(?:_ev)?|path_gap(?:_ev)?)", str(item.get("key") or ""))
               and _gap_family(item.get("method")) == method]
    if matches:
        only = matches[0]
        valid = (len(matches) == 1 and only.get("unit") == "eV" and only.get("status") != "failed"
                 and _number(only.get("value")))
        return only["value"] if valid else None
    summary = record.get("summary") or {}
    if method == "DFT":
        value = summary.get("dft_gap_ev") if summary.get("dft_gap_ev") is not None else summary.get("pbe_gap_ev")
    else:
        value = summary.get("exx_gap_ev" if method == "EXX" else "gw_gap_ev")
    if _number(value):
        return value
    if (method == "GW" and re.search(r"(?:GW|G0W0).*gap", str(summary.get("observable") or ""), re.I)
            and summary.get("unit") == "eV" and _number(summary.get("value"))):
        return summary["value"]
    return None


def _band_gap(record: dict, method: str):
    paper = _paper_gap(record, method)
    return paper["value"] if paper else _archived_band_gap(record, method)


# Which family a recorded gap belongs to. This mirrors ``gapFamily`` in
# database/records.mjs: the mean-field bucket is defined by exclusion so that a
# functional the archive has not seen yet (HSE06, PBE0, SCAN, ...) lands in the
# Kohn-Sham column instead of disappearing from the overview.
_MANY_BODY_FAMILY = (
    (re.compile(r"^(?:G0W0|GW|GW path|QSGW)$", re.I), "GW"),
    (re.compile(r"^EXX$", re.I), "EXX"),
    (re.compile(r"^RPA$", re.I), "RPA"),
    (re.compile(r"^BSE$", re.I), "BSE"),
    (re.compile(r"^DMFT$", re.I), "DMFT"),
)


def _gap_family(method) -> str:
    name = str(method or "").strip()
    for pattern, family in _MANY_BODY_FAMILY:
        if pattern.match(name):
            return family
    return "DFT"


def _finite_property(record: dict, predicate):
    matches = [item for item in record.get("properties") or []
               if item.get("status") != "failed" and _number(item.get("value")) and predicate(item)]
    return matches[0] if len(matches) == 1 else None


def _sampled_grid_gap(record: dict, method: str = "G0W0"):
    family = "DFT" if method in ("PBE", "DFT") else _gap_family(method)
    return _finite_property(record, lambda item: item.get("category") == "electronic"
                            and item.get("key") == "sampled_grid_gap_ev" and item.get("unit") == "eV"
                            and _gap_family(item.get("method")) == family)


def _gap_overview(record: dict):
    kind = _record_type(record)
    if kind == "rpa_energy":
        return None
    if kind == "large_system_gw":
        pbe, gw = _sampled_grid_gap(record, "PBE"), _sampled_grid_gap(record, "G0W0")
        if not pbe and not gw:
            return None
        return {"ks": pbe["value"] if pbe else None, "exx": None, "gw": gw["value"] if gw else None, "scope": "sampled"}
    if kind == "reader_conversion":
        run = record.get("associated_gw_run") or {}
        if run.get("scheduler_state") != "COMPLETED":
            return None
        gap = run.get("gap") or {}
        ks = gap["ks_value"] if gap.get("ks_available") and _number(gap.get("ks_value")) else None
        gw = gap["g0w0_value"] if gap.get("g0w0_available") and _number(gap.get("g0w0_value")) else None
        if ks is None and gw is None:
            return None
        return {"ks": ks, "exx": None, "gw": gw, "scope": "sampled"}
    ks, exx, gw = (_band_gap(record, method) for method in ("DFT", "EXX", "GW"))
    if ks is None and exx is None and gw is None:
        return None
    restricted = re.search(r"raw[- ]band|frontier|restricted", str((record.get("summary") or {}).get("observable") or ""), re.I)
    return {"ks": ks, "exx": exx, "gw": gw, "scope": "path" if restricted else "band"}


def _primary_result(record: dict):
    kind = _record_type(record)
    if kind == "large_system_gw":
        item = _sampled_grid_gap(record, "G0W0")
        return {"label": "Sampled Γ G0W0 gap", "value": item["value"], "unit": item.get("unit"),
                "scope": item.get("definition") or "Regular-grid Γ-point observable"} if item else None
    if kind == "rpa_energy":
        for key in ("rpa_dissociation_energy", "rpa_correlation_dissociation_energy", "rpa_cohesive_energy", "rpa_correlation_energy"):
            item = _finite_property(record, lambda entry, key=key: entry.get("key") == key)
            if item:
                return {"label": item.get("label") or "RPA correlation energy", "value": item["value"],
                        "unit": item.get("unit"), "scope": item.get("definition") or ""}
        return None
    if kind == "reader_conversion":
        run = record.get("associated_gw_run") or {}
        if run.get("scheduler_state") == "COMPLETED":
            gap = run.get("gap") or {}
            item = _sampled_grid_gap(record, "G0W0")
            if gap.get("g0w0_available") and _number(gap.get("g0w0_value")):
                return {"label": "Sampled Γ G0W0 gap", "value": gap["g0w0_value"], "unit": "eV",
                        "scope": (item or {}).get("definition") or "Frontier states present in the complete QP output; "
                                                                   "not a full-spectrum finite-table result"}
            return {"label": "Sampled Γ G0W0 gap", "value": "Unavailable", "unit": "",
                    "scope": "Frontier states 4096 and 4097 are missing from the retained QP output; no numerical gap is claimed"}
        rows = (record.get("computational_scale") or {}).get("matrix_rows")
        if _integer(rows) and rows > 0:
            return {"label": "Reader-v1 matrix dimension", "value": rows, "unit": "states",
                    "scope": "Conversion evidence only; no RPA/GW observable"}
        return None
    definition = (record.get("summary") or {}).get("gap_definition") or ""
    value = _band_gap(record, "GW")
    if value is not None:
        return {"label": "GW gap", "value": value, "unit": "eV", "scope": definition}
    for method in ("EXX", "DFT"):
        fallback = _band_gap(record, method)
        if fallback is not None:
            return {"label": f"{method} gap", "value": fallback, "unit": "eV", "scope": definition}
    return None


def _atom_count(record: dict):
    value = (record.get("computational_scale") or {}).get("atom_count")
    return value if _integer(value) and value > 0 else None


def _page_url(record: dict) -> str:
    return f"{_site_root()}/database/#/material/{quote(str(record.get('id', '')), safe='')}"


def _record_json_url(record: dict) -> str:
    parts = ["data", "calculations", record.get("dimension"), record.get("material"), record.get("id"), "record.json"]
    return f"{_site_root()}/" + "/".join(quote(str(part), safe="") for part in parts)


def _gap_values(gaps) -> dict:
    gaps = gaps or {}
    return {"ks_ev": gaps.get("ks"), "exx_ev": gaps.get("exx"), "gw_ev": gaps.get("gw"), "scope": gaps.get("scope")}


def _record_summary(record: dict) -> dict:
    files = record.get("files") or {}
    return {
        "id": record.get("id"),
        "material": record.get("material"),
        "formula": record.get("formula"),
        "dimension": record.get("dimension"),
        "record_type": record.get("record_type"),
        "frontend": _frontend(record),
        "workflow": _workflow_label(record),
        "methods": _method_chips(record),
        "elements": _record_elements(record),
        "spin_orbit": record.get("spin_orbit"),
        "spin_polarized": record.get("spin_polarized"),
        "atom_count": _atom_count(record),
        "gaps": _gap_values(_gap_overview(record)),
        "primary_result": _primary_result(record),
        "summary": record.get("summary"),
        "file_counts": {group: len(entries) for group, entries in files.items() if isinstance(entries, list)},
        "page_url": _page_url(record),
        "record_json_url": _record_json_url(record),
    }


def _searchable_text(record: dict) -> str:
    parts = [str(record.get(key, "")) for key in
             ("id", "material", "formula", "dimension", "record_type", "workflow")]
    parts.append(" ".join(_method_chips(record)))
    parts.append(" ".join(_record_elements(record)))
    parts.append(_workflow_label(record))
    parts.append(record.get("functional") or "")
    if record.get("spin_orbit"):
        parts.append("soc spin_orbit")
    if record.get("spin_polarized"):
        parts.append("spin spin_polarized")
    for property_ in record.get("properties") or []:
        parts.append(str(property_.get("key", "")))
        parts.append(str(property_.get("method", "")))
    return " ".join(parts).lower()


def _band_rows(text: str) -> dict:
    """Parse the archived ABACUS band table exactly as scripts/plot_bands.py does:
    column layout is  k_index  kx  ky  kz  (occupation energy) ...  per line."""
    indices, coordinates, energies, occupations = [], [], [], []
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = raw.split()
        if len(fields) < 6 or (len(fields) - 4) % 2:
            raise ValueError(f"line {number}: expected occupation/energy pairs")
        values = [float(item) for item in fields]
        if not math.isfinite(values[0]) or values[0] != int(values[0]):
            raise ValueError(f"line {number}: k-point index must be an integer")
        if energies and len(values[5::2]) != len(energies[0]):
            raise ValueError(f"line {number}: inconsistent band count")
        indices.append(int(values[0]))
        coordinates.append(values[1:4])
        occupations.append(values[4::2])
        energies.append(values[5::2])
    if not energies:
        raise ValueError("band table contains no data rows")
    return {"indices": indices, "coordinates": coordinates,
            "energies": energies, "occupations": occupations}


def _string_list(value, name: str) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        value = [item for item in re.split(r"[\s,]+", value) if item]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return value


def _optional_number(arguments: dict, name: str):
    value = arguments.get(name)
    if value is None:
        return None
    if not _number(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


# ---------------------------------------------------------------------------
# Tool implementations. Each returns a plain value that is rendered as JSON.
# ---------------------------------------------------------------------------


def tool_database_overview(arguments: dict) -> dict:
    records, sets = _records(), _basis_sets()
    elements, kinds, frontends, dimensions, methods = {}, {}, {}, {}, {}
    for record in records:
        for symbol in _record_elements(record):
            elements[symbol] = elements.get(symbol, 0) + 1
        for bucket, key in ((kinds, _record_type(record)), (frontends, _frontend(record)),
                            (dimensions, record.get("dimension"))):
            bucket[key] = bucket.get(key, 0) + 1
        for chip in _method_chips(record):
            methods[chip] = methods.get(chip, 0) + 1
    return {
        "name": "LibRPA materials database",
        "calculations": len(records),
        "materials": len({record.get("material") for record in records}),
        "basis_sets": len(sets),
        "dimensions": dimensions,
        "record_types": kinds,
        "frontends": frontends,
        "methods": methods,
        "elements": dict(sorted(elements.items())),
        "website": f"{_site_root()}/database/",
        "catalog_url": _catalog_url(),
        "start_with": [
            "search_materials to find records by text, elements, method, front end, or GW-gap range",
            "compare_gaps to put KS, EXX, and GW gaps side by side",
            "get_material, list_files, and read_file for one record and its hash-verified files",
        ],
        "reading_rule": "Quote summary.observable and summary.gap_definition with any gap: many values are "
                        "sampled-path or sampled-Gamma observables, not global fundamental gaps.",
        "writing": "This server is read-only. New data arrives as a GitHub pull request; call contribution_guide.",
    }


def tool_search_materials(arguments: dict) -> dict:
    query = str(arguments.get("query") or "").strip()
    dimension = arguments.get("dimension")
    record_type = arguments.get("record_type")
    frontend = arguments.get("frontend")
    elements = _string_list(arguments.get("elements"), "elements")
    unknown = [symbol for symbol in elements if symbol not in ELEMENT_SYMBOLS]
    if unknown:
        raise ValueError(f"unknown element symbol(s) {unknown}; use symbols such as 'Ga' or 'As'")
    element_mode = arguments.get("element_mode", "all")
    if element_mode not in ("all", "only"):
        raise ValueError("element_mode must be 'all' or 'only'")
    methods = _string_list(arguments.get("methods"), "methods")
    gap_min, gap_max = _optional_number(arguments, "gw_gap_min"), _optional_number(arguments, "gw_gap_max")
    has_inputs = arguments.get("has_inputs")
    limit = max(1, min(int(arguments.get("limit") or 20), 100))
    offset = max(0, int(arguments.get("offset") or 0))
    sort = str(arguments.get("sort", "material"))
    tokens = [token for token in re.split(r"\s+", query.lower()) if token]
    matches = []
    for record in _records():
        if dimension and record.get("dimension") != dimension:
            continue
        if record_type and _record_type(record) != record_type:
            continue
        if frontend and _frontend(record) != frontend:
            continue
        present = set(_record_elements(record))
        if elements and (not set(elements) <= present or (element_mode == "only" and present != set(elements))):
            continue
        chips = {chip.lower() for chip in _method_chips(record)}
        if methods and not all(method.lower() in chips for method in methods):
            continue
        gaps = _gap_overview(record) or {}
        if (gap_min is not None or gap_max is not None) and (
                gaps.get("gw") is None or (gap_min is not None and gaps["gw"] < gap_min)
                or (gap_max is not None and gaps["gw"] > gap_max)):
            continue
        if has_inputs is not None and bool(len(_files_of(record, "inputs"))) != bool(has_inputs):
            continue
        haystack = _searchable_text(record)
        if all(re.search(rf"\b{re.escape(token)}", haystack) for token in tokens):
            matches.append(record)
    keys = {"material": None, "gw_gap": "gw", "ks_gap": "ks", "atoms": "atoms"}
    descending = sort.startswith("-")
    key = keys.get(sort.lstrip("-"))
    if sort.lstrip("-") not in keys:
        raise ValueError(f"sort must be one of {sorted(keys)} with an optional '-' for descending")

    def value_of(record):
        if key == "atoms":
            return _atom_count(record)
        return (_gap_overview(record) or {}).get(key) if key else None

    matches.sort(key=lambda record: (str(record.get("material")), str(record.get("id"))), reverse=descending and key is None)
    if key:
        present_values = [record for record in matches if value_of(record) is not None]
        missing = [record for record in matches if value_of(record) is None]
        present_values.sort(key=value_of, reverse=descending)
        matches = present_values + missing
    page = matches[offset:offset + limit]
    return {"query": query, "total": len(matches), "count": len(page), "offset": offset,
            "records": [_record_summary(record) for record in page]}


def tool_get_material(arguments: dict) -> dict:
    record = _find_record(str(arguments.get("record_id", "")))
    compact = dict(record)
    compact["files"] = {
        group: [{"path": file.get("path"), "name": file.get("name") or Path(str(file.get("path", ""))).name,
                 "tier": file.get("tier", "local"), "size_bytes": file.get("size_bytes"),
                 "role": file.get("role"), "label": file.get("label"),
                 "url": _file_url(file),
                 "mirror_url": file.get("external_url_backup")}
                for file in entries]
        for group, entries in (record.get("files") or {}).items()
    }
    compact["derived"] = {
        "workflow": _workflow_label(record),
        "methods": _method_chips(record),
        "elements": _record_elements(record),
        "gaps": _gap_values(_gap_overview(record)),
        "primary_result": _primary_result(record),
        "page_url": _page_url(record),
        "record_json_url": _record_json_url(record),
    }
    return compact


def tool_list_files(arguments: dict) -> dict:
    record = _find_record(str(arguments.get("record_id", "")))
    group = arguments.get("group")
    files = record.get("files") or {}
    groups = [group] if group else list(files)
    unknown = [name for name in groups if name not in files]
    if unknown:
        raise ValueError(f"unknown file group(s) {unknown}; known: {list(files)}")
    entries = []
    for name in groups:
        for file in files.get(name, []):
            entries.append({"group": name, "path": file.get("path"),
                            "name": file.get("name") or Path(str(file.get("path", ""))).name,
                            "tier": file.get("tier", "local"),
                            "size_bytes": file.get("size_bytes"),
                            "role": file.get("role"), "label": file.get("label"),
                            "url": _file_url(file), "mirror_url": file.get("external_url_backup")})
    return {"record_id": record.get("id"), "count": len(entries), "files": entries}


def tool_read_file(arguments: dict) -> dict:
    record = _find_record(str(arguments.get("record_id", "")))
    wanted = str(arguments.get("path", ""))
    declared = [file for group in (record.get("files") or {}).values() for file in group]
    file = next((entry for entry in declared if entry.get("path") == wanted), None)
    if file is None:
        raise ValueError(f"{wanted!r} is not declared in {record.get('id')}; "
                         "use list_files to see the declared paths")
    max_bytes = max(1, min(int(arguments.get("max_bytes", TEXT_LIMIT_DEFAULT)), TEXT_LIMIT_MAX))
    cached = _payload_path(file)
    size = cached.stat().st_size
    with cached.open("rb") as stream:
        prefix = stream.read(4096)
    if b"\x00" in prefix:
        return {"path": wanted, "binary": True, "size_bytes": size,
                "sha256_verified": True, "cached_at": str(cached),
                "note": "binary payload; the cached file holds the exact verified bytes"}
    # TextIOWrapper may decode a small buffered block, but never requires the
    # full archived file. One extra character determines truncation exactly.
    with cached.open("r", encoding="utf-8", errors="replace") as stream:
        preview = stream.read(max_bytes + 1)
    truncated = len(preview) > max_bytes
    return {"path": wanted, "size_bytes": size, "sha256_verified": True,
            "truncated": truncated, "content": preview[:max_bytes]}


def tool_get_band_table(arguments: dict) -> dict:
    record = _find_record(str(arguments.get("record_id", "")))
    method = str(arguments.get("method", "GW")).upper()
    if method not in {"KS", "EXX", "GW"}:
        raise ValueError("method must be one of KS, EXX, GW")
    results = (record.get("files") or {}).get("results", [])
    file = next((entry for entry in results
                 if str(entry.get("path", "")).endswith((f"{method}_band_spin_1.dat",
                                                         f"{method}_bands.dat"))), None)
    if file is None:
        available = sorted(str(entry.get("path", "")).split("/")[-1] for entry in results)
        raise ValueError(f"no {method} band table in {record.get('id')}; "
                         f"result files: {available}")
    table = _band_rows(_payload_bytes(file).decode("utf-8", errors="replace"))
    band_start = int(arguments.get("band_start", 1))
    band_count = int(arguments.get("band_count", 0)) or len(table["energies"][0])
    band_end = min(band_start - 1 + band_count, len(table["energies"][0]))
    if band_start < 1 or band_start > len(table["energies"][0]):
        raise ValueError(f"band_start must be within 1..{len(table['energies'][0])}")
    energies = [row[band_start - 1:band_end] for row in table["energies"]]
    occupations = [row[band_start - 1:band_end] for row in table["occupations"]]
    return {"record_id": record.get("id"), "method": method, "source_path": file.get("path"),
            "n_kpoints": len(table["indices"]), "n_bands_total": len(table["energies"][0]),
            "band_range": [band_start, band_end],
            "k_indices": table["indices"], "k_coordinates": table["coordinates"],
            "energies_ev": energies, "occupations": occupations,
            "column_layout": "k_index kx ky kz then (occupation energy) pairs per line"}


def tool_compare_gaps(arguments: dict) -> dict:
    material = str(arguments.get("material") or "").strip().lower()
    record_ids = set(_string_list(arguments.get("record_ids"), "record_ids"))
    elements = set(_string_list(arguments.get("elements"), "elements"))
    frontend = arguments.get("frontend")
    sort = arguments.get("sort", "gw")
    if sort not in ("gw", "material"):
        raise ValueError("sort must be 'gw' or 'material'")
    rows = []
    for record in _records():
        if material and material not in {str(record.get("material") or "").lower(), str(record.get("formula") or "").lower()}:
            continue
        if record_ids and record.get("id") not in record_ids:
            continue
        if elements and not elements <= set(_record_elements(record)):
            continue
        if frontend and _frontend(record) != frontend:
            continue
        gaps = _gap_overview(record)
        if not gaps:
            continue
        summary = record.get("summary") or {}
        rows.append({"record_id": record.get("id"), "material": record.get("material"),
                     "dimension": record.get("dimension"), "workflow": _workflow_label(record),
                     "ks_gap_ev": gaps["ks"], "exx_gap_ev": gaps["exx"], "gw_gap_ev": gaps["gw"],
                     "scope": gaps["scope"], "observable": summary.get("observable"),
                     "gap_definition": summary.get("gap_definition"), "page_url": _page_url(record)})
    if sort == "material":
        rows.sort(key=lambda row: (str(row["material"]), str(row["record_id"])))
    else:
        rows.sort(key=lambda row: (row["gw_gap_ev"] is None, -(row["gw_gap_ev"] or 0), str(row["material"])))
    return {"count": len(rows), "unit": "eV", "scope_legend": GAP_SCOPES,
            "note": "Each value keeps its record's own definition; compare across codes only when "
                    "observable and gap_definition agree.", "rows": rows}


def _basis_label(entry: dict):
    label = entry.get("label")
    if not isinstance(label, dict):
        return None
    shape = lambda part: ({"shells": part.get("shells"), "dimension_per_atom": part.get("dimension_per_atom")}
                          if isinstance(part, dict) else None)
    return {"sentence": label.get("sentence"), "valence_electrons": label.get("valence_electrons"),
            "orbital": shape(label.get("orbital")), "auxiliary": shape(label.get("auxiliary")),
            "uses": len(label.get("uses") or [])}


def tool_list_basis_sets(arguments: dict) -> dict:
    element = arguments.get("element")
    sets = []
    for entry in _basis_sets():
        if element and entry.get("element") != element:
            continue
        sets.append({
            "id": entry.get("id"), "element": entry.get("element"), "family": entry.get("family"),
            "origin": (entry.get("publication") or {}).get("status"),
            "label": _basis_label(entry),
            "files": [{"role": file.get("role"), "name": file.get("name"),
                       "tier": file.get("tier", "local"),
                       "size_bytes": file.get("size_bytes"), "url": _file_url(file)}
                      for file in entry.get("files", [])],
        })
    return {"count": len(sets), "basis_sets": sets}


def tool_get_basis_set(arguments: dict) -> dict:
    entry = _find_basis_set(str(arguments.get("set_id", "")))
    set_id = entry.get("id")
    linked = []
    for record in _records():
        exact = any(item.get("set_id") == set_id for item in record.get("species") or [])
        candidate = any(item.get("set_id") == set_id for item in record.get("basis_candidates") or [])
        if exact or candidate:
            linked.append({"record_id": record.get("id"), "material": record.get("material"),
                           "relation": "exact binding" if exact else "candidate only",
                           "primary_result": _primary_result(record)})
    return {"id": set_id, "element": entry.get("element"), "family": entry.get("family"),
            "label": _basis_label(entry), "validation_scope": entry.get("validation_scope"),
            "notes": entry.get("notes"), "source": entry.get("source"),
            "generation_provenance": entry.get("generation_provenance"),
            "files": [{"role": file.get("role"), "name": file.get("name"), "path": file.get("path"),
                       "tier": file.get("tier", "local"), "size_bytes": file.get("size_bytes"),
                       "sha256": file.get("sha256"), "url": _file_url(file)}
                      for file in entry.get("files", [])],
            "linked_calculations": linked}


CONTRIBUTION_GUIDE = {
    "principle": "The database has no write API. A new calculation is a GitHub pull request: CI runs the "
                 "repository gates on it, a maintainer reviews it, and merging publishes it.",
    "steps": [
        "Fork AroundPeking/LibRPA-database and create a branch named add/<case-id>.",
        "Validate the run scientifically from its own program output (never from scheduler state alone); "
        "state the observable and its exact scope.",
        "Create data/calculations/<2d|3d>/<Material>/<case-id>/ with record.json plus inputs/, results/, "
        "logs/, and figures/. Sanitize private paths and scheduler identifiers before hashing.",
        "Record path, size_bytes, and sha256 for every file; give both the front end and LibRPA a full "
        "40-hex source commit or the executable SHA-256.",
        "Regenerate generated files with the scripts, never by hand: scripts/library.py --write-catalog, "
        "scripts/build_indexes.py --write, scripts/export_missing_evidence.py --write, then copy "
        "database/archive-completeness.json to the repository root.",
        "Run the gates: scripts/library.py --check-catalog, scripts/build_indexes.py --check, "
        "scripts/public_scan.py ., python -m unittest discover -s tests, node --test tests/*.mjs.",
        "Push the branch and open a pull request titled 'Add <case-id> (<record_type>)'. Fill in the "
        "template: source run, observable and scope, evidence checklist, limitations.",
        "After merge, the Publish workflow deploys the record and the External archive sync moves the "
        "payload bytes to the dataset archive; contributors need no archive account.",
    ],
    "record_types": list(RECORD_TYPES),
    "never": [
        "push to main or force-push",
        "hand-edit database/data.json, data/log-index.json, or database/missing-evidence.html",
        "invent or relabel values (a sampled-path gap is not a fundamental gap)",
        "guess software identity or extend the historical exception lists",
        "archive private paths, hostnames, credentials, or unlicensed binaries",
    ],
    "links": {
        "contributing": f"{REPOSITORY_URL}/blob/main/CONTRIBUTING.md",
        "intake_skill": f"{REPOSITORY_URL}/blob/main/plugin/skills/librpa-database-intake/SKILL.md",
        "schema": f"{REPOSITORY_URL}/blob/main/references/database.md",
        "pull_request_template": f"{REPOSITORY_URL}/blob/main/.github/pull_request_template.md",
    },
}


def tool_contribution_guide(arguments: dict) -> dict:
    return CONTRIBUTION_GUIDE


# ---------------------------------------------------------------------------
# Minimal MCP stdio transport: newline-delimited JSON-RPC 2.0.
# ---------------------------------------------------------------------------

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
METHOD_LIST = {"type": "array", "items": {"type": "string", "enum": list(METHOD_FACETS) + list(MEAN_FIELD_FUNCTIONALS)}}

TOOLS = [
    {
        "name": "database_overview",
        "title": "Database overview",
        "description": "Counts of calculations, materials, and basis sets; records per element, record type, "
                       "front end, dimension, and method; and how to start. Call this first.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_materials",
        "title": "Search calculation records",
        "description": "Search the LibRPA materials database catalog. Optional free text (all whitespace-"
                       "separated tokens must match against material, formula, id, elements, front end, "
                       "method chips such as GW, EXX, PBE, RPA, SOC, SPIN, and property keys) combined with "
                       "filters: elements (contains all, or only these), dimension, front end, record type, "
                       "methods, GW-gap range in eV, and input availability. Returns sorted record summaries "
                       "with gap values, headline result, and URLs.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "e.g. 'Si GW', 'MoS2 2d', 'soc'; omit to list"},
            "elements": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['Ga', 'As']"},
            "element_mode": {"type": "string", "enum": ["all", "only"], "default": "all",
                             "description": "'all': contains every element; 'only': exactly this chemical system"},
            "dimension": {"type": "string", "enum": ["2d", "3d"]},
            "frontend": {"type": "string", "enum": ["abacus", "fhi_aims"]},
            "record_type": {"type": "string", "enum": list(RECORD_TYPES)},
            "methods": {**METHOD_LIST, "description": "every listed method chip must be present"},
            "gw_gap_min": {"type": "number", "description": "eV; records without a GW gap are excluded"},
            "gw_gap_max": {"type": "number", "description": "eV; records without a GW gap are excluded"},
            "has_inputs": {"type": "boolean"},
            "sort": {"type": "string", "enum": ["material", "-material", "gw_gap", "-gw_gap", "ks_gap", "-ks_gap", "atoms", "-atoms"],
                     "default": "material"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        }},
    },
    {
        "name": "get_material",
        "title": "Get one calculation record",
        "description": "Return one full calculation record by id, including properties, software identity, "
                       "species bindings, every declared file with its download URL, and derived values "
                       "(methods, elements, gaps, headline result) as the website shows them.",
        "inputSchema": {"type": "object", "properties": {
            "record_id": {"type": "string", "description": "e.g. 'si-paper-all_kpath'"},
        }, "required": ["record_id"]},
    },
    {
        "name": "list_files",
        "title": "List a record's files",
        "description": "List the declared files of one record, optionally filtered by group (inputs, results, "
                       "logs, figures). Every entry carries its tier, size, and primary/mirror download URL.",
        "inputSchema": {"type": "object", "properties": {
            "record_id": {"type": "string"},
            "group": {"type": "string", "enum": ["inputs", "results", "logs", "figures"]},
        }, "required": ["record_id"]},
    },
    {
        "name": "read_file",
        "title": "Read one archived file",
        "description": "Fetch one archived payload by its declared path and return the text content (SHA-256 "
                       "verified against the catalog before returning; truncated to max_bytes). Binary "
                       "payloads report the local cache path of the verified bytes instead.",
        "inputSchema": {"type": "object", "properties": {
            "record_id": {"type": "string"},
            "path": {"type": "string", "description": "declared path from list_files"},
            "max_bytes": {"type": "integer", "minimum": 1, "maximum": 4194304, "default": 65536},
        }, "required": ["record_id", "path"]},
    },
    {
        "name": "get_band_table",
        "title": "Parse a band table",
        "description": "Parse one record's archived ABACUS band table (KS/EXX/GW) into k-point indices, "
                       "fractional coordinates, energies (eV), and occupations. Optionally slice a band "
                       "window with band_start/band_count; by default every exported band is returned.",
        "inputSchema": {"type": "object", "properties": {
            "record_id": {"type": "string"},
            "method": {"type": "string", "enum": ["KS", "EXX", "GW"], "default": "GW"},
            "band_start": {"type": "integer", "minimum": 1},
            "band_count": {"type": "integer", "minimum": 1},
        }, "required": ["record_id"]},
    },
    {
        "name": "compare_gaps",
        "title": "Compare band gaps",
        "description": "KS, EXX, and GW gaps side by side for every record that lists one, as on the "
                       "website's Gap overview, each with its scope (band, path, or sampled Gamma), "
                       "observable, and gap definition. Filter by material or formula, record ids, "
                       "elements, or front end.",
        "inputSchema": {"type": "object", "properties": {
            "material": {"type": "string", "description": "exact material or formula, e.g. 'GaAs'"},
            "record_ids": {"type": "array", "items": {"type": "string"}},
            "elements": {"type": "array", "items": {"type": "string"}},
            "frontend": {"type": "string", "enum": ["abacus", "fhi_aims"]},
            "sort": {"type": "string", "enum": ["gw", "material"], "default": "gw"},
        }},
    },
    {
        "name": "list_basis_sets",
        "title": "List basis sets",
        "description": "List basis sets (pseudopotentials, physical NAOs, auxiliary bases), optionally "
                       "filtered by element, with size labels (valence electrons, orbital and auxiliary "
                       "shells per atom) and payload URLs.",
        "inputSchema": {"type": "object", "properties": {
            "element": {"type": "string", "description": "e.g. 'Si'"},
        }},
    },
    {
        "name": "get_basis_set",
        "title": "Get one basis set",
        "description": "One basis set by id: size label, validation scope, source, generation provenance, "
                       "every payload with its SHA-256 and URL, and the calculations that used it.",
        "inputSchema": {"type": "object", "properties": {
            "set_id": {"type": "string", "description": "id from list_basis_sets"},
        }, "required": ["set_id"]},
    },
    {
        "name": "contribution_guide",
        "title": "How to contribute data",
        "description": "The pull-request workflow for adding a calculation: steps, gates to run locally, "
                       "prohibitions, and links to the contribution rules and the intake skill. This server "
                       "never writes; contributions are reviewed pull requests.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]
for _tool in TOOLS:
    _tool["annotations"] = {"title": _tool["title"], **READ_ONLY}

TOOL_FUNCTIONS = {
    "database_overview": tool_database_overview,
    "search_materials": tool_search_materials,
    "get_material": tool_get_material,
    "list_files": tool_list_files,
    "read_file": tool_read_file,
    "get_band_table": tool_get_band_table,
    "compare_gaps": tool_compare_gaps,
    "list_basis_sets": tool_list_basis_sets,
    "get_basis_set": tool_get_basis_set,
    "contribution_guide": tool_contribution_guide,
}

RESOURCES = [
    {"uri": "librpa://overview", "name": "Database overview", "mimeType": "application/json",
     "description": "Counts per element, record type, front end, and method."},
    {"uri": "librpa://contributing", "name": "Contribution guide", "mimeType": "application/json",
     "description": "The pull-request workflow for adding a calculation."},
]
RESOURCE_TEMPLATES = [
    {"uriTemplate": "librpa://record/{record_id}", "name": "Calculation record", "mimeType": "application/json",
     "description": "One complete calculation record with derived values and file URLs."},
    {"uriTemplate": "librpa://basis/{set_id}", "name": "Basis set", "mimeType": "application/json",
     "description": "One basis set with payloads and linked calculations."},
]

PROMPTS = [
    {"name": "investigate-material", "title": "Investigate a material",
     "description": "Survey what the database holds for one material, with each value's scope.",
     "arguments": [{"name": "material", "description": "Material name or formula, e.g. GaAs", "required": True}]},
    {"name": "contribute-calculation", "title": "Contribute a calculation",
     "description": "Prepare a finished GW/RPA run as a pull request to the database.",
     "arguments": [{"name": "run", "description": "Where the finished run lives and what it computed", "required": False}]},
]


def _read_resource(uri: str) -> dict:
    if uri == "librpa://overview":
        value = tool_database_overview({})
    elif uri == "librpa://contributing":
        value = CONTRIBUTION_GUIDE
    elif uri.startswith("librpa://record/"):
        value = tool_get_material({"record_id": uri[len("librpa://record/"):]})
    elif uri.startswith("librpa://basis/"):
        value = tool_get_basis_set({"set_id": uri[len("librpa://basis/"):]})
    else:
        raise KeyError(f"unknown resource {uri!r}")
    return {"contents": [{"uri": uri, "mimeType": "application/json",
                          "text": json.dumps(value, ensure_ascii=False)}]}


def _prompt(name: str, arguments: dict) -> dict:
    if name == "investigate-material":
        material = str(arguments.get("material") or "").strip()
        if not material:
            raise ValueError("argument 'material' is required")
        text = (f"Report what the LibRPA materials database holds for {material}.\n"
                f"1. Call search_materials with query '{material}' (or with elements and element_mode 'only' "
                "for a chemical system) and list the records by front end and record type.\n"
                f"2. Call compare_gaps with material '{material}' and present KS, EXX, and GW side by side.\n"
                "3. For the record you rely on, call get_material and quote summary.observable and "
                "summary.gap_definition next to every number. Never call a sampled path or sampled Gamma gap a "
                "fundamental gap, and compare across codes only when the definitions agree.\n"
                "4. Give each record's page_url so a reader can check the evidence.")
        return {"description": f"Investigate {material}",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}
    if name == "contribute-calculation":
        run = str(arguments.get("run") or "the finished run").strip()
        steps = "\n".join(f"{index}. {step}" for index, step in enumerate(CONTRIBUTION_GUIDE["steps"], 1))
        text = (f"Prepare {run} as a contribution to the LibRPA materials database.\n"
                f"{CONTRIBUTION_GUIDE['principle']}\n\n{steps}\n\n"
                "Before writing any file, present a read-only candidate summary (source run, observable and "
                "scope, finite-result checks, input/basis/software identity, missing evidence, file hashes) and "
                "wait for the user's approval. Follow the librpa-database-intake skill if it is installed: "
                f"{CONTRIBUTION_GUIDE['links']['intake_skill']}")
        return {"description": "Contribute a calculation as a pull request",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}
    raise KeyError(f"unknown prompt {name!r}")


def _result(message_id, result) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}) + "\n")
    sys.stdout.flush()


def _error(message_id, code: int, message: str) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message_id,
                                 "error": {"code": code, "message": message}}) + "\n")
    sys.stdout.flush()


def _handle(message: dict) -> None:
    method = message.get("method", "")
    message_id = message.get("id")
    params = message.get("params") or {}
    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if isinstance(requested, str) else "2024-11-05"
        _result(message_id, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False},
                             "resources": {"listChanged": False, "subscribe": False},
                             "prompts": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "LibRPA materials database", "version": SERVER_VERSION},
            "instructions": "Read-only access to the LibRPA materials database (GW and RPA results from "
                            "ABACUS and FHI-aims with LibRPA). Start with database_overview or "
                            "search_materials, then compare_gaps, get_material, list_files, read_file, or "
                            "get_band_table. Quote each record's observable and gap definition with its "
                            "numbers. The server never writes: new data arrives as a GitHub pull request "
                            "(see contribution_guide).",
        })
    elif method.startswith("notifications/"):
        return
    elif method == "ping":
        _result(message_id, {})
    elif method == "tools/list":
        _result(message_id, {"tools": TOOLS})
    elif method == "tools/call":
        name = params.get("name", "")
        function = TOOL_FUNCTIONS.get(name)
        if function is None:
            _error(message_id, -32602, f"unknown tool {name!r}")
            return
        try:
            value = function(params.get("arguments") or {})
            _result(message_id, {"content": [{"type": "text",
                                              "text": json.dumps(value, ensure_ascii=False)}],
                                 "isError": False})
        except Exception as error:  # noqa: BLE001 - reported to the client as tool error
            _result(message_id, {"content": [{"type": "text",
                                              "text": f"Error: {error}"}],
                                 "isError": True})
    elif method == "resources/list":
        _result(message_id, {"resources": RESOURCES})
    elif method == "resources/templates/list":
        _result(message_id, {"resourceTemplates": RESOURCE_TEMPLATES})
    elif method == "resources/read":
        try:
            _result(message_id, _read_resource(str(params.get("uri", ""))))
        except Exception as error:  # noqa: BLE001 - reported as an invalid request
            _error(message_id, -32002, f"resource unavailable: {error}")
    elif method == "prompts/list":
        _result(message_id, {"prompts": PROMPTS})
    elif method == "prompts/get":
        try:
            _result(message_id, _prompt(str(params.get("name", "")), params.get("arguments") or {}))
        except Exception as error:  # noqa: BLE001 - reported as invalid params
            _error(message_id, -32602, str(error))
    elif message_id is None:
        return
    else:
        _error(message_id, -32601, f"method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            _handle(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
