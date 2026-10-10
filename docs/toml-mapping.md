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

**XML export order is the source order.** The layout captured by the reader (§4.1) is authoritative, so `export` walks children in the order they appeared in the file and reproduces it byte for byte. Measured over the stock corpus on 2026-10-11: 1840 of 1840 files come back identical (`tools/export_fidelity.py`). Only a document that has no source text — a `.toml` project file — is rendered by the canonical writer, where siblings follow first-appearance order as stored in the TOML (which, for a file converted from XML, is the source order).

### 4.1 Layout (blank lines, indentation, comments, newlines)

Blank lines and indentation are **authored** in the stock files — the reader cannot infer them from the element tree, so they are captured as text:

* every element keeps `prefix` (the text between the previous sibling and its own `<tag>`), `suffix` (the gap before `</tag>` of a branch) or `raw_value` (the gap inside a leaf), and the document keeps `header`, `footer`, `newline` and `indent`;
* the captured text includes the `//` comments of that gap, so comments survive export; the reader still counts and strips them for the TOML view;
* `None` means "no source layout for this element" and the writer falls back to the canonical form (tab indent, CRLF, and the newline style of the document);
* an in-memory edit of a leaf clears that leaf's `raw_value`, so exactly one line changes and every other byte stays as it was — the property `tests/test_roundtrip_bytes.py` pins down.

Consequence for editing: a value change keeps the whole file's layout; a structural change (adding or removing an element) falls back to the canonical form for the touched element only.

## 5. Comments and illegal characters

| Case | Treatment |
|---|---|
| `//` comments | Not modelled in TOML, but **kept as part of the captured layout and written back by `export`** (§4.1); optionally collected into `.editor/notes.toml` on first import for human inspection |
| Bare `&` (16 stock files) | Read as an ordinary character on import and **written back as a bare `&`** on export (converting it to `&amp;` would change the string the game actually reads, which is not semantically equivalent) |
| Numeric tags `<1>` in `mod.txt` | See §2.1; `mod_setting.toml` is implemented separately |
| Line endings | Normalised on import; **export keeps the newline style of the source file** (decision D3, revised 2026-10-11). Stock is CRLF in 1824 of 1840 files and LF in the other 16, and all 1840 now come back byte-identical. A document without source text (a `.toml` project file) is written CRLF |
| Indentation | Export keeps the source indentation (tabs, depth equal to element nesting depth); an element without captured layout falls back to tabs at its nesting depth |
| Blank lines | Authored grouping, captured per element as part of its `prefix` (§4.1) and reproduced as-is |
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

1. **XML → TOML → XML**: run over **all 1840 files** and produce XML that is **semantically equivalent** to stock. The comparison is defined as: parse both sides permissively into element trees, compare **siblings of different names as an unordered multiset** and **repeated blocks of the same name as an ordered sequence**; compare tag names, nesting and leaf text exactly, with a bare `&` never equal to `&amp;`. The count of files whose rendered order happens to equal the source order is reported as information, not as a gate. Rationale for the refinement in [m1-design.md](m1-design.md) §3.6. Since 2026-10-11 that count is 1840 of 1840 and a stronger gate is in place: see item 6.
2. **TOML → XML → TOML**: lossless at field level, including fixed-point decimals such as `0.12`, `yes/no` values and mixed-case keys.
3. The round trip must **cover the 16 files containing a bare `&`, the 59 aircraft and the single `recoilless_rifle`** (boundary samples).
4. Encoding: every exported file must encode in the encoding it was read with — UTF-8 strict first, cp1252 fallback, ASCII reported as cp1252 (0 failures; §7.1 of [m1-report.md](m1-report.md)). Stock data is not uniformly cp1252: 13 files store `×` as UTF-8. cp1252 encodability of the export is recorded as information, not as a gate.
5. The in-house TOML implementation **must raise an error rather than degrade silently** on unsupported syntax (with unit tests).
6. **Byte fidelity (added 2026-10-11)**: `export` reproduces a file read from disk **byte for byte**, including sibling order, blank lines, indentation, `//` comments and newline style, because the reader captures the source layout (§4.1). Gate: `python tools/export_fidelity.py --data "<Firefight>/Data"` exits non-zero unless every file is identical (1840 of 1840 on the stock corpus), and `tests/test_roundtrip_bytes.py` pins the individual layout cases (CRLF, LF, missing trailing newline, trailing blank line, comment before an element, inline branch, multiline leaf, self-closing element, declaration, deep indentation, cp1252 text, stray text). The semantic criterion of item 1 stays the floor and must keep holding for documents rendered without source layout (a `.toml` project file).

---

# XML ↔ TOML 映射规范（草案 v0）

> 状态：已合并进 `main`，并包含 [m1-design.md](m1-design.md) 记录的 M1 细化。本文档定义 M1 实现的双向映射。
> 底层事实来自 [m0-baseline.md](m0-baseline.md)，均为实测。

