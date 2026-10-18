# Changelog

## [Unreleased]

### Added

* The `/help` page carries a command index: every command the CLI knows, with
  one line of purpose taken from that command's own docstring, so a command
  added to the CLI shows up without a second list to edit.
* The `/cmd` line input suggests those command names and prints the purpose of
  the first word typed, read from the same index; the Chinese page takes that
  line from `core/web/i18n.py`, the English page from the docstring.
* The front page reports a `Setting.toml` key that names a directory this
  machine does not have, instead of failing later with an unexplained scope
  error.
* The status bar counts are stored in `EditorCache/check.json` and read from
  there by a later process while it recomputes in the background; a write made
  from a page schedules the same recomputation, so the counts move on without a
  page waiting for a scan.
* The MCP listener names three reach options instead of taking a bind address: `在本地开放`
  binds this machine, `在内网开放` binds the local network, and `在公网开放` binds every
  interface and asks the router to forward the port to this machine, through NAT-PMP first
  and UPnP next (`core/web/nat.py`). The page reports what the router answered — source,
  gateway, external address and lifetime — and, when the router's external address differs
  from the one an outside service reads, says the machine sits behind two layers of NAT
  instead of naming an address that cannot be dialled. Closing the listener drops the
  mapping it opened. A router that answers neither protocol leaves the local and private
  addresses working, and the page says so.
* The editor command line: 34 commands over two scopes, `Firefight` for the
  game's own data and any named directory for a mod project. `init`, `import`,
  `list`, `show`, `get`, `find`, `stats`, `refs`, `deps`, `check`, `verify`,
  `diff`, `set`, `batch`, `add`, `remove`, `index`, `convert`, `settings`,
  `export`, `pack`, `roster`, `clone`, `schema`, `log`, `undo`, `redo`,
  `version`, `web`. Each accepts `--json`.
* `import` makes a project out of a mod that already exists, given as a
  directory or a zip. The mod root is found the way the packager looks for it —
  under `Mod/`, at the top of the source, or one directory of its own above
  that — and `Data/`, `Images/` and `Sounds/` are copied byte for byte, with
  `mod.txt`, `README.md`, `LICENSE` and the two project files when the source
  carries them. `ModSetting.toml` is rendered from the source's `mod.txt` when
  it is missing, `ModInformation.toml` is written from the schema skeleton, and
  an existing project is only replaced with `overwrite=1` (docs/cli.md section
  4.16).
* `batch` applies a patch file — an array of `[[edit]]` entries in TOML — to as
  many documents as it names, in order. Every entry is planned before anything
  is written, later entries to one document are planned against the text the
  earlier ones would leave, and each document is written once and journalled
  once, so `undo` puts the whole run back (docs/cli.md section 4.15).
* `diff` compares two documents or two trees lined up by entity path, rendering
  both sides as stock XML first so a project `toml` and the stock `txt` it came
  from compare in the same shape. `verify` reads every selected document and
  writes it again, reporting the documents the editor cannot reproduce together
  with the first line that differs; a TOML file is compared after the trip
  through stock XML, so a file that was only edited in place is not reported for
  its layout (docs/cli.md sections 4.10, 4.11).
* `clone` copies one entity document under a new token: the root table's own
  `name` is set to the token and the result is written as `<Token>.toml`, so a
  document with no source project to copy from can still be made. `into=`
  writes the copy under another scope, which is how a stock document becomes a
  project document. `schema` lists the fields the editor declares for one root
  element — path, shape, type, whether it is required and the enum its values
  come from — or the values of one enum table, so a document can be filled in
  without guessing from a sample (docs/cli.md sections 4.12, 4.13).
* `roster` reads the plain-text rosters the project settings declare and edits
  them by physical line: `op=add`, `op=set` and `op=remove` go through the same
  plan, journal and undo path as every other change. `roster check` compares both
  directions — an entry no document answers, and a unit no roster names
  (docs/cli.md section 4.14).
* `check` takes three widening options. `assets=1` names the file a missing image
  or sound would have to be, `rosters=1` folds the roster comparison into the same
  table and the same exit code, and `against=<root>` answers references the
  project itself does not hold from a second root. On the WW3 project with the
  stock installation as `against=`, 911 dangling references become 29, and 235 of
  them want an asset file the project does not have (docs/cli.md section 6).
