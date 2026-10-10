# 独立验算报告 — task-3

> **路径说明（2026-10-11 补记）**：本报告写于工程目录搬迁之前，正文里的 `D:\deepseek-harness\WorkSpace\_scratch\ffplugin`、`_scratch\verify`、`_scratch\m3-cli`、`_scratch\m2-refs` 现位于 `D:\deepseek-harness\WorkSpace\firefight-mod-editor-open\` 下同名目录（`m2-refs` 已并入 `m3-cli`）。正文为当时事实，未改写。**再补记（同日第二次整理）**：本报告所在目录已由 `firefight-mod-editor-open\verify\` 挪到 `firefight-mod-editor-open\docs\verify\`，`ffplugin\`、`m3-cli\` 位置不变。

对象：`BiancaoAwa/dsh-firefight-mod-tools`，`main@bc183fcddab3d7e403c11d6d44359957b028c011`（父 `08ab0284bb4e7fe2bb97596aef1069c5e90e9bac`）
本地工作树：`D:\deepseek-harness\WorkSpace\_scratch\ffplugin`
验算员：`verifier-repo`（task-3）· 时间：2026-10-10（Asia/Shanghai）
只读远端（未 push / 未开改 PR / 未合并 / 未删分支）；未改动插件 `lib/`、`test/`、`README.md`。

## 结论先行

| # | 待证声明 | 判定 | 一句话 |
| --- | --- | --- | --- |
| 1 | 远端与本地逐字节一致 | **成立** | 23/23 文件的 git blob sha1 与字节数完全相同；远端无 `node_modules`、无多余/缺失文件 |
| 2 | README 的每条声明都对得上代码 | **不成立** | 4 处声明与代码不符（含 2 处会直接影响使用者的命令/安装说明），另有 2 处无法判定 |
| 3 | `ff_export` 的审批门不可绕过 | **成立** | 27 个对抗用例，0 个可绕过；2 项设计性风险（HAZARD）只能由"更早注册的同事件监听器"或宿主契约变更触发，不是当前代码可被绕过的路径 |

发现的严重度：**中 2 · 低 4 · 信息 3**（详见 §7）。

---

## 0. 环境与方法

- node：`C:\Users\BC_aw\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe` = **v24.21.0**（满足 `engines: ^22.19.0 || >=24.0.0`；该目录无 npm/pnpm）。
- 本地 `D:\deepseek-harness\WorkSpace\_scratch\ffplugin` 不是 git 仓库（`git rev-parse` → `fatal: not a git repository`），且带 `node_modules`（pnpm@11.7.0，storeDir `D:\deepseek-harness\WorkSpace\.pnpm-store\v11`，真实 `@deepseek-ai/dsh-tools@0.2.1-alpha.1` 已安装）。
- 远端读取：`gh_repo` / `gh_file` / `gh_review`（只读），外加只读 `api.github.com` GET（token 取自 `C:\Users\BC_aw\.dsh\.credentials.yaml` 的 `refs.GITHUB_TOKEN`，全程未回显）。
- 字节比对方法：本地用 raw git blob sha1 = `SHA1("blob " + <byteLength> + "\0" + bytes)`（PowerShell `[System.Security.Cryptography.SHA1Managed]`），远端用 `GET /repos/.../git/trees/bc183fc?recursive=1` 的 40 位 blob sha 与 size。
  - **坑（记录）**：`git hash-object` 在本目录给出 `.gitignore` = `c5abc91761aa0d0bb57f51b8bc752bd41f3c7c2c`，与远端 `3be3c7c67e1887ab8ae0d0af260d4dad8ee93aed` 不同——因为 git 施加了 CRLF 过滤器。手工 raw sha1 与远端一致。**别用 `git hash-object` 在仓库外比对 CRLF 文件。**
- 宿主真实契约：从随产品发布的 `D:\deepseek-harness\resources\app.asar` 中检索（ripgrep 可直接在 asar 上匹配文本），用于判定审批门在真实宿主中的行为。

---

## 1. 声明 1：远端与本地逐字节一致 —— **成立**

命令（远端）：

```
GET /repos/BiancaoAwa/dsh-firefight-mod-tools/git/trees/bc183fc?recursive=1   → truncated=false, 25 entries
GET /repos/BiancaoAwa/dsh-firefight-mod-tools/commits/bc183fc                 → parents=["08ab0284bb4e7fe2bb97596aef1069c5e90e9bac"]
GET /repos/BiancaoAwa/dsh-firefight-mod-tools/branches                        → main@bc183fc（唯一分支）
GET /repos/BiancaoAwa/dsh-firefight-mod-tools/pulls?state=all                 → []
GET /repos/BiancaoAwa/dsh-firefight-mod-tools/issues?state=all                → []
```

25 entries = 23 blobs + `lib/`、`test/` 两棵树；**无 `node_modules` 条目**。本地 `Get-ChildItem -Recurse -Force`（排除 `node_modules`）正好是同样 23 个文件，无缺失、无多余。

23 个文件本地 raw blob sha1 == 远端 blob sha，且 size 相同（本地 `node_modules` 未被推送，故不参与比对）：

| 路径 | bytes | sha1 |
| --- | --- | --- |
| `.gitignore` | 25 | `3be3c7c67e1887ab8ae0d0af260d4dad8ee93aed` |
| `LICENSE` | 35149 | `f288702d2fa16d3cdf0035b15a9fcbc552cd88e7` |
| `README.md` | 5313 | `268ebbd942909932d919c3c7ef624bd9290d5dd1` |
| `cordis.patch.yml` | 727 | `484d1c9bfa977a362c9d115d7668a5d2f87da05a` |
| `package.json` | 1121 | `de949f3a60bb00730046fcd9f384b0f1a60e8635` |
| `pnpm-lock.yaml` | 2652 | `bda46cd1053080b63aacb84573e8857a4d55eb13` |
| `lib/approval.js` | 1212 | `34bad516dbb48b9f1bb58786b9ff63003a5edf9d` |
| `lib/call.js` | 2690 | `7fb3f938fd919147f53968fedde332f4d09b4321` |
| `lib/config.js` | 1535 | `24f9a65b8a717282b13913cc72d818147f56727c` |
| `lib/index.js` | 1481 | `86db516918ac117e859510298471bb94c16bd2a5` |
| `lib/render.js` | 8962 | `1b8c0249241b4fc1e8199686013679cd3e252999` |
| `lib/runner.js` | 4830 | `9ebafb7d14cde15c2329360c81b02ae9b58b898f` |
| `lib/specs.js` | 15785 | `ade9a1f0d90fd8d2924bc23436b15ab9605657c8` |
| `lib/tools.js` | 1872 | `b0d2354cd6dcede38757a0de8bf79e9a16adf6d7` |
| `test/approval.test.js` | 2086 | `97041235aba2d1f4d569397aae8b5b98c6580658` |
| `test/call.test.js` | 2758 | `3b7ae18ac6772616e81632b56068f77ae74af251` |
| `test/config.test.js` | 979 | `c102cc47d2e148c300d90e0014d66788bb300747` |
| `test/harness-stub.js` | 7584 | `6e7cc41370940c3d7d825e971b6f67e362ea839d` |
| `test/plugin.test.js` | 6423 | `bf3e832ba55c21a318a7b08a326c0a52aa6cca74` |
| `test/render.test.js` | 3777 | `37d9dc8889c6e9c74371b3bfd3356bb092e09d9d` |
| `test/runner.test.js` | 4191 | `a41bff05a2dc8bb616b07959b8c59fb23540e50c` |
| `test/specs.test.js` | 4706 | `a6f58bd8d1034e0dca779bb5e5cace0b19855366` |
| `test/support.js` | 4121 | `ffb6823705391bc9b6a8d5a9bf26ad144702f507` |

附带核对：`bc183fc` 的改动集 = 新增 21 个文件 + 修改 `README.md`；`08ab028` = "Add LICENSE file"；仓库私有，默认分支 `main`，GPL-3.0。**"直接推到 main"这一背景也成立**（唯一分支、无 PR、无 issue）。

## 2. 清单自洽性（属声明 2 的前置项）—— **成立**

- `LICENSE` 35149 字节，blob sha `f288702d2fa16d3cdf0035b15a9fcbc552cd88e7`，与编辑器仓库 `BiancaoAwa/firefight-mod-editor-open` 的 `LICENSE` **逐字节相同**（同 sha、同 size）。
- `package.json`：`name dsh-firefight-mod-tools` / `version 0.1.0` / `main lib/index.js` / `exports {".":"./lib/index.js","./package.json":"./package.json"}` / `files ["lib","cordis.patch.yml","README.md","LICENSE"]`（四个都在远端树中）/ `license GPL-3.0` / `repository git+https://github.com/BiancaoAwa/dsh-firefight-mod-tools.git` / `engines node ^22.19.0 || >=24.0.0`（本机 v24.21.0 满足）/ `dsh.manifestVersion 1` / `dsh.bundle.patch ./cordis.patch.yml`。全部自洽。
- `cordis.patch.yml`（20 行）为单条 `- insert:` 列表项，与 `dsh.manifestVersion: 1` + `dsh.bundle.patch` 的结构一致。
- `lib/config.js` 的 `Config` 恰有 9 个键，README 配置表 9 行与默认值一一相同。
- 一处完整性小缺口：`cordis.patch.yml` 的 `config:` 只列 8 个键，**缺 `cwd`**（`lib/config.js` 有，默认 `''`）。因缺省键回落 schema 默认值，行为等价 → 文档完整性 nit，非缺陷。

