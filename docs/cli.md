> Language: **English** | [中文](cli.zh-CN.md)

# Command line

Status: **read-only except three writers**. `set` changes one field of one project document,
`undo` and `redo` put back and re-apply what the log records, and `export` writes stock XML into
a directory the caller names; every other command only prints a result. The writers keep the
source around what they touch: `set` guarantees it per field (§4.1), `undo` and `redo` write
recorded bytes rather than a re-serialisation (§4.2), and `export` per file (order, blank lines,
indentation, comments and newline style — see §9 and toml-mapping §4). `web` serves the same
results as pages on `127.0.0.1` and runs the same commands, writing ones included
(docs/web.md). No packaging: that stage does not exist
yet.

## 1. Invocation

```
python -m core.cli <scope> <command> [selector] [key=value ...] [--json]
```

Run it from the editor root, which is the directory that holds `core/`. `help` prints the
same table the parser accepts; `version` prints editor version, interpreter and the scopes
that resolve from the current directory.

## 2. Scopes

A scope root is a directory holding `Data/`, `Images/` and `Sounds/`.

| Scope | Meaning | Resolution |
|---|---|---|
| `Mod` | the mod project the current directory belongs to | `root=`/`mod=` option, else `mod` in the local config, else nearest ancestor with `ModInformation.toml`; the project directory is its data root |
| `Firefight` | the stock game data | `root=`/`firefight=` option, else `FIREFIGHT_DATA`, else `firefight` in the local config found upwards, else the copy shipped with the editor |
| `<name>` | another mod folder in the workspace | a directory of that name, else `<workspace>/Mod/<name>`, else `<workspace>/<name>`; workspace from `workspace=<dir>`, else `FIREFIGHT_MODS`, else the local config, else the current directory |

A scope root is the directory that holds `Data/`, `Images/` and `Sounds/`; passing the
`Data` directory itself is accepted and normalized to its parent. For an installed game
that is the directory containing `Firefight.exe`. The `Firefight` scope is never written:
the editor does not edit the game directory, and `export` writes only under `to=`. A project
is written only by `set`, `undo` and `redo` with `--write`, and only inside the project
directory (§4.1, §4.2). The local config `Setting.toml` (keys `firefight`, `mod`,
`workspace`) is read from the nearest ancestor directory and belongs in `.gitignore`.

## 3. Paths and selectors

A command's third argument selects what to work on:

* nothing, or `all` — every entity in the scope;
* a category — `Infantry`, `Vehicles`, `Weapons`, `AT Guns`, `Aircraft`;
* a subdirectory or a single file — `Data/Weapons/WEAPON_PISTOL_P38.txt`;
* a document path suffix after the file — `Data/Infantry/American-Rifle Squad.txt/man/ammo`.

