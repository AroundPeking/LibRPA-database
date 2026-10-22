#!/usr/bin/env python3
"""Read-only MCP server for the LibRPA materials database.

Serves the public catalog and every archived payload byte over plain HTTPS,
so it needs no credentials, no clone of the repository, and no third-party
Python packages -- only the standard library.

Endpoints (all overridable through environment variables):
  LIBRPA_DB_CATALOG_URL  catalog JSON   (default: the published data.json)
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

SERVER_NAME = "librpa-database"
SERVER_VERSION = "1.0.0"
DEFAULT_CATALOG_URL = "https://aroundpeking.github.io/LibRPA-database/database/data.json"
DEFAULT_SITE_ROOT = "https://aroundpeking.github.io/LibRPA-database"
USER_AGENT = "librpa-database-mcp/1.0"
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
    if location.startswith("file://"):
        data = json.loads(Path(location[7:]).read_text(encoding="utf-8"))
    elif location.startswith("/"):
        data = json.loads(Path(location).read_text(encoding="utf-8"))
    else:
        data = json.loads(_fetch(location).decode("utf-8"))
    _catalog_cache["data"] = data
    _catalog_cache["fetched"] = now
    return data


def _records() -> list:
    return _load_catalog().get("calculations", [])


def _find_record(record_id: str) -> dict:
    for record in _records():
        if record.get("id") == record_id:
            return record
    known = ", ".join(record.get("id", "?") for record in _records()[:8])
    raise KeyError(f"unknown record id {record_id!r} (catalog starts with: {known} ...)")


def _file_url(file: dict) -> str:
    url = file.get("external_url")
    if isinstance(url, str) and url.startswith("https://"):
        return url
    return f"{_site_root()}/{file.get('path', '')}"


def _file_urls(file: dict) -> list:
    urls = [_file_url(file)]
    backup = file.get("external_url_backup")
    if isinstance(backup, str) and backup.startswith("https://"):
        urls.append(backup)
    return urls


def _payload_bytes(file: dict) -> bytes:
    digest = file.get("sha256")
    cache = _cache_dir() / str(digest)[:2] / str(digest)
    if cache.is_file():
        data = cache.read_bytes()
        if hashlib.sha256(data).hexdigest() == digest:
            return data
    last_error = None
    for url in _file_urls(file):
        try:
            data = _fetch(url)
        except RuntimeError as error:
            last_error = error
            continue
        if hashlib.sha256(data).hexdigest() != digest:
            last_error = f"SHA-256 mismatch at {url}"
            continue
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        return data
    raise RuntimeError(f"could not fetch {file.get('path', '?')} with a matching hash "
                       f"({last_error})")


def _methods_of(record: dict) -> list:
    names = []
    if record.get("functional"):
        names.append(record["functional"])
    for property_ in record.get("properties", []):
        method = property_.get("method")
        if method and method not in names:
            names.append(method)
    return names


def _record_summary(record: dict) -> dict:
    files = record.get("files", {})
    return {
        "id": record.get("id"),
        "material": record.get("material"),
        "formula": record.get("formula"),
        "dimension": record.get("dimension"),
        "record_type": record.get("record_type"),
        "methods": _methods_of(record),
        "spin_orbit": record.get("spin_orbit"),
        "spin_polarized": record.get("spin_polarized"),
        "summary": record.get("summary"),
        "atom_count": (record.get("computational_scale") or {}).get("atom_count"),
        "file_counts": {group: len(entries) for group, entries in files.items()},
    }


def _searchable_text(record: dict) -> str:
    parts = [str(record.get(key, "")) for key in
             ("id", "material", "formula", "dimension", "record_type", "workflow")]
    parts.append(" ".join(_methods_of(record)))
    parts.append(record.get("functional") or "")
    if record.get("spin_orbit"):
        parts.append("soc spin_orbit")
    if record.get("spin_polarized"):
        parts.append("spin spin_polarized")
    for property_ in record.get("properties", []):
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


# ---------------------------------------------------------------------------
# Tool implementations. Each returns a plain value that is rendered as JSON.
# ---------------------------------------------------------------------------


def tool_search_materials(arguments: dict) -> dict:
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    dimension = arguments.get("dimension")
    record_type = arguments.get("record_type")
    limit = min(int(arguments.get("limit", 20)), 100)
    tokens = [token for token in re.split(r"\s+", query.lower()) if token]
    matches = []
    for record in _records():
        if dimension and record.get("dimension") != dimension:
            continue
        if record_type and record.get("record_type") != record_type:
            continue
        haystack = _searchable_text(record)
        if all(re.search(rf"\b{re.escape(token)}", haystack) for token in tokens):
            matches.append(_record_summary(record))
        if len(matches) >= limit:
            break
    return {"query": query, "count": len(matches), "records": matches}


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
    max_bytes = min(int(arguments.get("max_bytes", TEXT_LIMIT_DEFAULT)), TEXT_LIMIT_MAX)
    data = _payload_bytes(file)
    if b"\x00" in data[:4096]:
        cached = _cache_dir() / str(file["sha256"])[:2] / str(file["sha256"])
        return {"path": wanted, "binary": True, "size_bytes": len(data),
                "sha256_verified": True, "cached_at": str(cached),
                "note": "binary payload; the cached file holds the exact verified bytes"}
    text = data.decode("utf-8", errors="replace")
    truncated = len(text) > max_bytes
    return {"path": wanted, "size_bytes": len(data), "sha256_verified": True,
            "truncated": truncated, "content": text[:max_bytes]}


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


def tool_list_basis_sets(arguments: dict) -> dict:
    element = arguments.get("element")
    sets = []
    for entry in _load_catalog().get("basis_sets", []):
        if element and entry.get("element") != element:
            continue
        sets.append({
            "id": entry.get("id"), "element": entry.get("element"),
            "origin": (entry.get("publication") or {}).get("status"),
            "files": [{"role": file.get("role"), "name": file.get("name"),
                       "tier": file.get("tier", "local"),
                       "size_bytes": file.get("size_bytes"), "url": _file_url(file)}
                      for file in entry.get("files", [])],
        })
    return {"count": len(sets), "basis_sets": sets}


# ---------------------------------------------------------------------------
# Minimal MCP stdio transport: newline-delimited JSON-RPC 2.0.
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "search_materials",
        "description": "Search the LibRPA materials database catalog. All whitespace-"
                       "separated tokens must match (AND) against material, formula, id, "
                       "dimension, record_type, method chips (e.g. GW, EXX, PBE, RPA, SOC, "
                       "SPIN), and property keys. Returns record summaries.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "e.g. 'Si GW', 'MoS2 2d', 'soc'"},
            "dimension": {"type": "string", "enum": ["2d", "3d"]},
            "record_type": {"type": "string",
                            "enum": ["band", "large_system_gw", "rpa_energy", "reader_conversion"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        }, "required": ["query"]},
    },
    {
        "name": "get_material",
        "description": "Return one full calculation record by id, including properties, "
                       "software identity, species bindings, and every declared file with "
                       "its download URL. File lists are compacted to identity + URL.",
        "inputSchema": {"type": "object", "properties": {
            "record_id": {"type": "string", "description": "e.g. 'si-paper-all_kpath'"},
        }, "required": ["record_id"]},
    },
    {
        "name": "list_files",
        "description": "List the declared files of one record, optionally filtered by "
                       "group (inputs, results, logs, figures). Every entry carries its "
                       "tier, size, and primary/mirror download URL.",
        "inputSchema": {"type": "object", "properties": {
            "record_id": {"type": "string"},
            "group": {"type": "string", "enum": ["inputs", "results", "logs", "figures"]},
        }, "required": ["record_id"]},
    },
    {
        "name": "read_file",
        "description": "Fetch one archived payload by its declared path and return the "
                       "text content (SHA-256 verified against the catalog before "
                       "returning; truncated to max_bytes). Binary payloads report the "
                       "local cache path of the verified bytes instead.",
        "inputSchema": {"type": "object", "properties": {
            "record_id": {"type": "string"},
            "path": {"type": "string", "description": "declared path from list_files"},
            "max_bytes": {"type": "integer", "minimum": 1, "maximum": 4194304, "default": 65536},
        }, "required": ["record_id", "path"]},
    },
    {
        "name": "get_band_table",
        "description": "Parse one record's archived ABACUS band table (KS/EXX/GW) into "
                       "k-point indices, fractional coordinates, energies (eV), and "
                       "occupations. Optionally slice a band window with band_start/"
                       "band_count; by default every exported band is returned.",
        "inputSchema": {"type": "object", "properties": {
            "record_id": {"type": "string"},
            "method": {"type": "string", "enum": ["KS", "EXX", "GW"], "default": "GW"},
            "band_start": {"type": "integer", "minimum": 1},
            "band_count": {"type": "integer", "minimum": 1},
        }, "required": ["record_id"]},
    },
    {
        "name": "list_basis_sets",
        "description": "List basis sets (pseudopotentials, physical NAOs, auxiliary "
                       "bases), optionally filtered by element, with payload URLs.",
        "inputSchema": {"type": "object", "properties": {
            "element": {"type": "string", "description": "e.g. 'Si'"},
        }},
    },
]

TOOL_FUNCTIONS = {
    "search_materials": tool_search_materials,
    "get_material": tool_get_material,
    "list_files": tool_list_files,
    "read_file": tool_read_file,
    "get_band_table": tool_get_band_table,
    "list_basis_sets": tool_list_basis_sets,
}


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
    if method == "initialize":
        requested = message.get("params", {}).get("protocolVersion")
        version = requested if isinstance(requested, str) else "2024-11-05"
        _result(message_id, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": "Read-only access to the LibRPA materials database. "
                            "Start with search_materials, then get_material / "
                            "list_files / read_file / get_band_table.",
        })
    elif method in {"notifications/initialized", "notifications/cancelled",
                    "notifications/roots/list_changed"}:
        return
    elif method == "ping":
        _result(message_id, {})
    elif method == "tools/list":
        _result(message_id, {"tools": TOOLS})
    elif method == "tools/call":
        params = message.get("params", {})
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
    elif method in {"resources/list", "resources/templates/list", "prompts/list"}:
        _result(message_id, {})
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
