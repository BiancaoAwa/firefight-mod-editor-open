# 工程布局 / 数据文件分工 / CLI 规范（草案 v0）

> 状态：**待用户审阅**。第 11 节记录了用户已明确裁决的条目；标「默认」的是用户尚未表态、我先采用的方案，随时可推翻。

## 1. 分层与铁律

```
core   ── 数据模型、容错解析、TOML 读写、引用图、校验、事件日志、打包
  ↑
CLI    ── 命令行入口（core 的唯一"脚本化"外壳）
  ↑
API    ── 给 UI / AI 的本地接口（与 CLI 同一套能力）
  ↑
UI     ── 本地 Web（浏览器打开，不起独立服务器）
```

三条铁律：

1. **UI 能做的，CLI 必须都能做**（UI 只是 CLI/API 的视图）。
2. **任何写入都必须产生一条事件**（可回滚、可审计）。
3. **文本 I/O 只有一个出口**：cp1252 / 无 BOM / 制表符缩进 / **行尾统一 CRLF**（见 [m0-baseline.md](m0-baseline.md)；CRLF 为用户裁决，见第 11 节 D3）。

## 2. 工程目录结构

工程 = 一个**以模组名命名的文件夹**；可直接导出/导入为 zip 或 7z。

```
<模组名>/
├── mod.toml                    模组元数据（工程自身的信息）
├── mod_setting.toml            模组设置（= 原版 mod.txt 的 TOML 形态）
├── README.md                   随包发布的说明
├── LICENSE                     随包发布的许可证
├── Mod/                        ← 导出为标准模组时，这一层就是原版 Firefight/Mod
│   ├── Data/
│   │   ├── Infantry/<单位名>.toml
│   │   ├── Vehicles/<单位名>.toml
│   │   ├── AT Guns/<单位名>.toml
│   │   ├── Aircraft/<单位名>.toml
│   │   ├── Weapons/<武器名>.toml
│   │   └── equipment_<国籍>.toml     单位清单（原版是纯文本）
│   ├── Images/
│   │   ├── Units/{HMGs,Mortars,Vehicles/{Hulls,Turrets,Profiles}}
│   │   ├── Uniforms/uniform_<部队名>/...
│   │   ├── Chooser/{Buttons}
│   │   └── Game/{Control Panel,Flags,Map,Toolbar}
│   └── Sounds/...
└── .editor/                    编辑器工作数据与缓存（**进工程、不进安装包**，用户已确认）
    ├── setting.toml            编辑器设置
    ├── log/                    事件日志分段目录（见 §8）
    │   ├── 20261009T012000.jsonl
    │   └── 20261009T031500.jsonl
    ├── refs.toml               交叉引用缓存
    ├── index.toml              实体索引 / 搜索缓存
    ├── baseline/               未编辑实体的原版源快照（保证"原样回吐"）
    └── notes.toml              从原版 `//` 注释里提取出来的人类可读备注（可选）
```

**已确认的规则**

* 每实体一个文件，目录**镜像原版模组架构**（`Data/<类型>/`）。
* `mod.toml` 存模组元数据；`mod_setting.toml` 存模组设置（原版 `mod.txt`）；交叉引用等缓存各自单独一个 toml。
* 缓存与编辑器状态统一放工程根下的 **`.editor/`**，随工程走（用户已确认「模组缓存扔模组文件夹里面」），且**不打进安装包**。
* 模组是**部分覆盖**：工程里只放被改动/新增的实体，其余实体从原版基线读取（实测 WW3 样本就没有 `AT Guns/` 和 `Aircraft/`）。
* `Surnames/` **不建模、不打包**（用户已确认「不是模组内容」），最多作为原版只读资源被引用。

## 3. `mod.toml`（模组元数据）

```toml
[mod]
name = "World War III - the Final War"
version_name = "2.3.0"        # 大.中.小
version_code = 2030007        # BMMSSNN
update_code = 2640            # YYWW
game_version = "13.2.0.0"     # 适配的游戏版本
authors = ["WW3 Mod Development Team"]
license = "CC BY-SA 4.0"
```

## 4. `mod_setting.toml`（= 原版 `mod.txt`）

实测 `mod.txt` 结构（10170 字节 / 428 行 / 12 个国家）见 [m0-baseline.md](m0-baseline.md) §2.4。映射示例：

```toml
[mod_setting]
name = "Firefight: World War III - the Final War"
author = "WW3 Mod Development Team"
show_scenarios = false
choose_unique_rifle_squad = false
allow_vehicles = true
allow_infantry = true
allow_at_guns = false
allow_artillery = true
minimum_commonness = 25
minimum_commonness_to_upgrade = 100

