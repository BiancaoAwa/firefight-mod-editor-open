# M1 round-trip report

> Status: measured on the installed stock data, 2026-10-09. This is the evidence for the M1 acceptance criteria in [toml-mapping.md](toml-mapping.md) §8. The per-file rows are committed as `docs/m1-roundtrip.tsv`.

## 1. What was run

```
python tools/m1_roundtrip.py --data "<Firefight>\Data" --out docs
```

* Corpus: `D:\Program Files (x86)\Steam\steamapps\common\Firefight\Data` (game version 13.2.0.0), **1840 `.txt` files**.
* Interpreter: CPython **3.12.14** on Windows, standard library only.
* The harness only reads the game directory: every file is opened with `rb` and never written.

Each modelled file goes through **XML → TOML → TOML text → TOML → XML**, and four gates are recorded per row: the conversion itself, re-parsing the rendered TOML and re-rendering it identically, semantic equivalence of the exported XML with the source, and encodability of the export in the source file's encoding. cp1252 encodability is recorded as a fifth, advisory column.

## 2. Result

| Measurement | Result |
|---|---|
| Files modelled | **1792** (squad 1017, weapon 716, aircraft 59) |
| Files skipped | 48 (12 `equipment_*.txt`, 36 `surnames_*.txt` — out of M1 scope) |
| XML → TOML | 1792 / 1792 ok |
| TOML re-parse and re-render | 1792 / 1792 stable |
| Exported XML semantically equivalent | **1792 / 1792** |
| Source encoding: cp1252 | 1779 |
| Source encoding: UTF-8 | 13 |
| Export encodable as cp1252 | 1792 / 1792 (advisory) |
| Failures | **0** |

Exit status is 0; a single failing file would make it non-zero.

## 3. Acceptance criteria, one by one

### 3.1 Semantic equivalence (toml-mapping §8.1)

Comparison parses both sides permissively into element trees and compares **siblings of different names as an unordered multiset** and **repeated blocks of the same name as an ordered sequence**, with tag names, nesting and leaf text compared exactly. All 1792 modelled files pass.

**The rendered text equals the source text in 0 of 1792 files.** This is expected and is reported as information, not as a gate (toml-mapping §4 and §8.1). Three measured causes, from the smallest file in the corpus (`WEAPON_BOMB_100_POUND.txt`, 14 source lines):

1. **Blank lines between blocks** are dropped: the canonical writer emits a header or a key on every line and nothing else.
2. **Inline branch elements** are expanded. Stock writes
   `<type><flavour>FLAVOUR_BOMB_HE</flavour><speed>0</speed><mass>50</mass><HE>23</HE><name>HE</name></type>` on one line; the canonical export puts every element on its own line at its nesting depth.
3. **Sibling order inside a branch changes** to the canonical order. The same file shows `flavour, speed, mass, HE, name` in stock and `HE, flavour, mass, name, speed` after export. Sibling order of differently-named elements carries no semantics (toml-mapping §4), and the comparison in §8.1 ignores it by design.

### 3.2 TOML → XML → TOML losslessness (toml-mapping §8.2)

For every file the rendered TOML is parsed again and re-rendered; the second rendering is byte-identical to the first in all 1792 cases. Leaf literals survive, including fixed-point decimals (`0.12`), `yes`/`no` flags and mixed-case keys such as `offsetX` and `for`.

### 3.3 Boundary samples (toml-mapping §8.3)

| Sample | Files | Result |
|---|---|---|
| Files containing a bare `&` | 16 | pass (the `&` is written back unescaped, never as `&amp;`) |
| `aircraft` roots | 59 | pass |
| Files containing `<recoilless_rifle>` | 1 (`Infantry/American-Recoilless Rifle M18.txt`) | pass |

### 3.4 Encoding (toml-mapping §8.4)

The corpus is **not uniformly cp1252**: 13 of the 1792 modelled files (the Chinese weapon files, e.g. `WEAPON_RIFLE_QBZ_95.txt`) store `×` as `C3 97`, which every cp1252 decoder accepts as `Ã—`. Decoding cp1252 first therefore corrupts them without any error, so the pipeline decodes **UTF-8 strict first and falls back to cp1252**: a genuine cp1252 file (for example `Chinese-75mm leIG 18.txt` with `ü` as `FC`) is not valid UTF-8 and still lands on cp1252. Pure-ASCII files are reported as cp1252, the export default.

The export is re-encoded in the encoding the file was read with, and no file fails. The `cp1252` column stays in the report as information: it marks files that could not be written as cp1252 at all (none in stock data; the WW3 mod project has 36, mostly Chinese weapon names). BOMs are still stripped on read and never written. **Open question:** whether the engine itself decodes these 13 stock files as UTF-8 is not verified here — an in-game text check would settle it.

### 3.5 Unsupported TOML syntax raises (toml-mapping §8.5)

Inline tables, arrays, dates, multi-line strings, duplicate keys, a table declared twice, unterminated strings, unsupported escapes and unreadable bare keys all raise `TomlSyntaxError` with line and column. Unit tests: **173 tests, all passing** (`python -m unittest discover -s tests -t .`).

### 3.6 Golden fixtures (m1-design §4)

`tests/fixtures/{squad,weapon,aircraft}/` each hold a small hand-written `stock.txt` and the `mapped.toml` the pipeline derives from it. The tests assert that the derived TOML is byte-identical to the committed file, that the TOML renders back to the same tree signature as the source (toml-mapping §8.1), that a full TOML → XML → TOML cycle returns the committed text, and that the fixtures raise no unknown-element warning. They are synthetic, not copies of stock data, and they exercise only paths the schema declares.

## 4. Warnings

| Warning | Files |
|---|---|
| `//` comments removed | 599 |
| File is UTF-8, not cp1252 | 13 |
| Unknown element kept by fallback | **0** |

No element in the corpus falls outside the schema, so the path-keyed shape decision covers the whole stock data tree at path level.

## 5. Reproducing

```
python tools/m1_roundtrip.py --data "<Firefight>\Data" --out docs
python -m unittest discover -s tests -t .
```

The harness is deterministic: two runs write byte-identical `docs/m1-roundtrip.tsv`. `--limit N` stops after N modelled files for a quick check, and `--verbose` prints failures as they happen.

## 6. Not covered here

* `Maps/`, `Surnames/` and `equipment_*` are out of M1 scope (measured as skipped above).
* `mod.txt` and `mod_setting.toml` are deferred to M5 (toml-mapping §6, m1-design §2.7).
* Stock source snapshots and snapshot echo for unedited entities are not implemented yet, so exported order follows the canonical writer rather than the source.
* The reference graph, event log, CLI, packaging and UI are later milestones.
* This repository has no CI runner: the status is a local measurement, not a check run.
