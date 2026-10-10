# 验算 A：`dsh-firefight-mod-tools` 与真实 dsh-tools / cordis 契约

> **路径说明（2026-10-11 补记）**：本报告写于工程目录搬迁之前，正文里的 `_scratch\ffplugin`、`_scratch\verify`、`_scratch\m3-cli` 现位于 `D:\deepseek-harness\WorkSpace\firefight-mod-editor-open\` 下同名目录。正文为当时事实，未改写。**再补记（同日第二次整理）**：本报告所在目录已由 `firefight-mod-editor-open\verify\` 挪到 `firefight-mod-editor-open\docs\verify\`，`ffplugin\`、`m3-cli\` 位置不变。

- 对象：私有仓库 `BiancaoAwa/dsh-firefight-mod-tools@bc183fc`，本地工作树 `D:\deepseek-harness\WorkSpace\_scratch\ffplugin`
- 真实类型：`_scratch\ffplugin\node_modules\@deepseek-ai\dsh-tools\lib\types\*.d.ts`（0.2.1-alpha.1，含 `schema.d.ts`）
- 真实实现：`_scratch\ffplugin\node_modules\@deepseek-ai\dsh-tools\lib\index.js`（158002 B，与 `.d.ts` 同包）
- cordis 真实实现（从本机 pnpm store 内容寻址库定位到 cordis@4.0.5-alpha.1 的 `lib/index.js`）：
  `D:\deepseek-harness\WorkSpace\.pnpm-store\v11\files\0d\338475427fd14312da510c87704c5b049d6ac1473444257294a4eb7731ede9cad7d50f1fd8021e6d3ec58e8027467d417d3fa00c83388d3775a493e6b2e485`
- 判定三态：成立 / 不成立 / 无法判定。本报告只写这一个文件，未改 lib/、test/，未推送。

---

## 0. 结论先行

1. **注册契约本身成立**：9 个工具的定义在**真实 `defineTool`**（真 bundle，非替身）下全部编译通过；9 个真实 CLI payload 全部通过**真实 `validateJsonSchemaValue`**；参数 `required` 标注与真实 `validateArgs` 一致；approval gate 的 `ctx.on('tools/pre-execute', …)` 与 `PreToolDecision`/cordis waterfall 语义一致；`ctx.effect` / `ctx.tools.register` 的 disposer 用法正确。
2. **一个真实宿主可见的功能缺陷（高）**：真实 output 校验要求 `oneOf` **恰好命中一个**分支，而 payload 分支是"全可选 + `additionalProperties:true`"的开放对象，**错误值同时命中两个分支**。插件在 CLI 失败时把 `errorValue(...)` 当正常返回值返回，真实 registry 会因此抛 `ToolOutputError`——模型拿不到结构化 `code/guidance`。46 条单测看不到，因为替身的 `oneOf` 是"任一分支命中即可"。
3. **替身与真实确有偏差**（决定 46 条单测的证明力）：替身在 3 处**偏松**（oneOf 语义、schema 节点未知关键字、嵌套 `required`）、2 处**偏严**（未知 option 键、name 格式），另有 2 处更严的私有规则（`description` 非空、`execute` 存在）。用真 bundle 实测后，payload 侧全部通过，唯一被真实校验器拒绝的是 errorValue 分支歧义。
4. **端到端（真实宿主装配）无法判定**：本机没有 cordis 及其它 peer，`import('@deepseek-ai/dsh-tools')` 必然失败，`test/plugin.test.js` 的"真实包优先"分支在本机是死代码；我用 node loader hook 在内存里注入了 6 个 peer 替身才跑起真 bundle，因此**只证明 schema/定义编译契约，不证明 registry/fiber/审批端到端**。

---

## 1. 结论表

| # | 断言 | 证据（命令 + 关键原始行） | 判定 | 影响（是否让验证过度自信） |
|---|---|---|---|---|
| A1 | 真实 `defineTool` 接受全部 9 个工具定义（含 `output.schema = {oneOf:[payload, ERROR_SCHEMA]}`） | `REAL-DEFINETOOL-ACCEPTED count=9 names=ff_list,…,ff_export`（loader-hook 脚本，真 bundle `lib/index.js`） | 成立 | 消除"未在真实 harness 下注册过"的主要疑虑 |
| A2 | 9 个真实 payload 全部通过真实 output 校验 | `REAL-VALIDATE ff_list key=list payload=[] … ff_export key=export payload=[]`（9/9 空违规） | 成立 | 输出契约成立 |
| A3 | `errorValue(...)` 通过真实 output 校验 | `REAL-VALIDATE … errorValue=["\"value\" must match exactly one oneOf branch (matched 2)"]`（9/9） | **不成立** | **高**：单测以为错误分支被覆盖，真实宿主会抛 `ToolOutputError` |
| A4 | 参数 schema 与真实 `validateArgs` 一致 | `ARGS ff_show sample=["missing required property \"selector\""]`；`ff_export … "to"`；`ARGS badtype=["\"scope\" must be a string"]`；`ARGS unknownKey=[]` | 成立 | 无 |
| A5 | `isConcurrencySafe` 语义正确 | `ISCONCURRENTSAFE ff_list=true ff_export=false`（真实包装器对非法 args 返回 false，`lib/index.js:882-885`） | 成立 | 无 |
| A6 | 未声明 `timeoutMs` 无注册期隐患 | 真实 jsdoc `index.d.ts:152-157` "Omit for no deadline"；`defineTool` 仅在显式给出时校验 `lib/index.js:847`；`TIMEOUTMS ff_list=undefined` | 成立 | 无；但宿主超时策略不会介入（插件自管 CLI 超时） |
| A7 | 替身的 `ALLOWED_OPTIONS` 与真实 `DefineToolOptions` 键一致 | 替身 `harness-stub.js:12-15` vs `schema.d.ts:178-240`（name/description/parameters/output/deferLoading/timeoutMs/isConcurrencySafe/execute/projectContent/finalizeContent/presentCall/presentResult） | 成立 | 无（多一个 key 会被替身拒绝，方向安全） |
| A8 | `object` 必须显式声明 `additionalProperties`：替身 = 真实 | 真实 `schema.d.ts:58-62`（`additionalProperties: boolean` 必填）、实现 `lib/index.js:699` `authorError('… must be explicitly true or false')`；替身 `harness-stub.js:38-39` | 成立 | 无 |
| A9 | `oneOf` 至少 2 分支：替身 = 真实 | 真实 `schema.d.ts:68-70` 元组 `[V,V,...V[]]`、raw 校验 `lib/index.js:227` "must be an array of at least two schemas"；替身 `harness-stub.js:30-31` | 成立 | 无 |
| A10 | `required` 只能是 `true` 且只在参数属性上：替身**部分**忠实 | 真实 `schema.d.ts:73-76` `ParameterPropertySpec = ValueSchemaSpec & { required?: true }`；实现用 `allowRequired` 门控 `lib/index.js:655`；替身只在参数根检查 `harness-stub.js:121-122`，对 object `properties` 下的 `required` 完全不校验 | 部分成立（替身偏松） | 中：新增嵌套 `required` 写法不会被单测发现 |
| A11 | schema 节点未知关键字：替身比真实**松** | 真实 `assertAuthorKeys` 拒绝未知键（错误文案见 `lib/index.js:206` `is not a supported keyword (subset: …)`），并校验 `title`/`description` 类型与注解 lossless（`lib/index.js:199-209`）；替身只认 `description`/`oneOf`/`type` 等少数键，未知键直接忽略（`harness-stub.js:21-47`） | 成立（存在偏差） | 中：替身经不起"真实也会拒绝"的推断 |
| A12 | `defineTool` 未知 option：替身比真实**严** | 真实只读已知键、忽略其余（`lib/index.js:838-887`）；替身 `throw new TypeError('defineTool received an unknown option: …')`（`harness-stub.js:108-111`） | 成立（存在偏差） | 低：方向安全（会误杀而不会放过） |
| A13 | 替身的 `oneOf` 值校验 = "任一分支命中" | 替身 `harness-stub.js:51-53` `branches.some(problems => problems.length === 0)`；真实 `lib/index.js:418-419` `frame.matches === 1 ? [] : ['… must match exactly one oneOf branch (matched N)']` | **不成立** | **高**：与 A3 同源，是单测漏检的直接原因 |
| A14 | 真实 registry 会校验 execute 返回值并抛错 | `lib/index.js:3541-3544` `createSuccessResult`：`validateJsonSchemaValue(tool.output.schema, detached, "value")` → `throw new ToolOutputError(tool.name, violations)`；`ToolOutputError` 定义 `lib/index.js:2550-2555` | 成立 | 决定 A3 的严重度 |
| A15 | 插件在 CLI 失败时**返回**（而非抛出）错误值 | `lib/call.js:48` `return errorValue('cancelled', …)`；`:50` timeout；`:57` empty-output；`:59` `return errorValue(result.code === 2 ? 'usage' : 'cli-error', …)` | 成立 | A3 因此在真实宿主可达 |
| A16 | `ctx.on('tools/pre-execute', async (exec, next) => …)` 是正确的注册方式与签名 | 真实事件签名 `index.d.ts:47`（waterfall，`(exec, next) → Promise<PreToolDecision>`）；dsh-tools 用 `this.ctx.waterfall(carrier, 'tools/pre-execute', exec, () => Promise.resolve({ kind: 'allow' }))`（`lib/index.js:876`）；cordis `dispatch` 读同一 `_hooks` 表（cordis blob `:258-264`）、`waterfall` 组装 `next`（`:317-325`）、`on` 写入该表并返回 disposer（`:371-380`） | 成立 | 无 |
| A17 | `{ kind:'ask', reason }` 合法 | `index.d.ts:445-460`：`{ kind:'ask'; reason?: string; displayReason?: {en, …} }`；返回 `ask` 时**不调用 `next()`** 即短路后续 waterfall，符合 cordis 文档 `:310-312`"a listener that does not call `next()` vetoes the rest of the chain" | 成立 | 无 |
| A18 | 审批存在旁路（exec 为 undefined / 名称别名 / 吞掉 next） | `exec?.name !== 'ff_export' ? next() : {kind:'ask'}`（`lib/approval.js:21-25`）；真实 `ToolExecutionInput.name: string`（`index.d.ts:223`）且分发按注册名精确解析（`lib/index.js:3519` `resolveExecution(exec.name, …)`）。exec 为 undefined 时放行的是**别的**工具，ff_export 执行时 exec 必带 name；无别名机制 | 不成立（未发现旁路） | 无 |
| A19 | gate 注册条件与工具注册条件一致 | `lib/index.js:34-35` 仅 `enableExport === true` 时 `ctx.effect(() => registerExportGate(ctx))`；`lib/tools.js:23-25` 同条件才加 `EXPORT_SPEC` | 成立 | 无 |
| A20 | `ctx.effect(fn)` 要求返回 disposer：插件两处都满足 | cordis blob `:1138-1140` `if (typeof dispose === 'function') runner.collect(dispose); else if (!isNullable(dispose)) throw new TypeError('Invalid effect')`；`lib/index.js:27-33` 返回闭包；`:35` 返回 `ctx.on` 的 disposer（cordis `:379` `return this.register(...)`，`:337-344` 返回 `() => this.unregister(...)`） | 成立 | 无 |
| A21 | 9 个工具反向注销写法无 bug | `lib/index.js:28-32`：`map(...)` 结果数组是新建的，`undo.reverse()` 不污染外部；`ctx.tools.register` 契约 `index.d.ts:636` "returns the exact disposer that unregisters the tool" | 成立 | 无 |
| A22 | `name` / `inject=['tools']` / `apply(ctx, config)` 符合 cordis 插件形态 | cordis blob `:1446-1447` `isApplicable(object)` = `typeof object.apply === 'function'`；`:1625-1635` 读取 `plugin.name` / `plugin.Config` / `plugin.inject`；`:956-958` `resolveConfig` 用 `runtime.Config['~standard'].validate(config)`；插件 `lib/index.js:14-15,38-40` 与之匹配，`lib/config.js:7` 的 `Config` 是 `Schema.object({...})` | 成立 | 无 |
| A23 | 真实 peer 在本机不可安装，"真实包优先"分支是死代码 | `node -e "import('@deepseek-ai/dsh-tools')…"` → `IMPORT-FAIL ERR_MODULE_NOT_FOUND \| Cannot find package '@deepseek-ai/cordis' imported from …dsh-tools\lib\index.js`；`node_modules\@deepseek-ai` 下只有 `cosmokit, dsh-tools, schemastery`（`cordis NO`）；`test/plugin.test.js:16-26` try/catch 永远落到 `stub.defineTool` | 成立 | **高**：46 条单测的证明力 100% 依赖替身 |
| A24 | 46 条单测当前全绿 | `node --test --test-isolation=none approval.test.js call.test.js config.test.js plugin.test.js render.test.js runner.test.js specs.test.js` → `tests 46 / pass 46 / fail 0`（cwd=`…\ffplugin\test`） | 成立 | 基线成立；但见 A23/A13 |
| A25 | 真实 `render` 投影契约（`ContentBlock[]`）成立 | `lib/render.js:44-46` `textBlock` → `[{ type:'text', text }]`；真实 `index.d.ts:110` `render(args, value): ContentBlock[]`；`lib/index.js:3548-3552` 调用并要求投影可 lossless 快照 | 成立（静态） | 低：替身只检查 `render` 的 arity，不检查返回类型/内容 |

---

## 2. 重点发现（按严重度）

### F1（高）错误值在真实 output 校验下必然失败 → CLI 失败路径退化为 `ToolOutputError`
- 机制：每个工具 `output.schema = { oneOf: [ <payload>, ERROR_SCHEMA ] }`（`lib/tools.js:40`）。payload 分支由 `obj(...)` 生成，即 `{type:'object', additionalProperties:true, properties:{…}}`（`lib/specs.js:23`、`:53-152`），**没有任何 `required`**，因此它对任意对象都成立；`ERROR_SCHEMA`（`lib/render.js:13-23`）也接受错误对象 → 两个分支同时命中。
- 真实校验器要求**恰好一个**分支：`lib/index.js:418-419`。
- 真实 registry 在成功路径上校验返回值：`lib/index.js:3543-3544` → `ToolOutputError`。
- 插件在 CLI 失败时返回错误值：`lib/call.js:48,50,57,59`。
- 实测（真 bundle）：
  ```
  REAL-VALIDATE ff_list key=list payload=[] errorValue=["\"value\" must match exactly one oneOf branch (matched 2)"]
  … 9/9 同样的 errorValue 违规，payload 全部为 []
  ```
- 替身为何漏检：`harness-stub.js:51-53` 用 `branches.some(...)`（任一命中即通过），与真实 `matches === 1` 相反（A13）。
- 影响：真实宿主里 CLI 超时/取消/空输出/退出码非 0 时，模型收到的是 output 校验失败，而不是插件设计的 `{status:'error', code, message, guidance, detail}`；`code` 与 `guidance` 丢失。失败仍然可见（fail-closed），不是静默错误，但插件最核心的错误契约在真实宿主中不生效。
- 复核命令：见 §4 脚本 + `REAL-VALIDATE` 输出。

### F2（中）替身在 3 处偏松，削弱 46 条单测的证明力
- oneOf 语义（A13）、schema 节点未知关键字与注解类型校验（A11）、嵌套 `required` 非 `true` 不检查（A10）。
- 影响：任何"真实宿主会拒绝、替身放行"的新写法都不会被现有单测拦住；反之 A3 这种"替身放行、真实拒绝"的场景已经真实发生。

### F3（中）替身在 2 处偏严（方向安全，但不可当作真实行为推断）
- 未知 option 键直接抛错（A12，真实忽略）；`name` 强制 `^[a-z][a-z0-9_]*$`、`description` 非空、`output.render` arity≥2（`harness-stub.js:112-130`，真实 `defineTool` 无这些检查）。
- 影响：通过 ≠ 真实通过；失败 ≠ 真实失败。当前插件未触及这些差异，故无实际风险。

### F4（信息）"真实包优先"在本机是死代码
- A23 的 import 失败与 `node_modules` 内容证明：`test/plugin.test.js:24` 的 `host?.defineTool ?? stub.defineTool` 永远取替身；`harness-stub.js:3-9` 自述"contract-faithful stand-in"是当前唯一的契约证据来源。

### F5（信息）已用真 bundle 做的补强验证
- 通过 node `module.registerHooks`（data: URL，无文件写入）为 6 个缺失 peer 注入最小替身，真实加载 `.pnpm` 里的 dsh-tools `lib/index.js`（`exportCount=23`），并直接调用真实 `defineTool` / `validateJsonSchemaValue` / `validateArgs`。`defineTool` 与 schema 编译器没有任何 peer 调用，因此 A1/A2/A3/A4 是**真实实现**的结果；peer 替身只影响本报告未断言的 registry/fiber/审批路径。

---

## 3. 无法判定

| 条目 | 为什么无法判定 | 需要什么才能判定 |
|---|---|---|
| U1 真实宿主端到端装配（`ctx.plugin(plugin)` → fiber → `ctx.tools` 注入 → 真实 approval 服务把 `ask` 变成暂停/拒绝） | 本机装不上 `@deepseek-ai/cordis` 等 peer；本报告只能真实执行 dsh-tools bundle 的纯函数路径（其 peer 由我 stub） | 在能安装 peer 的真实 DSH 宿主里加载一次插件 |
| U2 `tools/pre-execute` 的 ask 在真实 approval 服务下的最终行为（是否暂停、无审批通道时是否 fail-closed） | 上述 peer 缺失；类型注释 `index.d.ts:37-47` 说"missing approval support turns `ask` into denial"，但这是声明而非本机可实测的行为 | 同上 |
| U3 真实宿主对插件 `Config`（schemastery）的合并/校验细节 | cordis `resolveConfig` 依赖 `@standard-schema/spec` 的 `~standard` 通道与真实 `Config` 实例；本机无法装配完整 peer | 同上 |
| U4 `node --test test/` 的默认（多进程）运行 | 沙箱拒绝 piped stdio 的 `spawn`：`Error: spawn EPERM … errno: -4048`（这是文档化的沙箱边界，不是插件缺陷）；改用 `--test-isolation=none` + 显式文件列表后才得到 46/46 | 若必须用默认模式，需 Lead 提权/换非管道 stdio |
| U5 `render` 投影在真实 registry 里的 lossless 快照 | 需真实 `dsh-util-values.snapshotProjection`（本机为 stub）；静态看 `[{type:'text',text}]` 是合法 `ContentBlock[]` | 真实宿主端到端 |

未被沙箱拦下、无需提权的命令：`node --import <data-url loader> --input-type=module -e …`（全部脚本均如此运行）。

---

## 4. 复核方法（可复制）

环境：node = `C:\Users\BC_aw\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe`（v24.21.0）。以下均为**只读**执行，脚本经 `-e` / data: URL 传入，不落盘。

1. 真实 peer 是否可解析：
   `cd _scratch\ffplugin; node -e "import('@deepseek-ai/dsh-tools').then(m=>console.log('IMPORT-OK',Object.keys(m).join(','))).catch(e=>console.log('IMPORT-FAIL',e.code,'|',e.message))"`
   → `IMPORT-FAIL ERR_MODULE_NOT_FOUND | Cannot find package '@deepseek-ai/cordis' imported from …\dsh-tools\lib\index.js`
   `Get-ChildItem node_modules\@deepseek-ai` → `cosmokit, dsh-tools, schemastery`

2. 单测基线（绕开 spawn EPERM）：
   `cd _scratch\ffplugin\test; node --test --test-isolation=none approval.test.js call.test.js config.test.js plugin.test.js render.test.js runner.test.js specs.test.js`
   → `tests 46 / pass 46 / fail 0`

3. 真 bundle + 真 `defineTool` / 真校验器（关键实验）。`--import` 的 data: URL 里 `registerHooks` 把 6 个缺失 peer 映射到内存内最小替身（cordis/dsh-scope/dsh-llm/dsh-sandbox/dsh-util-values/dsh-brand），随后：
   ```js
   const dt = await import('file:///D:/deepseek-harness/WorkSpace/_scratch/ffplugin/node_modules/@deepseek-ai/dsh-tools/lib/index.js');
   const { createTools } = await import('file:///D:/…/lib/tools.js');
   const { PAYLOADS } = await import('file:///D:/…/test/support.js');
   const tools = createTools({ config: {…, enableExport: true}, run }, dt.defineTool);
   dt.validateJsonSchemaValue(tool.output.schema, PAYLOADS[tool.name.replace(/^ff_/,'')], 'value'); // payload → []
   dt.validateJsonSchemaValue(tool.output.schema, errorValue('usage','bad option','run ff help'), 'value'); // → matched 2
   dt.validateArgs(spec.parameters, args);
   ```
   注意 `test/support.js` 的 `PAYLOADS` 键是 `list/show/…`（无 `ff_` 前缀，`test/support.js:45-110`）；用 `PAYLOADS[tool.name]` 会得到 `undefined` 并产生"matched 0"的假象（我第一轮脚本就是这样，已修正）。
   → `REAL-DEFINETOOL-ACCEPTED count=9`、`REAL-VALIDATE … payload=[]`、`errorValue=["\"value\" must match exactly one oneOf branch (matched 2)"]`

4. cordis 语义：读 §0 给出的 store blob（内容寻址路径即 cordis `lib/index.js`）。
   定位方法：`.pnpm-store\v11\index.db` 的 `package_index` 表里 `key='sha512-…\t@deepseek-ai/cordis@4.0.5-alpha.1'`，其二进制 data 段以 `文件路径 + sha512(hex)` 成对出现（package.json 的 hex 与 store 路径 `files\cc\0283d8…` 一致，已验证哈希为 `sha512(content).hexdigest()`）。

---

## 5. 给 Lead 的判定建议

- 可以放心断言"**工具的注册/schema/参数契约与真实 dsh-tools 类型和实现一致**"（A1/A2/A4/A5/A6/A8/A9）。
- **不能**由 46 条单测断言"错误值契约在真实宿主中成立"：F1 是真实的输出校验缺陷（建议修复方向：把 payload 分支改为 `additionalProperties:false` + 声明必需字段，或让 `ERROR_SCHEMA` 与 payload 分支互斥，或在插件内对错误值走 `throw`（真实 `ToolOutputError`/失败结果）而不是返回值）。
- 本机无法完成真实宿主端到端加载（U1–U3），这是"插件能否在宿主里跑起来"这一问题的**最后一公里**，需要能安装 peer 的宿主环境。

---

# Post-fix re-verification（复核 Lead 对 F1 的修复）

复核时间：2026-10-10（turn 3）。方法**独立于 Lead 的数字**：仍用我的 loader-hook（`module.registerHooks` + data: URL，6 个缺失 peer 注入最小替身，不落盘）加载**真实** `_scratch\ffplugin\node_modules\@deepseek-ai\dsh-tools\lib\index.js`（158002 B），用真实 `defineTool` 编译、真实 `validateJsonSchemaValue` 校验（该函数**返回** violations 数组；`typeof dt.validateJsonSchemaValue === 'function'` 已确认导出）。

## P0. 结论

1. **F1 已修复，且我独立复现为 `[]`**：9 个工具的真实 `output.schema`（编译后）对 9 个 canned payload 与 9 个 errorValue 全部返回 `[]`（`A-FAILURES=0`）。
2. **判别式在真实编译后保留**：`output.schema.oneOf[0].required` 与 `discriminatorOf(spec)` 完全一致（scope ×6 / path ×2 / count ×1），payload 分支 `additionalProperties:true`、error 分支 `false`（`B` 行）。
3. **真实采集的 38 个 payload 无一被新 `required` 误拒**（`C REJECTIONS=0`），7 个零字节 `.out.json` 是 CLI 失败（无 payload），2 个未映射文件是 help 输出（插件没有对应工具）。
4. **对抗性输入没有制造歧义**：`{}`/`{status:'error'}`/`{status,code}`/`{unrelated}` 全部被拒；payload 附带 `status/code/message` 或未知键仍**恰好命中一个**分支；去掉判别式的 payload 被拒；errorValue 通过。唯一"两分支都不命中"的输入是 `ff_find` 的 errorValue 注入 `count:'injected'`（类型不符），属预期。
5. **`outputContract` 同源**：`lib/specs.js:351` 是唯一构造点，`lib/tools.js:12` 导入、`:40` 使用；`grep oneOf|ERROR_SCHEMA|outputContract lib/` 只命中这两处 + `lib/render.js:13` 的 `ERROR_SCHEMA` 定义。`test/harness-stub.js` 的 oneOf 值校验已改为**恰好一个**（`harness-stub.js:71-79`），`validateSpec` 新增未知关键字拒绝（`:36-39`）与"oneOf 分支节点不得声明 `required`"（`:42-43`，分支内部 property 仍 `allowRequired: true`，`:59`）。
6. **但我在复核中发现 3 个新的测试侧问题（N1/N2/N3），其中 N1 会让仓库自带的 `plugin.test.js` 在真实宿主里变红。**

## P1. 原始输出（节选）

```
== A: real defineTool + real validator, canned payloads/error values ==
A ff_list payload=[] errorValue=[]        （ff_show/ff_get/ff_find/ff_stats/ff_refs/ff_deps/ff_check/ff_export 同样 payload=[] errorValue=[]）
A-FAILURES=0

