# M1 detailed design — tolerant XML ↔ in-house TOML, both directions

> Status: **implemented and measured**. The error model and the schema are on the published branch `m1/pr1-schema`; the parsers, the conversion and the corpus harness are implemented locally and verified against all 1792 modelled stock files — see [m1-report.md](m1-report.md). Publication of the code awaits the project owner's instruction. This document refines [toml-mapping.md](toml-mapping.md) into an implementable design and records the measurements that changed it.

## 1. Scope

M1 delivers the data layer only: reading stock XML, writing TOML, reading TOML, and rendering XML again. No CLI, no reference graph, no event log, no UI, no packaging.

Acceptance is [toml-mapping.md](toml-mapping.md) §8, with the revision in §3.6 below.

## 2. New measurements (all read-only)

The probe that produced these numbers is a local research script and is deliberately **not committed to this repository**; the numbers below are the record, and every one of them can be re-derived from the corpus. Each measurement states the predicate it applies, so it can be re-checked independently:

* §2.1 counts files where, within one parent element, a child that has children appears before a later sibling that has none.
* §2.2 counts files where a child name that already appeared with children reappears after a different child name.
* §2.3 groups every tag by the parent path it occurs under and compares the shapes (leaf, single table, array of tables) it takes in each group.
* §2.4 reads the maximum occurrence count of a tag per parent instance.
* §2.5 counts, within one parent instance, child names that occur more than once **as leaves** (as opposed to branch elements).
* §2.6 counts elements that have neither children nor non-whitespace text.
* §2.7 reads the `mod.txt` of a published mod project, which is not stock data.

### 2.1 The source sibling order cannot be written as literal TOML order (807 of 1792 files)

TOML puts a bare key into the most recently opened table, so every leaf of a parent must be written **before** any of that parent's sub-table or array-of-tables headers. The stock data violates this in **807 of 1792 files**, on these parents:

| Parent tag | Files affected |
|---|---|
| `drive` | 599 |
| `atgun` | 111 |
| `mortar` | 42 |
| `hmg` | 38 |
| `weapon` | 16 |
| `recoilless_rifle` | 1 |

Example (`AT Guns\American-40mm M1.txt`, parent `atgun`): the source order is `image_view_base, image_view_gun, image_profile, weapon, ammo, ammo, AA, mass, trail_length, moveable`, in which the leaves `AA`, `mass`, `trail_length` and `moveable` follow the branch elements `weapon` and `ammo`.

Consequence: **TOML text order is a canonical order chosen by the writer, not a copy of the source order.** Round-trip verification therefore cannot compare sibling order literally; see §3.6.

### 2.2 A branch name reappears after another sibling name in 2 files

`Vehicles\American-M2 Medium Tank.txt` and `Vehicles\American-M2A4 Light Tank.txt` order their `vehicle` children as `attributes, drive, hull, superstructure, fixed_weapon, turret, fixed_weapon, …`, so `<fixed_weapon>` is split by `<turret>`.

This is the only non-contiguous branch case in the corpus. Because sibling order carries no semantics (verified by the project owner), the writer groups `[[squad.vehicle.fixed_weapon]]` together and the order relative to `[[squad.vehicle.turret]]` changes for those two files. Re-opening an array of tables after another header **is** legal TOML (checked against `tomllib`, which accepts `[[a.b]]` … `[a.c]` … `[[a.b]]` while rejecting a re-declared plain table `[a.c]`), so preserving the original order exactly is possible if it is ever wanted; the design does not rely on it.

### 2.3 The same tag has different shapes in different contexts

The corpus uses one tag name with different structures depending on its parent:

| Tag | Under | Shape | Evidence |
|---|---|---|---|
| `type` | `weapon` (root) | leaf | `<type>WEAPON_AT_RIFLE</type>` |
| `type` | `ammo` | array of tables, up to 7 | `<ammo><type>…</type><type>…</type></ammo>` |
| `type` | `description` | leaf | `<type>TYPE_TANK</type>` |
| `weapon` | `man`, `turret`, `fixed_weapon` | array of tables | up to 5 / 3 / 2 per instance |
| `weapon` | `atgun`, `hmg`, `mortar`, `recoilless_rifle` | table | exactly 1 per instance |
| `ammo` | `man`, `turret`, `fixed_weapon`, `atgun` | array of tables | up to 7 / 6 / 5 / 5 |
| `armour` | `hull`, `turret`, `superstructure` | table | 1 per instance |
| `armour` | `description` side (as `body_armour`) | leaf | `body_armour` is a distinct tag |

Consequence: **the schema must be keyed by parent path, never by tag name alone.** A tag-name-keyed schema would give `type` the wrong shape in at least one of its three contexts.

### 2.4 Maximum occurrences per parent instance

The probe prints the full table; the entries that decide array-versus-table are:

| Parent | Children that repeat (max per instance) | Children that never repeat |
|---|---|---|
| `squad` | `man` 13 | `description`, `availability`, `vehicle`, `atgun`, `mortar`, `hmg`, `recoilless_rifle` |
| `vehicle` | `turret` 5, `fixed_weapon` 5, `superstructure` 2 | `attributes`, `drive`, `hull` |
| `drive` | `exhaust_pipe` 2 | `engine`, `gears`, `steering`, `can_make_smoke_screen` |
| `hull` | `man` 5, `smoke_discharger` 2 | `image_view`, `width`, `length`, `height`, `armour` |
| `turret` | `ammo` 6, `smoke_discharger` 6, `man` 5, `weapon` 3 | `diameter`, `height`, `offsetX`, `offsetY`, `rotate_time`, `image_view`, `armour`, `AA`, `rotate_left`, `rotate_right`, `offset_angle` |
| `fixed_weapon` | `ammo` 5, `man` 5, `weapon` 2 | `offsetX`, `offsetY`, `offsetZ`, `rotate_time`, `rotate_left`, `rotate_right`, `image_view`, `offset_angle`, `AA` |
| `man` | `ammo` 7, `weapon` 5 | `job`, `body_armour` |
| `atgun` | `ammo` 5 | `image_view_base`, `image_view_gun`, `image_profile`, `mass`, `trail_length`, `rotate_left`, `rotate_right`, `moveable`, `AA`, `weapon` |
| `mortar` | `ammo` 2 | the rest |
| `recoilless_rifle` | `ammo` 3 | the rest |
| `superstructure` | `smoke_discharger` 6 | `width`, `length`, `height`, `offsetX`, `offsetY`, `armour` |
| `availability` | `data` 14 | — |
| `armament` | `weapon` 20, `ammo` 4 | — |
| `ammo` | `type` 7 | `for`, `rounds`, `flavour` |
| `weapon` (root) | — | `name`, `type`, `usage`, `shoot`, `dimensions`, `magazine`, `ammo`, `offsetX`, `offsetY`, `offset_angle`, `mount`, `comments` |

The per-path form of this table is committed as `docs/baseline/path-inventory.tsv` (289 paths: 227 leaf, 61 branch, 1 mixed), so the schema in `core/schema.py` is reviewable against the measurement rather than against prose.

### 2.5 No leaf repeats anywhere, so M1 needs only arrays of tables

Applying §2.4's predicate to leaves only: across 1792 files there are **26 (parent path, tag) combinations that repeat, and all 26 are branch elements**; no leaf name ever occurs twice inside one parent instance.

Consequence: the TOML subset needs arrays of tables (`[[squad.man]]`) but never a scalar array (`[ "a", "b" ]`), so [toml-mapping.md](toml-mapping.md) §6 stays as narrow as it is. This is what makes §2.7 below a genuine scope boundary rather than a detail.

### 2.6 Empty elements: 70 in the corpus, all of them `<name>` or `<dimensions>`

An element with neither children nor non-whitespace text occurs **70** times: `<name></name>` 37, `<dimensions></dimensions>` 33. The source writes them across two lines (`<dimensions>` newline `</dimensions>`), for example in `Data\Weapons\WEAPON_GRENADE_1914.txt`.