Paths use `/` and are relative to the scope root; `\` is accepted. Documents are read as
`.toml` under `Mod` and as `.txt` under `Firefight`; when both exist the `.toml` wins.

## 4. Commands

| Command | Aliases | What it does |
|---|---|---|
| `list` | `ls` | entities with category, storage format and size |
| `show` | `cat` | one entity as stored, or `as=toml`, `as=xml`, `as=raw` |
| `get` | | field values at a document path, or `field=<a.b.c>` |
| `find` | `grep` | search `tag=<name>`, `value=<text>` or `path=<a/b>` across the selection |
| `stats` | | counts by category, root element and storage format |
| `refs` | `graph` | outgoing references of the selection, grouped by kind |
| `deps` | | incoming references of `value=<token>` (who points at it) |
| `check` | `lint` | load everything; report load errors, warnings and dangling references |
| `schema` | | the declared fields of one root element, or one enum table; read-only (§4.13) |
| `verify` | | read every selected document back and report what does not survive; read-only (§4.11) |
| `build` | `to=` | index, check and pack in one run; stops at the first step that fails (§4.17) |
| `audit` | | verify every document, then check with both gates on; read-only (§4.17) |
| `adopt` | `<tree or zip>` `to=` | import a tree or zip as a project, then index it (§4.17) |
| `unpack` | `to=` | write the project back out as the original XML and text (§4.17) |
| `run` | `<steps.toml>` | run the steps the file lists, in order (§4.17) |
| `diff` | | compare two documents, or two trees lined up by entity path; read-only (§4.10) |
| `roster` | | read the rosters the settings declare, or check the entries against the documents; `op=` needs `--write` (§4.14) |
| `set` | | change one field of one document, or add and delete array entries; needs `--write` (§4.1) |
| `batch` | | apply the edits of a patch file, in order, to many documents; needs `--write` (§4.15) |
| `init` | | create a project: `ModInformation.toml` and an empty `Data/`; needs `--write` (§4.9) |
| `import` | | make a project out of a mod that already exists, a directory or a zip; needs `--write` (§4.16) |
| `add` | `new` | create one entity document, from the schema skeleton or `from=<path>`; needs `--write` (§4.5) |
| `clone` | | copy one entity document under a new token, from this project or from another scope; needs `--write` (§4.12) |
| `remove` | `rm` | delete one entity document; needs `--write` (§4.5) |
| `index` | | write `EditorCache/index.toml` and `EditorCache/refs.toml`; needs `--write` (§4.6) |
| `settings` | | translate between the project's stock `mod.txt` and `ModSetting.toml`; needs `--write` (§4.7) |
| `pack` | | build `<name>-<version>.zip` from the project; needs `--write` (§4.8) |
| `convert` | | turn the selection into project working files under `to=<dir>`; needs `--write` (§4.3) |
| `log` | | the log segments and the records inside them, with filters; read-only (§4.2) |
| `undo` | | put back what the last writes replaced; needs `--write` (§4.2) |
| `redo` | | re-apply what the last undo reverted; needs `--write` (§4.2) |
| `export` | `emit` | write the selection as stock XML under `to=<dir>`, source bytes for files read from disk |
| `web` | `serve` | serve the pages on `127.0.0.1` until Ctrl-C (§4.4, docs/web.md) |
| `version` | | editor version, interpreter, resolved scopes |

Options: `root=`, `workspace=`, `to=` (the `export` destination, the project `convert`
writes into, the directory `pack` leaves the archive in — §4.8 — or the project `import`
creates, §4.16), `as=` (the reading form
for `show`, the entity token for `clone` — §4.12), `into=` (the scope directory an imported
`clone` writes under, §4.12), `enum=` (`schema` prints the fields that use one enum, §4.13),
`field=`,
`type=`, `kind=`, `path=`, `left=`, `right=` (the two sides of `diff`, §4.10), `name=` (the mod name `init` writes, §4.9), `op=`, `from=` (an
index for `set op=append`, a document path for `add`), `limit=` (default 200 rows; `0` prints
every row), `document=`, `actor=`, `result=`, `since=`, `until=` (`log` filters, §4.2),
`lang=zh|en` (the web UI language, §4.4), `section=` (the roster entries under one group comment
or one trailing note, §4.14), `line=` (the physical line a `roster op=` writes at, deletes or
rewrites, §4.14), `strict=1` (`pack` refuses to write while the
project has load errors or dangling references, §4.8), `assets=1` (`convert` also copies the
scope's `Images/` and `Sounds/` trees, §4.3; `check` names the file a missing image or sound
would have to be, §6), `rosters=1` (`check` also compares the rosters against the documents,
§4.14), `against=<root>` (`check` answers references this project does not hold from a second
root — a scope name, `scope:path`, or a directory, §6), `ignore_case=1`, `overwrite=1` (`1` replaces a file, or a whole project, that is already there,
`0` leaves it; `export` and `pack` replace by default, `convert` and `settings` skip by
default; `import` needs one of the two when the destination is already a project, §4.16), `--json`. `init`, `import`, `set`, `batch`, `add`, `clone`, `remove`, `index`, `settings`,
`convert`, `pack`, `roster`, `undo` and `redo` also take the bare flags `--write` (write the
change) and `--dry-run` (report it without writing anything, §4.1, §4.3); `undo` and `redo` take
an optional count as well (§4.2).
Unknown options, unknown scopes and missing paths are usage errors. `key=value` options may
appear in any order; `--json` may appear anywhere.

`web` adds five options of its own: `port=` (an explicit port; without it a recorded instance
is reused or the first free port at or above 8765 is taken, §4.4), `token=<text>` (required
in every URL as `?t=<text>` when set), `pagesize=` (default 200 rows per page),
`lang=zh|en` (the language every page starts in; a page follows `?lang=` from then on,
§4.4) and `browser=1` (open the default browser instead of only printing the address).

### 4.1 Writing one field

```
python -m core.cli Mod set <document> field=<a.b.c> value=<text> --write [--dry-run]
python -m core.cli Mod set <document> field=<array> op=append [from=<n>] --write [--dry-run]
python -m core.cli Mod set <document> field=<array>.<n> op=delete --write [--dry-run]
```

* `field=` is a dotted path inside the document, relative to its root element. A repeated
  element or array needs an index segment, for example `ammo.type.0.flavour`; without it an
  ambiguous path is refused rather than guessed. `get` reads the same paths, so
  `field=ammo.type.1.name` returns the name of the second entry.
* The field must be declared by the schema of the document root, and the value must fit it: a
  boolean accepts `yes`/`no` (written in the document's own spelling), a number is written in
  the style the field already uses, and a string is written verbatim.
* An enumerated value comes from the table that ships with the editor
  (`tools/FirefightModPackager/enums_ext.txt`) or from a document of the same project; a value
  no table and no document declares is refused, and a field with no table is written without
  an enum check.
* Fidelity: a `.txt` document is re-rendered by the same layout-preserving writer `export`
  uses, and a `.toml` document is rewritten on the value's own source line. Sibling lines,
  comments, blank lines and the file's newline style survive, and a trailing `//` comment on
  the edited leaf survives too.
* Atomic: the new bytes go to a sibling temporary file and `os.replace` moves them over the
  original, so no half-written document is observable.
* Locked: the write holds `EditorCache/lock` for its duration. A lock another writer holds
  refuses the second writer instead of interleaving, is never removed by a process that did
  not create it, and a stale lock is reported rather than stolen.
* Guarded: a document that changed on disk after the change was staged is refused instead of
  overwritten.
* Refusals are final — nothing is retried, and the file, the lock and `EditorCache/` stay as they
  were. `set` without `--write`, a write aimed at the `Firefight` scope, an unknown field, a
  value of the wrong type and a held lock all exit with code 2; a value the document encoding
  cannot hold exits with code 1.
* `--dry-run` computes and reports the whole result without writing anything, not even
  `EditorCache/` itself.
* `op=append` adds one entry to an array of tables named by `field=`; `from=<n>` copies the
  leaves of the existing entry `n` into the new one instead of writing empty values.
  `op=delete` removes the entry named by the index segment. Both work on the source lines, so
  every other line, comment, blank line and the file's newline style keeps its bytes.

### 4.2 The event log, undo and redo

```
python -m core.cli Mod log [count] [document=<text>] [field=<text>] [actor=cli|mcp]
                       [result=set|add|remove|undo|redo] [since=<stamp>] [until=<stamp>] [--json]
python -m core.cli Mod undo [count] --write [--dry-run] [--json]
python -m core.cli Mod redo [count] --write [--dry-run] [--json]
```

