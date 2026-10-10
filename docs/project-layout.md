# Project layout, data-file responsibilities and CLI specification (draft v0)

> Status: merged into `main`. Section 11 records the items the project owner has decided; entries marked "default" are choices adopted provisionally while the project owner has not yet ruled on them, and may be overruled.

## 1. Layering and invariants

```
core   ── data model, tolerant parsing, TOML read/write, reference graph, validation, event log, packaging
  ↑
CLI    ── command-line entry point (the only "scriptable" shell over core)
  ↑
API    ── local interface for UI and AI (the same capabilities as the CLI)
  ↑
UI     ── local web UI (opened in a browser, no standalone server)
```

Three invariants:

1. **Anything the UI can do, the CLI must be able to do** (the UI is only a view onto the CLI and API).
2. **Every write must produce an event** (reversible and auditable).
3. **Text I/O has a single exit point**: cp1252 / no BOM / tab indentation / **line endings always CRLF** (see [m0-baseline.md](m0-baseline.md); CRLF is a project-owner decision, see §11 D3).

## 2. Project directory structure

A project is a **folder named after the mod** and can be exported to, or imported from, a zip or 7z archive directly.

```
<mod name>/
├── mod.toml                    mod metadata (information about the project itself)
├── mod_setting.toml            mod settings (the TOML form of the stock mod.txt)
├── README.md                   documentation shipped with the package
├── LICENSE                     licence shipped with the package
├── Mod/                        ← when exported as a standard mod, this level is the stock Firefight/Mod
│   ├── Data/
│   │   ├── Infantry/<unit name>.toml
│   │   ├── Vehicles/<unit name>.toml
│   │   ├── AT Guns/<unit name>.toml
│   │   ├── Aircraft/<unit name>.toml
│   │   ├── Weapons/<weapon name>.toml
│   │   └── equipment_<nation>.toml    unit list (plain text in stock)
│   ├── Images/
│   │   ├── Units/{HMGs,Mortars,Vehicles/{Hulls,Turrets,Profiles}}
│   │   ├── Uniforms/uniform_<unit name>/...
│   │   ├── Chooser/{Buttons}
│   │   └── Game/{Control Panel,Flags,Map,Toolbar}
│   └── Sounds/...
└── .editor/                    editor working data and caches (**part of the project, never part of the install package**, confirmed by the project owner)
    ├── setting.toml            editor settings
    ├── log/                    event-log segment directory (see §8)
    │   ├── 20261009T012000.jsonl
    │   └── 20261009T031500.jsonl
    ├── refs.toml               cross-reference cache
    ├── index.toml              entity index and search cache
    ├── baseline/               stock source snapshots of unedited entities (guarantees "echo back unchanged")
    └── notes.toml              human-readable notes extracted from stock `//` comments (optional)
