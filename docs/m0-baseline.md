# M0 基线勘察报告 —《交战》原版数据结构（13.2.0.0）

> 状态：**待用户审阅**。本文只记录对**只读**样本的实测结果与由此得出的结论，不含任何未经实测的断言。
> 复现方式见文末「复现命令」，原始数据见 [baseline/summary.json](baseline/summary.json) 与 [baseline/tag-inventory.tsv](baseline/tag-inventory.tsv)。

## 0. 结论摘要（先说会影响实现的）

| # | 实测结论 | 对实现的影响 |
|---|---|---|
| 1 | 原版数据目录共 **1840** 个 `.txt`，全部是 XML（除 48 个纯文本清单） | 解析规模很小，可全量内存处理，无需流式 |
| 2 | 根元素**有三种**：`<squad>`（1017）、`<weapon>`（716）、`<aircraft>`（59） | 既有资料（针对 12.2.0 的 SKILL 文档）只写了 `squad`/`weapon` 两种，**aircraft 被漏掉**，必须补齐第三套 schema |
| 3 | 全部 1792 个 XML 文件**没有任何 XML 属性**，纯元素嵌套 | 映射到 TOML 时无需处理属性/命名空间，规则可以极简 |
| 4 | 严格 XML 解析有 **64/1840 失败**：48 个是纯文本清单，**16 个是含裸 `&` 的真 XML**（如 `Image-Panzer IV Ausf D&E.png`） | **不能**用 `xml.etree` 之类严格解析器读原版；必须自研容错解析器（裸 `&` 当普通字符） |
| 5 | `mod.txt` **不是合法 XML**：`<ranks>` 下用 `<1>`..`<7>` 作标签名，数字不能作 XML 标签名 | `mod_setting.toml` 的解析同样不能复用严格 XML 解析器 |
| 6 | 编码 **cp1252 无 BOM、0 个无法解码**；换行 CRLF 1824 / 纯 LF 16；缩进制表符，最大深度 4 | 文本 I/O 必须走单一出口；导出时可统一 CRLF，代价是 16 个文件从 LF 变 CRLF（XML 语义等价，符合已确认的验收口径） |
| 7 | 同一父元素下**同一子元素集合存在多种排列**（如 `<vehicle>` 109 种排列 / 28 种子元素集合） | 兄弟块顺序不承载语义，可安全地按固定 schema 顺序导出；**但仍列为 M1 的实测验收项**（见 §7） |

## 1. 勘察对象与环境

| 项 | 值 |
|---|---|
| 游戏 | Firefight（Sean O'Connor 二战即时战术），Steam 版 |
| 游戏根目录 | `D:\Program Files (x86)\Steam\steamapps\common\Firefight` |
| 版本 | `version.txt` = `13.2.0.0`（10 字节，含 CRLF） |
| 数据目录 | `<游戏>/Data` |
| 模组实物样本 | `C:\Users\BC_aw\Downloads\WW3-模组工程文件-发行版2030007-20261001.zip`（43.8 MB / 1712 项，**不入本仓库**） |
| 既有资料（参考） | `C:\Users\BC_aw\Downloads\firefight-modding-SKILL.md`（470 行，基线 12.2.0） |
| 勘察工具 | Python 3（dsh 运行时），仅标准库 |

## 2. 原版数据基线（13.2.0.0）

### 2.1 文件分布

```
Data/                          1840 个文件，扩展名全部为 .txt
├── Weapons/     716   → 根元素 <weapon>
├── Vehicles/    599   ┐
├── Infantry/    307   ├→ 根元素 <squad>
├── AT Guns/     111   ┘
├── Aircraft/     59   → 根元素 <aircraft>
├── Surnames/     36   → 纯文本（每行一个姓氏），非 XML
└── (根)          12   → equipment_<国>_WW2.txt，纯文本（每行一个单位名，可带 // 注释）
```

**目录 → 根元素**是一一对应的确定性映射，每个文件恰好一个根文档：

| 目录 | 根元素 | 文件数 |
|---|---|---|
| `Infantry/`、`Vehicles/`、`AT Guns/` | `<squad>` | 307 + 599 + 111 = **1017** |
| `Weapons/` | `<weapon>` | **716** |
| `Aircraft/` | `<aircraft>` | **59** |
| `Surnames/` | 无（纯文本） | 36 |
| `Data/` 根 | 无（纯文本） | 12 |

### 2.2 文本层铁律（实测）