* Every write appends one record to `EditorCache/log/<segment start local time>.jsonl` and stores
  the bytes it replaced and the bytes it left under `EditorCache/baseline/<sha256>`. The record
  names the change (`id`, `segment`, `timestamp`, `actor`, `result`, `target`, `document`,
  `entity`, `field`, `before`, `after`, `digest_before`, `digest_after`, `bytes_before`,
  `bytes_after`, `dry_run`); `result` is `set`, `add`, `remove`, `undo` or `redo`, and the field
  list and the byte layout are in docs/project-layout.md §8.
* A segment is sealed after five idle minutes and the next record opens a new one, so segment
  files read in filename order are in chronological order. `log` lists the segments and the
  newest `count` records (default 20), and it is read-only: it creates nothing.
* `log` also filters. `document=` and `field=` keep a record whose value contains the text,
  `actor=` and `result=` keep the ones that are exactly equal, and `since=`/`until=` keep the
  records whose timestamp falls in the interval. The timestamps are compared as written, so a
  `since=` shares the offset of the machine that wrote the log. The payload names the filters it
  applied, and the counts say how many records passed out of how many were read.
* `undo [count]` restores the recorded bytes of the last `count` applied changes (default 1),
  newest first, and appends one record per revert naming the change it reverted. `redo [count]`
  re-applies the most recently reverted changes. A revert of a revert is what `undo` after
  `redo` is, so `undo` → `redo` → `undo` returns byte-identical content. Undoing an `add`
  deletes the document again, and redoing it writes the recorded bytes back.
* The whole invocation is planned before anything is written: a missing baseline, a document
  that changed on disk after the recorded change, a document that is gone, a count larger than
  the log and a log with nothing to revert are all refused with code 2, and no part of the
  invocation is written. Recorded bytes that are gone or no longer hash to their name are a
  hard failure with code 1.
* `undo` and `redo` need `--write`, hold the same `EditorCache/lock` as `set`, refuse the
  `Firefight` scope, and are confined to the project directory. A refusal is final and nothing
  is retried. `--dry-run` reports the restores without holding the lock, without touching
  `EditorCache/` and without writing a document.
* A new `set` discards what could be redone, as a fresh edit does in an editor.

### 4.3 Turning stock files into project working files

```
python -m core.cli Firefight convert to=<project> --write [--dry-run] [assets=1] [type=<category>] [--json]
```

* The selection is read from the scope and written under `<project>/<relative path>` with
  the suffix replaced by `.toml`. A destination whose own last segment is already `Mod` is
  used as it stands. Missing directories are created, so `convert` is the one command that
  establishes a project directory out of the game data; no `ModInformation.toml` is written, because the
  metadata of a project is the author's to fill in (docs/project-layout.md §3).
* A file that is already there is skipped and counted; `overwrite=1` replaces it. Files that
  are not entities are skipped and counted too. The plain-text tables are the ones the
  project's settings name: `<equipment>` and `<surnames>` in `mod.txt`, or the same keys
  in `ModSetting.toml` when that file is the one the project carries. A name declared there
  is a table whatever the file holds (`Data/news_main.txt` is one). A scope that declares
  nothing — the stock scope has no `mod.txt` — falls back to the name conventions
  (`equipment_*`, `surnames_*`), and a `.txt` with no root element is a table by its content.
* Output is UTF-8 without BOM with CRLF line endings, the canonical layout of the TOML writer,
  so the result is not byte-identical to the stock `Data/*.txt` it came from. Byte-for-byte
  reproduction is what `export` is for, not `convert`.
* Without `--write` the command is a usage error (code 2). `--dry-run` reports the same plan
  and writes nothing, not even the destination directory.
* `assets=1` also copies the scope's `Images/` and `Sounds/` trees into `<project>/`,
  byte for byte, under the same skip rule (`overwrite=1` replaces). Off by default, because
  the stock scope's two trees are the game's own artwork and sound: a mod that ships
  replacements should name the scope that holds them (a project scope) or pass `assets=1`
  deliberately. The pack of §4.8 then carries them like any other unmanaged file.
* The exit code is 1 when at least one file failed to convert, 0 otherwise.
* `convert` writes documents that have no recorded version yet, so it appends no event-log
  record and takes no `EditorCache/lock`; `EditorCache/` is not created either. Two gaps follow: the
  files it writes cannot be reverted with `undo`, and a concurrent `set` is not excluded.

### 4.4 The web UI and the running-instance record

```
python -m core.cli Mod web [port=<n>] [token=<text>] [pagesize=<n>] [browser=1]
```

* An explicit `port=` always starts a server on that port. Without one, a recorded instance
  that still answers is reused: its address is printed, its page is opened when the caller
  asked for a browser, and the process returns at once, so a second backend never starts by
  accident. Otherwise the first free port at or above 8765 is taken.
* The running instance is recorded in `<editor folder>/EditorCache/web.json`, or under the project
  directory when no editor folder is recognised: `pid`, `host`, `port`, `url`, `scope`, `token`
  and `started`. A clean stop removes the record. A record left behind by a killed process is
  stale, and the probe of its address decides, so a crashed UI never keeps the next one from
  starting — the launcher presents the same rule (`tools/launcher/ff-tool.ps1`).
* A page may run a writing command, and the command's own gate stays the final word: the page
  passes `write=1` on for the commands that take it, and a refusal reads exactly as it does on
  the command line. `web` is refused inside a request, because it would try to bind a second
  port (docs/web.md §3).