The bare `<dimensions>` form occurs **703** times in total (670 with children, 33 empty), which makes `weapon/dimensions` the one mixed path in §2.4's inventory. It is declared as a `table`: the empty instances become empty tables, and the writer renders an empty table back as `<dimensions></dimensions>`. No dual-shape mechanism is needed.

### 2.7 `mod.txt` repeats a leaf, so it is out of M1

`mod.txt` in the released WW3 mod project (release 2030007 / 2026-10-01) repeats a leaf inside one parent:

```xml
<nationality>
  <equipment>news_main.txt</equipment>
  <equipment>equipment_american.txt</equipment>
```

Expressing that needs a scalar array, which §2.5 shows no stock file requires. Consequence: the `mod` schema moves **out of M1 and into M5** (project files), so M1 covers exactly the three stock roots `squad`, `weapon` and `aircraft`, and `schema_for("mod")` returns `None`. The rest of `mod.txt` is otherwise ordinary: `years`, `credits`, `minimum_commonness`, `text_colours` (hex strings that must stay strings), `flags`, `voice`, `ranks`, `default_images`, and yes/no leaves.

## 3. Design

### 3.1 Module layout

```
core/
├── __init__.py
├── textio.py      single text I/O exit point (cp1252, no BOM, CRLF out, tab indent)
├── errors.py      exception types with file/line context
├── xmlmodel.py    element tree plus raw-text retention
├── xmlread.py     tolerant reader
├── tomlmodel.py   TOML document model (ordered)
├── tomlread.py    in-house TOML reader (documented subset only)
├── tomlwrite.py   in-house TOML writer
├── schema.py      path-keyed schema for squad / weapon / aircraft
└── convert.py     xml_to_toml / toml_to_xml
tools/
└── m1_roundtrip.py   corpus-wide round-trip harness
tests/
├── test_errors.py
├── test_schema.py
├── test_textio.py
├── test_xmlread.py
├── test_tomlread.py
├── test_tomlwrite.py
├── test_convert.py
└── fixtures/
```

### 3.2 Text I/O (`core/textio.py`)

Single exit point, per invariant 3.

```python
def read_source(path: Path) -> SourceText
def write_source(path: Path, text: str) -> None
def normalize_newlines(text: str) -> str      # CRLF/CR/LF -> LF internally
def to_export_newlines(text: str) -> str      # LF -> CRLF on export (decision D3)
```

Rules: decode `cp1252`, record whether a BOM was present (always assert absent for stock), normalise line endings to LF in memory, never re-encode anything that the source could not encode, and always write CRLF with no BOM. A `UnicodeEncodeError` during export is a hard error mapped to `ExportEncodingError` (acceptance item 4).

### 3.3 Tolerant XML reader (`core/xmlread.py`)

```python
def parse(text: str, origin: str) -> XmlDocument
```

Scanner, not a grammar. Rules, each derived from a measurement:

1. A tag opens at `<` and closes at the next `>`; the name charset is `[A-Za-z_][A-Za-z0-9_-]*` plus `[0-9]+` (numeric names occur in `mod.txt`).
2. `&` is an ordinary character; no entity expansion at all. This is what makes the 16 bare-`&` files readable.
3. `//` starts a comment that runs to the end of the line, but only where the marker is at the start of a line or preceded by whitespace, a tab or `>`. All 1732 occurrences in the corpus satisfy that test, so no legitimate value is truncated. Comments are removed from element text before the text is recorded, and the raw commented text is offered to the caller for optional `.editor/notes.toml` capture.
4. Whitespace-only text between elements is discarded; non-whitespace text is retained as the element's value.
5. Nesting is tracked with a stack; a closing tag that does not match the innermost open tag unwinds to the nearest matching open tag (never raises on ragged input), and the unwind is reported as a warning on the document.
6. Each node records `tag`, `children`, `value`, and `line` (1-based).

`XmlDocument` also exposes the original text, used for the "was it edited" test in later milestones.

### 3.4 TOML reader and writer

`core/tomlmodel.py` defines the model:

```python
@dataclass
class TomlValue:
    raw: str          # literal as written in the source, e.g. "0.12" or '"X"'
    value: object     # parsed: int | float | bool | str
    line: int

@dataclass
class TomlTable:
    entries: list[tuple[str, TomlValue | TomlTable | TomlArrayEntry]]
```

`entries` is an ordered list, never a dict, so key order survives; a dict view is offered for lookups.

`tomlread.parse(text, origin) -> TomlTable` accepts exactly the subset in [toml-mapping.md](toml-mapping.md) §6 and raises `TomlSyntaxError` with line and column for everything else: inline tables, arrays, dates, multi-line strings, dotted bare keys. No silent degradation (acceptance item 5).

`tomlwrite.render(doc) -> str` emits the canonical order of §3.5, quotes keys only when required, and writes `raw` verbatim when the value was not edited.

### 3.5 Canonical emission order

For each table the writer emits, in this order:

1. leaf keys, in the order the schema lists them;
2. single-instance sub-tables, in schema order;
3. arrays of tables, in schema order, with each array's items contiguous.

This is the only order TOML can express, and §2.1 shows the source order is unreachable anyway. Because sibling order carries no semantics, the change is safe; §3.6 defines the comparison that makes this testable.

Schema order itself is the order observed in stock, so most files come out in an order close to the original.

### 3.6 Revised acceptance comparison

[toml-mapping.md](toml-mapping.md) §8.1 said "compare node by node on an ordered tree". The measurements in §2.1 and §2.2 make a literal ordered comparison impossible for 807 files, so the criterion is refined to the semantic one the project owner already verified:

* **Siblings of different names**: compared as a multiset, i.e. order-insensitive.
* **Repeated blocks of the same name**: compared as an ordered sequence, i.e. order-sensitive.
* Reported separately as informational, not pass/fail: the count of files whose rendered order happens to equal the source order.

Everything else is compared exactly: tag names, nesting, leaf text (a bare `&` is not equal to `&amp;`), and the number of occurrences.

### 3.7 Conversion

```python
def xml_to_toml(doc: XmlDocument, schema: Schema) -> TomlTable
def toml_to_xml(table: TomlTable, schema: Schema) -> str
```

Type inference follows [toml-mapping.md](toml-mapping.md) §3, with the raw literal kept beside the parsed value. Export re-renders from `raw` unless the value was edited, which is what keeps `0.12` from becoming `0.12000000000000001`.

Values are **not** coerced to the schema's nominal type on import: a field that stock writes as `RELOAD_AUTOMATIC` in one file and `0` in another (both occur under `shoot/reload`) keeps whatever each file had.

Entities are rendered from TOML only; a snapshot shortcut for unedited entities belongs to a later milestone and is deliberately **not** available to M1, so the round-trip test cannot pass vacuously.

### 3.8 Schema (`core/schema.py`)

Declarative and path-keyed:

```python
@dataclass(frozen=True)
class Node:
    name: str
    shape: Literal["leaf", "table", "array"]
    type: Literal["int", "float", "bool", "str", "auto"] = "auto"
    children: tuple["Node", ...] = ()
    required: bool = False
```

Three schemas: `squad`, `weapon` and `aircraft`, all derived from the measured path inventory. `mod` is deferred to M5 (§2.7), so `SCHEMAS` has exactly these three keys and `schema_for("mod")` returns `None`.

The declaration is queried by path:

```python
SCHEMAS: dict[str, Schema]                       # "squad" | "weapon" | "aircraft"
def schema_for(root_tag: str) -> Schema | None
Schema.lookup(path: tuple[str, ...]) -> Node | None   # path includes the root name
Schema.children(path: tuple[str, ...]) -> tuple[Node, ...]
```

A path that the schema does not know resolves to `None` rather than raising; deciding what to do about it is the converter's job.

Shapes come from §2.4/§2.5: a child is `array` exactly when it repeats inside one parent instance, otherwise `table`. The comparison is always made on the parent **path**, never on the tag name, per §2.3 — `type` is a `leaf` under `weapon` and an `array` under `ammo`.

