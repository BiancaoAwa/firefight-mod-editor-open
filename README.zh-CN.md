> 语言：**中文** | [English](README.md)

# firefight-mod-editor-open（中文）

面向 Sean O'Connor 的 *Firefight* 的第三方开源模组编辑器：覆盖面比游戏自带工具更广，往返保真更严格。

当前状态：数据内核、XML/TOML 往返、引用图、命令行，以及本地 Web 界面的只读浏览部分。
编辑功能**尚未实现**：除 `export` 外的所有命令只输出结果、不写文件。`export` 能按字节复现原版文件
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
`FIREFIGHT_DATA` 或本地的 `.ff-editor.local.toml` 解析；见 [cli.md](docs/cli.zh-CN.md) §2。

退出码：`0` 成功，`1` 已执行但报告失败（JSON 载荷通常仍然有效），`2` 用法错误，`130` 被中断。

## 仓库结构

```
core/     代码：core/cli（命令行）、core/web（Web 界面）、schema、解析器、模型
docs/     规范：编辑器做什么、如何构建
tests/    测试套件（不需要游戏安装、不联网）
tools/    辅助工具：往返与保真度脚本、FirefightModPackager、
          launcher/（发行版 ff-web.cmd / ff-ai.cmd 背后的实现）
```

命令行以 `python -m core.cli` 启动，`core/cli/__main__.py` 是模块入口，因此根目录不再有需要导入或包装的
`ff.py`。

发行版随附的**编辑器文件夹**——启动器、`skills/`、`docs/`、`core/`、`launcher/`、内置的 `Firefight/`
数据副本与 `Mods/`——见 [project-layout.md](docs/project-layout.zh-CN.md) §10；上面的仓库是源码树，形状有意不同。

## 测试

```
python -m unittest discover -s tests -t .      # 不联网、不需要游戏安装
```

需要真实语料的测试用例是针对原版安装与已发布的 WW3 工程手工运行的，实测数字见
[cli.md](docs/cli.zh-CN.md) §7。两个脚本需要游戏目录：

```
python tools/m1_roundtrip.py  --data "<游戏>/Data"          # XML -> TOML -> XML，语义等价
python tools/export_fidelity.py --data "<游戏>/Data"        # 导出与源文件逐字节比较
```

## 文档

| 文档 | 内容 |
|---|---|
| [cli.md](docs/cli.zh-CN.md) | 命令行：作用域、选择器、命令、选项、退出码、实测结果 |
| [web.md](docs/web.zh-CN.md) | 本地只读 Web 界面：路由、选项、设计规则、限制 |
| [project-layout.md](docs/project-layout.zh-CN.md) | 工程布局、命令行规范、权限、事件日志、依赖策略 |
| [mcp.md](docs/mcp.zh-CN.md) | AI MCP 交付面：协议修订、工具、资源、权限、错误映射 |
| [refs.md](docs/refs.zh-CN.md) | 引用规则与覆盖情况 |
| [toml-mapping.md](docs/toml-mapping.zh-CN.md) | 原版 XML 如何映射到 TOML 编辑模型 |
| [m1-design.md](docs/m1-design.md) | 数据内核设计 |

## 制作模组

模组是含 `Data/` 的目录；编辑器在工程作用域下读 `.toml`、在原版作用域下读 `.txt`，`export` 把选定内容写回
原版 XML（`to=<目录>`），并保留来自磁盘的文件的原始排版。任何作用域都不会被写入：游戏安装目录永不被修改。

## 许可

GPL-3.0，见 [LICENSE](LICENSE)。

