> Language: **English** | [中文](web.zh-CN.md)

# Local web UI

Status: **browsing, editing and the command line**. The UI renders the same results as the CLI,
and a page may run a writing command: the command's own gate (`--write`, project confinement,
the stock-scope rule) decides whether the write happens, so a refusal reads exactly as it does
in a shell ([cli.md](cli.md) §4.1–§4.3). Three pages cover the writing side: `/edit` lists every
field of one document with the control the schema and the enum tables call for, `/ops` offers
every writing command as a form with a check step before the write, and `/log` shows the event log
with the undo and redo forms (§2.1). What is still missing is a semantic diff before the write,
conflict detection and a permission indicator.

The whole UI is served by the Python standard library — no new dependency, no build step,
no external asset, no cookie. Every page is server-rendered HTML, so the first slice works in
any browser that can show a table, and there is no client state to get out of sync.

## 0. The shell

Every page is laid out as a workbench, the shape a production tool uses: a menu bar, a tool bar,
a project tree on the left, the document in the middle, a property pane on the right, an output
pane along the bottom and a status bar under it.

| Region | What it holds | Where it is filled |
|---|---|---|
| Menu bar | the brand, the current scope, the language switch, the exit link (the sections live on the tab strip only) | `nav_bar` |
| Tool bar | one button per pane that folds it, plus the sections the tabs do not carry | `Handler.tool_bar` |
| Tab strip | the open sections; the script swaps the centre pane without a page load | `Handler.section_tabs` |
| Tree pane | every file of the project as folders, with a file count per folder and a search box over the paths; a `.txt` that a `.toml` of the same name renders is dimmed | `Handler.pane_tree` |
| Centre | the section that is open | the `page_*` methods |
| Property pane | the scope, and the fields of the document the request names, each with the way into the editor | `Handler.pane_props` |
| Output pane | the last command of this session with its output, then the tail of the event log | `Handler.pane_output` |
| Status bar | the scope, the counts of the last check, the language, and how the page was produced | `Handler.status_bar` |

The panes are named areas of a CSS grid; the separators between them are drag handles. Panel
widths, folded panes and the language are the only things kept in the browser, under
`localStorage["ff.workbench"]`. Every page still works with the script disabled: no content is
produced by the script, so a browser that refuses it sees a slightly plainer workbench, not a
broken one.

A page carries two links to the shell — one stylesheet and one script — and nothing else. Both
are served by the same process at `/shell.css` and `/shell.js`, need no token, carry a one-hour
cache header and an `ETag`, so walking through the pages fetches them once (§3). A page that
cannot load them still reads: the content is server-rendered HTML, and the script only moves the
panes around.

The tree and the property pane read the payloads the `list` and `get` commands return, so what
they show is what those commands print. The property pane follows the document the request
names in `path=` or `selector=`; a page that names none leaves it at the scope summary. The tree
draws every file under the project root — documents, the manifest, the settings, the readme, the
pictures and the sounds — and hides only the editor's own state (`EditorCache/`). It opens the
top level with `<details>` and folds without any script. Above the tree sits one search box:
typing in it filters the drawn files by their path without a round trip, and pressing enter asks
the server the same question, so `?q=` alone filters the page for a browser without scripting
(`?q=` never reaches a command; it is a page parameter). A search that finds nothing says so and
offers the same query on the list page, where the command's own selector filter answers it.

A `.txt` beside a `.toml` of the same name is the rendered copy of that document, so the tree
dims it instead of hiding it. When the copy still matches the original byte for byte, the entry
carries a delete link (`/twin`): the page compares the two files, offers the write only after
that check, and the removal goes through `core.edit` and the event log, so `undo` brings the file
back. When the copy differs, the entry carries `≠` and a link that shows the difference; no
delete link is offered, because deleting the file would lose the change.

