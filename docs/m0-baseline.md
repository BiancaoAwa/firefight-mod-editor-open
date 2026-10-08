# M0 Baseline Survey — Firefight stock data structures (13.2.0.0)

> Status: merged into `main`. This report records measured results obtained from **read-only** samples and the conclusions drawn from them. It contains no assertion that was not measured.
> Reproduction is described under "Reproduction commands" below. Raw data is in [baseline/summary.json](baseline/summary.json) and [baseline/tag-inventory.tsv](baseline/tag-inventory.tsv).

## 0. Summary of findings (implementation-relevant items first)

| # | Measured result | Effect on the implementation |
|---|---|---|
| 1 | The stock data directory holds **1840** `.txt` files, all XML except 48 plain-text lists | The corpus is small enough to be held in memory; no streaming parser is required |
| 2 | There are **three** root elements: `<squad>` (1017), `<weapon>` (716), `<aircraft>` (59) | The pre-existing reference material (a SKILL document written against 12.2.0) describes only `squad`/`weapon`; **`aircraft` is missing** and a third schema must be added |
| 3 | None of the 1792 XML files contains **any XML attribute**; the format is pure element nesting | TOML mapping needs no attribute or namespace handling and the rules stay minimal |
| 4 | Strict XML parsing fails on **64 of 1840** files: 48 are plain-text lists and **16 are real XML containing a bare `&`** (for example `Image-Panzer IV Ausf D&E.png`) | A strict parser such as `xml.etree` **cannot** be used to read stock data; a tolerant parser that treats a bare `&` as an ordinary character is required |
| 5 | `mod.txt` **is not well-formed XML**: `<ranks>` uses `<1>`..`<7>` as tag names, and a digit is not a legal XML tag name | `mod_setting.toml` likewise cannot be produced by reusing a strict XML parser |
| 6 | Encoding is **cp1252 with no BOM** and **0 files fail to decode**; line endings are CRLF in 1824 files and bare LF in 16; indentation is tabs, maximum depth 4 | Text I/O must pass through a single exit point; export may normalise to CRLF at the cost of 16 files changing from LF to CRLF, which stays within the agreed acceptance criterion of XML semantic equivalence |
| 7 | Within one parent element the **same set of child elements occurs in many different orders** (for example `<vehicle>` shows 109 orderings over 28 child-element sets) | Sibling order carries no semantics, so export in a fixed schema order is safe; the item remains listed as an M1 acceptance check (see §7) |
| 8 | The source sibling order cannot be written as literal TOML order in **807 of 1792** files, because a leaf follows a branch while TOML forbids a bare key after a sub-table header | Export uses a canonical TOML order; the acceptance comparison is refined to be order-insensitive between siblings of different names ([m1-design.md](m1-design.md) §2.1, §3.6) |
| 9 | One tag name carries different shapes in different contexts: `type` is a leaf under `weapon` and `description` but an array of tables under `ammo`; `weapon` is an array under `man`/`turret`/`fixed_weapon` but a single table under `atgun`/`hmg`/`mortar`/`recoilless_rifle` | The schema is keyed by parent path, never by tag name alone ([m1-design.md](m1-design.md) §2.3) |

## 1. Subject and environment

