# Command line (M3, first slice)

Status: **read-only**. Every command except `export` prints a result and writes nothing;
`export` writes stock XML into a directory the caller names, and for a file that came from
disk it reproduces the source bytes exactly (order, blank lines, indentation, comments and
newline style — see §9 and toml-mapping §4). `web` serves the same read-only results as
pages on `127.0.0.1` (docs/web.md). No project storage, no event log, no packaging — those
are later milestones (docs/m1-design.md §5).

## 1. Invocation

```
python -m core.cli <scope> <command> [selector] [key=value ...] [--json]
```

Run it from the editor root, which is the directory that holds `core/`. `help` prints the
same table the parser accepts; `version` prints editor version, interpreter and the scopes
that resolve from the current directory.

## 2. Scopes

A scope root is a directory holding `Data/`, `Images/` and `Sounds/`.

| Scope | Meaning | Resolution |
|---|---|---|
| `Mod` | the mod project the current directory belongs to | `root=`/`mod=` option, else `mod` in the local config, else nearest ancestor with `mod.toml`; data lives under `Mod/` when present, otherwise at the project root |
| `Firefight` | the stock game data | `root=`/`firefight=` option, else `FIREFIGHT_DATA`, else `firefight` in the local config found upwards, else the copy shipped with the editor |
| `<name>` | another mod folder in the workspace | a directory of that name, else `<workspace>/Mods/<name>`, else `<workspace>/<name>`; workspace from `workspace=<dir>`, else `FIREFIGHT_MODS`, else the local config, else the current directory |

A scope root is the directory that holds `Data/`, `Images/` and `Sounds/`; passing the
`Data` directory itself is accepted and normalized to its parent. For an installed game
that is the directory containing `Firefight.exe`. Nothing is written
to a scope: the editor never edits the game directory, and `export` writes only under
`to=`. The local config `.ff-editor.local.toml` (keys `firefight`, `mod`, `workspace`) is
read from the nearest ancestor directory and belongs in `.gitignore`.

## 3. Paths and selectors

A command's third argument selects what to work on:

* nothing, or `all` — every entity in the scope;
* a category — `Infantry`, `Vehicles`, `Weapons`, `AT Guns`, `Aircraft`;
* a subdirectory or a single file — `Data/Weapons/WEAPON_PISTOL_P38.txt`;
* a document path suffix after the file — `Data/Infantry/American-Rifle Squad.txt/man/ammo`.

Paths use `/` and are relative to the scope root; `\` is accepted. Documents are read as
`.toml` under `Mod` and as `.txt` under `Firefight`; when both exist the `.toml` wins.

## 4. Commands

| Command | Aliases | What it does |
|---|---|---|
| `list` | `ls` | entities with category, storage format and size |
| `show` | `cat` | one entity as stored, or `as=toml`, `as=xml`, `as=raw` |
| `get` | | field values at a document path, or `field=<a.b.c>` |
| `find` | `grep` | search `tag=<name>`, `value=<text>` or `path=<a/b>` across the selection |
| `stats` | | counts by category, root element and storage format |
| `refs` | `graph` | outgoing references of the selection, grouped by kind |
| `deps` | | incoming references of `value=<token>` (who points at it) |
| `check` | `lint` | load everything; report load errors, warnings and dangling references |
| `export` | `emit` | write the selection as stock XML under `to=<dir>`, source bytes for files read from disk |
| `web` | `serve` | serve the read-only pages on `127.0.0.1` until Ctrl-C (docs/web.md) |
| `version` | | editor version, interpreter, resolved scopes |

Options: `root=`, `workspace=`, `to=`, `as=`, `field=`, `type=`, `kind=`, `path=`,
`limit=` (default 200 rows), `ignore_case=1`, `--json`. Unknown options, unknown scopes
and missing paths are usage errors. `key=value` options may appear in any order; `--json`
may appear anywhere.

`web` adds four options of its own: `port=` (default 8765), `token=<text>` (required in
every URL as `?t=<text>` when set), `pagesize=` (default 200 rows per page) and `browser=1`
(open the default browser instead of only printing the address).

## 5. Exit codes

| Code | Meaning |
|---|---|
| 0 | the command ran and found nothing to report |
| 1 | `check` found load errors, dangling references or warnings; **or** a parse/IO error aborted the command (the message names the file and, where known, the line) |
| 2 | usage error: unknown scope or command, missing or unknown option, unresolvable path |
| 130 | interrupted (Ctrl-C) |

## 6. Warnings

Warnings never fail a load, and `check` reports them as counts plus up to 20 samples. The
four kinds seen on real data: `//` comments removed, a file decoded as UTF-8 rather than
cp1252, an unknown element kept as a leaf, and text inside an element that also holds
children (dropped on export — see the `</data>>` typos in the WW3 project).

