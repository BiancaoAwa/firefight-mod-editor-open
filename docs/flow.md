# How the editor works

This repository is the editor core: one command layer, three faces over it, and the readers
and writers for the game's files. There is no build step.

## The flow

```mermaid
flowchart TD
    subgraph stock["Game installation (read only)"]
        A1["Firefight/Data/**/*.txt<br/>stock XML"]
        A2["Firefight/Images, Sounds<br/>binaries"]
    end

    subgraph project["Editor project, Mod/&lt;name&gt;"]
        B1["ModInformation.toml<br/>the project's metadata"]
        B2["ModSetting.toml<br/>the TOML form of mod.txt"]
        B3["mod.txt<br/>the file the game reads"]
        B4["Data/**/*.toml<br/>working files"]
        B5["Images/, Sounds/"]
        B6["EditorCache/log/*.jsonl<br/>EditorCache/baseline/**"]
        B7["EditorCache/index.toml<br/>EditorCache/refs.toml"]
    end

    subgraph layer["The command layer"]
        C1["core/cli/commands.py<br/>run_command, 22 commands"]
        C2["core/cli/specs.py<br/>the one tool table"]
        C3["core/cli/scope.py<br/>Mod, Firefight, &lt;name&gt;"]
    end

    subgraph faces["The faces"]
        D1["CLI<br/>python -m core.cli"]
        D2["MCP server<br/>python -m core.mcp, in process"]
        D3["Web UI<br/>python -m core.cli Mod web, in process"]
        D4["DSH plugin<br/>separate repository, spawns the CLI"]
    end

    E1["&lt;name&gt;-&lt;version&gt;.zip<br/>Mod/ + README.md + LICENSE"]

    A1 -->|convert| B4
    A2 -->|"convert assets=1"| B5
    A1 -->|firefight scope| C1
    C1 -->|init| B1
    B3 -->|settings op=render| B2
    B2 -->|settings op=emit| B3
    B4 -->|set, add, remove| B4
    B1 -->|set| B1
    B2 -->|set| B2
    C1 --> B6
    B6 -->|undo, redo| B4
    C1 -->|index --write| B7
    B7 -->|refs, deps| C1
    B4 -->|pack| E1
    B3 -->|pack| E1
    C3 --> C1
    C1 --> C2
    C1 --> D1
    C1 --> D2
    C1 --> D3
    D4 --> D1
```

Every write goes through `core/edit.py`, which stages the new bytes, holds `EditorCache/lock`,
stores the old and new blobs under `EditorCache/baseline/`, and appends one record to the log.
`undo` and `redo` write recorded bytes back, so the log is the only source of truth
(docs/project-layout.md section 8).

## Repository files

| Path | Role |
| --- | --- |
| `core/cli/main.py` | argument parsing, the usage text, exit codes |
| `core/cli/commands.py` | every command and the `Document` it works on |
| `core/cli/scope.py` | `Mod`, `Firefight` and `<name>` resolution, `entity_files` |
| `core/cli/specs.py` | the tool table the MCP server renders and the plugin mirrors |
| `core/xml.py`, `core/toml.py` | the two parsers and the TOML writer |
| `core/convert.py` | XML to TOML and back, including the layout-preserving writer |
| `core/schema.py` | shapes and types per root, plus the two project files |
| `core/refs.py` | reference rules and the graph over a corpus |
| `core/index.py` | writes and reads `EditorCache/index.toml` and `EditorCache/refs.toml` |
| `core/edit.py` | field writes, whole documents, array entries, locking, atomic replace |
| `core/journal.py` | log segments, baselines, the lock |
| `core/history.py` | plans and applies `undo` and `redo` |
| `core/settings.py` | renders `mod.txt` to `ModSetting.toml` and back |
| `core/pack.py` | builds the mod-zip |
| `core/textio.py` | decoding, newlines, the export encoding |
| `core/enums.py`, `core/errors.py` | enum tables, the error model |
| `core/mcp/` | stdio JSON-RPC server, its tools and resources |
| `core/web/` | the pages, the instance record, the language table |
| `docs/` | usage and architecture documents, each in English and Chinese |
| `tests/` | `python -m unittest discover -s tests -t .` |
| `tools/launcher/` | the PowerShell launcher and its `.cmd` entry points |
| `tools/FirefightModPackager/` | the upstream packager, vendored |

## Build artifacts

There is no build step: the core is pure Python with no dependencies outside the standard
library, and the faces run from source with `python -m`.

Two artifacts exist, both produced outside a build system:

| Artifact | Produced by | Contents |
| --- | --- | --- |
| The editor folder | copying `core/`, `docs/` and `launcher/` next to the entry points | the same source plus `Firefight/`, `Mod/` and `Setting.toml` |
| `&lt;name&gt;-&lt;version&gt;.zip` | `pack` | `Mod/`, `README.md`, `LICENSE`; `Mod/mod.txt` is rendered from `ModSetting.toml`, `Mod/Data/**` documents are written back as stock XML, everything else is copied byte for byte |

`pack` writes members with a fixed timestamp, so the same project packs to the same bytes
and the tests can compare archives.

## Not yet done

| Missing | Marker |
| --- | --- |
| `vehicle` and `at_gun` documents have no schema, so `set` cannot name a field in one and `add` falls back to a bare root | `# TODO(m5)` in `core/schema.py` |
| the stock-baseline comparison and APK packaging of docs/project-layout.md section 5 | `# TODO(pack)` in `core/pack.py` |
| a document that exists only as TOML is re-emitted canonically, so a source file with other endings or indentation is not reproduced byte for byte | `# KNOWN:` in `core/pack.py` |

These have no marker yet:

* `init` writes `ModInformation.toml` and an empty `Data/` and nothing else; it reads no template and
  imports no stock data.
* `Images/` and `Sounds/` are imported only when `convert` is asked for them with `assets=1`;
  references to them stay dangling until the files are imported or placed by hand.
* `Maps/`, `Surnames/` and `equipment_*` lists are outside the schema.
* a reference that does not resolve inside one scope is not retried against the stock
  corpus; the fallback is measured (882 of 912 references in one real project) but not
  implemented.
* no batch edit.