```

**Confirmed rules**

* One file per entity, with directories **mirroring the stock mod structure** (`Data/<type>/`).
* `mod.toml` holds mod metadata; `mod_setting.toml` holds the mod settings (stock `mod.txt`); caches such as cross-references each get their own TOML file.
* Caches and editor state live together under **`.editor/`** at the project root, travel with the project (the project owner confirmed "put the mod cache inside the mod folder") and are **never packed into the install package**.
* A mod is a **partial overlay**: the project contains only changed or added entities, and everything else is read from the stock baseline (the measured WW3 sample has no `AT Guns/` and no `Aircraft/`).
* `Surnames/` is **neither modelled nor packaged** (the project owner confirmed "not mod content"); at most it is referenced as a read-only stock resource.

## 3. `mod.toml` (mod metadata)

```toml
[mod]
name = "World War III - the Final War"
version_name = "2.3.0"        # major.minor.patch
version_code = 2030007        # BMMSSNN
update_code = 2640            # YYWW
game_version = "13.2.0.0"     # targeted game version
authors = ["WW3 Mod Development Team"]
license = "CC BY-SA 4.0"
```

## 4. `mod_setting.toml` (= the stock `mod.txt`)

The measured `mod.txt` structure (10170 bytes / 428 lines / 12 nations) is described in [m0-baseline.md](m0-baseline.md) §2.4. A mapping example:

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

Key points

* `<1>`..`<7>` become quoted TOML keys, because a TOML bare key may not start with a digit. `mod.txt` is not well-formed XML, so its parser is implemented separately.
* A repeated `<equipment>` is merged into one array, rendered back as one `<equipment>` per array element on export.
* `<units>` / `<filename>` inside `<nationality>` (one occurrence each in WW3): **preserved and passed through unchanged**, with the original value stored in TOML. The project owner classifies them as **a feature of the stock editor itself**, defers them as a TODO and does not interpret their semantics in v1 (see §11 D2).

## 5. Packaged output layout

```
<mod name>-<version>.zip
├── Mod/                       ← the game MOD root (confirmed by the project owner; evidenced by assets/Mod/ on Android)
│   ├── mod.txt                rendered from mod_setting.toml
│   ├── Data/...               rendered from the entity TOML files
│   ├── Images/...
│   └── Sounds/...
├── README.md
└── LICENSE
```

* Packaging must compare against the stock baseline of the **target game version**: a file that already exists in the target version may be reused and need not be packed (the project owner confirmed this is what "anything stock does not report an error" means).
* **v1 does not do APK packaging** (confirmed by the project owner).
* The default prefix is **`Mod/`** with README/LICENSE at the zip root (decision D1). It can be changed in `mod.toml`; **the import side must accept any prefix** (`.Mod/`, `<mod name>/` and a flat, prefixless layout must all be recognised), using the same test as the existing tool's `find_mod_root()`: the project root is the shallowest directory containing `mod.txt`.
* The PC-side root name has been verified by the project owner on a running installation: relative to the directory holding the game executable (`Firefight/`), it is **`Mod/`**, matching `assets/Mod/` on Android, so the exported root name `Mod/` is supported on both sides.
* The WW3 distribution uses `.Mod/` with its documents inside `.Mod/`; that is a **project folder naming habit**, not the standard install layout.

## 6. CLI specification

Form (retaining the project owner's requirement that the scope comes first). The base form of the original draft was `ff <who> <command> <operation> <path...> [key=value ...] [--json]`; the implemented entry is the module `core.cli`, started from the editor root:

```
python -m core.cli <scope> <command> <operation> <path...> [key=value ...] [--json]
```

`<scope>` is the scope root and takes these values:

| Value | Meaning |
|---|---|
| `Mod` | Path relative to the current mod |
| `Firefight` | Stock game path (given by `root=<path>`, `FIREFIGHT_DATA`, or `.ff-editor.local.toml`) |
| `<other mod folder name>` | Another mod, used for cross-mod references |

An entity in another mod may also be addressed with the form `<other mod folder name>:<path>`, which overrides the prefix for that single path.

Examples:

```
python -m core.cli Mod list Vehicles                       # list this mod's vehicles
python -m core.cli Firefight show Infantry/"American-Infantry Section 1"
python -m core.cli Mod set Infantry/"American-Infantry Section 1" description.quality=QUALITY_ELITE
python -m core.cli Mod refs Weapons/WEAPON_AT_RIFLE_L_39   # query references (who refers to it)
python -m core.cli Mod check                               # full validation
python -m core.cli Mod log --last 20                       # the 20 most recent events
python -m core.cli Mod undo 3                              # roll back the 3 most recent events
python -m core.cli Mod export --out dist/ --format mod-zip
```

`--json` applies to every command so that the UI and AI can call it.

## 7. AI operation permissions (mirroring DSH permission management, confirmed by the project owner)

| Mode | Capability |
|---|---|
| `read-only` | Read-only queries, validation and report generation, with no writes at all |
| `workspace-write` | May write files inside the project directory; anything outside is refused |
| `danger-full-access` | May write outside the project directory (exporting to an arbitrary path and so on), with **human approval required every time** |

* Operations enter an approval queue one by one; **a refusal is never retried**; every failure is handled fail-closed.
* All AI actions are written to `.editor/log/`, recording who made the change.
* Any command that writes produces an event (invariant 2).

## 8. Event log and rollback

* Granularity: **a single entity field-level modification** (one `set` may produce several field events). [default]
* Dual track: a human-facing change description plus a machine-facing structured event. [default]
* Form: event sourcing with periodic snapshots (`.editor/baseline/` provides unchanged echo-back of unedited entities).
* Deliberate exception: the log uses **JSONL** (append-only, O(1)); TOML cannot be appended to, so logging in TOML would be O(N²).
* **Segmentation (decision D4)**: one file per segment, with the rule "**seal the current segment after 5 minutes without a new event, and start a new segment on the next event**".
  * Path: `.editor/log/<segment start local time>.jsonl`, for example `20261009T012000.jsonl`.
  * A segment is appended to only; sealing merely means "no further writes to this file" and produces no extra marker.
  * Rollback and time travel work across segments by reading them in filename order, which equals chronological order.
  * Segment files have no size limit; the 5-minute rule is the **only** split condition (not process start/stop, not calendar day).

## 9. Milestones (aligned with the conclusions in [m0-baseline.md](m0-baseline.md))

| Milestone | Content | Acceptance |
|---|---|---|
| **M0** (this one) | Baseline survey, schema reverse-engineering, mapping specification | This document plus [m0-baseline.md](m0-baseline.md) and [toml-mapping.md](toml-mapping.md), with reproducible data |
| M1 | Tolerant XML ↔ in-house TOML, both directions | All of [toml-mapping.md](toml-mapping.md) §8 passes |
| M2 | Reference graph and bidirectional validation | Bidirectional references inside a mod are fully checked; dangling references are locatable |
| M3 | CLI | Every command in §6 works and `--json` is stable |
| M4 | Event log and rollback | Any change is reversible and auditable |
| M5 | Project files and import/export | Folder ↔ zip/7z round trip is lossless |
| M6 | Packaging and multi-mod | The output loads in the game (**final verification by the project owner**); parallel mods plus cross-mod references |
| M7 | Local web UI | Capability-equivalent to the CLI |
| M8 | Distribution | Install package and usage documentation |

## 10. Dependency policy

* **Standard library first**, fully local and usable offline (the project owner asked for "as local as possible").
* The UI uses web technology (confirmed by the project owner); any front-end library must be listed and approved before being introduced.
* No TOML library such as tomlkit or tomli (the project owner confirmed an in-house implementation).
* Target runtime: Windows; a Python core with a built-in web UI.

## 11. Decision record

| Id | Date | Question | Decision | Status |
|---|---|---|---|---|
| D1 | 2026-10-09 | Root layout of the install-package zip | **`Mod/` prefix with README/LICENSE at the zip root**; import accepts any prefix | Settled |
| D2 | 2026-10-09 | `<nationality><units>`/`<filename>` in WW3 `mod.txt` | A **feature of the stock editor itself**; **tracked as a TODO**, passed through unchanged and uninterpreted in v1 | Settled, work outstanding |
| D3 | 2026-10-09 | Exported line endings | **Always CRLF** | Settled; its known cost (the 16 bare-LF files are not byte-identical to stock after export) is explicitly accepted by the project owner |
| D4 | 2026-10-09 | Log segmentation | **One file per segment**, sealed and replaced after 5 minutes without a new event | Settled |
| D5 | 2026-10-09 | Location of caches and editor data | **`.editor/`** under the project root, travelling with the project and excluded from the install package | Settled |
| D6 | 2026-10-09 | Strictness of export versus import | **Conservative export, tolerant import**: the export side follows stock as closely as possible (sibling order follows stock), while the import side is more robust (tolerant parsing, accepting any sibling order and illegal characters) | Settled |

**Known cost of D3**: 16 of the 1840 stock files use **bare LF** (measured), so after normalisation to CRLF those 16 files differ from stock in line endings on first export. The difference does not affect the agreed acceptance criterion (XML semantic equivalence, not byte identity), but the exported artifact is not byte-identical to stock for those 16 files. The project owner has explicitly accepted this trade-off.

**What D6 means in detail:**

* Export: sibling blocks are rendered in stock order; repeated blocks within a group (`[[man]]`, `[[turret]]`, `[[ammo]]` …) keep their order strictly; nothing is rearranged on the editor's own initiative.
* Import: no failure is caused by sibling order, a bare `&`, a numeric tag name or mixed case; shape decisions are fixed by the schema and never depend on a single file's data.

**TODO from D2**: reverse-engineer the real semantics of `<units>` / `<filename>` under `<nationality>` (in WW3 they are `NATIONALITY_TAIWANESE` and `Taiwanese-`, apparently a unit-file prefix filter for that nationality) and expose them as editable fields in the UI.

## 12. Repository layout and the editor folder

Two layouts exist and they are deliberately different: the **repository** is the source tree
on GitHub, the **editor folder** is what an installation looks like — the same shape whether
the editor ships as loose code or as a packed executable.

### 12.1 Repository (GitHub: `core/ docs/ tests/ tools/`)

```
<repo>/
├── core/          the code
│   ├── cli/       command line: scope resolution, commands, main
│   ├── web/       the local read-only web UI: server
│   └── *.py       schema, parsers (XML/TOML), model, conversion, reference graph
├── docs/          specification and reports (this file lives here)
├── tests/         the suite (231 tests, no game install, no network)
├── tools/         auxiliary tools: m1_roundtrip.py, export_fidelity.py,
│                  FirefightModPackager/, and launcher/ (the implementation behind
│                  ff-web.cmd / ff-ai.cmd)
└── README.md  LICENSE  .gitignore  .gitattributes
```

The CLI and the web UI live in `core/cli` and `core/web` and are imported as
`core.cli.*` / `core.web.*`. `core/cli/scope.py` (`_editor_root`) is the one place that
recognises an editor folder — repository or distribution — so a bundled `Firefight/` copy
can be found without an installed game.

The CLI entry is the module `core.cli`, started from the repository root; there is no
`ff.py` at the top level, so `python -m core.cli <scope> <command> ...` is the only form.

### 12.2 Editor folder (a release: loose code or packed)

```
<editor>/
├── ff-web.cmd          launcher with the web UI (double-click; page in its own window)
├── ff-ai.cmd           launcher without a UI, for AI callers (forwards to the CLI)
├── skills/             AI skills: skills/firefight-editor/SKILL.md
├── docs/               documentation
├── core/               the code (core/cli/__main__.py is the CLI entry)
├── launcher/           the implementation behind ff-web.cmd / ff-ai.cmd
├── Firefight/          stock game data copy (optional; reference, read-only)
├── Mods/               mod projects
│   └── <name>/         mod.toml, mod_setting.toml, README.md, LICENSE,
│                       Mod/{Data,Images,Sounds},
│                       .editor/{refs.toml, index.toml, log/, baseline/, notes.toml}
└── .ff-editor.local.toml   machine-local settings: which mod, which stock directory
```

Rules that follow from this layout:

* The editor looks for the stock data next to its own entry point (`<editor>/Firefight/Data`)
  and reports that origin as `editor copy <path>`; an installation therefore works without
  the game being installed.
* `Mods/` is the workspace root for `<name>` scopes and `mod.toml` marks a mod project.
* A mod project is a **partial overlay**: it may only replace files the game already reads,
  so `Mod/Data`, `Mod/Images` and `Mod/Sounds` mirror the game folders exactly.
* `.editor/` travels with a project, is excluded from any package (D5), and holds the
  caches (`refs.toml`, `index.toml`), the event log and the baseline snapshots.
* `mod_setting.toml` is the TOML form of the stock `Mod/mod.txt`; its renderer is M5, so a
  fixture project may carry a deliberately partial file, marked as such inside the file.
* Both launchers run the CLI as `python -m core.cli`, which resolves the `core` package from
  the current directory, so the entry works in both layouts while the code sits one level
  down in `core/`.

---

# 工程布局、数据文件职责与命令行规范（草案 v0）

> 状态：已合并进 `main`。第 11 节记录项目方已裁决的事项；标注「default」的条目是项目方尚未裁定、暂先采用的
> 选择，可能被推翻。

## 1. 分层与不变量

```
core   ── 数据模型、宽容解析、TOML 读写、引用图、校验、事件日志、打包
  ↑
