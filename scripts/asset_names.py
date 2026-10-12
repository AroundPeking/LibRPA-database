"""为目录中的资产添加有证据的名称，不改写归档身份或源记录。"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import PurePosixPath
import re
import unicodedata

BASIS_ROLES = {"pp", "nao", "for_aux", "abf"}
HASH_NAME = re.compile(r"[0-9a-f]{7,64}", re.IGNORECASE)


def _safe_basename(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value != "."
        and value == value.strip()
        and ".." not in value
        and not any(char in value for char in '/\\<>:"|?*')
        and not any(unicodedata.category(char).startswith("C") for char in value)
    )


def _recorded_name(value: object, suffix: str) -> bool:
    if not _safe_basename(value):
        return False
    path = PurePosixPath(value)
    return (
        path.suffix.lower() == suffix.lower()
        and path.stem.lower() not in {"payload", "hash"}
        and not HASH_NAME.fullmatch(path.stem)
    )


def _descriptive_name(basis: dict, item: dict) -> str:
    def slug(value: object, fallback: str) -> str:
        return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-_") or fallback

    parts = (
        slug(basis.get("element"), "element"),
        slug(basis.get("family"), "unknown-family"),
        slug(item.get("role"), "asset"),
        item["sha256"][:12],
    )
    return "_".join(parts) + PurePosixPath(item["path"]).suffix


def enrich_catalog(catalog: dict) -> dict:
    """返回独立目录副本；同 SHA 和角色可共享名称证据，但不共享使用关系。"""
    result = deepcopy(catalog)
    sets = result["basis_sets"]
    by_id = {basis["id"]: basis for basis in sets}
    names = defaultdict(set)
    for basis in sets:
        for item in basis["files"]:
            if item.get("role") not in BASIS_ROLES:
                continue
            suffix = PurePosixPath(item["path"]).suffix
            if _recorded_name(item.get("label"), suffix):
                names[(item["sha256"], item["role"])].add(item["label"])

    for case in result["calculations"]:
        # 只读取 exact species；候选集不能证明本次计算使用了某个文件。
        for species in case.get("species", []):
            basis = by_id.get(species.get("set_id"))
            aliases = species.get("asset_aliases", {})
            if (basis is None or basis["element"] != species.get("element")
                    or not isinstance(aliases, dict)):
                continue
            files_by_role = defaultdict(list)
            for item in basis["files"]:
                files_by_role[item.get("role")].append(item)
            for role, files in files_by_role.items():
                if role not in BASIS_ROLES or len(files) != 1:
                    continue
                item = files[0]
                calculation_alias = aliases.get(role)
                if _recorded_name(calculation_alias, PurePosixPath(item["path"]).suffix):
                    names[(item["sha256"], role)].add(calculation_alias)

    for basis in sets:
        for item in basis["files"]:
            path = PurePosixPath(item["path"])
            original_names = sorted(
                name for name in names[(item["sha256"], item.get("role"))]
                if _recorded_name(name, path.suffix)
            )
            if original_names:
                label = item.get("label")
                name = label if label in original_names else original_names[0]
                source = "recorded"
            elif item.get("role") not in BASIS_ROLES and _recorded_name(path.name, path.suffix):
                name = path.name
                source = "archive_name"
            else:
                name = _descriptive_name(basis, item)
                source = "descriptive_alias"
            item.update({
                "display_name": name,
                "download_name": name,
                "name_source": source,
                "original_names": original_names,
            })
    return result
