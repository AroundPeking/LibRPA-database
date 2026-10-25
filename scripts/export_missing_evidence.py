#!/usr/bin/env python3
"""导出原始缺项、历史接受项与当前CI阻断项；默认只读。"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
from pathlib import Path, PurePosixPath

import library

SOFTWARE_REQUIREMENTS = [
    "The full immutable source commit for the historical stage or the SHA-256 of the exact executable; never use the current HEAD, a branch name, or a short token as a substitute.",
    "The version/commit token, launch time, and actual launch command from the original log of that stage.",
    "source_commit.txt or an equivalent source-identity receipt recording the historical source tree and its clean/dirty state.",
    "The historical build manifest, CMakeCache, or build receipt, bound to the SHA-256 of the executable actually run.",
    "A launch/job receipt binding the executable hash, input manifest, and spectrum-output hash from the same run.",
]
SCOPE_NOTES = [
    "Missing evidence means the public archive is not closed; it does not prove that files are absent from the original private directory. Do not search again for already archived files.",
    "Seven potential ABACUS identity groups and five potential LibRPA identity groups have been located in the original private sources but are not fully audited. They do not automatically close any fullcommit issue.",
    "Inspect existing stage controls, logs, and receipts first, then recover evidence from the same historical run. Do not substitute the current HEAD, another material, or a new case.",
    "Raw upload completeness, the fixed historical acceptance baselines (software identity, delta-Sternheimer program output), a full runtime seal, and numerical/scientific acceptance are separate levels. This checklist does not change scientific status.",
]
PATH_KEYS = {"path", "paths", "record_path", "repository_path", "evidence", "source_paths", "metadata_path", "receipt_path", "existing_identity_evidence"}


def assert_public(value: object, key: str = "") -> None:
    """拒绝私有绝对路径，而不是静默删去导致 issue 数量变化。"""
    if isinstance(value, str):
        if library.PRIVATE_PATH.search(value) or re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError("Export contains a private path; refusing to write public deliverables")
        if re.search(r"(?:^|[\s\"'=])/(?!/)[^\s]", value) or re.search(r"(?:^|\s)(?:file|ssh)://", value):
            raise ValueError("Export contains an absolute path or private source; refusing to write public deliverables")
        if key in PATH_KEYS or key.endswith("_path") or key.endswith("_paths"):
            path = PurePosixPath(value)
            if not value or path.is_absolute() or ".." in path.parts or "\\" in value or "://" in value:
                raise ValueError("Export file references must be repository-relative paths")
    elif isinstance(value, dict):
        for name, nested in value.items():
            assert_public(nested, name)
    elif isinstance(value, list):
        for nested in value:
            assert_public(nested, key)


def _file_view(item: dict) -> dict:
    view = {key: item[key] for key in ("path", "sha256", "label", "stage_id") if key in item}
    if re.search(r"[\u3400-\u9fff\uf900-\ufaff]", view.get("label", "")):
        prefix, separator, _ = view["label"].partition(" / ")
        filename = PurePosixPath(item["path"]).name
        view["label"] = (f"{prefix} / {filename}" if separator and not re.search(r"[\u3400-\u9fff\uf900-\ufaff]", prefix)
                         else filename)
    return view


def _stages(case: dict) -> list[dict]:
    stages = {}
    for item in case.get("files", {}).get("inputs", []):
        stage_id = item.get("stage_id")
        if not stage_id:
            continue
        stage = stages.setdefault(stage_id, {
            "id": stage_id, "label": _file_view(item).get("label", "").split(" / ", 1)[0],
            "controls": [], "execution_identity_verified_by_this_export": False,
        })
        stage["controls"].append(_file_view(item))
    return list(stages.values())


def _binding_request(root: Path, case: dict) -> dict:
    required = sorted(library._formula_elements(case.get("formula", case.get("material"))))
    generated_auxiliary = case.get("auxiliary_basis", {}).get("mode") == "pca_generated"
    required_roles = ["pp", "nao"] if generated_auxiliary else ["pp", "nao", "abf"]
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
        "elements": [{"element": element, "required_roles": required_roles} for element in required],
        "production_stru_declarations": declarations,
        "requirements": ([
            "Recover the original PP (.upf) and physical NAO (.orb) files and SHA-256 for each element, as actually used in the same production run.",
            "Bind the order and names in the original STRU ATOMIC_SPECIES/NUMERICAL_ORBITAL declarations to those exact payload hashes.",
            "Verify the PCA threshold from the declared production INPUT; do not invent a standalone .abfs payload.",
        ] if generated_auxiliary else [
            "Recover the original PP (.upf), physical NAO (.orb), and ABF (.abfs) files and SHA-256 for each element, as actually used in the same production run.",
            "Bind the order and names in the original STRU ATOMIC_SPECIES/NUMERICAL_ORBITAL/ABFS_ORBITAL declarations to those exact payload hashes.",
            "Candidate sets, matching filenames, for_aux orbitals, another material, or assets from a new case cannot replace exact role binding.",
        ]),
        "note": ("This run used a PCA-generated auxiliary basis; no standalone .abfs payload is required or claimed."
                 if generated_auxiliary else
                 "Existing partial STRU files establish the original PP/NAO names below, but lack ABFS_ORBITAL. Recover the ABF declarations, payloads, and run evidence from the original DF/EXX/GW stage; do not guess the ABF."
                 if declarations and not any(item["has_abfs_orbital"] for item in declarations)
                 else "No audited production STRU binding is available. Recover the original structure and role files first; do not fill them from candidate basis sets."),
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
        if not any(issue.startswith(f"software.{name}.identity:") for issue in issues):
            continue
        app = case.get("software", {}).get(name, {})
        result["software_requests"].append({
            "software": "ABACUS" if name == "abacus" else "LibRPA",
            "field": f"software.{name}.identity",
            "known_full_commit": app.get("commit"),
            "known_abbreviated_commit": app.get("abbreviated_commit"),
            "existing_identity_evidence": app.get("evidence", []),
            "stages_to_bind": ([f"{stage['label']} [{stage['id']}]" for stage in result["existing_stage_controls"]
                                if (stage["label"] in {"EXX", "GW", "LibRPA"}) == (name == "librpa")]
                               or (["SCF/DF/NSCF (ABACUS)"] if name == "abacus" else ["EXX/GW (LibRPA)"])),
            "requirements": SOFTWARE_REQUIREMENTS,
            "note": "The public historical identity chain is not closed. Audit existing/located evidence first; this does not prove that the files are absent.",
        })
    if any(issue.startswith(("species", "STRU")) for issue in issues):
        result["basis_binding_request"] = _binding_request(root, case)
    if result["missing_inputs"]:
        result["notes"].append("Recover this case's original production INPUT, KPT, STRU, and librpa.in files, preserving the SCF/DF/NSCF/EXX/GW stages. Do not synthesize replacements.")
    if any(issue.startswith("properties: EXX") for issue in issues):
        result["notes"].append("The existing EXX anomaly is not a missing ordinary gap. Recover a correct, complete spectrum from the same source with diagnostic, occupation, and export-range evidence, or explicitly record the scientific decision to retain the failed diagnostic. Do not invent a normal gap or substitute a paper value.")
    if not issues:
        result["notes"].append("No current raw completeness issues; this does not automatically establish a full runtime mirror or scientific acceptance.")
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
                       "note": "Existing 3D frontier figures and same-source plotting data can be redrawn; no search for missing ordinary images is needed. Redrawing does not promote numerical/scientific acceptance."})
    if rejected:
        extras.append({"kind": "rejected_gw_figures", "counted_in_strict_issues": False,
                       "entries": rejected,
                       "note": "The new GaAs/GaP GW frontier figures are scientifically/numerically rejected because of the near-gap window, not missing ordinary plots. Do not redraw them as normal results to fill a figure gap."})
    for case in cases:
        for item in case.get("files", {}).get("results", []):
            if PurePosixPath(item["path"]).name != "stage_input_receipt.json":
                continue
            receipt = json.loads(library._payload_bytes(root, item))
            if receipt.get("full_runtime_handoff_verified") is False or receipt.get("runtime_asset_seal_verified") is False:
                extras.append({"kind": "full_runtime_seal", "case_id": case["id"],
                               "material": case["material"], "counted_in_strict_issues": False,
                               "receipt_path": item["path"],
                               "note": "Recovered controls/role bindings do not establish a full runtime seal. Recover each stage's inputs, reader payloads, payload-survival/rehash evidence, and the identity chain from the same run."})
            text = json.dumps(receipt, ensure_ascii=False)
            if case["id"] == "mos2_ws2-table-gw" and re.search(r"405.*(?:悬空|dangling)|405 dangling", text):
                extras.append({"kind": "dangling_reader_links", "case_id": case["id"],
                               "material": case["material"], "counted_in_strict_issues": False,
                               "reported_link_count": 405, "receipt_path": item["path"],
                               "note": "The original recovery audit reported 405 dangling reader links in input_librpa. A manifest does not prove payload survival. Recover the original target payloads/full backup; do not add the link count to the raw completeness issue count. This export did not rescan the private directory."})
    return extras


def build_export(root: Path) -> tuple[dict, dict]:
    sets, cases = library.load_records(root)
    library.validate(root, sets, cases)
    report = library.completeness_report(root, sets, cases)
    if report["integrity_issues"]:
        raise ValueError("archive schema/hash integrity failed: " + "; ".join(report["integrity_issues"]))
    export = copy.deepcopy(report)
    export["export_scope"] = {"raw_issues_preserved": True, "historical_identity_baseline_applied_only_to_ci_gate": True, "notes": SCOPE_NOTES}
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
    lines = ["ABACUS + LibRPA public archive: complete missing-evidence checklist", "",
             f"Raw completeness status: {export['status']}; CI gate: {export['gate_status']}; {stats['total']} records, {stats['incomplete']} with retained raw issues, {stats['complete']} without raw issues, {stats['issue_count']} original issues in total.",
             "All original issues are preserved case by case. Supplementary evidence requests and runtime gaps are excluded from this total.", ""]
    lines += export["export_scope"]["notes"]
    for category, value in stats["missing_categories"].items():
        lines.append(f"Category {category}: {value['cases']} cases / {value['issues']} issues")
    number = 0
    for case in export["cases"]:
        collection = case["collection"]
        lines += ["", f"=== {case['material']} | {case['dimension']} | {case['id']} ===",
                  f"Archive completeness: {case['status']}",
                  f"Record: {collection['record_path']}", "Original raw completeness issues (full, unmodified text)"]
        if not case["issues"]:
            lines.append("  None.")
        for issue in case["issues"]:
            number += 1
            lines.append(f"  [{number:03d}] {issue}")
        if collection["missing_inputs"]:
            lines.append("Original inputs to recover: " + ", ".join(collection["missing_inputs"]))
        binding = collection.get("basis_binding_request")
        if binding:
            role_labels = {"pp": "PP(.upf)", "nao": "physical NAO(.orb)", "abf": "ABF(.abfs)"}
            lines.append("Exact roles by element: " + "; ".join(
                f"{item['element']} => " + " / ".join(role_labels[role] for role in item["required_roles"])
                for item in binding["elements"]
            ))
            lines.extend(binding["requirements"] + [binding["note"]])
            for stru in binding["production_stru_declarations"]:
                lines.append("Existing partial STRU: " + stru["path"])
                for element in stru["elements"]:
                    names = element["original_names"]
                    lines.append(f"  {element['element']}: PP={names['pp'] or 'not declared'}; NAO={names['nao'] or 'not declared'}; ABF={names['abf'] or 'not declared (do not guess)'}")
        for request in collection["software_requests"]:
            lines += [f"{request['software']} immutable identity to close: {request['field']}", request["note"],
                      "Stages to cross-check: " + "; ".join(request["stages_to_bind"])]
            lines += ["  - " + requirement for requirement in request["requirements"]]
        if collection["existing_stage_controls"]:
            lines.append("Existing stage controls (inspect first; do not search again)")
            for stage in collection["existing_stage_controls"]:
                lines.append(f"  {stage['label']} [{stage['id']}]")
                lines += ["    " + item["path"] for item in stage["controls"]]
        for group, label in (("existing_logs", "Existing logs"), ("existing_receipts", "Existing receipts/manifests")):
            lines.append(label + (" (cross-check first)" if collection[group] else ": not declared in the public record; inspect historical sources first."))
            lines += ["  " + item["path"] for item in collection[group]]
        lines += collection["notes"]
    lines += ["", "=== Supplementary items: excluded from the strict issue total ==="]
    for item in export["supplementary_not_counted_in_strict"]:
        lines.append(f"{item['kind']} | {item.get('case_id', 'whole archive')}: {item['note']}")
        if "receipt_path" in item:
            lines.append("  Public evidence: " + item["receipt_path"])
        for entry in item.get("entries", []):
            lines.append(f"  {entry['case_id']} | {entry['material']} | {entry.get('path', entry.get('metadata_path', ''))}")
            lines += ["    " + reason for reason in entry.get("reasons", [])]
    if number != stats["issue_count"]:
        raise ValueError("Report statistics and itemized issue count do not match")
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
                     f'<p class="case-id">{escape(case["id"])}</p><p>{escape(case["status"])} · '
                     f'{len(case["issues"])} original issues</p>'
                     f'<ol start="{start}">{raw}</ol>'
                     f'{"<p>No current raw completeness issues; scientific acceptance is not automatic.</p>" if not raw else ""}'
                     f'<details><summary>Evidence to recover, existing files, and stage identity checklist</summary><pre>{escape(detail)}</pre></details></article>')
    supplemental = text.split("=== Supplementary items: excluded from the strict issue total ===", 1)[1]
    notes = "".join(f"<li>{escape(note)}</li>" for note in export["export_scope"]["notes"])
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GW database: complete missing-evidence checklist</title><style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#10151e;color:#e9eef6;font:16px/1.65 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:40px 24px 80px}}h1{{font-size:30px;line-height:1.3;margin:0 0 16px}}h2{{font-size:22px;margin:0}}h2 span{{font-size:14px;color:#a9c0df}}.summary,.case,.notes{{padding:22px;margin:18px 0;background:#1a2330;border:1px solid #35455c;border-radius:10px}}.summary{{border-color:#cfa85e}}.counts{{font-size:22px;color:#ffd68b}}.muted,.case-id{{color:#bed0e5}}.case-id{{overflow-wrap:anywhere;margin:6px 0}}input{{width:100%;padding:13px 16px;background:#0b111b;border:1px solid #6c82a0;border-radius:8px;color:#f4f7fb;font:inherit}}input:focus{{outline:2px solid #78bafa;outline-offset:2px}}label{{display:block;margin-bottom:8px}}code,pre{{font:14px/1.75 ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere;white-space:pre-wrap}}li{{margin:8px 0}}ol{{padding-left:36px}}details{{margin-top:16px;border-top:1px solid #35455c;padding-top:12px}}summary{{cursor:pointer;color:#98ccff}}pre{{color:#d4e1f0}}[hidden]{{display:none!important}}.toolbar{{position:sticky;top:0;background:#10151eee;padding:18px 0;z-index:2;backdrop-filter:blur(8px)}}footer{{color:#a7bdd8;margin-top:30px}}@media(max-width:600px){{main{{padding:24px 14px}}.case,.summary,.notes{{padding:16px}}h1{{font-size:25px}}}}
</style></head><body><main>
<h1>GW database: complete missing-evidence checklist</h1><p class="muted">All original raw completeness issues are preserved by material and case. The fixed historical acceptance baselines (software identity, delta-Sternheimer program output) change only the CI decision, not these facts or scientific acceptance.</p><p><a href="index.html#/" style="color:#98ccff">Back to database</a> · <a href="archive-completeness.json" style="color:#98ccff">Download full JSON report</a></p>
<section class="summary"><div class="counts">{stats['issue_count']} original issues · {stats['incomplete']}/{stats['total']} records with raw issues</div><p>Raw completeness: {escape(export['status'])}; CI gate: {escape(export['gate_status'])}; {stats['accepted_exception_count']} grandfathered historical exception issues. Supplementary items, redrawn figures, and runtime seal gaps are excluded from these counts.</p></section>
<section class="notes"><ul>{notes}</ul></section>
<div class="toolbar"><label for="search">Search material / case ID / dimension</label><input id="search" type="search" placeholder="For example: GeTe, MoSe2, C512, 3d" autocomplete="off"><p id="result-count" class="muted" aria-live="polite">Showing all {stats['total']} records</p></div>
{''.join(cards)}
<section class="notes"><h2>Supplementary items: excluded from strict counts</h2><pre>{escape(supplemental)}</pre></section>
<footer>Generated by scripts/export_missing_evidence.py using load_records / validate / completeness_report. No original issues are removed or waived, and scientific status is not promoted. All file references are repository-relative.</footer>
</main><script>
const search=document.getElementById('search');const cards=[...document.querySelectorAll('.case')];
search.addEventListener('input',()=>{{const query=search.value.trim().toLowerCase();let shown=0;for(const card of cards){{card.hidden=!card.dataset.search.includes(query);if(!card.hidden)shown++;}}document.getElementById('result-count').textContent=`Showing ${{shown}} / ${{cards.length}} records`;}});
</script></body></html>\n'''


def checked_target(path: Path) -> Path:
    path = path.absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("export target contains a symlink")
    if not path.parent.is_dir():
        raise ValueError("The target parent directory must already exist; no deliverables were written")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Complete missing-evidence export with separate raw completeness and CI gate status; read-only by default")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Explicitly write database reports and optional output deliverables")
    mode.add_argument("--check", action="store_true", help="Verify public JSON/HTML matches the current full report byte for byte")
    parser.add_argument("--output-dir", type=Path, help="Explicit output directory; must exist and requires --write")
    parser.add_argument("--report-output", type=Path, help="Explicitly write the full raw and CI-gate report; success does not mean scientific acceptance")
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
            print(f"Missing-evidence report {'written' if args.write or args.report_output else 'checked'}: {report['stats']['issue_count']} original issues retained; CI gate is {report['gate_status']}.")
            print("This command validates schema/hash and report freshness; it does not change scientific acceptance.")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Missing-evidence export stopped: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