| Item | Value |
|---|---|
| Game | Firefight (Sean O'Connor, WW2 real-time tactics), Steam release |
| Game root | `D:\Program Files (x86)\Steam\steamapps\common\Firefight` |
| Version | `version.txt` = `13.2.0.0` (10 bytes including CRLF) |
| Data directory | `<game>/Data` |
| Mod sample | `C:\Users\BC_aw\Downloads\WW3-模组工程文件-发行版2030007-20261001.zip` (43.8 MB / 1712 entries, **not stored in this repository**) |
| Pre-existing reference | `C:\Users\BC_aw\Downloads\firefight-modding-SKILL.md` (470 lines, baseline 12.2.0) |
| Survey tooling | Python 3 (dsh runtime), standard library only |

## 2. Stock data baseline (13.2.0.0)

### 2.1 File distribution

```
Data/                          1840 files, every extension .txt
├── Weapons/     716   → root element <weapon>
├── Vehicles/    599   ┐
├── Infantry/    307   ├→ root element <squad>
├── AT Guns/     111   ┘
├── Aircraft/     59   → root element <aircraft>
├── Surnames/     36   → plain text (one surname per line), not XML
└── (root)        12   → equipment_<nation>_WW2.txt, plain text (one unit name per line, may carry // comments)
```

The **directory → root element** mapping is a deterministic one-to-one correspondence, with exactly one root document per file:

| Directory | Root element | File count |
|---|---|---|
| `Infantry/`, `Vehicles/`, `AT Guns/` | `<squad>` | 307 + 599 + 111 = **1017** |
| `Weapons/` | `<weapon>` | **716** |
| `Aircraft/` | `<aircraft>` | **59** |
| `Surnames/` | none (plain text) | 36 |
| `Data/` root | none (plain text) | 12 |

### 2.2 Text-layer invariants (measured)

| Property | Measured result |
|---|---|
| Encoding | Windows-1252 (cp1252), **0 BOMs**, **0 files undecodable as cp1252** |
| Line endings | CRLF in **1824** files, bare LF in **16** (the game reads both) |
| Indentation | Tabs, depth 1–4 (maximum depth 4; 43963 lines carry no leading indentation) |
| Comments | 611 files contain `//`; in plain-text lists a comment may follow content on the same line (`Chinese-GEID Infantry Section 1<TAB><TAB>// Central Army Infantry`) |
| XML attributes | **0 files** contain an attribute |
| Text before the root element | 0 files (an XML file begins with its root tag) |

### 2.3 Parseability (this determines parser selection)

Each of the 1840 files was parsed with the strict `xml.etree.ElementTree` parser:

- **Parsed successfully: 1776 / 1840**
- **Parse failures: 64**, in two groups:
  - **48 plain-text lists** (12 `equipment_*.txt` plus 36 `Surnames/surnames_*.txt`) — these were never XML.
  - **16 real XML files containing a bare `&`**, all under `Vehicles/`:

    ```
    Vehicles/German-Panzer IV Ausf A.txt      <image_view>Image-Panzer IV Ausf A&B.png</image_view>
    Vehicles/German-Panzer IV Ausf B.txt      same
    Vehicles/German-Panzer IV Ausf D.txt      <image_view>Image-Panzer IV Ausf D&E.png</image_view>
    Vehicles/German-Panzer IV Ausf E.txt      same
    Vehicles/German-Panzer IV Ausf F (early).txt  <image_view>Image-Panzer IV Ausf F&F2.png</image_view>
    Vehicles/German-Panzer IV Ausf F2.txt     same
    Vehicles/German-StuG III Ausf A.txt       <image_profile>Profile-Stug III Ausf A&B.png</image_profile>
    Vehicles/German-StuG III Ausf B.txt       same
    Vehicles/German-StuG III Ausf C.txt       <image_profile>Profile-Stug III Ausf C&D.png</image_profile>
    Vehicles/German-StuG III Ausf D.txt       same
    Vehicles/German-StuG III Ausf E.txt       <image_view>Image-Stug III Ausf C&D&E.png</image_view>
    Vehicles/Hungarian-Panzer IV Ausf F.txt   <image_view>Image-Panzer IV Ausf F&F2.png</image_view>
    Vehicles/Hungarian-Panzer IV Ausf F2.txt  same
    Vehicles/Romanian-T4 G (early).txt        <image_view>Image-Panzer IV Ausf D&E.png</image_view>
    Vehicles/Romanian-T4 G.txt                same
    Vehicles/Romanian-T4 J.txt                same
    ```

  The game loads these files normally, so **the game's parser does not treat `&` as an entity escape**, and this editor's parser must be equally permissive.

### 2.4 `mod.txt` is not well-formed XML (measured)

```xml
<mod>
	...
	<nationality>
		<name>America (In Production)</name>
		<surnames>surnames_american.txt</surnames>
		...
		<equipment>news_main.txt</equipment>
		<equipment>equipment_american.txt</equipment>

		<voice>US</voice>

		<ranks>
			<1>Pvt</1>
			<2>PFC</2>
			...
```

`ElementTree` reports `not well-formed (invalid token): line 63, column 4`, which is the `<1>` line.
→ **Numeric tag names** must be accepted by the parser, and when mapped to TOML the key requires quoting (`"1" = "Pvt"`).

## 3. Complete tag inventory for the three schemas

Stock 13.2.0.0 uses **118 distinct tags**. Full counts are in [baseline/tag-inventory.tsv](baseline/tag-inventory.tsv); a summary follows:

| Root element | Distinct tags | Total tag occurrences |
|---|---|---|
| `<squad>` | 91 | 118605 |
| `<weapon>` | 31 | 18244 |
| `<aircraft>` | 23 | 3177 |

### 3.1 `<aircraft>` (absent from the pre-existing reference material; reverse-engineered here)

Every file contains exactly one `<aircraft>` with three sections beneath it:

```
<aircraft>
├── <description>     required: type/nationality/long_name/short_name/comment/image/sound/speed
├── <availability>    <data>* where each entry = month/year/number
└── <armament>
    ├── <weapon>*     type[+offsetX][+offsetY] (hardpoint offsets; some hardpoints carry none)
    └── <ammo>*       for/flavour/rounds
```

Measured sample (`Aircraft/German-Junkers Ju 87 Stuka G.txt`, 856 bytes; blank lines of the original are omitted below for readability, while element content and indentation are preserved):

```xml
<aircraft>
	<description>
		<type>TYPE_PLANE</type>
		<nationality>NATIONALITY_GERMAN</nationality>

		<long_name>Ju 87 Stuka G</long_name>
		<short_name>Stuka G</short_name>
		<comment>Stuka G</comment>

		<image>Plane-Junkers Ju 87 Stuka G.png</image>
		<sound>SOUND_PROPELLER</sound>
		<speed>200</speed>
	</description>

	<availability>
		<data><month>3</month><year>1943</year><number>100</number></data>
		<data><month>12</month><year>1945</year><number>100</number></data>
	</availability>

	<armament>
		<weapon><type>WEAPON_CANNON_FLAK_43</type><offsetX>-315</offsetX><offsetY>32</offsetY></weapon>
		<weapon><type>WEAPON_CANNON_FLAK_43</type><offsetX>331</offsetX><offsetY>28</offsetY></weapon>
		<ammo><for>WEAPON_CANNON_FLAK_43</for><flavour>FLAVOUR_HE</flavour><rounds>750</rounds></ammo>
	</armament>
</aircraft>
```

Note that the stock data frequently packs sibling elements **onto a single line**, which makes "XML semantic equivalence" rather than byte-for-byte identity the only workable acceptance criterion, consistent with the agreed acceptance standard.

### 3.2 Vehicle structure (`<vehicle>` inside `<squad>`, 599 instances)

```
<squad>
├── <description>            present in all 1017 files
├── <availability>           present in all 1017 files; 2.7 <data> entries on average
├── <man>*                   <job>+<weapon>+<ammo>+ optional <body_armour>
└── <vehicle>  (599)
    ├── <attributes>   image_profile / weight / [can_mount_infantry] / [is_amphibious]
    ├── <drive>        exhaust_pipe{offsetX,offsetY,[angle],[vertical_angle]} / engine / gears / steering
    ├── <hull>         man* / image_view / width / length / height / armour / [smoke_discharger]
    ├── <superstructure>*  (1 in 537 files, 2 in 9 files)
    ├── <turret>*      (1 in 427 files, 2 in 10, 3 in 5, 5 in 1)
    └── <fixed_weapon>* (1 in 319 files, 2 in 64, … up to 5)
```

The `<armour>` child tag set is fixed (`top/side/rear/front/bottom/upper_front/lower_front/upper_rear/lower_rear/upper_side/lower_side/side_spaced/rear_spaced`), and values have the form `thickness@angle`.

### 3.3 Towed guns and infantry support weapons (standalone blocks inside `<squad>`)

| Block | Count | Note |
|---|---|---|
| `<atgun>` | 111 | Matches the 111 files in `AT Guns/`; carries `<AA>yes</AA>` (42 squad files contain `AA`) |
| `<mortar>` | 42 | |
| `<hmg>` | 38 | |
| `<recoilless_rifle>` | **1** | Very rare, but it must still be modelled |

### 3.4 `<weapon>` (716 files)

```
<weapon>
├── <type>            2203 occurrences — **<type> repeats within one file** (one per ammunition type),
│                              and the <name> inside <type> corresponds to the file name
│   └── flavour / mass / speed / [HE (high-explosive charge mass in kg)] / [era] / [smoke_trail] / [explode_in] / [guided] / name
├── <usage>  → countries / [period]
├── <shoot>  → sound_shoot / rof / [reload] / [muzzle_flash] / [range]
├── <dimensions> → calibre / barrel_length / [number_barrels]
├── <magazine>  → capacity / [sound_reload] / [single_shot] / [sound_eject_clip]
└── <mass> / <speed> / <flavour>
```

### 3.5 Tags requiring special handling

| Tag | Occurrences | Property |
|---|---|---|
| `offsetX` / `offsetY` / `offsetZ` | 3319 / 3325 / 480 (squad), 297 / 241 / 0 (aircraft) | **Mixed case** (camelCase); a scan cannot assume lowercase tag names |
| `HE` | 583 (weapon) | High-explosive charge mass inside `<ammo><type>`; same shape as the adjacent `<mass>` but different semantics |
| `AA` | 42 (squad) | Boolean `yes`/`no`, appearing in `atgun`/`turret`/`fixed_weapon` |
| `<1>`..`<7>` | only in `mod.txt` | Numeric tag names, not legal XML |
| `language` | 2 | Very rare optional field (`French-Infantry Section (Colonial).txt` and similar) |
| `comments` (plural) | 16 | **Not** the same tag as `<comment>` (singular, used by squad); the two must not be merged |

## 4. Differences from the pre-existing SKILL document (12.2.0 baseline)

| Item | SKILL document (12.2.0) | Measured (13.2.0.0) | Disposition |
|---|---|---|---|
| Root elements | Only `<squad>` and `<weapon>` | Adds **`<aircraft>` (59 files, 23 tags)** | Add the third schema |
| File count | "1740 data txt files under Data", split 308/111/597/676 | **1840**; 307/111/599/716/59 (Aircraft)/36 (Surnames) | All numbers come from this repository's measurement script; the older figures are no longer cited |
| Parseability | Not mentioned | 16 files contain a bare `&` and are not well-formed XML | Tolerant parser written in-house |
| `mantlet` | "required on turrets, 439/439" | 467 `<turret>` and 467 `<mantlet>` | Consistent with the "required" conclusion |
| British spelling | "invariant: `<armour>`, not armor" | Measured data does use `armour` | Recorded as a data fact only; **the project owner has confirmed it is not enforced** |
| Scale | Units 1 m = 16 px, map 1 m = 8 px, dimensions in data are cm | Not re-verified (M0 covers only the text layer) | Deferred to the M2 validator's re-verification list |
| Enumeration baseline | Ships `enums_ext.txt` | Not rebuilt | Per the agreed position: reuse the existing enum table and warn, never error, on an unknown enum |

## 5. Mod-side structure (WW3 sample, used to settle packaging and project layout)

The ZIP holds **1712 entries, all under the `.Mod/` prefix**:

```
.Mod/
├── mod.txt                     10170 bytes / 428 lines / 12 nations
├── ABOUT.md  Changelog_en.md  Changelog_zh.md  Credits.md  ...
├── CC BY-SA 4.0.txt  ThirdPartyNotices.md  ...
├── Data/                       768 .txt files
│   ├── (root) 13               equipment_american.txt … equipment_Israel.txt … news_main.txt
│   ├── Weapons/    510
│   ├── Vehicles/   179
│   └── Infantry/    63
├── Images/                     861 .png + 1 .jpg
│   ├── Chooser/{Buttons}
│   ├── Game/{Control Panel, Flags, Map, Toolbar}
│   ├── Uniforms/uniform_<unit name>/...
│   └── Units/{HMGs, Mortars, Vehicles/{Hulls, Turrets, Profiles}}
└── Sounds/                     68 entries + Voices/CN
```

**Four measured facts:**

1. **A mod is a partial overlay, not a complete copy**: the sample mod has **no** `Data/AT Guns/` and no `Data/Aircraft/`. Packaging and loading must therefore be able to **merge** with the stock baseline.
2. **`equipment_*.txt` names omit the era suffix**: stock uses `equipment_american_WW2.txt` while the sample mod uses `equipment_american.txt`; `mod.txt` lists each one individually with `<equipment>` (`news_main.txt` is listed as an equipment too).
3. **README and licence files sit *inside* `.Mod/`, and the ZIP root holds no files** — which is **inconsistent** with "a `Mod/` folder inside the zip with README and licence outside it". Decision D1 settles this in favour of **`Mod/` prefix with the documents at the zip root**; `.Mod/` is a folder-naming convention of that one project, not the root name the game reads. Supporting evidence appears under "Supplementary evidence" below.
4. Beyond the fields listed above, `<nationality>` in `mod.txt` carries two sample-specific tags: `<units>NATIONALITY_TAIWANESE</units>` and `<filename>Taiwanese-</filename>` (one occurrence each). They appear to be a unit-file prefix filter for that nationality. Decision D2 classifies them as **a feature of the stock editor itself**, defers them as a TODO, and passes them through unchanged in v1.

### Supplementary evidence: the game's actual MOD root name (added after M0, from the packager source)

Source: `C:\Users\BC_aw\Downloads\FirefightModPackager.zip` → `FirefightModPackager/ffpack.py`.

| Location | Fact |
|---|---|
| `ffpack.py` line 9 (comment) | "the game MOD root is `assets/Mod/`; `mod.txt` defines the faction and equipment list" |
| `ffpack.py` line 1098 | `mod_files.append((p, "assets/Mod/" + os.path.relpath(p, mod_dir)…))` — packaging writes the whole project under `assets/Mod/` |
| `ffpack.py` lines 1351–1366, `pack_mod_zip()` | A standalone zip task applies **no prefix**; `Data/` and `mod.txt` sit at the zip root |
| `ffpack.py` lines 56–68, `find_mod_root()` | Import accepts only "the **shallowest directory containing `mod.txt`**"; paths such as `Data/` are irrelevant |
| `Firefight.exe` string scan (9464 ASCII strings) | **No** hard-coded `Mod/` or `.Mod/` path; only templates of the form base directory + `Data/…`, such as `Data/Aircraft/`, `Data/AT Guns/`, `Data/Infantry/`, `Data/Vehicles/`, `BData/Weapons/`, `%sData/Surnames/`, `Data/%s` |
| PC-side runtime check (project owner) | The MOD root name is **`Mod/`**, that is, `Mod/` relative to the directory holding the game executable (`Firefight/`) |

Conclusion: **the root name is `Mod/` on both PC and Android** (PC confirmed by the project owner on a running installation, Android evidenced by the `assets/Mod/` packaging path). Export uses `Mod/`; the import path must still accept an arbitrary prefix, because third-party distributions use conventions such as `.Mod/`.

## 6. Implementation decisions taken directly from this survey

| Decision | Basis |
|---|---|
| Write a **tolerant** XML parser in-house (it reads bare `&`, numeric tag names and mixed-case tags) | §2.3, §2.4, §3.5 |
| Single text I/O exit point: cp1252 / no BOM / tab indentation | §2.2 |
| Model the three schemas as peers, with independent rules for `<aircraft>` | §3.1 |
| Export siblings in a fixed schema order while preserving the order of repeated blocks within a group | §0-7 |
| Export acceptance is XML semantic equivalence, not byte identity | §3.1 packed sibling lines plus the agreed standard |
| `mod.txt` → `mod_setting.toml` must be implemented separately, without reusing the XML parser | §2.4 |
| Packaging must be able to merge with the stock baseline, because a mod is a partial overlay | §5-1 |
| Normalise exported line endings to CRLF; install-package root prefix `Mod/` with documents at the zip root; accept any prefix on import | §2.2, §5 supplementary evidence, decisions D1/D3 |
| Conservative export, tolerant import: render in stock order on export and do not validate order on import | §0-7, project owner's runtime verification, decision D6 |

## 7. Decisions taken, pending measurements and open items

**Decided (2026-10-09, details in [project-layout.md](project-layout.md) §11)**

1. Packaged ZIP layout → **`Mod/` prefix with README/LICENSE at the ZIP root**; import accepts any prefix (D1).
2. `<units>` / `<filename>` in `mod.txt` → classified as **a feature of the stock editor itself**, deferred as a TODO, **passed through unchanged and uninterpreted** in v1 (D2).
3. Line endings of 16 files normalised from LF to CRLF → **accepted** (D3). Consequence: those 16 files are not byte-identical to stock after export, which does not affect the semantic-equivalence criterion.
4. Log segmentation → **one file per segment**, sealed after 5 minutes without a new event (D4).
5. Cache location → `.editor/` under the project root (D5).

**Confirmed by the project owner on a running installation**

6. **Sibling order carries no semantics**: exchanging the order of sibling blocks under the same parent still loads correctly in the game, turning the statistical inference in §0-7 into a verified result.
7. **The PC-side MOD root name is `Mod/`**, relative to the directory holding the game executable (`Firefight/`). See §5, "Supplementary evidence".

**Pending M1 measurement**

8. Whether `<ranks>` in `mod.txt` must contain exactly 7 entries; only 11 of the sample's 12 nations carry `<ranks>`, and the game's behaviour with a missing entry is unknown.

**Open TODO (from D2)**

9. Reverse-engineer the real semantics of `<units>` / `<filename>` under `<nationality>` and expose them as editable fields in the UI.

## 8. Reproduction commands

```powershell
python tools/recon/baseline_stats.py --data "D:\Program Files (x86)\Steam\steamapps\common\Firefight\Data" --out docs/baseline
```

The script is **read-only** (`open(path, "rb")` plus the standard-library `os.walk`) and never writes into the game directory. Two runs must produce identical `summary.json` and `tag-inventory.tsv`.
