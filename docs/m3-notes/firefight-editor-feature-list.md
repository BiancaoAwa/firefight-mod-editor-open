# Firefight 模组编辑器 —— 功能清单（已完成 / 待完成）

> 状态快照：2026-10-11（仓库 / 发行版布局定型后更新）。本文件是工作笔记，放在 `m3-cli\docs\m3-notes\`（**未跟踪**，不随仓库发布）。
> 现状一句话：**只读的查询层已经完全能用，并且有能在浏览器里点的界面了**（CLI + DSH 插件 + 一键启动器 + 本地 Web UI），**写数据的能力一点都还没有**。

---

## 0. 交付面（四个部件）

| 部件 | 位置 | 状态 |
|---|---|---|
| 编辑器 CLI | 仓库 `BiancaoAwa/firefight-mod-editor-open`；本地工作树 `firefight-mod-editor-open\m3-cli`（入口 `m3-cli\ff.py`，代码在 `m3-cli\core\`） | 可用（只读 + export） |
| 本地 Web UI | 同一工作树 `firefight-mod-editor-open\m3-cli\core\web\`（`ff.py <scope> web`） | 可用（只读浏览，零 JS，230 条测试全过） |
| DSH 插件 | `firefight-mod-editor-open\ffplugin` → 仓库 `BiancaoAwa/dsh-firefight-mod-tools` | 本地 0.1.1 可用；远端仍是 0.1.0 `bc183fc` |
| 一键启动器 | `firefight-mod-editor-open\m3-cli\tools\launcher\`（`ff-tool.ps1` / `ff-tool.cmd` / `ff-start.cmd` / `ff-stop.cmd` / `ff-web.cmd`），发行版里是 `dist\launcher\`（junction） | 可用；脚本按布局自适应（仓库 `..\..\ff.py` / 发行版 `..\ff.py`） |
| AI 接口（无 UI） | `dist\ff-ai.cmd`（转发给同目录 `ff.py`，退出码 = CLI 退出码）+ `dist\skills\firefight-editor\SKILL.md` | 新增（2026-10-11） |
| 仓库结构 | `m3-cli\` 顶层 = `core\ docs\ tests\ tools\ ff.py README.md LICENSE`（**与 GitHub 一致**）；CLI/Web 在 `core\cli\`、`core\web\`，启动器实现在 `tools\launcher\` | 2026-10-11 第四批重整（用户裁决「仓库与 GitHub 对齐」） |
| 工作区布局 | `firefight-mod-editor-open\README.md` —— 顶层 = `m3-cli\`(仓库工作树) `dist\`(发行版形状的测试文件夹) `ffplugin\` `_out\` `README.md` | 2026-10-11 整理（辅助物全部并入仓库的 `tools\ docs\ tests\`） |
| 发行版形状测试文件夹 | `dist\`：`ff-web.cmd` `ff-ai.cmd` `ff.py` + `core\ docs\ launcher\`（junction 指向 `m3-cli`，不复制、不漂移）+ `skills\` + `.ff-editor.local.toml` + `Firefight\` + `Mods\{WW3, sample-mod}\` | `Firefight` 作用域实跑走 `editor copy` 分支、`Mod` 走 config 分支；形态与缓存都记在 `docs\project-layout.md` §12 |
| 游戏数据副本 | `dist\Firefight\Data\|Images\|Sounds\`（1840 文件，对 stock 逐字节 0 mismatch） | 原 `export-fidelity` → 原 `stock\`，现挂在发行版形状里 |
| 模组工程 | `dist\Mods\WW3\`（§2 形状：`mod.toml` + `mod_setting.toml`（部分，等 M5 渲染器）+ `Mod\{Data,Images,Sounds}` + README/LICENSE + `.editor\{refs,index}.toml`）、`dist\Mods\sample-mod\`（TOML 实体 + stock 原文 + 全默认 `mod_setting.toml`） | 原 `projects\`；WW3 工程 765 文件 / 1329766 B / 13 列表 |

---

## 1. 已完成

### 1.1 编辑器 CLI（里程碑 M0–M3）

- **入口与形态**：`ff.py <scope> <命令> [选择器] [键=值 …] [--json]`；scope = `Firefight`（原版数据）/ `Mod`（有 `mod.toml` 的工程）/ 其他模组文件夹名。退出码：`0` 成功、`1` 已执行的失败（JSON 载荷通常仍有效）、`2` 用法错误。
- **11 个命令**：`list` `show` `get` `find` `stats` `refs` `deps` `check` `export` `web` `version`（别名 `ls`→list、`cat`→show）。除 `export` 外**全部只读**。
- **目录扫描与分类**：原版数据 1840 文件 / 4003531 字节 / 48 个列表；分类 weapon 716、vehicle 599、infantry 307、at_gun 111、aircraft 59、surnames 36、equipment 12。
- **格式与保真读取**：自研特化 TOML（不引 tomlkit）；XML/TXT 双格式；`show` 支持 `raw` / `toml` / `xml` 三种视图并回报警告。
- **读取健壮性**：UTF-8 优先 + cp1252 回退（原版里有 16 个 UTF-8 武器文件，注释带中文）；重复单例表（`squad/vehicle/hull/man/ammo` 同父下出现两次）降级为数组 + 警告，不再报错；`//` 注释与游离文本被识别并警告而不是静默丢弃。
- **交叉引用**：`refs`（本实体指向谁）、`deps`（谁引用我，含 `kind` 过滤与解析结果/未解析标志）。例：`WEAPON_PISTOL_P38` 有 1204 条传入引用。
- **工程体检**：`check` → 加载/跳过/错误/警告总数/警告文件/悬空引用，单文件与整 scope 都行。
- **导出（逐字节对齐原版，2026-10-11 完成）**：`export <选择器> to=<目录>`，按 `Data/...` 原树写 XML；**原先只保证语义等价（D7），现在对有来源文本的文件逐字节复现原版** —— 兄弟顺序按文档出现顺序、空行/缩进/`//` 注释/文件自身换行风格全部保留。实测原版数据 **1840 / 1840 文件完全一致**（`tools\export_fidelity.py` 闸门，有差异即非零退出）；改动前是「顺序变 1792、换行变 12、完全一致 36」。`export Vehicles` = 599 文件 / 2371815 字节 / 0 错误；同一导出连跑 sha256 一致（确定性）；只在 `to=` 下写，不碰源数据。
- **枚举**：复用 `enums_ext.txt`，不重建 13.2.0.0 枚举，未知枚举只警告。
- **工程与文档**：`docs\cli.md`（含只读声明）、`docs\project-layout.md`（里程碑与 D1–D9 裁决）、`tests\` 单测、`tools\` 脚本；WW3 真实模组工程冒烟通过。
- **版本**：editor 0.1.0 / python 3.12.14。

### 1.2 DSH 插件 `dsh-firefight-mod-tools`

- **9 个工具**：`ff_list` `ff_show` `ff_get` `ff_find` `ff_stats` `ff_refs` `ff_deps` `ff_check`（8 个只读、并发安全）+ `ff_export`（仅当 `enableExport: true` 才注册，且经 `tools/pre-execute` 逐次审批）。
- **工程化**：Schemastery 配置（`pythonPath` / `editorRoot` / `scriptPath` / `firefightRoot` / `workspace` / `cwd` / `timeoutMs` / `maxOutputChars` / `enableExport`）；`cordis.patch.yml` 整行覆盖；payload 与错误值两个 schema 分支互斥（判别式字段钉死 exactly-one-oneOf）。
- **已装入本机 DSH**：`C:\Users\BC_aw\.dsh\profiles\desktop` 的 `package.json`（link 依赖 + bundles 列表）与 `cordis.patch.yml`（config 九键，`enableExport: false`）；重启后已确认 8 个 `ff_*` 出现在模型工具目录、实际调用返回正确数据（stats 1840/4003531/48、deps 1204）。
- **验证强度**：替身宿主 59 条测试（55 通过 / 4 条诚实跳过）、真实宿主 bundle 59/59、端到端校验 318/318、真实 payload 与错误值全部通过真实 `defineTool` 编译与校验；审批门 27 条绕过尝试 0 成功。
- **本地版本 0.1.1 相对远端 0.1.0 的修正**：oneOf 判别式修复（F1，原先错误值被真实 registry 拒收）、`node --test` 目录参数修正、README 的 ff.py 位置/`ff_find` selector/100 行上限等描述修正、`cordis.patch.yml` 补 `cwd`、timeout 文案修到位。

### 1.3 一键启动器

- **动作**：`start` / `stop` / `restart` / `status` / `run` / `web` / `help`；`-Quick`（跳过原版扫描）、`-KeepOutput`、`-Project`、`-Python`、`-Cli`、`-Root`、`-WorkDir`、`web -Window`（Web UI：服务后台隐藏运行，页面开在独立 app 窗口）、`-NoBrowser`、`-Browser`（强制用普通浏览器窗口）、`-Port <n>`，也可用环境变量 `FF_PYTHON`/`FF_CLI`/`FF_ROOT`/`FF_PROJECT`/`FF_WORK`/`FF_PORT` 覆盖。
- **窗口内快捷**：`ff <CLI 参数>`、`ff-start`、`stop`、`restart`、`status`、`web`（本窗口起 Web UI）、`web-open`（同上：后台起服务 + 独立 app 窗口）、`ff-help`（`start` 归 PowerShell 自己的 `Start-Process` 别名，故重启是 `ff-start`）。
- **防呆**：`Firefight` 作用域自动补 `root=<真实游戏目录>`；`键=<...>` 占位符直接拦下并给出可执行提示；横幅与帮助里不再出现假路径；`web -Window` 先探端口，被占就报 `port … is already in use … (pid …)` 并给「页面退出 / `stop` / 换端口」三条出路，绝不劫持别人的服务。
- **可运维**：日志 `logs\tool-yyyyMMdd.log`、`state.json`、`web.json`（服务进程 pid、端口、作用域、日志路径、app 窗口 pid/profile、watchdog pid、调试端口）、`out\`；`status` 会汇报 Web UI 是「正在监听（pid + 日志 + watchdog）/ 端口没响应（陈旧状态）」，并给出 `last session`（最近一次退出的核对结论）；`stop` 会结束 Web UI 进程（按命令行的 `ff.py … web` 匹配，WMI 不可用时回退按进程名，最后再用 `web.json` 里的 pid 兜底）+ 等 watchdog 收尾（最多 10 秒）+ 关掉它开的窗口并删临时 profile + 清掉残留的 `ff.py` 进程与中间产物（日志保留）；双击 `ff-tool.cmd` 进 `-NoExit` 窗口；`web -Window` 不留任何控制台窗口（服务是隐藏的 `python ff.py … web`，输出重定向到 `logs\web-<port>-{out,err}.log`），所以停 Web UI 只有两招：页面「退出」或 `stop`。
- 本机是 Windows PowerShell 5.1（`pwsh` 未安装），脚本按 5.1 兼容编写。
- **双击入口必须纯 ASCII（2026-10-11 修，用户报「`ff-web.cmd` 打不开了」）**：`cmd.exe` 按 **OEM 代码页**（本机 cp936）读 `.cmd`，`ff-web.cmd` 的 `rem` 里带了 `(退出)` 这 6 个 UTF-8 字节，双击时整段脚本被解析坏掉——启动器的横幅、日志、`web.json` 一个都不出现，进程就挂着（表现就是「点了没反应」）。改成 `(the quit link there)` 后恢复正常：横幅、`listening`、`page opened in its own window`、`window up, watched through its profile lock`、watchdog、`web.json` 全部出现（实测 `ff-web.cmd` 只用了十几秒就返回）。四个 `.cmd`（`ff-tool`/`ff-start`/`ff-stop`/`ff-web`）现已全部 0 个非 ASCII 字节，并在文件顶部写了这条规则；`ff-tool.cmd` 同时改成延迟展开 `!ERRORLEVEL!`（原来在括号块里 `%ERRORLEVEL%` 是解析期展开，打印的是旧值）。`.ps1` 不受影响（PowerShell 认 UTF-8 BOM，启动器始终保留 `EF BB BF`）。
- **双击入口默认单开窗口 + 退出监听（2026-10-11 修，用户报「web 是单开一个窗口 / 退出监听似乎没生效」）**：根因是发行版 `dist\ff-web.cmd` 默认走 `:run` 分支 —— 直接前台跑 `ff.py <scope> web port=… browser=1`，页面开在**普通浏览器标签**里、进程占着控制台、**没有 watchdog**，所以既不是独立窗口也没有退出监听（`m3-cli\tools\launcher\ff-web.cmd` 第 19 行本来就是 `web -Window`，两处入口不一致）。现在 `dist\ff-web.cmd` 是薄封装：默认 `launcher\ff-tool.ps1 web -Window -Scope <名字>`（后台服务 + 独立 app 窗口 + watchdog），`-Foreground` 才退回原来的前台直连路径，`-Browser`/`-NoBrowser`/`-Port <n>` 照旧透传。启动器同时新增 `-Scope`（`FF_SCOPE`）与 `Get-WebScope`/`Get-WebRootArgs`/`Get-WebRootText`：作用域按 `-Project` → `-Scope` → `Firefight` 取，`root=` 只在原版作用域或显式 `-Project` 时补，命名作用域交给 CLI 自己解析。实测：`dist\ff-web.cmd -Port 9051 -NoBrowser` → `scope Mod` / `root (resolved by the editor config)` / `listening http://127.0.0.1:9051/ (pid 26084)` / `watchdog pid 29008` / `web.json` 写入（scope=Mod、root 空），首页 200、`/quit?do=1` 200、状态文件与端口都清掉、exit log `… :: the server stopped :: graceful True :: backend exited normally`；`-Scope Firefight -Port 9061` → `root D:\Program Files (x86)\Steam\steamapps\common\Firefight`，同样干净退出。

