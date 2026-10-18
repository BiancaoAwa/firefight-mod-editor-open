> Language: **English** | [中文](web.zh-CN.md)

# Local web UI

Status: **browsing, editing and the command line**. The UI renders the same results as the CLI,
and a page may run a writing command: the command's own gate (`--write`, project confinement,
the stock-scope rule) decides whether the write happens, so a refusal reads exactly as it does
in a shell ([cli.md](cli.md) §4.1–§4.3). Two modes cover the writing side of one document: `/edit`
shows its whole text, TOML, XML or plain text alike, and `/cmd` carries every writing command as
a form with a check step before the write, beside one command line of its own; `/log` shows the event
log with the undo and redo forms
(§2.1). What is still missing is a semantic diff before the write, conflict detection and a
permission indicator.

The whole UI is served by the Python standard library — no new dependency, no build step,
no external asset, no cookie. Every page is server-rendered HTML, so the first slice works in
any browser that can show a table, and there is no client state to get out of sync.

## 0. The shell

Every page is laid out as a workbench, the shape a production tool uses: a menu bar, a tool bar,
a project tree on the left, the document in the middle, a property pane on the right, an output
pane along the bottom and a status bar under it.

| Region | What it holds | Where it is filled |
|---|---|---|
| Menu bar | the brand, the current scope, the language switch, the MCP server link, the address the server answers on and the exit link (the sections live on the tab strip only) | `nav_bar` |
| Tool bar | the sections the tabs do not carry: find, deps, check, stats | `Handler.tool_bar` |
| Tab strip | the open sections, each an ordinary link | `Handler.section_tabs` |
| Tree pane | every file of the project as folders, with a file count per folder and a search box over the paths; `Data` is the folder opened by default; a `.txt` that a `.toml` of the same name renders is dimmed | `Handler.pane_tree` |
| Centre | the section that is open | the `page_*` methods |
| Property pane | the scope, and the fields of the document the request names, each with the way into the editor | `Handler.pane_props` |
| Output pane | the last command of this session with its output, then the tail of the event log | `Handler.pane_output` |
| Status bar | the scope, the counts of the last check and the language | `Handler.status_bar` |

The panes are named areas of a CSS grid. Nothing is kept in the browser: no width, no folded
pane, no theme. A page is complete HTML the moment it arrives.

A page carries one link to the shell — the style sheet at `/shell.css` — and no script at all.
The file is served by the same process, needs no token, and carries a one-hour cache header and
an `ETag`, so walking through the pages fetches it once (§3).

A request may ask for the centre pane alone (`?pane=doc`), which leaves the tree, the property
pane, the output pane and the status bar out of the response. The pages themselves do not ask
for it — there is no script to swap it in — but the shape stays for a client that wants it.

The tree and the property pane read the payloads the `list` and `get` commands return, so what
they show is what those commands print. The property pane follows the document the request
names in `path=` or `selector=`; a page that names none leaves it at the scope summary. The tree
draws every file under the project root — documents, the manifest, the settings, the readme, the
pictures and the sounds — and hides only the editor's own state (`EditorCache/`). It opens the
top level with `<details>`. Above the tree sits one search box: pressing enter asks the server
the question, so `?q=` alone filters the page (`?q=` never reaches a command; it is a page
parameter).
The drawn tree is held per scope and language for `TREE_SECONDS` (30 s), because walking the
files and testing each one for a list shape is what a large scope spends its time on; any write
that reaches the project drops the held trees, so the next page walks the files again.

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