## 1. 总则

1. **TOML 是唯一事实来源**：项目内实体数据只以 TOML 存在；XML 仅为「导出为原版标准」而渲染。
2. **验收标准**（已议定）：`XML → TOML → XML` 必须与原版**语义等价**，而非逐字节相同；`TOML → XML → TOML` 必须
   在字段级无损。
3. **不使用第三方依赖**：按项目方「为编辑器自研 TOML 实现」的要求，代码自研（见 §6），不使用 `tomlkit` 或
   `tomli`。
4. **保真优先**：未编辑的实体必须能原样导出。为此项目为每个实体保存**原版来源快照**（见
   [project-layout.md](project-layout.md)），导出未编辑实体时回显快照。
5. **保守导出、宽容导入**（裁决 D6）：导出侧尽量贴合原版，导入侧可以更健壮。细节见 §4 与 §5。

## 2. 元素 → TOML 映射规则

原版 XML **没有属性、没有命名空间、没有混合内容**（实测），因此五条规则足够：

| # | XML | TOML | 示例 |
|---|---|---|---|
| R1 | 根元素 | 以元素名命名的顶层表 | `<squad>` → `[squad]` |
| R2 | 单实例子元素 | 同名键（表或标量） | `<description><type>X</type></description>` → `[squad.description]` 加 `type = "X"` |
| R3 | 多实例子元素 | 表数组 `[[...]]` | `<man>…</man><man>…</man>` → 两个 `[[squad.man]]` 条目 |
| R4 | 叶子元素 | 按 §3 定型的标量键 | `<speed>200</speed>` → `speed = 200` |
| R5 | 元素名不是合法裸键 | 基本字符串键 | `<1>Pvt</1>` → `"1" = "Pvt"` |

叶子还是分支由元素是否有子节点决定：有子节点即表，无子节点即标量。**该判定由 schema 固定**，而不是由单个文件
的数据决定，从而避免同一字段在不同文件里形状不同。**schema 以父路径为键，绝不只用标签名**：`type` 在 `weapon`
与 `description` 下是叶子，但在 `ammo` 下是表数组（每个实例最多 7 个）；`weapon` 在
`man`/`turret`/`fixed_weapon` 下是表数组，而在 `atgun`/`hmg`/`mortar`/`recoilless_rifle` 下是单表。只按标签名
建键的 schema 至少会把其中之一判错。实测见 [m1-design.md](m1-design.md) §2.3 与 §2.4。

**空元素**（实测：语料中共 70 个，`<name></name>` 37 个、`<dimensions></dimensions>` 33 个）：schema 判定为
叶子时是空字符串，判定为表时是空表。`weapon/dimensions` 是唯一两种写法都出现的字段，它被声明为表，因此其 33 个
空实例渲染回 `<dimensions></dimensions>`（[m1-design.md](m1-design.md) §2.6）。

**表数组是 M1 唯一需要的数组形式**：语料中没有任何一个父实例内重复出现叶子（[m1-design.md](m1-design.md)
§2.5），因此 §6 的子集不需要标量数组。

### 2.1 键名规则

| 情形 | 处理 | 示例 |
|---|---|---|
| `[A-Za-z0-9_-]+`（TOML 裸键字符集） | 原样裸键 | `type = …`、`offsetX = …`、`for = …` |
| 以数字开头 | 基本字符串键 | `"1" = "Pvt"` |
| 其他（原版中不存在） | 带转义的基本字符串键 | — |

驼峰标签（`offsetX`/`offsetY`/`offsetZ`）**保留原拼写**，不转换为 snake_case，以避免引入无法逆转的重命名。

## 3. 值定型

导出为原版标准时**按值的内容重新渲染**，因此类型推断必须可逆。

| 类型 | 判定 | TOML | 示例 |
|---|---|---|---|
| 整数 | `^-?\d+$` | 整数 | `<width>284</width>` → `284` |
| 小数 | `^-?\d+\.\d+$` | 浮点 | `<mass>0.12</mass>` → `0.12` |
| 布尔 | `yes` / `no` | 布尔 | `<AA>yes</AA>` → `true` |
| 字符串 | 其余一切 | 字符串 | `<type>TYPE_TANK</type>` → `"TYPE_TANK"` |

定点风险：`<mass>0.12</mass>` 这类小数**必须原样回写**，绝不能变成 `0.12000000000000001`。实现把原始字符串与
解析值一同保存，只在编辑之后重新渲染；这是 M1 的核心保真点之一。

