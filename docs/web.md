# Local web UI (M7, browsing slice)

Status: **read-only browsing**. The UI renders the same results as the CLI and can write
nothing. Editing belongs to M4 (event log and undo) and is not implemented yet.

The whole UI is served by the Python standard library — no new dependency, no build step,
no JavaScript, no external asset, no cookie. Every page is server-rendered HTML, so the
first slice works in any browser that can show a table, and there is no client state to get
out of sync.

## 1. Running it

```
python -m core.cli <scope> web [key=value ...]
```

| Option | Default | Meaning |
|---|---|---|
| `root=` / `workspace=` | as everywhere else | the scope to browse |
| `port=` | `8765` | TCP port on `127.0.0.1` |
| `token=<text>` | empty | require `?t=<text>` on every URL |
| `pagesize=` | `200` | rows per page |
| `browser=1` | off | open the default browser after binding |
| `--json` | off | print `{scope, root, url}` when the server stops (the startup banner carries the same URL) |

It binds `127.0.0.1` only, serves one request at a time and blocks until Ctrl-C **or until the
`退出` link on any page is confirmed**; a failed bind is reported as an error, not a traceback.
The address is printed at startup, and each request is logged to stderr:

```
Firefight 模组编辑器 Web UI · 作用域 Firefight
  根目录   D:\Program Files (x86)\Steam\steamapps\common\Firefight
  地址     http://127.0.0.1:8765/
  只读界面，无 JavaScript；Ctrl-C 停止，或点页面上的「退出」
  GET / 200 (312 ms)
```

Example:

```
python -m core.cli Firefight web "root=D:\Program Files (x86)\Steam\steamapps\common\Firefight"
```

To serve it without tying up the prompt, use the local launcher that wraps the CLI
(`tools/launcher/ff-tool.ps1`, shipped as `launcher/` in the editor folder):
`ff-tool.cmd web -Window` starts the
server **hidden in the background** — no console window is left behind — and opens the page in
a plain application window of its own (`msedge --app=<url>`: no tabs, no address bar — a
window, not a browser session); `-Browser` forces an ordinary browser window and `-NoBrowser`
opens nothing at all. The released `ff-web.cmd` in the editor folder takes that path by
default — `-Foreground` serves in the console instead — and `-Scope <name>` chooses the scope
it serves, so a double click always gets its own window and the watchdog below.

The caller returns as soon as the port answers; the server's output goes
to `logs\web-<port>-err.log` next to the launcher log, so nothing needs to stay open to read
it. Its `status` action shows the server process and that log, `stop` ends the process and
clears the recorded state, and starting a second server on a busy port is refused instead of
reusing somebody else's. Because nothing is left open, the ways to stop the UI are the
`退出` button on the page and the launcher's `stop`.

The **busy port** refusal is asked for, not inherited: `HTTPServer` sets `SO_REUSEADDR`, and on
Windows that lets a second bind of a port somebody already serves succeed, so two UIs would
quietly share one port and which one answers would be luck. `make_server` therefore probes the
port first (`socket.connect_ex`) and raises `cannot listen on 127.0.0.1:<port>: the port is
already in use`. Port `0` — what the tests use — always gets a free one.

A hidden **watchdog** stays with a background session, and it works in both directions:

* **The server stopped** — `退出`, `stop`, Ctrl-C or a crash: it checks how it stopped (process
  gone, port released, and whether the server left its graceful-exit marker in the log), closes
  the application window it opened and removes that window's throw-away browser profile, then
  exits. The verdict is appended to `logs\web-<port>-exit.log` (`graceful True/FALSE` plus
  `backend exited normally` or one of the failure phrasings), which `status` reports as
  `last session`. A session `退出` reads `backend exited normally`; one stopped with the
  launcher's `stop` reads `graceful False ... (killed?)`, because `stop` ends the process
  rather than asking it.