The counts are also written to `EditorCache/check.json` beside the project: a later process
starts from that file and recomputes in the background, and a write made from a page schedules
the same recomputation, so the numbers move on without a page waiting for a scan. When the scope
is a game installation — a root that carries `Firefight.exe` — the file goes to
`%TEMP%/firefight-mod-editor/check-<digest>.json` instead, keyed by the root, so the editor never
writes into the installation it is only reading.

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
  页面     服务端渲染的纯 HTML，没有脚本
  停止     Ctrl-C，或页面上的「退出」
  GET / 200
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
default and keeps its console open for 15 s to print the address it bound, because the server
itself runs hidden — `-Foreground` serves in the console instead — and `-Scope <name>` chooses the scope
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
| 实体列表 | `/list` | every entity with category, format and size; filter by `prefix=` and `type=`, paged with `page=`; each row carries the edit, copy and delete links, the page offers a new-document form, and it lists the declared plain-text tables with their row editor (§2.3, §2.4) |
| 实体详情 | `/show` | one entity as `as=toml` (default), `as=xml` or `as=raw`, plus its incoming and outgoing references |
| 读取字段 | `/get` | `field=<a.b.c>` at a document path |
| 查找 | `/find` | `tag=`, `value=`, `path=`, `ignore_case=1`; needs a selection |
| 引用 | `/refs` | what one file points at, grouped by kind |
| 反查 | `/deps` | who points at `value=<token>`; shows what the token resolved to |
| 体检 | `/check` | load errors, warnings and dangling references; `selector=` narrows the scope |
| 统计 | `/stats` | counts by category, root element and storage format |
| 编辑 | `/edit` | `path=<document>` as its whole text — TOML, XML or plain text, and a file that does not parse (§2.1) |
| 日志 | `/log` | the event log, filtered by `document=`, `field=`, `actor=`, `result=`, `since=`, `until=`, plus the undo and redo forms |
| 命令行 · MCP · 帮助 | `/cmd`, `/mcp`, `/help` | three modes of one page: the writing commands as forms and one command line, the MCP tool table, and the reference text (§2.5, §2.6) |
| 退出 | `/quit` | ask first, then stop the server (`/quit?do=1`) |
| `/json?command=<cmd>&selector=<sel>&…` | | the raw `--json` payload, `text/plain` |
| `/asset?path=<file>` | | one project file as its own bytes, with its content type and an `ETag` (§2.2) |
| `/equipment?path=<file>` | | the rows of one declared table, with its edit forms (§2.4); `/tables` is the same page under its earlier name |
| `/twin?path=<file>` | | delete a plain-text twin that still matches the document rendering it byte for byte; the write link appears only when the two agree |
| `/mcpstart?host=local|lan|public&port=<n>&write=1` | | open the MCP listener and redirect to `/mcp`: `local` binds `127.0.0.1`, `lan` binds `0.0.0.0`, `public` also asks the router for a mapping (§2.6) |
| `/mcpstop` | | close the listener socket and drop the mapping it opened |

`/edit` is a mode of one open document rather than a section of the tab strip: every page that
carries a document prints a strip under its path — 查看 (`/show`) and 编辑 (`/edit`), with the
current mode in bold — and the property pane's 当前文件 row repeats the same links. The tab strip
keeps the scope-wide pages only: 首页, 实体列表, 日志 and 命令行.

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

### 2.1 The edit mode

Reached from the strip of an open document, `/edit` takes `path=<document>` and shows the whole
file in one box. TOML and XML are edited as text, and a plain `.txt` or a TOML/XML file that does
not parse is opened the same way, because a file that fails to load is exactly the file someone
opened this page to repair. It opens the project's `.xml`, `.toml` and `.txt` files and nothing
else; the path is resolved inside the project directory, so `../` and an absolute path are refused.

The save keeps the file's own encoding, BOM and line ending: a file that carried a BOM is written
back as `utf-8-sig`, because `textio.encode_export` never adds one on its own. The write goes
through `core.edit.plan_render` and `core.edit.apply_document` with `actor=web`, exactly as the
table page does, so it lands in the event log and `undo` restores it.

Before and after the write the page runs `check` on that document and prints the result. It never
blocks on it — a document that does not load is the document someone came here to fix. The save is
the same two steps as everywhere else: a check that touches nothing, then the write. The check step
prints a line diff of the file as it is and as it would be, and the write link carries the digest it
was planned from (the check step of the writing page, below).

One limit comes from the interface rather than the editor: the UI answers GET only, so the edited
text travels in the query string, and files larger than 16000 bytes are refused with that number
named. Every shipped document is far below it.

