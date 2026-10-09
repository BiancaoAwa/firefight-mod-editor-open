# Command line (M3, first slice)

Status: **read-only**. Every command except `export` prints a result and writes nothing;
`export` writes stock XML into a directory the caller names. No project storage, no event
log, no packaging, no UI — those are later milestones (docs/m1-design.md §5).

## 1. Invocation

```
python ff.py <scope> <command> [selector] [key=value ...] [--json]
```

`ff help` prints the same table the parser accepts; `ff version` prints editor version,
interpreter and the scopes that resolve from the current directory.

## 2. Scopes

A scope root is a directory holding `Data/`, `Images/` and `Sounds/`.

| Scope | Meaning | Resolution |
|---|---|---|
| `Mod` | the mod project the current directory belongs to | `root=`/`mod=` option, else `mod` in the local config, else nearest ancestor with `mod.toml`; data lives under `Mod/` when present, otherwise at the project root |
| `Firefight` | the stock game data | `root=`/`firefight=` option, else `FIREFIGHT_DATA`, else `firefight` in the local config found upwards, else the copy shipped with the editor |
| `<name>` | another mod folder in the workspace | a directory of that name, else `<workspace>/Mods/<name>`, else `<workspace>/<name>`; workspace from `workspace=<dir>`, else `FIREFIGHT_MODS`, else the local config, else the current directory |

A scope root is the directory that holds `Data/`, `Images/` and `Sounds/`; passing the
`Data` directory itself is accepted and normalized to its parent. For an installed game
that is the directory containing `Firefight.exe`. Nothing is written
to a scope: the editor never edits the game directory, and `export` writes only under
`to=`. The local config `.ff-editor.local.toml` (keys `firefight`, `mod`, `workspace`) is
read from the nearest ancestor directory and belongs in `.gitignore`.

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
| `export` | `emit` | render the selection as stock XML under `to=<dir>` |
| `version` | | editor version, interpreter, resolved scopes |

Options: `root=`, `workspace=`, `to=`, `as=`, `field=`, `type=`, `kind=`, `path=`,
`limit=` (default 200 rows), `ignore_case=1`, `--json`. Unknown options, unknown scopes
and missing paths are usage errors. `key=value` options may appear in any order; `--json`
may appear anywhere.

## 5. Exit codes

| Code | Meaning |
|---|---|
| 0 | the command ran and found nothing to report |
| 1 | `check` found load errors, dangling references or warnings; **or** a parse/IO error aborted the command (the message names the file and, where known, the line) |
| 2 | usage error: unknown scope or command, missing or unknown option, unresolvable path |
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
errors. Semantic round-trip equivalence on both corpora is reported in
[m1-report.md](m1-report.md); reference rules and coverage in [refs.md](refs.md).

The two stock dangling references are in the shipped data (`WEAPON_PISTOL_WZ_35_VIS` from
`Hungarian-TK3.txt` and `Hungarian-TKS.txt`). The 911 in WW3 are mostly references into
stock data: when a mod project is checked with the stock installation as a second scope,
882 of the 912 resolve. **That fallback is measured but not implemented** — the CLI
resolves each scope on its own, and cross-scope resolution arrives with the workspace
registry.

## 8. Reproducing the demo

```
python -m unittest discover -s tests -t .                       # 173 tests
python ff.py Firefight stats  "root=<Firefight>"
python ff.py Firefight check  "root=<Firefight>" --json
python ff.py Firefight refs   "root=<Firefight>" --json --limit 5
python ff.py Firefight deps   "value=WEAPON_PISTOL_P38" "root=<Firefight>"
python ff.py Firefight export Vehicles "root=<Firefight>" "to=<somewhere>"
python ff.py WW3 stats "root=<extracted WW3>/.Mod"
```

`check` exits 1 on both corpora, which is the intended report and not a crash. `deps` is
scope-wide: it answers for one scope at a time.

## 9. Limits of this slice

* No writes, no project directories, no `.editor/` state, no event log, no undo.
* `export` follows the canonical writer, so sibling order inside a branch differs from the
  source file (toml-mapping §4; measured in m1-report §3.1). Whether the engine accepts
  the canonical order for every branch is verified by an in-game load check, not here.
* `Maps/`, `Surnames/` and `equipment_*` are out of scope, as in M1.
* Modules are not loaded through `mod.txt` yet; a mod is a directory with `Data/`.