上表描述的是语法允许的形态。**对通用判定会破坏来源的字段，schema 会覆盖它**（[m1-design.md](m1-design.md)
§3.8）：钉为 `str` 的字段即使看起来是数字也保留文本（`armour` 的 `30@12`、`20` 等），钉为 `bool` 的字段恰好
是 `yes`/`no` 集合，其余字段为 `auto`，即保留原始字面量并原样渲染。因此同一字段可以在一个文件里是
`RELOAD_AUTOMATIC`、在另一个文件里是 `0`，两者都不会被改写。

> 尺寸与质量：数据文件中长度单位为 **cm**，质量为 **kg**（取自既有参考材料；M0 未重新核验）。

## 4. 顺序

统计证据：同一个父元素内**同一子元素集合会以多种顺序出现**（`<vehicle>` 出现 28 种集合、109 种排列），说明
兄弟顺序不承载语义。项目方已在运行中的安装上验证：交换同一父元素下兄弟块的顺序依然能正确加载。

约定（裁决 D6：保守导出、宽容导入）：

* **同名重复块之间**（`[[man]]`、`[[turret]]`、`[[ammo]]` …）：顺序**严格保留**，数组顺序即原始顺序。这是零代价
  的安全选择。
* **不同名兄弟之间**：导出按**原版顺序**渲染，绝不自行重排。未编辑的实体走快照回显，因此自然保持原顺序。
* **导入侧不校验顺序**：兄弟块的任何排列都必须能解析成功。

**TOML 文本顺序是写入方选定的规范顺序，不是源顺序的复制。** 实测：**1792 个文件中有 807 个**源顺序把叶子放在
分支之后，而 TOML 不允许在子表头之后出现裸键（见 [m1-design.md](m1-design.md) §2.1）。规范顺序是叶子在前、
单实例子表居中、表数组最后，各组内按 schema 顺序。该差异是安全的，因为兄弟顺序不承载语义；用于验证的比较定义
见 §8 第 1 条。

**XML 导出顺序即源顺序。** 读取器捕获的布局（§4.1）是权威的，因此 `export` 按子节点在文件中出现的顺序遍历并
逐字节复现。2026-10-11 在原版语料上的实测：1840 个文件全部原样返回（`tools/export_fidelity.py`）。只有没有源
文本的文档——`.toml` 工程文件——由规范写入器渲染，其兄弟顺序按 TOML 中记录的首现顺序（对由 XML 转换来的文件而言
即源顺序）。

### 4.1 布局（空行、缩进、注释、换行）

空行与缩进在原版文件中是**人为撰写**的——读取器无法从元素树推断，因此按文本捕获：

* 每个元素保留 `prefix`（上一个兄弟与自身 `<tag>` 之间的文本）、`suffix`（分支 `</tag>` 之前的空隙）或
  `raw_value`（叶子内部的空隙），文档保留 `header`、`footer`、`newline` 与 `indent`；
* 捕获的文本包含该空隙中的 `//` 注释，因此注释能存活到导出；读取器仍会为 TOML 视图统计并剥离它们；
* `None` 表示「该元素没有源布局」，写入器回退到规范形式（制表符缩进、CRLF，以及文档的换行风格）；
* 内存中编辑一个叶子会清除该叶子的 `raw_value`，因此恰好只有一行发生变化，其余字节保持不变——该性质由
  `tests/test_roundtrip_bytes.py` 固定。

对编辑的影响：改值会保留整个文件的布局；结构性改动（增删元素）只对被触及的元素回退到规范形式。

## 5. 注释与非法字符

| 情形 | 处理 |
|---|---|
| `//` 注释 | 不在 TOML 中建模，但**作为捕获布局的一部分保留，并由 `export` 写回**（§4.1）；首次导入时可选收集到 `.editor/notes.toml` 供人工查看 |
| 裸 `&`（16 个原版文件） | 导入时按普通字符读取，导出时**写回裸 `&`**（转成 `&amp;` 会改变游戏实际读取的字符串，不再语义等价） |
| `mod.txt` 中的数字标签 `<1>` | 见 §2.1；`mod_setting.toml` 单独实现 |
| 换行符 | 导入时归一化；**导出保留源文件的换行风格**（裁决 D3，2026-10-11 修订）。原版 1840 个文件中 1824 个为 CRLF、其余 16 个为 LF，现在 1840 个全部逐字节相同。无源文本的文档（`.toml` 工程文件）按 CRLF 写出 |
| 缩进 | 导出保留源缩进（制表符，深度等于元素嵌套深度）；没有捕获布局的元素按其嵌套深度回退到制表符 |
| 空行 | 人为分组，按元素作为其 `prefix` 的一部分捕获（§4.1）并原样复现 |
| `mod.txt` 中的 `<nationality><units>` / `<filename>` | **原样透传**，不解释语义（项目方判定为原版编辑器特性；记为 TODO，见 [project-layout.md](project-layout.md) §11 D2） |

## 6. 自研 TOML 实现的范围（`core/toml`）

按「为编辑器专用」的要求，只实现编辑器真正需要的子集，以换取**可控的往返保真**与**零依赖**：

