> Language: **English** | [中文](README.zh-CN.md)

# firefight-mod-editor-open

An open-source third-party mod editor compatible with *Firefight* by Sean O'Connor: broader
coverage and stricter round-trip fidelity than the tooling that ships with the game.

Status: data core, XML/TOML round-trip, reference graph, the command line, the read-only
browsing slice of the local web UI, and `set` — one field of one project document, leaving the
rest of the file byte-identical ([cli.md](docs/cli.md) §4.1). `export` reproduces a stock file
byte for byte, layout included — 1840 of 1840 files on the installed game
(`tools/export_fidelity.py`). No event log, no undo, no packaging yet.

## Quick start

Run the commands from the repository root; `-m core.cli` resolves the package there.

```
python -m core.cli version
python -m core.cli Firefight stats "root=<game directory>"
python -m core.cli Firefight show Data/Weapons/WEAPON_PISTOL_P38.txt as=toml --json
python -m core.cli Firefight deps value=WEAPON_PISTOL_P38 "root=<game directory>"
python -m core.cli Firefight web  "root=<game directory>"   # read-only pages on 127.0.0.1:8765
```

`<game directory>` is the directory that holds `Data/`, `Images/` and `Sounds/` — the one
containing `Firefight.exe` for an installed game. `Mod` is the project the current
directory belongs to (nearest ancestor with `mod.toml`). `Firefight` may also be resolved
from the `FIREFIGHT_DATA` environment variable or a local `.ff-editor.local.toml`; see
[cli.md](docs/cli.md) §2.

Exit codes: `0` success, `1` executed but reported a failure (the JSON payload is usually
still valid), `2` usage error, `130` interrupted.

## Repository layout

```
core/     the code: core/cli (command line), core/web (web UI), schema, parsers, model
docs/     specification: what the editor does and how it is built
tests/    the suite (no game install, no network)
tools/    auxiliary tools: round-trip and fidelity harnesses, FirefightModPackager,
          launcher/ (the implementation behind the released ff-web.cmd / ff-ai.cmd)
```

The command line is started as `python -m core.cli`; `core/cli/__main__.py` is the module
entry point, so there is no `ff.py` at the root to import or wrap.

The **editor folder** a release ships — launchers, `skills/`, `docs/`, `core/`, `launcher/`,
a bundled `Firefight/` data copy and `Mods/` — is specified in
[project-layout.md](docs/project-layout.md) §10; the repository above is the source tree and
deliberately has a different shape.

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
| [web.md](docs/web.md) | the local read-only web UI: routes, options, design rules, limits |
| [project-layout.md](docs/project-layout.md) | project layout, CLI specification, permissions, event log, dependency policy |
| [mcp.md](docs/mcp.md) | the AI MCP surface: protocol revisions, tools, resources, permissions, error mapping |
| [refs.md](docs/refs.md) | reference rules and coverage |
| [toml-mapping.md](docs/toml-mapping.md) | how stock XML maps onto the TOML editing model |
| [m1-design.md](docs/m1-design.md) | data core design |

## Building a mod

A mod is a directory containing `Data/`; the editor reads `.toml` under a project and
`.txt` under the stock scope, and `export` writes a selection back to stock XML under
`to=<directory>`, keeping the source layout of any file that came from disk. Nothing is
written to a scope: the game installation is never modified.

## License

GPL-3.0 — see [LICENSE](LICENSE).