* Every page is Chinese unless `lang=en` is given or the URL carries `?lang=en`; the switch in
  the navigation bar keeps the current route and rewrites only the language. A page in one
  language links to the same page in the other (`core/web/i18n.py`).

### 4.5 Creating and deleting a document

```
python -m core.cli Mod add <document> [from=<path>] --write [--dry-run]
python -m core.cli Mod remove <document> --write [--dry-run]
```

* `add` writes one new entity document. Without `from=` the body comes from the schema
  skeleton of the root element the folder carries (`Data/Weapons` is `weapon`; `Data/Infantry`,
  `Data/Vehicles` and `Data/AT Guns` are all `squad`; `Data/Aircraft` is `aircraft`); a folder
  the editor cannot map is refused, and `from=<path>` is then the way to say what the document
  is. With `from=` the named document's bytes are re-rendered into the new file, so a `.txt`
  source becomes a `.toml` one.
* `remove` deletes one entity document.
* Both write UTF-8 without a BOM and CRLF, take the project lock, and append one event
  (`result` is `add` or `remove`); `undo` brings a deleted document back byte for byte and a
  reverted `add` deletes the file again. Neither writes anything outside the project.
* `add` refuses a path that is already there, `remove` refuses one that is not, and both refuse
  the `Firefight` scope.

### 4.6 The reference index

```
python -m core.cli Mod index [selector] --write [--dry-run]
```

* `index` walks the selection once and writes `EditorCache/index.toml` (a `[documents]` table
  mapping each relative document path to its root element) and `EditorCache/refs.toml` (a
  `[by_source]` table mapping each document to the tokens it points at). A `[built]` table in
  both files records when the index was written, the scope, the counts, and one fingerprint of
  the scope.
* The fingerprint is the SHA-256 of the relative name, size and write time of every file that
  was read; it is one digest for the whole scope, not one per document. A document that gains,
  loses or changes a byte produces a different fingerprint, and `refs` and `deps` then ignore
  both tables and walk the documents again. The payload says which of the two produced the rows
  (`origin` is `index` or `scan`), and the tables are a cache of one query, not a second source
  of truth.
* The plain-text tables — the names the project declares under `<equipment>` and `<surnames>`,
  and the `equipment_*` / `surnames_*` conventions — plus `.txt` files with no root element and
  unreadable files are counted as skipped; they are not errors.
* The entries of a declared **unit roster** (an `equipment_*` list) are references of kind
  `roster`, so the tables carry them beside the ones inside XML documents and `deps <unit>`
  answers from the index too. A surname list contributes nothing: it names people, not files
  (docs/refs.md §1).
* The web server reads both tables at start-up and rebuilds them in a background thread when the
  fingerprint no longer matches; the command itself is unchanged, and the pages fall back to
  walking the files if the rebuild fails (docs/web.md §1).

### 4.7 Translating between `mod.txt` and `ModSetting.toml`

```
python -m core.cli Mod settings --write [--dry-run] [op=render|emit] [overwrite=1]
```

* The editor carries the project's stock settings file (docs/project-layout.md §4) in two
  forms, and this command moves between them. `op=render`, the default, reads
  `<project>/mod.txt` and writes `<project>/ModSetting.toml`. `op=emit` reads
  `<project>/ModSetting.toml` and writes `<project>/mod.txt`.
* `render`: every element becomes its table or key, `<nationality>` blocks become
  `[[mod_setting.nationality]]` entries, the repeated `<equipment>` elements become one array
  per nation, the bare `<ranks>` numbers become quoted keys, and the nation names keep the
  exact spelling of the source (the shipped WW3 file spells them
  `Taiwan, China(In Production)` and `Japan(In Production)`, without a space before the
  bracket).
* `emit` is the exact inverse on a stock-shaped file: `Mod settings op=emit --write` over the
  shipped WW3 `mod.txt` reproduces all 10170 bytes unchanged. The element order, the tab
  indentation and the blank lines are the shape the stock files use, so a file already in that
  shape round-trips byte for byte. `render` does not keep the layout of a file written
  differently, so such a file comes back in this shape.
* Both directions are pure functions of their source, and both report what they could not
  carry rather than dropping it silently.
* An existing target is skipped unless `overwrite=1`. The target of `op=render` is the
  hand-editable `ModSetting.toml`, so `overwrite=1` discards those edits; `op=emit` replaces
  the stock file the game reads, so the same flag there is the one that reaches a release
  package. The shipped WW3 project shows the scale of `render`: its hand-written
  `ModSetting.toml` holds 79 lines and one nation, while the renderer produces 333 lines and
  all twelve from the same `mod.txt`, with no warnings.
* The stock scope `Firefight` is refused, since both targets live in a project. `op` must be
  `render` or `emit`; a missing source is refused (`nothing to <op> from: <path> is not
  there`).

### 4.8 Building the mod-zip

```
python -m core.cli Mod pack --write [--dry-run] [to=<directory>] [strict=1] [overwrite=1]
```

* The archive holds the layout the game installs (docs/project-layout.md §5): `Mod/`,
  `README.md` and `LICENSE`, taken from the project directory. The default destination is
  `<name>-<version>.zip` in the project directory; `to=<directory>` names another directory.
* Inside `Mod/`, a document that exists as TOML is written back as stock XML. `Mod/mod.txt`
  is rendered from `ModSetting.toml` when that file is there. Everything else, including
  `Images/` and `Sounds/`, is copied byte for byte: a file placed by hand arrives unchanged,
  and a document with only a TOML twin is emitted in canonical form (tabs, CRLF, UTF-8).
