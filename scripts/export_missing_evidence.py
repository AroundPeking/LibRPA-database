#!/usr/bin/env python3
"""导出不放宽 strict 门槛的逐材料缺证清单；默认只读。"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
from pathlib import Path, PurePosixPath

import library

SOFTWARE_REQUIREMENTS = [
    "对应历史 stage 的完整不可变源码 commit；不是当前 HEAD、分支名或短 token",
    "同 stage 原始运行日志中的版本/commit token、启动时间及实际启动命令",
    "source_commit.txt 或等价源码身份 receipt，记录当时源码树及 clean/dirty 状态",
    "当时 build manifest/CMakeCache/构建 receipt，并绑定实际运行可执行文件 SHA-256",
    "运行启动/作业 receipt 将 executable hash、输入 manifest 和该谱输出 hash 绑定",
]
SCOPE_NOTES = [
    "缺证指公共归档未闭合，不等于私人原目录中的文件一定不存在；已归档文件不要重复寻找。",
    "已在私人原来源定位到七组 ABACUS、五组 LibRPA 潜在身份入口，尚未全部审完；这些入口不自动关闭任何 fullcommit issue。",
    "先检查已有 stage controls、日志和 receipt，再补同一次历史运行证据；禁止用当前 HEAD 或其他材料/新算例替代。",
    "strict 上传完整性、完整 runtime seal、数值/科学接受是不同层次；本清单不改变科学状态。",
]
PATH_KEYS = {"path", "paths", "record_path", "repository_path", "evidence", "source_paths", "metadata_path", "receipt_path", "existing_identity_evidence"}


def assert_public(value: object, key: str = "") -> None:
    """拒绝私有绝对路径，而不是静默删去导致 issue 数量变化。"""
    if isinstance(value, str):
        if library.PRIVATE_PATH.search(value) or re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError("导出包含私有路径，拒绝写入公共交付")
        if re.search(r"(?:^|[\s\"'=])/(?!/)[^\s]", value) or re.search(r"(?:^|\s)(?:file|ssh)://", value):
            raise ValueError("导出包含绝对路径或私有来源，拒绝写入公共交付")
        if key in PATH_KEYS or key.endswith("_path") or key.endswith("_paths"):
            path = PurePosixPath(value)
            if not value or path.is_absolute() or ".." in path.parts or "\\" in value or "://" in value:
                raise ValueError("导出文件引用必须是仓库相对路径")
    elif isinstance(value, dict):
        for name, nested in value.items():
            assert_public(nested, name)
    elif isinstance(value, list):
        for nested in value:
            assert_public(nested, key)


def _file_view(item: dict) -> dict:
    return {key: item[key] for key in ("path", "sha256", "label", "stage_id") if key in item}


def _stages(case: dict) -> list[dict]:
    stages = {}
    for item in case.get("files", {}).get("inputs", []):
        stage_id = item.get("stage_id")
        if not stage_id:
            continue
        stage = stages.setdefault(stage_id, {
            "id": stage_id, "label": item.get("label", "").split(" / ", 1)[0],
            "controls": [], "execution_identity_verified_by_this_export": False,
        })
        stage["controls"].append(_file_view(item))
    return list(stages.values())


def _binding_request(root: Path, case: dict) -> dict:
    required = sorted(library._formula_elements(case.get("formula", case.get("material"))))
    declarations = []
    for item in case.get("files", {}).get("inputs", []):
        if not library._input_name(item, "STRU"):
            continue
        sections = library._stru_sections(library._payload_bytes(root, item).decode("utf-8", errors="replace"))
        rows = [line.split() for line in sections.get("ATOMIC_SPECIES", [])]
        names = {"nao": sections.get("NUMERICAL_ORBITAL", []), "abf": sections.get("ABFS_ORBITAL", [])}
        elements = []
        for index, row in enumerate(rows):
            if not row:
                continue
            roles = {"pp": row[2] if len(row) > 2 else None}
            roles.update({role: values[index].split()[0] if index < len(values) else None
                          for role, values in names.items()})
            elements.append({"element": row[0], "original_names": roles})
        declarations.append({"path": item["path"], "elements": elements,
                             "has_abfs_orbital": bool(sections.get("ABFS_ORBITAL"))})
    return {
        "elements": [{"element": element, "required_roles": ["pp", "nao", "abf"]} for element in required],
        "production_stru_declarations": declarations,
        "requirements": [
            "每个元素找回同一次生产实际使用的 PP(.upf)、physical NAO(.orb)、ABF(.abfs) 原始文件和 SHA-256。",
            "原 STRU 的 ATOMIC_SPECIES/NUMERICAL_ORBITAL/ABFS_ORBITAL 顺序与名称必须绑定到这些精确 payload hash。",
            "候选集、相同文件名、for_aux orbital、其他材料或新算例资产都不能替代 exact role 绑定。",
        ],
        "note": ("已有 partial STRU 能证明下列 PP/NAO 原名，但没有 ABFS_ORBITAL；找原 DF/EXX/GW stage 的 ABF 声明、payload 与运行证据，不得猜 ABF。"
                 if declarations and not any(item["has_abfs_orbital"] for item in declarations)
                 else "没有已审定的生产 STRU 绑定；先找原结构与原角色文件，不能凭候选基组填入。"),
    }


def _case_collection(root: Path, case: dict, issues: list[str]) -> dict:
    files = case.get("files", {})
    result = {
        "record_path": f"data/calculations/{case['dimension']}/{case['material']}/{case['id']}/record.json",
        "missing_inputs": [name for name in ("INPUT", "KPT", "STRU", "librpa.in")
                           if any(issue.startswith(f"input {name}:") for issue in issues)],
        "software_requests": [],
        "existing_stage_controls": _stages(case),
        "existing_logs": [_file_view(item) for item in files.get("logs", [])],
        "existing_receipts": [_file_view(item) for item in files.get("results", [])
                              if re.search(r"receipt|manifest|identity|source_commit", PurePosixPath(item["path"]).name, re.I)],
        "notes": [],
    }
    for name in ("abacus", "librpa"):
        if not any(issue.startswith(f"software.{name}.commit:") for issue in issues):
            continue
        app = case.get("software", {}).get(name, {})
        result["software_requests"].append({
            "software": "ABACUS" if name == "abacus" else "LibRPA",
            "field": f"software.{name}.commit",
            "known_full_commit": app.get("commit"),
            "known_abbreviated_commit": app.get("abbreviated_commit"),
            "existing_identity_evidence": app.get("evidence", []),
            "stages_to_bind": ([f"{stage['label']} [{stage['id']}]" for stage in result["existing_stage_controls"]
                                if (stage["label"] in {"EXX", "GW", "LibRPA"}) == (name == "librpa")]
                               or (["SCF/DF/NSCF (ABACUS)"] if name == "abacus" else ["EXX/GW (LibRPA)"])),
            "requirements": SOFTWARE_REQUIREMENTS,
            "note": "公共历史身份未闭合；先审已有/已定位证据，不代表这些文件必定不存在。",
        })
    if any(issue.startswith(("species", "STRU")) for issue in issues):
        result["basis_binding_request"] = _binding_request(root, case)
    if result["missing_inputs"]:
        result["notes"].append("寻找该 case 原始生产 INPUT、KPT、STRU、librpa.in，按 SCF/DF/NSCF/EXX/GW stage 保留；不要合成替代文件。")
    if case["id"] == "hbn-table-gw":
        result["notes"].append("这是旧 hBN 表格算例；hbn-tzdp10-fgext-20261008 的新输入/基组/软件身份不得挪来关闭旧算例缺口。")
    if any(issue.startswith("properties: EXX") for issue in issues):
        result["notes"].append("现有 EXX 异常不是遗失普通 gap：需要同源正确完整谱和诊断/占据/导出范围证据，或明确记录保留失败诊断的科学决定；不得编造正常 gap 或拿论文值替代。")
    if not issues:
        result["notes"].append("当前 strict 无缺项；这不自动表示完整运行镜像或科学接受。")
    return result


def _supplementary(root: Path, cases: list[dict]) -> list[dict]:
    extras = []
    redraw, rejected = [], []
    for case in cases:
        if case.get("dimension") != "3d":
            continue
        figures = case.get("files", {}).get("figures", [])
        for item in figures:
            if re.fullmatch(r"(?:ks|exx|gw)_frontier\.svg", PurePosixPath(item["path"]).name):
                redraw.append({"case_id": case["id"], "material": case["material"], **_file_view(item),
                               "source_paths": item.get("source_paths", [])})
        if case["material"] in {"GaAs", "GaP"}:
            for item in figures:
                if PurePosixPath(item["path"]).name != "band_frontier_metadata.json":
                    continue
                metadata = json.loads(library._payload_bytes(root, item))
                reasons = metadata.get("methods", {}).get("GW", {}).get("diagnostic_reasons", [])
                rejected.append({"case_id": case["id"], "material": case["material"],
                                 "method": "GW", "metadata_path": item["path"], "reasons": reasons})
    if redraw:
        extras.append({"kind": "reproducible_figures", "counted_in_strict_issues": False,
                       "count": len(redraw), "entries": redraw,
                       "note": "3D 已有 frontier 图及同源绘图数据可重绘，无需寻找遗失普通图片；重绘不提升数值/科学接受。"})
    if rejected:
        extras.append({"kind": "rejected_gw_figures", "counted_in_strict_issues": False,
                       "entries": rejected,
                       "note": "GaAs/GaP 新 GW frontier figure 因近隙窗口科学/数值拒绝，不是遗失普通图；不得为了补图绘制成正常结果。"})
    for case in cases:
        for item in case.get("files", {}).get("results", []):
            if PurePosixPath(item["path"]).name != "stage_input_receipt.json":
                continue
            receipt = json.loads(library._payload_bytes(root, item))
            if receipt.get("full_runtime_handoff_verified") is False or receipt.get("runtime_asset_seal_verified") is False:
                extras.append({"kind": "full_runtime_seal", "case_id": case["id"],
                               "material": case["material"], "counted_in_strict_issues": False,
                               "receipt_path": item["path"],
                               "note": "已恢复 controls/角色绑定不等于完整 runtime seal；需各 stage 输入、reader payload、生存/重hash证据及同一次运行身份链。"})
            text = json.dumps(receipt, ensure_ascii=False)
            if case["id"] == "mos2_ws2-table-gw" and re.search(r"405.*(?:悬空|dangling)|405 dangling", text):
                extras.append({"kind": "dangling_reader_links", "case_id": case["id"],
                               "material": case["material"], "counted_in_strict_issues": False,
                               "reported_link_count": 405, "receipt_path": item["path"],
                               "note": "原恢复审计报告 input_librpa 有405个悬空reader链接；manifest存在不证明payload存活。找原目标payload/完整备份，不把405加进87；本导出未重新扫描私人目录。"})
    return extras


def build_export(root: Path) -> tuple[dict, dict]:
    sets, cases = library.load_records(root)
    library.validate(root, sets, cases)
    report = library.completeness_report(root, sets, cases)
    if report["integrity_issues"]:
        raise ValueError("archive schema/hash integrity failed: " + "; ".join(report["integrity_issues"]))
    export = copy.deepcopy(report)
    export["export_scope"] = {"strict_gate_unchanged": True, "notes": SCOPE_NOTES}
    by_id = {case["id"]: case for case in cases}
    for record in export["cases"]:
        record["collection"] = _case_collection(root, by_id[record["id"]], record["issues"])
    export["supplementary_not_counted_in_strict"] = _supplementary(root, cases)
    assert_public(report)
    assert_public(export)
    return report, export


def render_text(export: dict) -> str:
    assert_public(export)
    stats = export["stats"]
    lines = ["ABACUS + LibRPA 公共归档：完整缺证清单", "",
             f"strict 状态：{export['status']}；{stats['total']}条记录，{stats['incomplete']}条不完整，{stats['complete']}条完整，原始issue总数{stats['issue_count']}。",
             "所有原始issue逐case保留；附加取证说明和runtime缺口不计入该总数。", ""]
    lines += export["export_scope"]["notes"]
    for category, value in stats["missing_categories"].items():
        lines.append(f"分类 {category}：{value['cases']}个case / {value['issues']}条issue")
    number = 0
    for case in export["cases"]:
        collection = case["collection"]
        lines += ["", f"=== {case['material']} | {case['dimension']} | {case['id']} ===",
                  f"科学状态：{case['scientific_status']}；归档：{case['status']}",
                  f"记录：{collection['record_path']}", "原始 strict issues（完整原文）"]
        if not case["issues"]:
            lines.append("  无。")
        for issue in case["issues"]:
            number += 1
            lines.append(f"  [{number:03d}] {issue}")
        if collection["missing_inputs"]:
            lines.append("需找原输入：" + ", ".join(collection["missing_inputs"]))
        binding = collection.get("basis_binding_request")
        if binding:
            lines.append("逐元素 exact role：" + "；".join(f"{item['element']} => PP(.upf) / physical NAO(.orb) / ABF(.abfs)" for item in binding["elements"]))
            lines.extend(binding["requirements"] + [binding["note"]])
            for stru in binding["production_stru_declarations"]:
                lines.append("已有 partial STRU：" + stru["path"])
                for element in stru["elements"]:
                    names = element["original_names"]
                    lines.append(f"  {element['element']}: PP={names['pp'] or '未声明'}；NAO={names['nao'] or '未声明'}；ABF={names['abf'] or '未声明（不可猜）'}")
        for request in collection["software_requests"]:
            lines += [f"需闭合 {request['software']} fullcommit：{request['field']}", request["note"],
                      "stage 核对入口：" + "；".join(request["stages_to_bind"])]
            lines += ["  - " + requirement for requirement in request["requirements"]]
        if collection["existing_stage_controls"]:
            lines.append("已有stage controls（先检查，勿重复寻找）")
            for stage in collection["existing_stage_controls"]:
                lines.append(f"  {stage['label']} [{stage['id']}]")
                lines += ["    " + item["path"] for item in stage["controls"]]
        for group, label in (("existing_logs", "已有日志"), ("existing_receipts", "已有receipt/manifest")):
            lines.append(label + ("（先核对）" if collection[group] else "：公共记录未声明，先找历史来源。"))
            lines += ["  " + item["path"] for item in collection[group]]
        lines += collection["notes"]
    lines += ["", "=== 附项：不计入 strict issue 总数 ==="]
    for item in export["supplementary_not_counted_in_strict"]:
        lines.append(f"{item['kind']} | {item.get('case_id', '全库')}：{item['note']}")
        if "receipt_path" in item:
            lines.append("  公共证据：" + item["receipt_path"])
        for entry in item.get("entries", []):
            lines.append(f"  {entry['case_id']} | {entry['material']} | {entry.get('path', entry.get('metadata_path', ''))}")
            lines += ["    " + reason for reason in entry.get("reasons", [])]
    if number != stats["issue_count"]:
        raise ValueError("报告统计与逐条issue数量不一致")
    return "\n".join(lines) + "\n"


def render_html(export: dict) -> str:
    text = render_text(export)
    stats = export["stats"]
    escape = html.escape
    cards = []
    number = 0
    for case in export["cases"]:
        start = number + 1
        number += len(case["issues"])
        raw = "".join(f"<li><code>{escape(issue)}</code></li>" for issue in case["issues"])
        heading = f"{case['material']} · {case['dimension']} · {case['id']}"
        block_start = text.index(f"=== {case['material']} | {case['dimension']} | {case['id']} ===")
        block_end = text.find("\n=== ", block_start + 1)
        detail = text[block_start:block_end if block_end >= 0 else len(text)]
        cards.append(f'<article class="case" data-search="{escape(heading.lower(), quote=True)}">'
                     f'<h2>{escape(case["material"])} <span>{escape(case["dimension"])}</span></h2>'
                     f'<p class="case-id">{escape(case["id"])}</p><p>{escape(case["scientific_status"])} · '
                     f'{escape(case["status"])} · {len(case["issues"])}条原始issue</p>'
                     f'<ol start="{start}">{raw}</ol>'
                     f'{"<p>当前 strict 无缺项；不自动表示科学接受。</p>" if not raw else ""}'
                     f'<details><summary>找什么、已有证据与逐stage身份清单</summary><pre>{escape(detail)}</pre></details></article>')
    supplemental = text.split("=== 附项：不计入 strict issue 总数 ===", 1)[1]
    notes = "".join(f"<li>{escape(note)}</li>" for note in export["export_scope"]["notes"])
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GW数据库完整缺证清单</title><style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#10151e;color:#e9eef6;font:16px/1.65 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:40px 24px 80px}}h1{{font-size:30px;line-height:1.3;margin:0 0 16px}}h2{{font-size:22px;margin:0}}h2 span{{font-size:14px;color:#a9c0df}}.summary,.case,.notes{{padding:22px;margin:18px 0;background:#1a2330;border:1px solid #35455c;border-radius:10px}}.summary{{border-color:#cfa85e}}.counts{{font-size:22px;color:#ffd68b}}.muted,.case-id{{color:#bed0e5}}.case-id{{overflow-wrap:anywhere;margin:6px 0}}input{{width:100%;padding:13px 16px;background:#0b111b;border:1px solid #6c82a0;border-radius:8px;color:#f4f7fb;font:inherit}}input:focus{{outline:2px solid #78bafa;outline-offset:2px}}label{{display:block;margin-bottom:8px}}code,pre{{font:14px/1.75 ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere;white-space:pre-wrap}}li{{margin:8px 0}}ol{{padding-left:36px}}details{{margin-top:16px;border-top:1px solid #35455c;padding-top:12px}}summary{{cursor:pointer;color:#98ccff}}pre{{color:#d4e1f0}}[hidden]{{display:none!important}}.toolbar{{position:sticky;top:0;background:#10151eee;padding:18px 0;z-index:2;backdrop-filter:blur(8px)}}footer{{color:#a7bdd8;margin-top:30px}}@media(max-width:600px){{main{{padding:24px 14px}}.case,.summary,.notes{{padding:16px}}h1{{font-size:25px}}}}
</style></head><body><main>
<h1>GW数据库完整缺证清单</h1><p class="muted">逐材料、逐case保留全部原始 strict issue；可搜索并展开实际取证入口。公开网站不代表严格数据验收通过。</p><p><a href="index.html#/" style="color:#98ccff">返回数据库</a> · <a href="archive-completeness.json" style="color:#98ccff">下载完整JSON报告</a></p>
<section class="summary"><div class="counts">{stats['issue_count']}条原始issue · {stats['incomplete']}/{stats['total']}条记录不完整</div><p>strict：{escape(export['status'])}；{stats['complete']}条完整。附项、重绘图与runtime seal缺口不计入上述数量。</p></section>
<section class="notes"><ul>{notes}</ul></section>
<div class="toolbar"><label for="search">搜索材料 / case id / 维度</label><input id="search" type="search" placeholder="例如 GeTe、MoSe2、hbn-table-gw、3d" autocomplete="off"><p id="result-count" class="muted" aria-live="polite">显示全部{stats['total']}条记录</p></div>
{''.join(cards)}
<section class="notes"><h2>附项：不计入strict数量</h2><pre>{escape(supplemental)}</pre></section>
<footer>由 scripts/export_missing_evidence.py 读取 load_records / validate / completeness_report 生成。原始issue不删减、不豁免、不提升科学状态；所有文件引用仅使用仓库相对路径。</footer>
</main><script>
const search=document.getElementById('search');const cards=[...document.querySelectorAll('.case')];
search.addEventListener('input',()=>{{const query=search.value.trim().toLowerCase();let shown=0;for(const card of cards){{card.hidden=!card.dataset.search.includes(query);if(!card.hidden)shown++;}}document.getElementById('result-count').textContent=`显示 ${{shown}} / ${{cards.length}} 条记录`;}});
</script></body></html>\n'''


def checked_target(path: Path) -> Path:
    path = path.absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("export target contains a symlink")
    if not path.parent.is_dir():
        raise ValueError("目标父目录必须先存在；未写入任何交付文件")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="完整缺证导出；不改变strict门槛，默认不写文件")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="显式写database报告与可选outputs交付")
    mode.add_argument("--check", action="store_true", help="验证公开JSON/HTML与当前完整报告逐字节一致")
    parser.add_argument("--output-dir", type=Path, help="明确交付目录；必须已存在且配合--write")
    parser.add_argument("--report-output", type=Path, help="显式写原始完整报告；成功不代表strict通过")
    args = parser.parse_args()
    if args.output_dir and not args.write:
        parser.error("--output-dir requires --write")
    root = args.root.resolve()
    try:
        report, export = build_export(root)
        txt = render_text(export)
        report_text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        targets = {
            root / "database/archive-completeness.json": report_text,
            root / "database/missing-evidence.html": render_html(export),
        }
        if args.check:
            for target, content in targets.items():
                checked_target(target)
                if not target.is_file() or target.read_bytes() != content.encode("utf-8"):
                    raise ValueError("public missing-evidence report is missing or stale: " + target.name)
        if args.output_dir:
            output = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
            targets.update({output / "archive-completeness.json": report_text,
                            output / "missing-evidence.json": json.dumps(export, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                            output / "missing-evidence.html": render_html(export),
                            output / "missing-evidence.txt": txt})
        if args.report_output:
            if args.report_output.resolve() in {p.resolve() for p in targets}:
                raise ValueError("report-output must not replace a public check target")
            targets[args.report_output] = report_text
        to_write = targets if args.write else ({args.report_output: report_text} if args.report_output else {})
        for target in to_write:
            checked_target(target)
        for target, content in to_write.items():
            target.write_bytes(content.encode("utf-8"))
        if not args.write and not args.check and not args.report_output:
            print(txt, end="")
        else:
            print(f"缺证报告已{'写入' if args.write else '校验'}：{report['stats']['issue_count']}条原始issue；strict状态仍为{report['status']}。")
            print("This command validates schema/hash and report freshness, not strict completeness or scientific acceptance.")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Missing-evidence export stopped: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
