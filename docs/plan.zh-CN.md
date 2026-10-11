> 语言：**中文** | [English](plan.md)

# 更新计划：先做 MVP 切片，再设计 AI MCP 交付面

本文档把 [firefight-editor-feature-list.md](m3-notes/firefight-editor-feature-list.zh-CN.md) §2 的待完成项排成顺序，并确定编辑器最先交付的最小完整编辑能力。S1–S9 是本文档内部的阶段编号；[project-layout.md](project-layout.zh-CN.md) §9 的里程碑表仍然定义 M0–M8 的含义，对应关系见 §3。

## 1. 目标与 MVP 定义

**D10 —— MVP 定义。** 最小完整功能是一条完整编辑闭环：读文档 → 改一个字段 → 校验 → 留痕 → 可撤销。该闭环必须在真实模组工程上成立，被改字段以外的内容按字节保持，事后可审计。不含打包、不含 Web 编辑面板、不含批量。折算到里程碑即 M4 的第一片：`set` + 事件日志 + `undo`。

**D11 —— 赋值写法。** 现有解析器把任何含 `=` 的 token 当作 `key=value` 选项（[core/cli/main.py](../core/cli/main.py) 的 `parse_argv`），而含 `=` 的选择器会被该规则吞掉（已知缺陷，功能清单 §2.4）。因此 MVP 沿用纯选项写法：

```
python -m core.cli Mod set <选择器> field=<点分路径> value=<值> [--dry-run] [--write]
```

[project-layout.md](project-layout.zh-CN.md) §6 中的内联写法（`set Infantry/"…" description.quality=QUALITY_ELITE`）不实现，它需要命令感知的解析器；实现阶段（S1）把 §6 的示例改写成上面的形式。

**本文档新增的裁决。** D10、D11 见上；D12–D16 见 [mcp.md](mcp.zh-CN.md) §2、§3、§5，并在本文档 §3 汇总。D1–D6 仍在 [project-layout.md](project-layout.zh-CN.md) §11，D7–D9 仍在 [firefight-editor-feature-list.md](m3-notes/firefight-editor-feature-list.zh-CN.md) §3。本文档不重开其中任何一条。

## 2. MVP 切片（S1 + S2 交付内容）

| 能力 | 细节 |
|---|---|
| `set` | 只改一个文档里一个实体的一个字段。寻址：选择器 = 文档路径，`field=` = 文档内的点分路径。 |
| `--dry-run` | 计算并报告结果；不写任何东西，包括不写日志记录。 |
| 写入保真 | 保持源文本的编码与行尾（16 个 UTF-8 文件保持 UTF-8，cp1252 保持 cp1252，CRLF 保持 CRLF，裸 LF 保持 LF）；注释、游离文本与未被触碰元素的排版保留；文档编码无法表示的新值硬失败并抛 `ExportEncodingError`，不写出文件。 |
| 原子写 | 在同目录写临时文件，再用 `os.replace` 覆盖原文件；不存在可见的半成品文件。 |
| 并发 | `.editor/lock`（O_EXCL，内含 pid 与时间戳）拒绝第二个写者，不做交错写；陈旧锁只报告，不静默删除。 |
| 外部改动防护 | 暂存时记录文件指纹，写入前复核；被编辑器之外改动的文件一律拒绝，不覆盖。 |
| 权限门 | 命令行默认只读；`set` 与 `undo` 需要 `--write`（workspace-write 档）。写入仅限工程目录内（`Mod/` 与 `.editor/`）；写入 `Firefight` 库存作用域无条件拒绝。拒绝即终态：不重试、fail-closed。 |
| 事件日志 | 每次写入在 `.editor/log/<分段起始本地时间>.jsonl` 追加一条记录，空闲 5 分钟封段（D4）：分段、时间戳、actor（`cli` 或 `mcp`）、文档、实体、字段、改动前值、改动后值、dry-run 标记、结果。 |
| 基线 | 每个被触碰文档的改动前镜像存入 `.editor/baseline/`，使 `undo` 还原字节而不是重新序列化的近似值。 |
| `log` | 列出分段与段内记录；只读。 |
| `undo` / `redo` | `undo N` 按逆序还原最近 N 次写入的改动前镜像；`redo N` 重新应用。保真判据：`undo` → `redo` → `undo` 后内容逐字节相同（sha256 相等）。 |
| `check` | 在改动后的工程上运行，不出现由本次编辑引入的新问题（引用一致性）。 |