## 3. 声明 2：README 每条声明 vs 代码 —— **不成立**

### 3.1 与代码相符的声明（成立）

- 工具表 9 行的**参数名、required、枚举**与 `lib/specs.js` 一致：`ff_show` 的 `as ∈ {raw,toml,xml}`；`ff_show`/`ff_get`/`ff_refs` 的 `selector` required；`ff_deps` 的 `value` required 且 `build` 置 `selector: undefined`；`ff_export` 的 `to` required；`ff_find` 的 `ignoreCase` → `ignore_case`。表格省略的共享 `scope`/`root`/`workspace` 由表格上方段落说明（README:58-60）。
- README:7 的调用形状 `ff.py <scope> <command> [selector] [key=value ...] --json` 与 `lib/runner.js:43` `buildArgs()` 完全一致；`formatOption` 把布尔转成 `1`/`0`。
- README:76-80 "Payload first"：`lib/call.js` 先 `parsePayload(result.stdout)`（stdout 能 JSON.parse 即结果，即使退出码非 0），再按 `code` 给 `usage`(2)/`cli-error`/`empty-output`，`timeout`/`cancelled` 由标志位给出；`result.failure !== undefined` 时抛 `FfCliError`（"无法启动进程 = 基础设施失败"）。与 README 完全对应。
- README:81-83 "Export asks"：`lib/index.js:34` 仅在 `config.enableExport === true` 时 `ctx.effect(() => registerExportGate(ctx))`；`lib/approval.js:21-25` 对 `ff_export` 每个调用返回 `{ kind: 'ask' }` 且不调用 `next()`。宿主侧（app.asar @59465760）`unavailable` → `{kind:'deny', reason:'tool "ff_export" requires approval, but no approval channel is available'}`，"无审批通道则拒绝"成立（见 §4 C1）。
- README:87-88 "Concurrency"：`lib/specs.js` 中 8 个只读工具均 `concurrencySafe: true`，`EXPORT_SPEC` 为 `false`；宿主 app.asar @1044733 `if (!tool?.isConcurrencySafe) return { kind: "exclusive" }`——非并发安全的工具被排为排他，于是"导出不会与其他调用重叠"成立。

### 3.2 与代码不符的声明（不成立）

**R1 —— 不成立（中）：Development 命令 `node --test test/`（README:96，即 `pnpm test`）在本 Node 版本不会按预期运行。**

```
$ node --test --test-isolation=none test          # 裸目录参数，无子进程参与
✖ test (0.8143ms)
ℹ tests 1   ℹ pass 0   ℹ fail 1
$ node --test --test-isolation=none test/
Error [ERR_UNSUPPORTED_DIR_IMPORT]: Directory import 'D:\deepseek-harness\WorkSpace\_scratch\ffplugin\test' is not supported resolving ES modules
$ node --test test/                               # README 原文
Error: spawn EPERM  errno: -4048  code: 'EPERM'  syscall: 'spawn'
    at node:internal/test_runner/runner:529 FileTest.run     （本沙箱子进程限制）
$ node --test --test-isolation=none 'test/*.test.js'        # 同一 node，显式 glob（node 自己展开）
ℹ tests 46   ℹ pass 46   ℹ fail 0   ℹ skipped 0
$ node --test --test-isolation=none '**/*.test.js'          → 同样 46 通过
```

关键点：**裸目录参数不被展开这一点在本机无需子进程即可复现**（`✖ test` / `ERR_UNSUPPORTED_DIR_IMPORT`），所以默认隔离下 spawn 出的子进程同样会在导入该目录时失败；EPERM 只是沙箱掩盖了失败的后半段。可用的等价命令是 `node --test 'test/*.test.js'`（或省略参数的默认发现 `node --test`，本机 48/48 通过）。

**R2 —— 不成立（中）：安装说明不可复现——编辑器默认分支 `main` 里没有 `ff.py`。**

```
$ gh_file BiancaoAwa/firefight-mod-editor-open ff.py@main
404 Not Found
$ GET /repos/.../firefight-mod-editor-open/compare/main...m2/refs  → status=diverged ahead_by=2 behind_by=1
$ branch main → b9851652fb4b0d2137475165b462b9072aec3d93
```

`ff.py`（以及整个 `cli/`）只存在于 `m2/refs@7896814bc2b733fa39beb563b8c904cc0957d8bd` 与 `m3/cli@9829cd5efd997a4573a90d8423defc357eebf7e2`。而 README:16 只说"the directory that holds `ff.py`"，README:4-5 链接仓库但不提分支。按 README 的 `pnpm add` + 配置示例（`editorRoot: 'D:/src/firefight-mod-editor-open'`）照做，`lib/runner.js:30-31` 会给出 `<editorRoot>/ff.py`，spawn 得到 ENOENT → 所有工具以基础设施失败结束。**文档缺陷，不是代码缺陷**：代码的行为与它自己的文档一致（`editorRoot` 语义正确），缺的是"必须检出含 `ff.py` 的分支"。

**R3 —— 不成立（低）：README:67 "It needs a selector"（`ff_find`）与代码相反。**

`lib/specs.js:236`：`selector: str('Optional folder or entity to search inside.')` —— **非必填**，且 README 自己的表格行也没写 "(required)"（同为 `selector` 的 `ff_show`/`ff_get`/`ff_refs` 都标了 required）。README 表格与散文自相矛盾，代码站在表格一边。

**R4 —— 不成立（低）：README:84 "Each renderer prints at most 100 rows" 过度概括。**

`lib/render.js:10` `const ROW_LIMIT = 100;` 只约束 `rows()`（第 76 行 `items.slice(0, ROW_LIMIT)`）。`renderShow`（第 99-100 行）直接把 `value.toml ?? value.xml ?? value.text` 全文输出，不做行裁剪；`renderCheck`（第 159-171 行）有 `warning_samples` 与 `dangling` **两段各 100 行**，即最多 200 行再加两行省略提示。准确说法是"每个列表段最多 100 行"。

**R5 —— 不成立（低）：README:99-102 "test/plugin.test.js … skips itself when @deepseek-ai/dsh-tools is not installed locally" 不实。**

`test/plugin.test.js:16-24`：

```js
let host;
try { host = await import('@deepseek-ai/dsh-tools'); } catch { host = undefined; }
const defineTool = host?.defineTool ?? stub.defineTool;
```