* Every pack runs the check of §4.3 first and the payload carries its counts
  (`check.errors`, `check.dangling`). A document that cannot be rendered is named in
  `errors`, left out of the archive, and the pack goes ahead.
* Below the member table the output names what was left out and what was reported: one
  `skipped: <path> (<reason>)` line per file that stayed out of the archive — including a
  `.txt` that a same-named TOML document covers — and one `warning: <text>` line per warning.
  The counts in the summary line are not the whole answer.
* `strict=1` turns both into refusals: the pack writes nothing while the project has a load
  error or a reference that does not resolve, so a package cannot ship either by accident.
  The reference graph is built over the project alone; the stock corpus is not consulted
  (see §9).
* Members are written with a fixed timestamp, so packing an unchanged project twice produces
  the same bytes.
* `pack` changes no document and takes no lock, but a pack that writes appends one `pack`
  record to the project log saying what was built. A `pack` record names no document and
  sits on neither the undo nor the redo stack, so nothing reverts it (docs/project-layout.md
  section 8). A `--dry-run`, a refused pack and one that skipped an existing archive leave
  no record.
* `pack` does refuse an on-disk `mod.txt` that disagrees with `ModSetting.toml`, because
  replacing that file would otherwise drop content the shorter of the two does not carry. The
  message names both sizes and both ways out: `settings op=emit --write overwrite=1` rewrites
  `mod.txt` from the settings file, which is the destructive one, while
  `settings op=render --write overwrite=1` rewrites the settings file from `mod.txt`.
* The stock scope `Firefight` is refused. `overwrite=1` replaces an archive that is already
  there; without it the file is skipped.

### 4.9 Creating a project

```
python -m core.cli Mod init --write [--dry-run] [name=<text>]
```

* `init` is the one command whose scope need not exist yet: `root=` or `workspace=` names the
  directory to create the project in, the working directory otherwise, and the directory is
  created when it is missing. Every other command resolves a scope that is already there.
* It writes `ModInformation.toml` from the schema skeleton (docs/project-layout.md §3) and an empty
  `Data/`. `name=` fills the mod name in, the directory name otherwise. The stock scope
  `Firefight` is refused: that installation is not a project.
* A directory that already carries a `ModInformation.toml` is refused, so an initialised project is never
  overwritten. Removing a project is a plain directory delete; `init` has no counterpart.
* The new `ModInformation.toml` is recorded like any other new document, so `Mod undo --write` takes the
  file away again. The empty `Data/` is a directory rather than a document, and no record
  reverts it.
* A list-typed leaf such as `authors` is written as `key = []`, which the reader accepts.

### 4.10 Comparing two documents or two trees

```
python -m core.cli Mod diff left=<scope:path> right=<scope:path> [limit=<rows>]
```

* `left=` and `right=` name the two sides. The `scope:` prefix is optional and defaults to the
  scope the command ran with, so `left=Firefight:Data/Weapons/X.txt right=Data/Weapons/X.toml`
  compares a stock file with the working file converted from it. A one-letter name before the
  colon is a drive letter, not a scope, so an absolute Windows path stays a path.
* Both sides are rendered as stock XML before the comparison, so a project `toml` and the stock
  `txt` it came from compare in the same shape rather than as two different syntaxes (§4.3).
* Two directories are lined up by entity path with the suffix dropped, so `X.txt` and `X.toml`
  are the same document; within one entity path the working file wins over the stock file. The
  report gives the count of identical documents, the ones that differ, and the ones only one
  side carries.
* The output is a unified diff of the two stock renderings, capped at `limit=` lines (default
  200; `limit=0` prints all of them).
* Exit code 1 means the two sides are not the same, 2 means the command could not compare them
  (a side that is not there, one file against one directory). A clean exit means every document
  lined up and matched.

### 4.11 Checking that a document survives being read and written

```
python -m core.cli Mod verify [selector] [limit=<rows>]
```

* Every selected document is read and written again, and the result is compared with what is on
  disk. Line endings are normalised first, so what a run reports is content the editor cannot
  reproduce rather than a difference in line endings.
* A stock XML file is compared with the layout the editor writes back, which is the layout the
  reader captured. A `toml` file is written back as stock XML, read again and compared as TOML,
  so a file the editor only edits in place is not reported for its layout.
* A plain-text table named by the project settings is never parsed, so it is reported as copied
  rather than compared (§4.3).
* The table lists only the documents that differ, with the first line that differs; `--json`
  carries `files`, `same`, `differ`, `items`, `shown` and `total`. Exit code 1 means at least one
  document does not survive the trip, 0 means every document round-trips.

### 4.12 Copying a document under a new token

```
python -m core.cli Mod clone <document> as=<Token> [into=<scope or directory>] --write [--dry-run]
```

* The command makes a document that has no source to copy from: it reads one entity document,
  sets the root table's own `name` to the new token and writes the result as `<Token>.toml` at
  the same relative path. Only the first table's direct keys are searched — a later `name`
  belongs to a sub-table or an array entry, and rewriting one of those would change something
  other than the name the document declares. A source that declares no name is refused rather
  than copied under the wrong token.
* `into=` names the destination scope: either a scope name, or a directory, which is read as a
  project root the same way `root=` is (§4.1). That is how a stock document becomes a project
  document — `clone Firefight:Data/Weapons/WEAPON_PISTOL_P38.txt as=WEAPON_PISTOL_P38
  into=<project> --write` reads the stock file, renders it as TOML and writes it into the
  project. Without `into=` the copy lands in the scope the command already resolved.
* A plain-text table named by the project settings is refused: `clone` copies an entity document
  (§4.3). The stock scope is never a destination. A destination that is already there is refused
  unless `overwrite=1`.
