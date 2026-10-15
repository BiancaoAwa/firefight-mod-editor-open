> 语言：**中文** | [English](cli.md)

# 命令行

状态：**除三个写入者外只读**。`set` 修改一个工程文档的一个字段，`undo` 与 `redo` 按日志记录回退与重做，`export` 把原版 XML
写入调用方指定的目录；其余命令只打印结果。写入者都只改动它们触及的内容：`set` 按字段保证（§4.1），`undo` 与 `redo` 写入
记录下来的字节而非重新序列化的结果（§4.2），`export` 按文件保证（顺序、空行、缩进、注释与换行风格，见 §9 与
toml-mapping §4）。`web` 把同样的结果作为页面发布在 `127.0.0.1`，页面跑的就是同一批命令，写入类命令也一样（见
docs/web.md）。没有打包：该阶段尚不存在。

## 1. 调用方式

```
python -m core.cli <作用域> <命令> [选择器] [key=value ...] [--json]
```

在编辑器根目录（即含 `core/` 的目录）执行。`help` 打印解析器接受的同一张表；`version` 打印编辑器版本、解释器
以及从当前目录解析出的作用域。

## 2. 作用域

作用域根是含 `Data/`、`Images/`、`Sounds/` 的目录。

| 作用域 | 含义 | 解析顺序 |
|---|---|---|
| `Mod` | 当前目录所属的模组工程 | `root=`/`mod=` 选项，否则本地配置里的 `mod`，否则向上最近的含 `mod.toml` 的目录；存在 `Mod/` 时数据在其下，否则在工程根 |
| `Firefight` | 原版游戏数据 | `root=`/`firefight=` 选项，否则 `FIREFIGHT_DATA`，否则向上找到的本地配置里的 `firefight`，否则编辑器随附的副本 |
| `<名称>` | 工作区里的另一个模组文件夹 | 同名目录，否则 `<workspace>/Mods/<名称>`，否则 `<workspace>/<名称>`；工作区来自 `workspace=<目录>`，否则 `FIREFIGHT_MODS`，否则本地配置，否则当前目录 |

作用域根是含 `Data/`、`Images/`、`Sounds/` 的目录；直接传 `Data` 目录也接受，会被归一化到其父目录。对安装版游戏
而言就是含 `Firefight.exe` 的目录。`Firefight` 作用域永不被写入：编辑器不修改游戏目录，`export` 只写入 `to=`
之下。工程只由 `set`、`undo`、`redo` 带 `--write` 写入，且只在工程目录内（§4.1、§4.2）。本地配置
`.ff-editor.local.toml`（键 `firefight`、`mod`、`workspace`）从最近的祖先目录读取，应当写进 `.gitignore`。

## 3. 路径与选择器

命令的第三个参数决定操作对象：

* 省略或 `all`——作用域内的全部实体；
* 类别——`Infantry`、`Vehicles`、`Weapons`、`AT Guns`、`Aircraft`；
* 子目录或单个文件——`Data/Weapons/WEAPON_PISTOL_P38.txt`；
* 文件之后的文档路径后缀——`Data/Infantry/American-Rifle Squad.txt/man/ammo`。