在 `test/` 全目录 grep `skip|todo` 只命中 `test/support.js:102` 里的字符串 `skipped: 0` 与 `test/harness-stub.js:6` 注释中的 "skipping away"——**没有任何 skip 逻辑**；依赖缺失时它替换成 `test/harness-stub.js` 的严格假工厂，而不是跳过自己。且本机 `node_modules` 里**确实装着**真实的 `@deepseek-ai/dsh-tools`（0.2.1-alpha.1），所以本地跑的就是真实工厂 + stub 两条路径中的真实分支。文件头注释（`test/plugin.test.js:4-6`）描述的行为也是"注入 stub"，与 README 说法不符。

### 3.3 README 中无法判定的声明

**U1 —— 无法判定：`pnpm install --config.auto-install-peers=false`（README:95）。** 未执行，依据：(a) 会改写共享的 `node_modules`，而其他队友可能正在同一份检出上跑测试；(b) 会改动共享 pnpm store 且需要网络；(c) task-3 把我的写入限制在两个交付文件内。反面证据：一次安装曾经成功——`pnpm-lock.yaml` 已提交，`node_modules/.modules.yaml` 记录 pnpm@11.7.0、storeDir `D:\deepseek-harness\WorkSpace\.pnpm-store\v11`，且 `@deepseek-ai/{dsh-tools,schemastery,cosmokit}` 齐备。命令本身与 `package.json` 的 `peerDependencies` 设计（peer 由宿主提供）一致。

**U2 —— 无法判定：README:15 "Python 3.10+ on PATH (tested with 3.12)"。** 本机 `python` 解析到 `D:\Program Files\QClaw\v0.2.32.610\resources\openclaw\config/bin/python\python.cmd` = **3.14.5**，既非 3.12、也没有 3.10/3.12 环境可对照，且本地不存在 `ff.py`，无法端到端验证版本声明。

## 4. 声明 3：审批门对抗 —— **成立（不可绕过；27 用例 / 0 绕过 / 2 项设计性风险）**

脚本：`D:\deepseek-harness\WorkSpace\_scratch\verify\gate-attack.mjs`（驱动真实入口 `lib/index.js` 的 `applyWithDeps`，假 ctx 建模宿主；假 payload runner，不 spawn、不联网、不写文件）。
命令：`node gate-attack.mjs`（完整原始输出另存于同目录 `attack-out.txt`）。

```
=== summary ===
cases=27 invariantFailures=0 bypasses=0 hazards=2
```

复刻的真实宿主契约（均为 app.asar 内证据）：

- `tools/pre-execute` 是 waterfall，默认结果为 `{kind:'allow'}`：`const gate = await this.ctx.waterfall(carrier, "tools/pre-execute", exec, () => Promise.resolve({ kind: "allow" }))`（@59456100 / @59523624）。
- `exec` 形态：`export interface ToolExecutionInput { readonly callId; readonly name: string; readonly arguments: unknown; readonly agent?; readonly signal }`（@1021339）；`PreToolDecision` 含 `{kind:'ask'; reason?}`（@1019742）。
- `ask` → 审批服务；`unavailable` → `deny: tool "<name>" requires approval, but no approval channel is available`（@59465760）。
- 所有分发路径都经过同一门：`execute()` 与并行/PTC 调度器的 `prepareScheduledExecution()` 都汇聚到 `prepareExecution()`（@59452261、@59430800），即 waterfall 所在处。

对抗用例与结果（节选；完整 JSON 在 `attack-out.txt`）：

| 用例 | 攻击意图 | 实际结果 | 能否绕过 |
| --- | --- | --- | --- |
| A1 | `enableExport` 关闭时偷注册 `ff_export` | `tools=8 listeners=0`，无 `ff_export` | 否 |
| A2 | 开启时确认工具+门成对 | `tools=9 export=true listeners=1 effects=2` | 否 |
| A3 | 11 种配置值（`'true'`/`'yes'`/`1`/`0`/`null`/`undefined`/畸形配置回落）下"有工具无门" | 11/11 一致，`disagreements=0` | 否 |
| A4 | 配置 getter 每次读取翻转值（TOCTOU 制造工具/门不同步） | `reads=1 export=true gate=true`（`resolveConfig` 回落路径只复制一次快照） | 否 |
| A5 | `defineTool` 不可用 + 开导出 | 工具 effect 抛错，`tools=0 gate=0`，`applyWithDeps` 抛出（fail-closed） | 否 |
| A6 | 宿主吞掉 effect 错误 | `tools=0 gate=1`——没有任何工具被半注册 | 否 |
| B1.1–B1.10 | `ff_export` 的 10 种 `arguments`（完整/undefined/null/`{}`/字符串/数字/数组/非字符串字段/抛异常的 getter/`__proto__` 污染） | 10/10 返回 `ask` 且 `passedThrough=false`；getter 抛异常时监听器抛出（宿主 try/catch → 调用失败，仍无写入） | 否 |
| B2 | reason 文案形状 | `"dsh-firefight-mod-tools: export Mod / Weapons to D:/out; this writes files"`（与 README/测试一致） | 否 |
| B3 | 名称大小写/空白/后缀变体（`FF_EXPORT`、`ff_Export `、`ff_export\n`、`ff_exportX`、`ff-export`、``、`ff_export.export` 等 12 种） | 12/12 全部落到 `next()`（严格 `!==`，无归一化）——但真实宿主按注册名解析 `exec.name`，模型侧不存在别名，故当前不可达 | 否（前提：无别名注册） |
| B4 | `exec.name` 缺失 / `exec` 为 `undefined` | 均 `passedThrough=true`（**fail-open 形状**） | 否（宿主契约不可达） |
| B5 | 误拦 8 个只读工具 | 8/8 原样放行 | 否 |
| B6 | 下游 `next()` 抛异常 | 原样上抛，未吞掉、未 fail-open | 否 |
| C1 | 端到端：`ask` → 审批服务（无通道 / 允许一次 / 用户拒绝） | `none → deny: tool "ff_export" requires approval, but no approval channel is available`；`allow-once → allow`；`reject → deny` | 否 |
| C2 | 无审批通道时只读工具被误伤 | `ff_list → allow` | 否 |
| C3 | **更早注册**的 `tools/pre-execute` 监听器返回 `{kind:'allow'}` 且不调用 `next()` | 门**从未被调用**，`decision={kind:'allow'}` | **顺序相关（HAZARD）** |
| C4 | 更晚注册的宽松监听器把 `ask` 改回 `allow` | 仍是 `ask`（门返回时不调用 `next()`，后续监听器不执行） | 否 |
| D1 | 并发安全声明 | 8 个只读工具 `isConcurrencySafe()===true`，`ff_export` 为 `false` | 否 |
| D2 | 绕过注册表直接调 `execute()` | `execute` 存在且内部无审批检查——门在流水线层，不在工具实现里 | 否（真实调度必经 `prepareExecution`；仅对可信的进程内直接调用者成立） |

**判定**：在真实宿主契约下，**审批门不可绕过**。唯一"关掉门"的路径（C3）依赖**另一个插件注册在同一上下文且排在前面并短路 waterfall**——宿主自己把这个事件称为 "reorderable allow/deny/ask gate"（app.asar:1041318），并把 `ctx.tools.guard()` 作为顺序无关的拒绝路径（app.asar:1041265）；而"询问用户"必须返回 `ask`、`ask` 只能来自 waterfall，这是宿主明示的取舍。因此 C3/B4 记为 HAZARD（设计前提），不是本插件代码的缺陷；建议在 README 里显式写出这个前提（见 F7）。

## 5. 敏感信息扫描 —— 成立（无泄漏）

对 `*.{js,json,yml,yaml,md,txt}` grep `BC_aw|deepseek-harness|Steam|steamapps|ghp_|github_pat_|gho_|Bearer |api[_-]?key|password|token|@gmail|@qq\.com|@outlook|C:\\Users|D:\\|/Users/` → 16 处命中，全部无害：

