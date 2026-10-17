# Changelog

Notable changes are recorded here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the version is
semantic and is written down in one place, `core/__init__.py`.

## [0.1.0] — unreleased

### Added

* The editor command line: 27 commands over two scopes, `Firefight` for the
  game's own data and any named directory for a mod project. `init`, `list`,
  `show`, `get`, `find`, `stats`, `refs`, `deps`, `check`, `verify`, `diff`,
  `set`, `add`, `remove`, `index`, `convert`, `settings`, `export`, `pack`,
  `roster`, `clone`, `schema`, `log`, `undo`, `redo`, `version`, `web`. Each
  accepts `--json`.
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
* An MCP server for two protocol families, exposing 19 tools of which 8 are
  read-only; the writing tools are registered only under `--write`
  (docs/mcp.md).
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
* `/tables` edits the plain-text tables the commands skip: every line with its own box, a delete
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
  translation of all 415 templates and a `lang=zh|en` switch.
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