== B: compiled payload branch keeps its discriminator ==
B ff_list  want=["scope"] got=["scope"] payloadOpen=true errorOpen=false
B ff_show  want=["path"]  got=["path"]  payloadOpen=true errorOpen=false
B ff_get   want=["path"]  got=["path"]  payloadOpen=true errorOpen=false
B ff_find  want=["count"] got=["count"] payloadOpen=true errorOpen=false
B ff_stats/ff_refs/ff_deps/ff_check/ff_export want=["scope"] got=["scope"] payloadOpen=true errorOpen=false

== D: adversarial values ==
D ff_list disc=scope empty=REJECT statusOnly=REJECT statusCode=REJECT unrelated=REJECT errPlusDisc=accept
           payloadPlusErrKeys=accept payloadPlusUnknownKey=accept payloadNoDisc=REJECT errorValue=accept
D ff_find disc=count … errPlusDisc=REJECT（注入的 count 是字符串，类型不符）…
（其余 8 个工具与 ff_list 同形；disc 分别为 scope / path / count）

== C: sweep of captured real payloads ==
C files=47 emptyOut(CLI failure,no payload)=7 mapped=38 unmapped=["help_json.out.json","no_positionals_json.out.json"]
C payloadBranchMatched=38 errorBranchMatched=0
C REJECTIONS=0
C PARSE-FAILURES=0
C ERROR-SHAPED(out.json matching the error branch)=[]
```
映射规则：`<prefix>_…` 取 prefix；`show_subtree` 按 get 形状映射到 `ff_get`；`probe_X` 映射到 `ff_X`（probe_check/probe_export/probe_find/probe_refs/probe_stats）。

## P2. 新发现

### N1（中）`test/plugin.test.js` 把"真实 `defineTool`"与"替身校验器"混用，在真实宿主下必失败
- `test/plugin.test.js:24` `const defineTool = host?.defineTool ?? stub.defineTool`；`:26` `const validateValue = stub.validateValue`（永远用替身校验）。
- 真实 `defineTool` 会把作者 spec **编译**成 raw JSON Schema（`lib/index.js:848-849` 立即编译），其中对象级 `required` 变成 `required: ["status","code","message"]` 数组；而替身的 `validateValue` 只认"property 级 `child.required === true`"（`harness-stub.js:112`），**完全不实现对象级 `required` 数组**。
- 实测：
  ```
  F compiled error branch = {"type":"object","additionalProperties":false,"properties":{"status":{"type":"string","const":"error"},…},"required":["status","code","message"]}
  F stub.validateValue(compiledErrorBranch, {})             -> []
  F real.validateJsonSchemaValue(compiledErrorBranch, {})   -> ["missing required property \"value.status\"", …共 3 条]
  F stub.validateValue(wholeCompiledSchema, errorValue)     -> ["value: must match exactly one oneOf branch (matched 2)"]
  F stub.validateValue(wholeCompiledSchema, ff_listPayload) -> []
  F stub.validateValue(authorSpecContract, errorValue)      -> []   ← 用作者 spec 时替身是对的
  ```
- 后果（用同一个 loader 让真实包可解析后跑全部测试）：
  ```
  ===== WITH LOADER (real bundle reachable) =====
  ✖ createTools wires the eight read-only tools with valid definitions (8.5ms)
  ✖ the published output schemas accept the real payloads and the error value (2.5ms)
  ✔ the real factory accepts every definition
  ✔ the real validator accepts every payload and every error value
  ✔ the real validator rejects values that belong to neither branch
  ℹ tests 56  ℹ pass 54  ℹ fail 2  ℹ skipped 0
  ```
  失败点：`plugin.test.js:89`（`ff_list rejects an error value`，正是上面的 matched 2）与 `plugin.test.js:43`（见 N3）。
- 今天不可见的原因：本机 `import('@deepseek-ai/dsh-tools')` 必然失败，`host` 恒为 `undefined`，`:24` 永远取替身（A23）。**这段"真实包优先"的代码路径从未被真正执行过，一执行就红。**
- 建议：`host` 存在时用 `host.validateJsonSchemaValue(tool.output.schema, value, 'value')` 校验；或始终用作者 spec（`outputContract(spec)` / `spec.output`）喂替身校验器；不要把"真实编译后的 schema"交给替身校验器。

### N2（低）`plugin.test.js:25` 的注释与事实不符
注释称 "The real package exposes `validateArgs`, not a value validator, so schemas are always checked with ours."，但真实包**确实导出** `validateJsonSchemaValue`：`lib/index.js:3714` 的 export 列表包含它；本次实测 `typeof dt.validateJsonSchemaValue === 'function'`。这条错误假设正是 N1 的根因。

### N3（低）`plugin.test.js:43` 断言仅在替身下成立
`assert.equal(tool.isConcurrencySafe({}), true)` 对 8 个工具无条件断言 true；真实包装器会先校验参数，参数不合法即返回 false（`lib/index.js:882-885`）。实测：
```
E ff_list=true  ff_show=false  ff_get=false  ff_find=true  ff_stats=true
E ff_refs=false ff_deps=false  ff_check=true  ff_export=false
```
插件自身行为正确（默认独占调度），是测试断言把替身行为当成了真实行为。真实语义下应按工具给合法参数再断言。

### N4（信息）替身仍然存在的宽容面（当前插件未触及）
- `ALLOWED_KEYS` 收录 `title/examples/default/deprecated` 但不校验其类型/lossless（真实校验，`lib/index.js:199-209`）。
- 未拒绝 `oneOf` 旁的兄弟关键字（真实对 `properties/required/additionalProperties/items/enum/const` beside `oneOf` 报错，`lib/index.js:143-150,175`）。
- 未校验 `enum`/`const` 的标量类型正确性（真实 `lib/index.js:745-749`）。
- property 级 `required` 非 `true` 的值不被拒绝（真实类型 `schema.d.ts:73-76` `required?: true`）。

## P3. 测试套件执行现状（更新 U4）

```
# 仓库声明命令（package.json scripts.test = node --test "test/*.test.js"，此处由沙箱运行）
ℹ tests 9  ℹ pass 0  ℹ fail 9   Error: spawn EPERM (×9, errno -4048)   exit=1
# 绕开多进程隔离（单进程、显式文件列表）
node --test --test-isolation=none approval.test.js call.test.js config.test.js plugin.test.js \
  render.test.js runner.test.js specs.test.js output-schema.test.js real-harness.test.js
