> 语言：**中文** | [English](project-layout.md)

# 工程布局、数据文件职责与命令行规范（草案 v0）

> 状态：已合并进 `main`。标注「default」的条目是项目方尚未裁定、暂先采用的
> 选择，可能被推翻。项目方已裁决的规则写在所属小节中。

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
3. **文本 I/O 只有一个出口**：cp1252 / 无 BOM / 制表符缩进；从磁盘读入的文档保留其源字节，没有源文本的内容
   以 CRLF + 制表符写出（见 [toml-mapping.md](toml-mapping.zh-CN.md) §4.1 与 §5）。

AI 层经 [mcp.md](mcp.zh-CN.md) 规定的 MCP 服务取得同样的能力。

## 2. 工程目录结构

工程是**以模组名命名的文件夹**，可以直接导出为、或从 zip / 7z 包导入。

```
<模组名>/
├── ModInformation.toml                    模组元数据（关于工程自身的信息）
├── ModSetting.toml            模组设置（原版 mod.txt 的 TOML 形式）
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
└── EditorCache/                    编辑器工作数据与缓存（**属于工程，绝不进入安装包**，项目方已确认）
    ├── setting.toml            编辑器设置
    ├── log/                    事件日志分段目录（见 §8）
    │   ├── 20261009T012000.jsonl
    │   └── 20261009T031500.jsonl
    ├── refs.toml               交叉引用缓存
    ├── index.toml              实体索引与搜索缓存
    ├── baseline/               每次写入所替换的每个版本，按 sha256 存放（见 §8）
    ├── lock                    一次写入期间持有
    └── notes.toml              从原版 `//` 注释中提取的可读说明（可选）