路径用 `/`、相对于作用域根；`\` 也接受。文档在 `Mod` 下按 `.toml` 读取、在 `Firefight` 下按 `.txt` 读取；两者都存在
时以 `.toml` 为准。

## 4. 命令

| 命令 | 别名 | 作用 |
|---|---|---|
| `list` | `ls` | 列出实体及类别、存储格式与大小 |
| `show` | `cat` | 按存储形态显示一个实体，或 `as=toml`、`as=xml`、`as=raw` |
| `get` | | 文档路径处的字段值，或 `field=<a.b.c>` |
| `find` | `grep` | 在选择范围内搜索 `tag=<名称>`、`value=<文本>` 或 `path=<a/b>` |
| `stats` | | 按类别、根元素与存储格式计数 |
| `refs` | `graph` | 选择范围的出向引用，按类别分组 |
| `deps` | | `value=<令牌>` 的入向引用（谁指向它） |
| `check` | `lint` | 全量加载；报告加载错误、警告与悬空引用 |
| `set` | | 修改一个字段，或增删数组项；需要 `--write`（§4.1） |
| `init` | | 新建工程：`mod.toml` 与空的 `Mod/Data`；需要 `--write`（§4.9） |
| `add` | `new` | 新建一个实体文档，内容取自 schema 骨架或 `from=<路径>`；需要 `--write`（§4.5） |
| `remove` | `rm` | 删除一个实体文档；需要 `--write`（§4.5） |
| `index` | | 写出 `.editor/index.toml` 与 `.editor/refs.toml`；需要 `--write`（§4.6） |
| `settings` | | 在工程的原版 `Mod/mod.txt` 与 `mod_setting.toml` 之间转换；需要 `--write`（§4.7） |
| `pack` | | 由工程生成 `<名称>-<版本>.zip`；需要 `--write`（§4.8） |
| `convert` | | 把选择范围转成工程工作文件，写入 `to=<目录>`；需要 `--write`（§4.3） |
| `log` | | 列出日志分段与其中的记录，可过滤；只读（§4.2） |
| `undo` | | 回退最后若干次写入所替换的内容；需要 `--write`（§4.2） |
| `redo` | | 重做最后一次撤销所回退的内容；需要 `--write`（§4.2） |
| `export` | `emit` | 把选择范围写成原版 XML（`to=<目录>`）；来自磁盘的文件按源字节写入 |
| `web` | `serve` | 在 `127.0.0.1` 上发布页面，直到 Ctrl-C（§4.4，见 docs/web.md） |
| `version` | | 编辑器版本、解释器、已解析的作用域 |

选项：`root=`、`workspace=`、`to=`（`export` 的目标目录、`convert` 写入的工程目录，或 `pack` 放置压缩包的目录，§4.8）、
`as=`、`field=`、`type=`、`kind=`、`path=`、`name=`（`init` 写入的模组名，§4.9）、`op=`、`from=`（`set op=append`
用下标，`add` 用文档路径）、`limit=`（默认 200 行；`0` 表示全部）、`document=`、`actor=`、`result=`、`since=`、`until=`
（`log` 的过滤项，§4.2）、`lang=zh|en`（Web 界面语言，§4.4）、`strict=1`（`pack` 在工程存在加载错误或悬空引用时
拒绝写出，§4.8）、`assets=1`（`convert` 另把作用域的 `Images/` 与 `Sounds/` 两棵树复制进来，§4.3）、
`ignore_case=1`、`overwrite=1`（`1` 覆盖已存在的文件，`0` 保留；`export` 与 `pack` 默认覆盖，`convert` 与 `settings`
默认跳过）、`--json`；`init`、`set`、`add`、`remove`、`index`、`settings`、`convert`、`pack`、`undo` 与 `redo`
另有两个裸标志 `--write`（写入改动）与 `--dry-run`（只报告、不写任何东西，§4.1、§4.3）；`undo` 与 `redo` 接受一个
可选计数（§4.2）。
未知选项、未知作用域与不存在的路径都算用法错误。`key=value` 选项顺序任意；`--json` 可以出现在任意位置。

`web` 另有五个选项：`port=`（显式指定端口；不给时复用已在运行的实例，否则取 8765 及以上的第一个空闲端口，§4.4）、
`token=<文本>`（设置后每个 URL 都必须带 `?t=<文本>`）、`pagesize=`（默认每页 200 行）、
`lang=zh|en`（每个页面起始所用的语言，之后页面跟随 `?lang=`，§4.4）、`browser=1`（打开默认浏览器，
而不只是打印地址）。

### 4.1 写一个字段

```
python -m core.cli Mod set <文档> field=<a.b.c> value=<文本> --write [--dry-run]
python -m core.cli Mod set <文档> field=<数组> op=append [from=<n>] --write [--dry-run]
python -m core.cli Mod set <文档> field=<数组>.<n> op=delete --write [--dry-run]
```

* `field=` 是文档内的点分路径，相对于根元素。重复元素或数组需要索引段，例如 `ammo.type.0.flavour`；缺少索引的
  歧义路径会被拒绝，而不是猜一个。`get` 读的是同一套路径，因此 `field=ammo.type.1.name` 返回第二项的 `name`。
* 字段必须由文档根元素的 schema 声明，且值要符合它：布尔接受 `yes`/`no`（按文档自身拼写写出），数值按该字段已有
  的写法写出，字符串原样写出。
* 枚举值来自随编辑器发行的表（`tools/FirefightModPackager/enums_ext.txt`）或同一工程中文档已声明的值；任何表与任何
  文档都未声明过的值会被拒绝，而没有表的字段不做枚举检查。
* 保真：`.txt` 文档由 `export` 使用的同一个保排版写入器重新渲染，`.toml` 文档只在该值所在源行上改写。兄弟行、注释、
  空行与文件自身的换行风格都保留，被改叶子行尾的 `//` 注释同样保留。
