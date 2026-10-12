# Contributing to the ABACUS + LibRPA GW database

Use the companion [basis skill](https://github.com/AroundPeking/abacus-librpa-gw-basis-skill) for the generation and validation method. This repository is the data layer: it receives immutable element-set and calculation records.

## Before adding files

Confirm that the PP, NAO, and ABF may be redistributed. Keep the source URL, release or archive commit, license status, original SHA-256, and any redaction note. Do not add private paths, hostnames, scheduler output, credentials, or binaries whose redistribution is not authorized.

## Add an element set

1. Put byte-preserved payloads in `data/elements/<Element>/pseudopotentials/`, `orbitals/`, `for_aux/`, or `auxiliary/`, using the SHA-256 as the filename stem.
2. Create `sets/<set-id>/set.json` with exact roles, hashes, dimensions, generation evidence, validation scope, and source information.
3. Use a new immutable set ID whenever a payload or PP/NAO/ABF binding changes.

## Add a calculation

在 `data/calculations/2d/<material>/<case-id>/` 或 `data/calculations/3d/<material>/<case-id>/` 中归档同一次计算的可移植 `inputs`、`results`、`logs` 和 `figures`。`species` 只绑定有生产关联证据的精确 set ID。历史证据仍可由基础 schema/hash 校验器读取；确实缺失关联时保留空 `species` 和 `missing` 说明，**但这不是完整上传，也不能通过 CI 或 Pages 发布门槛**。不得通过补一个候选集、描述性别名、missing 注释或历史白名单让不完整记录显示为完整。

`basis_candidates` 仅表示未证明生产绑定的后续候选。`gw_validated` 只用于指定 observable 和物理门槛真正通过的记录；`gw_diagnostic`、`path_diagnostic`、`failed` 和 `legacy_incomplete` 保留原始科学/归档状态，但所有记录必须遵守相同的完整上传要求。档案完整不等于科学验证通过，科学诊断也不能豁免档案缺证。

当前自动检查核验同 record 目录、已声明文件、完整 SHA、原 STRU 名称与精确角色绑定；“同 record”不自动证明所有阶段来自同一个生产 run。跨阶段谱/输入同 run 的科学来源审计须另有可复核原证据。本轮 MoS2/WSe2 导入器额外对独立原 run 的三谱和 15 份原输入逐字节核验；这不构成其他历史记录已完成同样审计。原 STRU 没有 ABFS 声明时，当前检查仍阻断，尚未实现经过真实案例验证的 receipt/manifest 替代合同；不能补自述布尔标志跳过此项。

### 严格完整上传要求

- 同 record、同 case 目录中的真实、可读、已声明并记录 SHA-256 的 `INPUT`、`KPT`、`STRU` 和 `librpa.in`。允许 `scf__INPUT`、`INPUT_scf` 等明确阶段名，不允许用 manifest、`INPUT.info`、`STRU.cif` 或别的计算目录冒充原输入。
- `species` 覆盖 formula/material 的所有元素，所有 `set_id` 均非 null。每个精确 set 都有一个可辨的 PP、**physical NAO** 和 ABF payload；`for_aux` 不代替 physical NAO，`missing_roles` 必须为空。
- 对照每份 `STRU` 中出现的 `ATOMIC_SPECIES`、`NUMERICAL_ORBITAL` 和 `ABFS_ORBITAL` 原始文件名，使用 exact species 的 `asset_aliases` 或同角色、同完整 SHA-256 文件的可信 `label`/`original_name` 证明绑定。至少一份生产 `STRU` 必须声明 physical NAO 和 ABF；普通 SCF 阶段可不含 ABF，但不能全部跳过 ABF 关联。可移植相对路径（含 `../assets/`）必须精确对应已证明的 alias 或实际指向绑定的同 hash 资产，不能按 basename 猜测。描述性 catalog 别名、相同元素和碰巧相同的文件名不证明生产关联。
- 通用辅助基 `ORBITAL_<R>U.abfs` 的内部 `Element` 可是模板元素，但仅在同 run 原始 `STRU` 明确声明该文件名、精确 `asset_aliases` 和 payload SHA-256 绑定均成立时接受。此规则仅用于 ABF，不放宽 PP/physical NAO 的元素匹配，也不改写原文件头。
- ABACUS、LibRPA 都记录完整不可变 commit。未知 identity 必须如实保留，并阻断完整上传；不能猜测补齐。
- 至少一个实际 KS/PBE/DFT、EXX 或 GW 能带结果；原始表须可读、非空、各行宽度一致。表中真实保留的 NaN/Inf 属于科学诊断，不应伪称缺文件，也不能因此删除异常态或宣布科学通过。
- 每个**实际存在**的方法都必须有非 failed、有限数值、单位 eV 的 `band_gap`，或明确受限/路径 gap observable，证据包含本 record 的同方法原始 band 文件且所有 evidence 都在本 record 有效声明。并非默认要求每条记录都有三个方法；failed 性质本身不能代替有限 observable。
- 至少一张可读的 SVG/PNG/PDF 能带图；空文件、损坏图和非 band 图片不能通过。SVG 必须有可见的曲线 stroke；隐藏、全透明或零线宽路径不能代替实际图。所有格式都声明 `source_paths`，至少包含一份同 record 可读的 band；允许同时包含同 record 的 KPT、log、sidecar，但所有图源须存在、非空且通过 hash。SVG 的能量/k-path 语义与实际曲线路径也须可识别；跨 case 软链不能冒充同一次 run 的归档。
- 对受限 observable，明确记录 restricted/raw-band frontier **path observable**、原始态索引、定义和证据；不得伪造普通 gap 或将路径/有限态结果改称全局基本带隙。完整性检查不推断或重算 gap，不升级原始科学状态。

## Add a calculated property

Append one entry to the calculation's `properties` array. A property needs a
stable key, an open lowercase category slug, a label, method, value, unit,
status, and at least one evidence path that is already listed in the same
record's `files` groups. The evidence file must have its SHA-256 recorded
there. Values may be numbers, text, arrays, or objects; use arrays or objects
for vector/tensor values and multi-part invariants.

```json
{
  "key": "z2_invariant",
  "category": "topological",
  "label": "Z2 invariant",
  "method": "Wilson loop",
  "value": {"spin_up": 1, "spin_down": 1},
  "unit": "dimensionless",
  "status": "reported",
  "definition": "Invariant from the occupied subspace on the stated k mesh",
  "evidence": [
    "data/calculations/2d/Material/case/results/wilson_loop.json"
  ]
}
```

Use `reported` when the result is recorded but has not passed a dedicated
validation gate, `validated` only when that gate is documented, `provisional`
for an explicitly incomplete analysis, and `failed` when the property test
failed. Existing categories include `electronic`, `topological`, `optical`,
`magnetic`, `structural`, and `other`; new lowercase slugs appear in the same
detail-page table automatically. Empty categories show no value until evidence
is contributed. Do not add a placeholder number.

The record validator checks required fields, category/status values, unique
`(category, key, method)` identities, and same-record evidence ownership. The
catalog is generated from calculation records:

```bash
python3 scripts/library.py --write-catalog
python3 scripts/library.py --check-catalog
python3 scripts/library.py --check-completeness
# 可选完整机器可读报告；真实缺证仍返回非零。
python3 scripts/library.py --check-completeness --completeness-report /tmp/archive-completeness.json
```

## Checks

```bash
python3 scripts/library.py --check-completeness
python3 scripts/library.py --write-catalog
python3 scripts/library.py --check-catalog
python3 scripts/build_indexes.py --write
python3 scripts/public_scan.py .
python3 -m unittest discover -s tests -v
git diff --check
```

这些检查不会编译或运行 ABACUS/LibRPA。`--check-completeness` 会一次输出全部不完整 case ID 和缺证项并非零退出；CI 与 Pages build 均显式执行该门槛，不使用 `continue-on-error`、diff-only 或历史豁免。旧库有真实缺失时门槛就应失败，不能为绿灯放宽规则。基础 `validate()` 和 catalog 生成保留历史 schema/hash 可读能力；catalog 的 `archive_completeness.status/issues` 诚实展示完整与缺失，不能取代严格检查。`--completeness-report <path>` 输出全部 case（包括完整记录）、原科学状态、缺证项、分类和总统计；CI 即使失败也保存此 JSON artifact，但不豁免严格步骤的失败。归档完整性与全谱 finite/物理接受单独审计，报告不得将一个已归档的异常数值表冒称科学合格。

能带图参考 [`references/plotting.md`](references/plotting.md)、`scripts/plot_bands.py` 和 `scripts/generate_band_figures.py`。通用脚本支持表格解析、能带绘制和 provenance；原生归档生成器先审计原谱、按占据冻结近隙 raw 集，再对每个方法独立设置 VBM 对齐和能量视窗。运行 `python3 scripts/plot_bands.py --help` 或 `python3 scripts/generate_band_figures.py --help` 查看命令。保留原始表的带顺序、占据证据与输入/图源 hash。对于 band-path table，记录的是 sampled/path gap；只有覆盖充分全 k 空间并完成对应物理验证后才称 global/fundamental gap。归档完整性、过程结束、数值可靠性和科学接受四者必须区分。

论文主值与归档运行值分开：`paper_values` 保存论文标题、PDF SHA-256、页码、表号、主作者列及报告精度，并引用同记录 `results/paper_reported_values.json`。该摘录与显示元数据必须一致且通过文件 hash 检查。列表及详情优先使用论文明确报告的 PBE/GW 值，Overview 同时展示原归档/path 值；原 `properties`、`summary`、谱和科学状态不改。主表未报告 EXX 时不能补造论文 EXX；现有 EXX 仍标归档来源。论文有限值不能替代严格上传要求的同方法原谱证据，也不会解除完整性阻断。旧 hBN 记录不使用新基组表行的数值。

The generated log index is a bijection: every retained file under a case's
`logs/` directory must appear exactly once in `data/log-index.json`. A basis
set enters `data/release-index.json` only when both the set and its linked case
are explicitly `publishable`; the basis-skill mirror then validates those
same IDs and hashes before accepting a copy.
