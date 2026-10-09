# XML ↔ TOML mapping specification (draft v0)

> Status: merged into `main`, with the M1 refinements noted in [m1-design.md](m1-design.md). This document defines the bidirectional mapping that M1 implements.
> The underlying facts come from [m0-baseline.md](m0-baseline.md) and are all measured.

## 1. General principles

1. **TOML is the single source of truth**: entity data exists inside a project only as TOML; XML is rendered only for "export to the stock standard".
2. **Acceptance criteria** (agreed): `XML → TOML → XML` must be **semantically equivalent** to stock, not byte-identical; `TOML → XML → TOML` must be lossless at field level.
3. **No third-party dependencies**: following the project owner's instruction to write a TOML implementation specialised for this editor, the code is written in-house (see §6) with no `tomlkit` or `tomli`.
4. **Fidelity first**: an unedited entity must be exportable exactly as it was. To achieve this, the project stores a **stock source snapshot** per entity (see [project-layout.md](project-layout.md)) and echoes the snapshot back when an unedited entity is exported.
5. **Conservative export, tolerant import** (decision D6): the export side follows stock as closely as possible, while the import side may be more robust. Details in §4 and §5.

## 2. Element → TOML mapping rules

Stock XML has **no attributes, no namespaces and no mixed content** (measured), so five rules suffice:

| # | XML | TOML | Example |
|---|---|---|---|
| R1 | Root element | Top-level table named after the element | `<squad>` → `[squad]` |
| R2 | Single-instance child element | Key of the same name (table or scalar) | `<description><type>X</type></description>` → `[squad.description]` plus `type = "X"` |
| R3 | Multiple-instance child element | Array of tables `[[...]]` | `<man>…</man><man>…</man>` → two `[[squad.man]]` entries |
| R4 | Leaf element | Scalar key typed per §3 | `<speed>200</speed>` → `speed = 200` |
| R5 | Element name is not a legal bare key | Basic string key | `<1>Pvt</1>` → `"1" = "Pvt"` |

Leaf or branch is decided by whether the element has children: children mean a table, no children mean a scalar.
**That decision is fixed by the schema**, not by a single file's data, so that one field cannot take different shapes in different files.
**The schema is keyed by parent path, never by tag name alone**: `type` is a leaf directly under `weapon` and under `description`, but an array of tables under `ammo` (up to 7 per instance), and `weapon` is an array of tables under `man`/`turret`/`fixed_weapon` yet a single table under `atgun`/`hmg`/`mortar`/`recoilless_rifle`. A tag-name-keyed schema would assign at least one of those the wrong shape. Measurements are in [m1-design.md](m1-design.md) §2.3 and §2.4.

**Empty elements** (measured: 70 in the corpus, `<name></name>` 37 and `<dimensions></dimensions>` 33) are the empty string as a scalar when the schema calls the field a leaf, and an empty table when the schema calls it a table. `weapon/dimensions` is the one field that is written both ways, and it is declared a table, so its 33 empty instances render back as `<dimensions></dimensions>` ([m1-design.md](m1-design.md) §2.6).

**Arrays of tables are the only array form M1 needs**: no leaf repeats inside one parent instance anywhere in the corpus ([m1-design.md](m1-design.md) §2.5), so the subset in §6 needs no scalar arrays.

### 2.1 Key name rules

| Case | Treatment | Example |
|---|---|---|
| `[A-Za-z0-9_-]+` (the TOML bare-key character set) | Bare key as-is | `type = …`, `offsetX = …`, `for = …` |
| Starts with a digit | Basic string key | `"1" = "Pvt"` |
| Anything else (absent from stock) | Basic string key with escaping | — |

camelCase tags (`offsetX`/`offsetY`/`offsetZ`) **keep their original spelling** and are not converted to snake_case, which avoids introducing a rename that cannot be reversed.

## 3. Value typing

Export to the stock standard **re-renders from the value's content**, so type inference must be reversible.

| Type | Test | TOML | Example |
|---|---|---|---|
| Integer | `^-?\d+$` | Integer | `<width>284</width>` → `284` |
| Decimal | `^-?\d+\.\d+$` | Float | `<mass>0.12</mass>` → `0.12` |
| Boolean | `yes` / `no` | Boolean | `<AA>yes</AA>` → `true` |
| String | everything else | String | `<type>TYPE_TANK</type>` → `"TYPE_TANK"` |

Fixed-point risk: decimals such as `<mass>0.12</mass>` **must be echoed back verbatim** and must never become `0.12000000000000001`.
The implementation keeps the original string alongside the parsed value and re-renders only after an edit; this is one of the core fidelity points of M1.

The table above describes what the syntax would allow. **The schema overrides it for the fields where the generic test would corrupt the source** ([m1-design.md](m1-design.md) §3.8): a pinned `str` field keeps its text even when it looks numeric (`armour` values like `30@12` and `20`), a pinned `bool` field is exactly the `yes`/`no` set, and every other field is `auto`, meaning the original literal is kept and re-rendered verbatim. A field may therefore hold `RELOAD_AUTOMATIC` in one file and `0` in another without either being rewritten.

