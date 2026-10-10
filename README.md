# firefight-mod-editor-open

An open-source third-party mod editor compatible with *Firefight* by Sean O'Connor: broader
coverage and stricter round-trip fidelity than the tooling that ships with the game.

Status: data core, XML/TOML round-trip, reference graph and the command line (M0–M3) plus
the read-only browsing slice of the local web UI (M7). Editing is M4 and is **not
implemented**: every command except `export` prints a result and writes nothing. `export`
reproduces a stock file byte for byte, layout included — 1840 of 1840 files on the installed
game (`tools/export_fidelity.py`).

## Quick start

Run the commands from the repository root; `-m core.cli` resolves the package there.

```
python -m core.cli version
python -m core.cli Firefight stats "root=<game directory>"
python -m core.cli Firefight show Data/Weapons/WEAPON_PISTOL_P38.txt as=toml --json
python -m core.cli Firefight deps value=WEAPON_PISTOL_P38 "root=<game directory>"
python -m core.cli Firefight web  "root=<game directory>"   # read-only pages on 127.0.0.1:8765
```

`<game directory>` is the directory that holds `Data/`, `Images/` and `Sounds/` — the one
containing `Firefight.exe` for an installed game. `Mod` is the project the current
directory belongs to (nearest ancestor with `mod.toml`). `Firefight` may also be resolved
from the `FIREFIGHT_DATA` environment variable or a local `.ff-editor.local.toml`; see
[cli.md](docs/cli.md) §2.

Exit codes: `0` success, `1` executed but reported a failure (the JSON payload is usually
still valid), `2` usage error, `130` interrupted.

## Repository layout

```
core/     the code: core/cli (command line), core/web (web UI), schema, parsers, model
docs/     specification and reports
tests/    the suite (231 tests, no game install, no network)
tools/    auxiliary tools: round-trip and fidelity harnesses, FirefightModPackager,
          launcher/ (the implementation behind the released ff-web.cmd / ff-ai.cmd)
```

The command line is started as `python -m core.cli`; `core/cli/__main__.py` is the module
entry point, so there is no `ff.py` at the root to import or wrap.

The **editor folder** a release ships — launchers, `skills/`, `docs/`, `core/`, `launcher/`,
a bundled `Firefight/` data copy and `Mods/` — is specified in
[project-layout.md](docs/project-layout.md) §12; the repository above is the source tree and
deliberately has a different shape.

## Tests

```
python -m unittest discover -s tests -t .      # 231 tests, no network, no game install
```

The suites that touch a real corpus are run by hand against the stock installation and the
released WW3 project; the measured numbers are in [m1-report.md](docs/m1-report.md) and
[cli.md](docs/cli.md) §7. Two harnesses need the game directory:

```
python tools/m1_roundtrip.py  --data "<game>/Data"          # XML -> TOML -> XML, semantic
python tools/export_fidelity.py --data "<game>/Data"        # export vs source, byte for byte
```

## Documentation

| Document | Contents |
|---|---|
| [cli.md](docs/cli.md) | command line: scopes, selectors, commands, options, exit codes, measured results |
| [web.md](docs/web.md) | the local read-only web UI: routes, options, design rules, limits |
| [project-layout.md](docs/project-layout.md) | milestones, module layout, permissions, event log plan |
| [refs.md](docs/refs.md) | reference rules and coverage |
| [toml-mapping.md](docs/toml-mapping.md) | how stock XML maps onto the TOML editing model |
| [m1-design.md](docs/m1-design.md) | data core design |
| [m1-report.md](docs/m1-report.md) | round-trip measurements on real data |
| [m0-baseline.md](docs/m0-baseline.md) | baseline inventory of the stock data |

## Building a mod

A mod is a directory containing `Data/`; the editor reads `.toml` under a project and
`.txt` under the stock scope, and `export` writes a selection back to stock XML under
`to=<directory>`, keeping the source layout of any file that came from disk. Nothing is
written to a scope: the game installation is never modified.

## License

GPL-3.0 — see [LICENSE](LICENSE).

---

# firefight-mod-editor-open（中文）

面向 Sean O'Connor 的 *Firefight* 的第三方开源模组编辑器：覆盖面比游戏自带工具更广，往返保真更严格。