CLI    ── 命令行入口（core 之上唯一「可脚本化」的外壳）
  ↑
API    ── 面向 UI 与 AI 的本地接口（能力与 CLI 相同）
  ↑
UI     ── 本地 Web 界面（在浏览器中打开，不是独立服务器）
```

三条不变量：

1. **UI 能做的，CLI 必须能做到**（UI 只是 CLI 与 API 之上的视图）。
2. **每次写入都必须产生事件**（可回滚、可审计）。
3. **文本 I/O 只有一个出口**：cp1252 / 无 BOM / 制表符缩进 / **换行一律 CRLF**（见
   [m0-baseline.md](m0-baseline.md)；CRLF 是项目方裁定，见 §11 D3）。

## 2. 工程目录结构

工程是**以模组名命名的文件夹**，可以直接导出为、或从 zip / 7z 包导入。

```
<模组名>/
├── mod.toml                    模组元数据（关于工程自身的信息）
├── mod_setting.toml            模组设置（原版 mod.txt 的 TOML 形式）
├── README.md                   随包发布的说明
├── LICENSE                     随包发布的许可
├── Mod/                        ← 按标准模组导出时，这一层就是原版的 Firefight/Mod
│   ├── Data/
│   │   ├── Infantry/<单位名>.toml
│   │   ├── Vehicles/<单位名>.toml
│   │   ├── AT Guns/<单位名>.toml
│   │   ├── Aircraft/<单位名>.toml
│   │   ├── Weapons/<武器名>.toml
│   │   └── equipment_<国家>.toml    单位列表（原版为纯文本）
│   ├── Images/
│   │   ├── Units/{HMGs,Mortars,Vehicles/{Hulls,Turrets,Profiles}}
│   │   ├── Uniforms/uniform_<单位名>/...
│   │   ├── Chooser/{Buttons}
│   │   └── Game/{Control Panel,Flags,Map,Toolbar}
│   └── Sounds/...
└── .editor/                    编辑器工作数据与缓存（**属于工程，绝不进入安装包**，项目方已确认）
    ├── setting.toml            编辑器设置
    ├── log/                    事件日志分段目录（见 §8）
    │   ├── 20261009T012000.jsonl
    │   └── 20261009T031500.jsonl
    ├── refs.toml               交叉引用缓存
    ├── index.toml              实体索引与搜索缓存
    ├── baseline/               未编辑实体的原版来源快照（保证「原样回显」）
    └── notes.toml              从原版 `//` 注释中提取的可读说明（可选）
