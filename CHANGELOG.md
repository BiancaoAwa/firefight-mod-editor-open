# Changelog

Notable changes are recorded here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the version is
semantic and is written down in one place, `core/__init__.py`.

## [0.1.0] — unreleased

### Added

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
  (docs/web.md). Three pages carry the writing side: `/edit` lists every field
  of a document with one input box each, `/ops` offers each of the eleven
  writing commands as a form and runs it with `--write --dry-run` before
  offering the write, and `/log` shows the event log with the undo and redo
  forms. `/assets` draws the project's pictures and sounds from the files
  themselves, through a read-only route that serves a file's own bytes with its
  content type and an `ETag` and refuses any path outside the project; the
  property pane uses the same route to preview a field that names a picture or
  a sound. `/list` is the entity grid: each row carries edit, copy and delete,
  and the page offers a new-document form, so the three document-level writes
  are reachable from the list and each still ends on the operation page's check
  step.
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

* The workbench shell is two files rather than two blocks copied into every page: `/shell.css` and
  `/shell.js` are served once, with a one-hour cache header and an `ETag`, so walking through the
  pages fetches them a single time and a page that cannot load them still reads.
* The tool bar offers a dark theme and a second face (the mono stack at 14px); both are CSS
  variables on the root element, so one attribute repaints the page, and the choice joins the
  panel widths in `localStorage`. The menu bar and the tool bar are shorter, and the scope origin
  in the property pane reads as a sentence instead of the log wording.
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
* The asset pages serve the project's pictures and sounds: `/assets` draws the files themselves,
  and `/asset?path=` hands back one file's own bytes with its content type and an `ETag`. The
  route reads only inside the project, and a field that names a picture gets a preview beside it.
* `/equipment` edits the plain-text tables the commands skip: every line with its own box, a delete
  and an append, comments and blank lines shown as markers. The write goes through
  `core.edit` — plan, then apply — so it lands in the event log and `undo` restores it; `web` joins
  `cli` and `mcp` as an actor, which is what `log actor=web` filters on.
* `/source` opens one document as its whole text and saves it back as a whole. The file's own
  encoding, BOM and line ending are kept, the write goes through `core.edit` like every other
  write, and `check` runs on the document before and after it without blocking the save.
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
* A check step shows what it would change before it offers the write: `/ops` prints the field, the
  value now and the value after, `/equipment` prints the row as it is and as it would be, and
  `/source` prints a line diff. The write link carries the digest the check read, so a write whose
  documents changed in the meantime is refused and the other writer's bytes are left in place.
* `/ops` carries every writing command, the later `batch`, `clone`, `roster` and `import` included,
  and `undo` and `redo` name their count in the document field because that count is the command's
  positional selector. A payload key that is a count in one command and a list of paths in another
  no longer makes the check step of `index` fail with a server error.
* `/edit` draws the control each field's schema calls for: a checkbox for a boolean, a drop-down for
  a leaf whose values come from an enum table, and a row table for an array. A field outside the
  schema keeps its text box, and only a working TOML document carries the `添加` and `删除` forms
  that add or delete an array entry, because that is the shape `set` can append to.
* The web server reads `EditorCache/index.toml` and `refs.toml` at start-up and rebuilds them in a
  background thread when their fingerprint no longer matches the files; the rebuild replaces both
  tables atomically, a failure is printed as `web: index rebuild skipped`, and the reference pages
  fall back to walking the documents.
* The workbench reads at the density of a desktop tool: a narrow industrial system face
  (`Tahoma`, with `Arial Narrow` and the platform sans behind it) at a 15px base size, with the
  pane widths, controls and thumbnails scaled to match.
* The tree pane carries a search box. Typing filters the files the tree already holds by their
  path without a round trip; pressing enter asks the server the same question, so `?q=` alone
  filters the page for a browser without scripting, and a search that finds nothing offers the
  same query on the list page.
* The MCP panel can open one more socket for clients that speak MCP over HTTP. It is off until
  asked for, binds either this machine or the local network, carries a token of its own, refuses
  a port it cannot take, registers the writing tools only when the form allows them, and answers
  one POSTed JSON-RPC message at a time.
* User-visible text is English throughout. The Web UI carries a Chinese
  translation of all 482 templates and a `lang=zh|en` switch.
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

### Known limitations

* `pack` carries the project directory as it stands, plus the
  project's `README.md` and `LICENSE`; `Images/` and `Sounds/` reach the archive only when
  they are already in the project directory (docs/cli.md section 4.8).
* Dangling references are reported by `check` and counted by `pack`, but
  nothing resolves them.

[0.1.0]: https://github.com/BiancaoAwa/firefight-mod-editor-open