**必需**

* 顶层表 `[a]`、嵌套表 `[a.b]`、表数组 `[[a.b]]`
* 基本字符串（含转义）、字面量字符串、带引号的键
* 整数、浮点、布尔
* `#` 注释、空行、CRLF/LF 混合输入
* **顺序保留**：解析结果按书写顺序保留键序，使写入对 diff 友好
* **字面量保留**：数字与字符串保留原始书写形式（`0.12` 绝不变成 `0.120000`）
* 位置信息：每个键携带其源行号，供 UI 报错与 AI 定位

**明确不支持**（抛错而不是静默退化）

* 内联表 `{ }`、数组 `[ ]`、日期时间、多行字符串、跨层级的点分裸键

理由：这些在原版数据结构中都没有对应物，抛错比「半支持」造成的静默破坏更安全。

这些排除项是实测得出而非假设：没有任何原版文件在同一个父实例内重复出现叶子（[m1-design.md](m1-design.md)
§2.5），因此表示原版数据从不需要标量数组。唯一需要它的文件是 `mod.txt`，正因如此其 schema 推迟到 M5
（[m1-design.md](m1-design.md) §2.7）。

## 7. 映射示例

### 7.1 完整 `<aircraft>` 示例

来源（`Aircraft/German-Junkers Ju 87 Stuka G.txt`，见 [m0-baseline.md](m0-baseline.md) §3.1）：TOML 见上文英文
部分同节（`[aircraft.description]`、两个 `[[aircraft.availability.data]]`、两个 `[[aircraft.armament.weapon]]`
与一个 `[[aircraft.armament.ammo]]`）。

`<availability>` 本身是单实例（表），其下只有 `<data>` 重复，因此数组头是 `[[aircraft.availability.data]]`。

### 7.2 `<squad>` 与 `<vehicle>` 节选（所有取值均来自实测原版数据）

来源：`Vehicles/German-Panzer IV Ausf D.txt`（151 行）。关键节选与映射结果见上文英文部分同节（XML 中的
`attributes`/`drive`/`hull` 结构，映射为 `[squad.description]`、`[[squad.availability.data]]`、
`[squad.vehicle.drive.engine]`、`[squad.vehicle.hull.armour]` 等）。

该节选还确立两个事实：

* **`//` 注释会出现在元素内部**（`<armour>` 行尾），构成该元素文本的一部分 → 导入时丢弃，导出时可选回放。
* **`armour` 中的角度可以省略**（`<side>20</side>` 没有 `@`）。因此每个 `armour` 叶子值都**按字符串**处理，不做
  数值分解，使导出无风险。

## 8. M1 验收标准

1. **XML → TOML → XML**：对**全部 1840 个文件**运行，产出的 XML 与原版**语义等价**。比较定义为：把两侧宽容
   解析为元素树，**不同名兄弟按无序多重集**比较、**同名重复块按有序序列**比较；标签名、嵌套与叶子文本精确比较，
   且裸 `&` 永不等于 `&amp;`。渲染顺序恰好等于源顺序的文件数只作为信息报告，不作为门槛。细化的理由见
   [m1-design.md](m1-design.md) §3.6。2026-10-11 起该计数为 1840/1840，并启用了更强的门槛：见第 6 条。
2. **TOML → XML → TOML**：字段级无损，包括 `0.12` 这类定点小数、`yes/no` 值与大小写混用的键。
3. 往返必须**覆盖含裸 `&` 的 16 个文件、59 个飞行器与唯一的 `recoilless_rifle`**（边界样本）。
4. 编码：每个导出文件必须用读取时使用的编码编码——先严格 UTF-8，回退 cp1252，ASCII 报告为 cp1252（0 失败；
   [m1-report.md](m1-report.md) §7.1）。原版数据并非统一 cp1252：13 个文件用 UTF-8 存 `×`。导出的 cp1252
   可编码性作为信息记录，不作为门槛。
5. 自研 TOML 实现对不支持的语法**必须抛错而不是静默退化**（含单元测试）。
6. **逐字节保真（2026-10-11 新增）**：`export` 把从磁盘读入的文件**逐字节**复现，包括兄弟顺序、空行、缩进、
   `//` 注释与换行风格，因为读取器捕获了源布局（§4.1）。门槛：`python tools/export_fidelity.py --data
   "<Firefight>/Data"` 在任一文件不相同（原版语料为 1840/1840）时以非零退出；`tests/test_roundtrip_bytes.py`
   固定各个布局用例（CRLF、LF、缺尾换行、尾空行、元素前注释、内联分支、多行叶子、自闭合元素、声明、深层缩进、
   cp1252 文本、游离文本）。第 1 条的语义标准仍是底线，并且对没有源布局渲染的文档（`.toml` 工程文件）必须继续
   成立。