* `--dry-run` reports the destination and the byte counts without writing. `--json` carries
  `path`, `scope`, `source` (as `<scope>:<path>`), `into`, `format`, `bytes_before`,
  `bytes_after`, `existed_before` and `recorded`. The write is recorded as an `add`, so one
  `undo` removes the copy again (§4.2).

A project file is copied the same way, without `as=`: the source names
`ModInformation.toml` or `ModSetting.toml`, and `into=` names the project that receives it.

### 4.13 Reading the schema of a root element

```
python -m core.cli Mod schema <root element> [limit=<rows>]
python -m core.cli Mod schema enum=<name> [limit=<rows>]
```

* The first form lists the fields the editor declares for one root element, so a document can be
  filled in without guessing from a sample. Each row carries the dotted `path`, the `shape`
  (`leaf`, `table`, `array` or a list), the value `type`, whether the field is `required`, and
  the enum its values come from with the number of values. Children of an array node carry `[]`
  in their path (`weapon.ammo.type[].flavour`); the array node itself keeps its plain path.
* The second form lists one enum table's values, as the editor resolves them for the project —
  the project's own enum file when it has one, the built-in table otherwise. `--json` carries
  `enum`, `table` (whether the table was found), `count`, `shown`, `values` and `source`, the
  file the table came from.
* `schema` reads the same declaration the writer validates against, so a field it lists is a
  field `set` accepts (§4.1). It is read-only, and `limit=` caps the rows as everywhere else.

### 4.14 Reading and editing the rosters

```
python -m core.cli Mod roster [<roster>] [section=<text>] [limit=<rows>]
python -m core.cli Mod roster check [limit=<rows>]
python -m core.cli Mod roster <roster> op=add    value=<name> [line=<n>] --write [--dry-run]
python -m core.cli Mod roster <roster> op=set    line=<n> as=<name>     --write [--dry-run]
python -m core.cli Mod roster <roster> op=remove value=<name> [line=<n>] --write [--dry-run]
```

A roster is one of the plain-text tables the project's settings declare (§4.3): one entry per
line, the entry is the name of a document under `Data/`, and `//` starts a comment — the whole
line, or a note trailing the entry. A line that is only a comment names the group the entries
after it belong to, which is why rewriting an entry keeps its note and the note stays the group
the entry sits in.

* Without a selector, `roster` lists the declared rosters with their entry counts. With one it
  lists the entries, each with the physical `line` a reader sees in an editor, the `group` from
  the comment above it and its trailing `note`. The selector may be a relative path, a file name
  or a file stem; a name the settings do not declare is a usage error.
* `section=<text>` keeps the entries whose group comment or trailing note is that text, so
  `section=tanks` finds the entries noted `// tanks` under a `// vehicles` comment.
* `roster check` compares both directions and exits 1 when either side is not empty. `missing`
  pairs a roster with an entry no document answers — the game shows that as a missing unit;
  `orphans` names a unit no roster lists, which is a document the game cannot reach, and carries
  its `path`. Only units count as orphans: a weapon or an engine sound is pulled in by the
  document that uses them, so counting those would report every one of them.
* The entries are also part of the reference graph (§4.6): a unit an `equipment_*` list names
  but no document answers is reported by `check` as a dangling reference of kind `roster`, and
  `deps <unit>` names the roster and the line that lists it.
* The three writes are `op=add` (append the entry, or insert it at `line=`), `op=set` (replace
  the entry on `line=` with `as=<name>`, or replace the one named by `value=`) and `op=remove`
  (drop the entry named by `value=` or the line given as `line=`). Each is planned and then
  applied through the same writer as every other change, so it is journalled, `undo` puts the
  bytes back, and `--dry-run` reports the change without writing. A dry run still needs
  `--write`, as everywhere else.
* The file's encoding, byte-order mark and line endings are kept: an entry is written with the
  ending the file already uses, and the rest of the file is untouched.

### 4.15 `batch` — several edits in one run

```
python -m core.cli Mod batch <patch.toml> --write [--dry-run] [--json]
```

A patch is a TOML file holding an array of `[[edit]]` entries. Each entry names the document, the
field and what to do:

```toml
[[edit]]
document = "Data/Weapons/WEAPON_PISTOL_P38.toml"
field = "name"
value = "P38 Neu"

[[edit]]
document = "Data/Weapons/WEAPON_PISTOL_P38.toml"
field = "ammo.type"
op = "append"
```

* `document` accepts what any selector accepts: a relative path, a file name or a file stem, and
  it must name exactly one document.
* `value` is required by `op = "set"`, which is the default; `op = "append"` and `op = "delete"`
  are the array-of-tables operations of §4.1, and `from=0` copies an existing entry the way
  `set op=append from=0` does.
* Entries are applied in the order they appear, and later entries to the same document are
  planned against the text the earlier ones would leave behind, so the `before` and `after` of
  every row name what that edit really changes.
* Nothing is written unless every entry plans: the first entry that cannot be planned stops the
  run, the message names it (`patch.toml: [[edit]] 2: ...`), and no document is touched. A run
  that succeeds writes each document once and records one journal record per document, so
  `undo <n>` puts every document it wrote back.
* `--dry-run` reports the rows, the planned byte counts and the documents without writing. It
  still needs `--write`, as everywhere else.
* The payload carries `patch`, `edits`, `documents`, `rows` (`edit`, `document`, `field`, `op`,
  `before`, `after`, `bytes`) and `written`, the same per-document report `set` returns.

### 4.16 `import` — make a project out of a mod that already exists