The status bar is fed by one `check` run per scope per page load, held in memory for
`CHECK_SECONDS` so that walking through the pages does not rescan the project. It carries the
file count, the load errors and the dangling references the command reports, each with the
moment the counts were taken; a scope whose counts cannot be read says so instead. The output
pane opens with the last command this session ran — the line, its output, its exit code, how
long it took, and a link that runs it again — and keeps it while the session walks to other
pages. Under it sits the tail of the event log, so a write from a page shows up next to the
command that caused it.

A write reached through a page is recorded in the journal as `web` (`cli`, `mcp` and `web` are
the three actors `log actor=` accepts), so the event log says which surface the change came
from. The JSON link a page offers never writes: on a line that carries `--write` it adds
`--dry-run`, so following a link that reads like a read cannot change the project twice.

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
  页面     服务端渲染，一个内联脚本只负责工作台布局
  停止     Ctrl-C，或页面上的「退出」
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

Start-up reads the reference cache before any page is served: `EditorCache/index.toml` and
`refs.toml` are the tables `index --write` produces, and the server accepts them only when their
recorded fingerprint still matches the files on disk (SHA-256 over the relative path, size and
mtime of every indexed document). When the fingerprint does not match, a daemon thread runs
`index --write` and replaces both tables atomically, so a page that arrives during the rebuild
still reads whatever was there before. The rebuild is best effort: a failure is printed as
`web: index rebuild skipped: <error>` and the reference pages fall back to walking the files,
which is slower but gives the same answers. A stock scope is skipped because `index` refuses it.

## 2. Pages

| Page | Route | Shows |
|---|---|---|
| 首页 | `/` | scope, root, origin, counts, links to everything |
| 实体列表 | `/list` | every entity with category, format and size; filter by `prefix=` and `type=`, paged with `page=`; each row carries the edit, copy and delete links, and the page offers a new-document form (§2.3) |
| 实体详情 | `/show` | one entity as `as=toml` (default), `as=xml` or `as=raw`, plus its incoming and outgoing references |
| 读取字段 | `/get` | `field=<a.b.c>` at a document path |
| 查找 | `/find` | `tag=`, `value=`, `path=`, `ignore_case=1`; needs a selection |
| 引用 | `/refs` | what one file points at, grouped by kind |
| 反查 | `/deps` | who points at `value=<token>`; shows what the token resolved to |
| 体检 | `/check` | load errors, warnings and dangling references; `selector=` narrows the scope |
| 统计 | `/stats` | counts by category, root element and storage format |
| 编辑 | `/edit` | every field of `path=<document>` with the control its schema calls for (§2.1) |
| 源码 | `/source` | one document as its whole text, TOML or XML, saved as a whole (§2.5) |
| 日志 | `/log` | the event log, filtered by `document=`, `field=`, `actor=`, `result=`, `since=`, `until=`, plus the undo and redo forms |
| 操作 | `/ops` | every writing command as a form, with a check step before the write (§2.1) |
| MCP | `/mcp` | the MCP tool table, the connection snippet, one `tools/call` trial in process, and the optional HTTP listener (§2.6) |
| 资源 | `/assets` | the pictures and sounds of the project, drawn from the files themselves (§2.2) |
| 装备表 | `/equipment` | the equipment tables the project settings declare, one row per line, with edit, delete and append; surnames files are listed read-only (§2.4) |
| 命令行 | `/cmd` | one command line, run as typed, printed as the CLI prints it (`line=`, `json=1`) |
| 帮助 | `/help` | the CLI reference and the page list |
| 退出 | `/quit` | ask first, then stop the server (`/quit?do=1`) |
| `/json?command=<cmd>&selector=<sel>&…` | | the raw `--json` payload, `text/plain` |
| `/asset?path=<file>` | | one project file as its own bytes, with its content type and an `ETag` (§2.2) |
| `/equipment?path=<file>` | | the rows of one declared table, with its edit forms (§2.4) |

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

