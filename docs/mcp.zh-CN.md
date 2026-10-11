> 语言：**中文** | [English](mcp.md)

# AI MCP 交付面

本文档规定随编辑器仓库一起交付的 MCP 服务：交付面及其边界（§1）、传输与应答的协议修订（§2）、工具面与唯一来源（§3）、资源与提示（§4）、权限（§5）、错误映射（§6）、入口与客户端接线（§7）、验证方式（§8）、明确不做的事（§9）。由 [plan.md](plan.zh-CN.md) 的 S3、S4 阶段实现。

## 1. 交付面与边界

| 交付面 | 位置 | 到达编辑器的方式 | 用途 |
|---|---|---|---|
| 编辑器命令行 | 本仓库 `core/cli/` | 直接调用 | 脚本、人工、启动器 `.cmd` |
| DSH 插件 `dsh-firefight-mod-tools` | 另一仓库 | 以子进程 spawn 命令行 | DSH 内的日常智能体使用 |
| MCP 服务 | 本仓库 `core/mcp/` | 进程内调用 `run_command` | DSH 之外的 MCP 客户端，以及 DSH 通过 MCP 客户端条目接入 |
| 技能（`SKILL.md`） | 编辑器文件夹，不在本仓库 | 提示词层流程，可走上面任一面 | 可复用的智能体流程 |

**D12 —— 归属与形态。** MCP 服务属于编辑器仓库，放在 `core/mcp/`，入口为 `python -m core.mcp`。仅用标准库，讲 stdio JSON-RPC，进程内构造 `Context` 并调用 `core.cli.commands.run_command`，复用 `Result`，不 spawn 命令行：进程内调用使权限门、退出码语义与 JSON 负载同命令行完全一致。

**重叠规则。** 各交付面的工具名相同，因此同时装入 DSH 插件与 MCP 服务的客户端会出现重名工具。同一个 DSH 会话不要同时启用两者；文档里说明某流程按哪一个交付面工作。

## 2. 传输与协议修订

**D14 —— 修订。** 服务只走 stdio，并同时应答两个协议族，由第一个请求判定：

* **`initialize`**（2025-06-18 与 2025-11-25 修订）：经典握手，其后跟随 `notifications/initialized`；协商出的修订在 `initialize` 结果中回显。
* **`server/discover`**（2026-07-28 无状态修订）：无握手、无会话标识。每个请求的 `_meta` 携带 `io.modelcontextprotocol/protocolVersion`、`clientCapabilities` 与 `clientInfo`；每个结果携带 `_meta.serverInfo` 与显式 `resultType`（`"complete"`，需要补充输入时为 `"input_required"`）。版本不受支持时返回 `UnsupportedProtocolVersionError`（`-32022`）。

实现的子集：`tools`、`resources`、`prompts`。不实现、且以「方法不存在」如实应答而不是静默忽略：Streamable HTTP 与 SSE 传输、OAuth 或任何鉴权、`sampling`、`roots`、`logging`（上游已弃用）、任务、`subscriptions/listen`。真实客户端实际接受的修订属实测事实，记入 §8。

## 3. 工具面与唯一来源

**D13 —— 命名。** 工具名与 `dsh-firefight-mod-tools` `lib/specs.js` 中的插件表逐字相同，参数沿用插件的 camelCase 拼写，使同一提示词或技能可在各交付面之间迁移而无需改名。

| 工具 | 参数 | 是否写入 | 注册条件 |
|---|---|---|---|
| `ff_list` | `scope`、`selector`、`type`、`root`、`workspace` | 否 | 始终 |
| `ff_show` | `scope`、`selector`、`as`、`root`、`workspace` | 否 | 始终 |
| `ff_get` | `scope`、`selector`、`field`、`root`、`workspace` | 否 | 始终 |
| `ff_find` | `scope`、`selector`、`tag`、`value`、`path`、`ignoreCase`、`limit`、`root`、`workspace` | 否 | 始终 |
| `ff_stats` | `scope`、`selector`、`root`、`workspace` | 否 | 始终 |
| `ff_refs` | `scope`、`selector`、`kind`、`root`、`workspace` | 否 | 始终 |
| `ff_deps` | `scope`、`selector`、`kind`、`root`、`workspace` | 否 | 始终 |
| `ff_check` | `scope`、`selector`、`root`、`workspace` | 否 | 始终 |
| `ff_export` | `scope`、`selector`、`to`、`as`、`root`、`workspace` | 是 | 始终（导出是既有写入路径） |
| `ff_set` | `scope`、`selector`、`field`、`value`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write`（S4 阶段） |
| `ff_undo` | `scope`、`selector`、`count`、`root`、`workspace` | 是 | 仅 `--write`（S4 阶段） |

后续阶段按同一规则增加 `ff_add` 与 `ff_remove`。

**D16 —— 一份规格。** 命令行帮助、Web 界面与 MCP 工具表读取同一份 Python 规格表（候选 `core/cli/specs.py`），不再各写一份。快照测试断言 `tools/list` 的工具名、参数名与必填性与插件表一致，并断言只读模式下不出现写入工具。跨仓一致性由该测试与本文档保证，不引入共享构建。

## 4. 资源与提示

| 类型 | URI 或名称 | 内容 |
|---|---|---|
| 资源 | `firefight://{scope}/entity/{path}` | `path` 处的文档，渲染方式与 `ff_show` 相同 |
| 资源 | `firefight://{scope}/list/{category}` | 某个分类的实体路径，同 `ff_list` 返回的内容 |
| 资源 | `firefight://{scope}/log` | 工程作用域的事件日志分段，只读 |
| 提示 | `firefight-editor-workflow` | 编辑器文件夹 `skills/firefight-editor/SKILL.md` 中的流程：定位文档 → 读取 → 暂存改动 → 校验 → 确认 → 写入 → 复核 |