MVP 之外：`add` / `remove`、批量编辑、重命名链、Web 编辑面板、工程导入导出、mod-zip 打包、发行。

## 3. 阶段

每个阶段是叠在前一阶段之上的一个 PR，自带测试与文档更新。S3–S6 不依赖 S7–S9，项目方如另有优先级可调整顺序。

| 阶段 | 内容 | 里程碑 | 依赖 |
|---|---|---|---|
| **S1** | `set` 引擎：寻址、按 schema 校验、保真写入器、原子写、锁、外部改动防护、权限门。暂不含日志。 | M4（第一片） | — |
| **S2** | 事件日志、`.editor/baseline/`、`log`、`undo`、`redo`。 | M4 | S1 |
| **S3** | MCP 服务与只读工具（`ff_list` … `ff_check`）、单源规格表、协议转录测试。 | M4/M7 辅助 | S1（仅为规格表） |
| **S4** | MCP 写入工具 `ff_set`、`ff_undo`，仅在服务以 `--write` 启动时注册。 | M4 | S3 |
| **S5** | Web 编辑面板：暂存、语义 diff 预览、逐次写入确认、权限指示、事件日志查看器。 | M7 | S2 |
| **S6** | `add` / `remove`（重复表按 index 寻址）、幂等、对选区批量改同一字段。 | M4 | S2 |
| **S7** | M5 工程文件：`mod.toml`、`mod_setting.toml`、引用缓存、工程导入导出。 | M5 | S2 |
| **S8** | M6 打包：mod-zip 内层 `Mod/`、外层 README/licence，在 `export Vehicles` 规模（599 文件）下文件夹 ↔ zip 往返无损。 | M6 | S7 |
| **S9** | M8 发行：版本、更新与安装说明、发行形态。 | M8 | S8 |

**S1。** 在 [core/cli/commands.py](../core/cli/commands.py) 增加命令，并新增复用 `_export_text`（[core/cli/commands.py](../core/cli/commands.py)）的写入器，使写入路径与导出路径逐字节一致。校验走 `core/schema.py`；枚举外的值在任何文件被触碰之前拒绝，退出码 2。验收：B1–B11、B17–B19，以及缩小规模的 B20。

**S2。** 日志记录按 JSONL 追加在 `.editor/log/` 下；分段文件名是 D4 格式的本地起始时间（`20261009T012000.jsonl`），因此文件名顺序即时间顺序。`undo` 逆序读日志，用同样的原子写还原记录的改动前镜像，并追加自己的记录，`actor` 与指向被还原记录的 `undone` 字段随附。验收：B12–B16。

**S3。** `core/mcp/` 是 stdio JSON-RPC 服务，直接 import 并进程内调用 `core.cli.commands.run_command`，不 spawn 命令行。工具、资源与提示见 [mcp.md](mcp.zh-CN.md)。快照测试断言 `tools/list` 的工具名与参数名集合等于 `dsh-firefight-mod-tools` `lib/specs.js` 中的插件表。验收：协议转录、快照、只读模式下不出现写入工具。

**S4。** 增加 `ff_set` 与 `ff_undo`；只有以 `--write` 启动的服务才把它们放进 `tools/list`。拒绝语义与命令行一致：不半写、不重试，返回给调用方的错误负载保留命令行退出码。

**S5。** 仅服务端渲染、无 JavaScript，遵循 [web.md](web.zh-CN.md) 的规则：按字段类型生成表单、由暂存文档计算 diff 视图、写入前确认一步。事件日志查看器展示分段、记录与基线对比。

**S6。** `add` / `remove` 按 index 寻址重复表；相同参数重复调用是空操作；批量编辑把一个字段应用到选区，每个文档产生一条日志记录。

**S7–S9。** 工程文件、打包与发行遵循 [project-layout.md](project-layout.zh-CN.md) §3–§5，本计划不改其定义。

## 4. 验收用例 B1–B20