* A Web UI bound to the loopback address, in Chinese and English with a
  language switch, offering the same commands behind the same gates
  (docs/web.md). One document has two modes: `/edit` edits its whole text —
  TOML, XML and plain text alike, including a file the editor cannot parse —
  and `/show` reads it, with the other mode one link away in the document bar.
  `/cmd` is a command line that prints exactly what the CLI prints, and it
  carries each of the nineteen writing commands as a form that runs the command
  with `--write --dry-run` before offering the write; `/mcp` and `/help` are the
  same page seen from two further angles — the MCP tool table and the reference
  text — and the explanation of the three entrances is written once, on
  `/help`. `/log` shows the event log with the undo and redo forms. Pictures and
  sounds open from the file tree on `/show`,
  through a read-only route that serves a file's own bytes with its content type
  and an `ETag` and refuses any path outside the project; the property pane uses
  the same route to preview a field that names a picture or a sound. `/list` is
  the entity grid: each row carries edit, copy and delete, the page offers a
  new-document form, and it also lists the declared plain-text tables, each
  opening their row editor, so the document-level writes are reachable from the
  list and each still ends on the check step. A plain-text twin that still
  matches the document rendering it byte for byte can be deleted from `/twin`,
  and the page offers that link only while the two agree.
* `build`, `audit`, `adopt`, `unpack` and `run` turn the multi-step workflows and any list of
  steps into one command each: index then check then pack, verify then check with both gates,
  import then index, export alone. A failing step stops the run and the summary names it.
* The MCP server exposes the same five: `mcp_ff_build`, `mcp_ff_audit`, `mcp_ff_adopt`,
  `mcp_ff_unpack` and `mcp_ff_run`.
* `clone` also copies a project file (`ModInformation.toml`, `ModSetting.toml`) into another
  project, without `as=`.
* The page that edits the declared plain-text tables is `/equipment`, not `/tables`.
* The optional MCP listener can bind any interface rather than only loopback or the LAN, and
  the panel shows the address it really bound. The token stays mandatory.
* An MCP server for two protocol families, exposing 31 tools of which 12 are
  read-only; the writing tools are registered only under `--write`. Every
  command carries a tool, including the later `batch`, `clone`, `roster`,
  `schema`, `diff`, `verify` and `import` (docs/mcp.md).
* `pack` builds an installable mod archive: `<name>-<version>.zip` holding a
  `Mod/` prefix, project documents rendered back to the stock XML, the
  project's `ModSetting.toml` rendered into `Mod/mod.txt`, and no
  `EditorCache/` in the archive. Member timestamps are fixed,
  so two runs over the same project produce identical bytes. A document that
  cannot be rendered is reported and left out; `strict=1` refuses instead.
* `init` creates a project from nothing: `ModInformation.toml` and an empty `Data/`.
* `convert` turns the stock `.txt` documents of a scope into working `.toml`
  files under a destination project; `assets=1` also copies the scope's
  `Images/` and `Sounds/` trees byte for byte.
* `settings` translates between the project's `mod.txt` and `ModSetting.toml` in both
  directions (`op=render`, `op=emit`).
* `index` caches the document list and the reference table under `EditorCache/`;
  `refs` and `deps` read the cache while its fingerprint is current and walk
  the documents again when it is not.
* An undo journal: every write appends a record holding the bytes before and
  after it. `log` lists the records and filters them by document, field,
  actor, result or time; `undo` and `redo` restore from them. `log`, `undo`
  and `redo` accept `--dry-run`.
* Editing of array and table entries in `set` (`op=append`, `op=delete`) and
  whole-document `add` and `remove`.

### Changed

* The workbench holds the drawn tree per scope and language for `TREE_SECONDS`
  (30 s) and drops it on any write, and walks the files in one `os.scandir`
  pass instead of a `Path` walk with a `stat` per entry: on a game installation
  the front page went from 2.4 s to 0.3 s and `/show` from 2.3 s to 0.2 s.
* A link inside the workbench asks the server for the centre pane alone
  (`?pane=doc`) and swaps it in place, so the tree, the property pane, the
  output pane and the status bar are not rendered again for every click; the
  address bar follows with `pushState`.
* The menu bar shows the address the server answers on, and `StartWebUI.cmd`
  keeps its console open for 15 s to print it, because the server itself runs
  hidden.