| 属性 | 实测结果 |
|---|---|
| 编码 | Windows-1252 (cp1252)，**0 个 BOM**，**0 个无法用 cp1252 解码** |
| 换行 | CRLF **1824** 个 / 纯 LF **16** 个（两者游戏都能读） |
| 缩进 | 制表符，深度 1–4（最大深度 4；行首无缩进 43963 行） |
| 注释 | 611 个文件含 `//`；纯文本清单里注释可跟在一行末尾（`Chinese-GEID Infantry Section 1<TAB><TAB>// Central Army Infantry`） |
| XML 属性 | **0 个文件**出现属性 |
| 根元素前文本 | 0 个文件（XML 文件首字符即根标签） |

### 2.3 可解析性（决定解析器选型）

对 1840 个文件逐一做 `xml.etree.ElementTree` 严格解析：

- **可解析 1776 / 1840**
- **不可解析 64**，分成两类：
  - **48 个纯文本清单**（12 个 `equipment_*.txt` + 36 个 `Surnames/surnames_*.txt`）——本来就不是 XML。
  - **16 个真 XML 文件含裸 `&`**，全部在 `Vehicles/`：

    ```
    Vehicles/German-Panzer IV Ausf A.txt      <image_view>Image-Panzer IV Ausf A&B.png</image_view>
    Vehicles/German-Panzer IV Ausf B.txt      同上
    Vehicles/German-Panzer IV Ausf D.txt      <image_view>Image-Panzer IV Ausf D&E.png</image_view>
    Vehicles/German-Panzer IV Ausf E.txt      同上
    Vehicles/German-Panzer IV Ausf F (early).txt  <image_view>Image-Panzer IV Ausf F&F2.png</image_view>
    Vehicles/German-Panzer IV Ausf F2.txt     同上
    Vehicles/German-StuG III Ausf A.txt       <image_profile>Profile-Stug III Ausf A&B.png</image_profile>
    Vehicles/German-StuG III Ausf B.txt       同上
    Vehicles/German-StuG III Ausf C.txt       <image_profile>Profile-Stug III Ausf C&D.png</image_profile>
    Vehicles/German-StuG III Ausf D.txt       同上
    Vehicles/German-StuG III Ausf E.txt       <image_view>Image-Stug III Ausf C&D&E.png</image_view>
    Vehicles/Hungarian-Panzer IV Ausf F.txt   <image_view>Image-Panzer IV Ausf F&F2.png</image_view>
    Vehicles/Hungarian-Panzer IV Ausf F2.txt  同上
    Vehicles/Romanian-T4 G (early).txt        <image_view>Image-Panzer IV Ausf D&E.png</image_view>
    Vehicles/Romanian-T4 G.txt                同上
    Vehicles/Romanian-T4 J.txt                同上
    ```

  游戏能正常加载这些文件 → **游戏的解析器不把 `&` 当实体转义**，我们的解析器必须同样宽松。

### 2.4 `mod.txt` 不是合法 XML（实测）

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

`ElementTree` 报 `not well-formed (invalid token): line 63, column 4`（即 `<1>`）。
→ **数字标签名**必须被解析器接受，映射到 TOML 时键要加引号（`"1" = "Pvt"`）。

## 3. 三套 schema 的完整标签清单

原版 13.2.0.0 共出现 **118 个不同标签**。完整计数见 [baseline/tag-inventory.tsv](baseline/tag-inventory.tsv)，摘要：

| 根元素 | 不同标签数 | 标签总出现次数 |
|---|---|---|
| `<squad>` | 91 | 118605 |
| `<weapon>` | 31 | 18244 |
| `<aircraft>` | 23 | 3177 |

### 3.1 `<aircraft>`（既有资料完全缺失，需逆向）

每文件恰好 1 个 `<aircraft>`，其下三段：

```
<aircraft>
├── <description>     必填：type/nationality/long_name/short_name/comment/image/sound/speed
├── <availability>    <data>* 每项 = month/year/number
└── <armament>
    ├── <weapon>*     type[+offsetX][+offsetY]（挂点偏移；有的挂点无偏移）
    └── <ammo>*       for/flavour/rounds
```

实测样例（`Aircraft/German-Junkers Ju 87 Stuka G.txt`，856 字节；为便于阅读，下面省去了原文件中的空行，元素内容与缩进原样保留）：

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

注意：原版会把兄弟元素**压在同一行**，所以「XML 语义等价」而非逐字节一致是唯一可行的验收口径（与已确认的验收标准一致）。

