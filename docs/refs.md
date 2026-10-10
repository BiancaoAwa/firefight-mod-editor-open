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

Tests: `tests/test_refs.py` (21 cases); the full suite is `python -m unittest discover -s tests
-t .` with 231 cases.

---

# 引用图（M2，第一部分）

`core/refs.py` 回答一个作用域（原版数据或某个模组工程）的三个问题：

1. 文档里哪些值指向另一个文件（`references_in`）；
2. 双向的谁指向谁（`RefGraph`）；
3. 目标在作用域根下是否存在（`TargetIndex`、`unresolved`、`summary`）。

收集是纯函数式的：输入一个 `XmlElement` 及其来源路径，输出引用。不写文件、不涉及文本编码，因此这一部分直接
跑在 M1 的模型上。

## 1. 规则表

引用是标签在下表中的叶子。规则以标签为键，标签有歧义时再加上父标签。

| 类别 | 标签 | 父标签 | 解析方式 |
| --- | --- | --- | --- |
| `weapon` | `type` | `weapon` | `Data/Weapons/<值>.toml`，否则 `.txt` |
| `weapon` | `for` | `ammo` | `Data/Weapons/<值>.toml`，否则 `.txt` |
| `sound` | `sound_shoot` | 任意 | `Sounds/<值>.ogg` |
| `sound` | `sound_reload` | 任意 | `Sounds/<值>.ogg` |
| `sound` | `sound_eject_clip` | 任意 | `Sounds/<值>.ogg` |
| `image` | `image_view` | 任意 | `Images/` 下按文件名或主干名匹配 |
| `image` | `image_view_base` | 任意 | `Images/` 下按文件名或主干名匹配 |
| `image` | `image_view_gun` | 任意 | `Images/` 下按文件名或主干名匹配 |
| `image` | `image_profile` | 任意 | `Images/` 下按文件名或主干名匹配 |
| `image` | `uniform_ranks` | 任意 | `Images/` 下按文件名或主干名匹配 |
| `image` | `image` | 任意 | `Images/` 下按文件名或主干名匹配 |
| `uniform` | `uniform` | 任意 | 目录 `Images/Uniforms/uniform_<值>/` |
| `engine_sound` | `sound` | 任意 | 别名表，见 §4 |

两条规则必须带上上下文才准确：

* 武器文档自身的 `<type>`（`WEAPON_RPG`、`WEAPON_RIFLE` 等）是类别而不是文件。因此
  `RefRule.skip_document_root` 会跳过深度 2 的 `<type>`，只有嵌在根元素 `<weapon>` 之下的槽位才算引用。
* `type` 在 `<weapon>` 槽位里是引用，在别处只是普通叶子（例如 `squad/type` = `TYPE_TANK`），所以该规则标明了
  父标签。

空叶子永不作为引用：`<dimensions></dimensions>` 没有可解析的值。

## 2. 解析

`TargetIndex(root)` 把一个值映射到某个作用域根。原版数据与模组工程布局相同（`Data/`、`Images/`、`Sounds/`），
因此同一个索引对两者都适用，区别只在根目录。

* 武器优先 `.toml`（模组工程以 TOML 存实体），回退 `.txt`。
* 图像在每个作用域内按文件名与主干名各索引一次，因为两种写法都会出现：`Image-M2 Medium Tank turret.png`
  与 `Plane-Curtiss A-12 Shrike.png` 带扩展名，而文档省略扩展名时主干名查找仍能解析。
* 图像查找忽略大小写。原版有四个飞行器文档写 `Plane-Ilyushin Il-10.png` 与
  `Plane-Ilyushin Il-2 Sturmovik.png`，磁盘上的文件却是 `Plane-Ilyushin IL-10.png` 与
  `Plane-Ilyushin IL-2 Sturmovik.png`。两者都存在时精确大小写匹配优先。
* 武器、声音与制服查找直接访问文件系统，大小写敏感性取决于平台；只有内存中的图像索引需要显式折叠大小写。

## 3. 实测覆盖

对 Firefight 13.2.0.0 的原版 `Data/` 树本地运行（与 M1 建模的同一批 1792 个文件；不含 `equipment_*.txt` 与
`Surnames/`）：

| 类别 | 引用数 | 不同目标数 | 未解析 |
| --- | --- | --- | --- |
| `weapon` | 19456 | 420 | 2 |
| `sound` | 954 | 16 | 0 |
| `image` | 2492 | 1772 | 0 |
| `uniform` | 1017 | 86 | 0 |
| `engine_sound` | 59 | 1 | 0 |
| 合计 | 23978 | 2295 | 2 |

那两条未解析引用是原版数据自身的缺陷，不是规则缺失：`Data/Vehicles/Hungarian-TK3.txt` 与
`Data/Vehicles/Hungarian-TKS.txt` 在 `squad/vehicle/hull/man/ammo/for` 里写了 `WEAPON_PISTOL_WZ_35_VIS`，
而 `Data/Weapons/` 下没有任何文件匹配 `*WZ_35*`。

反向计数只是合理性检查，不是结论：716 个武器文档中有 297 个从未被 `type` 或 `for` 槽位引用，因为武器也会从装备
列表到达；2172 个 `.ogg` 文件中有 2155 个不被这些标签引用，因为其他系统也会播放声音。这两个数字都不代表资源
未被使用。

## 4. 飞行器的 `<sound>` 是令牌

`Data/Aircraft/*.txt` 里只有一个不同的值 `<sound>SOUND_PROPELLER</sound>`，而
`Sounds/SOUND_PROPELLER.ogg` 并不存在，实际文件是 `Sounds/Engines/plane_propeller.ogg`。因此该标签是符号令牌
而不是文件主干名，`ENGINE_SOUND_ALIASES` 保存了目前观察到的这一条映射。表外的令牌保持未解析，不做猜测。

## 5. API

```python
RefRule(kind, field, parent=None, skip_document_root=False)
Reference(source, path, kind, value)          # path 含根元素名
references_in(root: XmlElement, source: str) -> tuple[Reference, ...]

RefGraph()
  .add(source, element) -> int                # 返回贡献的引用数
  .references() / .for_source(source) / .for_target(kind, value)
  .targets(kind=None) / .sources()

TargetIndex(root: Path)
  .find(kind, value) -> tuple[Path, ...]      # 空即未解析；未知类别抛异常

unresolved(graph, index, kind=None) -> tuple[Reference, ...]
summary(graph, index) -> dict[kind, {"references", "targets", "unresolved"}]
```

## 6. 本部分未做

* 没有跨作用域查找（模组工程引用原版数据），没有工作区注册表：两者随命令行作用域一起到来。
* 没有严重级别模型，也没有报告渲染：`unresolved` 只返回引用；判断一条悬空引用是错误、警告还是有意覆盖属于 M2
  的第二部分，与检查器一同完成。
* 比较是精确的，仅在 §2 所述之处折叠大小写；不支持通配或模式目标。

测试：`tests/test_refs.py`（21 条）；全套为 `python -m unittest discover -s tests -t .`，231 条。
