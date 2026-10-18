> 语言：**中文** | [English](refs.md)

# 引用图

`core/refs.py` 回答一个作用域（原版数据或某个模组工程）的三个问题：

1. 文档里哪些值指向另一个文件（`references_in`）；
2. 双向的谁指向谁（`RefGraph`）；
3. 目标在作用域根下是否存在（`TargetIndex`、`unresolved`、`summary`）。

收集是纯函数式的：输入一个 `XmlElement` 及其来源路径，输出引用。不写文件、不涉及文本编码，因此这一部分直接
跑在数据模型上。

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
| `engine_sound` | `sound` | 任意 | 别名表，见 §3 |
| `roster` | （单位清单的一行） | — | `Data/` 各单位文件夹下按主干名匹配的文档 |

有一类引用不来自叶子标签。单位清单——工程在 `mod.txt` 或 `ModSetting.toml` 里声明的装备表——每行一条，
每条点名一份单位文档。这些条目同样是引用：`roster` 引用进入同一张图，因此 `refs` 会列出它们，
`deps <单位>` 能查出点名该单位的清单，`check` 会把「没有任何文档回应的条目」报成悬空引用而不是盲区
（见 docs/cli.md §4.6）。这条引用点名的是它所在的行号，而不是字段路径。姓氏清单**不是**这类清单：
它点名的是人名而不是文件，其条目只会成为噪声，因此只有装备表会产生引用。

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
* `roster` 条目按文件主干名在 `Data/` 的单位文件夹（`Infantry`、`Vehicles`、`AT Guns`、`Aircraft`）里解析。
  武器文件夹刻意不在其中：武器由使用它的文档引入，任何清单条目都不可能指它。文件夹列表由调用方传入，
  使 `core/cli/commands.py` 保持为唯一声明类别的地方。

## 3. 飞行器的 `<sound>` 是令牌

`Data/Aircraft/*.txt` 里只有一个不同的值 `<sound>SOUND_PROPELLER</sound>`，而
`Sounds/SOUND_PROPELLER.ogg` 并不存在，实际文件是 `Sounds/Engines/plane_propeller.ogg`。因此该标签是符号令牌
而不是文件主干名，`ENGINE_SOUND_ALIASES` 保存了目前观察到的这一条映射。表外的令牌保持未解析，不做猜测。

## 4. API

```python
RefRule(kind, field, parent=None, skip_document_root=False)
Reference(source, path, kind, value)          # path 含根元素名
references_in(root: XmlElement, source: str) -> tuple[Reference, ...]

RefGraph()
  .add(source, element) -> int                # 返回贡献的引用数
  .add_references(found) -> int               # 同上，用于在别处构造好的引用
  .add_roster(source, entries) -> int         # 单位清单的（行号, 名字）对
  .references() / .for_source(source) / .for_target(kind, value)
  .targets(kind=None) / .sources()

TargetIndex(root: Path, *, unit_folders=UNIT_FOLDERS)
  .find(kind, value) -> tuple[Path, ...]      # 空即未解析；未知类别抛异常

unresolved(graph, index, kind=None) -> tuple[Reference, ...]
summary(graph, index) -> dict[kind, {"references", "targets", "unresolved"}]
```

## 5. 本部分未做

* 引用图在一个根内解析。`check against=` 把工程没有持有的引用拿到第二个根下回答——目录、另一个作用域或 `stock`——这段在 `core/cli/commands.py` 里，不在本模块（docs/cli.zh-CN.md §6）；`refs` 与 `deps` 仍是单根，也没有工作区注册表。
* 没有严重级别模型，也没有报告渲染：`unresolved` 只返回引用；判断一条悬空引用是错误、警告还是有意覆盖由检查器
  负责。
* 比较是精确的，仅在 §2 所述之处折叠大小写；不支持通配或模式目标。

测试：`tests/test_refs.py`（21 条）；全套为 `python -m unittest discover -s tests -t .`。
`roster` 类别由 `tests/test_cli.py` 覆盖（已声明的条目有文档与无文档各一、清单的 `refs`、被点名单位的 `deps`、
以及姓氏清单不贡献引用）。