`/cmd` is the whole writing side: one command line, and the writing commands as forms — `set`,
`batch`, `add`, `clone`, `remove`, `index`, `convert`, `settings`, `roster`, `export`, `pack`,
`init`, `build`, `adopt`, `unpack`, `run`, `import`, `undo` and `redo`, the nineteen commands
that can change something. Without
parameters it runs nothing and lists a table with one link per command, each naming what the
command does and whether it takes a document; a `line=` argument runs that command line instead,
and `command=` gives the command's form; the fields come
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
beside it; those forms lead into the writing forms, so undoing is checked like everything else.

### 2.2 Pictures and sounds

Pictures and sounds are files like any other in the project, so the file tree on the left opens
them: a picture shows as itself, at the width of the pane and backed by a chequerboard for
transparency, and a sound shows with a player. The page prints the file, its type and its size, and
links `打开原文件` for the bytes on their own. A file whose extension says nothing to a browser is
not previewed; selecting it shows its path and size only. A `.txt` that happens to sit in `Images/`
is therefore not drawn as a picture.

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
复制 (`/cmd?command=add&from=<that document>`) and 删除 (`/cmd?command=remove&selector=<that
document>&confirm=1`), and the page carries a new-document form that runs `add` with a path and an
optional copy source. `add` without `from=` builds a schema skeleton; with it, the named document
is copied.

Only the first of the three writes goes straight to its page. 复制 and 删除 lead to the writing
form's check step, and 删除 carries `confirm=1` so the check has already run when the page opens:
what is on screen is the real result of `--write --dry-run` for that document, and the write stays
one more click away. The grid is therefore an entry point and not a second write path — every
action it offers ends on the same page, with the same gate, as the command line.

Field-level editing is gone: `/edit` (§2.1) edits the whole document as text, and the grid is what
gets you to the right document. The grid also lists the plain-text tables the project settings
declare under 单位表, each name opening its row editor (§2.4).

### 2.4 The plain-text tables

The `equipment_*.txt` and `surnames_*.txt` files are not XML documents and not TOML: each line is
one entry, `//` starts a comment, and the file carries neither a root element nor a schema. The
command line treats them as list files and skips them ([cli.md](cli.md) §4.3), so the row editor is
the only way to change one from the editor.

The entity grid lists them under 单位表 (§2.3). `/equipment?path=<table>` is their row editor.
It reads the project settings — `<工程>/mod.txt` when it is there, `ModSetting.toml` otherwise, the
same pair `declared_lists` reads — and lists the declared tables plus any other list file under
`Data/`. Opening one shows every line back in order with a box per row, the delete link per row and
an append form at the end.

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

### 2.5 One page, three modes

`/cmd`, `/mcp` and `/help` are the same page seen from three angles: the writing forms and one
command line, the MCP tool table, and the reference text. Both tables are grouped by the command
category the registry carries (read, check, write, project, build, serve), so a reader sees which
commands only read and which ones write before opening any of them. Each page prints the same strip of the
three names, with the current mode in bold, and the explanation is written once, on `/help`:
the three entrances (form, command line, MCP) end in the same command implementation and the same
write gate; a form checks before it writes, a command line writes only under its own `--write`, and
the MCP writing tools are registered only with `--write`; the command line is the part after
`python -m core.cli`, and a write made from a page is recorded with `actor=web`. Only `web` is
refused. The other two pages each keep one short pointer to that explanation, because a reader
who arrives on any of them needs the same rules.

The line input suggests the commands the CLI knows, and a line under it describes the command the
first word names, using the first line of that command's docstring, or the Chinese line in
`core/web/i18n.py` when the page is Chinese; the help page prints the same index in full. The command line page runs the same parser and the same handlers as the CLI, so the output is not a
re-rendering — a test compares the `<pre>` block with `Result.text`. Nothing else is refused: `set`,
`convert` and `export` run from a page exactly as they do from a shell, and the gate of the command
they name decides whether anything is written.

### 2.6 The MCP panel

The menu bar carries the link to `/mcp` next to the exit link, and while the listener is open the
page put its external addresses first, each with a box that copies it. The wildcard is left out and every address another machine can dial is listed; the loopback comes
last, labelled `本机`, so a client on the same machine has one too. The `地址` row names the
first dialable address while `绑定` keeps the bound host.