- `README.md:35`：Steam 示例路径（`D:/Program Files (x86)/Steam/steamapps/common/Firefight`），属于文档示例。
- `test/approval.test.js:38`、`test/render.test.js:38`：`D:/out` 假路径。
- `node_modules/.modules.yaml:36-37`：`D:\deepseek-harness\WorkSpace\.pnpm-store\v11` 与 `...\ffplugin\node_modules\.pnpm`——**node_modules 未被推送**，不构成远端泄漏。
- 其余命中是 `lib/specs.js` / `lib/render.js` 描述文本里的英文单词 "token"。

无 `BC_aw`、无真实家目录、无凭据、无邮箱进入远端树。

## 6. `ff.py` 的来源与编辑器仓库状态 —— 成立（已解释）

```
PR#8  main ← m2/refs    merged=true  merged_at=2026-10-09T17:33:29Z
      merge_commit_sha=b9851652fb4b0d2137475165b462b9072aec3d93  == 当前 main head
PR#9  m2/refs ← m3/cli  merged=true  merged_at=2026-10-09T17:33:44Z
      merge_commit_sha=7896814bc2b733fa39beb563b8c904cc0957d8bd  == 当前 m2/refs head
```

之前"PR #8/#9 都已合并、main 却没有 `ff.py`"并非异常：**#8 合并进 `main`，#9 的目标分支是 `m2/refs`**（不是 `main`）。所以：

- `m3/cli@9829cd5` 与 `m2/refs@7896814` **含** `ff.py` + `cli/{__init__,commands,documents,main,scope}.py` + `docs/cli.md` + `tests/test_cli.py`；
- 编辑器 `main@b9851652` **不含** `ff.py`（`ff.py?ref=main` → 404）。

插件 README 链接了该仓库却未指明分支/PR，这正是 R2。

## 7. 发现清单（严重度 / 证据 / 影响）

| ID | 严重度 | 发现 | 证据 | 影响 |
| --- | --- | --- | --- | --- |
| F1 | 中 | `node --test test/`（README:96 与 `scripts.test`）在 Node 24 不展开目录 | §3.2 R1 的 5 条命令输出（`✖ test`；`ERR_UNSUPPORTED_DIR_IMPORT`；`test/*.test.js` → 46 通过） | 贡献者/CI 照文档跑测试会失败；应改为 `node --test 'test/*.test.js'` 或裸 `node --test` |
| F2 | 中 | 安装说明未说明需要 `ff.py` 所在分支，而默认分支没有它 | `ff.py@main` → 404；`m2/refs`/`m3/cli` 有；`lib/runner.js:30-31` 拼 `<editorRoot>/ff.py` | 照 README 走一遍，所有工具立即以"无法启动进程"失败；应写出分支/PR 或脚本路径获取方式 |
| F3 | 低 | `ff_find` 的 `selector` 被 README 说成必需，代码里是可选 | `lib/specs.js:236` vs README:67 | 模型被误导去猜测必填选择器；README 自相矛盾 |
| F4 | 低 | "每个渲染器最多 100 行"过度概括 | `lib/render.js:10,76` vs `:99-100`（`renderShow` 全文）与 `:159-171`（两段各 100 行） | 读者高估了输出上限；`renderShow` 的大文档会整篇进入结果（仍受 `maxOutputChars` 约束） |
| F5 | 低 | README 称 `test/plugin.test.js` 会"skip itself"，实际是替换 stub，且全目录无 skip 逻辑 | `test/plugin.test.js:16-24`；`skip|todo` grep 无命中 | 读者对该测试的覆盖范围判断错误（本地跑的是真实 `defineTool`） |
| F6 | 低 | `cordis.patch.yml` 少列 `cwd` 键 | 8 键 vs `lib/config.js` 9 键 | 行为等价（回落默认值），仅文档/清单完整性 |
| F7 | 信息 | 审批门的有效性以"没有更早注册的宽松 `tools/pre-execute` 监听器"为前提 | §4 C3（门从未被调用）；宿主文档 app.asar:1041318 / 1041265 | 与另一插件共装时导出提示可能被静默短路；建议 README 声明该前提 |
| F8 | 信息 | 门按 `exec.name` 精确匹配；`exec?.name` 缺失时落入 `next()`（fail-open 形状） | §4 B3/B4；宿主 `ToolExecutionInput.name` 为必填（@1021339） | 当前不可达；若将来引入工具别名/前缀注册则成为真绕过 |
| F9 | 信息 | 门位于流水线层而非 `execute()` 内 | §4 D2；真实分发必经 `prepareExecution`（@59452261、@59430800） | 仅对可信的进程内直接调用者有意义，属可接受的信任边界 |

## 8. 无法判定项汇总

| 项 | 判定 | 依据 |
| --- | --- | --- |
| `pnpm install --config.auto-install-peers=false` 是否可跑（README:95） | **无法判定** | 见 §3.3 U1：写入范围/共享 store/网络限制 + 一次成功安装的反面证据 |
| "Python 3.10+ on PATH (tested with 3.12)"（README:15） | **无法判定** | 见 §3.3 U2：本机只有 3.14.5，无 3.10/3.12 环境，且无 `ff.py` 可端到端验证 |
| 默认隔离下 `node --test test/` 在无沙箱机器上的最终报错 | 部分无法判定（不影响判定） | EPERM 掩盖了子进程内的报错；但目录不被展开已在 `--test-isolation=none` 下确证，故 R1 判定不成立 |

## 9. 复现命令

```powershell
$n='C:\Users\BC_aw\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
# 审批门对抗（27 用例）
cd D:\deepseek-harness\WorkSpace\_scratch\verify; & $n gate-attack.mjs
# 测试命令差异
cd D:\deepseek-harness\WorkSpace\_scratch\ffplugin
& $n --test --test-isolation=none test                 # ✖ test, 1 test, 1 fail
& $n --test --test-isolation=none 'test/*.test.js'     # 46 pass
# 只读远端
& $n 'C:\Users\BC_aw\.dsh\profiles\desktop\skills-github-mode\github-collaboration\scripts\gh-bootstrap.mjs' tree BiancaoAwa/dsh-firefight-mod-tools --json
& $n '...\gh-bootstrap.mjs' repo-info BiancaoAwa/dsh-firefight-mod-tools
```

---

# 10. 修复后复核（0.1.1，2026-10-10 第二轮）

**对象**：本地工作树 `D:\deepseek-harness\WorkSpace\_scratch\ffplugin`（`package.json` version `0.1.1`，未推送）；远端仍是 0.1.0 的 `bc183fc`。本轮只读远端、只写 `_scratch/verify/`。

## 10.1 结论摘要

1. **Lead 声称的 6 项修复，5 项成立、1 项改错了方向。**
   - 成立：R1（测试命令改 glob）、R2（README 写明 `ff.py` 不在默认分支）、R4（100 行上限表述）、R5（`plugin.test.js` 回退 stub + `real-harness.test.js` 的可跳过说明）、F6（`cordis.patch.yml` 补齐 `cwd`）。
   - **不成立（新发现 N1）**：R3 把 `ff_find` 的说明从"需要 selector"改成"没有 selector 就不会搜到任何东西"——这句与 CLI 实际行为相反（无 selector 时 `find` 搜索整个 scope）。详见 §10.4。
2. **审批门没有被削弱。** `lib/index.js`、`lib/approval.js`、`lib/call.js`、`lib/render.js`、`lib/runner.js` 与远端 0.1.0 **逐字节相同**（不在 §10.5 的差异清单里）；对抗脚本重跑结果与第一轮完全一致：`cases=27 invariantFailures=0 bypasses=0 hazards=2`（`_scratch/verify/attack-out.txt:90`），两项 HAZARD 仍是原 B4/C3，无新增。
3. **0.1.1 的输出契约改动（每 payload 分支加一个判别式 `required`）在真实宿主包里是合法的**，虽然本机无法用真实 `defineTool` 执行（见 §10.4 观察 2），我用宿主编译器源码逐行确认（`schema.js:78-82`：属性级 `required` 只允许 `true`，并会被收集进分支的 `required` 数组）。
4. **差异清单**：本地 0.1.1 相对远端 `bc183fc` = 16 个文件相同、**7 个修改、2 个新增、0 个缺失、0 个仅远端**（§10.5）。推送与否由用户决定；若推送，**README:70 那句必须先改**。

