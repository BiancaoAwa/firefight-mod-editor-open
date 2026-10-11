> Language: **English** | [中文](project-layout.zh-CN.md)

# Project layout, data-file responsibilities and CLI specification (draft v0)

> Status: merged into `main`. Entries marked "default" are choices adopted provisionally while the project owner has not yet ruled on them, and may be overruled. Rules the project owner has settled are stated in the section they belong to.

## 1. Layering and invariants

```
core   ── data model, tolerant parsing, TOML read/write, reference graph, validation, event log, packaging
  ↑
CLI    ── command-line entry point (the only "scriptable" shell over core)
  ↑
API    ── local interface for UI and AI (the same capabilities as the CLI)
  ↑
UI     ── local web UI (opened in a browser, no standalone server)
```

Three invariants:

1. **Anything the UI can do, the CLI must be able to do** (the UI is only a view onto the CLI and API).
2. **Every write must produce an event** (reversible and auditable).
3. **Text I/O has a single exit point**: cp1252 / no BOM / tab indentation; a document read from disk keeps its source bytes, and text without a source is written CRLF with tabs (see [toml-mapping.md](toml-mapping.md) §4.1 and §5).

The AI layer reaches the same capabilities through the MCP server specified in [mcp.md](mcp.md).

## 2. Project directory structure

A project is a **folder named after the mod** and can be exported to, or imported from, a zip or 7z archive directly.

```
<mod name>/
├── mod.toml                    mod metadata (information about the project itself)
├── mod_setting.toml            mod settings (the TOML form of the stock mod.txt)
├── README.md                   documentation shipped with the package
├── LICENSE                     licence shipped with the package
├── Mod/                        ← when exported as a standard mod, this level is the stock Firefight/Mod
│   ├── Data/
│   │   ├── Infantry/<unit name>.toml
│   │   ├── Vehicles/<unit name>.toml
│   │   ├── AT Guns/<unit name>.toml
│   │   ├── Aircraft/<unit name>.toml
│   │   ├── Weapons/<weapon name>.toml
│   │   └── equipment_<nation>.toml    unit list (plain text in stock)
│   ├── Images/
│   │   ├── Units/{HMGs,Mortars,Vehicles/{Hulls,Turrets,Profiles}}
│   │   ├── Uniforms/uniform_<unit name>/...
│   │   ├── Chooser/{Buttons}
│   │   └── Game/{Control Panel,Flags,Map,Toolbar}
│   └── Sounds/...
└── .editor/                    editor working data and caches (**part of the project, never part of the install package**, confirmed by the project owner)
    ├── setting.toml            editor settings
    ├── log/                    event-log segment directory (see §8)
    │   ├── 20261009T012000.jsonl
    │   └── 20261009T031500.jsonl
    ├── refs.toml               cross-reference cache
    ├── index.toml              entity index and search cache
    ├── baseline/               every version a write replaced, under its sha256 (see §8)
    ├── lock                    held for the duration of one write
    └── notes.toml              human-readable notes extracted from stock `//` comments (optional)
```

**Confirmed rules**

* One file per entity, with directories **mirroring the stock mod structure** (`Data/<type>/`).
* `mod.toml` holds mod metadata; `mod_setting.toml` holds the mod settings (stock `mod.txt`); caches such as cross-references each get their own TOML file.
* Caches and editor state live together under **`.editor/`** at the project root, travel with the project (the project owner confirmed "put the mod cache inside the mod folder") and are **never packed into the install package**.
* A mod is a **partial overlay**: the project contains only changed or added entities, and everything else is read from the stock baseline (the measured WW3 sample has no `AT Guns/` and no `Aircraft/`).
* `Surnames/` is **neither modelled nor packaged** (the project owner confirmed "not mod content"); at most it is referenced as a read-only stock resource.

## 3. `mod.toml` (mod metadata)

```toml
[mod]
name = "World War III - the Final War"
version_name = "2.3.0"        # major.minor.patch
version_code = 2030007        # BMMSSNN
update_code = 2640            # YYWW
game_version = "13.2.0.0"     # targeted game version
authors = ["WW3 Mod Development Team"]
license = "CC BY-SA 4.0"
```

## 4. `mod_setting.toml` (= the stock `mod.txt`)

The structure of `mod.txt` is measured on the installed 13.2.0.0 sample: 10170 bytes, 428 lines, 12 nations. A mapping example:

```toml
[mod_setting]
name = "Firefight: World War III - the Final War"
author = "WW3 Mod Development Team"
show_scenarios = false
choose_unique_rifle_squad = false
allow_vehicles = true
allow_infantry = true
allow_at_guns = false
allow_artillery = true
minimum_commonness = 25
minimum_commonness_to_upgrade = 100