* When the scope is a game installation the counts file goes to
  `%TEMP%/firefight-mod-editor/` instead of `EditorCache/` inside the root, so
  the editor never writes into the installation it reads.
* `清单文件` is called `单位表` throughout the UI and the docs, and the section
  sits above the entity table.
* The menu bar links `/mcp` next to the exit link, and the listener section puts
  the external addresses and their copy boxes first.
* The project tree opens `Data` and leaves the other top-level folders folded;
  the tree search counts what it kept and hides a folder the search emptied.
* `/edit` edits one document as its whole text rather than one field per row: TOML and XML are
  treated as what they are, plain text, and a file the editor cannot parse opens and saves the same
  way, so a broken document can be repaired from the page. The structured field controls are gone,
  and so is the separate `/source` mode they sat beside; the document bar now carries the two modes
  of an open document, 查看 and 编辑. The tab strip keeps the four scope-level sections — home,
  entity list, log and command line.
* `/assets` is gone: the tree lists every file of the project already, and a picture or a sound
  opens from there on `/show`, which draws the media itself and links the raw bytes through
  `/asset?path=`. The read-only route and the field preview keep their behaviour.
* The entity list carries the plain-text tables the project settings declare, under 清单文件, each
  name opening its row editor `/equipment?path=`, so the equipment table is reached from the list
  rather than from a section of its own.
* `/cmd`, `/mcp` and `/help` are the three modes of one page with one bar between them — the
  command line with its writing forms, the MCP tool table, the reference text; the rules shared by
  the form, the command line and MCP are written once, on `/help`.
* The workbench shell is two files rather than two blocks copied into every page: `/shell.css` and
  `/shell.js` are served once, with a one-hour cache header and an `ETag`, so walking through the
  pages fetches them a single time and a page that cannot load them still reads.
* The workbench face is the monospace system stack (`Consolas` first) at a 14px base size, so the
  editor reads at the density of a desktop tool; there is no second face and no control for one.
  A dark theme, a set of CSS variables on the root element, is offered by one button in the tool
  bar, so one attribute repaints the page, and the choice joins the panel widths in `localStorage`.
  The menu bar and the tool bar are shorter, and the scope origin in the property pane reads as a
  sentence instead of the log wording.
* The tree lists every file of the project — the readme and the settings beside the documents,
  and the pictures and the sounds — while leaving `EditorCache/` out. A `.txt` that a `.toml` of
  the same name renders is drawn dimmed instead of being hidden, and when the copy still matches
  the original byte for byte it carries a delete link that goes through a check and the event log,
  so `undo` brings the file back (docs/web.md section 0).
* The menu bar keeps the brand, the scope, the language and the exit link; the sections are on the
  tab strip only, and the menu bar and the tool bar each declare a fixed height so a long menu
  cannot squeeze the document pane.
* `check` accepts `against=stock` for the installation named in the editor setting, and when
  more than one kind of reference is dangling the summary and `dangling_kinds` name the counts
  per kind, so an imported project's missing assets are told apart from its broken references.
* The entries of a declared unit roster join the reference graph, so `refs` lists them,
  `deps <unit>` names the roster and the line that lists it, and `check` reports a unit no
  document answers as a dangling reference of kind `roster` instead of leaving it invisible
  until `rosters=1` is given. A surname list contributes nothing (docs/refs.md section 1).
* Every page is now a workbench: a menu bar, a tool bar, a project tree, the document in the
  middle, a property pane, an output pane carrying the tail of the event log, and a status bar.
  The panes resize by dragging and fold from the tool bar; that state and the language are the
  only things kept in the browser. A page carries one inline script, the shell itself, and
  renders complete without it (docs/web.md section 0).
* The tree pane lists the project's documents by folder, from the same payload `list` returns,
  and the property pane shows the fields of the document the request names, from the same
  payload `get` returns.
* `/equipment` edits the plain-text tables the commands skip: every line with its own box, a delete
  and an append, comments and blank lines shown as markers. The write goes through
  `core.edit` — plan, then apply — so it lands in the event log and `undo` restores it; `web` joins
  `cli` and `mcp` as an actor, which is what `log actor=web` filters on.
* `/mcp` shows the tools the MCP server registers — the names, the commands and the arguments a
  client receives — prints the command line and the client configuration block that attach a
  client to this workspace, and runs one `tools/call` in process to print the JSON-RPC answer as
  it came back. A writing tool is trialled with `dryRun` added unless the request asks to write,
  so the check step writes nothing and offers the link that runs it as typed.