* 原子：新字节先写入同目录的临时文件，再用 `os.replace` 覆盖原文件，因此看不到写了一半的文档。
* 加锁：写入期间持有 `.editor/lock`。别人持有的锁会让第二个写者被拒绝而不是交错写入；非创建者永不删除它；陈旧锁只
  报告，不被抢占。
* 防护：暂存之后在磁盘上被改动的文档会被拒绝，而不是被覆盖。
* 拒绝即终态——不重试，文件、锁与 `.editor/` 保持原样。缺少 `--write` 的 `set`、指向 `Firefight` 作用域的写入、
  未知字段、类型不符的值与被持有的锁都以退出码 2 结束；文档编码无法表示的值以退出码 1 结束。
* `--dry-run` 计算并报告完整结果而不写任何东西，连 `.editor/` 本身也不创建。
* `op=append` 向 `field=` 指名的数组表追加一项；`from=<n>` 把已有第 `n` 项的叶子值复制进新项，而不是写空值。
  `op=delete` 删除索引段指的那一项。两者都只在源行上操作，因此其余行、注释、空行与文件自身的换行风格都保持原样。

### 4.2 事件日志、撤销与重做

```
python -m core.cli Mod log [计数] [document=<文本>] [field=<文本>] [actor=cli|mcp]
                       [result=set|add|remove|undo|redo] [since=<时间戳>] [until=<时间戳>] [--json]
python -m core.cli Mod undo [计数] --write [--dry-run] [--json]
python -m core.cli Mod redo [计数] --write [--dry-run] [--json]
```

* 每次实际写入都向 `.editor/log/<分段开始本地时间>.jsonl` 追加一条记录，并把被替换的字节与写入后的字节存入
  `.editor/baseline/<sha256>`。记录字段为 `id`、`segment`、`timestamp`、`actor`、`result`、`target`、`document`、
  `entity`、`field`、`before`、`after`、`digest_before`、`digest_after`、`bytes_before`、`bytes_after`、`dry_run`；
  `result` 为 `set`、`add`、`remove`、`undo` 或 `redo`；字段清单与字节布局见 docs/project-layout.md §8。
* 分段在空闲五分钟之后封存，下一条记录开启新分段，因此按文件名排序读取即按时间排序。`log` 列出分段与最新的 `计数` 条
  记录（默认 20）；它只读，不创建任何文件。
* `log` 也可以过滤。`document=` 与 `field=` 保留取值中包含该文本的记录，`actor=` 与 `result=` 保留完全相等的记录，
  `since=`/`until=` 保留时间戳落在区间内的记录。时间戳按写出的字面值比较，因此 `since=` 与写日志那台机器的时区偏移
  一致。载荷会写明所用过滤项，计数写明在读到多少条中筛出多少条。
