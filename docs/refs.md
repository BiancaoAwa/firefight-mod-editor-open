> Language: **English** | [中文](refs.zh-CN.md)

# Reference graph

`core/refs.py` answers three questions about a scope (stock data or one mod project):

1. which values in a document point at another file (`references_in`),
2. who points at what, in both directions (`RefGraph`),
3. whether a target exists under a scope root (`TargetIndex`, `unresolved`, `summary`).

Collection is pure: an `XmlElement` and its source path go in, references come out. Nothing
is written and no text encoding is involved, so this part runs on the data model as is.

## 1. Rule table

A reference is a leaf whose tag is listed below. Rules are keyed by tag plus, where a tag is
ambiguous, its parent tag.

| kind | tag | parent | resolution |
| --- | --- | --- | --- |
| `weapon` | `type` | `weapon` | `Data/Weapons/<value>.toml`, then `.txt` |
| `weapon` | `for` | `ammo` | `Data/Weapons/<value>.toml`, then `.txt` |
| `sound` | `sound_shoot` | any | `Sounds/<value>.ogg` |
| `sound` | `sound_reload` | any | `Sounds/<value>.ogg` |
| `sound` | `sound_eject_clip` | any | `Sounds/<value>.ogg` |
| `image` | `image_view` | any | file under `Images/` by name or stem |
| `image` | `image_view_base` | any | file under `Images/` by name or stem |
| `image` | `image_view_gun` | any | file under `Images/` by name or stem |
| `image` | `image_profile` | any | file under `Images/` by name or stem |
| `image` | `uniform_ranks` | any | file under `Images/` by name or stem |
| `image` | `image` | any | file under `Images/` by name or stem |
| `uniform` | `uniform` | any | directory `Images/Uniforms/uniform_<value>/` |
| `engine_sound` | `sound` | any | alias table, see §3 |
| `roster` | (a line of a unit roster) | — | a document under the unit folders of `Data/`, by stem |

One kind does not come from a leaf tag. A unit roster — an equipment list the project
declares in `mod.txt` or `ModSetting.toml` — carries one entry per line, and each entry names
a unit document. Those entries are references too: `roster` references belong to the same
graph, so `refs` lists them, `deps <unit>` finds the roster that names a unit, and `check`
reports an entry no document answers as a dangling reference rather than as a blind spot
(docs/cli.md §4.6). The reference names the line it sits on instead of a field path. A
surname list is *not* a roster: it names people, not files, and its entries would only read
as noise, so only equipment lists contribute.

Two rules need their context to stay honest:

- A weapon document's own `<type>` (`WEAPON_RPG`, `WEAPON_RIFLE`, ...) is a category, not a
  file. `RefRule.skip_document_root` therefore skips `<type>` at depth 2, so only a slot
  nested below the root `<weapon>` element counts.
- `type` is a reference inside a `<weapon>` slot but an ordinary leaf elsewhere (for example
  `squad/type` = `TYPE_TANK`), which is why the rule names its parent.

Empty leaves are never references: `<dimensions></dimensions>` carries no value to resolve.

## 2. Resolution

`TargetIndex(root)` maps a value onto one scope root. Stock data and a mod project share the
same layout (`Data/`, `Images/`, `Sounds/`), so the same index serves both; only the root
differs.

- Weapons prefer `.toml` (a mod project stores entities as TOML) and fall back to `.txt`.
- Images are indexed once per scope by both file name and stem, because values appear in
  both forms: `Image-M2 Medium Tank turret.png` and `Plane-Curtiss A-12 Shrike.png` carry the
  extension, while a stem lookup still resolves if a document omits it.
- Image lookup ignores case. Four stock aircraft documents name `Plane-Ilyushin Il-10.png`
  and `Plane-Ilyushin Il-2 Sturmovik.png` while the files on disk are `Plane-Ilyushin IL-10.png`
  and `Plane-Ilyushin IL-2 Sturmovik.png`. Exact-case matches win when both exist.
- Weapon, sound and uniform lookups probe the filesystem directly, so their case sensitivity
  is the platform's; only the in-memory image index has to fold case explicitly.
- A `roster` entry resolves against the unit folders of `Data/` (`Infantry`, `Vehicles`,
  `AT Guns`, `Aircraft`) by file stem. The weapon folder is deliberately out of that set: a
  weapon is pulled in by the document that uses it, so no roster entry can mean one. The
  folder list is passed in, so `core/cli/commands.py` stays the one place that names the
  categories.

## 3. Aircraft `<sound>` is a token

`Data/Aircraft/*.txt` contains a single distinct value, `<sound>SOUND_PROPELLER</sound>`, and
`Sounds/SOUND_PROPELLER.ogg` does not exist; the file is
`Sounds/Engines/plane_propeller.ogg`. The tag is therefore a symbolic token, not a file stem,
and `ENGINE_SOUND_ALIASES` holds the one observed mapping. Tokens outside the table stay
unresolved instead of being guessed.

## 4. API

```python
RefRule(kind, field, parent=None, skip_document_root=False)
Reference(source, path, kind, value)          # path includes the root element name
references_in(root: XmlElement, source: str) -> tuple[Reference, ...]

RefGraph()
  .add(source, element) -> int                # returns references contributed
  .add_references(found) -> int               # the same, for references built elsewhere
  .add_roster(source, entries) -> int         # (line, name) pairs of a unit roster
  .references() / .for_source(source) / .for_target(kind, value)
  .targets(kind=None) / .sources()

TargetIndex(root: Path, *, unit_folders=UNIT_FOLDERS)
  .find(kind, value) -> tuple[Path, ...]      # empty means unresolved; unknown kind raises

unresolved(graph, index, kind=None) -> tuple[Reference, ...]
summary(graph, index) -> dict[kind, {"references", "targets", "unresolved"}]
```

## 5. Not in this slice

- The graph resolves inside one root. `check against=` answers what a project does not hold
  from a second root — a directory, another scope, or `stock` — in `core/cli/commands.py`,
  outside this module (docs/cli.md §6); `refs` and `deps` stay single-root, and there is no
  workspace registry.
- No severity model and no report rendering: `unresolved` returns references; deciding
  whether a dangling reference is an error, a warning or a deliberate override belongs with
  the checker.
- Comparisons are exact and case-folded only where §2 says so; no glob or wildcard targets.

Tests: `tests/test_refs.py` (21 cases); the full suite is `python -m unittest discover -s tests
-t .`. The `roster` kind is covered by `tests/test_cli.py`
(a declared entry with and without a document, `refs` of a roster, `deps` of a named unit, and
a surname list contributing nothing).