## 10.2 逐条复核（R/F 现状）

| 项 | 现状 | 证据（命令 → 关键行） |
| --- | --- | --- |
| R1 测试命令 | **已修** | `package.json:38` = `"node --test \"test/*.test.js\""`；README:105 同形；`node --test --test-isolation=none "test/*.test.js"` → `tests 56 pass 52 fail 0 skipped 4`；反例 `node --test --test-isolation=none test/` → `✖ test  tests 1  fail 1`（目录当文件导入） |
| R2 `ff.py` 分支 | **已修且属实** | README:16-19 写明默认分支没有 CLI、取 `m2/refs` 或 PR #9 的 `m3/cli`、安装前确认 `<editorRoot>/ff.py`；远端 `contents/ff.py?ref=main` → 404；PR #9 `merged=true merge_commit_sha=7896814b…` 落进 `m2/refs`（§6 同源）；本地 `_scratch/m3-cli/ff.py` 存在，`_scratch/m2-refs/` 是合并前快照故无 |
| R3 `ff_find` | **仍不成立（改成另一种错）** | 见 §10.4 N1：`python ff.py Firefight find value=WEAPON_PISTOL_P38 limit=3 root=<stock> --json` → `"count": 3, "truncated": true`，无 selector 也照搜；`cli/commands.py:73` 空 selector 直接 `entity_files(ctx.scope)` |
| R4 100 行上限 | **已修且属实** | README:92-95；`lib/render.js:10` `const ROW_LIMIT = 100;`，唯一使用者是 `:76 rows()`，被 `renderList/renderGet/renderFind/renderRefs/renderDeps/renderExport` 与 `errorLines()` 复用；`renderShow`（`:99-104`）整篇输出；`renderCheck`（`:159-173`）对 `warning_samples` 与 `dangling` 各自调用 `rows()` → "两段各自 100 行"准确 |
| R5 测试替身说明 | **已修且属实** | README:108-117；`test/plugin.test.js:16-26` `try { host = await import('@deepseek-ai/dsh-tools') } catch { host = undefined }` + `const defineTool = host?.defineTool ?? stub.defineTool`；`test/real-harness.test.js:15-16` `const skip = harness === undefined ? '…is not importable here' : false`，本机实跑确实带该原因 skip（4 个 skip 中的 3 个来自本文件） |
| F6 `cwd` 键 | **已修** | 三个键集合完全一致（脚本比对）：`config.js keys` = `cordis.patch keys` = `readme table keys` = `pythonPath, editorRoot, scriptPath, firefightRoot, workspace, cwd, timeoutMs, maxOutputChars, enableExport`，且 9 个默认值逐项相同（`''`、`''`、`''`、`''`、`''`、`''`、`60000`、`40000`、`false`） |
| 输出契约（新增） | **成立** | `lib/specs.js:351` `outputContract = (spec) => ({ oneOf: [spec.output, ERROR_SCHEMA] })`；`:354` `discriminatorOf`；9 个 payload 分支各恰好 1 个 `req()`：`scope`×7、`path`×2（`ff_show`/`ff_get`）、`count`×1（`ff_find`），与 README:86-88 的枚举一致；`ERROR_SCHEMA`（`lib/render.js:13-23`）`additionalProperties: false` 且 `status/code/message` 都 `required: true`，两分支互斥 |
| F1–F5/F7–F9 | 见 §7；本轮无回归 | F1/F2/F4/F5 已随 R1/R2/R4/R5 消解；F3 演化为 N1；F7–F9 是设计性风险，代码未动故原样 |

## 10.3 判别式改动的宿主合法性与"恰好一支"

- 真实编译器（`node_modules/@deepseek-ai/dsh-tools/lib/types/schema.js`）：`:78-82` `if (Object.hasOwn(task.property, 'required') && task.property.required !== true) authorError(\`${task.path}.required must be true when present\`)`；同为 true 时 `task.required.push(task.key)`；`:68-71` 把收集结果写到分支节点的 `required`。`:126` `authorKeys = [...ANNOTATION_KEYS, ...(task.allowRequired ? ['required'] : [])]` → **分支节点本身不能声明 `required`，分支的属性可以**，与 `test/harness-stub.js:26-28,42-43` 的 `allowRequired` 语义一致。
- 真实校验器对 `oneOf` 是**恰好一支**：`lib/types/json-schema.js:441` / `lib/index.js:419` `finish(frame.matches === 1 ? [] : [\`"…" must match exactly one oneOf branch (matched ${frame.matches})\`])`。这正是 0.1.0 的隐患：开放对象分支没有必填属性时也会匹配闭合的 error 分支，导致每次失败都被判为非法输出；0.1.1 的 `req()` 修掉了它。
- `test/harness-stub.js` 同步改成恰好一支（`:72-78` 的 `matched === 1 / 0 / >1` 三分支），与真实校验器同语义。

## 10.4 新发现

**N1（低—中，必须改）README:70 的 `ff_find` 说明仍与 CLI 相反**

- 现文案：「Tag, value or document-path matches. **Nothing is searched without a selector**, so pass a folder or an entity; `limit` caps both the payload and the rendered rows.」
- CLI 事实（`_scratch/m3-cli`，即 PR #9 合并后的 `m2/refs` 内容）：`cli/main.py:104` `selector = " ".join(positionals[2:])`（缺省即 `""`）；`cli/commands.py:70-75` `targets()`：`if selector in ("", "all") or selector in CATEGORIES or "type" in ctx.options: return entity_files(ctx.scope)` → **空 selector = 整个 scope**；真正的约束在 `cli/commands.py:273-274`：`if tag is None and value is None and prefix is None: raise UsageError("nothing to search for; pass tag=<name>, value=<text> or path=<a/b>")`。
- 实测（只读，stock 数据 `D:\Program Files (x86)\Steam\steamapps\common\Firefight\Data`）：
  - `python ff.py Firefight find value=WEAPON_PISTOL_P38 limit=3 root=<stock> --json` → `"count": 3, "truncated": true`，命中来自 `Data/Infantry/German-Fallschirmjaegers 1.txt` —— 无 selector 照样全库搜索。
  - `python ff.py Firefight find limit=3 root=<stock> --json` → exit 2，stderr `nothing to search for; pass tag=<name>, value=<text> or path=<a/b>`。
- 建议改法（二选一）：「At least one of `tag`, `value` or `path` is required — the CLI refuses the call otherwise; without a selector the search covers the whole scope.」

**观察 1（信息）**：README:108-109 的括号「or a bare `node --test`, which searches `test/`」字面成立（`node --test --test-isolation=none` → `tests 58 pass 54 fail 0 skipped 4`），但裸跑还会把 `test/harness-stub.js` 与 `test/support.js` 当测试文件加载（TAP 报告出现 `# Subtest: test\harness-stub.js`、`# Subtest: test\support.js`，故 58 > 56）；两者无测试用例，无害。glob 形式仍是首选。

**观察 2（信息，影响"真实路径已验"的强度）**：本机 `@deepseek-ai/dsh-tools` **装了但导入必失败**：`import('@deepseek-ai/dsh-tools')` → `ERR_MODULE_NOT_FOUND | Cannot find package '@deepseek-ai/cordis' imported from …\node_modules\@deepseek-ai\dsh-tools\lib\index.js`（该包是 devDependency，其自身 peer `@deepseek-ai/cordis` 因 `--config.auto-install-peers=false` 不在树里；README:13 已说明 cordis 由宿主提供）。因此 `test/real-harness.test.js` 的真实工厂/真实校验器断言在本机 100% skip，`test/plugin.test.js` 走的一定是 stub。0.1.1 的新增真实路径未在本机执行过——我改用宿主包源码验证（§10.3）；真正跑通需要 DSH profile 环境。

