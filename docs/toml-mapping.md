# XML ↔ TOML 映射规范（草案 v0）

> 状态：**待用户审阅**。本文定义 M1 要实现的双向映射。
> 前置事实来自 [m0-baseline.md](m0-baseline.md)（全部实测）。

## 1. 总则

1. **TOML 是唯一真源**：工程内的实体数据只以 TOML 存在，XML 只在「导出原版标准」时渲染。
2. **验收口径**（已确认）：`XML → TOML → XML` 与原版 **XML 语义等价**，不要求逐字节一致；
   `TOML → XML → TOML` 要求字段无损。
3. **不引第三方依赖**：按用户指示「TOML 自己写一个对本编辑器特化优化的代码」，
   自研实现（见 §6），不引入 `tomlkit` / `tomli`。
4. **保真优先**：未编辑的实体必须能原样导出。为实现这点，工程内为每个实体保存一份
   「原版源快照」（见 [project-layout.md](project-layout.md)），导出未编辑实体时直接回吐快照。

## 2. 元素 → TOML 的映射规则

原版 XML **没有属性、没有命名空间、没有混合内容**（实测），因此映射规则可以只有 5 条：

| # | XML | TOML | 例 |
|---|---|---|---|
| R1 | 根元素 | 顶层表，表名 = 元素名 | `<squad>` → `[squad]` |
| R2 | 单实例子元素 | 同名键（表 / 标量） | `<description><type>X</type></description>` → `[squad.description]` + `type = "X"` |
| R3 | 多实例子元素 | 数组表 `[[...]]` | `<man>…</man><man>…</man>` → `[[squad.man]]` 两条 |
| R4 | 叶子元素 | 标量键，值按 §3 定型 | `<speed>200</speed>` → `speed = 200` |
| R5 | 元素名不是合法裸键 | 用基本字符串键 | `<1>Pvt</1>` → `"1" = "Pvt"` |

叶子/分支的判定：该元素有子元素 → 表；无子元素 → 标量。
**判定结果按 schema 固定**（不依赖单次数据），以避免同一字段在不同文件里形态不一致。

### 2.1 键名规则

| 情况 | 处理 | 例 |
|---|---|---|
| `[A-Za-z0-9_-]+`（TOML 裸键字符集） | 直接用裸键 | `type = …`、`offsetX = …`、`for = …` |
| 以数字开头 | 用基本字符串键 | `"1" = "Pvt"` |
| 其他（目前原版不存在） | 基本字符串键 + 转义 | — |

camelCase 标签（`offsetX`/`offsetY`/`offsetZ`）**保持原样**，不做 snake_case 化——避免引入无法回转的改名。

## 3. 值类型定型

导出原版标准时，**按值的内容重新渲染**，所以类型推断必须可逆。

| 类型 | 判据 | TOML | 例 |
|---|---|---|---|
| 整数 | `^-?\d+$` | 整数 | `<width>284</width>` → `284` |
| 小数 | `^-?\d+\.\d+$` | 浮点 | `<mass>0.12</mass>` → `0.12` |
| 布尔 | `yes` / `no` | 布尔 | `<AA>yes</AA>` → `true` |
| 字符串 | 其他一切 | 字符串 | `<type>TYPE_TANK</type>` → `"TYPE_TANK"` |

定点风险：`<mass>0.12</mass>` 这类小数**必须原样回吐**（不能变成 `0.12000000000000001`）。
实现上用「原始字符串保留 + 解析值并存」的方式（编辑过才重渲染），这是 M1 的核心保真点之一。

> 尺寸/质量单位：数据文件里的长度单位是 **cm**、质量是 **kg**（沿用既有资料，未在 M0 复核）。

## 4. 顺序

实测：同一父元素下**同一子元素集合存在多种排列**（`<vehicle>` 28 种集合 / 109 种排列），
说明兄弟块顺序不承载语义 → TOML 表天然无序是可接受的。

约定：