> Dimensions and mass: length units in the data files are **cm** and mass is in **kg** (taken from the pre-existing reference material; not re-verified in M0).

## 4. Ordering

Statistical evidence: within one parent element the **same child-element set occurs in several orders** (`<vehicle>` shows 28 sets over 109 orderings), which indicates that sibling order carries no semantics. The project owner has verified this on a running installation: exchanging the order of sibling blocks under the same parent still loads correctly.

Conventions (decision D6: conservative export, tolerant import):

* **Between repeated blocks of the same name** (`[[man]]`, `[[turret]]`, `[[ammo]]` …): order is **strictly preserved**, and array order is the original order. This is a zero-cost safe choice.
* **Between siblings of different names**: export renders in **stock order** and never rearranges on its own. An unedited entity goes through snapshot echo and therefore keeps its original order naturally.
* **The import side does not validate order**: any arrangement of sibling blocks must parse successfully.

**TOML text order is a canonical order chosen by the writer, not a copy of the source order.** Measured: in **807 of 1792** files the source order places a leaf after a branch, and TOML does not allow a bare key after a sub-table header (see [m1-design.md](m1-design.md) §2.1). The canonical order is leaves first, then single-instance sub-tables, then arrays of tables, each group following schema order. The difference is safe because sibling order carries no semantics; the comparison used to verify it is defined in §8 item 1.

## 5. Comments and illegal characters

| Case | Treatment |
|---|---|
| `//` comments | **Discarded** (they do not participate in semantic equivalence); optionally collected into `.editor/notes.toml` on first import for human inspection |
| Bare `&` (16 stock files) | Read as an ordinary character on import and **written back as a bare `&`** on export (converting it to `&amp;` would change the string the game actually reads, which is not semantically equivalent) |
| Numeric tags `<1>` in `mod.txt` | See §2.1; `mod_setting.toml` is implemented separately |
| Line endings | Normalised on import; export **always uses CRLF** (decision D3). Stock is CRLF in 1824 of 1840 files, so **the 16 bare-LF files differ from stock after export**; this does not affect the semantic-equivalence criterion but does prevent byte identity |
| Indentation | Export always uses tabs, with depth equal to element nesting depth |
| `<nationality><units>` / `<filename>` in `mod.txt` | **Passed through unchanged**, semantics not interpreted (classified by the project owner as a feature of the stock editor; tracked as a TODO, see [project-layout.md](project-layout.md) §11 D2) |

## 6. Scope of the in-house TOML implementation (`core/toml`)

Following the "specialised for this editor" requirement, only the subset this editor actually needs is implemented, in exchange for **controllable round-trip fidelity** and **zero dependencies**:

**Required**

* Top-level tables `[a]`, nested tables `[a.b]`, arrays of tables `[[a.b]]`
* Basic strings (with escapes), literal strings, quoted keys
* Integers, floats, booleans
* `#` comments, blank lines, mixed CRLF/LF input
* **Order preservation**: the parse result keeps key order as written, which keeps writes diff-friendly
* **Literal preservation**: numbers and strings keep their original written form (`0.12` never becomes `0.120000`)
* Location information: every key carries its source line number for UI error reporting and AI targeting

**Explicitly unsupported** (raises an error instead of degrading silently)

* Inline tables `{ }`, arrays `[ ]`, dates and times, multi-line strings, dotted bare keys that jump levels

Rationale: none of these has a counterpart in the stock data structures, and raising an error is safer than the silent corruption that half-support would cause.

The exclusions are measured, not assumed: no stock file repeats a leaf inside one parent instance ([m1-design.md](m1-design.md) §2.5), so a scalar array is never needed to represent stock data. `mod.txt` is the one file that would need it, and its schema is deferred to M5 for exactly this reason ([m1-design.md](m1-design.md) §2.7).

## 7. Mapping examples

### 7.1 Complete `<aircraft>` example

Source (`Aircraft/German-Junkers Ju 87 Stuka G.txt`, see [m0-baseline.md](m0-baseline.md) §3.1):

```toml
# Mod/Data/Aircraft/German-Junkers Ju 87 Stuka G.toml

[aircraft.description]
type = "TYPE_PLANE"
nationality = "NATIONALITY_GERMAN"
long_name = "Ju 87 Stuka G"
short_name = "Stuka G"
comment = "Stuka G"
image = "Plane-Junkers Ju 87 Stuka G.png"
sound = "SOUND_PROPELLER"
speed = 200

[[aircraft.availability.data]]
month = 3
year = 1943
number = 100

[[aircraft.availability.data]]
month = 12
year = 1945
number = 100

[[aircraft.armament.weapon]]
type = "WEAPON_CANNON_FLAK_43"
offsetX = -315
offsetY = 32

[[aircraft.armament.weapon]]
type = "WEAPON_CANNON_FLAK_43"
offsetX = 331
offsetY = 28

[[aircraft.armament.ammo]]
for = "WEAPON_CANNON_FLAK_43"
flavour = "FLAVOUR_HE"
rounds = 750
```