### 3.2 车辆架构（`<squad>` 内的 `<vehicle>`，599 个）

```
<squad>
├── <description>            1017 个文件全有
├── <availability>           1017 个文件全有；<data> 平均 2.7 条
├── <man>*                   <job>+<weapon>+<ammo>+可选 <body_armour>
└── <vehicle>  (599)
    ├── <attributes>   image_profile / weight / [can_mount_infantry] / [is_amphibious]
    ├── <drive>        exhaust_pipe{offsetX,offsetY,[angle],[vertical_angle]} / engine / gears / steering
    ├── <hull>         man* / image_view / width / length / height / armour / [smoke_discharger]
    ├── <superstructure>*  (537 个文件有 1 个，9 个文件有 2 个)
    ├── <turret>*      (427 文件 1 个 / 10 个 2 个 / 5 个 3 个 / 1 个 5 个)
    └── <fixed_weapon>* (319 文件 1 个 / 64 个 2 个 / … / 最多 5 个)
```

`<armour>` 子标签集合固定（`top/side/rear/front/bottom/upper_front/lower_front/upper_rear/lower_rear/upper_side/lower_side/side_spaced/rear_spaced`），值为 `厚度@角度`。

### 3.3 牵引炮/步兵支援武器（`<squad>` 内的独立块）

| 块 | 数量 | 说明 |
|---|---|---|
| `<atgun>` | 111 | 与 `AT Guns/` 111 个文件一致；含 `<AA>yes</AA>`（42 个 squad 文件含 `AA`） |
| `<mortar>` | 42 | |
| `<hmg>` | 38 | |
| `<recoilless_rifle>` | **1** | 极罕见，但仍要建模 |

### 3.4 `<weapon>`（716 个文件）

```
<weapon>
├── <type>            2203 次 —— **一个文件里 <type> 会重复**（每个弹药型号一个），
│                             且 `<type>` 内的 <name> 与文件名对应
│   └── flavour / mass / speed / [HE(高爆装药质量 kg)] / [era] / [smoke_trail] / [explode_in] / [guided] / name
├── <usage>  → countries / [period]
├── <shoot>  → sound_shoot / rof / [reload] / [muzzle_flash] / [range]
├── <dimensions> → calibre / barrel_length / [number_barrels]
├── <magazine>  → capacity / [sound_reload] / [single_shot] / [sound_eject_clip]
└── <mass> / <speed> / <flavour>
```

### 3.5 需要特别处理的标签

| 标签 | 出现次数 | 特点 |
|---|---|---|
| `offsetX` / `offsetY` / `offsetZ` | 3319 / 3325 / 480（squad）、297 / 241 / 0（aircraft） | **大小写混合**（camelCase），不能用「小写标签名」的假设去扫 |
| `HE` | 583（weapon） | `<ammo><type>` 内的高爆装药质量，与相邻 `<mass>` 同形但语义不同 |
| `AA` | 42（squad） | 布尔 `yes`/`no`，出现在 `atgun`/`turret`/`fixed_weapon` |
| `<1>`..`<7>` | 只出现在 `mod.txt` | 数字标签名，非合法 XML |
| `language` | 2 | 极罕见可选字段（`French-Infantry Section (Colonial).txt` 等） |
| `comments`（复数） | 16 | 与 `<comment>`（单数，squad 用）**不是**同一个标签，别合并 |

## 4. 与既有 SKILL 文档（12.2.0 基线）的差异

| 项 | SKILL 文档（12.2.0） | 实测（13.2.0.0） | 处置 |
|---|---|---|---|
| 根元素 | 仅 `<squad>` 与 `<weapon>` | 多出 **`<aircraft>`（59 个文件，23 个标签）** | 补齐第三套 schema |
| 文件总数 | 「Data 下 1740 个数据 txt」，分目录 308/111/597/676 | **1840**；307/111/599/716/59(Aircraft)/36(Surnames) | 一切以本仓库实测脚本为准，不再引用旧数字 |
| 可解析性 | 未提及 | 16 个文件含裸 `&`，非法 XML | 自研容错解析器 |
| `mantlet` | 「炮塔必填 439/439」 | 467 个 `<turret>`，467 个 `<mantlet>` | 与「必填」结论一致 |
| 英式拼写 | 「铁律：`<armour>` 而非 armor」 | 实测确实是 `armour` | 仅作数据事实记录；**用户已确认不强制** |
| 比例 | 单位 1 m=16 px、地图 1 m=8 px、数据里尺寸 cm | 未复核（M0 只做文本层勘察） | 归入 M2 校验器的待复核项 |
| 枚举基线 | 提供 `enums_ext.txt` | 未重建 | 按已确认口径：沿用旧枚举表，未知枚举只 warning |