```
python -m core.cli Mod import <directory or zip> to=<dir> --write [--dry-run] [--json]
```

`init` (§4.9) makes an empty project; `import` makes one from a mod that already exists, which is
the other half of the import/export pair. The source is a directory or a `.zip`, and the mod root
inside it is found the way the packager looks for it: everything under `Mod/`, the mod root at the
top of the source, or one directory of its own above that — which is how an extracted archive
usually looks.

* `Data/`, `Images/` and `Sounds/` are copied byte for byte, as are `mod.txt`, `README.md`,
  `LICENSE`, `ModInformation.toml` and `ModSetting.toml` when the source carries them.
  `EditorCache/` and anything hidden is left behind: it belongs to the editor, not to the mod.
* `ModSetting.toml` is rendered from the source's `mod.txt` when the source does not already
  carry one, the same translation `settings op=render` performs (§4.7).
* `ModInformation.toml` is written from the schema skeleton, named after the destination
  directory, when the source does not already carry one.
* The destination must hold no `ModInformation.toml` unless one of the two overwrite values is
  given: `overwrite=1` replaces what is there, `overwrite=0` keeps every file that is already
  there and reports each one as `exists`.
* A source with no `Data/` folder inside is refused, and so is a source that is not there.
* No journal record is written per copied file: several thousand records would drown the log, and
  the copied bytes are still in the source. The rendered `ModSetting.toml` and the written
  `ModInformation.toml` do go through `core.edit` and are recorded like any other write.
* The payload carries `source`, `root` (the prefix inside the source that held the mod), `to`,
  `overwrite`, `dry_run`, `count`, `shown` (`path`, `bytes`), `files` (how many files the source
  offered), `has_settings`, `skipped` and `errors`.

### 4.17 `build`, `audit`, `adopt`, `unpack` and `run` — one call for a whole sequence

The four workflows that used to take several invocations each now have one command, and a
fifth runs any list of steps:

```
ff Mod build to=<directory> --write [--dry-run]
ff Mod audit [--json]
ff Mod adopt <tree or zip> to=<directory> --write [--dry-run] [overwrite=1]
ff Mod unpack to=<directory> --write [--dry-run] [overwrite=1]
ff Mod run <steps.toml> --write [--dry-run] [--json]
```

`build` runs `index`, then `check`, then `pack`. `audit` runs `verify`, then `check` with
`assets=1 rosters=1`. `adopt` runs `import`, then `index` on the project it just wrote.
`unpack` runs `export`, preceded by `settings op=render --write` when the project carries a
`mod.txt`.

Every step is an ordinary command call, so it is logged, gated and reversible exactly as it
would be on its own. A step that reports a failure stops the run and the summary names it;
the steps before it have already happened, and `undo` reverses them. `--dry-run` switches
each step to its own dry run and changes nothing.

`run` takes a TOML file:

```toml
[[step]]
command = "set"
selector = "Data/Weapons/WEAPON_PISTOL_P38.toml"
with = ["field=name", "value=P38 Carbine"]

[[step]]
command = "check"
```

`command` must be one of the commands above; `selector` is the document or element the step
works on; `with` is a list of `key=value` options. The same rule applies: the first failing
step stops the run.

## 5. Exit codes

| Code | Meaning |
|---|---|
| 0 | the command ran and found nothing to report |
| 1 | `check` found load errors, dangling references or warnings; **or** `roster check` found an entry with no document or a unit no roster names (§4.14); **or** a parse/IO error aborted the command (the message names the file and, where known, the line); **or** a recorded document version is unreadable (§4.2); **or** at least one file failed to convert (§4.3) |
| 2 | usage error: unknown scope or command, missing or unknown option, unresolvable path, and every refused write (§4.1, §4.2, §4.3, §4.9) |
| 130 | interrupted (Ctrl-C) |

## 6. Warnings

Warnings never fail a load, and `check` reports them as counts plus up to 20 samples. The
four kinds seen on real data: `//` comments removed, a file decoded as UTF-8 rather than
cp1252, an unknown element kept as a leaf, and text inside an element that also holds
children (dropped on export — see the `</data>>` typos in the WW3 project).

`check` prints every sampled warning as its own row in the issue table, so the counts in the
summary line and the rows below it agree; `warning_samples`, `warnings_shown`, `dangling`,
`dangling_shown` and `truncated` in the payload say the same for a reader that does not see
the table. `limit=` (20 by default, `limit=0` for every row) caps how many documents and
references are listed, and a capped table ends with a row saying how many rows were left out.

Three options widen the check. `assets=1` writes the file a missing image or sound would have
to be (`missing Images/**/x.png`) in place of the value that did not match, which is what an
imported project needs to fill in; `assets_missing` counts them in the payload. `rosters=1`
folds the two-way roster comparison of §4.14 into the same table and the same exit code, and
the payload carries its three counts under `rosters`. `against=<root>` answers a reference the
project itself does not hold from a second root — the stock installation for an imported
project, given as a scope name, `scope:path`, or a directory — so a reference that resolves
there is not dangling; the payload reports how many were answered that way
(`dangling_answered_elsewhere`) and which root answered (`against`). `against=stock` names the
installation the editor setting points at, which is what an imported project wants. Measured on
WW3 with the stock root as `against=`: 911 dangling references become 29, with 882 answered by
the other root, and 235 of the 911 want an asset file that is not in the project. When more than
one kind is dangling, the summary also names the counts by kind and the payload carries them
under `dangling_kinds`.

