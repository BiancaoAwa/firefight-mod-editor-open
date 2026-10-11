> 语言：**中文** | [English](cli.md)

# 命令行

状态：**除两个写入者外只读**。`set` 修改一个工程文档的一个字段，`export` 把原版 XML 写入调用方指定的目录；其余命令只打印
结果。两个写入者都只改动它们触及的内容：`set` 按字段保证（§4.1），`export` 按文件保证（顺序、空行、缩进、注释与换行风格，
见 §9 与 toml-mapping §4）。`web` 把同样的只读结果作为页面发布在 `127.0.0.1`（见 docs/web.md）。没有事件日志、没有撤销、
没有打包：这些都尚不存在。

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
之下。工程只由 `set --write` 写入，且只在工程目录内（§4.1）。本地配置 `.ff-editor.local.toml`（键 `firefight`、
`mod`、`workspace`）从最近的祖先目录读取，应当写进 `.gitignore`。

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
| `set` | | 修改一个文档的一个字段；需要 `--write`（§4.1） |
| `export` | `emit` | 把选择范围写成原版 XML（`to=<目录>`）；来自磁盘的文件按源字节写入 |
| `web` | `serve` | 在 `127.0.0.1` 上发布只读页面，直到 Ctrl-C（见 docs/web.md） |
| `version` | | 编辑器版本、解释器、已解析的作用域 |

选项：`root=`、`workspace=`、`to=`、`as=`、`field=`、`type=`、`kind=`、`path=`、`limit=`（默认 200 行）、
`ignore_case=1`、`--json`；`set` 另有两个裸标志 `--write`（写入改动）与 `--dry-run`（只报告、不写任何东西，§4.1）。
未知选项、未知作用域与不存在的路径都算用法错误。`key=value` 选项顺序任意；`--json` 可以出现在任意位置。

`web` 另有四个选项：`port=`（默认 8765）、`token=<文本>`（设置后每个 URL 都必须带 `?t=<文本>`）、`pagesize=`
（默认每页 200 行）、`browser=1`（打开默认浏览器，而不只是打印地址）。

### 4.1 写一个字段

```
python -m core.cli Mod set <文档> field=<a.b.c> value=<文本> --write [--dry-run]
```

* `field=` 是文档内的点分路径，相对于根元素。重复元素或数组需要索引段，例如 `ammo.type.0.flavour`；缺少索引的
  歧义路径会被拒绝，而不是猜一个。
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

## 5. 退出码

| 码 | 含义 |
|---|---|
| 0 | 命令执行完成，没有需要报告的内容 |
| 1 | `check` 发现加载错误、悬空引用或警告；**或**解析/IO 错误导致命令中止（消息会指出文件，已知时给出行号） |
| 2 | 用法错误：未知作用域或命令、缺少或未知选项、路径无法解析 |
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
python -m core.cli WW3 stats "root=<解包的 WW3>/.Mod"
python -m core.cli Firefight web    "root=<Firefight>" port=8765
```

两个语料上 `check` 都退出 1，这是有意的报告而非崩溃。`deps` 是作用域级的：一次只回答一个作用域。`web` 会一直
阻塞到 Ctrl-C，并打印它绑定到的地址。

## 9. 本部分的限制

* 不写文件、没有工程目录、没有 `.editor/` 状态、没有事件日志、没有撤销。
* `export` 保留源排版：兄弟节点顺序、空行、缩进、`//` 注释与文件自身的换行风格全部来自源文本
  （toml-mapping §4）。没有源文本的文件——`.toml` 工程文档——改用规范写入器（制表符缩进、CRLF、schema 顺序）；
  一次编辑会在内存中让它触及的元素的排版失效。
* 重新输出的文件是否被引擎接受，要在游戏内加载验证，本工具不做这件事。
* `Maps/`、`Surnames/` 与 `equipment_*` 不在范围内。
* 模组尚未通过 `mod.txt` 加载；模组就是含 `Data/` 的目录。

