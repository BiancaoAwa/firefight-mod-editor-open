# 编辑器的工作方式

本仓库是编辑器核心：一层命令层，其上三个交付面，以及游戏文件的读写器。没有构建步骤。

## 数据流

```mermaid
flowchart TD
    subgraph stock["游戏安装目录（只读）"]
        A1["Firefight/Data/**/*.txt<br/>原版 XML"]
        A2["Firefight/Images、Sounds<br/>二进制"]
    end

    subgraph project["编辑器工程 Mod/&lt;名称&gt;"]
        B1["ModInformation.toml<br/>工程元数据"]
        B2["ModSetting.toml<br/>mod.txt 的 TOML 形式"]
        B3["mod.txt<br/>游戏实际读取的文件"]
        B4["Data/**/*.toml<br/>工作文件"]
        B5["Images/、Sounds/"]
        B6["EditorCache/log/*.jsonl<br/>EditorCache/baseline/**<br/>EditorCache/lock"]
        B7["EditorCache/index.toml<br/>EditorCache/refs.toml"]
    end

    subgraph layer["命令层"]
        C1["core/cli/commands.py<br/>run_command，34 条命令"]
        C2["core/cli/specs.py<br/>唯一一张工具表"]
        C3["core/cli/scope.py<br/>Mod、Firefight、&lt;名称&gt;"]
    end

    subgraph faces["交付面"]
        D1["命令行<br/>python -m core.cli"]
        D2["MCP 服务<br/>python -m core.mcp，进程内"]
        D3["Web 界面<br/>python -m core.cli Mod web，进程内"]
        D4["DSH 插件<br/>独立仓库，以子进程调用命令行"]
    end

    E1["&lt;名称&gt;-&lt;版本&gt;.zip<br/>Mod/ + README.md + LICENSE"]

    subgraph webmods["Web 交付面，按模块"]
        W1["core/web/server.py<br/>路由、各页面、写入路径"]
        W2["core/web/tables.py<br/>/equipment 背后的纯文本表编辑器"]
        W3["core/web/mcp_listener.py<br/>MCP over HTTP，其令牌与绑定地址"]
        W4["core/web/i18n.py<br/>页面模板与中文对照表"]
    end

    F1["core/roster.py<br/>纯文本单位清单，按物理行编辑"]

    subgraph pending["待完成"]
        P1["core/schema.py<br/># TODO(m5)：vehicle 与 at_gun 没有 schema"]
        P2["core/pack.py<br/># TODO(pack)：stock 基线比对与 APK 打包"]
        P3["core/pack.py<br/># KNOWN：只有 TOML 的文档按规范形式回写"]
        P4["无标记：init 不读模板，Images/ 与 Sounds/ 需 convert assets=1，<br/>Maps/、Surnames/、equipment_* 在 schema 之外，不向 stock 语料重试"]
    end

    A1 -->|convert| B4
    A2 -->|"convert assets=1"| B5
    A1 -->|firefight 作用域| C1
    C1 -->|"init、import"| B1
    B3 -->|settings op=render| B2
    B2 -->|settings op=emit| B3
    B4 -->|set、add、remove| B4
    B1 -->|set| B1
    B2 -->|set| B2
    C1 --> B6
    B6 -->|undo、redo| B4
    C1 -->|index --write| B7
    B7 -->|refs、deps| C1
    B4 -->|pack| E1
    B3 -->|pack| E1
    C3 --> C1
    C1 --> C2
    C1 --> D1
    C1 --> D2
    C1 --> D3
    D4 --> D1
    D3 --> W1
    W1 --> W2
    W1 --> W3
    W1 --> W4
    C1 --> F1
```

每次写入都经过 `core/edit.py`：暂存新字节、持有 `EditorCache/lock`、把新旧字节存进
`EditorCache/baseline/`，再向日志追加一条记录。`undo` 与 `redo` 写回记录里的字节，因此日志是
唯一的事实来源（见 docs/project-layout.md 第 8 节）。

## 仓库文件