* `undo [计数]` 按时间倒序恢复最后 `计数` 次已生效改动所替换的字节（默认 1），每恢复一次追加一条记录，标注它所回退的
  记录。`redo [计数]` 重做最近被回退的改动。`redo` 之后再 `undo` 就是对回退的回退，因此 `undo` → `redo` → `undo`
  得到逐字节相同的内容。撤销一次 `add` 会再次删掉该文档，重做它则按记录的字节写回。
* 整次调用先规划再写入：缺失的基线、记录之后在磁盘上被改动的文档、已消失的文档、大于日志的计数、无内容可回退的日志
  都以退出码 2 拒绝，且该次调用不写入任何部分。已记录字节丢失或与其摘要不符属于硬失败，退出码 1。
* `undo` 与 `redo` 需要 `--write`，与 `set` 一样持有 `.editor/lock`，拒绝 `Firefight` 作用域，并限制在工程目录内。
  拒绝即终态，不重试。`--dry-run` 只报告将要恢复的内容，不持锁、不碰 `.editor/`、不写文档。
* 新的 `set` 会丢弃可重做的内容，与编辑器中的新改动一致。

### 4.3 把原版文件转成工程工作文件

```
python -m core.cli Firefight convert to=<工程> --write [--dry-run] [assets=1] [type=<类别>] [--json]
```

* 从作用域读出选择范围，写到 `<工程>/Mod/<相对路径>`，后缀换成 `.toml`。目标目录自身最后一段已经是 `Mod` 时按原样
  使用。缺少的目录会被创建，因此 `convert` 是唯一能从游戏数据建立工程目录的命令；它不写 `mod.toml`，因为工程元数据
  由作者填（docs/project-layout.md §3）。
* 已存在的目标文件被跳过并计入统计；`overwrite=1` 覆盖它。非实体文件同样跳过并计入统计。纯文本表格由工程设置点名：`Mod/mod.txt` 里的 `<equipment>` 与 `<surnames>`，工程只带 `mod_setting.toml` 时则是该文件的同名键。被点名的文件无论内容如何都算表格（`Mod/Data/news_main.txt` 即是一例）。什么都不点名的作用域——原版作用域没有 `mod.txt`——退回命名约定（`equipment_*`、`surnames_*`），此外没有根元素的 `.txt` 按内容算表格。
* 输出为 UTF-8 无 BOM、CRLF 换行，即 TOML 写入器的规范排版，因此结果与来源的原版 `Data/*.txt` 并不逐字节相同。逐字节
  复现是 `export` 的职责，不是 `convert` 的。
* 不带 `--write` 属于用法错误（退出码 2）。`--dry-run` 报告同一份计划且什么都不写，连目标目录也不建。
* `assets=1` 另把作用域的 `Images/` 与 `Sounds/` 两棵树逐字节复制到 `<工程>/Mod/` 下，跳过规则相同（`overwrite=1` 覆盖）。
  默认关闭：原版作用域下的这两棵树是游戏自带的图与音，携带替换资源的模组应指向持有它们的那个作用域（工程作用域），
  或显式传 `assets=1`。此后 §4.8 的打包会像其他非受管文件一样把它们带进压缩包。
* 至少一个文件转换失败时退出码为 1，否则为 0。
* `convert` 写的是尚无记录版本的文档，因此不追加事件日志记录，也不持有 `.editor/lock`，连 `.editor/` 都不创建。由此有
  两处缺口：它写入的文件无法用 `undo` 回退，并发的 `set` 也不被排除。

### 4.4 Web 界面与运行实例记录

```
python -m core.cli Mod web [port=<n>] [token=<文本>] [pagesize=<n>] [lang=zh|en] [browser=1]
```

