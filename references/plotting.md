# Reference band plotting

`scripts/plot_bands.py` defines the database plotting input: one data row per
k-path point, with the first column as the cumulative path coordinate and every
remaining column as one band. The order of the energy columns is preserved.
Blank lines and lines beginning with `#` are ignored.

```text
# x  band_1  band_2  band_3
0.0  -2.1     1.4     3.8
0.5  -1.9     1.2     3.7
1.0  -2.0     1.3     3.9
```

Optional high-symmetry labels use JSON:

```json
{"ticks": [{"x": 0.0, "label": "Γ"}, {"x": 1.0, "label": "M"}]}
```

The command writes the figure and a same-stem JSON sidecar containing the
calculation ID, input/table SHA-256 values, and labels. Matplotlib is optional
for static validation; the parser and sidecar writer use only the Python
standard library.

```bash
python3 scripts/plot_bands.py bands.dat \
  --output figures/si-gw.png \
  --calculation-id si-paper-all_kpath \
  --input-sha256 <sha256-of-the-input-bundle> \
  --labels kpath.json
```

## 原生 ABACUS 前沿图与科学边界

通用表格接口保持原始列序，不推断占据。归档生成使用
`index kx ky kz occupation_1 energy_1 ...` 表格，完整保留原生 k 序号、
分数坐标、占据与源文件 SHA-256。

```bash
python3 -B scripts/generate_band_figures.py --audit --allow-weighted-occupations
python3 -B scripts/generate_band_figures.py --write --allow-weighted-occupations
python3 -B -m unittest discover -s tests -p 'test*band*.py'
```

默认及 `--audit` 只读；只有 `--write` 写入。生成仅限 3D，不修改 2D。
新 `ks_frontier.svg`、`exx_frontier.svg`、`gw_frontier.svg` 和
`band_frontier_metadata.json` 登记为 primary；原 `band_comparison.svg/json`
改为 secondary，但原文件及全部原始谱的字节不变。重复生成必须字节幂等。

### 占据、导出维度和路径

- 物理整数占据必须是固定的占据前缀及空态后缀。
  `--allow-weighted-occupations` 仅接受有同记录日志占据数证据、完整路径核验、
  显式五位小数 `2/nk` 的均匀加权合同；不把任意分数占据当整数。
- 有限全零导出占据不意味着全空态。同一归档 `librpa.out` 中唯一一致的
  `Bands of occupation` 可作为显式 raw occupied/empty boundary 合同；
  不凭材料化学式、排序、GW gap 或视觉形状猜边界。原零值和日志哈希保留。
  无唯一边界则拒绝；非有限占据只能有显式低能诊断，不能报告普通 gap。
- `band_kpath_info` 首行语义是 **nbasis, nbands, nspins, nkpts**，
  不是把 nbasis 当作已导出的态数。此 schema 由独立阅读的 LibRPA
  `driver/read_data.cpp:2078–2089`、`docs/develop/dataset_format.md`
  的 `band_kpath_info` 节，以及预处理器
  `preprocess_abacus_for_librpa_band.py:103–157` 的输出次序交叉核验。
  这些新源仅作格式证据，**不代表历史 AlP 的 producer commit 已查明**。
- 同记录实际归档的 `KPT_nscf`、`KPT`、其他 `KPT*` 是候选。
  只有 Line 路径逐点分数坐标、全部采样数及 `band_kpath_info` 核验通过后使用。
  失败候选及实际采用路径保存；绝不将端点均摊到横轴。
  当前 x 为原生 k-point index，无倒空间度量，不能称 Å⁻¹ 或累积倒空间距离。

### 先冻结，再排序，再画图

完整未排序谱先审计，包括所有非有限位置、每条 raw band 范围、负 gap、
未选态侵入、声明导出窗与拒绝尾带。显示 raw 集先冻结为边界前最近 3 条
occupied 和后最近 4 条 empty（不足则取实际已有条数），随后逐 k 分别在
两个 manifold 内能量排序并连接等能量秩；不跨占据、不扩窗、不平滑，
不等价于波函数性格跟踪。完整一基 raw mapping 验证能量重构和多重集不变。
普通邻近带触及 ylim 仅报告 intrusion，不因此拒绝可信导出窗的 gap；
病态高空态掉到低能区则不能排序导入冻结窗以隐藏问题。

