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
| `Mod` | the mod project the current directory belongs to | `root=`/`mod=` option, else `mod` in the local config, else nearest ancestor with `mod.toml`; data lives under `Mod/` when present, otherwise at the project root |
| `Firefight` | the stock game data | `root=`/`firefight=` option, else `FIREFIGHT_DATA`, else `firefight` in the local config found upwards, else the copy shipped with the editor |
| `<name>` | another mod folder in the workspace | a directory of that name, else `<workspace>/Mods/<name>`, else `<workspace>/<name>`; workspace from `workspace=<dir>`, else `FIREFIGHT_MODS`, else the local config, else the current directory |

A scope root is the directory that holds `Data/`, `Images/` and `Sounds/`; passing the
`Data` directory itself is accepted and normalized to its parent. For an installed game
that is the directory containing `Firefight.exe`. The `Firefight` scope is never written:
the editor does not edit the game directory, and `export` writes only under `to=`. A project
is written only by `set`, `undo` and `redo` with `--write`, and only inside the project
directory (§4.1, §4.2). The local config `.ff-editor.local.toml` (keys `firefight`, `mod`,
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
| `set` | | change one field of one document; needs `--write` (§4.1) |
| `convert` | | turn the selection into project working files under `to=<dir>`; needs `--write` (§4.3) |
| `log` | | the log segments and the newest records inside them; read-only (§4.2) |
| `undo` | | put back what the last writes replaced; needs `--write` (§4.2) |
| `redo` | | re-apply what the last undo reverted; needs `--write` (§4.2) |
| `export` | `emit` | write the selection as stock XML under `to=<dir>`, source bytes for files read from disk |
| `web` | `serve` | serve the pages on `127.0.0.1` until Ctrl-C (§4.4, docs/web.md) |
| `version` | | editor version, interpreter, resolved scopes |

Options: `root=`, `workspace=`, `to=` (the `export` destination, or the project `convert`
writes into), `as=`, `field=`, `type=`, `kind=`, `path=`, `limit=` (default 200 rows),
`ignore_case=1`, `overwrite=1` (`convert`: replace a working file that is already there),
`--json`. `set` and `convert` also take the bare flags `--write` (write the change) and
`--dry-run` (report it without writing anything, §4.1, §4.3); `undo` and `redo` take
`--write` and an optional count (§4.2).
Unknown options, unknown scopes and missing paths are usage errors. `key=value` options may
appear in any order; `--json` may appear anywhere.

`web` adds four options of its own: `port=` (an explicit port; without it a recorded instance
is reused or the first free port at or above 8765 is taken, §4.4), `token=<text>` (required
in every URL as `?t=<text>` when set), `pagesize=` (default 200 rows per page) and
`browser=1` (open the default browser instead of only printing the address).

### 4.1 Writing one field

```
python -m core.cli Mod set <document> field=<a.b.c> value=<text> --write [--dry-run]
```

* `field=` is a dotted path inside the document, relative to its root element. A repeated
  element or array needs an index segment, for example `ammo.type.0.flavour`; without it an
  ambiguous path is refused rather than guessed.
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
* Locked: the write holds `.editor/lock` for its duration. A lock another writer holds
  refuses the second writer instead of interleaving, is never removed by a process that did
  not create it, and a stale lock is reported rather than stolen.
* Guarded: a document that changed on disk after the change was staged is refused instead of
  overwritten.
* Refusals are final — nothing is retried, and the file, the lock and `.editor/` stay as they
  were. `set` without `--write`, a write aimed at the `Firefight` scope, an unknown field, a
  value of the wrong type and a held lock all exit with code 2; a value the document encoding
  cannot hold exits with code 1.
* `--dry-run` computes and reports the whole result without writing anything, not even
  `.editor/` itself.

### 4.2 The event log, undo and redo

```
python -m core.cli Mod log [count] [--json]
python -m core.cli Mod undo [count] --write [--json]
python -m core.cli Mod redo [count] --write [--json]
```

* Every written `set` appends one record to `.editor/log/<segment start local time>.jsonl` and
  stores the bytes it replaced and the bytes it left under `.editor/baseline/<sha256>`. The
  record names the change (`id`, `segment`, `timestamp`, `actor`, `result`, `target`,
  `document`, `entity`, `field`, `before`, `after`, `digest_before`, `digest_after`,
  `bytes_before`, `bytes_after`, `dry_run`); the field list and the byte layout are in
  docs/project-layout.md §8.
* A segment is sealed after five idle minutes and the next record opens a new one, so segment
  files read in filename order are in chronological order. `log` lists the segments and the
  newest `count` records (default 20); it is read-only and creates nothing.
* `undo [count]` restores the recorded bytes of the last `count` applied changes (default 1),
  newest first, and appends one record per revert naming the change it reverted. `redo [count]`
  re-applies the most recently reverted changes. A revert of a revert is what `undo` after
  `redo` is, so `undo` → `redo` → `undo` returns byte-identical content.
* The whole invocation is planned before anything is written: a missing baseline, a document
  that changed on disk after the recorded change, a document that is gone, a count larger than
  the log and a log with nothing to revert are all refused with code 2, and no part of the
  invocation is written. Recorded bytes that are gone or no longer hash to their name are a
  hard failure with code 1.
* `undo` and `redo` need `--write`, hold the same `.editor/lock` as `set`, refuse the
  `Firefight` scope, and are confined to the project directory. A refusal is final and nothing
  is retried.
* A new `set` discards what could be redone, as a fresh edit does in an editor.

### 4.3 Turning stock files into project working files

```
python -m core.cli Firefight convert to=<project> --write [--dry-run] [type=<category>] [--json]
```

* The selection is read from the scope and written under `<project>/Mod/<relative path>` with
  the suffix replaced by `.toml`. A destination whose own last segment is already `Mod` is
  used as it stands. Missing directories are created, so `convert` is the one command that
  establishes a project directory out of the game data; no `mod.toml` is written, because the
  metadata of a project is the author's to fill in (docs/project-layout.md §3).
* A file that is already there is skipped and counted; `overwrite=1` replaces it. Files that
  are not entities are skipped and counted too — the list files such as `mod.txt`.
* Output is UTF-8 without BOM with CRLF line endings, the canonical layout of the TOML writer,
  so the result is not byte-identical to the stock `Data/*.txt` it came from. Byte-for-byte
  reproduction is what `export` is for, not `convert`.
* Without `--write` the command is a usage error (code 2). `--dry-run` reports the same plan
  and writes nothing, not even the destination directory.
* The exit code is 1 when at least one file failed to convert, 0 otherwise.
* `convert` writes documents that have no recorded version yet, so it appends no event-log
  record and takes no `.editor/lock`; `.editor/` is not created either. Two gaps follow: the
  files it writes cannot be reverted with `undo`, and a concurrent `set` is not excluded.

### 4.4 The web UI and the running-instance record

```
python -m core.cli Mod web [port=<n>] [token=<text>] [pagesize=<n>] [browser=1]
```

* An explicit `port=` always starts a server on that port. Without one, a recorded instance
  that still answers is reused: its address is printed, its page is opened when the caller
  asked for a browser, and the process returns at once, so a second backend never starts by
  accident. Otherwise the first free port at or above 8765 is taken.
* The running instance is recorded in `<editor folder>/.editor/web.json`, or under the project
  directory when no editor folder is recognised: `pid`, `host`, `port`, `url`, `scope`, `token`
  and `started`. A clean stop removes the record. A record left behind by a killed process is
  stale, and the probe of its address decides, so a crashed UI never keeps the next one from
  starting — the launcher presents the same rule (`tools/launcher/ff-tool.ps1`).
* A page may run a writing command, and the command's own gate stays the final word: the page
  passes `write=1` on for the commands that take it, and a refusal reads exactly as it does on
  the command line. `web` is refused inside a request, because it would try to bind a second
  port (docs/web.md §3).

## 5. Exit codes

| Code | Meaning |
|---|---|
| 0 | the command ran and found nothing to report |
| 1 | `check` found load errors, dangling references or warnings; **or** a parse/IO error aborted the command (the message names the file and, where known, the line); **or** a recorded document version is unreadable (§4.2); **or** at least one file failed to convert (§4.3) |
| 2 | usage error: unknown scope or command, missing or unknown option, unresolvable path, and every refused write (§4.1, §4.2, §4.3) |
| 130 | interrupted (Ctrl-C) |

## 6. Warnings

Warnings never fail a load, and `check` reports them as counts plus up to 20 samples. The
four kinds seen on real data: `//` comments removed, a file decoded as UTF-8 rather than
cp1252, an unknown element kept as a leaf, and text inside an element that also holds
children (dropped on export — see the `</data>>` typos in the WW3 project).

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

* No `add`/`remove`, no batch edit, no packaging. Writes are one leaf of one document at a
  time, or a whole selection in the case of `convert`; the log and the baseline are per
  project, and `Firefight` is never written. The project metadata commands are still missing:
  `mod.toml` and `mod_setting.toml` are read but not written, and `.editor/refs.toml` and
  `.editor/index.toml` remain empty placeholders, so `refs` and `deps` answer from the graph
  built on each run rather than from an index.
* `export` keeps the source layout: sibling order, blank lines, indentation, `//` comments
  and the file's own newline style all come from the source text (toml-mapping §4). Files
  without source text — a `.toml` project document — use the canonical writer instead
  (tab indent, CRLF, schema order), and an edit invalidates the layout of the element it
  touches for as long as it is applied in memory.
* Whether the engine accepts a file we re-emit is verified by an in-game load check, not here.
* `Maps/`, `Surnames/` and `equipment_*` are out of scope.
* Modules are not loaded through `mod.txt` yet; a mod is a directory with `Data/`.