ℹ tests 56  ℹ pass 52  ℹ fail 0  ℹ skipped 4   exit=0     ← 与 Lead 数字一致
```
- 9 个测试文件 = 9 次 `spawn` → 沙箱 piped-stdio EPERM（文档化边界，非仓库缺陷）。**本沙箱内要用 `--test-isolation=none` + 显式文件路径**；正常机器上声明命令应可运行（未验证，属 U4）。
- 4 个 skipped 全部来自 `test/real-harness.test.js`（`:16` `skip = harness === undefined ? '… not importable here' : false`），skip 原因是真实包不可导入，属**诚实跳过**；加上 loader 后这 4 条**实际执行且全部通过**（上表 WITH LOADER 的 3 个用例 + "the compiled payload branch keeps its discriminator"）。

## P4. 无法判定项现状（U1–U5）

| 条目 | 现状 |
|---|---|
| U1 真实宿主端到端装配（`ctx.plugin` → fiber → `ctx.tools` → 真实 approval 把 `ask` 变成暂停/拒绝） | **仍无法判定**：本机 peer 不可安装。修复未改变这一结论；本次只把"schema/定义编译契约"从静态读源码升级为真实执行 |
| U2 `tools/pre-execute` 的 `ask` 在真实 approval 服务下的最终行为 | **仍无法判定**（同上；`index.d.ts:37-47` 的 "missing approval support turns `ask` into denial" 是声明，非本机可实测） |
| U3 真实宿主对插件 `Config`（schemastery）的合并/校验 | **仍无法判定**（需真实 cordis `resolveConfig` + `~standard` 通道） |
| U4 `node --test "test/*.test.js"`（多进程） | **本沙箱内不成立（spawn EPERM）**；`--test-isolation=none` 下成立（56/52/0/4）。真实机器未验证 |
| U5 `render` 投影在真实 registry 里的 lossless 快照 | **仍无法判定**（需真实 `dsh-util-values.snapshotProjection`，本机为替身） |

## P5. 复核结论一句话

修复方向正确且经真 bundle 独立确认（A/B/C/D 全绿、`outputContract` 同源、替身 oneOf 已对齐"恰好一个"）；同时暴露两个测试侧隐患：`plugin.test.js` 在真实包可用时会把"编译后 schema"喂给只认作者 spec 的替身校验器而失败（N1，根因是 N2 的错误注释），以及 `isConcurrencySafe({})` 的无条件断言（N3）。这两条都属"测试证明力/可迁移性"问题，不是插件运行期缺陷。