* **The window was closed first** — then it asks the server to stop the polite way
  (`/quit?do=1`, so the log still reads `backend exited normally`) instead of leaving a server
  running with nobody watching. Liveness is read from the window's **profile lock**: with
  `--user-data-dir` the browser holds `lockfile` in that directory for exactly as long as the
  window lives, which survives the browser handing the window to another process. The pid
  `Start-Process` returns, and the number of browser processes, do not — both were measured
  lying. The launcher waits (up to 15 s) for that lock before it calls the session watched: if
  the window never shows up, it says so and leaves the server un-watched rather than
  half-watched. A miss is only believed after three consecutive checks (~5 s), so a slow
  browser cannot kill a live session.

`-Browser` starts the page in the user's own browser: that window is never watched and never
closed, because it is not the launcher's to close. `-NoBrowser` opens nothing, and there is
nothing to watch either way.

## 2. Pages

| Page | Route | Shows |
|---|---|---|
| 首页 | `/` | scope, root, origin, counts, links to everything |
| 实体列表 | `/list` | every entity with category, format and size; filter by `prefix=` and `type=`, paged with `page=` |
| 实体详情 | `/show` | one entity as `as=toml` (default), `as=xml` or `as=raw`, plus its incoming and outgoing references |
| 读取字段 | `/get` | `field=<a.b.c>` at a document path |
| 查找 | `/find` | `tag=`, `value=`, `path=`, `ignore_case=1`; needs a selection |
| 引用 | `/refs` | what one file points at, grouped by kind |
| 反查 | `/deps` | who points at `value=<token>`; shows what the token resolved to |
| 体检 | `/check` | load errors, warnings and dangling references; `selector=` narrows the scope |
| 统计 | `/stats` | counts by category, root element and storage format |
| 命令行 | `/cmd` | one command line, run as typed, printed as the CLI prints it (`line=`, `json=1`) |
| 帮助 | `/help` | the CLI reference and the page list |
| 退出 | `/quit` | ask first, then stop the server (`/quit?do=1`) |
| `/json?command=<cmd>&selector=<sel>&…` | | the raw `--json` payload, `text/plain` |

Every result page also prints the equivalent command (`python -m core.cli Firefight list all
--json`) and links to its own JSON, so what is on screen can always be reproduced from a shell.

`/cmd` is the same idea taken one step further: one text box that takes what you would type
after `python -m core.cli` (`list weapon`, `show Data/Weapons/WEAPON_PISTOL_P38.txt as=toml`,
`deps value=WEAPON_PISTOL_P38`), an optional scope name in front, and double quotes for a path
with a space. The page prints the command's own text output, or the payload with `json=1`, plus
the exit code, the elapsed time and the equivalent shell command. It runs the same parser and
the same handlers as the CLI, so the output is not a re-rendering — a test compares the `<pre>`
block with `Result.text`. `export` and `web` are refused on `/cmd` and on `/json`, because the
first writes files and the second would try to bind a second port (aliases `emit` and `serve`
are refused with them).

Every page carries a `退出` link in the top bar. It leads to a confirmation page rather than
stopping anything directly, because the UI is GET-only: a link can be prefetched or followed
by accident, a second deliberate click cannot. Confirming stops the server (the background
thread stops `serve_forever` after the goodbye page has been sent); open data files and the
game installation are untouched, and only the local serving process ends.

## 3. Design rules

* **One implementation.** A page calls the same command handler the CLI calls
  (`cli.commands` with a parsed `Context`), in the same process. The UI cannot drift from
  `python -m core.cli --json`; a test asserts the `/json` payload equals what the CLI prints.
* **No JavaScript.** Links and `GET` forms only. Nothing on a page is generated on the
  client, so a page is valid even with scripting disabled.
* **Old, plain HTML.** One inline `style` block, grey background, bordered tables, `<pre>`
  for data. No framework, no font, no icon, no CDN — a page renders identically offline.
