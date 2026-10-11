# Mo 历史配套复核

本轮仅整理已有文件，没有提交新的轨道或辅助基生成任务。
用户已明确禁止重复生成 Mo。

## 已确认的区别

| 用途 | PP / 物理 Mo NAO | 已有 ABFS / 来源范围 |
|---|---|---|
| 历史接受的 MoS2 | GTH，4s2p2d1f，27 函数 | 单层原始完整哈希链待补关联，不能称为资产不存在 |
| 历史接受的 MoSe2 | GTH，4s2p2d1f，27 函数 | 单层原始完整哈希链待补关联，不能借用异质结哈希作证明 |
| MoS2/WS2 异质结 producer3158800 | GTH，27 函数 | 库中 GTH_Mo_heterobilayer_3158800 已有完整配套，ABFS256 |
| 当前 MoTe2 PBE3328958 | Dojo-NC-SR，6s3p3d2f，44 函数 | PP/物理 NAO 从库中原样复用；Mo396 是已导出的辅助基，不再重复生成 |

两个历史单层属于相同的 GTH/27 函数定义，但没有拿到完整原始清单前，
不能断言它们的全部文件逐字节相同。当前 MoTe2 不属于这套 GTH 定义，
不能把 GTH 的辅助基直接拼到 Dojo44，也不能为统一名称而覆盖已完成 PBE。

## 核实的完整哈希

GTH 异质结配套，已与 producer3158800 输入清单核对：

```text
PP       f8d99b6265c66b570a1da1bdf23f0f3c9ef7328819b250c5795c87208d24ba9a
NAO27    84542972564084dd3257ab17c0a8ba6c9d04e72829a0dabae705ffa7fbee2161
ABFS256  3f9f08c7e3efa7971c817e58db697f6bb687cab4aa936e81fcd272e1ab43b7c6
```

当前 Dojo 配套：

```text
PP       7a392dee2cc7088d02184ddefa73b709f11e266fdde348a08eeaf8ea2870e448
NAO44    a259e30e8d201b110ea5429b9a75c4aae4388c6204197b219bd35256dec4e76e
ABFS396  6f0882fc4b224992633a34f0b33142d789b7ac37b361676d5d6f735b61637044
```

ABFS396 原生生成器退出0并写出完整文件，径向检查通过；原子 SCF 未收敛，
原封装因此 FAILED1:0。这些事实都保留，入库不等于材料 RI/EXX/GW 验收。
物理 Mo44 轨道不是本轮重新生成的。

## 来源

- `sets/GTH_Mo_heterobilayer_3158800/manifest.json`
- `sets/Dojo-NC-SR_Mo_repository_TZDP10/manifest.json`
- `../2d_gw_applications_20260905/reuse_sources/mos2_ws2_3158800/INPUT_MANIFEST.sha256`
- `../2d_gw/derivations/sections/material_numerical_validation.tex`
- `../2d_gw/validation/mos2_existing_producers_rpa_qavg_20260901/producer_manifest.csv`
- `..[private-path]
- `../2d_gw_applications_20260905/production_20260912/mote2_library_tzdp10_20260912/PBE_MANIFEST.json`
- `../2d_gw_applications_20260905/production_20260912/mote2_library_tzdp10_20260912/aux_preparation/EXPORT_RADIAL_REVIEW.json`
