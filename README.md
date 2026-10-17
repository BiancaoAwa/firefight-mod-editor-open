> Language: **English** | [中文](README.zh-CN.md)

# firefight-mod-editor-open

An open-source third-party mod editor compatible with *Firefight* by Sean O'Connor: broader
coverage and stricter round-trip fidelity than the tooling that ships with the game.

Status: data core, XML/TOML round-trip, reference graph, the command line, the local web UI,
the editing loop — `set` changes one field of one project document, adds and deletes array
entries, and leaves the rest of the file byte-identical; `add` and `remove` create and delete
whole documents; `log`, `undo` and `redo` record every write and revert it from the bytes kept
under `EditorCache/` ([cli.md](docs/cli.md) §4.1, §4.2, §4.5) — one-command import of the stock
data as project documents (`convert`), the reference index (`EditorCache/index.toml` and
`EditorCache/refs.toml`, [cli.md](docs/cli.md) §4.6), the translation between the stock `mod.txt`
and `ModSetting.toml` in both directions ([cli.md](docs/cli.md) §4.7), the mod-zip builder
`pack` ([cli.md](docs/cli.md) §4.8), the MCP server `python -m core.mcp`,
which offers the commands as tools, resources and prompts ([mcp.md](docs/mcp.md)), and a web UI
that runs the same commands, writing ones included, in Chinese or English ([web.md](docs/web.md)):
`/edit` lists every field of a document with its own input box, `/ops` offers each writing command
as a form and runs it with `--write --dry-run` before offering the write, and `/log` shows the
event log with the undo and redo forms. `init` creates a
project in an empty directory ([cli.md](docs/cli.md) §4.9), and `import` makes one out of a mod
that already exists, a directory or a zip ([cli.md](docs/cli.md) §4.16). `export` reproduces a stock file
byte for byte, layout included — 1840 of 1840 files on the installed game
(`tools/export_fidelity.py`). [flow.md](docs/flow.md) shows how the pieces fit together. `batch`
applies a patch file of several edits to many documents in one run ([cli.md](docs/cli.md)
§4.15); interactive multi-document editing is still missing.

## Quick start

Run the commands from the repository root; `-m core.cli` resolves the package there.

```
python -m core.cli version
python -m core.cli Firefight stats "root=<game directory>"
python -m core.cli Firefight show Data/Weapons/WEAPON_PISTOL_P38.txt as=toml --json
python -m core.cli Firefight deps value=WEAPON_PISTOL_P38 "root=<game directory>"
python -m core.cli Firefight convert "to=<project directory>" --write
python -m core.cli Firefight web  "root=<game directory>"   # pages on 127.0.0.1, first free port
```

`<game directory>` is the directory that holds `Data/`, `Images/` and `Sounds/` — the one
containing `Firefight.exe` for an installed game. `Mod` is the project the current
directory belongs to (nearest ancestor with `ModInformation.toml`). `Firefight` may also be resolved
from the `FIREFIGHT_DATA` environment variable or a local `Setting.toml`; see
[cli.md](docs/cli.md) §2.

Exit codes: `0` success, `1` executed but reported a failure (the JSON payload is usually
still valid), `2` usage error, `130` interrupted.

## Repository layout

```
core/     the code: core/cli (command line), core/mcp (stdio MCP server), core/web (web UI),
          schema, parsers, model
docs/     specification: what the editor does and how it is built
tests/    the suite (no game install, no network)
tools/    auxiliary tools: round-trip and fidelity harnesses, FirefightModPackager,
          launcher/ (the implementation behind the released StartWebUI.cmd /
          StartWebUI(Basic).cmd)
```

The command line is started as `python -m core.cli`; `core/cli/__main__.py` is the module
entry point, so there is no `ff.py` at the root to import or wrap.

The **editor folder** a release ships — launchers, `skills/`, `docs/`, `core/`, `launcher/`,
a bundled `Firefight/` data copy and `Mod/` — is specified in
[project-layout.md](docs/project-layout.md) §10; the repository above is the source tree and
deliberately has a different shape.

## Installing a release