**观察 3（信息）**：payload 分支开放（`additionalProperties: true`）+ error 分支闭合且要求 `status/code/message`，互斥性依赖"CLI payload 顶层不出现 `status` 字段"（`lib/specs.js:12-18` 的注释即此意）。当前 CLI 满足（`grep '"status"|'status'' _scratch/m3-cli/cli` 无命中）；若将来 CLI 在 payload 顶层加 `status`，`oneOf` 会因匹配多支而拒绝合法结果——值得在 specs 注释里作为升级注意点保留。

## 10.5 本地 0.1.1 vs 远端 `bc183fc`（0.1.0）差异清单

`node _scratch/compare-remote.mjs BiancaoAwa/dsh-firefight-mod-tools D:\deepseek-harness\WorkSpace\_scratch\ffplugin --ref bc183fc`
→ `remote files=23  local files=25  identical=16  only on remote: -- none --`

| 文件 | 类型 | 改动内容（`git diff --no-index`，远端 blob sha 见括号） |
| --- | --- | --- |
| `README.md` | 修改（`268ebbd9…`） | R2 `ff.py` 分支段（+4 行）；R3 `ff_find` 那句改错（N1）；新增 Disjoint shapes 段；R4 有界输出改写；R1 测试命令加目录不展开说明；R5 替身/真实测试说明 |
| `package.json` | 修改（`de949f3a…`） | `version` `0.1.0`→`0.1.1`；`scripts.test` `node --test test/` → `node --test "test/*.test.js"` |
| `cordis.patch.yml` | 修改（`484d1c9b…`） | `config:` 下新增 `cwd: ''`（8 键 → 9 键，F6） |
| `lib/specs.js` | 修改（`ade9a1f0…`） | 新增 `req()`；9 个 payload 分支各加 1 个判别式；导入 `ERROR_SCHEMA`；新增 `outputContract()`、`discriminatorOf()`；文件头补原理注释 |
| `lib/tools.js` | 修改（`b0d2354c…`） | `schema: { oneOf: [spec.output, ERROR_SCHEMA] }` → `schema: outputContract(spec)`（`ERROR_SCHEMA` 改由 specs 侧导入） |
| `test/harness-stub.js` | 修改（`6e7cc413…`） | 新增 `ALLOWED_KEYS` 白名单、`validateSpec` 的 `allowRequired` 语义、`validateValue` 的 `oneOf` 恰好一支 |
| `test/support.js` | 修改（`ffb68237…`） | `PAYLOADS.get.field` `weapon/name` → `name`（与"相对根元素的点分路径"说明对齐） |
| `test/output-schema.test.js` | **新增** | 66 行：对 `ALL_SPECS` 断言契约合法、每个 payload 恰好 1 个判别式、载荷/错误值各恰好命中一支、缺判别式被拒 |
| `test/real-harness.test.js` | **新增** | 60 行：可导入真实包时用真实 `defineTool` + `validateJsonSchemaValue`，否则 4 个用例带原因 skip |

未变（16 个，含关键安全面）：`lib/approval.js`、`lib/index.js`、`lib/call.js`、`lib/render.js`、`lib/runner.js`、`lib/config.js`、`pnpm-lock.yaml`、`LICENSE`、`.gitignore`、`test/approval.test.js`、`test/call.test.js`、`test/config.test.js`、`test/plugin.test.js`、`test/render.test.js`、`test/runner.test.js`、`test/specs.test.js`。

## 10.6 本轮复现命令

```powershell
$n='C:\Users\BC_aw\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
# 差异清单（本地 vs 远端 0.1.0）
& $n D:\deepseek-harness\WorkSpace\_scratch\compare-remote.mjs BiancaoAwa/dsh-firefight-mod-tools D:\deepseek-harness\WorkSpace\_scratch\ffplugin --ref bc183fc
# 远端快照 + 逐文件 diff（写入 _scratch/verify/remote-0100/）
& $n D:\deepseek-harness\WorkSpace\_scratch\verify\fetch-remote.mjs BiancaoAwa/dsh-firefight-mod-tools bc183fc D:\deepseek-harness\WorkSpace\_scratch\verify\remote-0100 README.md cordis.patch.yml package.json lib/specs.js lib/tools.js test/harness-stub.js test/support.js
git diff --no-index -- _scratch/verify/remote-0100/README.md _scratch/ffplugin/README.md
# 审批门重跑（结论：27/0/0，2 HAZARD，与首轮一致）
cd D:\deepseek-harness\WorkSpace\_scratch\verify; & $n gate-attack.mjs
# 测试与参数形态
cd D:\deepseek-harness\WorkSpace\_scratch\ffplugin
& $n --test --test-isolation=none "test/*.test.js"   # 56 tests, 52 pass, 0 fail, 4 skip
& $n --test --test-isolation=none                    # 58 tests, 54 pass, 0 fail, 4 skip（含 stub/support 文件）
& $n --test --test-isolation=none test/              # ✖ test, 1 test, 1 fail（目录不展开）
& $n -e "import('@deepseek-ai/dsh-tools').catch(e=>console.log(e.code,e.message.split('\n')[0]))"
# 真实 CLI 行为（find 无 selector）
cd D:\deepseek-harness\WorkSpace\_scratch\m3-cli
python ff.py Firefight find value=WEAPON_PISTOL_P38 limit=3 "root=D:\Program Files (x86)\Steam\steamapps\common\Firefight\Data" --json
python ff.py Firefight find limit=3 "root=D:\Program Files (x86)\Steam\steamapps\common\Firefight\Data" --json
```

## 10.7 给 Lead 的建议

1. **推送前必改**：README:70 的 `ff_find` 一句（N1）。
2. **可选**：README:108-109 补半句说明裸 `node --test` 也会加载 `test/harness-stub.js`、`test/support.js`。
3. 其余 5 项修复与输出契约改动我认为可以推送；审批门相关代码本轮零改动，重跑结论与首轮一致。
4. 真实 `defineTool` 路径的端到端验证要在 DSH profile 里做一次（本机因 `@deepseek-ai/cordis` 缺失无法执行）。

---

# 11. Follow-up verification（task-5，e2e 驱动的修复之后）

**对象**：本地工作树 `D:\deepseek-harness\WorkSpace\_scratch\ffplugin`（仍是 `0.1.1`，2016-10-10 02:30 前后的一批改动，未推送）；远端仍是 0.1.0 的 `bc183fc`。本节结论取代 §10.7 的推送建议。只读远端、只写本报告。

## 11.1 结论：是否仍阻断推送？

**是，有两处建议推送前修正**——都不是审批门或输出契约的正确性问题：

- **G1（功能回退，建议必修）**：`ff_deps` 的 `kind` 被删除，理由是"CLI 忽略它"——**不成立**。CLI 在 `cmd_deps` 里读取并应用 `kind`：`_scratch/m3-cli/cli/commands.py:420` `kind = ctx.options.get("kind")`、`:438` `if reference.value == value and (kind is None or reference.kind == kind)`。真机实测（stock 数据）：`python ff.py Firefight deps value=WEAPON_PISTOL_P38 root=<stock> --json` → `"count": 1204`；加 `kind=weapon` → `1204`；加 `kind=sound` → `0`；加 `kind=__none__` → `0`。另一组更干净的对照（sound 类 token，避免"恰好全是 weapon"的歧义）：`deps value=shoot_at_rifle` → `12`，`+kind=sound` → `12`，`+kind=weapon` → `0`；`refs kind=sound limit=1` 返回 `by_kind={"sound":954}`。删掉后 0.1.1 比远端 0.1.0 **少一个可用过滤器**（远程 0.1.0 的 spec 里 `kind` 是有的，见 `_scratch/verify/remote-0100/lib/specs.js:288,295`）。修法：把 `kind` 加回 `lib/specs.js` 的 `ff_deps.parameters` 与 `build()`，README 工具表补回。
- **G2（本轮新增文本不准确，建议必修）**：README:77-80 与 `lib/specs.js:202` 在说明 `=` 缺口时建议"rename such a folder or read it with `ff_show`"。**`ff_show` 不是替代路径**：含 `=` 的 selector 同样被 CLI 当成 `key=value` 吃掉，实测 `python ff.py Firefight show "Data/Weapons/eq=1.txt" root=<stock> --json` → exit 2，stderr `expected one file, got 1840; name the file explicitly`（空 selector 落到整个 scope，`single_document` 才报"expected one file"）。建议改成"这样的文件无法通过 CLI 定位，只能改名"。（`ff_list` 那半句"silently widens the listing"是对的：`python ff.py Firefight list "Data/eq=1" root=<stock> --json` → `"count": 1840`、exit 0。）