* **GET only.** `POST` answers `501`. The only route that changes anything is `/quit`, and all
  it does is stop this serving process after a confirmation step; no data file is written.
  `/cmd` and `/json` refuse the two commands that could break that promise (`export`, `web`),
  including their aliases, so no page can start a write or a second server.
* **One thread per connection.** The server is a `ThreadingHTTPServer` (daemon threads, it
  does not wait for them when it closes). A browser opens speculative connections and leaves
  them idle; a single-threaded server would sit on such a socket reading a request line that
  never comes, and every other request would queue behind it, which looks exactly like a
  frozen page.
* **A taken port is a refusal.** `make_server` probes the port before binding, because
  `SO_REUSEADDR` (on by default) would otherwise let a second server bind a port that is
  already served on Windows. One UI per port, or a clear error.
* **Forms keep the scope and the token.** A `GET` submission replaces the query of the form's
  action with the form's own controls, so `server.form` moves the parameters of the action
  (`scope`, `t`) into hidden inputs and leaves the action as a bare path. Without that rule a
  form on a non-default scope silently searched the stock data and every form answered `400`
  once a token was set — and the confirmation form of `/quit` kept asking instead of quitting.
* **Escaped by default.** Every interpolated value goes through one escaping helper, both
  for text and for attribute values; a test feeds `<script>` through a list file and the
  TOML view to prove it stays text.
* **Bounded output.** `pagesize=` caps list, find, refs and deps rows; the page says how
  many rows it left out and links to the full JSON.
* **Untrusted input.** A selector is refused when it is absolute, starts with `~`, carries
  a drive letter or contains a `..` segment, before any command sees it.

## 4. Limits and security

* It is an editor for a local game installation, not a server: keep it on `127.0.0.1`.
  `token=` exists for the case where another local user or process could reach the port.
* No TLS, no authentication beyond the shared token, no user accounts, no rate limiting.
* Long scans are synchronous and hold one worker thread each: `check` over the whole stock
  scope takes about as long as the same `check` in a shell (seconds), while other requests are
  served on their own threads.
* A `Mod` scope still needs `mod.toml` (or `root=`); the UI does not invent projects.

## 5. Tests

```
python -m unittest tests.test_web          # 57 tests, ~4 s
python -m unittest discover -s tests -t .  # 231 tests
```

`tests/test_web.py` builds a small fixture project (`tests/_scratch_web/`) and starts the
real server on port `0`, so the tests cover parsing, escaping, paging, tokens, `404`,
`POST`/`PUT`/`DELETE` (all `501`, body drained), traversal attempts, the JSON view, the
`退出` link on every page, the confirmation form submitted the way a browser submits it, the
confirmed-quit stop, the command line (text output equal to `Result.text`, the JSON checkbox,
a quoted path, a scope prefix, an unknown command, and `export`/`emit`/`web`/`serve` refused on
both `/cmd` and `/json`). Measured against the stock installation, the first slice answers
every page in about two seconds (a cold `/stats` over the whole 1840-file stock scope was the
slowest measured) and serves the 1204 references of
`WEAPON_PISTOL_P38` from the paged `deps` view; `/cmd` answers `stats`, `deps
value=WEAPON_PISTOL_P38` and a quoted `show` the same way.

## 6. Next

Editing (M4) is the gate for everything write-shaped: typed editing, semantic diff,
`--dry-run`, the event log with undo, conflict detection and a permission indicator. The
browsing slice deliberately stays a read-only projection of the CLI so that the write path
can be designed once, in the core, and reused by both the CLI and the UI.

---

# 本地 Web 界面（M7，浏览部分）

状态：**只读浏览**。界面渲染的结果与命令行一致，不能写入任何东西。编辑属于 M4（事件日志与撤销），尚未实现。

整个界面由 Python 标准库提供——不新增依赖、没有构建步骤、不用 JavaScript、不引外部资源、不设 cookie。每个页面都是
服务端渲染的 HTML，因此这第一部分在任何能显示表格的浏览器里都能用，也没有会失步的客户端状态。

## 1. 运行