### 1.4 本地 Web UI（M7 的浏览部分，只读）

- **跑法**：`ff.py <scope> web [port=8765] [token=…] [pagesize=200] [browser=1]`；启动器里是 `ff-tool.cmd web`（本窗口）、`ff-tool.cmd web -Window` 或窗口内敲 `web-open`（本窗口的提示符立刻回来），双击 `ff-web.cmd` 也行。`-Window` 不留控制台窗口：服务由 `Start-Process -WindowStyle Hidden` 直接起（`python ff.py <scope> web root=… port=…`），stdout/stderr 重定向到 `logs\web-<端口>-out.log` / `-err.log`（`stop` 不删，`out\` 才删）。`-Window` 默认把页面开在**独立的 Chromium app 窗口**里（`msedge --app=<url>`：没有标签栏和地址栏，看起来就是个独立窗口，不是浏览器），`-Browser` 改用普通浏览器窗口，`-NoBrowser` 什么都不开。绑 `127.0.0.1`、单请求串行，启动横幅打印地址，每个请求打到 stderr。
- **退出**：每页顶栏都有「退出」链接 → `/quit` 先给确认页（零 JS 下链接可能被预取，所以点第二次才真停）→ 确认按钮真的停掉服务并回「已退出」；只结束本地服务进程，不写任何数据文件。等价命令行是 `stop`（前台模式 `ff-tool.cmd web` 里还可以 Ctrl-C；`-Window` 后台模式下没有窗口可按，只有页面「退出」和 `stop`）。
  - **2026-10-11 加：退出后自动收尾（你要求「webui点击退出后，检查后端有没有正常退出，随后它也退出」）**：后台会话多一个隐藏 **watchdog**。服务一停（页面「退出」/`stop`/Ctrl-C/崩溃），它先核对**后端是否正常退出**（进程已消失 + 端口释放 + 日志里有那条优雅退出标记 `web: stopped by the quit link`），然后关掉它开的那扇 app 窗口、删掉那扇窗口的临时浏览器 profile、自己退出；结论追加到 `logs\web-<端口>-exit.log`，`status` 里显示成 `last session …`。实测（端口 8891，同一次调用内完成）：页面抓取 `200` → 页面「退出」`200` → 服务进程 / watchdog / 窗口全部消失、临时 profile 删除、msedge 进程数 5→4 → exit log 为 `… :: the server stopped :: graceful True :: page window closed, 1 process(es) :: backend exited normally`。用 `stop` 停是同一条链，但日志如实写 `graceful False … (killed?)`，因为 `stop` 是直接结束进程而不是请它退。
  - **反向逻辑（先关窗口 → 自动停服务）已实现（2026-10-11，用户要求「把反向逻辑做一下」）**：活体信号取自那扇 app 窗口的 **profile 锁**（`--user-data-dir` 下浏览器持有的 `lockfile`，窗口活着它就锁着；这是唯一能扛住「浏览器把窗口交给另一个进程」的信号 —— 实测按进程 pid 和按 msedge 数量判断都会说谎）。连续三次（约 5 秒）判死才认为窗口关了，然后用 `/quit?do=1` 礼貌停服（所以 exit log 仍记 `graceful True … backend exited normally`），而不是留一个没人看的后台服务。启动器会等这把锁最多 15 秒，确认窗口起来了才叫「已监视」（打印 `window up, watched through its profile lock`）；15 秒没起来就明说 `did not show up in 15 s - the server is not watched` 并把会话降级为不监视，绝不做半监视。`-Browser`（用户自己的浏览器标签）与 `-NoBrowser` 都不做反向。实测（8911）：窗口开着 12 秒无假警报；手动关掉窗口后 watchdog 自行触发 → exit log `… :: the page window was closed first :: graceful True :: page window was already gone :: backend exited normally`，临时 profile 删除、端口释放。
  - **端口占用是真拒绝（2026-10-11 修）**：`HTTPServer` 默认开 `SO_REUSEADDR`，Windows 上**允许第二个进程再绑同一端口并成功**（实测把服务放在 8931 后，直接跑 `ff.py Firefight web port=8931` 竟然打印横幅并开始服务，两个 UI 会抢同一端口）。现在 `web\server.py` 的 `make_server` 先 `socket.connect_ex` 探一下端口，占用就抛 `cannot listen on 127.0.0.1:<port>: the port is already in use`（`port=0` 永远可用，测试就用它）；启动器侧的预探测照旧。
  - **`stop` 不误杀复用的 pid（2026-10-11 修）**：状态文件里的 pid 在进程退出后会被系统复用，`stop` 现在先核对进程名（python / `powershell|pwsh` / `msedge|chrome`），不匹配就打印 `pid N is … - a reused pid, leaving it alone` 并跳过。实测：把 `web.json` 的 pid/page/watchdog 全指向一个 `cmd.exe` 旁观进程 → 三条都是「reused pid, leaving it alone」，旁观进程存活，状态文件正常清理。
  - **2026-10-11 修：Web 服务改成多线程**（`web\server.py` 从 `HTTPServer` 改为 `ThreadingHTTPServer`，daemon 线程 + 关闭时不等连接）。原因：浏览器会开空闲的预连接，单线程服务会卡在那条连接上读请求行，后面所有请求排队 —— 表现就是页面像卡死（我发退出请求时真撞上了，一直挂住）。
  - 2026-10-11 修：确认页原来是个 `GET` 表单、`do=1` 写在 `action` 的查询串里，而**浏览器提交 GET 表单时会丢掉 action 自己的查询串**，于是点确认只会回到确认页（「退出没用」）。现在 `pages.form` 把 action 里的 `scope`/`t` 等参数改写成隐藏输入、action 只留路径，`do=1` 也作为隐藏输入提交。顺带修掉同一根因的另一个坑：`scope=Mod` 的工程里提交查找/字段表单会被静默当成原版数据（配了 `token=` 时所有表单直接 400）。
- **页面**：首页（scope/根目录/计数）· 实体列表（按分类与路径过滤 + 翻页）· 实体详情（`toml`/`xml`/`raw` 三视图 + 双向引用）· 读取字段 · 查找（tag/value/path/忽略大小写）· 引用（本文件指向谁）· 反查（谁引用我，含解析结果）· 体检（错误/警告/悬空引用）· 统计 · 命令行 · 帮助 · 退出 · `/json?...` 原始载荷。每页都显示等价命令行并链到自己的 JSON。

- **命令行页 `/cmd`（2026-10-11 加，用户要求「把 web 里面也加上命令行」）**：一个输入框，写 `ff` 后面的内容即可（`list weapon`、`stats`、`deps value=WEAPON_PISTOL_P38`、`show "Data/Weapons/WEAPON_PISTOL_P38.txt" as=toml`），可以在最前面写作用域名，路径带空格用双引号；勾「JSON 输出」就是 `--json`。走的是**同一套 argparse 与命令处理器**（`cli.main.parse_argv` + `App.call`），页面直接把 `Result.text` 放进 `<pre>`，所以输出与 CLI 完全一致（有测试逐字比对），下面再给作用域/命令/选择器/选项/退出码/耗时，以及等价命令行、原始 JSON、按 JSON 重跑三个链接。**只读保证**：`export`（写文件）与 `web`（会再绑一个端口）连同别名 `emit`/`serve` 在 `/cmd` 与 `/json` 上一律 400「不可用」，顺带堵住了此前 `/json?command=export&to=…` 能写盘的缺口。真数据实测：`stats` → 1840、`deps value=WEAPON_PISTOL_P38` → 1204、带引号的 `show` 正常、未知命令 400「没有这个命令」。
- **形态**：纯 Python 标准库 `http.server`，**零新依赖、零构建、零 JavaScript、零外部资源、零 cookie**，老式服务端渲染 HTML（内联一套朴素灰色 CSS）。
- **正确性保证**：页面在**同一进程内调用同一批命令处理器**，因此与 `ff --json` 不可能漂移（有测试对拍）；`/json` 路由直接给原始载荷。
- **安全与边界**：只绑回环、只支持 GET（POST/PUT/DELETE/PATCH→501 且先排空请求体，避免 RST）、全程转义（有 XSS 用例）、选择器拒绝绝对路径/盘符/`..`（4 条穿越用例全 400）、`token=` 门（缺 token→400，链接自动带 `?t=`）、行数按 `pagesize` 截断并提示"+N 条未显示"。
- **验证**：`tests\test_web.py` 57 条全过；全套 230 条全过；原版真数据全页面 200（首页 5.1 KB / 列表 716 行 / 反查 1204 行已分页 / 体检 7.5 KB），最慢一页 1.4 s。单开窗口与退出按钮在真服务上实测（2026-10-11）：`web -Window -NoBrowser` 后台起服务、首页 4624 B 带「退出」链接、服务 10 秒后仍在监听、确认页表单字段是 `do=1 scope=Firefight`、按浏览器的方式提交后回「已退出」且服务与端口都消失、`stop` 清 `web.json`、端口被占时拒绝启动（退出码 2）。不留窗口这一点是实测的：子进程 `python` 的 `MainWindowHandle = 0`，启动前后新增的 `powershell`/`cmd`/`pwsh` 进程数为 0，`logs\web-<端口>-err.log` 在 `stop` 之后仍然存在。测试里专门有一条「按浏览器提交确认表单」的用例，就是为了钉住上面那个「退出没用」的回归。
- **文档**：新增 `docs\web.md`（路由、选项、设计规则、限制、测试）；`README.md` 补了快速开始与文档索引；`docs\cli.md` 补了 `web`/`serve` 命令与四个选项。

### 1.5 代码结构与注释（2026-10-11 去碎片化）

- **模块合并**：`core/xml.py` ← `xmlmodel.py` + `xmlread.py`；`core/toml.py` ← `tomlmodel.py` + `tomlread.py` + `tomlwrite.py`；`core/cli/commands.py` ← 吸收 `documents.py`；`core/web/server.py` ← 吸收 `pages.py`。core 的 `.py` 由 18 个减到 11 个。
- **做法**：一次性脚本 `_out\merge_modules.py`（ast 驱动）按顶层定义逐段搬运，保留 `import … as` 别名、剥掉已消失模块的限定符（`pages.`/`documents.`）、并集重复的 import；被吸收模块的 body 放在目标 body **之前**（`core/web/server.py` 里 `class App` 的注解 `-> Url` 会在类创建时求值，放后面会 `NameError: name 'Url' is not defined`）。`_out\check_merge.py` 用 ast 比对 `core/xml.py` / `core/toml.py` 的顶层定义与合并前一致（14/14、25/25，problems 0）。
- **测试文件合并**：`tests/test_xml.py` ← `test_xmlread.py`；`tests/test_toml.py` ← `test_tomlread.py` + `test_tomlwrite.py`；测试模块 13 → 11 个。
- **验证**：`python -m unittest discover -s tests -t .` → `Ran 230 tests … OK`（约 4.2 s）；单模块 57/37/34/21/20/19/16/7/7/6/6（web/cli/toml/refs/convert/schema/xml/errors/textio/golden/roundtrip_bytes）。合并后的 Web UI 在真数据上冒烟：`GET /` 200 · 5217 B、`/quit?do=1` 200、端口随即释放。
- **合并的代价（据实记录）**：过程中一次 `git checkout -- tests tools/m1_roundtrip.py` 误丢了未提交的 WIP 测试增量（`tests/test_textio.py` +34 行、`tests/test_xmlread.py` +4 行，约 6 条用例），`_out\backup` 里没有 tests 副本，无法恢复，测试总数因此由 236 变为 230（未跟踪的 `tests/test_roundtrip_bytes.py` 仍在，字节级往返覆盖未丢）。三个 golden fixture（`tests/fixtures/{aircraft,squad,weapon}/mapped.toml`）按现有管线重生成；`tests/test_convert.py` 里「重复表必须报错」那条改为符合宽容导入语义的「重复表变成数组 + 警告」。
- **注释与文档串**：core 各模块与 `ff.py` 的模块文档串统一成三行（职责 / 空行 / 一句约束+出处），最长的 `core/web/server.py` 由 21 行降到 3 行、路由表改由 `docs/web.md` 承载；`tests/test_*.py` 的模块文档串同样压短。`tools\launcher\ff-tool.ps1` 的 14 处推理型长注释按 C1–C7 改写（去掉设计辩护与变更历史），并**恢复 UTF-8 BOM**：无 BOM 时 PowerShell 5.1 按 cp936 解码，`退出` 等中文会变乱码，实测 `powershell -File ff-tool.ps1 help` 输出恢复正常。
- **未做**：`tools\launcher\logs\` 的约 120 个 `web-*.log`/`*-exit.log`/探针日志残件与 `tools\probes\` 的 27 个小脚本尚未清理或归并；`docs/m1-design.md` 只在 §3.1 目录树后加了一段「当前名称」说明，正文小节标题保留写作时的模块名。

---

## 2. 待完成

### 2.1 M7 本地 Web UI（浏览部分已完成，见 §1.4；下面是剩余部分）

**浏览部分已交付**：实体列表 / 详情三视图 / 字段取值与检索 / 双向引用 / 体检 / 统计 / 帮助 / JSON，见 §1.4 与 `docs\web.md`。
三条当初想要、这版**有意没做**的（都在文档里写明理由）：左侧折叠实体树、`/`+`j/k` 键盘导航、客户端惰性渲染 —— 为了守住「零 JavaScript、老式简单、少出 BUG」，改用「服务端分页 200 行 + 分类/路径过滤 + 链接跳转」替代；1840 条实测无压力。另有两项未做：详情页的**字段来源行号**与体检页的**点击定位到行**（现在按实体定位，行号只在 `find` 结果里）。

**编辑（依赖 M4 先落地，之后接进同一个 UI）**

- 类型感知的字段编辑器：枚举下拉、数字、布尔、字符串、多选；非法值就地拒绝。
- 未保存变更暂存 + **语义 diff** 预览；`--dry-run` 预览不写盘。
- 保存 = 追加一条事件日志记录；撤销 / 重做（`undo N` / `redo`），可跨段。
- 冲突检测：文件被外部改动时提示并拒绝覆盖。
- 权限模式指示（read-only / workspace-write / danger-full-access），写操作逐次确认，拒绝即中止且不重试。
- 批量编辑（多选同字段改同一值）。
- 导入 / 导出（`export to=`、mod-zip 打包）与工程切换（选择 `mod.toml`、scope 切换）。
- 事件日志查看器：时间线、按段、回放与导出；基线快照 diff。

**技术形态（已按此实现，不再是建议）**

已落地：Python 标准库 `http.server` 直接调用现有 `cli`/`core`（同进程、同一批命令处理器），不引新依赖；只监听 `127.0.0.1`，可选 `token=`；无构建、**零 JavaScript**（服务端渲染 HTML），不做任何外部网络请求；与 CLI 共用同一套 scope/编码/引用实现，所以「CLI 能查到的，UI 都能看到」。

### 2.2 M4 编辑引擎（Web UI 编辑面板的前提）

- `set <实体> <字段>=<值>`，`add` / `remove`（重复单例表用下标寻址，`--dry-run` 不写盘，幂等）。
- 事件日志：JSONL，`.editor\log\<段起始本地时间>.jsonl`，静默 5 分钟封段。
- `undo N` 字节级还原；`.editor\baseline\` 快照。
- 保真：编码保持（UTF-8 那 16 个文件仍是 UTF-8、cp1252 仍是 cp1252、CRLF/LF 各自保持）、注释与游离文本保留、不可编码字符硬错误 `ExportEncodingError`。
- 一致性：引用校验与重命名引用链；写盘原子性（临时文件 + 原子改名）；并发写不交错。
- 权限三级（同 DSH 语义）+ 逐次审批 + 拒绝不重试 + fail-closed。
- 验收用例 B1–B20 已列（见对话记录 b81）：改对改准、保真、引用一致、回滚审计、权限失败模式、规模往返。

### 2.3 M5 / M6 / M8

- **M5 工程文件**：`mod.toml`（模组元数据）、`mod_setting.toml`（对应 `mod.txt` 设置）、交叉引用缓存（各自 TOML）；工程导入 / 导出。
- **M6 打包**：mod-zip —— 包内是 `Mod/` 文件夹，README 与许可放包外；folder ↔ zip 往返无损（`export Vehicles` 599 文件的规模）。
- **M8 分发**：版本、更新与安装说明。

### 2.4 已知缺陷与风险（都在案）

- **选择器里含 `=` 会被 CLI 当成 `键=值` 吞掉**：原版 1840 个数据文件里 0 实例，已按行号核对并文档化；是否加守卫待定。
- **UTF-8 回退是否与引擎一致未验证**：需进游戏确认引擎是否按 UTF-8 读那 16 个文件。
- **导出会重排兄弟顺序**：~~语义等价已证，引擎是否容忍需进游戏验证~~ → **2026-10-11 已修**：导出改按文档出现顺序并保留布局，原版数据 1840/1840 逐字节一致，此风险消失。
- **编辑器默认分支没有 `ff.py`**：它只在 `m2/refs`（PR #9 目标）与 `m3/cli` 分支上；所以插件 README 必须写明去哪个分支取 CLI，否则照抄会 ENOENT。
- **`Mod` 作用域无测试工程**：工作区里没有带 `mod.toml` 的工程（CLI 提示 `Mod scope needs -Project <dir with mod.toml>`），需要补一个最小 fixture。
- **本机沙箱限制**：沙箱里 node 的 spawn 一律 EPERM，端到端 live 用例要提权才能跑（非沙箱环境不受影响）。
- **Web UI 的两条取舍**（有意为之，见 §2.1）：无 JavaScript ⇒ 没有键盘导航与树形折叠；无编辑 ⇒ 所有页面只读、POST 一律 501。

### 2.5 待你决定

1. ~~Web UI 用标准库还是引前端框架~~ → 已按你的要求（兼容性优先、牵扯少、老式简单）落地为**标准库 + 零 JavaScript**，不再需要决定。
2. ~~是否要 token、绑定端口、多窗口~~ → 已实现：默认绑 `127.0.0.1:8765`，`token=` 可选，多窗口各自选端口即可。
3. ~~先交付纯只读浏览还是等 M4~~ → **已交付纯只读浏览**；编辑面板等 M4。
4. 下一步做哪件：**(a)** M4 编辑引擎（`set` + 事件日志 + `undo`，然后接进 Web UI）；**(b)** 把浏览部分补细（字段来源行号、体检点击定位到行、左侧折叠树）；**(c)** 别的（例如先补一个最小 `mod.toml` 工程 fixture，让 `Mod` 作用域也能在 UI 里点）。
5. 编辑器 PR #9 是否要改基到 `main`（现在目标是 `m2/refs`）；Web UI 这些新文件是否要我提交并开 PR（现在只是本地未提交的工作树）。
6. DSH 插件本地 0.1.1 是否推送到远端 `main`（现远端 0.1.0）。

---

## 3. 已定裁决（不要反复推翻）

| 编号 | 内容 |
|---|---|
| D7 | 导出保真 = **XML 语义等价**，不追求字节相同（**2026-10-11 修订**：对有来源文本的文件升级为**逐字节复现原版**，原版数据 1840/1840 一致；语义等价仍是无来源文本 `.toml` 的底线） |
| D8 | 本地研究 / 测量脚本不入库 |
| D9 | schema 单独 PR |
| — | 不重建 13.2.0.0 枚举，复用 `enums_ext.txt`，未知枚举只警告 |
| — | AI 权限仿 DSH 三级 + 逐动作审批，拒绝即 fail-closed 不重试 |
| — | 实现语言 Python（兼容性优先）；一实体一文件，镜像原版 `Data` 树 |
| — | surnames 不建模、不打包；注释只客观注明功能与待实现 |
| — | 不做编辑功能前，CLI 一律只读；唯一写入口是 `export` / `ff_export` |
