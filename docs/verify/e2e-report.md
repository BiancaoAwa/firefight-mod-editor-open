# `dsh-firefight-mod-tools` 独立端到端验证报告（task-2）

> **路径说明（2026-10-11 补记）**：本报告写于工程目录搬迁之前，正文里的 `D:\deepseek-harness\WorkSpace\_scratch\<X>` 现全部位于 `D:\deepseek-harness\WorkSpace\firefight-mod-editor-open\<X>`（`ffplugin`、`m3-cli`、`verify` 等同名）；`_scratch\m2-refs` 工作树已删除，其内容等同 `firefight-mod-editor-open\m3-cli`（同一提交 94ad8a5）。正文为当时事实，未改写。**再补记（同日第二次整理）**：本报告所在目录已由 `firefight-mod-editor-open\verify\` 挪到 `firefight-mod-editor-open\docs\verify\`，`ffplugin\`、`m3-cli\` 位置不变；测试工程挪到 `firefight-mod-editor-open\dist\Mods\`、游戏数据镜像挪到 `firefight-mod-editor-open\dist\Firefight\`。

- 验证人：`verifier-e2e`（独立于插件作者；未修改 `lib/`、`test/`、未做任何远端写入）
- 被验对象：`D:\deepseek-harness\WorkSpace\_scratch\ffplugin`（0.1.1 工作树；**该目录不是 git 仓库**，见 §4）
- 被测 CLI：`D:\deepseek-harness\WorkSpace\_scratch\m3-cli\ff.py`（实现于 `cli\main.py`、`cli\commands.py`、`cli\scope.py`、`cli\documents.py`；必须 cwd=`D:\deepseek-harness\WorkSpace\_scratch\m3-cli` 才能 import `core`）
- 验证脚本：`D:\deepseek-harness\WorkSpace\_scratch\verify\e2e-verify.mjs`
- 原始证据：`D:\deepseek-harness\WorkSpace\_scratch\verify\export-out\_payloads\`（48 个真实运行的 stdout/stderr 落盘）
- 运行环境：python `C:\Users\BC_aw\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` (3.12.14)；node `C:\Users\BC_aw\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe` (v24.21.0，无 npm)；stock 游戏根 `D:\Program Files (x86)\Steam\steamapps\common\Firefight`

---

## 0. 结论（先行）

**整体判定：通过（有条件）。** 插件对 CLI 的 argv 装配、输出 schema、错误映射在可验证范围内全部与真实 CLI 行为一致；0.1.1 的输出契约修复经独立复算成立。

- `SUMMARY checks=274 passed=274 failed=0 notRun=1`（task-2 定稿，node 退出码 0）；§8 的 follow-up 与 §8.8 的 timeout 复算后为 `SUMMARY checks=318 passed=318 failed=0 notRun=2`。完整日志：`export-out\e2e-verify-run.txt`
- **2 项无法在本沙箱执行**：(1) 用**真实** `@deepseek-ai/dsh-tools` 校验器编译/校验契约（缺 peer `@deepseek-ai/cordis`，`test/real-harness.test.js` 因此自我 skip）；(2) `--live` 的 timeoutMs=1 真实子进程检查（沙箱拒绝一切 node spawn）。分别用「插件自带 stub 做可执行证明 + 真实校验器源码静态定位」（§4.3）与「真 1 ms 定时器 + 共用 helper 的源码定位」（§8.8）替代。
- **3 个真实缺陷/不一致**被独立复现（含最小复现）：其中 1 个（selector 含 `=`）仍是真正的功能缺陷（已在 README/`lib/specs.js` 文档化，§8.5）；`ff_list`/`ff_export` 的 `limit` 已被删除（§5.2/§8.3）；`ff_show` 子树 schema+渲染已补齐（§5.3/§8.4）；timeout 文案 `undefined ms` 已由 `resolveTimeoutMs` 修好（§5.4/§8.8）。另有 **1 条 task-2 结论被推翻**（`ff_deps` 的 `kind`：原来是假阳性，实际 CLI 有效），教训见 §5.5。
- 与 Lead 报出的数字无冲突：Lead 在**修复前**测得 `checks=198 passed=198 failed=0`；本轮把 0.1.1 的契约修复纳入检查后为 `274/274`（新增 41 项契约/源码检查 + 5 条新增真实样本）；§8 的 follow-up 复算后为 `318/318`（新增 timeout 修复 6 条后 `notRun=2`）。差异来自检查项增加，不是行为改变。

> **后续变更（0.1.1 follow-up，本报告 §8）**：作者随后又改动了行为——`ff_list`/`ff_export` 删掉 `limit` 参数（CLI 确实忽略它，§5.2 的对照是判别性的）、`ff_show` 补齐子树分支的 schema 与渲染（§5.3 已修）、`ff_deps` 的 `kind` 一度被误删后已按 CLI 实测**加回**（§5.5）。因此 §4.1 的“argv 逐字未变”只对 **42/43** 条 pre-fix 向量成立；两条**有意**变更的向量（`ff_list`/`ff_export` 的 `limit`）在 §8.2 逐条列出并重新冻结了黄金 hash。§8 的最终数字为 `checks=318 passed=318 failed=0 notRun=2`；§8.8 又把 task-4 §5.4 的 timeout 文案缺陷验证为**已修**（`resolveTimeoutMs` 统一了定时器与文案）。

---

## 1. 方法、证据链与可复现命令

**证据分层（关键：不拿插件渲染文本当证据）**

1. **argv 层**：脚本从 `lib/specs.js` + `lib/runner.js` 现算 argv，与手写的真实命令（`CASES[].manual`）逐字比对。手写命令是采集时**真正交给 python 执行**的 argv。
2. **payload 层**：`_payloads\<case>.out.json` 是 CLI 的**原始 stdout 字节**（未经过插件渲染），脚本用插件声明的 output schema 校验它。
3. **映射层**：把**真实捕获的 stdout/stderr/exit**（不是合成字符串）喂给 `lib/call.js` 的 `invokeCli`，检查 payload-first / usage / empty-output 判定。
4. **runner 层**：注入假 spawn（`EventEmitter` 伪造 child）覆盖 timeout/abort/child-error 分支——因为沙箱禁止 node 管道 spawn python（实测 `EPERM`，见 §6.1）。

**可复现命令（本报告每条结论都可据此重跑）**

```powershell
# 1) 重跑全部检查（本报告的数字来源；exit 0 = 全绿）
& 'C:\Users\BC_aw\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe' `
  'D:\deepseek-harness\WorkSpace\_scratch\verify\e2e-verify.mjs'

# 2) 只看插件会实际执行的 argv（采集用）
& <node> 'D:\deepseek-harness\WorkSpace\_scratch\verify\e2e-verify.mjs' --emit-argv

# 3) 手工复现单条 CLI 行为（必须 cwd= m3-cli）
cd 'D:\deepseek-harness\WorkSpace\_scratch\m3-cli'
& <python> 'D:\deepseek-harness\WorkSpace\_scratch\m3-cli\ff.py' Firefight list Data/Weapons 'root=D:\Program Files (x86)\Steam\steamapps\common\Firefight' --json
```

