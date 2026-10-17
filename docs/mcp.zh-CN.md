> 语言：**中文** | [English](mcp.md)

# AI MCP 交付面

本文档规定随编辑器仓库一起交付的 MCP 服务：交付面及其边界（§1）、传输与应答的协议修订（§2）、工具面与唯一来源（§3）、资源与提示（§4）、权限（§5）、错误映射（§6）、入口与客户端接线（§7）、验证方式（§8）、明确不做的事（§9）。服务在各自的实现 PR 中落地。

## 1. 交付面与边界

| 交付面 | 位置 | 到达编辑器的方式 | 用途 |
|---|---|---|---|
| 编辑器命令行 | 本仓库 `core/cli/` | 直接调用 | 脚本、人工、启动器 `.cmd` |
| DSH 插件 `dsh-firefight-mod-tools` | 另一仓库 | 以子进程 spawn 命令行 | DSH 内的日常智能体使用 |
| MCP 服务 | 本仓库 `core/mcp/` | 进程内调用 `run_command` | DSH 之外的 MCP 客户端，以及 DSH 通过 MCP 客户端条目接入 |
| 技能（`SKILL.md`） | 编辑器文件夹，不在本仓库 | 提示词层流程，可走上面任一面 | 可复用的智能体流程 |

**归属与形态。** MCP 服务属于编辑器仓库，放在 `core/mcp/`，入口为 `python -m core.mcp`。仅用标准库，讲 stdio JSON-RPC，进程内构造 `Context` 并调用 `core.cli.commands.run_command`，复用 `Result`，不 spawn 命令行：进程内调用使权限门、退出码语义与 JSON 负载同命令行完全一致。

**重叠规则。** 两个交付面注册的是同一批规范工具名，各自带自己的前缀：本服务应答 `mcp_<名字>`（`mcp_ff_list`），DSH 插件注册 `dsh_<名字>`（`dsh_ff_list`）。注册名不会冲突，因此同一个 DSH 会话可以同时启用两者；文档里说明某流程按哪一个交付面工作。

## 2. 传输与协议修订

**修订。** 服务只走 stdio，并同时应答两个协议族，由第一个请求判定：

* **`initialize`**（2025-06-18 与 2025-11-25 修订）：经典握手，其后跟随 `notifications/initialized`；协商出的修订在 `initialize` 结果中回显。
* **`server/discover`**（2026-07-28 无状态修订）：无握手、无会话标识。每个请求的 `_meta` 携带 `io.modelcontextprotocol/protocolVersion`、`clientCapabilities` 与 `clientInfo`；每个结果携带 `_meta.serverInfo` 与显式 `resultType`（`"complete"`，需要补充输入时为 `"input_required"`）。版本不受支持时返回 `UnsupportedProtocolVersionError`（`-32022`）。

实现的子集：`tools`、`resources`、`prompts`。不实现、且以「方法不存在」如实应答而不是静默忽略：Streamable HTTP 与 SSE 传输、OAuth 或任何鉴权、`sampling`、`roots`、`logging`（上游已弃用）、任务、`subscriptions/listen`。真实客户端实际接受的修订属实测事实，记入 §8。

## 3. 工具面与唯一来源

**命名。** 规范工具名与 `dsh-firefight-mod-tools` `lib/specs.js` 中的插件表逐字相同，参数沿用插件的 camelCase 拼写，使同一提示词或技能可在各交付面之间迁移而无需改名。各交付面把该名字放在自己的前缀之后（§1）；下表列出本服务应答的名字。

| 工具 | 参数 | 是否写入 | 注册条件 |
|---|---|---|---|
| `mcp_ff_list` | `scope`、`selector`、`type`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_show` | `scope`、`selector`、`as`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_get` | `scope`、`selector`、`field`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_find` | `scope`、`selector`、`tag`、`value`、`path`、`ignoreCase`、`limit`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_stats` | `scope`、`selector`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_refs` | `scope`、`selector`、`kind`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_deps` | `scope`、`value`、`kind`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_check` | `scope`、`selector`、`assets`、`rosters`、`against`、`limit`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_schema` | `scope`、`element`、`enum`、`limit`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_diff` | `scope`、`left`、`right`、`limit`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_verify` | `scope`、`selector`、`limit`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_audit` | `scope`、`root`、`workspace` | 否 | 始终 |
| `mcp_ff_export` | `scope`、`selector`、`to`、`overwrite`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_set` | `scope`、`selector`、`field`、`value`、`op`、`from`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_add` | `scope`、`selector`、`type`、`from`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_remove` | `scope`、`selector`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_index` | `scope`、`selector`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_convert` | `scope`、`selector`、`to`、`overwrite`、`assets`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_settings` | `scope`、`op`、`overwrite`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_undo` | `scope`、`count`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_redo` | `scope`、`count`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_init` | `scope`、`name`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_pack` | `scope`、`to`、`overwrite`、`strict`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_batch` | `scope`、`patch`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_clone` | `scope`、`source`、`as`、`into`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_roster` | `scope`、`roster`、`op`、`section`、`value`、`line`、`as`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_import` | `scope`、`source`、`to`、`overwrite`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_build` | `scope`、`to`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_adopt` | `scope`、`source`、`to`、`overwrite`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_unpack` | `scope`、`to`、`overwrite`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |
| `mcp_ff_run` | `scope`、`steps`、`dryRun`、`root`、`workspace` | 是 | 仅 `--write` |