`/edit` takes `path=<document>` and lists every field of that document, one row per field. The
control is driven by the schema of the document's root element and by the enum tables the `set`
command checks against ([cli.md](cli.md) §4.1, §4.13): a boolean leaf gets a checkbox, a leaf whose
value comes from an enum table gets a drop-down of that table, and a leaf outside the schema keeps
a plain text box. An array becomes a row table, one row per entry, each cell editable in place; on
a working (TOML) document the table also carries an `添加` form with `from=` to copy an entry and a
`删除` form per row, because that is the only shape where `set` can add or delete an array entry.
A retail XML document has no array of tables to append to, so its row table only edits the fields
that are already there. The field path is the one `get` prints (`ammo.type.0.name`), so a path
copied from this page works on the command line unchanged. A row does not write anything itself:
its form posts to `/ops` with `command=set`, the document, the field path and the new value, so a
save from this page passes the same check step as any other write. The page also links to `/ops`
for a change that needs more than one option, and to `/log`.

`/ops` is the whole writing side as a form: `set`, `batch`, `add`, `clone`, `remove`, `index`,
`convert`, `settings`, `roster`, `export`, `pack`, `init`, `import`, `undo` and `redo` — the
nineteen commands that can change something. Without `command=` it is a table with one link per
command, each naming what the
command does and whether it takes a document. A command argument gives its form; the fields come
from the command's own options, so a checkbox is a flag (`overwrite=`, `assets=`, `strict=`) and
a `select` is an enumeration (`op=` of `set` is `append`/`delete`, `op=` of `settings` is
`render`/`emit`, `op=` of `roster` is `add`/`set`/`remove`). `undo` and `redo` name their count
in the document field, because that count is the command's positional selector rather than an
option.

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

When the check step runs `set`, the page prints the change as a table first — the document, the
field path, the value now and the value after — above the raw output. The raw output is the
command's own answer; the table is only a reading of it, and it is left out when the command
reports its dry run in another shape.

The write link carries the digest the check step recorded (`expect=`). The write compares it with
the documents as they are when the link is followed and refuses when they differ, so a file edited
in the meantime is not overwritten by a decision made before the edit; the page says so and asks
for a fresh check. The same protection exists on the command line, where a plan is applied only
while the document is still the one it was planned from ([cli.md](cli.md) §4).

`/log` prints the event log with the filters the `log` command takes and the undo and redo forms
beside it; those forms lead into `/ops`, so undoing is checked like everything else.

### 2.2 The assets

`/assets` walks the project's `Images/` and `Sounds/` folders and draws what a browser can render
by itself: a picture becomes a thumbnail that opens full size, a sound becomes a player. A file
whose extension says nothing to a browser is skipped, so a `.txt` that happens to sit in `Images/`
is not offered as a picture. `folder=Images` narrows the page to one folder. At most 60 files per
folder are drawn and the page says how many there are in total; the largest project measured on
this machine (866 pictures, 70 sounds) renders in about 170 ms.

The bytes come from `/asset?path=<file>`, a read-only route outside the page set. It resolves the
path against the project directory and refuses anything that leaves it, so `../`, an absolute path
and a drive letter are answered as a missing file rather than read; a folder and a file that is not
there are refused as well. The response carries the file's own content type and an `ETag` built
from its size and modification time, so a browser that asks again with `If-None-Match` gets a `304`
and a picture that has not changed is not sent twice.

The same route backs the property pane: when the selected document has a field whose value names a
picture or a sound that is really in the project, the field's preview appears under the field table.
A value that names nothing is left alone — that is a reference the project has not filled in yet,
which `check` already reports as dangling ([refs.md](refs.md)).

### 2.3 The entity grid

`/list` is the grid the three document-level writes hang off: every row carries 改 (`/edit`),
复制 (`/ops?command=add&from=<that document>`) and 删除 (`/ops?command=remove&selector=<that
document>&confirm=1`), and the page carries a new-document form that runs `add` with a path and an
optional copy source. `add` without `from=` builds a schema skeleton; with it, the named document
is copied.

