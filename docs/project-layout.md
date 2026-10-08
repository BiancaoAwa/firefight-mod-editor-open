# Project layout, data-file responsibilities and CLI specification (draft v0)

> Status: merged into `main`. Section 11 records the items the project owner has decided; entries marked "default" are choices adopted provisionally while the project owner has not yet ruled on them, and may be overruled.

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
3. **Text I/O has a single exit point**: cp1252 / no BOM / tab indentation / **line endings always CRLF** (see [m0-baseline.md](m0-baseline.md); CRLF is a project-owner decision, see §11 D3).

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
    ├── baseline/               stock source snapshots of unedited entities (guarantees "echo back unchanged")
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

The measured `mod.txt` structure (10170 bytes / 428 lines / 12 nations) is described in [m0-baseline.md](m0-baseline.md) §2.4. A mapping example:

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
* `<units>` / `<filename>` inside `<nationality>` (one occurrence each in WW3): **preserved and passed through unchanged**, with the original value stored in TOML. The project owner classifies them as **a feature of the stock editor itself**, defers them as a TODO and does not interpret their semantics in v1 (see §11 D2).

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
* The default prefix is **`Mod/`** with README/LICENSE at the zip root (decision D1). It can be changed in `mod.toml`; **the import side must accept any prefix** (`.Mod/`, `<mod name>/` and a flat, prefixless layout must all be recognised), using the same test as the existing tool's `find_mod_root()`: the project root is the shallowest directory containing `mod.txt`.
* The PC-side root name has been verified by the project owner on a running installation: relative to the directory holding the game executable (`Firefight/`), it is **`Mod/`**, matching `assets/Mod/` on Android, so the exported root name `Mod/` is supported on both sides.
* The WW3 distribution uses `.Mod/` with its documents inside `.Mod/`; that is a **project folder naming habit**, not the standard install layout.

## 6. CLI specification