凡命令会写文件的工具都只在 `--write` 下注册，`mcp_ff_export` 亦然：命令行的 `export` 因为目标目录是显式选项而不需要标志，但一个自称只读的服务不得暴露会写入的工具。每个写入工具都接受 `dryRun` 参数，映射到命令行的 `--dry-run`，因此写入可以在发生之前先检视；`mcp_ff_roster` 只在给出 `op` 时写入，不给则只读。

`mcp_ff_settings` 承载工程原版设置文件的两个方向：`op=render` 读 `<工程>/mod.txt` 写 `ModSetting.toml`，`op=emit` 反向写回原版文件（docs/cli.zh-CN.md §4.7）。

`mcp_ff_init` 在还不是工程的目录里建工程，`mcp_ff_pack` 生成可安装的模组 zip（docs/cli.zh-CN.md §4.9、§4.8）。`mcp_ff_import` 由既有模组建工程，`mcp_ff_clone` 以新 token 复制一份文档（§4.16、§4.12），`mcp_ff_batch` 用补丁文件一次改多份文档（§4.15）。

`mcp_ff_check` 承载 docs/cli.zh-CN.md §6 描述的三道门：`assets` 给出缺失图片或声音本该落在的文件，`rosters` 把清单比对折进同一张表与同一个退出码，`against` 用第二个根库回答引用。`mcp_ff_schema`、`mcp_ff_diff`、`mcp_ff_verify` 只读，从不写入（docs/cli.zh-CN.md §4.13、§4.10、§4.11）。

**一份规格。** 工具表是唯一的 Python 规格表 `core/cli/specs.py`：MCP 服务据它渲染 `tools/list`，并把一次调用转成命令行调用；插件的 `lib/specs.js` 是它的跨仓对应物。快照测试断言 `tools/list` 的工具名、参数名与必填性与插件表一致，并断言只读模式下不出现写入工具。插件在编辑功能定稿后一次性同步，因此它的表有意落后于这一张：测试点名它尚缺的工具，凡是它已有的名字都必须一致。跨仓一致性由该测试与本文档保证，不引入共享构建。让命令行帮助与 Web 界面也读取同一张表属于后续工作：命令行列的是命令而不是工具，Web 界面按命令生成表单。

## 4. 资源与提示

| 类型 | URI 或名称 | 内容 |
|---|---|---|
| 资源 | `firefight://{scope}/entity/{path}` | `path` 处的文档，渲染方式与 `mcp_ff_show` 相同 |
| 资源 | `firefight://{scope}/list/{category}` | 某个分类的实体路径，同 `mcp_ff_list` 返回的内容 |
| 资源 | `firefight://{scope}/log` | 工程作用域的事件日志分段，只读 |
| 提示 | `firefight-editor-workflow` | 编辑器文件夹 `skills/firefight-editor/SKILL.md` 中的流程：定位文档 → 读取 → 暂存改动 → 校验 → 确认 → 写入 → 复核 |

资源只读。不实现订阅（2026-07-28 已改为长连接 `subscriptions/listen`），客户端需要时重新读取资源。提示参数：`scope`、`selector` 与可选的 `goal`。资源 URI 只带作用域名、不带根目录，因此服务工作目录解析不出的作用域——通常是原版游戏安装目录——必须在启动时用 `root=<目录>` 或 `firefight=<目录>` 给出；工具调用仍可按次覆盖。

## 5. 权限与批准

**权限门。** 服务启动时只读；`--write` 使其进入 workspace-write 档。

* 只读服务：`tools/list` 中不含写入工具，直接调用写入工具按未知工具拒绝，不做静默降级。
* 启用写入的服务：写入限于工程目录内（`Data/`、`Images/`、`Sounds/` 与 `EditorCache/`）。指向 `Firefight` 库存作用域的写入无条件拒绝；游戏安装目录永不被修改。
* 拒绝即终态。服务不重试、不在同一次调用里再次询问，并把拒绝如实报给调用方；fail-closed 行为与命令行一致。
* 每次写入追加一条事件日志记录，`actor` 为 `mcp`，使审计链能区分智能体写入与命令行写入。
* 逐动作批准属于客户端：MCP 协议没有批准原语。DSH 在每次写入前询问；其他客户端应自行对 `mcp_ff_set`/`mcp_ff_undo` 调用设门，服务的 `--write` 是第二道、服务端的门。
* 切到 `danger-full-access` 不在本计划范围内。