Value types stay `auto` (raw text preserved, per §3.7) except where a measurement shows coercion would corrupt the source:

* `bool` for leaves whose observed value set is only `yes`/`no` (`AA`, `body_armour`, `can_make_smoke_screen`, `can_mount_infantry`, `is_amphibious`, `moveable`, `muzzle_flash`, `single_shot`, `smoke_trail`);
* `str` for the whole `armour` subtree, whose values look like `30@12` or `20` and must not become numbers.

Mixed-typed fields are deliberately left `auto`, so the field that stock writes as `RELOAD_AUTOMATIC` in one file and `0` in another keeps what each file had (§3.7). `required` stays `false` everywhere; M1 does not consume it.

Unknown tags encountered during import are **not** an error in M1: they are preserved as a table of leaves and reported as a warning, because the enumeration tables and the exact tag set are explicitly not frozen (unknown enums warn, never error). Export renders anything the TOML holds, so an unknown tag still round-trips.

### 3.9 Error model (`core/errors.py`)

```
FfError
├── TextDecodeError      (file, offset)
├── XmlStructureError    (file, line)     -- unrecoverable only
├── TomlSyntaxError      (file, line, column, hint)
├── SchemaError          (path, message)
└── ExportEncodingError  (file, value)
```

Warnings are collected on the document, never raised: ragged close tags, unknown tags, unknown enum-shaped values, and dropped comments all take this path.

## 4. Test plan

**Unit tests** (no corpus needed): text I/O round trip including the 16 LF files and a cp1252-only character; the reader against hand-written snippets for a bare `&`, a numeric tag, mixed case, a `//` comment inside an element, an unmatched close tag, and a leaf after a branch; the TOML reader rejecting each unsupported construct with a line number; the writer's canonical order; `0.12` fidelity; `yes`/`no` to boolean.

**Schema tests** (no corpus needed, and no parser): every row of `docs/baseline/path-inventory.tsv` resolves in its root schema with the shape the row implies, the set of `array` nodes equals the set of rows whose `max_per_instance` exceeds 1, and the structural invariants hold (unique child names, `leaf` has no children, canonical child order, `required` unused). These are the tests that keep the committed declaration tied to the committed measurement.

**Failure to keep in mind**: a `mixed` row (`weapon/dimensions`) resolves to `table`, because §2.6 fixes one shape for the field and renders the empty instances as empty tables.

**Corpus harness** (`tools/m1_roundtrip.py`): for all 1840 files, run XML → TOML → XML and compare per §3.6, then TOML → XML → TOML and compare fields. It prints a per-file verdict to `docs/m1-roundtrip.tsv` and a summary, and exits non-zero on any failure.

**Result of that run** (2026-10-09, CPython 3.14.5): 1792 files modelled, 48 skipped by scope, **0 failures**; the exact-text match rate is 0 of 1792 and the three measured causes are listed in [m1-report.md](m1-report.md) §3.1. In short: the canonical writer drops blank lines, expands elements that stock writes inline, and orders differently-named siblings canonically — none of which the §3.6 comparison treats as a difference.

**Must-pass subsets** (acceptance item 3): the 16 bare-`&` files, the 59 aircraft, the single `recoilless_rifle`, the 2 files with a reopened branch, and at least one file from each of the 6 parents listed in §2.1.

**Golden files**: three XML files and their TOML, committed under `tests/fixtures/`, so the mapping itself is reviewable in a diff. The tests require the derived TOML to be byte-identical to the committed file, the TOML to render back to the source tree signature, a full TOML → XML → TOML cycle to return the committed text, and the fixtures to raise no unknown-element warning. They are synthetic and use only declared paths; the first draft used four stock tags that do not exist under the paths it assumed (`image_view` under `squad/description`, `name` and `type` under `squad/man`, `rounds_per_minute` under `weapon/shoot`) and the schema reported each one.

## 5. Task order

The project owner confirmed that the schema is reviewed **first, on its own**, before any conversion code exists, so the schema module is written as a standalone declarative artifact that depends on nothing but `errors.py`.