Form (retaining the project owner's requirement that the scope comes first):

```
ff <who> <command> <operation> <path...> [key=value ...] [--json]
```

`<who>` is the scope root and takes these values:

| Value | Meaning |
|---|---|
| `mod` | Path relative to the current mod |
| `firefight` | Stock game path (given by `FIREFIGHT_REF` or in settings) |
| `<other mod folder name>` | Another mod, used for cross-mod references |

An entity in another mod may also be addressed with the form `<other mod folder name>:<path>`, which overrides the prefix for that single path.

Examples:

```
ff mod list Vehicles                       # list this mod's vehicles
ff firefight show Infantry/"American-Infantry Section 1"
ff mod set Infantry/"American-Infantry Section 1" description.quality=QUALITY_ELITE
ff mod refs Weapons/WEAPON_AT_RIFLE_L_39   # query references (who refers to it)
ff mod check                               # full validation
ff mod log --last 20                       # the 20 most recent events
ff mod undo 3                              # roll back the 3 most recent events
ff mod export --out dist/ --format mod-zip
```

`--json` applies to every command so that the UI and AI can call it.

## 7. AI operation permissions (mirroring DSH permission management, confirmed by the project owner)

| Mode | Capability |
|---|---|
| `read-only` | Read-only queries, validation and report generation, with no writes at all |
| `workspace-write` | May write files inside the project directory; anything outside is refused |
| `danger-full-access` | May write outside the project directory (exporting to an arbitrary path and so on), with **human approval required every time** |

* Operations enter an approval queue one by one; **a refusal is never retried**; every failure is handled fail-closed.
* All AI actions are written to `.editor/log/`, recording who made the change.
* Any command that writes produces an event (invariant 2).

## 8. Event log and rollback

* Granularity: **a single entity field-level modification** (one `set` may produce several field events). [default]
* Dual track: a human-facing change description plus a machine-facing structured event. [default]
* Form: event sourcing with periodic snapshots (`.editor/baseline/` provides unchanged echo-back of unedited entities).
* Deliberate exception: the log uses **JSONL** (append-only, O(1)); TOML cannot be appended to, so logging in TOML would be O(N²).
* **Segmentation (decision D4)**: one file per segment, with the rule "**seal the current segment after 5 minutes without a new event, and start a new segment on the next event**".
  * Path: `.editor/log/<segment start local time>.jsonl`, for example `20261009T012000.jsonl`.
  * A segment is appended to only; sealing merely means "no further writes to this file" and produces no extra marker.
  * Rollback and time travel work across segments by reading them in filename order, which equals chronological order.
  * Segment files have no size limit; the 5-minute rule is the **only** split condition (not process start/stop, not calendar day).

## 9. Milestones (aligned with the conclusions in [m0-baseline.md](m0-baseline.md))

| Milestone | Content | Acceptance |
|---|---|---|
| **M0** (this one) | Baseline survey, schema reverse-engineering, mapping specification | This document plus [m0-baseline.md](m0-baseline.md) and [toml-mapping.md](toml-mapping.md), with reproducible data |
| M1 | Tolerant XML ↔ in-house TOML, both directions | All of [toml-mapping.md](toml-mapping.md) §8 passes |
| M2 | Reference graph and bidirectional validation | Bidirectional references inside a mod are fully checked; dangling references are locatable |
| M3 | CLI | Every command in §6 works and `--json` is stable |
| M4 | Event log and rollback | Any change is reversible and auditable |
| M5 | Project files and import/export | Folder ↔ zip/7z round trip is lossless |
| M6 | Packaging and multi-mod | The output loads in the game (**final verification by the project owner**); parallel mods plus cross-mod references |
| M7 | Local web UI | Capability-equivalent to the CLI |
| M8 | Distribution | Install package and usage documentation |

## 10. Dependency policy

* **Standard library first**, fully local and usable offline (the project owner asked for "as local as possible").
* The UI uses web technology (confirmed by the project owner); any front-end library must be listed and approved before being introduced.
* No TOML library such as tomlkit or tomli (the project owner confirmed an in-house implementation).
* Target runtime: Windows; a Python core with a built-in web UI.

## 11. Decision record

| Id | Date | Question | Decision | Status |
|---|---|---|---|---|
| D1 | 2026-10-09 | Root layout of the install-package zip | **`Mod/` prefix with README/LICENSE at the zip root**; import accepts any prefix | Settled |
| D2 | 2026-10-09 | `<nationality><units>`/`<filename>` in WW3 `mod.txt` | A **feature of the stock editor itself**; **tracked as a TODO**, passed through unchanged and uninterpreted in v1 | Settled, work outstanding |
| D3 | 2026-10-09 | Exported line endings | **Always CRLF** | Settled; its known cost (the 16 bare-LF files are not byte-identical to stock after export) is explicitly accepted by the project owner |
| D4 | 2026-10-09 | Log segmentation | **One file per segment**, sealed and replaced after 5 minutes without a new event | Settled |
| D5 | 2026-10-09 | Location of caches and editor data | **`.editor/`** under the project root, travelling with the project and excluded from the install package | Settled |
| D6 | 2026-10-09 | Strictness of export versus import | **Conservative export, tolerant import**: the export side follows stock as closely as possible (sibling order follows stock), while the import side is more robust (tolerant parsing, accepting any sibling order and illegal characters) | Settled |

**Known cost of D3**: 16 of the 1840 stock files use **bare LF** (measured), so after normalisation to CRLF those 16 files differ from stock in line endings on first export. The difference does not affect the agreed acceptance criterion (XML semantic equivalence, not byte identity), but the exported artifact is not byte-identical to stock for those 16 files. The project owner has explicitly accepted this trade-off.

**What D6 means in detail:**

* Export: sibling blocks are rendered in stock order; repeated blocks within a group (`[[man]]`, `[[turret]]`, `[[ammo]]` …) keep their order strictly; nothing is rearranged on the editor's own initiative.
* Import: no failure is caused by sibling order, a bare `&`, a numeric tag name or mixed case; shape decisions are fixed by the schema and never depend on a single file's data.

**TODO from D2**: reverse-engineer the real semantics of `<units>` / `<filename>` under `<nationality>` (in WW3 they are `NATIONALITY_TAIWANESE` and `Taiwanese-`, apparently a unit-file prefix filter for that nationality) and expose them as editable fields in the UI.