* 显式给出 `port=` 时总在该端口启动服务。不给端口时，若已记录的实例仍然应答就复用：打印它的地址，调用方要求打开
  浏览器时打开其页面，本进程立即返回，因此不会意外起第二个后端。否则取 8765 及以上的第一个空闲端口。
* 运行中的实例记录在 `<编辑器文件夹>/.editor/web.json`，识别不出编辑器文件夹时记录在工程目录下，字段为 `pid`、
  `host`、`port`、`url`、`scope`、`token` 与 `started`。正常停止会删除记录。被强杀的进程会留下陈旧记录，此时由其地址
  的探测结果决定，因此崩溃过的界面不会阻塞下一次启动——启动器（`tools/launcher/ff-tool.ps1`）采用同一规则。
* 页面可以运行写入类命令，而命令自身的门始终是最终裁决：页面为接受 `write=1` 的命令传递它，被拒绝时的读法与命令行
  完全一致。`web` 本身在请求内被拒绝，因为它会试图绑定第二个端口（docs/web.md §3）。
* 页面默认中文；给出 `lang=en` 或 URL 上带 `?lang=en` 时用英文。导航栏的语言开关只改语言，保留当前路由；一种语言的
  页面会链到同页面的另一种语言（`core/web/i18n.py`）。

### 4.5 新建与删除文档

```
python -m core.cli Mod add <文档> [from=<路径>] --write [--dry-run]
python -m core.cli Mod remove <文档> --write [--dry-run]
```

* `add` 新建一个实体文档。不给 `from=` 时正文来自该文件夹所承载根元素的 schema 骨架（`Data/Weapons` 是 `weapon`；
  `Data/Infantry`、`Data/Vehicles` 与 `Data/AT Guns` 都是 `squad`；`Data/Aircraft` 是 `aircraft`）；编辑器无法映射的
  文件夹会被拒绝，此时用 `from=<路径>` 说明这是什么文档。给出 `from=` 时，被指名文档的字节会重新渲染进新文件，因此
  `.txt` 源会变成 `.toml`。
* `remove` 删除一个实体文档。
* 两者都写 UTF-8 无 BOM 与 CRLF，持工程锁，并追加一条事件（`result` 为 `add` 或 `remove`）；`undo` 会把被删文档逐字节
  恢复，撤销一次 `add` 则会再次删掉该文件。两者都不写工程目录之外的东西。
* `add` 拒绝已存在的路径，`remove` 拒绝不存在的路径，两者都拒绝 `Firefight` 作用域。

### 4.6 引用索引

```
python -m core.cli Mod index [选择器] --write [--dry-run]
```

* `index` 遍历一次选择范围，写出 `.editor/index.toml`（`[documents]` 表，把每个文档相对路径映射到它的根元素）与
  `.editor/refs.toml`（`[by_source]` 表，把每个文档映射到它指向的令牌）。两个文件的 `[built]` 表记录写入时间、作用域、
  计数，以及整个作用域的一份指纹。
* 该指纹是读到过的每个文件的相对名、大小与写入时间的 SHA-256，是整个作用域一份，而不是每个文档一份。只要有文档增删或
  改动一个字节，指纹就不同，`refs` 与 `deps` 随即忽略两张表、重新遍历文档。载荷会写明这批行来自哪一侧
  （`origin` 为 `index` 或 `scan`），两张表只是某一次查询的缓存，不是第二个事实源。
* 纯文本表格——工程在 `<equipment>`、`<surnames>` 下点名的名字，以及 `equipment_*`、`surnames_*` 命名约定——与没有根元素的 `.txt`、读不了的文件都计入跳过，不算错误。

### 4.7 在原版 `Mod/mod.txt` 与 `mod_setting.toml` 之间转换

```
python -m core.cli Mod settings --write [--dry-run] [op=render|emit] [overwrite=1]
```