```

**已确认规则**

* 每个实体一个文件，目录**镜像原版模组结构**（`Data/<类型>/`）。
* `mod.toml` 存模组元数据；`mod_setting.toml` 存模组设置（原版 `mod.txt`）；交叉引用等缓存各自一个 TOML 文件。
* 缓存与编辑器状态一起放在工程根下的 **`.editor/`**，随工程迁移（项目方确认「把模组缓存放进模组文件夹」），
  且**绝不打包进安装包**。
* 模组是**部分覆盖**：工程只包含改动或新增的实体，其余一切从原版基线读取（实测 WW3 样本没有 `AT Guns/`
  与 `Aircraft/`）。
* `Surnames/` **既不建模也不打包**（项目方确认「不是模组内容」）；最多作为只读的原版资源被引用。

## 3. `mod.toml`（模组元数据）

```toml
[mod]
name = "World War III - the Final War"
version_name = "2.3.0"        # major.minor.patch
version_code = 2030007        # BMMSSNN
update_code = 2640            # YYWW
game_version = "13.2.0.0"     # 目标游戏版本
authors = ["WW3 Mod Development Team"]
license = "CC BY-SA 4.0"
```

## 4. `mod_setting.toml`（= 原版 `mod.txt`）

实测 `mod.txt` 结构（10170 字节 / 428 行 / 12 个国家）见 [m0-baseline.md](m0-baseline.md) §2.4。映射示例见上文
英文部分同节（`[mod_setting]` 基本字段、`[mod_setting.years]`、`[mod_setting.credits]`、
`[mod_setting.text_colours]`、`[[mod_setting.nationality]]` 及其 `.flags` / `.ranks` / `.default_images`
子表）。

要点：

* `<1>`..`<7>` 变成带引号的 TOML 键，因为 TOML 裸键不能以数字开头。`mod.txt` 不是合法 XML，因此其解析器
  单独实现。
* 重复出现的 `<equipment>` 合并为一个数组，导出时按数组元素逐个渲染回 `<equipment>`。
* `<nationality>` 内的 `<units>` / `<filename>`（WW3 中各出现一次）：**原样保留并透传**，原值存入 TOML。项目方
  将其判定为**原版编辑器自身的特性**，作为 TODO 推迟，v1 不解释其语义（见 §11 D2）。

## 5. 打包输出布局

```
<模组名>-<版本>.zip
├── Mod/                       ← 游戏 MOD 根（项目方确认；Android 上 assets/Mod/ 可佐证）
│   ├── mod.txt                由 mod_setting.toml 渲染
│   ├── Data/...               由实体 TOML 文件渲染
│   ├── Images/...
│   └── Sounds/...
├── README.md
└── LICENSE
```

* 打包必须对照**目标游戏版本**的原版基线：目标版本中已存在的文件可以复用、不必打包（项目方确认这正是
  「原版的东西都不报错」的含义）。
* **v1 不做 APK 打包**（项目方确认）。
* 默认前缀是 **`Mod/`**，README/LICENSE 放在 zip 根（裁决 D1）。可在 `mod.toml` 中修改；**导入侧必须接受任意
  前缀**（`.Mod/`、`<模组名>/` 以及无前缀的扁平布局都要能识别），判定方式与既有工具的 `find_mod_root()` 相同：
  工程根是包含 `mod.txt` 的最浅目录。
* PC 侧的根目录名已由项目方在运行中的安装上验证：相对于存放游戏可执行文件的目录（`Firefight/`）为
  **`Mod/`**，与 Android 上 `assets/Mod/` 一致，因此导出的根名 `Mod/` 在两端都成立。
* WW3 发行版使用 `.Mod/` 且文档也放在 `.Mod/` 内；那是**工程文件夹命名习惯**，不是标准安装布局。

## 6. 命令行规范

形式（保留项目方「作用域在前」的要求）。原始草案的基础形式是
`ff <who> <command> <operation> <path...> [key=value ...] [--json]`；已实现的入口是模块 `core.cli`，在编辑器
根目录下启动：

```
python -m core.cli <作用域> <命令> <操作> <路径...> [key=value ...] [--json]
```

`<作用域>` 是作用域根，取值如下：

| 取值 | 含义 |
|---|---|
| `Mod` | 相对于当前模组的路径 |
| `Firefight` | 原版游戏路径（由 `root=<路径>`、`FIREFIGHT_DATA` 或 `.ff-editor.local.toml` 给出） |
| `<其他模组文件夹名>` | 另一个模组，用于跨模组引用 |

另一个模组中的实体也可以用 `<其他模组文件夹名>:<路径>` 形式寻址，该形式只对这一个路径覆盖前缀。

示例：

```
python -m core.cli Mod list Vehicles                       # 列出本模组的车辆
python -m core.cli Firefight show Infantry/"American-Infantry Section 1"
python -m core.cli Mod set Infantry/"American-Infantry Section 1" description.quality=QUALITY_ELITE
python -m core.cli Mod refs Weapons/WEAPON_AT_RIFLE_L_39   # 查询引用（谁引用了它）
python -m core.cli Mod check                               # 完整校验
python -m core.cli Mod log --last 20                       # 最近 20 条事件
python -m core.cli Mod undo 3                              # 回滚最近 3 条事件
python -m core.cli Mod export --out dist/ --format mod-zip
```

`--json` 适用于所有命令，以便 UI 与 AI 调用。

## 7. AI 操作权限（对齐 DSH 的权限管理，项目方确认）

| 模式 | 能力 |
|---|---|
| `read-only` | 只读查询、校验与报告生成，完全不写入 |
| `workspace-write` | 可写工程目录内的文件；目录之外一律拒绝 |
| `danger-full-access` | 可写工程目录之外（导出到任意路径等），**每次都需要人工批准** |

* 操作逐条进入批准队列；**拒绝之后绝不重试**；任何失败都按 fail-closed 处理。
* 所有 AI 动作都写入 `.editor/log/`，记录是谁做的改动。
* 任何写入型命令都产生事件（不变量 2）。

## 8. 事件日志与回滚

* 粒度：**单个实体的字段级修改**（一次 `set` 可能产生多条字段事件）。[default]
* 双轨：面向人的变更描述 + 面向机器的结构化事件。[default]
* 形式：事件溯源 + 周期性快照（`.editor/baseline/` 提供未编辑实体的原样回显）。
* 有意例外：日志用 **JSONL**（只追加，O(1)）；TOML 无法追加，用 TOML 记日志会退化为 O(N²)。
* **分段（裁决 D4）**：一个分段一个文件，规则是「**5 分钟内没有新事件就封存当前分段，下一个事件开启新分段**」。
  * 路径：`.editor/log/<分段开始本地时间>.jsonl`，例如 `20261009T012000.jsonl`。
  * 分段只追加；封存仅表示「不再写这个文件」，不产生额外标记。
  * 回滚与时间旅行按文件名字顺序读分段，而该顺序即时间顺序。
  * 分段文件没有大小上限；5 分钟规则是**唯一**的切分条件（不是进程启动/停止，也不是自然日）。

## 9. 里程碑（与 [m0-baseline.md](m0-baseline.md) 的结论对齐）

| 里程碑 | 内容 | 验收 |
|---|---|---|
| **M0**（本次） | 基线调查、模式逆向、映射规范 | 本文档加 [m0-baseline.md](m0-baseline.md) 与 [toml-mapping.md](toml-mapping.md)，数据可复现 |
| M1 | 宽容 XML ↔ 自研 TOML，双向 | [toml-mapping.md](toml-mapping.md) §8 全部通过 |
| M2 | 引用图与双向校验 | 模组内双向引用完全检查；悬空引用可定位 |
| M3 | 命令行 | §6 每条命令可用且 `--json` 稳定 |
| M4 | 事件日志与回滚 | 任何改动可回滚、可审计 |
| M5 | 工程文件与导入导出 | 文件夹 ↔ zip/7z 往返无损 |
| M6 | 打包与多模组 | 产物能在游戏内加载（**最终验证由项目方进行**）；并行模组与跨模组引用 |
| M7 | 本地 Web 界面 | 能力与命令行等价 |
| M8 | 发行 | 安装包与使用文档 |

## 10. 依赖策略

* **标准库优先**，完全本地、可离线使用（项目方要求「尽量本地」）。
* UI 使用 Web 技术（项目方确认）；任何前端库都必须先列出并获批才能引入。
* 不使用 tomlkit、tomli 之类的 TOML 库（项目方确认为自研实现）。
* 目标运行时：Windows；Python 核心 + 内置 Web 界面。

## 11. 裁决记录

| 编号 | 日期 | 问题 | 裁决 | 状态 |
|---|---|---|---|---|
| D1 | 2026-10-09 | 安装包 zip 的根布局 | **`Mod/` 前缀，README/LICENSE 在 zip 根**；导入接受任意前缀 | 已定 |
| D2 | 2026-10-09 | WW3 `mod.txt` 中的 `<nationality><units>`/`<filename>` | **原版编辑器自身的特性**；**记为 TODO**，v1 原样透传、不解释 | 已定，工作待做 |
| D3 | 2026-10-09 | 导出的换行符 | **一律 CRLF** | 已定；已知代价（16 个纯 LF 文件导出后与原版不是逐字节相同）由项目方明确接受 |
| D4 | 2026-10-09 | 日志分段 | **一个分段一个文件**，5 分钟无新事件后封存并换新 | 已定 |
| D5 | 2026-10-09 | 缓存与编辑器数据的位置 | 工程根下的 **`.editor/`**，随工程迁移，且不进安装包 | 已定 |
| D6 | 2026-10-09 | 导出与导入的严格程度 | **保守导出、宽容导入**：导出侧尽量贴合原版（兄弟顺序随原版），导入侧更健壮（宽容解析，接受任意兄弟顺序与非法字符） | 已定 |

**D3 的已知代价**：1840 个原版文件中有 16 个使用**纯 LF**（实测），因此归一化为 CRLF 之后，这 16 个文件首次
导出时与原版在换行上有差异。该差异不影响约定的验收标准（XML 语义等价，而非逐字节相同），但对这 16 个文件
而言导出产物与原版不是逐字节相同。项目方已明确接受这一取舍。

**D6 的具体含义：**

* 导出：兄弟块按原版顺序渲染；同一组内的重复块（`[[man]]`、`[[turret]]`、`[[ammo]]` …）严格保持其顺序；
  编辑器不会自行重排任何东西。
* 导入：不会因为兄弟顺序、裸 `&`、数字标签名或大小写混用而失败；结构判定由 schema 固定，绝不依赖单个文件
  的数据。

**来自 D2 的 TODO**：逆向 `<nationality>` 下 `<units>` / `<filename>` 的真实语义（WW3 中为
`NATIONALITY_TAIWANESE` 与 `Taiwanese-`，疑似该国籍单位文件的前缀过滤），并在 UI 中将其暴露为可编辑字段。

## 12. 仓库布局与编辑器文件夹

存在两种布局，且刻意不同：**仓库**是 GitHub 上的源码树，**编辑器文件夹**是安装后的样子——无论编辑器以散装
代码还是打包可执行文件发行，形状都一样。

### 12.1 仓库（GitHub：`core/ docs/ tests/ tools/`）

```
<仓库>/
├── core/          代码
│   ├── cli/       命令行：作用域解析、命令、main
│   ├── web/       本地只读 Web 界面：server
│   └── *.py       schema、解析器（XML/TOML）、模型、转换、引用图
├── docs/          规范与报告（本文件所在）
├── tests/         测试套件（231 条，无需安装游戏、无需联网）
├── tools/         辅助工具：m1_roundtrip.py、export_fidelity.py、
│                  FirefightModPackager/，以及 launcher/（ff-web.cmd / ff-ai.cmd 背后的实现）
└── README.md  LICENSE  .gitignore  .gitattributes
```

命令行与 Web 界面位于 `core/cli` 与 `core/web`，以 `core.cli.*` / `core.web.*` 导入。
`core/cli/scope.py`（`_editor_root`）是唯一识别编辑器文件夹的地方——仓库或发行版都识别——因此内置的
`Firefight/` 副本无需安装游戏也能找到。

命令行入口是模块 `core.cli`，在仓库根目录启动；顶层不再有 `ff.py`，因此
`python -m core.cli <作用域> <命令> ...` 是唯一形式。

### 12.2 编辑器文件夹（发行版：散装代码或打包）

```
<编辑器>/
├── ff-web.cmd          带 Web 界面的启动器（双击运行；页面在独立窗口）
├── ff-ai.cmd           不带界面、供 AI 调用的启动器（转发给命令行）
├── skills/             AI 技能：skills/firefight-editor/SKILL.md
├── docs/               文档
├── core/               代码（core/cli/__main__.py 是命令行入口）
├── launcher/           ff-web.cmd / ff-ai.cmd 背后的实现
├── Firefight/          原版游戏数据副本（可选；参考用，只读）
├── Mods/               模组工程
│   └── <名称>/         mod.toml、mod_setting.toml、README.md、LICENSE、
│                       Mod/{Data,Images,Sounds}、
│                       .editor/{refs.toml, index.toml, log/, baseline/, notes.toml}
└── .ff-editor.local.toml   本机设置：用哪个模组、哪个原版目录
```

由该布局得出的规则：

* 编辑器在自身入口旁边寻找原版数据（`<编辑器>/Firefight/Data`），并把该来源报告为 `editor copy <路径>`；
  因此不安装游戏也能用。
* `Mods/` 是 `<名称>` 作用域的工作区根，`mod.toml` 标记一个模组工程。
* 模组工程是**部分覆盖**：它只能替换游戏本来就会读取的文件，因此 `Mod/Data`、`Mod/Images` 与 `Mod/Sounds`
  严格镜像游戏目录。
* `.editor/` 随工程迁移，不进任何包（D5），存放缓存（`refs.toml`、`index.toml`）、事件日志与基线快照。
* `mod_setting.toml` 是原版 `Mod/mod.txt` 的 TOML 形式；其渲染器属于 M5，因此测试用工程可以带一份刻意不完整的
  文件，并在文件内标注。
* 两个启动器都以 `python -m core.cli` 运行命令行，该形式从当前目录解析 `core` 包，因此代码位于下一层 `core/`
  时两种布局都可用。
