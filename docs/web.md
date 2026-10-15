> Language: **English** | [中文](web.zh-CN.md)

# Local web UI

Status: **browsing, editing and the command line**. The UI renders the same results as the CLI,
and a page may run a writing command: the command's own gate (`--write`, project confinement,
the stock-scope rule) decides whether the write happens, so a refusal reads exactly as it does
in a shell ([cli.md](cli.md) §4.1–§4.3). Three pages cover the writing side: `/edit` lists every
field of one document with its own input box, `/ops` offers every writing command as a form with
a check step before the write, and `/log` shows the event log with the undo and redo forms
(§2.1). What is still missing is a semantic diff before the write, conflict detection and a
permission indicator.

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
| `port=` | first free from `8765` | TCP port on `127.0.0.1`; naming one takes it or fails, it never falls to another |
| `token=<text>` | empty | require `?t=<text>` on every URL |
| `pagesize=` | `200` | rows per page |
| `lang=` | `zh` | interface language, `zh` or `en` (see below) |
| `browser=1` | off | open the default browser after binding |
| `--json` | off | print `{scope, root, url}` when the server stops (the startup banner carries the same URL) |

It binds `127.0.0.1` only, serves one request at a time and blocks until Ctrl-C **or until the
`退出` link on any page is confirmed**; a failed bind is reported as an error, not a traceback.
The address is printed at startup, and each request is logged to stderr:

```
Firefight 模组编辑器 Web UI · 作用域 Firefight
  根目录   <game directory>
  地址     http://127.0.0.1:8765/
  实例记录 <editor folder>\EditorCache\web.json
  无 JavaScript；Ctrl-C 停止，或点页面上的「退出」
  GET / 200 (312 ms)
```

Example:

```
python -m core.cli Firefight web "root=<game directory>"
```

### The interface language

Chinese is the authoring language of the pages and the default. `lang=en` renders the same
pages in English, and any page can be asked for in the other language with `?lang=`; every
link on that page then carries the language on, so the choice survives navigation. The
navigation bar has the same link, named `English` or `中文`. The startup banner follows
`lang=` as well. A page whose `lang=` names no language the server knows is a `400`.

Every string the server prints goes through one table (`core/web/i18n.py`), and a test
asserts that the table covers each of them, so a page added without wording fails the suite
rather than quietly showing Chinese in English mode.

To serve it without tying up the prompt, use the local launcher that wraps the CLI
(`tools/launcher/ff-tool.ps1`, shipped as `launcher/` in the editor folder):
`ff-tool.cmd web -Window` starts the
server **hidden in the background** — no console window is left behind — and opens the page in
a plain application window of its own (`msedge --app=<url>`: no tabs, no address bar — a
window, not a browser session); `-Browser` forces an ordinary browser window and `-NoBrowser`
opens nothing at all. The released `StartWebUI.cmd` in the editor folder takes that path by
default — `-Foreground` serves in the console instead — and `-Scope <name>` chooses the scope
it serves, so a double click always gets its own window and the watchdog below.

The caller returns as soon as the port answers; the server's output goes
to `web-<port>-err.log` next to the launcher log, so nothing needs to stay open to read
it. Its `status` action shows the server process and that log, and `stop` ends the process and
clears the recorded state. A window that names no port does not fail on a busy one: it reuses
the instance this editor already records, and otherwise takes the first free port from 8765
([cli.md](cli.md) §4.4). `-Port <n>` keeps the older, stricter rule — that port or a refusal —
so an explicit request never quietly lands somewhere else. Because nothing is left open, the
ways to stop the UI are the `退出` button on the page and the launcher's `stop`.

The **busy port** refusal is asked for, not inherited: `HTTPServer` sets `SO_REUSEADDR`, and on
Windows that lets a second bind of a port somebody already serves succeed, so two UIs would
quietly share one port and which one answers would be luck. `make_server` therefore probes the
port first (`socket.connect_ex`) and raises `cannot listen on 127.0.0.1:<port>: the port is
already in use`. Port `0` — what the tests use — always gets a free one. A `web` that names no
port never reaches that error: it asks `free_port` for the first free port from 8765, so a
stray server on the default port no longer keeps the UI from starting.

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

A running server is recorded in `<editor folder>/EditorCache/web.json`, or under the project
directory when no editor folder is recognised: `pid`, `host`, `port`, `url`, `scope`, `token`
and `started`. The record is what makes a second `web` reuse the first instead of starting a
rival. `serve` writes it once the port has answered and removes it on a clean stop; a record
left behind by a killed process is stale, and the probe of its address decides, so a crashed
UI never keeps the next one from starting. The launcher reads the same file to find the
address to open, and its process-ownership check compares the recorded `pid` with the process
that answers the port — command-line matching was measured unreliable (`Get-CimInstance` is
refused in a restricted session), and a wrong verdict there left a server running with no
window and reported a port that was in fact its own.

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
| 编辑 | `/edit` | every field of `path=<document>` with its own input box (§2.1) |
| 日志 | `/log` | the event log, filtered by `document=`, `field=`, `actor=`, `result=`, `since=`, `until=`, plus the undo and redo forms |
| 操作 | `/ops` | every writing command as a form, with a check step before the write (§2.1) |
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
block with `Result.text`. `web` is refused on `/cmd` and on `/json`, because it would try to
bind a second port inside a request (its alias `serve` is refused with it). Nothing else is:
`set`, `convert` and `export` run from a page exactly as they do from a shell, and the gate of
the command they name decides whether anything is written.