* 编辑器以两种形态承载工程的原版设置文件（docs/project-layout.md §4），本命令在两者之间移动。`op=render`（默认）
  读 `<工程>/Mod/mod.txt`，写 `<工程>/mod_setting.toml`；`op=emit` 读 `<工程>/mod_setting.toml`，写
  `<工程>/Mod/mod.txt`。
* `render`：每个元素成为它的表或键，`<nationality>` 块成为 `[[mod_setting.nationality]]` 项，重复的 `<equipment>`
  元素成为每个国籍一个数组，裸的 `<ranks>` 数字成为带引号的键，国籍名保持来源的确切拼写（随附的 WW3 文件里写作
  `Taiwan, China(In Production)` 与 `Japan(In Production)`，括号前无空格）。
* `emit` 在原版形态的文件上是 `render` 的精确逆运算：对随附 WW3 的 `mod.txt` 执行
  `Mod settings op=emit --write`，10170 字节原样重现。元素顺序、制表符缩进与空行都采用原版文件的形态，因此本来就
  该形态的文件逐字节往返。写法不同的文件不被 `render` 保留布局，会以该形态回来。
* 两个方向都是各自源文件的纯函数，并且都会报告无法承载的内容，而不是静默丢弃。
* 目标已存在时会被跳过，除非给出 `overwrite=1`。`op=render` 的目标是可手工编辑的 `mod_setting.toml`，`overwrite=1`
  会丢弃那些编辑；`op=emit` 替换的是游戏读取的原版文件，那一下才会进发行包。随附的 WW3 工程可以说明 `render` 的
  规模：手写的 `mod_setting.toml` 是 79 行、一个国籍，而渲染器从同一份 `mod.txt` 产出 333 行、全部十二个国籍，
  无警告。
* `Firefight` 原版作用域被拒绝，因为两个目标都在工程内。`op` 必须是 `render` 或 `emit`；源文件不存在时被拒绝
  （`nothing to <op> from: <path> is not there`）。

### 4.8 生成模组 zip

```
python -m core.cli Mod pack --write [--dry-run] [to=<目录>] [strict=1] [overwrite=1]
```

* 压缩包采用游戏安装时的布局（docs/project-layout.md §5）：`Mod/`、`README.md` 与 `LICENSE`，都取自工程目录。
  默认目标是工程目录下的 `<名称>-<版本>.zip`；`to=<目录>` 指定别的目录。
* `Mod/` 内，以 TOML 存在的文档回写为原版 XML；该文件存在时，`Mod/mod.txt` 由 `mod_setting.toml` 渲染。
  其余文件（含 `Images/`、`Sounds/`）逐字节复制：手工放入的文件原样进入压缩包，而只有 TOML 孪生文件的文档
  以规范形式写出（制表符、CRLF、UTF-8）。
* 每次打包先跑 §4.3 的检查，载荷里带上它的计数（`check.errors`、`check.dangling`）。无法渲染的文档
  记入 `errors`、不进入压缩包，打包照常继续。
* `strict=1` 把两者都变成拒绝：工程存在加载错误或解析不到的引用时不写出任何内容，避免两种问题被无意带进包里。
  引用图只在工程内建立，不查原版语料（见 §9）。
* 成员使用固定时间戳，因此同一工程两次打包得到相同字节。
* `pack` 不改变任何文档、不加锁，但真正写出压缩包时会向工程日志追加一条 `pack` 记录，说明打了什么包。
  该记录不指向任何文档，也不在可撤销或可重做的栈上，因此不会被回滚（见 docs/project-layout.md §8）。
  `--dry-run`、被拒绝的打包、以及跳过已存在压缩包的情况都不留记录。
* 磁盘上的 `Mod/mod.txt` 与 `mod_setting.toml` 不一致时会被拒绝——否则替换该文件会丢掉较短那份没有承载的内容。
  当 TOML 一侧更新时，先运行 `Mod settings op=render overwrite=1 --write`。