| 路径 | 作用 |
| --- | --- |
| `core/__init__.py` | 版本号，只写在这一处 |
| `core/cli/__main__.py` | `python -m core.cli` 背后的入口 |
| `core/cli/main.py` | 参数解析、用法文本、退出码 |
| `core/cli/commands.py` | 全部命令，以及命令操作的 `Document` |
| `core/cli/scope.py` | `Mod`、`Firefight`、`<名称>` 三种作用域的解析，`entity_files` |
| `core/cli/specs.py` | MCP 服务据此渲染工具表、插件据此镜像的那张表 |
| `core/xml.py`、`core/toml.py` | 两个解析器与 TOML 写入器 |
| `core/convert.py` | XML 与 TOML 双向转换，含保布局写入器 |
| `core/schema.py` | 各根元素的形状与类型，以及两个工程文件 |
| `core/refs.py` | 引用规则与语料上的引用图 |
| `core/index.py` | 写出与读回 `EditorCache/index.toml` 与 `EditorCache/refs.toml` |
| `core/edit.py` | 字段写入、整文档增删、数组项、加锁、原子替换 |
| `core/journal.py` | 日志分段、基线、锁 |
| `core/history.py` | 规划并执行 `undo` 与 `redo` |
| `core/settings.py` | `mod.txt` 与 `ModSetting.toml` 的双向渲染 |
| `core/pack.py` | 生成模组 zip |
| `core/textio.py` | 解码、换行、导出编码 |
| `core/enums.py`、`core/errors.py` | 枚举表与错误模型 |
| `core/roster.py` | 纯文本单位清单，按物理行编辑 |
| `core/mcp/` | stdio JSON-RPC 服务、其工具与资源 |
| `core/mcp/__main__.py` | `python -m core.mcp` 背后的入口 |
| `core/mcp/server.py` | JSON-RPC 循环，兼容两代协议 |
| `core/mcp/tools.py` | 每个工具一次进程内命令调用 |
| `core/web/` | 页面、运行实例记录、语言表 |
| `core/web/server.py` | 路由、各页面，以及表单背后的写入路径 |
| `core/web/mcp_listener.py` | 可选的 MCP over HTTP 套接字、其令牌与绑定地址 |
| `core/web/tables.py` | `/equipment` 页面用的纯文本表编辑器 |
| `core/web/i18n.py` | 英文模板与中文对照表 |
| `docs/` | 说明文档与架构文档，中英各一份 |
| `docs/m1-design.md` | toml-mapping.md 背后的 M1 设计稿，不是说明文档 |
| `docs/firefight-docs/extract_docs_md.py` | 把游戏自带的 .mht 文档转成一份 markdown |
| `tests/` | `python -m unittest discover -s tests -t .` |
| `tools/launcher/` | PowerShell 启动器与其 `.cmd` 入口 |
| `tools/export_fidelity.py` | 对一个数据目录跑 `export`，逐文件比对字节 |
| `tools/m1_roundtrip.py` | 在 stock 树上来回 XML → TOML → XML，出一份 TSV 报告 |
| `tools/FirefightModPackager/` | vendored 的上游打包器 |

## 构建产物

没有构建步骤：核心是纯 Python，除标准库外无依赖，各交付面都以 `python -m` 从源码运行。

存在两种产物，都由构建系统之外的方式产生：

| 产物 | 产生方式 | 内容 |
| --- | --- | --- |
| 编辑器文件夹 | 把 `core/`、`docs/`、`launcher/` 复制到入口旁 | 同一份源码，另加 `Firefight/`、`Mod/` 与 `Setting.toml` |
| `&lt;名称&gt;-&lt;版本&gt;.zip` | `pack` | `Mod/`、`README.md`、`LICENSE`；`Mod/mod.txt` 由 `ModSetting.toml` 渲染，`Mod/Data/**` 的文档回写为原版 XML，其余逐字节复制 |

`pack` 以固定时间戳写入成员，因此同一工程两次打包得到相同字节，用例可以直接比较压缩包。

## 待完成

| 缺失 | 标记 |
| --- | --- |
| `vehicle` 与 `at_gun` 文档没有 schema，`set` 无法指定其字段，`add` 只能写裸根 | `core/schema.py` 的 `# TODO(m5)` |
| docs/project-layout.md 第 5 节的 stock 基线比对与 APK 打包 | `core/pack.py` 的 `# TODO(pack)` |
| 只有 TOML 的文档按规范形式回写，换行或缩进不同的源文件无法逐字节复现 | `core/pack.py` 的 `# KNOWN:` |

以下尚无标记：

* `init` 只写出 `ModInformation.toml` 与空的 `Data/`，不读模板、不导入原版数据。`import`（cli.md §4.16）
  是另一个方向：把已存在的模组——目录或 zip——变成工程。
* `Images/` 与 `Sounds/` 只在 `convert` 带 `assets=1` 时导入；指向它们的引用在导入或手工放置文件前一直是悬空引用。
* `Maps/`、`Surnames/` 与 `equipment_*` 清单不在 schema 范围内。
* 在某一个作用域内解析不到的引用不会再向原版语料回退；该回退已测量（某个真实工程
  912 条中 882 条可解析）但未实现。
* `batch` 能把一份补丁施加到多份文档，但补丁需手写，且每份文档仍按整份重写；没有交互式的多文档编辑器。