## 7. Measured on real data (2026-10-10)

Stock game 13.2.0.0 vs the released WW3 mod project (`.Mod/`, extracted outside this
repository):

| Command | Stock | WW3 |
|---|---|---|
| `stats` | 1840 files, 48 list files, 0 errors, 0.6 s | 765 files, 13 list files, 0 errors, 0.2 s |
| `check` | loaded 1792, skipped 48, 0 errors, 612 warnings, **2 dangling** | loaded 752, skipped 13, 0 errors, 559 warnings, **911 dangling** |
| `refs` | 23978 references, 0 errors, 4.3 s | 5793 references, 0 errors, 0.4 s |

`export` of the stock `Vehicles` selection writes 599 files and 2371815 bytes with 0
errors. Semantic round-trip equivalence on both corpora is reported in
[m1-report.md](m1-report.md); reference rules and coverage in [refs.md](refs.md).

Measured again on 2026-10-11, after the writer learned to keep the source layout:
`python tools/export_fidelity.py --data "<Firefight>/Data"` exports all 1840 stock files
and reports **1840 identical, 100.0%** (before, 1792 of them came back with reordered
siblings and 12 with different newlines).

The two stock dangling references are in the shipped data (`WEAPON_PISTOL_WZ_35_VIS` from
`Hungarian-TK3.txt` and `Hungarian-TKS.txt`). The 911 in WW3 are mostly references into
stock data: when a mod project is checked with the stock installation as a second scope,
882 of the 912 resolve. **That fallback is measured but not implemented** — the CLI
resolves each scope on its own, and cross-scope resolution arrives with the workspace
registry.

## 8. Reproducing the demo

```
python -m unittest discover -s tests -t .                       # 231 tests
python -m core.cli Firefight stats  "root=<Firefight>"
python -m core.cli Firefight check  "root=<Firefight>" --json
python -m core.cli Firefight refs   "root=<Firefight>" --json --limit 5
python -m core.cli Firefight deps   "value=WEAPON_PISTOL_P38" "root=<Firefight>"
python -m core.cli Firefight export Vehicles "root=<Firefight>" "to=<somewhere>"
python -m core.cli WW3 stats "root=<extracted WW3>/.Mod"
python -m core.cli Firefight web    "root=<Firefight>" port=8765
```

`check` exits 1 on both corpora, which is the intended report and not a crash. `deps` is
scope-wide: it answers for one scope at a time. `web` blocks until Ctrl-C and prints the
address it bound.

## 9. Limits of this slice

* No writes, no project directories, no `.editor/` state, no event log, no undo.
* `export` keeps the source layout: sibling order, blank lines, indentation, `//` comments
  and the file's own newline style all come from the source text (toml-mapping §4). Files
  without source text — a `.toml` project document — use the canonical writer instead
  (tab indent, CRLF, schema order), and an edit invalidates the layout of the element it
  touches for as long as it is applied in memory.
* Whether the engine accepts a file we re-emit is verified by an in-game load check, not here.
* `Maps/`, `Surnames/` and `equipment_*` are out of scope, as in M1.
* Modules are not loaded through `mod.txt` yet; a mod is a directory with `Data/`.

---

# 命令行（M3，第一部分）

状态：**只读**。除 `export` 外的所有命令都只打印结果、不写文件；`export` 把原版 XML 写入调用方指定的目录，对于
来自磁盘的文件按源字节精确复现（顺序、空行、缩进、注释与换行风格，见 §9 与 toml-mapping §4）。`web` 把同样的
只读结果作为页面发布在 `127.0.0.1`（见 docs/web.md）。没有工程存储、没有事件日志、没有打包——这些属于后续
里程碑（docs/m1-design.md §5）。