Every page carries a `退出` link in the top bar. It leads to a confirmation page rather than
stopping anything directly, because the UI is GET-only: a link can be prefetched or followed
by accident, a second deliberate click cannot. Confirming stops the server (the background
thread stops `serve_forever` after the goodbye page has been sent); open data files and the
game installation are untouched, and only the local serving process ends.

### 2.1 The writing pages

`/edit` takes `path=<document>` and lists every field of that document, one row per field, each
with its own input box and its own `保存` button. The field path is the one `get` prints
(`ammo.type.0.name`), so a path copied from this page works on the command line unchanged. A row
does not write anything itself: its form posts to `/ops` with `command=set`, the document, the
field path and the new value, so a save from this page passes the same check step as any other
write. The page also links to `/ops` for a change that needs more than one option, and to `/log`.

`/ops` is the whole writing side as a form: `set`, `add`, `remove`, `index`, `convert`,
`settings`, `export`, `pack`, `init`, `undo` and `redo` — the eleven commands that can change
something. Without `command=` it is a table with one link per command, each naming what the
command does and whether it takes a document. A command argument gives its form; the fields come
from the command's own options, so a checkbox is a flag (`overwrite=`, `assets=`, `strict=`) and
a `select` is an enumeration (`op=` of `set` is `append`/`delete`, `op=` of `settings` is
`render`/`emit`).

Nothing is written on the first pass. With `confirm=1` the page prints the equivalent `ff` line
and then the real result of running it with `--write --dry-run`, which is why it can promise that
nothing reached the disk; a `写入` link carrying `write=1` then applies it. The check step passes
`write=1 dry-run=1` rather than `--dry-run` alone, because every writing command takes `--write`
and it is `--dry-run` that keeps it off the disk ([cli.md](cli.md) §4). When the command refuses
the check — `undo` with nothing to undo, `init` over an existing project, `add` with a path that
is not a working document — the page shows that refusal as the result of the check and offers no
write link, because the write would be refused in exactly the same way. The two steps exist
because the UI is GET-only: a link can be prefetched or followed by accident, and a write stays
one deliberate click away from the page that shows what it would do. The command's own gate is
still the last word.

`/log` prints the event log with the filters the `log` command takes and the undo and redo forms
beside it; those forms lead into `/ops`, so undoing is checked like everything else.

## 3. Design rules

* **One implementation.** A page calls the same command handler the CLI calls
  (`cli.commands` with a parsed `Context`), in the same process. The UI cannot drift from
  `python -m core.cli --json`; a test asserts the `/json` payload equals what the CLI prints.
* **No JavaScript.** Links and `GET` forms only. Nothing on a page is generated on the
  client, so a page is valid even with scripting disabled.
* **Old, plain HTML.** One inline `style` block, grey background, bordered tables, `<pre>`
  for data. No framework, no font, no icon, no CDN — a page renders identically offline.
* **GET only.** `POST` answers `501`. The only route that ends the serving process is `/quit`,
  and it does that after a confirmation step. `/cmd` and `/json` refuse `web` and its alias
  `serve`, because it would try to bind a second port inside a request; every other command
  runs there, writing commands included. A page never decides on its own that a write happens:
  it passes the options it was given to the command, and the command's gate answers.
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
* A `Mod` scope still needs `ModInformation.toml` (or `root=`); the UI does not invent projects.

## 5. Tests

```
python -m unittest tests.test_web          # 80 tests, ~9 s
python -m unittest discover -s tests -t .  # run the suite
```

`tests/test_web.py` builds a small fixture project (`tests/_scratch_web/`) and starts the
real server on port `0`, so the tests cover parsing, escaping, paging, tokens, `404`,
`POST`/`PUT`/`DELETE` (all `501`, body drained), traversal attempts, the JSON view, the
`退出` link on every page, the confirmation form submitted the way a browser submits it, the
confirmed-quit stop, the command line (text output equal to `Result.text`, the JSON checkbox,
a quoted path, a scope prefix, an unknown command, and `web`/`serve` refused on both `/cmd` and
`/json` while a writing command is allowed through), a write from a page reaching the
command's own gate (a `set` without `--write` is refused with `set needs --write`, and the
document is left alone), and the instance record (an answering instance is reused, a stale one
is ignored, and a clean stop removes it). The writing pages add their own cases: `/edit` lists
every field of a document with one input box each and links the save through `/ops`; `/ops`
lists the eleven writing commands and carries a required parameter for each of the eight that
have one; a form names a parameter once; the check step runs `--write --dry-run` and leaves the
project untouched, prints the equivalent `ff` line, and drops no `write=1` link; a command that
refuses the check offers no write link and reports the refusal; `write=1` then changes the
document, appends an event and lets `/log` show it, undo included; `/pack` with `strict=1` on a
project with dangling references is refused and offers no write link; the field editor rejects
`set` without a field and without a value, and on a table-valued path it asks for the entry
directly; and the forms survive the language switch, so a link that was handed a language keeps
it. Measured against the stock installation, the first
slice answers every page in about two seconds (a cold `/stats` over the whole 1840-file stock
scope was the slowest measured) and serves the 1204 references of
`WEAPON_PISTOL_P38` from the paged `deps` view; `/cmd` answers `stats`, `deps
value=WEAPON_PISTOL_P38` and a quoted `show` the same way.

## 6. Next

Editing now has a front end: `/edit` lists the fields of a document and `/ops` offers every
writing command with a check step before the write. What is still missing is what a productivity
tool adds on top of that — a semantic diff between the check and the write (the check reports the
command's output, not a comparison of the before and after bytes), conflict detection when the
document changed between the two steps, and a permission indicator that says up front whether the
current scope and options can write at all. The other open piece is the indexer that would let
`refs` and `deps` answer from `EditorCache/index.toml` instead of rebuilding the graph on each
run.