**采集口径说明（避免误读字节数）**：首轮采集用 pwsh `1> file` 重定向，默认 UTF-16LE+BOM（首字节 `FF FE`）。为让 JSON 可被直接比对，`_payloads\` 全部文件**原地**转为 UTF-8 无 BOM（**未重跑采集**），因此本报告所有 payload 字节数都是 UTF-8 后的值（同一 payload 在 UTF-16 下的字节数约为其 2 倍）。脚本 `readCaptured()` 同时兼容 `FF FE` / `EF BB BF` 前缀。

---

## 2. 成功路径：9 个工具的 argv 与真实 payload 逐条对照 (a)

以下每一行都是**真实运行**的结果（argv 为该 case 的插件 argv，`manual` 与之逐字相等；payload 关键字段取自 `_payloads\<case>.out.json` 原文）。全部 payload 都被 `outputContract(spec) = {oneOf:[spec.output, ERROR_SCHEMA]}` 判定为**恰好匹配 1 支**。

### 2.1 `ff_list`（LIST_OUTPUT，判别式 `scope` / `root` / `count` / `entities[]`）

| case | argv（`ff.py` 之后） | exit | 原始 payload 关键字段 |
|---|---|---|---|
| list_weapons | `Firefight list Data/Weapons root=<stock> --json` | 0 | `count=716`, `entities.len=716`, bytes=104190 |
| list_type_weapon | `Firefight list root=<stock> type=weapon --json` | 0 | `count=716`, `entities.len=716` |
| list_weapons_limit5 | `Firefight list Data/Weapons root=<stock> limit=5 --json` | 0 | `count=716`（**与 list_weapons 逐字节相同**，见 §5.2） |
| list_missing_dir | `Firefight list Data/NoSuchDir root=<stock> --json` | 0 | `count=0`, `entities=[]` |
| list_garbage | `Firefight list zzz-nothing-matches root=<stock> --json` | 0 | `count=0`, `entities=[]` |
| list_file_spaces | `Firefight list Data/Vehicles/British-A13 Cruiser Mk III.txt root=<stock> --json` | 0 | `count=1`（含空格的文件名可用） |
| list_selector_equals | `Firefight list Data/Good/eq=file.toml root=<probe> --json` | 0 | `count=4`（**缺陷**，见 §5.1） |
| list_good_dir | `Firefight list Data/Good root=<probe> --json` | 0 | `count=2`（对照组） |

`entity_files` 的目录前缀语义被证实：`Data/Good` → 2 个文件；不存在的目录 → 0 而非报错；单个文件路径 → 1。

### 2.2 `ff_show`（SHOW_OUTPUT，判别式 `path`）

| case | argv | exit | 原始 payload 关键字段 |
|---|---|---|---|
| show_raw | `Firefight show Data/Weapons/WEAPON_PISTOL_P38.txt root=<stock> --json` | 0 | `format=xml`, 键 `{path,format,text,warnings}`, bytes=733 |
| show_as_raw | `... as=raw --json` | 0 | 与 show_raw **逐字节相同**（733 字节，sha256 前缀 `13350A22F20AC73B`，`format=xml`） |
| show_toml | `... as=toml --json` | 0 | `format=xml`, 键 `{path,format,toml,warnings}`, bytes=548 |
| show_xml | `... as=xml --json` | 0 | `format=xml`, 键 `{path,format,xml,warnings}`, bytes=812 |
| show_list_file | `Firefight show Data/Surnames/surnames_probe.txt root=<probe> --json` | 0 | `format=list`, 键 `{path,format,text,warnings}`（非 entity 走 list 分支） |
| show_subtree | `Firefight show Data/Weapons/WEAPON_PISTOL_P38.txt/ammo root=<stock> --json` | 0 | `{path,key:"weapon/ammo",count:1,values.len:4}`（**schema 未声明这些键**，见 §5.3） |

**注意一处易误读**：CLI 的 `show` 即使不带 `as=`、或显式写 `as=raw`，返回的都是 `format: "xml"` 且键名为 `text`（**不是** `raw`）；只有 `as=toml`/`as=xml` 才改变键名与 `format`。插件把 `as=` 原样透传（`as=json` → exit 2，`call` 映射为 `usage`），未做本地枚举校验。插件的 `SHOW_OUTPUT` 同时声明 `text/toml/xml` 三个可选键，正是为了覆盖这三种返回形状——这一点与真实 payload 一致。

### 2.3 `ff_get`（GET_OUTPUT，判别式 `path`）

| case | argv | exit | 原始 payload |
|---|---|---|---|
| get_name | `Firefight get Data/Weapons/WEAPON_PISTOL_P38.txt root=<stock> field=name --json` | 0 | `{path,field:"name",count:1,values.len:1}`, bytes=201 |
| get_ammo_type | `... field=ammo.type --json` | 0 | `{path,field:"ammo/type",count:4,values.len:4}` ← **点号被 CLI 规范化为 `/`** |
| get_missing_field | `... field=no.such.field --json` | 2 | stdout 空；stderr：`...: no field no/such/field` |
| get_nothing | `... --json`（无 selector、无 field） | 2 | stdout 空；stderr：`nothing to read; pass a document path or field=<a.b.c>` |

插件声明 `field` 为可选、`path` 为必需，与 CLI 的行为一致（`path` 是 get 的判别式，因为 CLI 无论成功失败都不返回 field 之外的判别键；error 分支由 `ERROR_SCHEMA` 承担）。

### 2.4 `ff_find`（FIND_OUTPUT，判别式 `count`）

| case | argv | exit | 原始 payload |
|---|---|---|---|
| find_tag | `Firefight find root=<stock> tag=name --json` | 0 | `count=200`, `truncated=true`, `matches.len=200`, bytes=42560 |
| find_value | `... value=WEAPON_PISTOL_P38 --json` | 0 | `count=200`, `truncated=true`, bytes=42937 |
| find_path | `... path=weapon/ammo --json` | 0 | `count=200`, `truncated=true`, bytes=37122 |
| find_ignorecase | `... value=weapon_pistol_p38 ignore_case=1 --json` | 0 | `count=200`, `truncated=true`, bytes=42936 |
| find_limit | `... tag=name limit=5 --json` | 0 | `count=5`, `truncated=true`, `matches.len=5`（**limit 对 find 有效**） |
| find_noselector | `Firefight find root=<stock> --json` | 2 | stdout 空；stderr：`nothing to search for; pass tag=<name>, value=<text> or path=<a/b>` |
| probe_find | `Firefight find root=<probe> tag=probe --json` | 0 | `count=2`, `truncated=false`，`matches` 中**混入错误项** `{path,error}` |

两个要点：
- **`ff_find` 不需要 selector**：`find root=<stock> tag=name` 返回 200 条（前 5 行全部如此）。README 第 70 行「Nothing is searched without a selector」与真实 CLI 不符（§5.6）。「无 selector」在 CLI 里唯一会报错的情形是**连 tag/value/path 都没有**（`find_noselector` → exit 2）。
- 插件把 boolean `ignore_case` 序列化为 `ignore_case=1/0`（`formatOption`），实测被 CLI 正确解析（大小写不敏感命中数 42936 vs 42937 字节，行为可辨）。
- `probe_find` 证明 `matches[]` 是**混合数组**：既可能是 `{path,line,tag,document_path,value}`，也可能是 `{path,error}`。插件 schema 把 `matches` 声明为对象数组且 `additionalProperties` 未收紧，因此两种形状都通过——这是**宽松但可行**的设计，若上游把 error 项换成字符串则会失败（§6.2）。

### 2.5 `ff_stats`（STATS_OUTPUT，判别式 `scope`）

| case | argv | exit | 原始 payload |
|---|---|---|---|
| stats_full | `Firefight stats root=<stock> --json` | 0 | `files=1840 bytes=4003531 lists=48`，`errors=[]`，含 `by_category/by_format/by_root` |
| stats_missing | `Firefight stats root=<stock> zzz-nothing-matches --json` | 0 | `files=0 bytes=0 lists=0 errors=[]`（**不报错**，空 scope 合法） |
| probe_stats | `Firefight stats root=<probe> --json` | 0 | `files=3 bytes=71 lists=1`，**`errors.len=1`**（`broken.toml`） |

任务描述里要求的「带 errors 的 stats」样本**已拿到**：见 `probe_stats`（`errors.len=1`）与 `refs_probe_all`（`errors.len=1`）。两者都被 schema 接受。

### 2.6 `ff_refs`（REFS_OUTPUT，判别式 `scope`）

| case | argv | exit | 原始 payload |
|---|---|---|---|
| refs_file | `Firefight refs Data/Weapons/WEAPON_PISTOL_P38.txt root=<stock> --json` | 0 | `count=2`, `references.len=2`, `errors=[]` |
| refs_dir | `Firefight refs Data/Weapons root=<stock> --json` | 0 | `count=954`, `references.len=954`, `errors=[]`, bytes=183858 |
| refs_kind | `Firefight refs Data/Weapons root=<stock> kind=weapon --json` | 0 | `count=0`, `references=[]`（**kind= 能过滤到空集而不报错**） |
| probe_refs | `Firefight refs Data/Good/ok.toml root=<probe> --json` | 0 | `count=0`, `errors=[]` |
| refs_probe_all | `Firefight refs root=<probe> --json` | 0 | `count=0`, **`errors.len=1`**（损坏文件被记录而非抛出） |

### 2.7 `ff_deps`（DEPS_OUTPUT，判别式 `scope`）

| case | argv | exit | 原始 payload |
|---|---|---|---|
| deps_resolved | `Firefight deps root=<stock> value=WEAPON_PISTOL_P38 --json` | 0 | `count=1204`, `references.len=1204`, `resolved.len=1`, `unresolved=false` |
| deps_kind | `Firefight deps root=<stock> value=... kind=weapon --json` | 0 | **与 deps_resolved 逐字节相同** → CLI 的 deps 不支持 `kind=` 过滤（静默忽略，不报错） |
| deps_unresolved | `Firefight deps root=<stock> value=ZZZ_NO_SUCH_TOKEN --json` | 0 | `count=0`, `references=[]`, `resolved=[]`, `unresolved=true` |
| deps_novalue | `Firefight deps root=<stock> --json` | 2 | stdout 空；stderr：`name what to look for: value=<token>` |

`ff_deps` 的 payload 体积最大（209703 字节）且**不受 `limit` 约束**（CLI 侧确认），与 `LIMIT` 描述中「Some JSON payloads, for example ff_deps, are not limited by it」一致。插件把 `kind` 声明为可选，与 CLI 静默忽略 `kind=` 的事实不冲突（仅提示性）。

### 2.8 `ff_check`（CHECK_OUTPUT，判别式 `scope`）

| case | argv | exit | 原始 payload |
|---|---|---|---|
| check_file | `Firefight check Data/Good/ok.toml root=<probe> --json` | 0 | `files=1 loaded=1 skipped=0 warnings_total=0 dangling=[] ok=true` |
| check_full | `Firefight check root=<stock> --json` | **1** | `files=1840 loaded=1792 skipped=48 warnings_total=612 warning_files=612 dangling.len=2 warning_samples.len=20 ok=false`（stdout 仍是**合法 JSON**） |
| probe_check | `Firefight check root=<probe> --json` | **1** | `files=3 loaded=1 skipped=1 errors.len=1 ok=false` |

`check_full` 是「exit ≠ 0 但 stdout 是合法 JSON」的真实样本，插件 `payload-first` 规则据此成立（§3.2）。

### 2.9 `ff_export`（EXPORT_OUTPUT，判别式 `scope`）

| case | argv | exit | 原始 payload |
|---|---|---|---|
| export_file | `Firefight export Data/Weapons/WEAPON_PISTOL_P38.txt root=<stock> to=...\export-out\single --json` | 0 | `count=1 files.len=1 errors=[]`；实际写出 `...\export-out\single\Data\Weapons\WEAPON_PISTOL_P38.txt`（bytes=605） |
| probe_export | `Firefight export root=<probe> to=...\export-out\probe-export --json` | **1** | `count=2 files.len=2 errors.len=1`（`broken.toml` 写入失败被记录，其余仍成功） |
| export_probe_limit1 | `Firefight export root=<probe> to=...\probe-export-limit1 limit=1 --json` | **1** | `count=3 files.len=3 errors.len=1` → **`limit=1` 无效**（§5.2） |

**导出副作用已核对**：`export-out\single\...` 下确实存在被写出的文件；`limit` 不参与 export 的写入集合。

### 2.10 边界样本清单：拿到了什么 / 没拿到什么

**已拿到非空边界样本**：list 的不存在目录（0）与逐文件命中（1）；show 的 `as=raw`/`as=toml`/`as=xml` 三种形状 + 非 entity（`format=list`）+ 子树（`key/count/values`）；get 的 `field=name` 与点号路径 `ammo.type`（被规范化为 `ammo/type`）；find 的 tag/value/path 三种 + `limit` 截断（`truncated=true`）+ **`matches` 中混入 `{path,error}`**；stats 的 stock 全量（1840/4003531/48）与**带 errors 的 scope**（`probe_stats`：`errors.len=1`）；refs 的单文件（2）/目录（954）/`kind=` 空集；deps 的 resolved（1204）与 unresolved=true；check 的单文件 ok 与 stock 全量（612 warning_files、dangling.len=2、exit 1 + 合法 JSON）；export 的单文件成功与部分失败（`errors.len=1`）。

**没拿到（无法在本沙箱构造）**：
- **Mod scope 的成功 payload**：没有可用 mod 工程，只有 `mod_no_project`（exit 2）。
- **真实的 exit 130（Ctrl+C）**：只能合成。
- **`FfError`（exit 1）配非 JSON stdout 的真实样本**：CLI 的 exit 1 场景都伴随合法 JSON（check/export），非 JSON 失败只出现在 exit 2 的 usage 路径——因此 `code 1 + 非 JSON → cli-error` 这条分支只有合成证据。
- **真实 Ctrl+C / 编码 / 审批门 / 真实 host 校验器**：见 §6。

---

## 3. 失败 / 边界路径 (b)

### 3.1 exit 码 → 错误码映射（用**真实捕获字节**喂 `invokeCli` 得出）

CLI 真实退出码（`cli\main.py:112-120`）：`UsageError` → 2；`FfError` → 1；`KeyboardInterrupt` → 130。插件映射实测：

| 真实样本 | CLI exit | stdout | 插件 `code` | 插件 `detail`（截断自真实 stderr/stdout） |
|---|---|---|---|---|
| show_bad_as | 2 | 空 | `usage` | `python.exe : unknown as=json; use raw, toml or xml` |
| get_missing_field | 2 | 空 | `usage` | `...: no field no/such/field` |
| get_nothing | 2 | 空 | `usage` | `nothing to read; pass a document path or field=<a.b.c>` |
| find_noselector | 2 | 空 | `usage` | `nothing to search for; pass tag=<name>, value=<text> or path=<a/b>` |
| deps_novalue | 2 | 空 | `usage` | `name what to look for: value=<token>` |
| mod_no_project | 2 | 空 | `usage` | `cannot find a mod project here; run inside a project (mod.toml), or pass root=<project directory>` |
| unknown_command | 2 | 空 | `usage` | `unknown command 'nosuchcmd'; try 'help'` |
| help_json | 0 | **非 JSON**（help 文本，1516 字节） | `empty-output` | help 文本本身 |
| no_positionals_json | 0 | **非 JSON**（同 help 文本） | `empty-output` | 同上 |
| check_full / probe_check / probe_export / export_probe_limit1 | **1** | **合法 JSON** | 不是错误 —— 直接作为结果 | — |

结论：`UsageError→usage`、`FfError→cli-error`、`0+非JSON→empty-output`、`stdout 有 JSON 一律 payload-first` 四条都成立。**`detail` 里带 pwsh 包装层**（`At line:7 char:3` 等）：这是采集用 pwsh 调用 python 的产物，不是 CLI 自己写的；插件只是原样保留 stderr，属可接受行为，但报告读者需要知道这一层噪声来自采集器。

### 3.2 payload-first 规则（真实样本证实）

- `check_full`（exit 1，stdout = 3420 字节合法 JSON，`ok=false`）→ `invokeCli` 返回 **payload**，不是 error。
- `probe_check`（exit 1）、`probe_export`（exit 1）、`export_probe_limit1`（exit 1）同样返回 payload。
- 反例：`help_json`（exit 0，stdout 非 JSON）**绝不会**被当成结果（§3.1）。

这条规则与 `lib/call.js` 的实现一致，且我用**真实字节**证明，不是合成字符串。

### 3.3 timeout / abort / spawn 失败 / exit 130（合成分支，真实 CLI 无法在沙箱内触发）

| 分支 | 触发 | 插件结果（原文） |
|---|---|---|
| timeout | `invokeCli` 的 `exec` 返回 `timedOut:true` | `{"code":"timeout","message":"the editor CLI did not answer within 60000 ms","status":"error","guidance":"raise timeoutMs in the plugin config, or narrow the selector"}` |
| abort | `aborted:true` | `{"code":"cancelled","message":"the call was cancelled before the editor CLI answered","status":"error"}` |
| spawn 失败 | 真实管道 spawn python → `EPERM` | 抛 `FfCliError`：`cannot run ...python.exe: spawn EPERM`（**不是** error value） |
| exit 130 | 伪造 `code:130` + `stderr:'interrupted'` | `cli-error`（**不是** `cancelled`）：`{"code":"cli-error","message":"the editor CLI exited with code 130",...}` |
| runner timeout | 假 spawn + `timeoutMs=1` | `{"timedOut":true,"code":null}` |
| runner abort（启动前 / 运行中） | `AbortSignal` | `{"aborted":true,...}` |
| runner child `error` 事件 | 假 child `emit('error')` | `{failure:'EPERM'}`，**不 reject** |
| runner 未配置脚本 | `scriptPath`/`editorRoot` 均空 | `FfCliError: no editor checkout configured: neither scriptPath nor editorRoot is set` |

另有 `runner/argv[0]=script, argv[1]=scope, argv[2]=command`、`runner/env pins utf-8`（`PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`）、`runner/stdio has no stdin and pipes the rest`、`runner/injected spawn is really used` 四项结构断言通过。

**exit 130 的语义分歧（低危）**：CLI 把 `KeyboardInterrupt` 映射为 130，插件把 130 归到通用 `cli-error` 而不是 `cancelled`。这**不是** bug（插件没看到信号，只能看退出码），但意味着「用户 Ctrl+C 中断的真实运行」在插件侧表现为 `cli-error` 而非 `cancelled`；`cancelled` 只在 `AbortSignal` 路径出现。本次**没有**真实 Ctrl+C 样本，见 §6.2。

### 3.4 缺失实体 / 空 scope

- 不存在的目录：`list`→count 0；`stats`→files 0；`refs`→count 0（全部 exit 0，不报错）。
- 损坏的 toml（合成 `Data\Bad\broken.toml`，内容含 `[[[`）：`check` 记录到 `errors[]` 且 exit 1；`stats`/`refs` 记录到 `errors[]` 且 exit 0；`find` 把 `{path,error}` 混进 `matches[]`；`export` 记录 `errors[]` 且 exit 1——四种命令对同一坏文件的行为差异被逐一实测。

---

## 4. 修复前后对照 (c)

### 4.1 argv 契约：逐字未变（**独立断言**）

> 本节是 task-2 时点的结论（0.1.1 输出契约修复）。0.1.1 follow-up 之后，43 条里有 **2 条被有意改动**（`ff_list`/`ff_export` 去掉 `limit`），本节因此更新为 **42/43 稳定 + 2 条记录在案的 delta**；完整记账见 §8.2。

- 断言名：`argv/prefix-vectors-stable (42 of 43 pre-fix cases byte-identical to the task-2 golden)`、`argv/delta-list_weapons_limit5`、`argv/delta-export_probe_limit1`、`argv/historical-prefix-golden-sha256 (43 pre-fix cases, reconstructed)`、`argv/re-frozen-prefix-vector-sha256 (43 pre-fix cases)`
- 做法：把修复前（0.1.0 工作树）那轮已与真实 CLI 对照过的 43 条 `manual` 向量冻结为黄金向量。现在脚本 (1) 对 42 条未变向量做整表逐字比较；(2) 对 2 条 delta 断言「新向量 == 旧向量删掉恰好一个 token」；(3) 用「42 条冻结向量 + 2 条记录的 delta」**重建** task-2 的 43 条向量，其 sha256 必须仍为 `70d089d8a7b8d3ab`；(4) 用新 hash `d83bc31f25d7aef8` 重新冻结当前 43 条向量。
- 结果：重建 hash = `70d089d8a7b8d3ab` == task-2 冻结值 ✅（证明除这两条外没有任何向量移动）；当前向量 `d83bc31f25d7aef8` ✅
- 覆盖：43 条向量含 8 个只读工具 + export 的成功路径、`limit=`、`type=`、`as=`、`field=`、`tag=`/`value=`/`path=`/`ignore_case=`、`kind=`、布尔 `false→0`、空值丢弃、`Mod` 不带 `root`、`Firefight` 注入 `config.firefightRoot`、显式 `root=` 覆盖 scope。
- 局限：`ffplugin` 不是 git 仓库（`git log` → `fatal: not a git repository`），因此「逐字不变」的对照基准是**我上一轮的冻结向量**，不是 git diff。这足以排除 argv 变化（脚本现算 = 冻结字节），但不排除「修复前后 `manual` 一起被改错」——该风险由 §2 的真实运行结果反向消除。

### 4.2 输出契约：修复前必然拒绝自己的错误值，修复后不再

断言（脚本 §5b，用插件自带 stub 的「恰好一支」语义）：

| 断言 | 9 个工具 | 结果 |
|---|---|---|
| `stub/prefix-contract-rejects-the-plugin's-own-error-value <tool>` | 全部 | `must match exactly one oneOf branch (matched 2)` ✅ |
| `stub/postfix-contract-accepts-the-error-value <tool>` | 全部 | accepted（violations = `[]`） ✅ |
| `stub/postfix-contract-accepts-real-payloads <tool>` | 全部 | 39 个真实捕获 payload 全部 accepted ✅ |
| `stub/postfix-contract-rejects-an-empty-object <tool>` | 全部 | 拒绝 ✅ |

机制：修复前的 payload 分支是「开放式对象、无 required」，`errorValue()` 的 `{code,message,status,guidance,detail}` 同时匹配 payload 分支与封闭的 `ERROR_SCHEMA` → **matched 2** → 每个工具的错误路径都会被 host 判为非法输出。修复后每个 payload 分支恰好声明一个判别式属性（`ff_list`/`stats`/`refs`/`deps`/`check`/`export`→`scope`，`ff_show`/`ff_get`→`path`，`ff_find`→`count`），而 error value **不含**任何一个判别键 → 恰好 matched 1。脚本另有 `schema/discriminator <tool>` 断言判别式恰好 1 个且不是 error 键（`status|code|message|guidance|detail`）。

### 4.3 真实 host 校验器：本沙箱无法导入（已用双证据替代）

- 实测：`ERR_MODULE_NOT_FOUND: Cannot find package '@deepseek-ai/cordis' imported from D:\deepseek-harness\WorkSpace\_scratch\ffplugin\node_modules\@deepseek-ai\dsh-tools\lib\index.js`
- 该包**确实安装**在工作区（`@deepseek-ai/dsh-tools@0.2.1-alpha.1`，pnpm 虚拟 store 仅含 `dsh-brand / dsh-tools / dsh-util-values / schemastery`，缺 `@deepseek-ai/cordis` 与 `@deepseek-ai/dsh-llm`）。因此 `test/real-harness.test.js` 在本工作区**永远自我 skip** —— 这是「插件自带测试并未真正运行过真实校验器」这一事实，属**未覆盖项**，不是插件缺陷。
- 替代证据 A（可执行，§4.2）：插件自带 stub 实现同一「恰好一支」语义，用它证明修复前/后行为差异。
- 替代证据 B（静态，断言名 `host-source/*`，5 项全绿）——直接读真实包源码定位同一规则：
  - `node_modules\@deepseek-ai\dsh-tools\lib\types\json-schema.js` 与 `lib\index.js` 均含 `frame.matches === 1 ? [] :` 及 `must match exactly one oneOf branch`；`lib\index.js` 含 `validateJsonSchemaValue(tool.output.schema`（真实流水线确实用该校验器校验工具输出）。
  - `lib\index.js` 的 `ONE_OF_SIBLING_KEYWORDS` 含 `"required"`，并在同一文件报 `is not supported beside oneOf` → 插件把判别式写成**属性级** `required:true` 而不是分支级 `required` 是**必需**的写法。
  - `lib\types\schema.js` 含 `task.property.required === true` / `task.required.push(task.key)` / `task.compiled.required = task.required` → 属性级 `required` 会被提升为父对象的 `required` 数组，`host/defineTool` 之后 `compiled.oneOf[0].required` 应等于 `discriminatorOf(spec)`（该断言在能导入 host 的机器上会执行）。
  - 真实包 README 含 `exact-one \`oneOf\`` 字样。
- **未做的（待有依赖的环境补）**：真实 `defineTool` 编译 9 个 contract 后比对 `compiled.oneOf[0].required`；真实 `validateJsonSchemaValue` 对 39 个真实 payload 与 `errorValue` 的判定；用真实 factory 跑 `createTools` 断言注册 9 个工具。命令：`node --test "test/*.test.js"`（cwd=`D:\deepseek-harness\WorkSpace\_scratch\ffplugin`，`package.json` 的 `scripts.test`），以及本文 §1 的脚本（在装好 peer 的机器上会自动走 host 分支）。

---

## 5. 缺陷与不一致（均含最小复现）

### 5.1 【功能缺陷 · 中】selector 里含 `=` 会被吞成 key=value 选项

- 机制：`cli\main.py` 的 `parse_argv` 对 `'=' in token and not token.startswith('-')` 一律按 option 解析，因此 selector 中含 `=` 的文件名/目录名无法表达；插件只负责拼接 argv，无转义能力。
- 最小复现（probe scope 里有 `Data\Good\eq=file.toml`）：

```powershell
cd 'D:\deepseek-harness\WorkSpace\_scratch\m3-cli'
& <python> .\ff.py Firefight list 'Data/Good/eq=file.toml' 'root=D:\deepseek-harness\WorkSpace\_scratch\verify\export-out\_probe-scope' --json
# 实际: {"count":4,...}  （整个 scope 被列出，selector 被当成 option "eq=file.toml" 丢弃；stderr 为空）
& <python> .\ff.py Firefight list 'Data/Good' 'root=<probe>' --json
# 对照: {"count":2,...}
```
- 证据：`_payloads\list_selector_equals.out.json`（673 字节，`count=4`，`entities` 含 `Data/Bad/broken.toml`、`Data/Good/eq=file.toml`、`Data/Good/ok.toml`、`Data/Surnames/surnames_probe.txt`）vs `_payloads\list_good_dir.out.json`（`count=2`）。
- 影响面：**静默给出错误结果**（不是报错），且 stock 数据里 1840 个 txt/toml 文件名**没有一个含 `=`**（全量扫描确认），所以实际触发概率低；但任何用户自己的 mod 用了 `=` 就会命中。同理 `-` 开头的 token 会触发 `unknown flag`（stock 数据里同样 0 个）。
- **更正（task-4）：`ff_show` 不是绕过办法。** 曾建议「用 `ff_show` 读这类文件」，实测不成立——`ff_show` 同样把 `=` 当 option，于是变成「没有 selector」，报错而不是读到文件：

```powershell
& <python> .\ff.py Firefight show 'Data/Good/eq=file.toml' 'root=<probe>' --json
# 实际: exit 2, stdout 空, stderr: expected one file, got 4; name the file explicitly
& <python> .\ff.py Firefight show 'root=<probe>' --json
# 对照（真正没有 selector）: 完全相同的报错文本
```
  证据：`_payloads\show_equals_selector.{out.json,err.txt}`（stdout 0 字节、exit 2）vs `_payloads\show_probe_noselector.{out.json,err.txt}`（同样 exit 2、同样文本）。脚本断言名：`finding/ff_show cannot read a "="-named file either (advice must be "rename")`。**因此唯一的规避手段是重命名**（Lead 已把 README/`lib/specs.js` 里那句 `ff_show` 建议删掉，并由脚本断言守住，见 §8.5）。

### 5.2 【缺陷 · 低】`ff_list` / `ff_export` 的 `limit` 无效

- 复现：`ff.py Firefight list Data/Weapons root=<stock> limit=5 --json` 的 stdout 与不带 limit 的 **逐字节相同**（104190 字节，`count=716`）；`ff.py Firefight export root=<probe> to=...\probe-export-limit1 limit=1 --json` → `count=3 files.len=3`。
- 证据：`_payloads\list_weapons_limit5.out.json` vs `list_weapons.out.json`；`_payloads\export_probe_limit1.out.json`。脚本断言名：`finding/ff_list limit= has no effect`、`finding/ff_export limit= has no effect on what is written`。
- 影响：`limit` 描述已改为「Row cap for the CLI text output (CLI default 200)…」，对 JSON 路径不承诺；因此这是**能力空洞而非谎报**，但 `ff_list` 的 `limit` 参数对 JSON 调用者完全无用（CLI 的 `cmd_list` 不读 limit），建议从 `ff_list` 参数里移除或注明 JSON 无效。`ff_find` 的 `limit` **有效**（find_limit → count=5），不应一起删。
- **这个方法本身是判别性的**（与 §5.5 的假阳性对比）：`limit=5` 生效就会返回 5 行，实测返回 716 行；`limit=1` 生效就会只写 1 个文件，实测写 3 个。对照与默认结果**不同**，所以「忽略」的结论成立。
- **已修（0.1.1 follow-up）**：`ff_list`/`ff_export` 的参数里已删除 `limit`（`ff_find` 保留）。见 §8。

### 5.3 【缺陷 · 中低】`ff_show` 的子树 payload（`key`/`count`/`values`）未进 schema，且渲染成空白

- 复现：`ff.py Firefight show Data/Weapons/WEAPON_PISTOL_P38.txt/ammo root=<stock> --json` → `{"path":...,"key":"weapon/ammo","count":1,"values":[...4 项...]}`。
- 插件侧：`SHOW_OUTPUT.properties` 只声明 `path/format/text/toml/xml/warnings`；`lib/render.js` 的 `renderShow` 是 `` `${value.path} (${value.format})` `` + `(value.toml ?? value.xml ?? value.text ?? '').trimEnd()`，对子树 payload 输出 **`Data/Weapons/WEAPON_PISTOL_P38.txt (undefined)`** 且正文为空（脚本断言名：`finding/ff_show subtree payload declares no key/count/values and renders blind`）。
- 为何仍通过 schema：`additionalProperties` 未收紧 + 判别式 `path` 存在 → 恰好 matched 1，所以 host 不会拦。**属于「能过校验但人看不到数据」**。
- 建议：要么在 `SHOW_OUTPUT` 增加 `key`/`count`/`values` 分支并把 `renderShow` 补上对应渲染，要么在插件层显式拒绝 `selector` 里带 `/` 的 show 调用。
- **已修（0.1.1 follow-up）**：作者采纳了第一种方案——`SHOW_OUTPUT` 增加 `key`/`count`/`values`，`renderShow` 增加子树分支（抬头 `path key · N element(s) · M value(s)`）。本轮独立复算通过，见 §8.4。

### 5.4 【已修】timeout 消息曾打印未解析的 `config.timeoutMs`

- 原状：`call.js` 的 timeout 文案是 `` `the editor CLI did not answer within ${config.timeoutMs} ms` ``；调用方传入未经 `resolveConfig` 归一化的配置（`timeoutMs` 缺失）时，用户会看到 `within undefined ms`（当时的脚本断言名：`finding/timeout message prints the raw config.timeoutMs`）。
- 通过 `lib/config.js` 正常路径不会出现（默认 60000）。
- **已修（task-7）**：`lib/runner.js` 新增并导出 `resolveTimeoutMs(config)`（`DEFAULT_TIMEOUT_MS = 60000`，非正数/非数字一律回落），`createRunner` 的定时器（`lib/runner.js:71`）与 `lib/call.js:50` 的文案**共用同一个 helper**，因此“打印的值”与“实际生效的超时”不可能再分叉；`test/call.test.js` 增加显式/缺失两种配置均报 60000 的断言。我把原 finding 探针改写为修复断言并加了对照，见 §8.8。

### 5.5 【已推翻 · 教训】`ff_deps` 的 `kind=` 曾被判为“被 CLI 忽略”，实为**假阳性**

- **原结论（错误）**：task-2 时我对比 `deps_resolved`（不带 kind）与 `deps_kind`（`kind=weapon`），stdout **逐字节相同**（均 209703 字节，SHA256 均为 `C43B24A2E2DDA3F3E1A447A3D2577FDBD2BFD335830FB6956F5A8F4F97B58746`），据此判定 CLI 忽略 `kind`。
- **更正（task-4，Lead + verifier-repo 指出）**：`kind` **确实有效**。CLI 源码真的读它：`cli\commands.py:420 kind = ctx.options.get("kind")`、`:438 if reference.value == value and (kind is None or reference.kind == kind)`。
- **判别性实测**（stock 数据，独立采集）：`deps value=WEAPON_PISTOL_P38 kind=sound` → `count=0`；`kind=__none__` → `count=0`；`kind=weapon` → `count=1204`；不带 kind → `count=1204`。证据：`_payloads\deps_kind_sound.out.json`（158 字节）、`_payloads\deps_kind_none.out.json`（158 字节）。脚本断言名：`finding/ff_deps kind= IS honoured (discriminating values change the count)`。
- **教训（已写入脚本注释）**：**控制组必须是判别性的**。该 token 的 1204 条传入引用**全部**是 weapon 类，所以“带 `kind=weapon`”与“不带 kind”本来就该产生同一结果——用它做对照等于什么都没验。要判定一个过滤参数是否生效，必须选一个**能把结果变成不同值（最好是 0/空）**的取值，而不是与默认结果相同的取值。
- 后果：这条假阳性直接导致 follow-up 中 `ff_deps` 的 `kind` 被误删；Lead 已将其加回（`lib/specs.js:302 kind: KIND`、`:309 build … kind: args.kind`），本轮 argv 向量也已恢复为 task-2 的形态。

### 5.6 【文档不一致 · 低】README 第 70 行「Nothing is searched without a selector」与 CLI 不符

- 实测 `ff.py Firefight find root=<stock> tag=name --json` → `count=200, truncated=true`（无 selector 完全可用）。真正的约束是「tag/value/path 至少给一个」。
- **已修（0.1.1 follow-up）**：README 第 70 行已改为 “At least one of `tag`, `value` or `path` is required, otherwise the CLI stops with a usage error; without a selector the whole scope is searched.”（本轮逐行核对通过）。
- 附带：README 第 70 行「`limit` caps both the payload and the rendered rows」对 `ff_find` 成立（CLI 侧 + `ROW_LIMIT=100` 渲染侧），但对 `ff_list`/`ff_export` 不成立（§5.2，作者已在参数表里删除这两处 `limit`，并在 §77-80 段落写明「`limit` is only honoured by `ff_find`」）。

---

## 6. 未覆盖 / 不确定项 (d)

### 6.1 沙箱限制：node → python 的管道 spawn 被拒（EPERM）

- 实测：`execFileSync(python, [...])` → `SPAWN_FAIL EPERM spawnSync ...python.exe EPERM`；`node --test 'test/output-schema.test.js'`（cwd=`D:\deepseek-harness\WorkSpace\_scratch\ffplugin`）→ `test at test\output-schema.test.js:1:1 ... Error: spawn EPERM at ChildProcess.spawn (node:internal/child_process:458:11) ... code: 'EPERM', syscall: 'spawn'`，EXIT=1。
- 因此：**插件自带的 9 个 `test\*.test.js`（另有两个辅助文件 `test\harness-stub.js`、`test\support.js`）我一次都没能运行**（`node --test` 在 node 24 下每个测试文件都开子进程）。这是 task-2「独立验证」最重要的缺口。
- 待提权执行的完整命令（不换写法绕沙箱）：

```powershell
# A) 插件自带测试套件（package.json 的 scripts.test）
cd 'D:\deepseek-harness\WorkSpace\_scratch\ffplugin'
& 'C:\Users\BC_aw\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe' --test "test/*.test.js"

# B) 本报告的验证脚本（无需 spawn；已在当前沙箱跑通 318/318、notRun=2，§8）
& <node> 'D:\deepseek-harness\WorkSpace\_scratch\verify\e2e-verify.mjs'

# C) 唯一需要真实子进程的检查（timeoutMs=1 打真实 python；沙箱内 exit 2，§8.8）
cd 'D:\deepseek-harness\WorkSpace\_scratch\verify'
& <node> .\e2e-verify.mjs --live
```
- 我**没有**用 `--test-isolation=none` 之类开关规避沙箱限制（遵 task-2 指示），上述 EPERM 是环境边界。
- 本轮补充确认：被拒的不只是 python——`export-out\spawn-probe.cjs` 里 node 与 python **都**在 `ChildProcess.spawn` 处同步抛 `Error: spawn EPERM … errno: -4048, code: 'EPERM', syscall: 'spawn'`（见 §8.8）。

### 6.2 其它未覆盖 / 不确定

1. **真实 Ctrl+C（exit 130）样本缺失**：§3.3 的 130 分支是合成输入。真实中断时的 stdout/stderr 形状未知。
2. **`matches[]` 混合形状的边界**：`probe_find` 证明了 `{path,error}` 与 `{path,line,tag,document_path,value}` 两种形状，但若上游改成字符串或其它键，插件 schema 会拒（未测，因为无法构造）。
3. **Mod scope 的成功路径未覆盖**：`mod_no_project` 只证明了「无 mod.toml → exit 2 → usage」。没有可用的真实 Mod 工程，因此 `Mod` scope 的成功 payload、以及 `root=` 注入 `config.firefightRoot` 在真实运行中的效果未测（argv 层已断言）。
4. **编码相关的真实运行未复测**：`PYTHONIOENCODING/PYTHONUTF8` 只在 argv/env 结构层断言（`runner/env pins utf-8`）；pwsh 采集层的 UTF-16 转码已修正，但「插件经 node 管道读取非 ASCII 内容」的端到端路径因 EPERM 未跑。
5. **`maxOutputChars`/`ROW_LIMIT` 渲染截断**：仅静态读 `lib/render.js` 确认逻辑（超限追加 `… N more`），未对真实超长 payload（如 deps 209703 字节）实测渲染长度（`renderValue` 未被端到端调用过；`renderShow` 被调用过一次，见 §5.3）。
6. **`tools/pre-execute` 导出审批门**：`lib/approval.js` 的 `registerExportGate` 需要 host 的 `tools/pre-execute` 事件，本沙箱无 host，未验证（`test/approval.test.js` 也因 EPERM 未跑）。
7. **`config.cwd` 语义**：`cordis.patch.yml` 新增的 `cwd` 只做了配置读取层面的核对（`createRunner` 的 `cwd: config.cwd || process.cwd()`），未在真实 host 中验证。

---

## 7. 附录

### 7.1 脚本检查项分布（`e2e-verify.mjs`，318 项 / 0 失败 / 2 未运行；见 §8）

| 段 | 覆盖 | 项数（task-2 定稿 → follow-up 后） |
|---|---|---|
| 1 | argv vs 手写命令、`--json` 末位、布尔/空值/scope-root 规则、参数与 spec 校验、黄金向量 sha256、判别式、新增 delta/re-frozen hash 与参数增删断言 | 104 → 138 |
| 2 | 真实 payload 过 `outputContract`（含 4 个 exit≠0 的 payload-first 样本 + 3 个 replay 样本） | 42 → 48 |
| 3 | 真实字节跑 `invokeCli`（payload-first / usage / empty-output）+ 合成 cancelled/timeout/exit130/spawn failure | 50 → 60 |
| 4 | 假 spawn 跑 `createRunner`（timeoutMs=1、abort、child error、无脚本、env/stdio/argv） | 10 → 11 |
| 5 | 契约修复：5b stub 可执行证明 + 5c 真实源码静态定位；`host/real-validator-importable` = NOT RUN | 41（+1 未运行） |
| 6 | 复现的缺陷与 follow-up 修复断言（PASS = 确认行为）；含 §8.8 的 timeout 修复 6 条 | 5 → 20（+1 未运行） |

（合计 138+48+60+11+41+20 = 318，与 `SUMMARY` 一致；另有 2 条 `NOT RUN`：真实 host 不可导入、真实 child 进程被沙箱拒。）

### 7.2 证据文件索引

- 运行日志：`export-out\e2e-verify-run.txt`
- 真实 payload：`export-out\_payloads\<case>.out.json` / `<case>.err.txt`（57 组，含 `replay_*`、`deps_kind_*`、`show_equals_selector`、`show_probe_noselector`）
- 合成探针 scope：`export-out\_probe-scope\`（`Data\Bad\broken.toml`、`Data\Good\ok.toml`、`Data\Good\eq=file.toml`、`Data\Surnames\surnames_probe.txt`）
- 导出副作用：`export-out\single\Data\Weapons\WEAPON_PISTOL_P38.txt`、`export-out\probe-export\`、`export-out\probe-export-limit1\`
- 验证脚本：`e2e-verify.mjs`（`--emit-argv` 可打印插件现算 argv）

---

## 8. Post-fix re-verification（0.1.1 follow-up）

本节是 task-4 的交付：对作者在 0.1.1 之后追加的行为改动做独立复算——**argv 向量有意变更并重新冻结**、`limit` 删除的 CLI 侧判别性证据、`ff_deps` 的 `kind` **误删后加回**、子树 payload 的 schema 与渲染修复。作者要求“改期望、重新冻结 hash 并说明哪些向量变了”，本节逐条给出。

> **本轮包含一次自我更正**：我最初把 `ff_deps` 的 `kind` 也判成“CLI 忽略”，依据是“带 `kind=weapon` 与不带 kind 的 stdout 逐字节相同”。该对照**不具判别性**（该 token 的 1204 条引用全是 weapon），Lead 与 verifier-repo 用 `kind=sound`/`kind=__none__` 证明 CLI 确实过滤，随后作者把 `kind` 加回。详见 §5.5 与 §8.3。

### 8.0 本轮被验树的实际改动（只读核对；我未修改 `lib/`、`test/`、`README.md`）

| 文件 | 改动 | 证据 |
|---|---|---|
| `lib/specs.js` | `ff_list.parameters` 去掉 `limit`；`ff_export.parameters` 去掉 `limit`；**`ff_deps` 一度去掉 `kind`，现已加回**（`ff_refs` 一直保留 `kind`） | 脚本断言 `parameters/ff_list no longer declares limit`、`… ff_export …`、`parameters/ff_find still declares limit`、`parameters/ff_refs still declares kind`、`parameters/ff_deps still declares kind`；源码 `lib/specs.js:302 kind: KIND`、`:309 … kind: args.kind` |
| `lib/specs.js` | `LIMIT` 描述改为 “Row cap for the CLI text output (CLI default 200). Only ff_find honours it; the other commands ignore it.” | 源码 line 38 |
| `lib/specs.js` | `ff_list.selector` 描述新增 `=` 缺口的文档化（**其中“改用 `ff_show`”的建议是错的**，见 §8.5） | 源码；与 README 同步 |
| `lib/specs.js` | `SHOW_OUTPUT` 新增 `key`(string)/`count`(number, “Number of elements the subtree selector matched”)/`values`(array of `{path,line,value}`)；`DEPS_OUTPUT.references` 改型为 `{source,kind,document_path}` | `fix/ff_show subtree branch is declared` 断言 declared=`[path,format,text,toml,xml,key,count,values,warnings]` |
| `lib/render.js:99-110` | `renderShow` 新增 `Array.isArray(value.values)` 子树分支，抬头 `path key · N element(s) · M value(s)` | `fix/ff_show subtree renders elements and values` |
| `lib/runner.js:56-61`、`lib/call.js:9,50`（task-7） | 新增并导出 `resolveTimeoutMs(config)`（`DEFAULT_TIMEOUT_MS = 60000`）；`createRunner` 的定时器与 timeout 文案共用它，彻底消除 `undefined ms` | 断言 `fix/runner timer and call.js message share resolveTimeoutMs`、`fix/timeout message reports the resolved default …` 等 6 条，见 §8.8 |
| `README.md:67,75` | `ff_list`/`ff_export` 行去掉 `limit`（`ff_deps` 行恢复 `kind`） | 逐行读取 |
| `README.md:70` | `ff_find` 改为 “At least one of `tag`, `value` or `path` is required, otherwise the CLI stops with a usage error; without a selector the whole scope is searched.” | 修正了 §5.6 记录的不一致 |
| `README.md:77-80` | 新增段落文档化 `=` 缺口，规避办法只保留“rename such a folder”（**原先错误的“read it with `ff_show`”建议已被删除**） | 逐行读取 + 脚本断言 `doc/the "=" gap is documented as rename-only…` + §8.5 的实测 |
| `README.md:97-99` | Bounded output 改为 “`ff_show` prints a whole document in full but caps a subtree at 100 values” | 逐行读取 |
| `test/output-schema.test.js`、`test/real-harness.test.js`、`package.json` 0.1.1 | 新增/更新测试 | **未在本沙箱执行**（EPERM，§8.7）；其断言语义已由 `e2e-verify.mjs` 段 5b/8.4 独立复算 |

### 8.1 复算命令

```powershell
# 1) 全部检查（本节数字与 hash 的来源；exit 0 = 全绿）
& 'C:\Users\BC_aw\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe' `
  'D:\deepseek-harness\WorkSpace\_scratch\verify\e2e-verify.mjs' *> export-out\e2e-verify-run.txt

# 2) 用“新 argv”重放真实 CLI，与 task-2 的旧采集逐字节对比
Set-Location 'D:\deepseek-harness\WorkSpace\_scratch\m3-cli'
& <python> ff.py Firefight list Data/Weapons "root=D:\Program Files (x86)\Steam\steamapps\common\Firefight" --json
& <python> ff.py Firefight deps "root=D:\Program Files (x86)\Steam\steamapps\common\Firefight" value=WEAPON_PISTOL_P38 --json
& <python> ff.py Firefight export "root=D:\deepseek-harness\WorkSpace\_scratch\verify\export-out\_probe-scope" `
    "to=D:\deepseek-harness\WorkSpace\_scratch\verify\export-out\probe-export-limit1" --json

# 3) 判别性对照：只有把结果变成 0 的取值才算证据（§8.3）
& <python> ff.py Firefight deps "<root=STOCK>" value=WEAPON_PISTOL_P38 kind=sound --json     # count=0
& <python> ff.py Firefight deps "<root=STOCK>" value=WEAPON_PISTOL_P38 kind=__none__ --json  # count=0
& <python> ff.py Firefight deps "<root=STOCK>" value=WEAPON_PISTOL_P38 kind=weapon --json    # count=1204
& <python> ff.py Firefight show 'Data/Good/eq=file.toml' "<root=PROBE>" --json               # exit 2, 不是读到文件

# 4) 字节对比（全部输出 True）
Get-FileHash ...\_payloads\{list_weapons,list_weapons_limit5,replay_list_dataweapons}.out.json
Get-FileHash ...\_payloads\{deps_resolved,deps_kind,deps_nokind,replay_deps_value}.out.json
```

pwsh 重定向默认写 UTF-16LE+BOM，脚本的 `readCaptured()` 兼容该前缀；本轮 replay/probe 文件已与 task-2 一致地归一化为 UTF-8 无 BOM（`stderr` 文件里 PowerShell 会带上自身的错误装饰文本，断言只匹配消息子串）。

### 8.2 argv 向量：两条**有意**变更与重新冻结的 hash

| case | task-2 冻结的 argv（pre-fix） | 现在的 argv | 差异 |
|---|---|---|---|
| `list_weapons_limit5` | `ff.py Firefight list Data/Weapons root=<STOCK> limit=5 --json` | `ff.py Firefight list Data/Weapons root=<STOCK> --json` | 去掉 `limit=5`（CLI 忽略，§5.2 判别性对照） |
| `export_probe_limit1` | `ff.py Firefight export root=<PROBE> to=…\probe-export-limit1 limit=1 --json` | `ff.py Firefight export root=<PROBE> to=…\probe-export-limit1 --json` | 去掉 `limit=1`（CLI 忽略，同上） |
| ~~`deps_kind`~~ | `… deps root=<STOCK> value=WEAPON_PISTOL_P38 kind=weapon --json` | **与 task-2 相同**（一度被去掉 `kind=weapon`，已恢复） | **无差异**（撤销的误改，§5.5） |

**为什么可以变**：§5.2（以及 §8.3 的新重放）用**真实 CLI** 证明这两个 `limit` 被 CLI 完全忽略——带与不带它，stdout 逐字节相同，且对照取值是判别性的（`limit=5` 该给 5 行却给 716 行；`limit=1` 该写 1 个文件却写 3 个）。删除一个“看起来有效、实际被忽略”的参数是接口修正，而不是行为改变。**`ff_deps` 的 `kind` 不在此列**：它的恢复（§5.5）说明仅凭“带/不带结果相同”不足以判定参数无效。

**hash 记账（脚本逐项断言，全部 PASS）**：

| 检查 | 值 |
|---|---|
| `argv/prefix-vectors-stable`（42 / 43 条 pre-fix 向量与 task-2 黄金向量逐字一致） | 子集 sha16 `9204021db2b01351` |
| `argv/historical-prefix-golden-sha256`（43 条：42 条冻结向量 + 从上表两条 `prefixManual` 重建） | `70d089d8a7b8d3ab` == task-2 冻结值 |
| `argv/re-frozen-prefix-vector-sha256`（43 条：当前插件现算向量，**重新冻结**） | `d83bc31f25d7aef8` |
| `argv/delta-list_weapons_limit5` / `argv/delta-export_probe_limit1` | 各自“新向量 == 旧向量删掉恰好一个 token”，长度差 1 |

**黄金向量 hash 链**（每一环都由脚本断言，可回溯）：

| 时点 | 43 条 pre-fix 向量 sha16 | 触发变化 |
|---|---|---|
| task-2（0.1.0 → 0.1.1 输出契约修复） | `70d089d8a7b8d3ab` | 无（契约修复不动 argv） |
| follow-up 中途（`limit` + `kind` 都被删） | `bd6f43d8256eb69f` | `ff_list`/`ff_export` 去 `limit`、`ff_deps` 误去 `kind` |
| **当前（`kind` 已恢复）** | `d83bc31f25d7aef8` | 仅 `ff_list`/`ff_export` 去 `limit` |

**为什么这组断言比单纯改 hash 强**：脚本不是把黄金值改成插件当前值就算了，而是先用**冻结的 prefix 向量 + 两条记录的 delta** *重建* 出 task-2 的 43 条向量，确认其 sha256 仍是 `70d089d8a7b8d3ab`——这同时证明 (a) 除这两条外没有任何向量移动，(b) 有意变更的集合恰好是这两条。然后用 `d83bc31f25d7aef8` 重新冻结当前向量，后续任何变化都会失败。

### 8.3 真实 CLI 重放：证明“删除是对的”

用 follow-up 之后的 argv（不含 `limit=`/`kind=`）重新执行真实 CLI，并与 task-2 的旧采集逐字节比较：

| 重放 | argv | exit | stdout 字节 | sha256(前 16) | 与旧采集对比 |
|---|---|---|---|---|---|
| `replay_list_dataweapons` | `list Data/Weapons root=<STOCK>` | 0 | 104190 | `4e26b5ec12b5f92c` | 与 `list_weapons`（无 limit）**和** `list_weapons_limit5`（`limit=5`）**都逐字节相同** |
| `replay_deps_value` | `deps root=<STOCK> value=WEAPON_PISTOL_P38` | 0 | 209703 | `c43b24a2e2dda3f3` | 与 `deps_resolved`（无 kind）、`deps_kind`（`kind=weapon`）、`deps_nokind` **都逐字节相同**——但**这不是**“`kind` 无效”的证据（见 §8.3 末的更正） |
| `replay_export_probe` | `export root=<PROBE> to=…\probe-export-limit1` | 1 | 1094 | `22436375383db481` | 与 `export_probe_limit1`（`limit=1`、**同一个 `to`**）逐字节相同；`count=3 files=3 errors=1 stderr=""` |

对应检查项：`fix/ff_list replay without limit= reproduces the same payload`、`fix/ff_deps without kind= still reproduces the no-kind payload`、`fix/ff_export replay without limit= reproduces the same payload`——全部 PASS。

同时保留了“limit 确实被忽略”的原始证据：`finding/ff_list limit= has no effect (CLI ignores it)`（104190 字节相同、count=716，而 `limit=5` 应给 5 行）、`finding/ff_export limit= has no effect on what is written`（`limit=1` 仍写 3 个文件）依旧 PASS。

**更正（`kind` 部分）**：原第 3 条 `finding/ff_deps kind= has no effect (CLI ignores it)` 已**删除**，替换为两条判别性检查：

| 检查 | 结果 |
|---|---|
| `finding/ff_deps kind= IS honoured (discriminating values change the count)` | `kind=sound` → `count=0`（158 字节）、`kind=__none__` → `count=0`（158 字节）、`kind=weapon` → `count=1204`、不带 → `count=1204` ⇒ CLI **确实**按 `kind` 过滤 |
| `finding/kind=weapon vs no kind shares sha256 but is NOT discriminating (all 1204 refs are weapon)` | 两者同为 209703 字节 / `c43b24a2e2dda3f3`，说明旧对照**无法区分**“参数生效”与“参数被忽略” |
| `fix/ff_deps keeps kind= in argv (the CLI filters on it)` | `Firefight deps root=<STOCK> value=WEAPON_PISTOL_P38 kind=weapon --json` —— 恢复后的向量与 task-2 逐字一致 |

即：`limit` 的删除用“带/不带结果相同”证明是充分的（对照取值判别性成立），`kind` 的删除用同一方法则不成立（对照取值恰好与默认结果同值）。这条更正由 Lead 与 verifier-repo 指出，并已在 §5.5 记为“假阳性”教训。

### 8.4 子树 payload：schema 与渲染都已修好

原始 CLI payload（`show_subtree`，`ff.py Firefight show Data/Weapons/WEAPON_PISTOL_P38.txt/ammo root=<STOCK> --json`，exit 0）：

```json
{"path":"Data/Weapons/WEAPON_PISTOL_P38.txt","key":"weapon/ammo","count":1,
 "values":[{"path":"weapon/ammo/type/flavour","line":23,"value":"FLAVOUR_BALL"},
           {"path":"weapon/ammo/type/speed","line":23,"value":"350"},
           {"path":"weapon/ammo/type/mass","line":23,"value":"0.008"},
           {"path":"weapon/ammo/type/name","line":23,"value":"9x19mm Parabellum"}]}
```

| 维度 | task-2 记录（0.1.0 树） | 现在 |
|---|---|---|
| 声明 | `SHOW_OUTPUT.properties` 只有 `[path,format,text,toml,xml,warnings]`，子树三个键全缺 | `[path,format,text,toml,xml,key,count,values,warnings]` |
| 渲染 | `` `${path} (undefined)` `` + 空 body（`format`/`toml`/`xml`/`text` 都不存在） | 首行 `Data/Weapons/WEAPON_PISTOL_P38.txt weapon/ammo · 1 element · 4 values`，随后 4 行 `  weapon/ammo/type/<leaf>:23 = "<value>"`，无 `undefined` |
| 契约 | payload 仍恰好匹配 1 个分支（旧契约也能过，但语义靠运气） | `fix/ff_show subtree payload still matches exactly one output branch` PASS |

抬头语义也顺带修正：`count` 是**子树选择器命中的元素数**（这里是 1），`values.length` 是**叶子值数**（这里是 4）。旧抬头把两者压成 `1 value(s)`，正是这个 bug 的可见症状；新抬头 `1 element · 4 values` 把两者区分开。

### 8.5 剩余的 CLI 侧缺陷：文档化，而非掩盖

- 缺陷本体仍在 CLI：`cli\main.py parse_argv` 把任何“含 `=` 且不以 `-` 开头”的 token 当 `key=value` 选项（`'=' in token and not token.startswith('-')`），所以 selector `Data/Good/eq=file.toml` 会被吞掉，调用静默扩大为整个 scope（`finding/a selector containing "=" is swallowed as a key=value option` 仍 PASS：`count=4` vs 对照 `Data/Good` 的 `count=2`，stderr 为空；最小复现命令见 §5.1）。
- 插件侧现在**文档化**了这一点，两处：`README.md:77-80` 与 `lib/specs.js:202` 的 `ff_list.selector` 描述。
- **正确的规避只有“重命名”。** `ff_show` 同样把 `=` 当选项，于是变成“没有给 selector”，**报错而不是读到文件**（`finding/ff_show cannot read a "="-named file either (advice must be "rename")` PASS）：

```powershell
& <python> ff.py Firefight show 'Data/Good/eq=file.toml' "root=<PROBE>" --json
# exit 2, stdout 0 字节, stderr: expected one file, got 4; name the file explicitly
& <python> ff.py Firefight show "root=<PROBE>" --json     # 对照：完全相同的报错
```
  证据：`_payloads\show_equals_selector.{out.json,err.txt}`、`_payloads\show_probe_noselector.{out.json,err.txt}`（两者 stderr 文本一致）。文档最初写的是“rename such a folder **or read it with `ff_show`**”，该后半句已被删掉，现在两处都只剩 `rename such a folder.`；脚本新增断言 `doc/the "=" gap is documented as rename-only, not "read it with ff_show"` 守住这一点（取含 `silently widens` 的那一行，要求含 `rename such a folder` 且不含 `ff_show`），PASS。
- **插件没有自动化防护**：`build()` 不检查 selector 里是否含 `=`，也不报错/不自愈；调用方传了含 `=` 的 selector 时仍会静默拿到整个 scope 的结果，而 payload 里 `count` 会明显偏大。定性：**已文档化的残留风险（低概率：stock 1840 个 txt/toml 文件名中含 `=` 的为 0），非“已修复”**。是否要加防护属于产品决策，我未擅自修改 `lib/`。

### 8.6 本轮结果

- `SUMMARY checks=318 passed=318 failed=0 notRun=2`，node exit 0；日志 `export-out\e2e-verify-run.txt`（338 行）
- 分段（见 §7.1）：**138 / 48 / 60 / 11 / 41 / 20 = 318**
- 本轮新增/改写的断言组：2 条 `argv/delta-*`（`limit` 删除）、1 条历史 hash 重建、1 条新冻结 hash、`argv/prefix-vectors-stable`（42/43）、5 条参数增删、4 条 `tool:null` 的真实探针（`show_equals_selector`/`show_probe_noselector`/`deps_kind_sound`/`deps_kind_none`）、3 条 replay 的 argv/payload/call 检查、**判别性** `kind` 对照 3 条（含“sha256 相同但并不判别”这条反例）、子树修复 3 条、`ff_deps` 保留 `kind` 的 argv 断言 1 条、timeout 修复 6 条（§8.8）
- `NOT RUN` 从 1 条增至 2 条：`host/real-validator-importable`（真实 host 包不可导入，§6.1/§8.7）+ `fix/live timeoutMs=1 with a real python child`（node 沙箱拒绝一切 spawn，§8.8/§8.7）
- 与 Lead 数字的核对：Lead 报 follow-up 改动后我处 **5 条失败**（当时 3 条含 `limit=`/`kind=` 的 argv 向量、1 条黄金 sha256、1 条子树 finding），我复算得到完全相同的 5 条（`plugin=bd6f43d8256eb69f`、子树已打印 `… · 1 value(s)` 即为修复生效）；随后按 Lead 的 `kind` 更正把该向量恢复，最终 0 失败，无未解释差异。
- **一处我自己的结论被推翻**（`ff_deps` 的 `kind`）：原判“CLI 忽略”是**非判别性对照**导致的假阳性，已按 CLI 源码与 `kind=sound`/`__none__` 实测更正（§5.5、§8.3）。这是本轮唯一的方法学失误，保留在报告里。

### 8.7 本轮新增的未覆盖 / 待提权项

1. **插件自带测试仍无法执行**：`node --test "test/*.test.js"`（cwd `D:\deepseek-harness\WorkSpace\_scratch\ffplugin`，即 `package.json` 的 `scripts.test`）在沙箱内 `spawn EPERM`（与 §6.1 同一限制）。因此新增的 `test/output-schema.test.js`、`test/call.test.js` 我从未执行过——我用 `e2e-verify.mjs` 段 5b（stub 可执行证明）+ §8.4/§8.8 独立复算了它们的等价断言，但“这 9 个测试文件全绿”不在我的证据范围内。
2. **真实 host 校验器仍未被执行**：`test/real-harness.test.js` 因缺 peer `@deepseek-ai/cordis` self-skip；§5.2/§8.4 的“恰好一支”断言是在插件自带 stub 上可执行的，真实 `validateJsonSchemaValue` 只做了源码静态定位（§4.3）。
3. **`--live` 超时探针待提权**：`e2e-verify.mjs --live` 需要真实子进程，沙箱内输出 `LIVE could not run: FfCliError: cannot run …python.exe: spawn EPERM`（exit 2，日志 `export-out\e2e-verify-live.txt`）。完整命令（cwd `D:\deepseek-harness\WorkSpace\_scratch\verify`）：`node e2e-verify.mjs --live`，期望 `LIVE code=timeout message="the editor CLI did not answer within 1 ms" elapsed=…ms -> PASS`（exit 0）。附带的 `export-out\sleep-probe.py`（`import time; time.sleep(5)`）由脚本自动生成。
4. **负样本的组合变化未测**：replay 只验证了“单参数缺省”与旧采集等价，没有构造 `limit=` 与 `kind=` 之外的组合参数变化。
5. **未做的事（遵指令）**：没有修改 `_scratch/ffplugin` 下任何文件、没有额外 commit/push（插件树本身不是 git 仓库，§4.1），报告与脚本是唯一写入。
6. **`lib/specs.js`/`README.md` 的文本类断言**：我用正则定位片断，不构成“README 全文无其他不一致”的证明。

### 8.8 timeout 消息修复验算（task-7）

Lead 在 task-7 中报告：`lib/runner.js` 新增并导出 `resolveTimeoutMs(config)`（默认 60000），`createRunner` 与实际 timeout 文案共用它。核验结果：

- 源码：`lib/runner.js:9` `export const DEFAULT_TIMEOUT_MS = 60000;`、`lib/runner.js:56-61` `resolveTimeoutMs(config)` = `Number(config?.timeoutMs) > 0 ? config.timeoutMs : DEFAULT_TIMEOUT_MS`；`createRunner` 内 `lib/runner.js:71` `const timeoutMs = resolveTimeoutMs(config);` 同时供定时器与 `result.timeoutMs` 使用；`lib/call.js:9` 导入该 helper，`lib/call.js:50` 文案 `` `the editor CLI did not answer within ${resolveTimeoutMs(config)} ms` ``。两处都是同一函数 ⇒ 文案与实际定时值无法再分叉（脚本断言 `fix/runner timer and call.js message share resolveTimeoutMs`）。
- 我把 task-4 的 finding 探针（原名 `finding/timeout message prints the raw config.timeoutMs`）**改写为修复断言**，并保留反面对照：
  - `fix/timeout message reports the resolved default instead of the raw config` → `{}`（无 `timeoutMs`）必须报 `the editor CLI did not answer within 60000 ms`
  - `fix/timeout message follows an explicit config.timeoutMs` → `timeoutMs=4321` → `… within 4321 ms`
  - `fix/non-positive or non-numeric timeoutMs falls back to the default in the message` → `0`、`-5`、`"60000"`（字符串）三种输入都报 `60000 ms`
  - `fix/resolveTimeoutMs is exported and matches the message path` → `250 → 250`、`{} → 60000`、`undefined → 60000`、`NaN → 60000`
  - `fix/timeoutMs=1: …` → 用注入假 child 的 runner 让**真 1 ms 定时器**触发（`elapsed=13ms`），`invokeCli` 返回 `code=timeout` 且文案 `… within 1 ms`，同时断言 `resolveTimeoutMs(shortCfg) === 1`（即“打印值 == 实际生效值”）
- 真实子进程版本（`--live`）在沙箱内无法执行：本沙箱**一切 node spawn 都被拒**（`Error: spawn EPERM … errno: -4048, code: 'EPERM', syscall: 'spawn'`，node 与 python 都一样，探针 `export-out\spawn-probe.cjs`），因此标记为 `NOT RUN` 并给出提权命令（§8.7 第 3 条）。这是本轮唯一新增的未覆盖项，不是失败。
- **其它 finding 探针是否翻转**：没有。逐条重跑后 `finding/*` 中只有 timeout 这一条被改写（因缺陷消失）；`ff_list`/`ff_export` 的 `limit`、selector 含 `=`、`ff_show` 子树、`ff_deps` 的 `kind` 等探针全部仍 PASS，无新增失败。