当前状态：数据内核、XML/TOML 往返、引用图与命令行（M0–M3），以及本地 Web 界面的只读浏览部分（M7）。
编辑功能属于 M4，**尚未实现**：除 `export` 外的所有命令只输出结果、不写文件。`export` 能按字节复现原版文件
（含排版），在已安装的游戏数据上是 1840/1840（见 `tools/export_fidelity.py`）。

## 快速开始

命令在仓库根目录执行；`-m core.cli` 从该目录解析包。

```
python -m core.cli version
python -m core.cli Firefight stats "root=<游戏目录>"
python -m core.cli Firefight show Data/Weapons/WEAPON_PISTOL_P38.txt as=toml --json
python -m core.cli Firefight deps value=WEAPON_PISTOL_P38 "root=<游戏目录>"
python -m core.cli Firefight web  "root=<游戏目录>"   # 只读页面，127.0.0.1:8765
```

`<游戏目录>` 指含 `Data/`、`Images/`、`Sounds/` 的目录，也就是安装版里放 `Firefight.exe` 的那一层。
`Mod` 指当前目录所属的工程（向上最近的含 `mod.toml` 的目录）。`Firefight` 也可以由环境变量
`FIREFIGHT_DATA` 或本地的 `.ff-editor.local.toml` 解析；见 [cli.md](docs/cli.md) §2。

退出码：`0` 成功，`1` 已执行但报告失败（JSON 载荷通常仍然有效），`2` 用法错误，`130` 被中断。

## 仓库结构

```
core/     代码：core/cli（命令行）、core/web（Web 界面）、schema、解析器、模型
docs/     规范与报告
tests/    测试套件（231 条，不需要游戏安装、不联网）
tools/    辅助工具：往返与保真度脚本、FirefightModPackager、
          launcher/（发行版 ff-web.cmd / ff-ai.cmd 背后的实现）
```

命令行以 `python -m core.cli` 启动，`core/cli/__main__.py` 是模块入口，因此根目录不再有需要导入或包装的
`ff.py`。

发行版随附的**编辑器文件夹**——启动器、`skills/`、`docs/`、`core/`、`launcher/`、内置的 `Firefight/`
数据副本与 `Mods/`——见 [project-layout.md](docs/project-layout.md) §12；上面的仓库是源码树，形状有意不同。

## 测试

```
python -m unittest discover -s tests -t .      # 231 条，不联网、不需要游戏安装
```

需要真实语料的测试用例是针对原版安装与已发布的 WW3 工程手工运行的，实测数字见
[m1-report.md](docs/m1-report.md) 与 [cli.md](docs/cli.md) §7。两个脚本需要游戏目录：

```
python tools/m1_roundtrip.py  --data "<游戏>/Data"          # XML -> TOML -> XML，语义等价
python tools/export_fidelity.py --data "<游戏>/Data"        # 导出与源文件逐字节比较
```

## 文档

| 文档 | 内容 |
|---|---|
| [cli.md](docs/cli.md) | 命令行：作用域、选择器、命令、选项、退出码、实测结果 |
| [web.md](docs/web.md) | 本地只读 Web 界面：路由、选项、设计规则、限制 |
| [project-layout.md](docs/project-layout.md) | 里程碑、模块布局、权限、事件日志规划 |
| [refs.md](docs/refs.md) | 引用规则与覆盖情况 |
| [toml-mapping.md](docs/toml-mapping.md) | 原版 XML 如何映射到 TOML 编辑模型 |
| [m1-design.md](docs/m1-design.md) | 数据内核设计 |
| [m1-report.md](docs/m1-report.md) | 真实数据上的往返实测 |
| [m0-baseline.md](docs/m0-baseline.md) | 原版数据的基线清单 |

## 制作模组

模组是含 `Data/` 的目录；编辑器在工程作用域下读 `.toml`、在原版作用域下读 `.txt`，`export` 把选定内容写回
原版 XML（`to=<目录>`），并保留来自磁盘的文件的原始排版。任何作用域都不会被写入：游戏安装目录永不被修改。

## 许可

GPL-3.0，见 [LICENSE](LICENSE)。