## 1. 调用方式

```
python -m core.cli <作用域> <命令> [选择器] [key=value ...] [--json]
```

在编辑器根目录（即含 `core/` 的目录）执行。`help` 打印解析器接受的同一张表；`version` 打印编辑器版本、解释器
以及从当前目录解析出的作用域。

## 2. 作用域

作用域根是含 `Data/`、`Images/`、`Sounds/` 的目录。

| 作用域 | 含义 | 解析顺序 |
|---|---|---|
| `Mod` | 当前目录所属的模组工程 | `root=`/`mod=` 选项，否则本地配置里的 `mod`，否则向上最近的含 `mod.toml` 的目录；存在 `Mod/` 时数据在其下，否则在工程根 |
| `Firefight` | 原版游戏数据 | `root=`/`firefight=` 选项，否则 `FIREFIGHT_DATA`，否则向上找到的本地配置里的 `firefight`，否则编辑器随附的副本 |
| `<名称>` | 工作区里的另一个模组文件夹 | 同名目录，否则 `<workspace>/Mods/<名称>`，否则 `<workspace>/<名称>`；工作区来自 `workspace=<目录>`，否则 `FIREFIGHT_MODS`，否则本地配置，否则当前目录 |

作用域根是含 `Data/`、`Images/`、`Sounds/` 的目录；直接传 `Data` 目录也接受，会被归一化到其父目录。对安装版游戏
而言就是含 `Firefight.exe` 的目录。任何作用域都不会被写入：编辑器永不修改游戏目录，`export` 只写入 `to=` 之下。
本地配置 `.ff-editor.local.toml`（键 `firefight`、`mod`、`workspace`）从最近的祖先目录读取，应当写进
`.gitignore`。

## 3. 路径与选择器

命令的第三个参数决定操作对象：

* 省略或 `all`——作用域内的全部实体；
* 类别——`Infantry`、`Vehicles`、`Weapons`、`AT Guns`、`Aircraft`；
* 子目录或单个文件——`Data/Weapons/WEAPON_PISTOL_P38.txt`；
* 文件之后的文档路径后缀——`Data/Infantry/American-Rifle Squad.txt/man/ammo`。

路径用 `/`、相对于作用域根；`\` 也接受。文档在 `Mod` 下按 `.toml` 读取、在 `Firefight` 下按 `.txt` 读取；两者都存在
时以 `.toml` 为准。

## 4. 命令

| 命令 | 别名 | 作用 |
|---|---|---|
| `list` | `ls` | 列出实体及类别、存储格式与大小 |
| `show` | `cat` | 按存储形态显示一个实体，或 `as=toml`、`as=xml`、`as=raw` |
| `get` | | 文档路径处的字段值，或 `field=<a.b.c>` |
| `find` | `grep` | 在选择范围内搜索 `tag=<名称>`、`value=<文本>` 或 `path=<a/b>` |
| `stats` | | 按类别、根元素与存储格式计数 |
| `refs` | `graph` | 选择范围的出向引用，按类别分组 |
| `deps` | | `value=<令牌>` 的入向引用（谁指向它） |
| `check` | `lint` | 全量加载；报告加载错误、警告与悬空引用 |
| `export` | `emit` | 把选择范围写成原版 XML（`to=<目录>`）；来自磁盘的文件按源字节写入 |
| `web` | `serve` | 在 `127.0.0.1` 上发布只读页面，直到 Ctrl-C（见 docs/web.md） |
| `version` | | 编辑器版本、解释器、已解析的作用域 |

选项：`root=`、`workspace=`、`to=`、`as=`、`field=`、`type=`、`kind=`、`path=`、`limit=`（默认 200 行）、
`ignore_case=1`、`--json`。未知选项、未知作用域与不存在的路径都算用法错误。`key=value` 选项顺序任意；`--json`
可以出现在任意位置。

`web` 另有四个选项：`port=`（默认 8765）、`token=<文本>`（设置后每个 URL 都必须带 `?t=<文本>`）、`pagesize=`
（默认每页 200 行）、`browser=1`（打开默认浏览器，而不只是打印地址）。

## 5. 退出码

| 码 | 含义 |
|---|---|
| 0 | 命令执行完成，没有需要报告的内容 |
| 1 | `check` 发现加载错误、悬空引用或警告；**或**解析/IO 错误导致命令中止（消息会指出文件，已知时给出行号） |
| 2 | 用法错误：未知作用域或命令、缺少或未知选项、路径无法解析 |
| 130 | 被中断（Ctrl-C） |

## 6. 警告

警告不会让加载失败，`check` 以计数加最多 20 条样例报告。真实数据上见到的四类：删除了 `//` 注释、文件按 UTF-8
而非 cp1252 解码、未知元素被保留为叶子、元素内同时有文本与子元素（导出时丢弃文本——见 WW3 工程里的
`</data>>` 笔误）。