* **不同名兄弟块之间**：导出时按固定 schema 顺序渲染。
* **同名重复块之间**（`[[man]]`、`[[turret]]`、`[[ammo]]`…）：**顺序严格保留**，数组顺序即原顺序。
  `<man>` 的排列在游戏里可能影响单位显示顺序，保留顺序是零成本的安全选择。

## 5. 注释与不合法字符

| 情况 | 处理 |
|---|---|
| `//` 注释 | **丢弃**（不参与语义等价）；可选：首次导入时把注释收进 `.editor/notes.toml` 供人查看 |
| 裸 `&`（16 个原版文件） | 解析时当普通字符读入；导出时**原样写出裸 `&`**（转成 `&amp;` 会改变游戏实际读到的字符串，属于语义不等价） |
| `mod.txt` 的数字标签 `<1>` | 见 §2.1；`mod_setting.toml` 单独实现 |
| 换行 | 读入时归一化；导出统一 CRLF（原版 1824/1840 为 CRLF） |
| 缩进 | 导出统一制表符，深度 = 元素嵌套深度 |

## 6. 自研 TOML 实现的范围（`core/toml`）

按「本编辑器特化优化」的要求，只实现我们真正需要的子集，换取**可控的往返保真**与**零依赖**：

**必须支持**

* 顶层表 `[a]`、嵌套表 `[a.b]`、数组表 `[[a.b]]`
* 基本字符串（含转义）、字面字符串、带引号键
* 整数、浮点、布尔
* 注释 `#`、空行、CRLF/LF 混合输入
* **保序**：解析结果保留键的书写顺序（写回 diff 友好）
* **保字面**：数值/字符串保留原始书写形式（`0.12` 不变成 `0.120000`）
* 定位信息：每个键附带源文件行号（供 UI 报错与 AI 定位）

**明确不支持**（遇到即报错，不做静默降级）

* 内联表 `{ }`、数组 `[ ]`、日期时间、多行字符串、点号裸键跨层跳转

理由：这些在原版数据结构里没有对应形态；不支持就报错，比「支持一半」造成的静默损坏安全。

## 7. 映射样例

### 7.1 `<aircraft>` 完整样例

源（`Aircraft/German-Junkers Ju 87 Stuka G.txt`，见 [m0-baseline.md](m0-baseline.md) §3.1）：

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

注意 `<availability>` 本身是单实例（表），其下 `<data>` 才是重复块，所以是 `[[aircraft.availability.data]]`。

### 7.2 `<squad>` + `<vehicle>` 片段（值全部取自原版实测）

源：`Vehicles/German-Panzer IV Ausf D.txt`（151 行）。原文关键片段：

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

映射结果：

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

# …另有 4 条：1940-01/100、1941-06/100、1941-09/50、1941-12/30

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
image_view = "Image-Panzer IV Ausf D&E.png"   # 原版此处为裸 &
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

来源片段同时证实了两件事：

* **`//` 注释会出现在元素内部**（`<armour>` 那一行行尾），且它是元素文本的一部分 → 解析后丢弃，导出时可选重放。
* **`armour` 的角度可省略**（`<side>20</side>` 没有 `@`）。因此 `armour` 的叶子值一律作为**字符串**原样处理，不做数值拆解——导出零风险。

## 8. M1 验收标准

1. **XML → TOML → XML**：对**全部 1840 个文件**跑一遍，产出 XML 与原版**语义等价**
   （判定：宽松解析成有序元素树后逐节点比较标签与文本；裸 `&` 与 `&amp;` 视为不同）。
2. **TOML → XML → TOML**：字段无损（含 `0.12` 这类定点小数、`yes/no`、大小写混合键）。
3. **往返必须覆盖 16 个含裸 `&` 的文件、59 个 aircraft、1 个 `recoilless_rifle`**（边界样本）。
4. 全程 cp1252：导出后每个文件都必须能 `cp1252` 编码（原来 0 个失败，导出也不允许出现失败）。
5. 自研 TOML 实现对不支持的语法**必须报错而非静默降级**（附单元测试）。