| 编号 | 用例 | 期望 |
|---|---|---|
| B1 | 对工程 TOML 文档 `set` 一个字符串字段 | 只有该字段变化，文件其余部分逐字节相同 |
| B2 | `set` 一个枚举字段为 `enums_ext.txt` 中的合法值 | 接受；`check` 无新增问题 |
| B3 | `set` 一个枚举字段为非法值 | 就地拒绝，退出码 2，文件不变 |
| B4 | `set` 一个数值字段 | 按文档自身的数字写法写出；未触碰的兄弟节点保持排版 |
| B5 | `set` 一个布尔字段 | 同 B4，涉及 `true`/`false` |
| B6 | 在 cp1252 文档上 `set` | 被改字段以外的字节相同 |
| B7 | 在 UTF-8 文档上 `set` | 仍为 UTF-8 且无 BOM |
| B8 | 在 CRLF 文档与裸 LF 文档上 `set` | 两者行尾风格各自保留 |
| B9 | 在注释与游离文本旁 `set` | 注释与游离文本原样保留 |
| B10 | `set` 一个文档编码无法表示的值 | `ExportEncodingError`，退出码 1，不写出任何内容 |
| B11 | `--dry-run` | 不产生文件、锁文件与日志记录（mtime 与字节均不变） |
| B12 | 成功 `set` | `.editor/log/` 下恰好一条 JSONL 记录，段名符合 D4，各字段完整 |
| B13 | 一次 `set` 后 `undo 1` | 文档 sha256 等于编辑前的值 |
| B14 | `undo` → `redo` → `undo` | 每次结果逐字节相同 |
| B15 | 跨分段边界的 `undo N` | 按逆时间顺序还原，每次还原产生一条日志记录 |
| B16 | 改动引用字段的编辑 | `check` 保持干净，不引入悬空引用 |
| B17 | `.editor/lock` 被占用时的第二个写者 | 拒绝并报出锁持有者；不写入 |
| B18 | 暂存后文档被磁盘上改动 | 拒绝写入；磁盘上的改动保留 |
| B19 | 不带 `--write` 的 `set`，以及任何指向 `Firefight` 作用域的写入 | 拒绝，退出码 2，不写入，不写日志 |
| B20 | 对 599 文件工程的某一字段 `set` | 598 个文件逐字节相同，被编辑文件只有一处变化，`check` 干净 |

## 5. 风险、硬约束与假设

* **基线磁盘占用。** 逐事件保存改动前镜像会让 `.editor/baseline/` 随编辑次数线性增长。`.editor/` 随工程走、不进包、不入版本库（D5），增长是本地占用；以 599 文件工程为计量用例。若成为问题，退路是每分段一份基线而不是每事件一份。
* **redo 的字节精确性。** `redo` 规定为重新应用记录中的改动后镜像。B14 的判据是逐字节相等；若实现无法达到，本计划要求显式记录改动后镜像，而不是重新计算结果。
* **MCP 协议修订。** 真实客户端接受的修订尚未验证。D14 规定服务同时应答 `initialize` 握手（2025-06-18、2025-11-25）与 2026-07-28 无状态修订；实际被接受的修订在 S3 用真实客户端确认，结果记入 [mcp.md](mcp.zh-CN.md)。
* **游戏内验证。** B1–B20 中的用例无法在本环境于游戏内验证；16 个文档的 UTF-8 回退仍未在运行中的游戏里验证（功能清单 §2.4）。
* **沙箱限制。** 沙箱内 node `spawn` 是 EPERM，实机端到端用例在沙箱外运行；MCP 服务因此进程内调用 `run_command`，不 spawn 命令行（D12）。
* **无 CI。** 仓库没有工作流；每个 PR 的证据是本地 `python -m unittest discover -s tests -t .` 的结果加 diff 审阅。
* **假设。** 编辑保持单写者、交互式；多进程并发由拒绝处理（B17），不做合并。

## 6. 每阶段的完成定义

1. 命令或服务入口存在，英文注释只写职责、待办（`# TODO(<milestone>):`）与已知缺陷（`# KNOWN:`）。
2. 测试覆盖该阶段点名的验收用例；`python -m unittest discover -s tests -t .` 全绿，测试数记入 PR 正文。
3. 受影响文档的中英两份在同一 PR 内更新。
4. PR 正文记录实际执行的命令与观察到的结果。
5. 仓库内不出现绝对本地路径、用户名、凭据或机器特定值；写入路径限于工程目录内。