## 7. 真实数据实测（2026-10-10）

原版游戏 13.2.0.0 对比已发布的 WW3 模组工程（`.Mod/`，在本仓库之外解包）：

| 命令 | 原版 | WW3 |
|---|---|---|
| `stats` | 1840 文件、48 个列表文件、0 错误、0.6 秒 | 765 文件、13 个列表文件、0 错误、0.2 秒 |
| `check` | 加载 1792、跳过 48、0 错误、612 警告、**2 悬空** | 加载 752、跳过 13、0 错误、559 警告、**911 悬空** |
| `refs` | 23978 条引用、0 错误、4.3 秒 | 5793 条引用、0 错误、0.4 秒 |

对原版 `Vehicles` 选择范围执行 `export` 写出 599 个文件、2371815 字节、0 错误。两个语料上的语义往返等价性见
[m1-report.md](m1-report.md)；引用规则与覆盖情况见 [refs.md](refs.md)。

2026-10-11 在写入器学会保留源排版之后重测：`python tools/export_fidelity.py --data "<Firefight>/Data"` 导出
全部 1840 个原版文件，结果为 **1840 个逐字节相同、100.0%**（此前其中 1792 个回来时兄弟节点顺序不同，12 个换行
不同）。

原版数据里的两条悬空引用来自随游戏发布的文件（`Hungarian-TK3.txt` 与 `Hungarian-TKS.txt` 指向
`WEAPON_PISTOL_WZ_35_VIS`）。WW3 的 911 条大多指向原版数据：把模组工程与原版安装作为两个作用域一起检查时，
912 条中有 882 条可以解析。**该回退已实测但尚未实现**——命令行逐个作用域独立解析，跨作用域解析要等工作区注册表。

## 8. 复现演示

```
python -m unittest discover -s tests -t .                       # 231 条测试
python -m core.cli Firefight stats  "root=<Firefight>"
python -m core.cli Firefight check  "root=<Firefight>" --json
python -m core.cli Firefight refs   "root=<Firefight>" --json --limit 5
python -m core.cli Firefight deps   "value=WEAPON_PISTOL_P38" "root=<Firefight>"
python -m core.cli Firefight export Vehicles "root=<Firefight>" "to=<某个目录>"
python -m core.cli WW3 stats "root=<解包的 WW3>/.Mod"
python -m core.cli Firefight web    "root=<Firefight>" port=8765
```

两个语料上 `check` 都退出 1，这是有意的报告而非崩溃。`deps` 是作用域级的：一次只回答一个作用域。`web` 会一直
阻塞到 Ctrl-C，并打印它绑定到的地址。

## 9. 本部分的限制

* 不写文件、没有工程目录、没有 `.editor/` 状态、没有事件日志、没有撤销。
* `export` 保留源排版：兄弟节点顺序、空行、缩进、`//` 注释与文件自身的换行风格全部来自源文本
  （toml-mapping §4）。没有源文本的文件——`.toml` 工程文档——改用规范写入器（制表符缩进、CRLF、schema 顺序）；
  一次编辑会在内存中让它触及的元素的排版失效。
* 重新输出的文件是否被引擎接受，要在游戏内加载验证，本工具不做这件事。
* `Maps/`、`Surnames/` 与 `equipment_*` 不在范围内，与 M1 相同。
* 模组尚未通过 `mod.txt` 加载；模组就是含 `Data/` 的目录。