Only the first of the three writes goes straight to its page. 复制 and 删除 lead to the operation
page's check step, and 删除 carries `confirm=1` so the check has already run when the page opens:
what is on screen is the real result of `--write --dry-run` for that document, and the write stays
one more click away. The grid is therefore an entry point and not a second write path — every
action it offers ends on the same page, with the same gate, as the command line.

Field-level editing lives on `/edit` (§2.1), which lists every field of one document with its own
box; the grid is what gets you to the right document.

### 2.4 The plain-text tables

The `equipment_*.txt` and `surnames_*.txt` files are not XML documents and not TOML: each line is
one entry, `//` starts a comment, and the file carries neither a root element nor a schema. The
command line treats them as list files and skips them ([cli.md](cli.md) §4.3), so until now there
was no way to change one from the editor at all.

`/equipment` closes that gap. It reads the project settings — `<工程>/mod.txt` when it is there,
`ModSetting.toml` otherwise, the same pair `declared_lists` reads — and lists the declared tables
plus any other list file under `Data/`. Opening one shows every line back in order with a box per
row, the delete link per row and an append form at the end.

The write does not go through a writing command. There is no command that writes a plain-text
table, and this page does not invent one: it builds the new document text with
`core/web/equipment.py`, and hands it to `core.edit.plan_render` and `core.edit.apply_document` — the
same plan-then-apply pair every other write uses. The record therefore lands in the event log with
`actor=web`, the bytes before and after, and the two digests, and `undo` puts the file back
byte-for-byte. `web` was added to `core.journal.ACTORS` for exactly this: the log says which
surface wrote, and `log actor=web` answers with what the pages changed.

A row keeps whatever ending the document already uses, a comment is never counted as a row, and a
delete leaves the orphaned newline behind rather than reformatting the file. Comments and blank
lines show as markers, never as editable entries.

The check step shows the row as it is now and as it would be, and the write link carries the digest
of the file the check read, so a table edited from a shell in between is refused rather than
overwritten (§2.1).

### 2.5 The source page

`/edit` edits one field at a time, which is the wrong shape for a document that has no schema or
that has to be rearranged. `/source` shows the whole file in one box and saves it back as a whole.
It opens the project's `.xml`, `.toml` and `.txt` files and nothing else; the path is resolved
inside the project directory, so `../` and an absolute path are refused.

The save keeps the file's own encoding, BOM and line ending: a file that carried a BOM is written
back as `utf-8-sig`, because `textio.encode_export` never adds one on its own. The write goes
through `core.edit.plan_render` and `core.edit.apply_document` with `actor=web`, exactly as the
table page does, so it lands in the event log and `undo` restores it.

Before and after the write the page runs `check` on that document and prints the result. It never
blocks on it — a document that does not load is the document someone came here to fix. The save is
the same two steps as everywhere else: a check that touches nothing, then the write. The check step
prints a line diff of the file as it is and as it would be, and the write link carries the digest it
was planned from (§2.1).

One limit comes from the interface rather than the editor: the UI answers GET only, so the edited
text travels in the query string, and files larger than 16000 bytes are refused with that number
named. Every shipped document is far below it.

### 2.6 The MCP panel

`/mcp` is the one page that does not call a CLI command. It builds the same tool specification
table the MCP server and the DSH plugin read (`core/cli/specs.py`), so the names, the commands and
the arguments on screen are the ones a client receives, and it prints the two command lines and the
client configuration block that attach a client to this workspace.

The trial runs one `tools/call` in process, through `core.mcp.server.Server`, and prints the
JSON-RPC answer as it came back: no socket, no second process, no stdio. A call that names a tool
the server does not register comes back as an error answer, which is what a client would see.

A writing tool follows the same two steps as `/ops`. The trial adds `dryRun` unless the request
carries `write=1`, so the check step runs the call with the write gate on and the dry-run gate
doing its job, and the page says so and offers the link that runs it as typed. A write performed
this way goes through `core.mcp.tools`, which sets `actor=mcp` on the same journal every other
write uses, so a page writes nothing the command line could not write.