```
python -m core.cli <作用域> web [key=value ...]
```

| 选项 | 默认 | 含义 |
|---|---|---|
| `root=` / `workspace=` | 与其他命令一致 | 要浏览的作用域 |
| `port=` | `8765` | `127.0.0.1` 上的 TCP 端口 |
| `token=<文本>` | 空 | 要求每个 URL 都带 `?t=<文本>` |
| `pagesize=` | `200` | 每页行数 |
| `browser=1` | 关 | 绑定后打开默认浏览器 |
| `--json` | 关 | 服务停止时打印 `{scope, root, url}`（启动横幅里已有同一地址） |

它只绑定 `127.0.0.1`，一次处理一个请求，阻塞到 Ctrl-C **或任意页面上的「退出」被确认**；绑定失败按错误报告，不
抛栈。地址在启动时打印，每个请求记录到 stderr：

```
Firefight 模组编辑器 Web UI · 作用域 Firefight
  根目录   D:\Program Files (x86)\Steam\steamapps\common\Firefight
  地址     http://127.0.0.1:8765/
  只读界面，无 JavaScript；Ctrl-C 停止，或点页面上的「退出」
  GET / 200 (312 ms)
```

示例：

```
python -m core.cli Firefight web "root=D:\Program Files (x86)\Steam\steamapps\common\Firefight"
```

若不想占住提示符，用包装命令行的本地启动器（`tools/launcher/ff-tool.ps1`，发行版里是 `launcher/`）：
`ff-tool.cmd web -Window` 把服务**隐藏在后台**启动——不留控制台窗口——并用自己的独立应用窗口打开页面
（`msedge --app=<url>`：没有标签页、没有地址栏，是窗口而不是浏览器会话）；`-Browser` 强制使用普通浏览器窗口，
`-NoBrowser` 什么都不打开。发行版里的 `ff-web.cmd` 默认就走这条路径——`-Foreground` 改为在控制台里服务——
`-Scope <名称>` 选择服务的作用域，因此双击总是得到独立窗口和下面的看门狗。

端口一有响应调用方就返回；服务输出写到启动器日志旁边的 `logs\web-<port>-err.log`，不必留着窗口才能看。
`status` 显示服务进程与那份日志，`stop` 结束进程并清除记录的状态，在已占用的端口上再起一个会被拒绝，而不是复用
别人的端口。由于什么都不用留着，停止界面的方式就是页面上的「退出」按钮和启动器的 `stop`。

**忙端口拒绝**是主动要求的，不是继承来的：`HTTPServer` 会设置 `SO_REUSEADDR`，在 Windows 上这会让第二次绑定
一个已在服务的端口成功，于是两个界面会悄悄共用同一端口、谁应答全看运气。因此 `make_server` 先探测端口
（`socket.connect_ex`），占用时抛 `cannot listen on 127.0.0.1:<port>: the port is already in use`。端口 `0`
（测试用的）总能拿到空端口。

后台会话会带一个隐藏的**看门狗**，双向工作：

* **服务先停**——`退出`、`stop`、Ctrl-C 或崩溃：它检查停止方式（进程是否消失、端口是否释放、服务是否在日志里留下
  正常退出的标记），关闭自己打开的应用窗口、删掉该窗口的临时浏览器 profile，然后退出。结论追加到
  `logs\web-<port>-exit.log`（`graceful True/FALSE` 加 `backend exited normally` 或某种失败描述），`status`
  以 `last session` 报告它。会话里点「退出」读到 `backend exited normally`；用启动器 `stop` 停掉的读到
  `graceful False ... (killed?)`，因为 `stop` 是结束进程而不是礼貌询问。
