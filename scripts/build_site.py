#!/usr/bin/env python3
"""按白名单构建静态站点；不修改源数据，不覆盖已有输出。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT_FILES = {"index.html", ".nojekyll", "robots.txt", "sitemap.xml", "README.md", "CONTRIBUTING.md", "LICENSE"}
REFERENCE_FILES = {"references/database.md", "references/plotting.md"}
INDEX_FILES = {"data/log-index.json"}
INTERNAL_WEB_FILES = {"database/archive-completeness.json", "database/missing-evidence.html"}
WEB_SUFFIXES = {".html", ".css", ".js", ".mjs", ".json"}
STATIC_DIRS = {"database", "references", "assets", "images", "fonts"}
ASSET_SUFFIXES = WEB_SUFFIXES | {
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".webm", ".pdf", ".txt", ".md",
}
EXCLUDED_DIRS = {"docs", "superpowers", "scripts", "tests", "cache", "__pycache__", "node_modules", "tmp", "temp"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".bak", ".part", ".swp", ".swo", ".orig"}
COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
CHUNK_SIZE = 1024 * 1024


def excluded(path: PurePosixPath) -> bool:
    return (any(part.lower() in EXCLUDED_DIRS or (part.startswith(".") and part != ".nojekyll")
                for part in path.parts)
            or path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.endswith("~"))


def repository_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or any(c in value for c in "\\\x00:?#"):
        raise ValueError(f"无效仓库路径: {value!r}")
    path = PurePosixPath(value)
    decoded = PurePosixPath(unquote(value))
    if (path.is_absolute() or decoded.is_absolute() or ".." in path.parts
            or ".." in decoded.parts or "\\" in unquote(value) or "\x00" in unquote(value)
            or not path.parts or excluded(path)):
        raise ValueError(f"路径逃逸或引用禁止发布的文件: {value!r}")
    return path


def source_file(root: Path, relative: str) -> Path:
    path = repository_path(relative)
    full = root
    for part in path.parts:
        full = full / part
        if full.is_symlink():
            raise ValueError(f"不允许符号链接: {relative}")
    if not full.is_file():
        raise ValueError(f"引用文件缺失: {relative}")
    return full


def load_json(root: Path, relative: str):
    with source_file(root, relative).open(encoding="utf-8") as stream:
        return json.load(stream)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("href", "xlink:href", "src", "poster", "data"):
            if attrs.get(key):
                self.urls.append(attrs[key])
        if attrs.get("srcset") and not attrs["srcset"].startswith("data:"):
            self.urls.extend(part.strip().split()[0] for part in attrs["srcset"].split(",") if part.strip())
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh":
            match = re.search(r"url\s*=\s*['\"]?([^'\"]+)", attrs.get("content", ""), re.I)
            if match:
                self.urls.append(match.group(1).strip())


def document_links(path: Path):
    with path.open(encoding="utf-8") as stream:
        text = stream.read()
    parser = Links()
    parser.feed(text)
    yield from parser.urls
    if path.suffix.lower() in {".css", ".html", ".svg"}:
        yield from re.findall(r"url\(\s*['\"]?([^'\"\s)]+)", text)
        yield from re.findall(r"@import\s+['\"]([^'\"]+)['\"]", text)
    if path.suffix.lower() in {".js", ".mjs", ".html"}:
        yield from re.findall(r"(?:\bfrom\s*|\bimport\s*(?:\(\s*)?|\bfetch\s*\(\s*|\bnew\s+URL\s*\(\s*)['\"]([^'\"]+)['\"]", text)
    if path.suffix.lower() == ".md":
        # 代码块是示例而非站点导航，不将其中的样例路径解释为依赖。
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        yield from re.findall(r"\]\(\s*<?([^\s)>]+)", text)
        yield from re.findall(r"^\s*\[[^\]]+\]:\s*<?([^\s>]+)", text, re.M)


def local_link(document: str, url: str) -> str | None:
    if "${" in url:
        return None  # 动态数据链接由 catalog 的文件清单单独验证。
    parsed = urlsplit(url.strip())
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    value = unquote(parsed.path)
    if "\\" in value or "\x00" in value:
        raise ValueError(f"无效本地链接: {document}: {url}")
    parts = [] if value.startswith("/") else list(PurePosixPath(document).parent.parts)
    for part in value.split("/"):
        if part == "..":
            if not parts:
                raise ValueError(f"本地链接逃逸: {document}: {url}")
            parts.pop()
        elif part not in {"", "."}:
            parts.append(part)
    result = "/".join(parts)
    if not result or value.endswith("/"):
        result = f"{result}/index.html".lstrip("/")
    return repository_path(result).as_posix()


def json_references(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "path":
                # referenced 档：path 仅为身份标识，字节在外部对象存储。
                yield nested, value.get("sha256"), value.get("tier") == "referenced"
            elif key == "evidence" and isinstance(nested, list):
                for entry in nested:
                    if isinstance(entry, str):
                        yield entry, None, False
            yield from json_references(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from json_references(nested)


def collect_files(root: Path) -> dict[str, str | None]:
    """先完整验证发布依赖，返回相对路径及可用的原始SHA-256。"""
    files = {}
    metadata = []
    # referenced 档字节在外部对象存储；这些路径不进入发布树，
    # 元数据引用（含纯路径形式的 evidence 清单）一律放行。
    referenced_paths = set()

    def add(relative, digest=None):
        relative = repository_path(relative).as_posix()
        if digest is not None and (not isinstance(digest, str) or not SHA256.fullmatch(digest)):
            raise ValueError(f"无效SHA-256: {relative}")
        if files.get(relative) is not None and digest is not None and files[relative] != digest:
            raise ValueError(f"同一路径存在冲突SHA-256: {relative}")
        # Shared assets occur in many sets and again in the catalog and records.
        # Check each unique source once during collection, then again when copied.
        if relative not in files:
            source_file(root, relative)
        files[relative] = digest or files.get(relative)

    add("index.html")
    add("database/index.html")
    add("database/data.json")
    for relative in sorted(ROOT_FILES | REFERENCE_FILES | INDEX_FILES):
        path = root / relative
        if path.exists() or path.is_symlink():
            add(relative)
            if relative in INDEX_FILES:
                metadata.append(load_json(root, relative))

    for directory, dirs, names in os.walk(root / "database", followlinks=False):
        relative_dir = Path(directory).relative_to(root)
        dirs[:] = sorted(name for name in dirs if not excluded(PurePosixPath(relative_dir, name)))
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise ValueError(f"不允许符号链接: {relative_dir / name}")
        for name in sorted(names):
            relative = PurePosixPath(relative_dir, name)
            if (not excluded(relative) and relative.as_posix() not in INTERNAL_WEB_FILES
                    and relative.suffix.lower() in WEB_SUFFIXES):
                add(relative.as_posix())

    catalog = load_json(root, "database/data.json")
    for key in ("basis_sets", "calculations"):
        if not isinstance(catalog.get(key), list):
            raise ValueError(f"catalog 缺少列表: {key}")
        for item in catalog[key]:
            payloads = item.get("files", [] if key == "basis_sets" else {})
            if key == "calculations":
                payloads = [entry for group in payloads.values() for entry in group]
            for entry in payloads:
                relative = repository_path(entry["path"])
                if relative.parts[:2] not in {("data", "elements"), ("data", "calculations")}:
                    raise ValueError(f"catalog 文件必须位于 data/elements 或 data/calculations: {relative}")
                if entry.get("tier") == "referenced":
                    # referenced 档字节存放在外部对象存储，不进入 Pages 发布树；
                    # 发布门禁只允许 https 直链离开仓库。
                    url = entry.get("external_url")
                    if not isinstance(url, str) or not url.startswith("https://") or any(ch.isspace() for ch in url):
                        raise ValueError(f"referenced 档必须是 https 直链: {relative}")
                    backup = entry.get("external_url_backup")
                    if backup is not None and (not isinstance(backup, str) or not backup.startswith("https://") or any(ch.isspace() for ch in backup)):
                        raise ValueError(f"referenced 档备用直链必须是 https: {relative}")
                    referenced_paths.add(relative.as_posix())
                    continue
                if entry.get("tier") is not None:
                    raise ValueError(f"不支持的存储档: {relative}")
                add(relative.as_posix(), entry.get("sha256"))
            if key == "basis_sets":
                parts = ("data", "elements", item["element"], "sets", item["id"], "set.json")
            else:
                parts = ("data", "calculations", item["dimension"], item["material"], item["id"], "record.json")
            if any(not isinstance(part, str) or "/" in part or "\\" in part or part in {"", ".", ".."} for part in parts):
                raise ValueError("record/set 路径字段必须是单个目录名")
            record = "/".join(parts)
            repository_path(record)
            if (root / record).exists() or (root / record).is_symlink():
                add(record)
                metadata.append(load_json(root, record))

    visited = set()
    while pending := sorted(set(files) - visited):
        for relative in pending:
            visited.add(relative)
            path = PurePosixPath(relative)
            # 科研证据是原样保留的历史文件，不递归解释其中的历史路径。
            if path.parts[0] == "data":
                continue
            if path.suffix.lower() == ".json":
                value = load_json(root, relative)
                metadata.append(value)
                for target, digest, referenced in json_references(value):
                    if referenced:
                        continue
                    target_path = repository_path(target)
                    if (target_path.parts[0] in STATIC_DIRS
                            and target_path.suffix.lower() in ASSET_SUFFIXES):
                        add(target_path.as_posix(), digest)
                continue
            if path.suffix.lower() not in {".html", ".css", ".js", ".mjs", ".md", ".svg"}:
                continue
            for url in document_links(source_file(root, relative)):
                target = local_link(relative, url)
                if target is None or target in {"build-info.json", ".nojekyll"}:
                    continue
                if target in files:
                    continue
                target_path = PurePosixPath(target)
                if (target in ROOT_FILES or
                        (target_path.parts[0] in STATIC_DIRS
                         and target_path.suffix.lower() in ASSET_SUFFIXES)):
                    add(target)
                else:
                    raise ValueError(f"引用未发布的文件: {relative}: {target}")

    for value in metadata:
        for relative, digest, referenced in json_references(value):
            if referenced:
                # 外部存储直链字节不进入发布树，路径只作为身份登记。
                continue
            relative = repository_path(relative).as_posix()
            if relative in referenced_paths:
                # 属性/性能 evidence 以纯路径引用 referenced 档时同样放行；
                # 前端经 files 索引解析为外部直链。
                continue
            if relative not in files:
                raise ValueError(f"JSON 引用未发布的文件: {relative}")
            add(relative, digest)
    return files


def source_commit(root: Path, commit: str | None) -> str | None:
    if commit is not None:
        if not COMMIT.fullmatch(commit):
            raise ValueError("--commit 必须是完整的40或64位小写十六进制SHA")
        return commit
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
                                check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    if not COMMIT.fullmatch(commit):
        raise ValueError("git 返回了非完整的提交SHA")
    return commit


def output_directory(root: Path, output: Path) -> Path:
    output = output if output.is_absolute() else root / output
    if output.is_symlink():
        raise ValueError("输出目录不能是符号链接")
    if output.is_relative_to(root):
        parent = root
        for part in output.relative_to(root).parts:
            parent = parent / part
            if parent.is_symlink():
                raise ValueError("输出路径不能经过仓库中的符号链接")
    output = output.resolve()
    if root.is_relative_to(output):
        raise ValueError("输出目录不能包含源仓库")
    if output.is_relative_to(root):
        relative = output.relative_to(root)
        if relative.parts[0] in STATIC_DIRS | {"data", "scripts", "tests", "docs", ".git", ".github"}:
            raise ValueError("输出目录不能位于源目录内")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("输出目录必须为新目录或空目录；拒绝覆盖")
    return output


def build_site(root: Path, output: Path, commit: str | None = None) -> dict:
    root = root.resolve(strict=True)
    output = output_directory(root, output)
    revision = source_commit(root, commit)
    files = collect_files(root)
    # 全部依赖检查通过后才开始写出。科学文件始终按固定大小分块复制和校验。
    output.mkdir(parents=True, exist_ok=True)
    for relative, expected in sorted(files.items()):
        source = source_file(root, relative)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            while chunk := incoming.read(CHUNK_SIZE):
                outgoing.write(chunk)
                digest.update(chunk)
        if expected is not None and digest.hexdigest() != expected:
            raise ValueError(f"SHA-256不一致: {relative}")
    if ".nojekyll" not in files:
        (output / ".nojekyll").touch(exist_ok=False)
    dirty = None
    if (root / ".git").exists():
        try:
            status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
                                    check=True, capture_output=True, text=True)
            dirty = bool(status.stdout.strip())
        except (OSError, subprocess.CalledProcessError):
            pass
    info = {"schema_version": 1, "source_commit": revision, "source_dirty": dirty}
    with (output / "build-info.json").open("x", encoding="utf-8") as stream:
        json.dump(info, stream, indent=2)
        stream.write("\n")
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("_site"))
    parser.add_argument("--commit", help="可选的完整来源提交SHA；默认从git读取，无git时为null")
    args = parser.parse_args()
    try:
        info = build_site(args.root, args.output, args.commit)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"静态站点构建失败: {exc}\n")
    print(f"静态站点构建完成: {args.output} (source_commit={info['source_commit']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