* `Firefight` 原版作用域被拒绝。`overwrite=1` 覆盖已存在的压缩包；不给则跳过。

### 4.9 新建工程

```
python -m core.cli Mod init --write [--dry-run] [name=<文本>]
```

* `init` 是唯一允许作用域尚不存在的命令：`root=` 或 `workspace=` 指定建工程的目录，都不给则用当前目录；
  目录不存在时会创建。其余命令都要求作用域已经存在。
* 它按 schema 骨架写出 `mod.toml`（docs/project-layout.md §3）与空的 `Mod/Data/`。`name=` 填入模组名，
  不给则用目录名。原版作用域 `Firefight` 被拒绝：该安装目录不是一个工程。
* 目录中已存在 `mod.toml` 时拒绝，已初始化的工程不会被覆盖。删除工程就是删除目录，`init` 没有对应命令。
* 新建的 `mod.toml` 与其他新文档一样记录进日志，因此 `Mod undo --write` 会把该文件移除。空的 `Mod/Data`
  是目录而非文档，没有记录可以回滚它。
* 列表型叶（如 `authors`）写成 `key = []`，读取器接受该写法。

## 5. 退出码

| 码 | 含义 |
|---|---|
| 0 | 命令执行完成，没有需要报告的内容 |
| 1 | `check` 发现加载错误、悬空引用或警告；**或**解析/IO 错误导致命令中止（消息会指出文件，已知时给出行号）；**或**已记录的文档版本无法读取（§4.2）；**或**至少一个文件转换失败（§4.3） |
| 2 | 用法错误：未知作用域或命令、缺少或未知选项、路径无法解析，以及所有被拒绝的写入（§4.1、§4.2、§4.3、§4.9） |
| 130 | 被中断（Ctrl-C） |

## 6. 警告

警告不会让加载失败，`check` 以计数加最多 20 条样例报告。真实数据上见到的四类：删除了 `//` 注释、文件按 UTF-8
而非 cp1252 解码、未知元素被保留为叶子、元素内同时有文本与子元素（导出时丢弃文本——见 WW3 工程里的
`</data>>` 笔误）。

## 7. 真实数据实测（2026-10-10）

原版游戏 13.2.0.0 对比已发布的 WW3 模组工程（`.Mod/`，在本仓库之外解包）：

| 命令 | 原版 | WW3 |
|---|---|---|
| `stats` | 1840 文件、48 个列表文件、0 错误、0.6 秒 | 765 文件、13 个列表文件、0 错误、0.2 秒 |
| `check` | 加载 1792、跳过 48、0 错误、612 警告、**2 悬空** | 加载 752、跳过 13、0 错误、559 警告、**911 悬空** |
| `refs` | 23978 条引用、0 错误、4.3 秒 | 5793 条引用、0 错误、0.4 秒 |

对原版 `Vehicles` 选择范围执行 `export` 写出 599 个文件、2371815 字节、0 错误。引用规则与覆盖情况见
[refs.md](refs.zh-CN.md)。

2026-10-11 在写入器学会保留源排版之后重测：`python tools/export_fidelity.py --data "<Firefight>/Data"` 导出
全部 1840 个原版文件，结果为 **1840 个逐字节相同、100.0%**（此前其中 1792 个回来时兄弟节点顺序不同，12 个换行
不同）。

原版数据里的两条悬空引用来自随游戏发布的文件（`Hungarian-TK3.txt` 与 `Hungarian-TKS.txt` 指向
`WEAPON_PISTOL_WZ_35_VIS`）。WW3 的 911 条大多指向原版数据：把模组工程与原版安装作为两个作用域一起检查时，
912 条中有 882 条可以解析。**该回退已实测但尚未实现**——命令行逐个作用域独立解析，跨作用域解析要等工作区注册表。

## 8. 复现演示