资源只读。不实现订阅（2026-07-28 已改为长连接 `subscriptions/listen`），客户端需要时重新读取资源。提示参数：`scope`、`selector` 与可选的 `goal`。

## 5. 权限与批准

**D15 —— 权限门。** 服务启动时只读；`--write` 使其进入 workspace-write 档。

* 只读服务：`tools/list` 中不含写入工具，直接调用写入工具按未知工具拒绝，不做静默降级。
* 启用写入的服务：写入限于工程目录内（`Mod/` 与 `.editor/`）。指向 `Firefight` 库存作用域的写入无条件拒绝；游戏安装目录永不被修改。
* 拒绝即终态。服务不重试、不在同一次调用里再次询问，并把拒绝如实报给调用方；fail-closed 行为与命令行一致。
* 每次写入追加一条事件日志记录，`actor` 为 `mcp`，使审计链能区分智能体写入与命令行写入。
* 逐动作批准属于客户端：MCP 协议没有批准原语。DSH 在每次写入前询问；其他客户端应自行对 `ff_set`/`ff_undo` 调用设门，服务的 `--write` 是第二道、服务端的门。
* 切到 `danger-full-access` 不在本计划范围内。

## 6. 错误映射

| 情形 | 应答 |
|---|---|
| JSON-RPC 信封格式错误 | `-32600` invalid request |
| 方法未知或工具名未知 | `-32601` method not found |
| 参数缺失或非法、资源不存在 | `-32602` invalid params（2026-07-28 把资源不存在从 `-32002` 移到这里） |
| 服务端意外故障 | `-32603` internal error |
| 权限门或作用域规则拒绝写入 | `-32000` |
| `.editor/lock` 被其他写者持有 | `-32001` |
| 暂存后文档被磁盘上改动 | `-32003` |
| 值无法用文档编码表示 | `-32004` |
| 值被 schema 拒绝 | `-32005` |

`-32000`–`-32019` 保留给实现自定义码；`-32020`–`-32099` 属规范码，不复用。命令自身抛出的错误（悬空引用、语法错误）属工具级失败：结果带 `isError: true`，负载保持命令行形状，含退出码（`0` 成功、`1` 命令失败、`2` 用法拒绝）。协议通道与工具通道因此可区分：客户端能分辨「调用失败」与「调用执行并报告了问题」。

## 7. 入口与分发

* 仓库内：`python -m core.mcp`（`core/mcp/__main__.py`），与 `core/cli` 形态一致。
* 编辑器文件夹（发行态，不是仓库）：与 `ff-ai.cmd`、`ff-web.cmd` 并列的 `ff-mcp.cmd`。它把参数转发给模块，除协议外不向 stdout 写任何内容，也不等待按键。
* DSH 接线使用 profile 的 MCP 客户端条目：`transport: stdio`、`serverName`、`command`（解释器）、`cwd`（编辑器文件夹）与 `args`（`-m core.mcp`，仅在需要写入时再加 `--write`）。
* 通用客户端在其自身配置块里填入同样三项：命令、工作目录、参数。不涉及网络监听、端口或 token。

## 8. 验证方式

1. **转录测试。** 测试套件以子进程启动服务，把脚本化的请求序列写入其 stdin，断言 stdout 的行：两个协议族的握手、`tools/list`、一次只读工具调用、一次被拒绝的写入、一次格式错误的请求。
2. **快照测试。** `tools/list` 的工具名、参数名与必填性等于 `dsh-firefight-mod-tools` `lib/specs.js`；工具名集合按精确相等断言，任一仓库改名都会让测试失败。
3. **只读模式。** `tools/list` 中不出现写入工具，直接调用写入工具被拒绝。
4. **fail-closed。** 被拒绝的写入不触碰文件、锁目录与事件日志。
5. **真实客户端手测。** 对真实 MCP 客户端手跑一次，记录被接受的协议修订与确切的启动配置。结果在 S3 落地时补入本节；在此之前被接受的修订属未验证。

## 9. 非目标

* 不做 HTTP 监听、SSE 传输、端口或 token；不做远程访问。
* 除 `--write` 之外不设鉴权或授权层。
* 不支持 sampling、roots、logging 与任务。
* 不支持资源订阅。
* 不把服务打成独立二进制；它随编辑器文件夹与内置 Python 运行时运行。