其余全部成立：新的 `ff_show` 子树契约与真实 CLI 一致、9 行 README 工具表与 spec 逐项一致、测试 58/54/0/4、审批门逐字节未动且对抗结论不变。

## 11.2 逐条核实（task-5 提到的 5 处 + Lead 追加的 3 处）

| 声明 | 判定 | 证据（本地文件 : 行） |
| --- | --- | --- |
| README 的 `ff_find` 改成"至少要给 tag/value/path 之一，否则 CLI 报 usage 错误；不给 selector 就搜整个 scope" | **成立** | `README.md:70`；CLI `_scratch/m3-cli/cli/commands.py:273-274`（三个都为 None → `UsageError("nothing to search for; pass tag=<name>, value=<text> or path=<a/b>")`）、`:70-75`（空 selector → `entity_files(ctx.scope)`）；实测见 §10.4 N1 的两条命令 |
| 因 CLI 忽略，`ff_list`/`ff_export` 去掉 `limit` | **成立（无功能损失）** | `lib/specs.js:200-206`（参数无 `limit`）、`:210 build`（options 无 limit）；`:332-338`/`:342`（export 同）。CLI 里 `limit` 只在 `cmd_find` 被读（`cli/commands.py:272,298,313` 是 find 内），list/export 从不读 |
| `ff_deps` 去掉 `kind` | **不成立 → G1** | `lib/specs.js:299-304`、`:308 build`；CLI 证据见 §11.1 |
| `ff_show` 声明并渲染子树 payload（`key`/`count`/`values`） | **成立** | 声明：`lib/specs.js:76-86`（`key`:82、`count`:83、`values`:84，均 `required: false`，判别式仍是 `path`:77）；CLI 形状：`cli/commands.py:189-217 _show_subtree`，raw → `{"path","key","count","values"}`（`:214-215`）、`as=xml` → `{"path","key","count","xml"}`（`:206`）、`as=toml` → `{"path","key","toml"}`（`:200`）；渲染：`lib/render.js:100-105` |
| README 新增 `=` 缺口段落 | **半成立 → G2** | `README.md:77-80`；解析证据 `cli/main.py:75-77`（任何含 `=` 且不以 `-` 开头的 token 变成 option）；实测见 §11.1 |
| 新增两条子树测试 + 夹具 | **成立** | `test/render.test.js:46-50`（断言 `WEAPON_PISTOL_P38.txt weapon/ammo · 2 elements · 2 values` 与 `weapon/ammo/type/name:23 = 9x19mm Parabellum`）、`test/output-schema.test.js:43-48`、夹具 `test/support.js:56-64 PAYLOADS.showSubtree` |
| 追加①：`renderShow` 子树抬头改成 `path key · N element(s) · M value(s)` | **成立** | `lib/render.js:101` `` [`${value.path} ${value.key ?? ''} · ${plural(value.count ?? 0, 'element')} · ${plural(value.values.length, 'value')}`] ``，与测试断言一致 |
| 追加②：`SHOW_OUTPUT.count` 描述改成"Number of elements the subtree selector matched" | **成立** | `lib/specs.js:83` |
| 追加③：README Bounded output 改成"`ff_show` prints a whole document in full but caps a subtree at 100 values" | **成立** | `README.md:97-99`；`lib/render.js:76 rows()` 的 `ROW_LIMIT=100`（`:10`）确实作用于子树分支 `:102`；整篇文档分支 `:106-107` 不截断 |

## 11.3 README 表格 vs 代码（本轮重做）

- **工具表 9 行的参数集合与 `lib/specs.js` 完全一致**（脚本按行解析 README:67-75 与 `ALL_SPECS`，忽略正文说明的 `scope`/`root`/`workspace`）：`ff_list`=[selector,type]、`ff_show`=[selector,as]、`ff_get`=[selector,field]、`ff_find`=[selector,tag,value,path,ignoreCase,limit]、`ff_stats`=[selector]、`ff_refs`=[selector,kind]、`ff_deps`=[value]、`ff_check`=[selector]、`ff_export`=[selector,to]。
- **required 标记一致**：`ff_show.selector`（`lib/specs.js:218`）、`ff_get.selector`（`:234`）、`ff_refs.selector`（`:285`）、`ff_deps.value`（`:301`）、`ff_export.to`（`:335`）——与 README 的 `(required)` 逐项相同。
- **`as` 枚举**：README:68 的 `raw|toml|xml` = `lib/specs.js:219`。
- **配置表 9 键 + 默认值**：三源一致（脚本比对输出 `equal: true true`）——`lib/config.js` = `cordis.patch.yml`（含补回的 `cwd: ''`）= README:49-57，键序都是 `pythonPath, editorRoot, scriptPath, firefightRoot, workspace, cwd, timeoutMs, maxOutputChars, enableExport`，默认值 `''`×6 / `60000` / `40000` / `false`。
- **判定式枚举**：README:92-93 的 `scope`（7 个）/`path`（ff_show、ff_get）/`count`（ff_find）与 `discriminatorOf()` 实际结果一致。
- **唯一表级缺口**：G1——CLI 接受 `deps … kind=`，而表格与 spec 都不再暴露它。
- 顺带确认 README:67 "selector 是目录前缀，不是子串"属实：`cli/scope.py:220` `return [path for path in files if _relative(scope, path).startswith(selector.strip("/"))]`。

## 11.4 审批门：零改动，重跑结论不变

- `lib/approval.js` **不在**本轮差异清单里（与远端 0.1.0 逐字节相同）；`lib/index.js`、`lib/call.js`、`lib/runner.js`、`lib/config.js` 同样未变。
- 重跑 `_scratch/verify/gate-attack.mjs`（对手树是当前 0.1.1）→ exit 0，`cases=27 invariantFailures=0 bypasses=0 hazards=2`，两项 HAZARD 与首轮/第二轮完全相同：B4（`exec`/`name` 缺失落入 `next()` 的 fail-open 形状，因宿主 `ToolExecutionInput.name` 必填而不可达）、C3（更早注册的宽松 `tools/pre-execute` 监听器短路门）。`attack-out.txt` 已随本次重跑更新。
- 测试：`node --test --test-isolation=none "test/*.test.js"` → `tests 58 pass 54 fail 0 skipped 4`（`test/render.test.js` 与 `test/output-schema.test.js` 各新增一条子树用例，故 56 → 58）；4 个 skip 仍全部来自 `test/real-harness.test.js`（`@deepseek-ai/cordis` 缺失）。

## 11.5 差异清单更新（本地 0.1.1 vs 远端 0.1.0 `bc183fc`）

`node _scratch/compare-remote.mjs BiancaoAwa/dsh-firefight-mod-tools D:\deepseek-harness\WorkSpace\_scratch\ffplugin --ref bc183fc`
→ `remote files=23  local files=25  identical=13  only on remote: -- none --`

**修改 10**：`README.md`、`cordis.patch.yml`、`lib/render.js`、`lib/specs.js`、`lib/tools.js`、`package.json`、`test/harness-stub.js`、`test/plugin.test.js`、`test/render.test.js`、`test/support.js`
**新增 2**：`test/output-schema.test.js`、`test/real-harness.test.js`
**未变 13**：`lib/approval.js`、`lib/index.js`、`lib/call.js`、`lib/runner.js`、`lib/config.js`、`pnpm-lock.yaml`、`LICENSE`、`.gitignore`、`test/approval.test.js`、`test/call.test.js`、`test/config.test.js`、`test/runner.test.js`、`test/specs.test.js`

本轮相对 §10.5 新进入差异集的三个文件及其 delta：