```

**已确认规则**

* 每个实体一个文件，目录**镜像原版模组结构**（`Data/<类型>/`）。
* `ModInformation.toml` 存模组元数据；`ModSetting.toml` 存模组设置（原版 `mod.txt`）；交叉引用等缓存各自一个 TOML 文件。
* 缓存与编辑器状态一起放在工程根下的 **`EditorCache/`**，随工程迁移（项目方确认「把模组缓存放进模组文件夹」），
  且**绝不打包进安装包**。
* 模组是**部分覆盖**：工程只包含改动或新增的实体，其余一切从原版基线读取（实测 WW3 样本没有 `AT Guns/`
  与 `Aircraft/`）。
* `Surnames/` **既不建模也不打包**（项目方确认「不是模组内容」）；最多作为只读的原版资源被引用。

## 3. `ModInformation.toml`（模组元数据）

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

## 4. `ModSetting.toml`（= 原版 `mod.txt`）

实测 `mod.txt` 结构：10170 字节 / 428 行 / 12 个国家。`settings` 在两者之间双向转换（docs/cli.zh-CN.md §4.7）：`op=render` 读原版文件写 TOML 形态，`op=emit` 反向写回。映射示例见 [英文版](project-layout.md) 同节（`[mod_setting]` 基本字段、`[mod_setting.years]`、`[mod_setting.credits]`、
`[mod_setting.text_colours]`、`[[mod_setting.nationality]]` 及其 `.flags` / `.ranks` / `.default_images`
子表）。

要点：

* `<1>`..`<7>` 变成带引号的 TOML 键，因为 TOML 裸键不能以数字开头。`mod.txt` 不是合法 XML，因此其解析器
  单独实现。
* 重复出现的 `<equipment>` 合并为一个数组，导出时按数组元素逐个渲染回 `<equipment>`。
* `<equipment>`、`<surnames>` 下的名字就是编辑器认定的纯文本表格，因此模组自己命名的表格也会被识别为表格（docs/cli.zh-CN.md §4.3）。
* `<nationality>` 内的 `<units>` / `<filename>`（WW3 中各出现一次）：**原样保留并透传**，原值存入 TOML。项目方
  将其判定为**原版编辑器自身的特性**，作为 TODO 推迟，v1 不解释其语义。

## 5. 打包输出布局

```
<模组名>-<版本>.zip
├── Mod/                       ← 游戏 MOD 根（项目方确认；Android 上 assets/Mod/ 可佐证）
│   ├── mod.txt                由 ModSetting.toml 渲染
│   ├── Data/...               由实体 TOML 文件渲染
│   ├── Images/...
│   └── Sounds/...
├── README.md
└── LICENSE
```

* 打包必须对照**目标游戏版本**的原版基线：目标版本中已存在的文件可以复用、不必打包（项目方确认这正是
  「原版的东西都不报错」的含义）。
* **v1 不做 APK 打包**（项目方确认）。
* 默认前缀是 **`Mod/`**，README/LICENSE 放在 zip 根。可在 `ModInformation.toml` 中修改；**导入侧必须接受任意
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
| `Firefight` | 原版游戏路径（由 `root=<路径>`、`FIREFIGHT_DATA` 或 `Setting.toml` 给出） |
| `<其他模组文件夹名>` | 另一个模组，用于跨模组引用 |

另一个模组中的实体也可以用 `<其他模组文件夹名>:<路径>` 形式寻址，该形式只对这一个路径覆盖前缀。

示例：

```
python -m core.cli Mod list Vehicles                       # 列出本模组的车辆
python -m core.cli Firefight show Infantry/"American-Infantry Section 1"
python -m core.cli Mod set Infantry/"American-Infantry Section 1" field=description.quality value=QUALITY_ELITE --write
python -m core.cli Mod log                                 # 分段与最新记录
python -m core.cli Mod undo 1 --write                      # 回退最后一次写入所替换的内容
python -m core.cli Mod redo 1 --write                      # 重做最后一次撤销所回退的内容
python -m core.cli Mod refs Weapons/WEAPON_AT_RIFLE_L_39   # 查询引用（谁引用了它）
python -m core.cli Mod check                               # 完整校验
python -m core.cli Mod export --out dist/ --format mod-zip
```

`set` 把字段作为选项传入（`field=` 与 `value=`），因为任何含 `=` 的 token 都按 `key=value` 选项解析；`set`、`undo`
与 `redo` 需要 `--write`，并拒绝 `Firefight` 作用域（docs/cli.md §4.1、§4.2）。

`--json` 适用于所有命令，以便 UI 与 AI 调用。

## 7. AI 操作权限（对齐 DSH 的权限管理，项目方确认）

| 模式 | 能力 |
|---|---|
| `read-only` | 只读查询、校验与报告生成，完全不写入 |
| `workspace-write` | 可写工程目录内的文件；目录之外一律拒绝 |
| `danger-full-access` | 可写工程目录之外（导出到任意路径等），**每次都需要人工批准** |

* 操作逐条进入批准队列；**拒绝之后绝不重试**；任何失败都按 fail-closed 处理。
* 命令行用标志表达档位：需要写入的命令必须带 `--write`，指向工程目录之外的写入被拒绝（`set`、`undo` 与 `redo`
  都把自己限制在工程目录内，docs/cli.md §4.1、§4.2）。
* 所有 AI 动作都写入 `EditorCache/log/`，记录是谁做的改动。
* 任何写入型命令都产生事件（不变量 2）。

## 8. 事件日志与回滚

* 粒度：**单个实体的字段级修改**（一次 `set` 可能产生多条字段事件）。[default]
* 双轨：面向人的变更描述 + 面向机器的结构化事件。[default]
* 形式：事件溯源 + 周期性快照（`EditorCache/baseline/` 提供未编辑实体的原样回显）。
* 有意例外：日志用 **JSONL**（只追加，O(1)）；TOML 无法追加，用 TOML 记日志会退化为 O(N²)。
* **分段**：一个分段一个文件，规则是「**5 分钟内没有新事件就封存当前分段，下一个事件开启新分段**」。
  * 路径：`EditorCache/log/<分段开始本地时间>.jsonl`，例如 `20261009T012000.jsonl`。
  * 分段只追加；封存仅表示「不再写这个文件」，不产生额外标记。
  * 回滚与时间旅行按文件名字顺序读分段，而该顺序即时间顺序。
  * 分段文件没有大小上限；5 分钟规则是**唯一**的切分条件（不是进程启动/停止，也不是自然日）。
* **一条记录**是每行一个 JSON 对象，字段顺序为：`id`（`<分段名>:<行号>`）、`segment`、`timestamp`（带偏移的本地
  ISO 8601）、`actor`（`cli` 或 `mcp`）、`result`（`set`、`add`、`remove`、`pack`、`undo` 或 `redo`）、
  `target`（undo/redo 所回退记录的
  `id`，否则 `null`）、`document`（相对于工程的 POSIX 路径）、`entity`、`field`、`before`、`after`、
  `digest_before`、`digest_after`、`bytes_before`、`bytes_after`（均为 sha256 十六进制）与 `dry_run`（恒为
  `false`：空跑不是事件）。`pack` 记录不指向任何文档，也不带摘要：它只记下打过一次包，且不在任何可回滚的栈上。
* **字节级回滚**：每次写入都把文档写入前与写入后的内容存到 `EditorCache/baseline/<sha256>`，按内容寻址、跨改动去重，
  因此 `undo` 与 `redo` 写的是记录下来的字节，而不是重新序列化的结果。摘要对应的字节丢失、或字节与其摘要不符时命令
  失败；记录之后文档在磁盘上被改动时拒绝回退，而不是覆盖它。
* **状态靠重放而非另存**：当前生效的改动即日志中被记录、且未被更晚的 `undo` 回退的那些；一次 `undo` 会追加一条自己
  的记录并指向它所回退的改动，因此日志始终是唯一事实来源，不会有独立索引与之漂移。新的 `set` 会丢弃可重做的内容。

## 9. 依赖策略

* **标准库优先**，完全本地、可离线使用（项目方要求「尽量本地」）。
* UI 使用 Web 技术（项目方确认）；任何前端库都必须先列出并获批才能引入。
* 不使用 tomlkit、tomli 之类的 TOML 库（项目方确认为自研实现）。
* 目标运行时：Windows；Python 核心 + 内置 Web 界面。

## 10. 仓库布局与编辑器文件夹

存在两种布局，且刻意不同：**仓库**是 GitHub 上的源码树，**编辑器文件夹**是安装后的样子——无论编辑器以散装
代码还是打包可执行文件发行，形状都一样。

### 10.1 仓库（GitHub：`core/ docs/ tests/ tools/`）

```
<仓库>/
├── core/          代码
│   ├── cli/       命令行：作用域解析、命令、main、specs.py（唯一一张工具表）
│   ├── mcp/       在这些命令之上的 stdio MCP 服务（docs/mcp.md）
│   ├── web/       本地 Web 界面：服务、页面、运行实例记录、i18n.py（语言表）
│   └── *.py       schema、解析器（XML/TOML）、模型、转换、引用图、
│                  编辑（edit、journal、history）、index.py（引用索引）、
│                  settings.py（mod.txt 与 ModSetting.toml 的双向转换器）
├── docs/          规范：编辑器做什么、如何构建；英文文件 + `*.zh-CN.md` 中文对照（本文件所在）
├── tests/         测试套件（无需安装游戏、无需联网）
├── tools/         辅助工具：m1_roundtrip.py、export_fidelity.py、
│                  FirefightModPackager/，以及 launcher/（StartWebUI.cmd / StartWebUI(Basic).cmd / Start(McpOnly).cmd 背后的实现）
└── README.md  README.zh-CN.md  LICENSE  .gitignore  .gitattributes
```

命令行、MCP 服务与 Web 界面位于 `core/cli`、`core/mcp` 与 `core/web`，以
`core.cli.*` / `core.mcp.*` / `core.web.*` 导入。
`core/cli/scope.py`（`_editor_root`）是唯一识别编辑器文件夹的地方——仓库或发行版都识别——因此内置的
`Firefight/` 副本无需安装游戏也能找到。

命令行入口是模块 `core.cli`，在仓库根目录启动；顶层不再有 `ff.py`，因此
`python -m core.cli <作用域> <命令> ...` 是唯一形式。

### 10.2 编辑器文件夹（发行版：散装代码或打包）

```
<编辑器>/
├── StartWebUI          启动器，带 Web 界面（双击运行；页面在独立应用窗口）
├── StartWebUI(Basic)   启动器，无窗口，在控制台里服务
├── Start(McpOnly)      供 AI 调用的 stdio MCP 服务
├── StopAll             结束正在运行的编辑器
├── ErrorFinder         把 `check` 的结果整理成可读形式
├── ReadMe.md  ReadMe(Cn).md  ChangeLog.md  ChangeLog(Cn).md  Lisense
├── core/               代码（core/cli/__main__.py 是命令行入口）
├── docs/               文档：英文文件 + 对应的 `*.zh-CN.md` 中文对照
├── EditorAssets/       编辑器自身的资源
├── launcher/           上面各入口背后的实现
├── Firefight/          原版游戏数据副本（可选；参考用，只读）
├── Logs/               启动器日志
├── Mod/                模组工程区：一个子目录一个工程
│   └── <名称>/         ModInformation.toml、ModSetting.toml、mod.txt、
│                       README.md、LICENSE、Data/、Images/、Sounds/、
│                       EditorCache/{refs.toml, index.toml, log/, baseline/, notes.toml}
└── Setting.toml        本机设置：用哪个模组、哪个原版目录
```

入口点在磁盘上带 `.cmd` 后缀（`StartWebUI.cmd` 等）；Windows 的「隐藏已知扩展名」把它们显示成上面的名字。

由该布局得出的规则：

* 编辑器在自身入口旁边寻找原版数据（`<编辑器>/Firefight/Data`），并把该来源报告为 `editor copy <路径>`；
  因此不安装游戏也能用。
* `Mod/` 是 `<名称>` 作用域的工作区根，`ModInformation.toml` 标记一个模组工程。
* 模组工程是**部分覆盖**：它只能替换游戏本来就会读取的文件，因此 `Mod/Data`、`Mod/Images` 与 `Mod/Sounds`
  严格镜像游戏目录。
* `EditorCache/` 随工程迁移，不进任何包，存放缓存（`refs.toml`、`index.toml`，两者都由 `index` 写出）、事件日志与
  基线快照。
* `ModSetting.toml` 是原版 `Mod/mod.txt` 的 TOML 形式，由 `settings` 双向转换（docs/cli.zh-CN.md §4.7）。
  两个方向都是各自源字节的函数：`render` 复现读到的 `mod.txt` 的每个元素，`emit` 复现读到的
  `ModSetting.toml` 的原版形态。
* 两个启动器都以 `python -m core.cli` 运行命令行，该形式从当前目录解析 `core` 包，因此代码位于下一层 `core/`
  时两种布局都可用。