| # | Task | PR | Depends on | Rough size |
|---|---|---|---|---|
| T1 | `errors.py` and its tests | PR 1 (schema) | — | ~60 lines |
| T4 | `schema.py` for `squad` and `weapon` | PR 1 (schema) | T1 | ~250 lines |
| T5 | `schema.py` for `aircraft` | PR 1 (schema) | T1 | ~120 lines |
| T2 | `textio.py`, `xmlmodel.py`, `xmlread.py` and their tests | PR 2 | T1 | ~300 lines |
| T3 | `tomlmodel.py`, `tomlread.py`, `tomlwrite.py` and their tests | PR 2 | T1 | ~450 lines |
| T6 | `convert.py` and its tests | PR 2 | T2, T3, T4 | ~250 lines |
| T7 | `tools/m1_roundtrip.py` and the corpus run | PR 3 | T6 | ~180 lines |
| T8 | Golden fixtures and `docs/m1-report.md` | PR 3 | T7 | ~100 lines |

PR 1 lands `errors.py`, the full schema and `docs/baseline/path-inventory.tsv`, and is reviewable without any parser: the schema is a table of parent paths, shapes and value types, derived from §2 and [m0-baseline.md](m0-baseline.md) §3, and its coverage test reads the committed inventory. PR 2 lands the parsers and the conversion. PR 3 lands the corpus harness and its report.

Current state: T1, T4 and T5 are on the published branch `m1/pr1-schema`; T2, T3, T6, T7, T8 and the report are complete in the working tree with the corpus run recorded in [m1-report.md](m1-report.md) and 109 unit tests passing locally. Following the project owner's instruction, no further branch is published until that code is verified, which the corpus run above now does.

T2 and T3 share no files, so they can proceed in parallel if the work is split; T6 onward is sequential.

## 6. Risks

| Risk | Mitigation |
|---|---|
| The TOML writer's canonical order diverges from source order more than expected | Measured and accepted: the exact-text match rate is 0 of 1792 files, and every difference is one of the three formatting causes in [m1-report.md](m1-report.md) §3.1. The milestone gate is the semantic criterion, which passes for all 1792 |
| A `//` inside a legitimate value (for example a URL) is stripped as a comment | Resolved by measurement: all **1732** `//` occurrences in the corpus are at the start of a line or preceded by whitespace, tab or `>`, so the reader treats `//` as a comment only in those positions and leaves any other occurrence as data |
| Schema errors surface late, when a rare tag appears | Unknown tags warn and are preserved rather than dropped, so a gap degrades to a warning instead of data loss |
| Numeric fidelity of floats | Never re-render an unedited value; assert in tests that `raw` survives `parse` → `render` |
| The 5-minute log segments and `.editor/` layout are irrelevant to M1 | Nothing in M1 writes `.editor/` |
| Deferring `mod` to M5 leaves the project file unmodelled for now | The deferral is a scope decision, not a gap: stock files never repeat a leaf (§2.5), so no M1 deliverable is blocked by it, and §2.7 records the shape `mod` will need |

## 7. Decisions confirmed by the project owner

1. The revised acceptance comparison in §3.6 is **accepted** as the M1 gate: siblings with different names compare as an unordered multiset, repeated blocks of the same name compare as an ordered sequence. The 807-file finding in §2.1 means source order cannot be reproduced as literal TOML text, and sibling order was verified in-game to carry no semantics.
2. The measurement probe stays **outside** this repository; the numbers are recorded in §2 and the document is the reference.
3. The schema lands **first, on its own**, in a reviewable pull request before any parser or conversion code exists. This is reflected in the PR column of §5.
4. The `mod` schema moves to M5, because `mod.txt` repeats a leaf and the M1 TOML subset deliberately has no scalar arrays (§2.5, §2.7).
5. `docs/baseline/path-inventory.tsv` is committed as a data artifact, like `docs/baseline/summary.json` and `tag-inventory.tsv`: the numbers are the record, and the measurement scripts stay outside the repository.
6. M1 covers the three stock roots `squad`, `weapon` and `aircraft` only. `Maps/` and `Surnames/` remain out of scope.