The panel can also open a second socket (`core/web/mcp_listener.py`) for clients that speak MCP
over HTTP rather than over stdio. The listener is off until the form opens it, binds exactly one
host and port in this process — `127.0.0.1` for this machine alone, `0.0.0.0` for the local
network — and carries a token of its own, generated when it is opened, which is what the page
prints for the client to send as `X-Ff-Token`. Opening it is a real bind, so a port that is taken
is refused with the reason rather than silently moved; closing it shuts the socket down at once.
Without the writing switch the listener registers the same eight read-only tools a command line
server registers without `--write`. The socket answers one POSTed JSON-RPC message at a time and
serves nothing else: a reply to anything but a message is a refusal, and a missing or wrong token
is a refusal before the body is read.

## 3. Design rules

* **One implementation.** A page calls the same command handler the CLI calls
  (`cli.commands` with a parsed `Context`), in the same process. The UI cannot drift from
  `python -m core.cli --json`; a test asserts the `/json` payload equals what the CLI prints.
* **One shell, fetched once.** Every page links the same two files: `/shell.css` and
  `/shell.js`, served by this process. The script resizes and folds the panes, remembers that in
  `localStorage`, swaps the centre pane when a tab is clicked, filters the tree as the search box
  is typed into, and switches the theme and the face. It renders nothing, so a page is complete
  and readable with scripting disabled; it fetches nothing but these two files, so there is no
  external asset and no CDN. A test walks every route and asserts one stylesheet link and one
  script link, with neither inline.