* The status bar carries the file, load-error and dangling-reference counts of a `check` run over
  the scope, kept for a short interval so walking through the pages does not rescan the project,
  and dates the counts it shows. The output pane opens with the last command this session ran —
  the line, its output, its exit code, its elapsed time and a link that runs it again — and keeps
  it while the session moves to other pages, above the tail of the event log. A write reached
  through a page is recorded as `web`, and the JSON link a page offers carries a dry run whenever
  the line it came from writes, so following it cannot change the project twice.
* A check step shows what it would change before it offers the write: `/cmd` prints the field, the
  value now and the value after, `/equipment` prints the row as it is and as it would be, and
  `/edit` prints a line diff. The write link carries the digest the check read, so a write whose
  documents changed in the meantime is refused and the other writer's bytes are left in place.
* `/cmd` carries every writing command, the later `batch`, `clone`, `roster` and `import` included,
  and `undo` and `redo` name their count in the document field because that count is the command's
  positional selector. A payload key that is a count in one command and a list of paths in another
  no longer makes the check step of `index` fail with a server error.
* The web server reads `EditorCache/index.toml` and `refs.toml` at start-up and rebuilds them in a
  background thread when their fingerprint no longer matches the files; the rebuild replaces both
  tables atomically, a failure is printed as `web: index rebuild skipped`, and the reference pages
  fall back to walking the documents.
* The workbench reads at the density of a desktop tool: the monospace system face
  (`Consolas`, with `Courier New` and the platform mono behind it) at a 14px base size.
* The tree pane carries a search box. Typing filters the files the tree already holds by their
  path without a round trip; pressing enter asks the server the same question, so `?q=` alone
  filters the page for a browser without scripting, and a search that finds nothing offers the
  same query on the list page.
* The MCP panel can open one more socket for clients that speak MCP over HTTP. It is off until
  asked for, binds this machine, the local network or any interface, carries a token of its own,
  refuses a port it cannot take, registers the writing tools only when the form allows them, and
  answers one POSTed JSON-RPC message at a time. The panel names the address it bound, the LAN
  address and the public address, each with a copyable `ip:port`.
* The web server preloads the entity tree of every scope it can reach at start-up, so the first
  visit to a scope does not pay for the scan the tree pane would otherwise trigger.
* User-visible text is English throughout. The Web UI carries a Chinese
  translation of all 465 templates and a `lang=zh|en` switch.
* `export` replaces a file that is already there unless `overwrite=0` is
  given; `convert` and `settings` skip an existing destination unless
  `overwrite=1` is given.
* The plain-text tables of a project are the names its settings declare under
  `<equipment>` and `<surnames>`, so a table a mod names itself is recognised
  as one whatever it holds. A scope without a settings file still falls back to
  the `equipment_*` / `surnames_*` conventions and to a `.txt` with no root
  element (docs/cli.md section 4.3).
* `check` prints every sampled warning as its own row, so the counts in the
  summary line and the table under it agree, and a capped table ends with a row
  saying how many references were left out. The payload adds `warnings_shown`,
  `dangling_shown` and `truncated`.
* `pack` names what it left out: one `skipped: <path> (<reason>)` line per file
  that stayed out of the archive, including a `.txt` that a same-named TOML
  document covers, and one `warning:` line per warning.
* `deps` says how many incoming references point at a file that is there
  (`2 of 3`), instead of printing a list that reads the same when it is empty.
* The `pack` refusal for a `mod.txt` that disagrees with `ModSetting.toml` names
  both sizes and both ways out, including the non-destructive one
  (`settings op=render`).

### Fixed

* The MCP panel drops the wildcard address, lists every address another machine can
  dial and puts the loopback last labelled `本机`; the address row names the first
  dialable address instead of `0.0.0.0`.
* `/list` paginates past the command's 200-row cap, so every entity of a large
  project is reachable; the page slices the rows itself.
* `is_plain_text` decides from the first non-blank character before it parses a
  file, which keeps a long `list` from parsing every document.
* A journal write from the same process no longer fails with `WinError 32` on Windows: the file
  lock is now taken behind an in-process lock, so two threads of one server do not race for the
  same lock file.