```
python -m unittest discover -s tests -t .                       # 运行测试套件
python -m core.cli Firefight stats  "root=<Firefight>"
python -m core.cli Firefight check  "root=<Firefight>" --json
python -m core.cli Firefight refs   "root=<Firefight>" --json --limit 5
python -m core.cli Firefight deps   "value=WEAPON_PISTOL_P38" "root=<Firefight>"
python -m core.cli Firefight export Vehicles "root=<Firefight>" "to=<某个目录>"
python -m core.cli Firefight convert "root=<Firefight>" "to=<新工程>" --write --dry-run
python -m core.cli WW3 stats "root=<解包的 WW3>/.Mod"
python -m core.cli Firefight web    "root=<Firefight>" port=8765
```

两个语料上 `check` 都退出 1，这是有意的报告而非崩溃。`deps` 是作用域级的：一次只回答一个作用域。在已安装的游戏上
`convert` 计划 1792 个文件、跳过 48 个清单文件；不带 `--dry-run` 时就把它们写出来。`web` 会一直阻塞到 Ctrl-C，并
打印它绑定到的地址。

## 9. 本部分的限制

* 一次写入是「一个字段、一个数组项、一个文档（`add`、`remove`）或一整个选择范围（`convert`、`settings`、`index`、`pack`）」。
  没有一次调用里对多个文档施加多处改动的批量编辑。日志与基线属于单个工程，`Firefight` 永不被写入。
* `pack` 生成模组 zip。docs/project-layout.md §5 的 stock 基线比对与 APK 打包未实现；也没有创建工程的命令，
  `mod.toml` 需手写。压缩包里的 `Mod/mod.txt` 在该文件存在时来自 `mod_setting.toml`；不存在时按原样复制现有的
  `Mod/mod.txt`。
* `add` 写的是文档根元素的 schema 骨架，数组被略去（它们的空形态无法被读回）；需要数组项的文档用
  `from=<已有文档>` 或 `convert` 建立，随后用 `set op=append` 填。
* 只有编辑器声明了 schema 的根才能被新建与编辑：`weapon`、`squad`、`aircraft`、`mod` 与 `mod_setting`。`vehicle` 与
  `at_gun` 文件夹承载的是 `squad` 根，同样在覆盖范围内。
* `.editor/index.toml` 与 `.editor/refs.toml` 现在由 `index` 写出；它们是带整作用域指纹的缓存，因此改动一个字节就会让
  `refs` 与 `deps` 退回现算。
* `settings` 在工程自带的原版 `Mod/mod.txt` 与 `mod_setting.toml` 之间双向转换。没有所求方向源文件的工程无法转换；
  源文件里渲染器不认识的元素按普通值保留，而不作解释。`emit` 手写 XML，因此带有原版形态无法直接承载的字符的值会被
  报告，并从该元素里略去。
* `export` 保留源排版：兄弟节点顺序、空行、缩进、`//` 注释与文件自身的换行风格全部来自源文本
  （toml-mapping §4）。没有源文本的文件——`.toml` 工程文档——改用规范写入器（制表符缩进、CRLF、schema 顺序）；
  一次编辑会在内存中让它触及的元素的排版失效。
* `pack` 写出 `Data/` 下的文档以及工程里的 `README.md`/`LICENSE`。`Images/` 与 `Sounds/` 已在工程目录中时被复制；
  把它们带进工程的是 `convert assets=1`（§4.3），从未导入的文件自然不在包里。打包摘要不说明缺了什么。
* `init` 只写出 `mod.toml` 与空的 `Mod/Data`。它不导入原版数据（那是 `convert`，§4.3）、不写 `mod_setting.toml`
  （那是 `settings op=render`，§4.7）、也不从别处读取模板。
* 重新输出的文件是否被引擎接受，要在游戏内加载验证，本工具不做这件事。
* `Maps/`、`Surnames/` 与 `equipment_*` 不在范围内。
* 模组尚未通过 `mod.txt` 加载；模组就是含 `Data/` 的目录。