The entries of a declared unit roster are references (§4.6), so a unit an `equipment_*` list
names but no document answers appears as an ordinary dangling reference of kind `roster`, with
the line it sits on as its `document_path`. Without that, a roster entry pointing at a unit
that does not exist would be invisible to `check` unless `rosters=1` was given. Measured on
WW3: 276 roster entries over 12 rosters, none of them unresolved, so the count stays at 911.

## 7. Measured on real data (2026-10-10)

Stock game 13.2.0.0 vs the released WW3 mod project (`.Mod/`, extracted outside this
repository):

| Command | Stock | WW3 |
|---|---|---|
| `stats` | 1840 files, 48 list files, 0 errors, 0.6 s | 765 files, 13 list files, 0 errors, 0.2 s |
| `check` | loaded 1792, skipped 48, 0 errors, 612 warnings, **2 dangling** | loaded 752, skipped 13, 0 errors, 559 warnings, **911 dangling** |
| `refs` | 23978 references, 0 errors, 4.3 s | 5793 references, 0 errors, 0.4 s |

`export` of the stock `Vehicles` selection writes 599 files and 2371815 bytes with 0
errors. Reference rules and coverage are in [refs.md](refs.md).

Measured again on 2026-10-11, after the writer learned to keep the source layout:
`python tools/export_fidelity.py --data "<Firefight>/Data"` exports all 1840 stock files
and reports **1840 identical, 100.0%** (before, 1792 of them came back with reordered
siblings and 12 with different newlines).

The two stock dangling references are in the shipped data (`WEAPON_PISTOL_WZ_35_VIS` from
`Hungarian-TK3.txt` and `Hungarian-TKS.txt`). The 911 in WW3 are mostly references into
stock data: when a mod project is checked with the stock installation as a second scope,
882 of the 912 resolve. **That fallback is measured but not implemented** — the CLI
resolves each scope on its own, and cross-scope resolution arrives with the workspace
registry.

## 8. Reproducing the demo

```
python -m unittest discover -s tests -t .                       # run the suite
python -m core.cli Firefight stats  "root=<Firefight>"
python -m core.cli Firefight check  "root=<Firefight>" --json
python -m core.cli Firefight refs   "root=<Firefight>" --json --limit 5
python -m core.cli Firefight deps   "value=WEAPON_PISTOL_P38" "root=<Firefight>"
python -m core.cli Firefight export Vehicles "root=<Firefight>" "to=<somewhere>"
python -m core.cli Firefight convert "root=<Firefight>" "to=<new project>" --write --dry-run
python -m core.cli WW3 stats "root=<extracted WW3>/.Mod"
python -m core.cli Firefight web    "root=<Firefight>" port=8765
```

`check` exits 1 on both corpora, which is the intended report and not a crash. `deps` is
scope-wide: it answers for one scope at a time. `convert` on the installed game plans 1792
files and skips 48 list files; without `--dry-run` it writes them. `web` blocks until Ctrl-C
and prints the address it bound.

## 9. Limits of this slice

* A write is one field, one array entry, one document (`add`, `remove`) or one whole selection
  (`convert`, `settings`, `index`, `pack`). `batch` (§4.15) applies several changes to several
  documents in one invocation, but the patch is written as text and each document is still
  written as a whole. The log and the baseline are per project, and `Firefight` is never written.
* `pack` builds the mod-zip. The stock-baseline comparison and the APK packaging of
  docs/project-layout.md §5 are not implemented. `init` (§4.9) writes a `ModInformation.toml`
  and an empty `Data/`; it reads no template and imports nothing from the stock data.
  `Mod/mod.txt` in the archive comes from `ModSetting.toml` when that
  file is there; without it the existing `Mod/mod.txt` is copied as it stands.
* `add` writes the schema skeleton of the document root, which leaves arrays out (their empty
  form would not be readable back); a document that needs array entries is created with
  `from=<an existing document>` or with `convert`, and its arrays are filled in with
  `set op=append` afterwards.
* Only the roots the editor declares a schema for can be created and edited: `weapon`, `squad`,
  `aircraft`, `mod` and `mod_setting`. The `vehicle` and `at_gun` folders carry a `squad` root,
  which is covered too.
* `EditorCache/index.toml` and `EditorCache/refs.toml` are now written by `index`; they are a cache
  with a whole-scope fingerprint, so one changed byte sends `refs` and `deps` back to the scan.
* `settings` translates between the project's stock `mod.txt` and `ModSetting.toml` in
  either direction. A project without the source file of the requested direction cannot be
  translated, and a source element the renderer does not know is kept as a plain value rather
  than interpreted. `emit` writes XML by hand, so a value carrying a character the stock form
  cannot hold literally is reported and left out of that element.
* `export` keeps the source layout: sibling order, blank lines, indentation, `//` comments
  and the file's own newline style all come from the source text (toml-mapping §4). Files
  without source text — a `.toml` project document — use the canonical writer instead
  (tab indent, CRLF, schema order), and an edit invalidates the layout of the element it
  touches for as long as it is applied in memory.
* `pack` writes the `Data/` documents and the project's `README.md`/`LICENSE`. `Images/` and
  `Sounds/` are copied when they are already in the project directory; `convert assets=1`
  (§4.3) is what brings them in, and a file that was never imported simply is not in the
  archive. The pack summary does not say what is missing.
* `init` writes `ModInformation.toml` and an empty `Data/` only. It does not import stock data (`convert`
  does that, §4.3), does not write `ModSetting.toml` (`settings op=render`, §4.7), and does not
  read a template from anywhere else.
* Whether the engine accepts a file we re-emit is verified by an in-game load check, not here.
* `Maps/`, `Surnames/` and `equipment_*` are out of scope.
* Modules are not loaded through `mod.txt` yet; a mod is a directory with `Data/`.

