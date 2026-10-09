# Reference graph (M2, first slice)

`core/refs.py` answers three questions about a scope (stock data or one mod project):

1. which values in a document point at another file (`references_in`),
2. who points at what, in both directions (`RefGraph`),
3. whether a target exists under a scope root (`TargetIndex`, `unresolved`, `summary`).

Collection is pure: an `XmlElement` and its source path go in, references come out. Nothing
is written and no text encoding is involved, so this slice runs on the M1 model as is.

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
| `engine_sound` | `sound` | any | alias table, see §4 |

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

## 3. Measured coverage

Local run over the stock `Data/` tree of Firefight 13.2.0.0 (the same 1792 files that M1
models; `equipment_*.txt` and `Surnames/` excluded):

| kind | references | distinct targets | unresolved |
| --- | --- | --- | --- |
| `weapon` | 19456 | 420 | 2 |
| `sound` | 954 | 16 | 0 |
| `image` | 2492 | 1772 | 0 |
| `uniform` | 1017 | 86 | 0 |
| `engine_sound` | 59 | 1 | 0 |
| total | 23978 | 2295 | 2 |

The two unresolved references are a genuine defect in the stock data, not a rule gap:
`WEAPON_PISTOL_WZ_35_VIS` is named by `Data/Vehicles/Hungarian-TK3.txt` and
`Data/Vehicles/Hungarian-TKS.txt` in `squad/vehicle/hull/man/ammo/for`, and no file in
`Data/Weapons/` matches `*WZ_35*`.

Reverse counts are a sanity check rather than a verdict: 297 of 716 weapon documents are
never named by a `type` or `for` slot, because weapons are also reached from equipment lists.
2155 of 2172 `.ogg` files are not named by these tags either, since other systems play
sounds. Neither number means the asset is unused.

## 4. Aircraft `<sound>` is a token

`Data/Aircraft/*.txt` contains a single distinct value, `<sound>SOUND_PROPELLER</sound>`, and
`Sounds/SOUND_PROPELLER.ogg` does not exist; the file is
`Sounds/Engines/plane_propeller.ogg`. The tag is therefore a symbolic token, not a file stem,
and `ENGINE_SOUND_ALIASES` holds the one observed mapping. Tokens outside the table stay
unresolved instead of being guessed.

## 5. API

```python
RefRule(kind, field, parent=None, skip_document_root=False)
Reference(source, path, kind, value)          # path includes the root element name
references_in(root: XmlElement, source: str) -> tuple[Reference, ...]

RefGraph()
  .add(source, element) -> int                # returns references contributed
  .references() / .for_source(source) / .for_target(kind, value)
  .targets(kind=None) / .sources()

TargetIndex(root: Path)
  .find(kind, value) -> tuple[Path, ...]      # empty means unresolved; unknown kind raises

unresolved(graph, index, kind=None) -> tuple[Reference, ...]
summary(graph, index) -> dict[kind, {"references", "targets", "unresolved"}]
```

## 6. Not in this slice

- No cross-scope lookup (a mod project reference pointing at stock data), no workspace
  registry: both arrive with the CLI scopes.
- No severity model and no report rendering: `unresolved` returns references; deciding
  whether a dangling reference is an error, a warning or a deliberate override is M2's
  second slice, together with the checker.
- Comparisons are exact and case-folded only where §2 says so; no glob or wildcard targets.

Tests: `tests/test_refs.py` (21 cases) plus the M1 suite, 130 in total.