每个方法独立按自己的 occupied sampled-path VBM 对齐。
近隙视窗按本方法 frozen selected-window gap 设置：
`lower=-max(2.5,0.5*selectedgap)`，
`upper=selectedgap+max(3,0.5*selectedgap)`，不按全部深层能带扩窗。
视窗裁切只影响绘制，sidecar 显式记录被裁切的 raw k/band/能量位置，
完整冻结窗 energies/mapping、全表审计与路径 gap 不改变。
原 5/6 冻结窗的 admission audit 必须保留，不因减少显示带数而解除病态拒绝。
GaAs/GaP 的 GW 原冻结窗本身 gap<=0，即使新 3/4 显示窗排除了侵入态也不修复该问题，
拒绝新图并移除 record 的新 SVG 引用；
旧文件不删除，sidecar 保留完整谱/映射与拒绝理由，原 GW summary 不变。
当前有效声明 49 个新单法 SVG、17 个审计 sidecar；2 个无引用旧派生 SVG 不算交付图。
白底、黑轴、衬线大字；KS 青色虚线、EXX 黑色 dash-dot、GW 朱红实线。
VBM/CBM 空心标记来自未排序 raw 极值，其 raw band/k 序号和并列点留在 sidecar。
纵轴是 E − E_VBM，**不是 Fermi level**。

### 可补的属性不等于全谱数值验收

只补不存在的 KS/PBE 和 EXX `band_gap` 属性，定义固定为
**declared finite export window path gap**：在全部声明有效且有限的 nbands
及实际采样路径上 raw CBM(empty) − VBM(occupied)。
它不是 global BZ gap、收敛验证、PP/NAO 推荐或历史源身份认证。
已有 failed/validated/reported 属性均不覆写，GW 属性、summary 和记录状态不升级。

AlP 的 `56 44 1 121` 只声明有效 raw 1–44；原始 45–56 全部保留但拒绝。
完整尾审计须披露 KS 前 120 行尾 12 条逐行等于下一 k 的首 12 条，
EXX 尾有 6 个 NaN 和低于 −874 eV 的异常值，GW 尾 121×12 个零。
图必须公开 tail rejection，KS/EXX 的有限声明窗路径值仍可报告。
CaO/NaCl 及其他全谱负 gap 的 GW 图仅为固定低能窗诊断；
不得用全空态最小值扩窗、不得替换原 GW summary 或提高验收状态。
非有限原始占据 JSON 编码为 null，另存 raw 原值、k/band/源列位置；
严格 `allow_nan=False`，原始源文件字节不变。

五条独立 raw extrema 核验的 KS/EXX 路径值（eV）为
AlP 1.60680/7.39451（nocc=8）、BAs 1.18591/6.49227（4）、
BP 1.28967/7.13040（4）、CaO 3.55481/14.26462（8）、
NaCl 5.08771/13.36155（8）；以上不是全局 BZ 带隙。

## 二维原表与既有图的证据恢复

`scripts/migrate_properties.py --recover-table-evidence` 只恢复原表中已有的
PBE/EXX 采样路径性质及既有 PNG/PDF 的 `source_paths`，不运行物理计算，
不重新生成基组或能带图。默认只预审；所有来源通过后才可显式写入：

```bash
python3 -B scripts/migrate_properties.py --recover-table-evidence \
  --source-root /path/to/paper_materials
python3 -B scripts/migrate_properties.py --recover-table-evidence \
  --source-root /path/to/paper_materials --write
```

原 `table_band_source.json` 的 SHA 必须与 record 中保留的原侧录 SHA 一致；
归档表、当前侧录、原表来源的 hash、维度、原生 k 序号/分数坐标、固定
occupied/empty 边界和冻结窗路径值分别验证。普通原 DAT 要求原字节一致。
GeTe/SnSe 的 KS 原来源是 NPZ，归档表是已有转换 DAT，二者不是同一字节资产；
此时仅按原侧录 `archive_path` 和 DAT 的完整 SHA 验证归档身份，分别保留
原 NPZ 的实际 SHA 与转换表 SHA，不冒称 NPZ→DAT 已独立重做或验证。
这类性质明确限定为归档转换表的 sampled path gap。

已有人工 gap 不覆盖、不因方法别名再新增歧义重复项；由恢复器登记的路径值
若与已验证原表冲突则拒绝写入。全原表异常不能用较小冻结窗“修复”：
GeTe/SnSe EXX 的全 raw 与冻结窗负值分别写入 `method_diagnostics` 列表，
不生成普通正 gap，原诊断图仍可下载并明确标记。进一步独立重算发现两条 EXX
原侧录的路径值与冻结 raw 窗也不同：GeTe 原侧录 −70.88803 eV、重算冻结窗
−153.68881 eV；SnSe 原侧录 −553.74944 eV、重算冻结窗 −1108.09860 eV。
原侧录数值不覆盖，诊断同时保留重算全 raw、重算冻结窗与原侧录三个值及冲突标记；
不以其中任何一个异常值冒充接受的带隙。原图与指定来源逐字节核验后
才补关联，原图/谱、软件身份、summary、科学状态和集合发布状态均不改。