`<availability>` is itself a single instance (a table) and only `<data>` beneath it repeats, which is why the array header is `[[aircraft.availability.data]]`.

### 7.2 `<squad>` plus `<vehicle>` excerpt (all values taken from measured stock data)

Source: `Vehicles/German-Panzer IV Ausf D.txt` (151 lines). Key excerpt:

```xml
	<vehicle>
		<attributes>
			<image_profile>Profile-Panzer IV Ausf D.png</image_profile>
			<weight>20000</weight>
		</attributes>

		<drive>
			<engine>
				<name>Maybach HL120 TRM</name>
				<horsepower>300</horsepower>
				<reliability>RELIABILITY_AVERAGE</reliability>
				<rpm_idle>500</rpm_idle>
				<rpm_limit>2500</rpm_limit>
			</engine>

			<gears>
				<forwards>6</forwards>
				<reverse>1</reverse>
			</gears>

			<steering>STEERING_CLUTCH_AND_BRAKE</steering>

			<exhaust_pipe><offsetX>-14</offsetX><offsetY>260</offsetY><angle>260</angle><vertical_angle>80</vertical_angle></exhaust_pipe>
		</drive>

		<hull>
			<image_view>Image-Panzer IV Ausf D&E.png</image_view>

			<width>284</width>
			<length>592</length>
			<height>126</height>

			<armour>				// @0 means vertically upright, @90 is horizontal
				<upper_front>30@12</upper_front>
				<lower_front>30@-12</lower_front>
				<side>20</side>
				...
			</armour>
```

Mapping result:

```toml
[squad.description]
type = "TYPE_TANK"
nationality = "NATIONALITY_GERMAN"
long_name = "Panzer IV Ausf. D"
short_name = "Panzer IV D"
comment = "A medium tank with a short barreled 7.5cm KwK 37 L/24 cannon and two MG 34 machine guns, with increased armor"
uniform = "german_vehicle_crew"

[[squad.availability.data]]
month = 11
year = 1939
number = 50

# …four more entries: 1940-01/100, 1941-06/100, 1941-09/50, 1941-12/30

[squad.vehicle.attributes]
image_profile = "Profile-Panzer IV Ausf D.png"
weight = 20000

[squad.vehicle.drive]
steering = "STEERING_CLUTCH_AND_BRAKE"

[squad.vehicle.drive.engine]
name = "Maybach HL120 TRM"
horsepower = 300
reliability = "RELIABILITY_AVERAGE"
rpm_idle = 500
rpm_limit = 2500

[squad.vehicle.drive.gears]
forwards = 6
reverse = 1

[squad.vehicle.drive.exhaust_pipe]
offsetX = -14
offsetY = 260
angle = 260
vertical_angle = 80

[squad.vehicle.hull]
image_view = "Image-Panzer IV Ausf D&E.png"   # bare & in stock
width = 284
length = 592
height = 126

[squad.vehicle.hull.armour]
upper_front = "30@12"
lower_front = "30@-12"
side = "20"
upper_rear = "20@10"
lower_rear = "20@-10"
top = "10"
bottom = "10"
```

The source excerpt also establishes two facts:

* **`//` comments occur inside elements** (at the end of the `<armour>` line) and form part of that element's text → discarded on import, optionally replayed on export.
* **The angle in `armour` may be omitted** (`<side>20</side>` has no `@`). Every `armour` leaf value is therefore handled **as a string**, with no numeric decomposition, which makes export risk-free.

## 8. M1 acceptance criteria

1. **XML → TOML → XML**: run over **all 1840 files** and produce XML that is **semantically equivalent** to stock. The comparison is defined as: parse both sides permissively into element trees, compare **siblings of different names as an unordered multiset** and **repeated blocks of the same name as an ordered sequence**; compare tag names, nesting and leaf text exactly, with a bare `&` never equal to `&amp;`. The count of files whose rendered order happens to equal the source order is reported as information, not as a gate. Rationale for the refinement in [m1-design.md](m1-design.md) §3.6.
2. **TOML → XML → TOML**: lossless at field level, including fixed-point decimals such as `0.12`, `yes/no` values and mixed-case keys.
3. The round trip must **cover the 16 files containing a bare `&`, the 59 aircraft and the single `recoilless_rifle`** (boundary samples).
4. cp1252 throughout: every exported file must encode as `cp1252` (0 failures originally, and export may not introduce any).
5. The in-house TOML implementation **must raise an error rather than degrade silently** on unsupported syntax (with unit tests).