[mod_setting.years]
start = 2024
end = 2033
increment = 1

[mod_setting.credits]
attack1 = 250
attack2 = 350
attack3 = 450
attack4 = 550
defend1 = 200
defend2 = 275
defend3 = 350
defend4 = 425

[mod_setting.text_colours]
map_description = "FFFFFF"
custom_heading = "FFFFFF"
custom_option = "FFFFFF"
custom_unit_description = "FFFFFF"
game = "FFFFFF"
friend = "0000FF"
enemy = "FF0000"

[[mod_setting.nationality]]
name = "America (In Production)"
surnames = "surnames_american.txt"
voice = "US"
equipment = ["news_main.txt", "equipment_american.txt"]

[mod_setting.nationality.flags]
static = "flag_USA.png"
animated = "flag_animated_USA.png"

[mod_setting.nationality.ranks]
"1" = "Pvt"
"2" = "PFC"
"3" = "Cpl"
"4" = "Sgt"
"5" = "2Lt"
"6" = "1Lt"
"7" = "Cpt"

[mod_setting.nationality.default_images]
infantry = "uniform_game_american.png"
tank_crew = "uniform_game_american_tank_crew.png"
infantry_profile = "uniform_profile_american.png"
tank_crew_profile = "uniform_profile_american_tank_crew.png"
ranks = "uniform_ranks_american_ww3.png"
```

Key points

* `<1>`..`<7>` become quoted TOML keys, because a TOML bare key may not start with a digit. `mod.txt` is not well-formed XML, so its parser is implemented separately.
* A repeated `<equipment>` is merged into one array, rendered back as one `<equipment>` per array element on export.
* `<units>` / `<filename>` inside `<nationality>` (one occurrence each in WW3): **preserved and passed through unchanged**, with the original value stored in TOML. The project owner classifies them as **a feature of the stock editor itself** and does not interpret their semantics in v1.
  * TODO: reverse-engineer the real semantics of `<units>` / `<filename>` under `<nationality>` (in WW3 they are `NATIONALITY_TAIWANESE` and `Taiwanese-`, apparently a unit-file prefix filter for that nationality) and expose them as editable fields in the UI.

## 5. Packaged output layout

```
<mod name>-<version>.zip
├── Mod/                       ← the game MOD root (confirmed by the project owner; evidenced by assets/Mod/ on Android)
│   ├── mod.txt                rendered from mod_setting.toml
│   ├── Data/...               rendered from the entity TOML files
│   ├── Images/...
│   └── Sounds/...
├── README.md
└── LICENSE
```

* Packaging must compare against the stock baseline of the **target game version**: a file that already exists in the target version may be reused and need not be packed (the project owner confirmed this is what "anything stock does not report an error" means).
* **v1 does not do APK packaging** (confirmed by the project owner).
* The default prefix is **`Mod/`** with README/LICENSE at the zip root. It can be changed in `mod.toml`; **the import side must accept any prefix** (`.Mod/`, `<mod name>/` and a flat, prefixless layout must all be recognised), using the same test as the existing tool's `find_mod_root()`: the project root is the shallowest directory containing `mod.txt`.
* The PC-side root name has been verified by the project owner on a running installation: relative to the directory holding the game executable (`Firefight/`), it is **`Mod/`**, matching `assets/Mod/` on Android, so the exported root name `Mod/` is supported on both sides.
* The WW3 distribution uses `.Mod/` with its documents inside `.Mod/`; that is a **project folder naming habit**, not the standard install layout.

## 6. CLI specification

Form (retaining the project owner's requirement that the scope comes first). The base form of the original draft was `ff <who> <command> <operation> <path...> [key=value ...] [--json]`; the implemented entry is the module `core.cli`, started from the editor root:

```
python -m core.cli <scope> <command> <operation> <path...> [key=value ...] [--json]
```

`<scope>` is the scope root and takes these values:

| Value | Meaning |
|---|---|
| `Mod` | Path relative to the current mod |
| `Firefight` | Stock game path (given by `root=<path>`, `FIREFIGHT_DATA`, or `.ff-editor.local.toml`) |
| `<other mod folder name>` | Another mod, used for cross-mod references |

An entity in another mod may also be addressed with the form `<other mod folder name>:<path>`, which overrides the prefix for that single path.

Examples:

```
python -m core.cli Mod list Vehicles                       # list this mod's vehicles
python -m core.cli Firefight show Infantry/"American-Infantry Section 1"
python -m core.cli Mod set Infantry/"American-Infantry Section 1" field=description.quality value=QUALITY_ELITE --write
python -m core.cli Mod log                                 # segments and the newest records
python -m core.cli Mod undo 1 --write                      # put back what the last write replaced
python -m core.cli Mod redo 1 --write                      # re-apply what the last undo reverted
python -m core.cli Mod refs Weapons/WEAPON_AT_RIFLE_L_39   # query references (who refers to it)
python -m core.cli Mod check                               # full validation
python -m core.cli Mod export --out dist/ --format mod-zip
```

`set` takes its field as an option (`field=` and `value=`), because every token containing `=`
is parsed as a `key=value` option; `set`, `undo` and `redo` need `--write` and refuse the
`Firefight` scope (docs/cli.md §4.1, §4.2).

`--json` applies to every command so that the UI and AI can call it.

## 7. AI operation permissions (mirroring DSH permission management, confirmed by the project owner)

| Mode | Capability |
|---|---|
| `read-only` | Read-only queries, validation and report generation, with no writes at all |
| `workspace-write` | May write files inside the project directory; anything outside is refused |
| `danger-full-access` | May write outside the project directory (exporting to an arbitrary path and so on), with **human approval required every time** |

* Operations enter an approval queue one by one; **a refusal is never retried**; every failure is handled fail-closed.
* The CLI expresses the tier with a flag: a command that writes needs `--write`, and a write
  outside the project directory is refused (`set`, `undo` and `redo` confine themselves to the
  project directory, docs/cli.md §4.1, §4.2).
* All AI actions are written to `.editor/log/`, recording who made the change.
* Any command that writes produces an event (invariant 2).

## 8. Event log and rollback

* Granularity: **a single entity field-level modification** (one `set` may produce several field events). [default]
* Dual track: a human-facing change description plus a machine-facing structured event. [default]
* Form: event sourcing with periodic snapshots (`.editor/baseline/` provides unchanged echo-back of unedited entities).
* Deliberate exception: the log uses **JSONL** (append-only, O(1)); TOML cannot be appended to, so logging in TOML would be O(N²).
* **Segmentation**: one file per segment, with the rule "**seal the current segment after 5 minutes without a new event, and start a new segment on the next event**".
  * Path: `.editor/log/<segment start local time>.jsonl`, for example `20261009T012000.jsonl`.
  * A segment is appended to only; sealing merely means "no further writes to this file" and produces no extra marker.
  * Rollback and time travel work across segments by reading them in filename order, which equals chronological order.
  * Segment files have no size limit; the 5-minute rule is the **only** split condition (not process start/stop, not calendar day).
* **A record** is one JSON object per line, in this order: `id` (`<segment stem>:<line number>`),
  `segment`, `timestamp` (local ISO 8601 with offset), `actor` (`cli` or `mcp`), `result` (`set`,
  `undo` or `redo`), `target` (the `id` an undo or redo reverts, else `null`), `document`
  (project-relative POSIX path), `entity`, `field`, `before`, `after`, `digest_before`,
  `digest_after`, `bytes_before`, `bytes_after` (all sha256, hex) and `dry_run` (always `false`:
  a dry run is not an event).
* **Byte-level rollback**: every write stores the document before and after it under
  `.editor/baseline/<sha256>`, content-addressed and deduplicated across changes, so `undo` and
  `redo` write recorded bytes rather than a re-serialisation. A digest whose bytes are gone, or
  whose bytes no longer hash to their name, fails the command; a document that moved on disk
  after the recorded change refuses the revert instead of overwriting it.
* **State is replayed, not stored**: the changes currently applied are those the log names and no
  later `undo` reverts; an `undo` appends one record of its own naming the change it reverted, so
  the log remains the only source of truth and no separate index can drift from it. A new `set`
  discards what could be redone.

## 9. Dependency policy

* **Standard library first**, fully local and usable offline (the project owner asked for "as local as possible").
* The UI uses web technology (confirmed by the project owner); any front-end library must be listed and approved before being introduced.
* No TOML library such as tomlkit or tomli (the project owner confirmed an in-house implementation).
* Target runtime: Windows; a Python core with a built-in web UI.

## 10. Repository layout and the editor folder

Two layouts exist and they are deliberately different: the **repository** is the source tree
on GitHub, the **editor folder** is what an installation looks like — the same shape whether
the editor ships as loose code or as a packed executable.

### 10.1 Repository (GitHub: `core/ docs/ tests/ tools/`)

```
<repo>/
├── core/          the code
│   ├── cli/       command line: scope resolution, commands, main
│   ├── web/       the local read-only web UI: server
│   └── *.py       schema, parsers (XML/TOML), model, conversion, reference graph
├── docs/          specification: what the editor does and how it is built, English plus *.zh-CN.md mirror (this file lives here)
├── tests/         the suite (no game install, no network)
├── tools/         auxiliary tools: m1_roundtrip.py, export_fidelity.py,
│                  FirefightModPackager/, and launcher/ (the implementation behind
│                  ff-web.cmd / ff-ai.cmd)
└── README.md  README.zh-CN.md  LICENSE  .gitignore  .gitattributes
```

The CLI and the web UI live in `core/cli` and `core/web` and are imported as
`core.cli.*` / `core.web.*`. `core/cli/scope.py` (`_editor_root`) is the one place that
recognises an editor folder — repository or distribution — so a bundled `Firefight/` copy
can be found without an installed game.

The CLI entry is the module `core.cli`, started from the repository root; there is no
`ff.py` at the top level, so `python -m core.cli <scope> <command> ...` is the only form.

### 10.2 Editor folder (a release: loose code or packed)

```
<editor>/
├── ff-web.cmd          launcher with the web UI (double-click; page in its own window)
├── ff-ai.cmd           launcher without a UI, for AI callers (forwards to the CLI)
├── README.md           package description; README.zh-CN.md is its Chinese mirror
├── skills/             AI skills: skills/firefight-editor/SKILL.md
├── docs/               documentation: English files and their *.zh-CN.md mirrors
├── core/               the code (core/cli/__main__.py is the CLI entry)
├── launcher/           the implementation behind ff-web.cmd / ff-ai.cmd
├── Firefight/          stock game data copy (optional; reference, read-only)
├── Mods/               mod projects
│   └── <name>/         mod.toml, mod_setting.toml, README.md, LICENSE,
│                       Mod/{Data,Images,Sounds},
│                       .editor/{refs.toml, index.toml, log/, baseline/, notes.toml}
└── .ff-editor.local.toml   machine-local settings: which mod, which stock directory
```

Rules that follow from this layout:

* The editor looks for the stock data next to its own entry point (`<editor>/Firefight/Data`)
  and reports that origin as `editor copy <path>`; an installation therefore works without
  the game being installed.
* `Mods/` is the workspace root for `<name>` scopes and `mod.toml` marks a mod project.
* A mod project is a **partial overlay**: it may only replace files the game already reads,
  so `Mod/Data`, `Mod/Images` and `Mod/Sounds` mirror the game folders exactly.
* `.editor/` travels with a project, is excluded from any package, and holds the
  caches (`refs.toml`, `index.toml`), the event log and the baseline snapshots.
* `mod_setting.toml` is the TOML form of the stock `Mod/mod.txt`; its renderer is not
  implemented yet, so a fixture project may carry a deliberately partial file, marked as
  such inside the file.
* Both launchers run the CLI as `python -m core.cli`, which resolves the `core` package from
  the current directory, so the entry works in both layouts while the code sits one level
  down in `core/`.