`/mcp` is the one page that does not call a CLI command. It builds the same tool specification
table the MCP server and the DSH plugin read (`core/cli/specs.py`), so the names, the commands and
the arguments on screen are the ones a client receives, and it prints the two command lines and the
client configuration block that attach a client to this workspace.

The trial runs one `tools/call` in process, through `core.mcp.server.Server`, and prints the
JSON-RPC answer as it came back: no socket, no second process, no stdio. A call that names a tool
the server does not register comes back as an error answer, which is what a client would see.

A writing tool follows the same two steps as a writing form. The trial adds `dryRun` unless the request
carries `write=1`, so the check step runs the call with the write gate on and the dry-run gate
doing its job, and the page says so and offers the link that runs it as typed. A write performed
this way goes through `core.mcp.tools`, which sets `actor=mcp` on the same journal every other
write uses, so a page writes nothing the command line could not write.

The panel can also open a second socket (`core/web/mcp_listener.py`) for clients that speak MCP
over HTTP rather than over stdio. The listener is off until the form opens it. The form names one
of three reach options: `在本地开放` binds `127.0.0.1`, `在内网开放` binds `0.0.0.0`, and
`在公网开放` binds `0.0.0.0` and asks the router to forward that port to this machine, through
NAT-PMP first and UPnP next (`core/web/nat.py`). The request runs while the page is being served,
so the page says it is in flight and the next load reports the outcome: a failure gives the reason
and states that the local and private addresses still answer, a success adds the public address to
the copies and reports what the router mapped — source, gateway, external address and lifetime —
then compares the router's external address with the one an outside service reads, so a machine
behind two layers of NAT is described as such rather than promised an address that does not work.
Closing the listener drops the mapping it opened. It carries a token of its own, generated when it
is opened, which is what the page prints for the client to send as `X-Ff-Token`. Beside the address it lists the ones a client can
dial — the private address of this machine or the local network, and the public one read from an
outside service when the machine is online — and gives a box that copies just `ip:port` for each;
a public address that cannot be read is reported as such, with a link that asks again. Opening it
is a real bind, so a port that is taken
is refused with the reason rather than silently moved; closing it shuts the socket down at once.
Without the writing switch the listener registers the same eight read-only tools a command line
server registers without `--write`. The socket answers one POSTed JSON-RPC message at a time and
serves nothing else: a reply to anything but a message is a refusal, and a missing or wrong token
is a refusal before the body is read.

## 3. Design rules

* **One implementation.** A page calls the same command handler the CLI calls
  (`cli.commands` with a parsed `Context`), in the same process. The UI cannot drift from
  `python -m core.cli --json`; a test asserts the `/json` payload equals what the CLI prints.
* **One style sheet, no script.** Every page links the same file, `/shell.css`, served by this
  process and cached for an hour. Nothing on a page is produced by a script: there is no script
  at all, so the pages work in a browser that blocks them and fetch nothing beyond this process
  — no external asset, no CDN, no font download. A test walks every route and asserts exactly
  one style-sheet link and no `<script`.
* **Old, plain HTML.** One style sheet, grey background, bordered tables, `<pre>`
  for data. No framework, no downloaded font, no icon, no CDN — a page renders identically
  offline. The face is the monospace system stack (`Consolas` first, with `Courier New`
  and the platform mono as fallbacks) at a 14px base size, so the workbench reads at the
  density of a desktop tool rather than a web page; there is no second face and no control
  for one. The colour scheme is one light set of CSS variables on the root element: there is no
  dark theme, no switching link, and the page keeps no preference in the browser.
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
* **Bounded output.** `pagesize=` is the page size of the entity list and the row cap of
  the find, refs and deps pages; a page that reaches the cap says so (`到达上限，请收窄条件`)
  instead of cutting rows without a word.
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
* The check step reports the command output, not a comparison of the bytes before and after, so
  there is no semantic diff between the check and the write, no conflict detection for a document
  changed between the two steps, and no indicator that says up front whether the current scope and
  options can write.

## 5. Running the tests

```
python -m unittest tests.test_web           # the web tests alone
python -m unittest discover -s tests -t .   # the whole suite
```