## 6. 错误映射

| 情形 | 应答 |
|---|---|
| JSON-RPC 信封格式错误 | `-32600` invalid request |
| 方法未知或工具名未知 | `-32601` method not found |
| 参数缺失或非法、资源不存在 | `-32602` invalid params（2026-07-28 把资源不存在从 `-32002` 移到这里） |
| 服务端意外故障 | `-32603` internal error |
| 权限门或作用域规则拒绝写入 | `-32000` |
| `EditorCache/lock` 被其他写者持有 | `-32001` |
| 暂存后文档被磁盘上改动 | `-32003` |
| 值无法用文档编码表示 | `-32004` |
| 值被 schema 拒绝 | `-32005` |

`-32000`–`-32019` 保留给实现自定义码；`-32020`–`-32099` 属规范码，不复用。四个写入拒绝码——`-32001` 锁被持有、`-32003` 暂存后文档被改动、`-32004` 值无法表示、`-32005` 值被 schema 拒绝——随写入工具一并落地，因为只有这些调用会抛出它们；`-32000` 已经实现，因为作用域规则同样适用于 `mcp_ff_export`。命令自身抛出的错误（悬空引用、语法错误）属工具级失败：结果带 `isError: true`，负载保持命令行形状，含退出码（`0` 成功、`1` 命令失败、`2` 用法拒绝）。协议通道与工具通道因此可区分：客户端能分辨「调用失败」与「调用执行并报告了问题」。

## 7. 入口与分发

* 仓库内：`python -m core.mcp`（`core/mcp/__main__.py`），与 `core/cli` 形态一致。它接受 `--write` 以暴露写入工具，并接受 `workspace=<目录>`、`root=<目录>` 与 `firefight=<目录>` 作为每次工具调用与资源读取默认继承的值；单次调用可以覆盖前两者。
* 编辑器文件夹（发行态，不是仓库）：与 `StartWebUI.cmd`、`StartWebUI(Basic).cmd` 并列的 `Start(McpOnly).cmd`。它把参数转发给模块，除协议外不向 stdout 写任何内容，也不等待按键。
* DSH 接线使用 profile 的 MCP 客户端条目：`transport: stdio`、`serverName`、`command`（解释器）、`cwd`（编辑器文件夹）与 `args`（`-m core.mcp`，仅在需要写入时再加 `--write`）。
* 通用客户端在其自身配置块里填入同样三项：命令、工作目录、参数。不涉及网络监听、端口或 token。

## 8. 验证方式

1. **转录测试。** 测试套件以子进程启动服务，把脚本化的请求序列写入其 stdin，断言 stdout 的行：经典握手（中间夹 `notifications/initialized`）、无状态的 `server/discover` 族、`tools/list`、一次只读工具调用、一次被拒绝的写入、一行格式错误的内容与一个不支持的协议修订。
2. **快照测试。** `tools/list` 的工具名、参数名与必填性等于 `dsh-firefight-mod-tools` `lib/specs.js`；工具名集合在编辑器仓库内也按精确相等断言，任一仓库改名都会让测试失败。该跨仓比较在找不到该检出时跳过（可用 `FIREFIGHT_PLUGIN_SPECS` 指向其 `lib/specs.js`）。
3. **只读模式。** `tools/list` 中不出现写入工具，直接调用写入工具按未知工具拒绝。
4. **fail-closed。** 被拒绝的写入不触碰文件、锁目录与事件日志。该用例目前对 `mcp_ff_export` 验证：库存作用域与其目标目录均未被改动；锁与事件日志两个用例随写入工具落地。
5. **真实客户端手测。** 对真实 MCP 客户端手跑一次，记录被接受的协议修订与确切的启动配置。该次实测完成后结果补入本节；在此之前被接受的修订属未验证。

编辑器仓库内已实测：`tests/test_mcp.py` 的 18 个用例，覆盖两个协议族、精确的工具集、`--write` 注册、库存作用域拒绝、带命令行退出码的工具级失败形状、资源、提示、命令行选项与插件快照（跨仓那一半在 `ffplugin/lib/specs.js` 可达时真跑）。

## 9. 非目标

* 不做 HTTP 监听、SSE 传输、端口或 token；不做远程访问。
* 除 `--write` 之外不设鉴权或授权层。
* 不支持 sampling、roots、logging 与任务。
* 不支持资源订阅。
* 不把服务打成独立二进制；它随编辑器文件夹与内置 Python 运行时运行。