A release is the editor folder described in [project-layout.md](docs/project-layout.md) §10:
`core/`, `docs/` and `launcher/` beside the entry points, plus `Mod/` for the projects, `Logs/`
for the run logs, `EditorCache/` for the editor's own state, `Firefight/` for a data copy, and
`Setting.toml` for the editor setting. Unpack it anywhere and keep those folders together: the
entry points look for `core/` beside themselves or one or two levels up.

Requirements: Windows, PowerShell 5.1 or PowerShell 7, and a Python 3.12 interpreter. The
launchers find the interpreter in this order — `FF_PYTHON`, then
`%DSH_HOME%\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`, then `python` on
`PATH`. Setting `FF_PYTHON` to an interpreter of your own is enough to use a different one.

| Entry point | What it starts |
|---|---|
| `StartWebUI.cmd` | the web UI in a window, with the launcher watching it; takes `-Scope`, `-Port`, `-Project`, `-NoBrowser` |
| `StartWebUI(Basic).cmd` | the same server in the foreground, no window and no watchdog |
| `Start(McpOnly).cmd` | the stdio MCP server, for an AI client to spawn |
| `StopAll.cmd` | stops the editor the launcher started |
| `ff-start.cmd` | prints what the launcher would do, without doing it |

`Setting.toml` is where the game installation and the project area are named:

```toml
firefight = "D:/Games/Firefight"   # the directory holding Data/, Images/ and Sounds/
workspace = "D:/Editor"            # project area; Mod/<name>/ under it
```

With neither key set, `Firefight` is looked for in the editor's own `Firefight/` copy and the
project is the nearest ancestor of the working directory that has `ModInformation.toml`. A
project is created with `import` (from an existing mod or a zip) or with `init`, run from the
editor folder:

```
python -m core.cli Mod import "D:/Downloads/some-mod.zip" to="D:/Editor/Mod/SomeMod" --write
python -m core.cli Mod init "root=D:/Editor/Mod/NewMod" name="NewMod" --write
```

## Tests

```
python -m unittest discover -s tests -t .      # no network, no game install
```

The suites that touch a real corpus are run by hand against the stock installation and the
released WW3 project; the measured numbers are in [cli.md](docs/cli.md) §7. Two harnesses need
the game directory:

```
python tools/m1_roundtrip.py  --data "<game>/Data"          # XML -> TOML -> XML, semantic
python tools/export_fidelity.py --data "<game>/Data"        # export vs source, byte for byte
```

## Documentation

| Document | Contents |
|---|---|
| [cli.md](docs/cli.md) | command line: scopes, selectors, commands, options, exit codes, measured results |
| [web.md](docs/web.md) | the local web UI: routes, options, design rules, limits |
| [project-layout.md](docs/project-layout.md) | project layout, CLI specification, permissions, event log, dependency policy |
| [mcp.md](docs/mcp.md) | the AI MCP surface: protocol revisions, tools, resources, permissions, error mapping |
| [refs.md](docs/refs.md) | reference rules and coverage |
| [toml-mapping.md](docs/toml-mapping.md) | how stock XML maps onto the TOML editing model |
| [m1-design.md](docs/m1-design.md) | data core design |
| [CHANGELOG.md](CHANGELOG.md) | what each version added, changed, and left as a known limitation |

## Building a mod

A project is a directory holding `ModInformation.toml`, `ModSetting.toml` and the data folders (the mod's own
`Data/`, `Images/`, `Sounds/`), plus `EditorCache/` for the log and baselines; a mod is a partial
overwrite, so anything it does not carry is read from the stock scope. The editor reads `.toml`
under a project and `.txt` under the stock scope. `convert` turns the stock data into project
documents one file at a time (`to=<project directory> --write`, existing targets skipped;
`assets=1` also copies the scope's `Images/` and `Sounds/` trees). `export` writes a selection back to stock XML under
`to=<directory>`, keeping the source layout of any file that came from disk. Nothing is
written to a scope: the game installation is never modified.

## License

GPL-3.0 — see [LICENSE](LICENSE).