* **窗口先关**——它会礼貌地请服务停止（`/quit?do=1`，日志里仍读作 `backend exited normally`），而不是留下一个
  没人看的服务在跑。存活信号取自窗口的 **profile 锁**：加了 `--user-data-dir` 后，浏览器在窗口存续期间一直持有
  该目录下的 `lockfile`，这比「浏览器把窗口交给别的进程」更可靠。`Start-Process` 返回的 pid 与浏览器进程数量都
  不可靠——两者都实测会骗人。启动器最多等 15 秒拿这个锁，拿到才认为会话受监视；窗口一直没出现就明确说明并让服务
  处于不受监视状态，而不是半监视。判死要连续三次检查（约 5 秒）都失败才采信，因此启动慢的浏览器不会误杀活会话。

`-Browser` 在用户自己的浏览器里打开页面：那个窗口永不被监视也永不被关闭，因为它不属于启动器。`-NoBrowser`
什么都不打开，也就没有可监视的对象。

## 2. 页面

| 页面 | 路由 | 内容 |
|---|---|---|
| 首页 | `/` | 作用域、根目录、来源、计数，以及指向各处的链接 |
| 实体列表 | `/list` | 全部实体及类别、格式与大小；可用 `prefix=`、`type=` 过滤，`page=` 翻页 |
| 实体详情 | `/show` | 一个实体的 `as=toml`（默认）、`as=xml` 或 `as=raw`，以及它的入向与出向引用 |
| 读取字段 | `/get` | 文档路径处的 `field=<a.b.c>` |
| 查找 | `/find` | `tag=`、`value=`、`path=`、`ignore_case=1`；需要选择范围 |
| 引用 | `/refs` | 一个文件指向什么，按类别分组 |
| 反查 | `/deps` | 谁指向 `value=<令牌>`；并显示该令牌解析到了什么 |
| 体检 | `/check` | 加载错误、警告与悬空引用；`selector=` 缩小范围 |
| 统计 | `/stats` | 按类别、根元素与存储格式计数 |
| 命令行 | `/cmd` | 一行命令，按输入执行，按命令行的方式打印（`line=`、`json=1`） |
| 帮助 | `/help` | 命令行参考与页面清单 |
| 退出 | `/quit` | 先确认，再停止服务（`/quit?do=1`） |
| `/json?command=<cmd>&selector=<sel>&…` | | 原始 `--json` 载荷，`text/plain` |

每个结果页面还会打印等价命令（`python -m core.cli Firefight list all --json`）并链接到自己的 JSON，因此屏幕上的
内容总能从 shell 复现。

`/cmd` 是同一思路的延伸：一个文本框接收 `python -m core.cli` 之后的部分（`list weapon`、
`show Data/Weapons/WEAPON_PISTOL_P38.txt as=toml`、`deps value=WEAPON_PISTOL_P38`），可选地在最前面写作用域名，
带空格的路径用双引号。页面打印命令自身的文本输出，或用 `json=1` 得到载荷，另外给出退出码、耗时与等价的 shell 命令。
它跑的是与命令行相同的解析器与处理函数，因此输出不是重新渲染——有测试比较 `<pre>` 块与 `Result.text`。`export` 与
`web` 在 `/cmd` 与 `/json` 上被拒绝，因为前者写文件、后者会尝试绑第二个端口（别名 `emit` 与 `serve` 同样被拒）。

每个页面顶栏都有「退出」链接。它指向确认页而不是直接停止，因为界面是纯 GET：链接可能被预取或被误点，而第二次有意
点击不会。确认后服务停止（后台线程在告别页发送完后停止 `serve_forever`）；已打开的数据文件与游戏安装不受影响，
只是本地服务进程结束。

## 3. 设计规则

* **同一套实现。** 页面在同一个进程里调用命令行调用的同一处理函数（`cli.commands` 加已解析的 `Context`）。界面
  不会与 `python -m core.cli --json` 漂移；有测试断言 `/json` 载荷与命令行打印的内容一致。
* **不用 JavaScript。** 只有链接和 `GET` 表单。页面上没有任何内容在客户端生成，禁用脚本也能正常显示。
* **老式朴素 HTML。** 一个内联 `style` 块、灰底、带边框的表格、数据用 `<pre>`。没有框架、没有字体、没有图标、
  没有 CDN——离线渲染结果一致。