## 5. 模组侧实物结构（WW3 样本，用于定型打包与工程布局）

ZIP 内 **1712 项，全部位于 `.Mod/` 前缀下**：

```
.Mod/
├── mod.txt                     10170 字节 / 428 行 / 12 个国家
├── ABOUT.md  Changelog_en.md  Changelog_zh.md  Credits.md  ...
├── CC BY-SA 4.0.txt  ThirdPartyNotices.md  ...
├── Data/                       768 个 .txt
│   ├── (根) 13 个              equipment_american.txt … equipment_Israel.txt … news_main.txt
│   ├── Weapons/    510
│   ├── Vehicles/   179
│   └── Infantry/    63
├── Images/                     861 个 .png + 1 .jpg
│   ├── Chooser/{Buttons}
│   ├── Game/{Control Panel, Flags, Map, Toolbar}
│   ├── Uniforms/uniform_<部队名>/...
│   └── Units/{HMGs, Mortars, Vehicles/{Hulls, Turrets, Profiles}}
└── Sounds/                     68 项 + Voices/CN
```

**三个必须注意的实测事实：**

1. **模组是「部分覆盖」而非完整副本**：样本 mod **没有** `Data/AT Guns/`、没有 `Data/Aircraft/`。所以打包/加载必须能与原版基线**合并**。
2. **`equipment_*.txt` 命名不带时代后缀**：原版是 `equipment_american_WW2.txt`，样本 mod 是 `equipment_american.txt`；mod.txt 用 `<equipment>` 逐个列出（`news_main.txt` 也被列为一个 equipment）。
3. **README/许可证在 `.Mod/` **内部**，ZIP 根目录没有文件** —— 与目前约定的「zip 里一个 Mod 文件夹，外面放 README 和许可证」**不一致**。此项列为待裁决（§7）。
4. `mod.txt` 的 `<nationality>` 里除已列字段外还有两个样本特有标签：`<units>NATIONALITY_TAIWANESE</units>` 与 `<filename>Taiwanese-</filename>`（共各 1 次）。它们像是「该国籍对应的单位文件前缀过滤器」，**需要用户确认语义**（§7）。

## 6. 由本次勘察直接确定的实现决策

| 决策 | 依据 |
|---|---|
| 自研**容错** XML 解析器（裸 `&`、数字标签名、大小写混合标签都能读） | §2.3、§2.4、§3.5 |
| 文本 I/O 单一出口：cp1252 / 无 BOM / 制表符缩进 | §2.2 |
| 三套 schema 平级建模，`<aircraft>` 独立规则 | §3.1 |
| 兄弟元素顺序按固定 schema 顺序导出，组内重复块顺序保留 | §0-7 |
| 导出验收 = XML 语义等价（非逐字节） | §3.1 原版兄弟元素压行 + 已确认口径 |
| `mod.txt` → `mod_setting.toml` 必须独立实现（不复用 XML 解析器） | §2.4 |
| 打包前必须能与原版基线合并（模组是部分覆盖） | §5-1 |

## 7. 待用户裁决 / M1 待实测

**待裁决**

1. 打包 ZIP 的目录布局：`Mod/`（当前约定）还是 `.Mod/`（WW3 实物）？README/许可证放在 ZIP 根还是 `Mod/` 内？
2. `mod.txt` 的 `<units>` / `<filename>` 语义是什么？导出时是否需要生成？
3. 16 个文件的换行从 LF 变为 CRLF（统一导出）是否可接受？

**M1 待实测**

4. 兄弟块顺序交换后游戏是否仍正常加载（本期只用统计证据推断「顺序无语义」，需实机确认）。
5. `mod.txt` 的 `<ranks>` 是否必须恰好 7 档；样本 12 个国家中只有 11 个带 `<ranks>`，缺档时的游戏行为未知。

## 8. 复现命令

```powershell
python tools/recon/baseline_stats.py --data "D:\Program Files (x86)\Steam\steamapps\common\Firefight\Data" --out docs/baseline
```

脚本**只读**（`open(path, "rb")` + 标准库 `os.walk`），不写入游戏目录。两次运行应产出完全相同的 `summary.json` / `tag-inventory.tsv`。