[mod_setting.years]
start = 2024
end = 2033
increment = 1

[mod_setting.credits]
attack1 = 250
attack2 = 350
attack3 = 450
attack4 = 550
defend1 = 200
defend2 = 275
defend3 = 350
defend4 = 425

[mod_setting.text_colours]
map_description = "FFFFFF"
custom_heading = "FFFFFF"
custom_option = "FFFFFF"
custom_unit_description = "FFFFFF"
game = "FFFFFF"
friend = "0000FF"
enemy = "FF0000"

[[mod_setting.nationality]]
name = "America (In Production)"
surnames = "surnames_american.txt"
voice = "US"
equipment = ["news_main.txt", "equipment_american.txt"]

[mod_setting.nationality.flags]
static = "flag_USA.png"
animated = "flag_animated_USA.png"

[mod_setting.nationality.ranks]
"1" = "Pvt"
"2" = "PFC"
"3" = "Cpl"
"4" = "Sgt"
"5" = "2Lt"
"6" = "1Lt"
"7" = "Cpt"

[mod_setting.nationality.default_images]
infantry = "uniform_game_american.png"
tank_crew = "uniform_game_american_tank_crew.png"
infantry_profile = "uniform_profile_american.png"
tank_crew_profile = "uniform_profile_american_tank_crew.png"
ranks = "uniform_ranks_american_ww3.png"
```

要点

* `<1>`..`<7>` → TOML 带引号键（TOML 裸键不能以数字开头）。`mod.txt` 本身不是合法 XML，解析器要单独实现。
* `<equipment>` 重复出现 → 合并成一个数组（导出时按数组顺序逐个渲染回 `<equipment>`）。
* `<nationality>` 内的 `<units>` / `<filename>`（WW3 各出现 1 次）：**原样保留、透传不改写**，TOML 里存原值。用户判定这是**原版编辑器自身功能**，先挂 TODO，不在 v1 解释其语义（见第 11 节 D2）。

## 5. 打包产物布局

```
<模组名>-<版本>.zip
├── Mod/                       ← 游戏 MOD 根（用户已确认；安卓侧 assets/Mod/ 实证）
│   ├── mod.txt                由 mod_setting.toml 渲染
│   ├── Data/...               由各实体 toml 渲染
│   ├── Images/...
│   └── Sounds/...
├── README.md
└── LICENSE
```

* 打包时必须能与**目标游戏版本**的原版基线对照：目标版本里已存在的文件可直接复用，不必打进包（用户已确认这就是「原版有的不报错」的含义）。
* **v1 不做 APK 打包**（用户已确认）。
* 前缀默认 **`Mod/`**，README/LICENSE 放 zip 根（用户裁决 D1）。可在 `mod.toml` 里改；**导入端必须兼容任意前缀**（`.Mod/`、`<模组名>/`、无前缀平铺都要能认），判据照现有工具 `find_mod_root()`：从最浅的含 `mod.txt` 的目录作为工程根。
* WW3 发行版用的是 `.Mod/` 且文档在 `.Mod/` 内——那是**工程文件夹命名**，不是标准安装布局（安卓 `assets/Mod/` 才是游戏实际读的根）。

## 6. CLI 规范

形式（保留用户要求的「谁在最前」）：

```
ff <谁> <命令> <操作> <路径...> [键=值 ...] [--json]
```

`<谁>` = 作用域根，取值：

| 取值 | 含义 |
|---|---|
| `mod` | 当前模组相对路径 |
| `firefight` | 原版游戏路径（由 `FIREFIGHT_REF` 或设置指定） |
| `<其他模组文件夹名>` | 其他模组，用于跨模组引用 |

其他模组的实体也可以用 `<其他模组文件夹名>:<路径>` 形式作**单个路径的前缀覆盖**。

示例：

```
ff mod list Vehicles                       # 列出本模组车辆
ff firefight show Infantry/"American-Infantry Section 1"
ff mod set Infantry/"American-Infantry Section 1" description.quality=QUALITY_ELITE
ff mod refs Weapons/WEAPON_AT_RIFLE_L_39   # 查引用（谁引用了它）
ff mod check                               # 全量校验
ff mod log --last 20                       # 最近 20 条事件
ff mod undo 3                              # 回滚最近 3 条事件
ff mod export --out dist/ --format mod-zip
```

`--json` 对所有命令生效，便于 UI / AI 调用。

## 7. AI 操作权限（仿 DSH 权限管理，用户已确认）

| 模式 | 能力 |
|---|---|
| `read-only` | 只读查询、校验、生成报告，不产生任何写入 |
| `workspace-write` | 可写工程目录内的文件，越界即拒绝 |
| `danger-full-access` | 可写工程目录之外（导出到任意路径等），**每次**都要人工批准 |

* 逐操作进审批队列；**被拒绝不重试**；一切失败按 fail-closed 处理。
* 所有 AI 动作都写进 `.editor/log/`（记录「谁改的」）。
* 有写入的命令一律产生事件（铁律 2）。

## 8. 事件日志与回滚

* 粒度：**单条实体字段级修改**（一次 `set` 可能产生多条字段事件）。【默认】
* 双轨：面向人的变更说明 + 面向机器的结构化事件。【默认】
* 形式：事件溯源 + 定期快照（`.editor/baseline/` 提供未编辑实体的原样回吐）。
* 破例说明：日志用 **JSONL**（追加写、O(1)）；TOML 无追加写能力，用 TOML 记日志会变成 O(N²)。
* **分段（用户裁决 D4）**：每段一个文件，规则是「**5 分钟没有新事件就封口，下一条事件开新段**」。
  * 路径：`.editor/log/<段起始本地时间>.jsonl`，例 `20261009T012000.jsonl`。
  * 段内是纯追加写；封口只表示"不再写入这个文件"，不产生任何额外标记。
  * 回滚 / 时间旅行跨段工作：按文件名字典序（= 时间序）串起来读即可。
  * 段文件不设大小上限；5 分钟是**唯一**的切分条件（不按进程启停切，也不按天切）。

## 9. 里程碑（与 [m0-baseline.md](m0-baseline.md) 结论对齐）

| 里程碑 | 内容 | 验收 |
|---|---|---|
| **M0**（本次） | 基线勘察、schema 逆向、映射规范 | 本文 + [m0-baseline.md](m0-baseline.md) + [toml-mapping.md](toml-mapping.md)，数据可复现 |
| M1 | 容错 XML ↔ 自研 TOML 双向 | [toml-mapping.md](toml-mapping.md) §8 全部通过 |
| M2 | 引用图与双向校验 | 模组内双向引用检查到位；悬空引用可定位 |
| M3 | CLI | 第 6 节全部命令可用、`--json` 稳定 |
| M4 | 事件日志与回滚 | 任意改动可回滚、可审计 |
| M5 | 工程文件与导入导出 | 文件夹 ↔ zip/7z 往返无损 |
| M6 | 打包与多模组 | 产物可被游戏加载（**由用户终验**）；多模组平行 + 跨模组引用 |
| M7 | 本地 Web UI | 与 CLI 能力等价 |
| M8 | 分发 | 安装包 / 使用说明 |

## 10. 依赖策略

* **标准库优先**，全本地、离线可用（用户要求「最好全本地实现」）。
* UI 用 Web 技术（用户已确认）；前端库若需引入，需先列清单等批准。
* 不引入 tomlkit / tomli 等 TOML 库（用户已确认自研）。
* 目标运行时：Windows；Python 主体 + 内置 Web UI。

## 11. 用户裁决记录

| 编号 | 日期 | 问题 | 裁决 | 状态 |
|---|---|---|---|---|
| D1 | 2026-10-09 | 安装包 zip 根布局 | **`Mod/` 前缀 + README/LICENSE 在 zip 根**；导入端兼容任意前缀 | 已定 |
| D2 | 2026-10-09 | WW3 `mod.txt` 的 `<nationality><units>/<filename>` | 这是**原版编辑器自身功能**，**先标记 TODO**，v1 原样透传不解释 | 已定，功能待做 |
| D3 | 2026-10-09 | 导出行尾 | **一律 CRLF** | 已定 |
| D4 | 2026-10-09 | 日志分段 | **每段一个文件**，5 分钟无新事件即封口开新段 | 已定 |
| D5 | 2026-10-09 | 缓存/编辑器数据位置 | 工程根下的 **`.editor/`**，随工程走，不进安装包 | 已定 |

**D3 的已知后果（如实记录，不美化）**：原版 1840 个文件里有 **16 个是纯 LF**（实测），统一 CRLF 后这 16 个文件在第一次导出时行尾会与原版不同。这**不影响**已商定的验收口径（XML 语义等价，而非逐字节一致），但导出产物与原版在这些文件上不会字节相同。

**D2 的 TODO**：逆向 `<nationality>` 下 `<units>` / `<filename>` 的真实语义（WW3 里是 `NATIONALITY_TAIWANESE` + `Taiwanese-`，疑似"该国籍单位文件前缀过滤器"），并在 UI 里暴露为可编辑项。