* **只用 GET。** `POST` 返回 `501`。唯一改变状态的路径是 `/quit`，它做的也只是在确认后停止本服务进程；不写任何
  数据文件。`/cmd` 与 `/json` 拒绝两个可能破坏这一承诺的命令（`export`、`web`）及其别名，因此没有页面能发起写入或
  第二个服务。
* **每连接一个线程。** 服务是 `ThreadingHTTPServer`（守护线程，关闭时不等待它们）。浏览器会开推测性连接并让它们
  空着；单线程服务会卡在这种 socket 上读一个永不到来的请求行，其他请求全部排在后面，看起来就像页面卡死。
* **端口被占就拒绝。** `make_server` 在绑定前探测端口，因为 `SO_REUSEADDR`（默认开启）在 Windows 上会让第二个
  服务绑定已在服务的端口。一个端口一个界面，或者给出明确错误。
* **表单保留作用域与令牌。** `GET` 提交会用表单自身的控件替换 action 的查询串，因此 `server.form` 把 action 的
  参数（`scope`、`t`）搬进隐藏输入，把 action 留成裸路径。没有这条规则时，非默认作用域上的表单会悄悄去搜原版数据，
  设置了令牌后所有表单都回 `400`，`/quit` 的确认表单也会一直追问而不退出。
* **默认转义。** 每个插值都经过同一个转义助手，文本与属性值都一样；有测试把 `<script>` 塞进列表文件与 TOML 视图，
  证明它仍然是文本。
* **输出有界。** `pagesize=` 限制列表、查找、引用与反查的行数；页面说明省略了多少行并链接到完整 JSON。
* **输入不可信。** 选择器是绝对路径、以 `~` 开头、带盘符或含 `..` 段时，在任何命令看到它之前就被拒绝。

## 4. 限制与安全

* 它是本地游戏安装的编辑器，不是服务器：只放在 `127.0.0.1`。`token=` 用于「本机其他用户或进程可能访问该端口」的
  场景。
* 没有 TLS、除共享令牌外没有认证、没有用户账户、没有限流。
* 长时间扫描是同步的，各占一个工作线程：对整个原版作用域跑 `check` 与在 shell 里跑同样耗时（数秒），期间其他请求
  由各自的线程处理。
* `Mod` 作用域仍需要 `mod.toml`（或 `root=`）；界面不会凭空造出工程。

## 5. 测试

```
python -m unittest tests.test_web          # 57 条，约 4 秒
python -m unittest discover -s tests -t .  # 231 条
```

`tests/test_web.py` 会建一个小型示例工程（`tests/_scratch_web/`）并在端口 `0` 上启动真实服务，因此测试覆盖解析、
转义、分页、令牌、`404`、`POST`/`PUT`/`DELETE`（都返回 `501` 且读完请求体）、目录穿越尝试、JSON 视图、每个页面上
的「退出」链接、按浏览器方式提交的确认表单、确认后的停止、命令行（文本输出等于 `Result.text`、JSON 复选框、带引号
的路径、作用域前缀、未知命令，以及 `export`/`emit`/`web`/`serve` 在 `/cmd` 与 `/json` 上被拒绝）。针对原版安装实测，
这第一部分每个页面约两秒应答（对整个 1840 文件的原版作用域冷启动 `/stats` 是最慢的一次），并在分页 `deps` 视图里
给出 `WEAPON_PISTOL_P38` 的 1204 条引用；`/cmd` 对 `stats`、`deps value=WEAPON_PISTOL_P38` 与带引号的 `show`
结果相同。

## 6. 后续

编辑（M4）是所有写入形态功能的前置：类型化编辑、语义 diff、`--dry-run`、带撤销的事件日志、冲突检测与权限指示。
浏览部分有意保持为命令行的只读投影，以便写入路径在内核里只设计一次，供命令行与界面共用。