* **Old, plain HTML.** One style sheet, grey background, bordered tables, `<pre>`
  for data. No framework, no downloaded font, no icon, no CDN — a page renders identically
  offline. The face is a system stack — a narrow industrial sans (`Tahoma` first, with
  `Arial Narrow` and the platform sans as fallbacks) — at a 15px base size, so the workbench
  reads at the density of a desktop tool rather than a web page. The tool bar offers a second
  face (`Consolas` and the mono stack, 14px) and a dark theme; both are CSS variables on the root
  element, so switching one attribute repaints without a round trip, and the choice joins the
  panel widths in `localStorage["ff.workbench"]`.
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
python -m unittest tests.test_web          # 170 tests, ~37 s
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
is ignored, and a clean stop removes it). The writing pages add their own cases: `/edit` draws
the control the schema and the enum tables call for (a checkbox for a boolean, a drop-down for an
enumerated value, a plain box for a field outside the schema), draws an array as a row table and
offers the add and delete forms only on a working TOML document, and links the save through `/ops`; `/ops`
lists the nineteen writing commands and answers the check step of every one of them, even when the
form is empty; a form names a parameter once; the check step runs `--write --dry-run` and leaves the
project untouched, prints the equivalent `ff` line, and drops no `write=1` link; a command that
refuses the check offers no write link and reports the refusal; `write=1` then changes the
document, appends an event and lets `/log` show it, undo included; `/pack` with `strict=1` on a
project with dangling references is refused and offers no write link; the field editor rejects
`set` without a field and without a value, and on a table-valued path it asks for the entry
directly; the forms survive the language switch, so a link that was handed a language keeps it;
and `/equipment` lists the declared plain-text tables with one row per line, marks comments and blank
lines instead of editing them, adds, edits and deletes a row, reports what the check would write
before the write link appears, reports a line number outside the file as an error, refuses a path
outside the project, writes through `core.edit` with `actor=web` (the log names the page, not the
command line, and undo restores the file); and `/source` opens a document as its whole text, lists
nothing before a path is given, refuses a suffix it does not edit, refuses a path outside the
project, refuses a file over the limit with the limit named, reports a check that writes nothing,
writes a UTF-8 file with a BOM back with its BOM and a CRLF file back with CRLF, offers no write
link when the text did not change, and logs the change as `actor=web`. The reference cache adds
its own cases: a pair of tables whose fingerprint still matches is reused instead of rebuilt, a
changed document makes it stale, the start-up rebuild runs in a background thread, and a rebuild
that raises is only printed so the pages keep answering from the files. The check step now shows the
change before it is offered: `/ops` prints the field, the value now and the value after, `/equipment`
prints the row as it is and as it would be, `/source` prints a line diff, and a write link followed
after the document changed on disk is refused with the other writer's bytes left in place. The MCP panel adds its own
cases: `/mcp` names every tool of the specification table and prints the command line and the client
block, a read-only trial answers with a JSON-RPC result and no error, a name the server does not
register and arguments that are not JSON are reported as such, and a writing tool is run with
`dryRun` added so the check step writes nothing while offering the link that runs it as typed —
following that link writes the document and lands one `actor=mcp` event in the log. The listener
adds its own: the panel opens it and a real MCP client gets the read-only tool table over HTTP
with the token the page printed, the writing tools appear only when the form asks for them, a
port that is taken is refused as a usage error with nothing left open, an address that is neither
`local` nor `lan` is refused, the socket answers a POST with the listener's token and refuses a
missing one before reading the body, a `GET` is a refusal, and closing it leaves the port shut. The shell of
the workbench adds the last group: every page links the two shell files and carries neither inline, a
page can ask for the centre region alone, the status bar carries the file, error and dangling
counts of a real `check` and dates them, the output pane starts with no command and then keeps
the last one across pages with its output, exit code, elapsed time and a link that runs it again,
a write reached from `/cmd` or `/ops` lands in the log as `web` while the same write from another
actor does not, and the JSON link of a writing line carries a dry run, so following it leaves the
document and the log untouched. The workbench face and its search box add the last cases: the
base size and the font stack come from the stylesheet, every page carries the search field, the
tree is drawn with the path of each file on it, `?q=` narrows the tree to the matching paths and
counts them, a query that matches nothing says so, the search box offers the same query on the
list page, and the tree form keeps the scope in a hidden input instead of in its action. The shell files are
served once with a cache header and a 304 on the second request, the style sheet carries the dark
theme and the mono face as variables, the tool bar carries both toggles, and the property pane
reads the scope origin as a sentence instead of the log wording. The tree
also lists a readme and the settings beside the documents while leaving `EditorCache/` out, dims a
`.txt` that a `.toml` renders, offers the delete link only while the copy still matches the
original, and marks a copy that differs with `≠`; the delete page compares the files, writes only
after that check, and the removal appears in the log as `web`. The menu bar carries no section
links and both top bars declare a fixed height. Measured
against the stock installation, the first
slice answers every page in about two seconds (a cold `/stats` over the whole 1840-file stock
scope was the slowest measured) and serves the 1204 references of
`WEAPON_PISTOL_P38` from the paged `deps` view; `/cmd` answers `stats`, `deps
value=WEAPON_PISTOL_P38` and a quoted `show` the same way.

## 6. Next

Editing now has a front end: `/edit` lists the fields of a document, `/ops` offers every writing
command with a check step before the write, `/equipment` edits the plain-text tables the commands
skip, `/source` edits a whole document as text, and `/mcp` shows and trials the tools the AI
surfaces read. The workbench around them is complete: the tree and the property pane read the
`list` and `get` payloads, the status bar carries the counts of the last `check`, and the output
pane keeps the last command beside the tail of the event log. What is still missing is what a productivity
tool adds on top of that — a semantic diff between the check and the write (the check reports the
command's output, not a comparison of the before and after bytes), conflict detection when the
document changed between the two steps, and a permission indicator that says up front whether the
current scope and options can write at all. The reference cache is no longer an open piece: the
server reads `EditorCache/index.toml` and `refs.toml` at start-up and rebuilds them in a background
thread when the files no longer match their fingerprint, and `refs` and `deps` read the stored
tables first, which is the shape the indexer was meant to give them.

