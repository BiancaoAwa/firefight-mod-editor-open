> Language: **English** | [中文](web.zh-CN.md)

# Local web UI

Status: **read-only browsing**. The UI renders the same results as the CLI and can write
nothing. Editing — typed edits and the event log — exists in the CLI only
([cli.md](cli.md) §4.1, §4.2); the web editing panel is a later stage.

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
python -m unittest discover -s tests -t .  # run the suite
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

Editing is the gate for everything write-shaped: typed editing, semantic diff,
`--dry-run`, the event log with undo, conflict detection and a permission indicator. The
browsing slice deliberately stays a read-only projection of the CLI so that the write path
can be designed once, in the core, and reused by both the CLI and the UI.