| 文件 | 本轮新增的改动 |
| --- | --- |
| `lib/render.js` | `renderShow` 增子树分支（本地 `:100-105`）；0.1.0 版本只有整篇文档分支 |
| `test/render.test.js` | 增子树渲染用例（本地 `:46-50`） |
| `test/plugin.test.js` | ff_list 的 options 断言去掉 `limit: undefined`（远端版本该行是 `{ root: undefined, workspace: undefined, type: undefined, limit: undefined }`）；改用 `outputContract(specOf(...))` + 可选真实 `validateJsonSchemaValue` 双重校验（本地 `:91-107`） |

`lib/specs.js` 与 `README.md` 的 delta 也在本轮扩大：前者删了 `ff_list`/`ff_export` 的 `limit` 与 `ff_deps` 的 `kind`、补了 `SHOW_OUTPUT.key/count/values`；后者改了 `ff_find` 一句、新增 `=` 段落与子树说明、改写 Bounded output。

## 11.6 其它观察（均非阻断）

- README:15 的 Python 版本声明与 README:110 的 `pnpm install --config.auto-install-peers=false` 仍是**无法判定**项（§8 U1/U2，本机只有 Python 3.14.5、无写权限装依赖）。
- 真实 `defineTool`/真实校验器路径在本机仍不可执行（`ERR_MODULE_NOT_FOUND: @deepseek-ai/cordis`），`test/real-harness.test.js` 的 4 个用例 100% skip；端到端验证需在 DSH profile 里做一次。
- 本轮我**没有**修改 `_scratch/ffplugin/lib/`、`test/`（发现缺陷只报告，见 §11.1 G1/G2）。

---

# 12. G1/G2 fixed（task-6 复核）

**结论：没有剩余阻断项。** §11.1 提出的两处问题都已修复并经独立复核；就我负责的范围（字节一致性、文档声明、审批门、输出契约形状）而言，**0.1.1 可以推送到 `main`**。§11.6 的两项"无法判定"（Python 版本声明、pnpm 安装说明）与 §11.4 的两项宿主语义 HAZARD（B4/C3）依旧存在，但它们不是本轮引入的、也不由本次修改解决。

## 12.1 G1（`ff_deps.kind`）已修复合核

- 声明恢复：`lib/specs.js:302 kind: KIND`，`KIND` 定义在 `:39` `str('Reference kind filter, for example weapon or sound.')`；`:309 build` 里 `options: { ...baseOptions(args, config), value: args.value, kind: args.kind }`。
- 参数集合与必填复核（脚本直读 spec）：`ff_deps` = `scope, value, kind, root, workspace`，required 只有 `value`；`kind` 由 `ff_refs`+`ff_deps` 共同保留（脚本输出 `kind kept by : ff_refs, ff_deps`）。
- argv 复算（`build` + `buildArgs`，config `{scriptPath: 'ff.py', firefightRoot: 'R', ...}`，args `{scope:'Firefight', value:'shoot_at_rifle', kind:'sound'}`）：
  `call = {"scope":"Firefight","command":"deps","options":{"root":"R","workspace":"","value":"shoot_at_rifle","kind":"sound"}}`
  `argv = ["ff.py","Firefight","deps","root=R","value=shoot_at_rifle","kind=sound","--json"]` —— 与 Lead 自测一致，`kind=sound` 重新出现在 argv 里。
- README:73 已恢复：``| `ff_deps` | `value` (required), `kind` | Incoming references of a token, plus the entities it resolves to; `kind` narrows them to one reference kind. Check this before renaming or deleting. |``
- 该修复的正确性依据仍是 §11.1 的实测：`deps value=shoot_at_rifle` → 12、`+kind=sound` → 12、`+kind=weapon` → 0（CLI `cli/commands.py:420,438`）。

## 12.2 G2（`=` 选择器的建议）已修复合核

- `lib/specs.js:202`（`ff_list` 的 selector 描述）现在结尾是 `… silently widens the listing; rename such a folder.` —— 删掉了 `ff_show` 替代路径。
- `README.md:77-80` 现在是：`The CLI reads `key=value` arguments positionally, so a selector that itself contains `=` (a folder named `eq=file.toml`) is taken as an option and the call silently widens to the whole scope; rename such a folder. `limit` is only honoured by `ff_find`.` —— 只剩"改名"这一条真补救。
- 全树 grep `ff_show`（`*.js`/`*.md`）12 处，全部是工具本身的说明/测试/渲染注释，**没有任何一处再把 `ff_show` 当作 `=` 选择器的出路**。
- "silently widens" 那一半仍与 CLI 实测一致（`list "Data/eq=1"` → count 1840、exit 0）；`show "Data/Weapons/eq=1.txt"` → exit 2 `expected one file, got 1840` 的反例已在 §11.1 记录。

## 12.3 保留项复核（未回退）

- `limit` 仍只被 `ff_find` 保留（脚本输出 `limit kept by : ff_find`；`ff_list` 参数 = `scope, selector, type, root, workspace`），README:79-80 的说明与之一致。
- `ff_show` 子树契约与渲染未动：`lib/specs.js:76-86`（`key`/`count`/`values`，`:83 count` 描述仍是 "Number of elements the subtree selector matched"）、`lib/render.js:100-105` 子树分支与 `${path} ${key} · N element(s) · M value(s)` 抬头、`test/render.test.js:46-50` 断言、`test/output-schema.test.js:43-48` + `test/support.js:56-64` 夹具。
- README vs 代码再次逐表核对：9 个工具的参数集合与 required 标记全部一致（含本轮的 `ff_deps` 行），配置 9 键三源一致，`as` 枚举、判别式枚举、`ff_show` 子树说明均无变化。

## 12.4 门与测试重跑

- `lib/approval.js` 仍与远端 0.1.0 逐字节相同（差异清单里没有它，也没有 `lib/index.js`/`call.js`/`runner.js`/`config.js`）。
- `node _scratch/verify/gate-attack.mjs` → exit 0，`cases=27 invariantFailures=0 bypasses=0 hazards=2`，两项 HAZARD 仍是 B4（不可达的 fail-open 形状）与 C3（更早注册的宽松监听器短路门），与前三轮完全一致；`attack-out.txt` 已更新。
- `node --test --test-isolation=none "test/*.test.js"` → `tests 58 / pass 54 / fail 0 / skipped 4`（skip 全部来自 `test/real-harness.test.js`，缺 `@deepseek-ai/cordis`）。
- 差异清单（`compare-remote.mjs` vs `bc183fc`）文件集合与 §11.5 完全相同：`identical 13 / only-remote none / differing 10 / only-local 2`（`test/output-schema.test.js`、`test/real-harness.test.js`）。

## 12.5 仍不准确 / 无法判定

- **无法判定（沿用 §8 U1/U2）**：README:15 的 Python 版本声明、README:110 的 `pnpm install --config.auto-install-peers=false`（本机 Python 3.14.5、无写权限装依赖）。
- **无新的文档-代码不符**：本轮复核没有再发现 README 或 `lib/specs.js` 描述与代码/CLI 矛盾之处。
- 需要明确写进推送说明（而非缺陷）：`ff_export` 门的存在依赖 `tools/pre-execute` 的调用顺序（C3），以及真实 `defineTool`/真实校验器路径在 DSH profile 里才能端到端验证。

---

**写入范围声明**：除本文档与 `_scratch/verify/gate-attack.mjs` 外，我在 `_scratch/verify/` 下新增/改写了这些文件，均在此显式披露：`attack-out.txt`（`gate-attack.mjs` 完整原始输出，本轮已用当前 0.1.1 工作树重生成）、`fetch-remote.mjs`（只读快照助手）、`remote-0100/`（远端 `bc183fc` 的 7 个差异文件字节快照，用于 `git diff --no-index`；本节另需的远端 `test/plugin.test.js`、`test/render.test.js` 改用只读的 `gh_file` 工具获取，未落盘）。task-5、task-6 两节均未新增任何文件。插件仓库的 `lib/`、`test/`、`README.md` 与远端均未被修改；远端无任何写操作（无 push/PR/merge）。
