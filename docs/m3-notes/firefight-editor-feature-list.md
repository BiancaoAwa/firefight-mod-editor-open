# Firefight mod editor — feature list (delivered / outstanding)

> Status snapshot: 2026-10-11, updated after the editor CLI and web UI reached `main` (PR #10) and the DSH plugin reached `0.1.0` (PR #1). Working note, kept in `m3-cli\docs\m3-notes\`.
> One-line status: **the read-only query layer is fully usable and now has a clickable browser UI** (CLI + DSH plugin + one-click launcher + local web UI); **data writing is not implemented at all**.

---

## 0. Delivery surface

| Part | Location | State |
|---|---|---|
| Editor CLI | repository `BiancaoAwa/firefight-mod-editor-open`; working tree `firefight-mod-editor-open\m3-cli`, started with `python -m core.cli` (code in `m3-cli\core\`) | usable (read-only + export) |
| Local web UI | same tree, `firefight-mod-editor-open\m3-cli\core\web\` (`python -m core.cli <scope> web`) | usable (read-only browsing, zero JavaScript, 231 tests pass) |
| DSH plugin | `firefight-mod-editor-open\ffplugin` → repository `BiancaoAwa/dsh-firefight-mod-tools` | 0.1.0 on both sides (merged 2026-10-11) |
| One-click launcher | `firefight-mod-editor-open\m3-cli\tools\launcher\` (`ff-tool.ps1` / `ff-tool.cmd` / `ff-start.cmd` / `ff-stop.cmd` / `ff-web.cmd`), shipped as `dist\launcher\` (junction) | usable; the script adapts to both layouts (repository and release) |
| AI entry (no UI) | `dist\ff-ai.cmd` (runs `python -m core.cli`; exit code = CLI exit code) + `dist\skills\firefight-editor\SKILL.md` | added 2026-10-11 |
| Repository layout | `m3-cli\` top level = `core\ docs\ tests\ tools\ README.md LICENSE` (matches GitHub); CLI/web in `core\cli\` and `core\web\`, launcher implementation in `tools\launcher\` | reshaped 2026-10-11 |
| Workspace layout | `firefight-mod-editor-open\README.md`; top level = `m3-cli\` (repository worktree) `dist\` (release-shaped test folder) `ffplugin\` `_out\` `README.md` | tidied 2026-10-11 |
| Release-shaped test folder | `dist\`: `ff-web.cmd` `ff-ai.cmd` + `core\ docs\ launcher\` (junctions into `m3-cli`) + `skills\` + `.ff-editor.local.toml` + `Firefight\` + `Mods\{WW3, sample-mod}\` | `Firefight` runs through the `editor copy` branch, `Mod` through the config branch; shape and caching in `docs\project-layout.md` §12 |
| Game-data copy | `dist\Firefight\Data\|Images\|Sounds\` (1840 files, byte-identical to stock) | formerly `stock\`, now part of the release shape |
| Mod projects | `dist\Mods\WW3\` (project shape: `mod.toml` + `mod_setting.toml` (partial, awaits M5) + `Mod\{Data,Images,Sounds}` + README/LICENSE + `.editor\{refs,index}.toml`), `dist\Mods\sample-mod\` (TOML entities + stock originals + default `mod_setting.toml`) | formerly `projects\`; WW3 = 765 files / 1329766 B / 13 lists |

---

## 1. Delivered

### 1.1 Editor CLI (milestones M0–M3)

- **Form**: `python -m core.cli <scope> <command> [selector] [key=value ...] [--json]`, run from the editor root; scope = `Firefight` (stock data) / `Mod` (a project with `mod.toml`) / any other mod folder name. Exit codes: `0` success, `1` an executed failure (the JSON payload is usually still valid), `2` usage error.
- **11 commands**: `list` `show` `get` `find` `stats` `refs` `deps` `check` `export` `web` `version` (aliases `ls`→list, `cat`→show). Everything except `export` is read-only.
- **Scan and classification**: stock data 1840 files / 4003531 bytes / 48 lists; weapon 716, vehicle 599, infantry 307, at_gun 111, aircraft 59, surnames 36, equipment 12.
- **Format and fidelity reading**: in-house specialised TOML (no tomlkit); XML/TXT dual format; `show` offers `raw` / `toml` / `xml` views and reports warnings.
- **Robust reading**: UTF-8 first with cp1252 fallback (16 stock weapon files carry Chinese comments); a repeated single-instance table (`squad/vehicle/hull/man/ammo` twice under one parent) degrades to an array plus a warning instead of failing; `//` comments and stray text are reported rather than dropped silently.
- **Cross references**: `refs` (what this entity points at), `deps` (who points at it, with `kind` filter and resolved/unresolved flags). Example: `WEAPON_PISTOL_P38` has 1204 incoming references.
- **Project check**: `check` reports loaded/skipped/errors/warnings/warning files/dangling references, for one file or a whole scope.
- **Export (byte-identical to stock, finished 2026-10-11)**: `export <selector> to=<dir>` writes XML along the original `Data/...` tree; a file with source text is reproduced **byte for byte** — sibling order as written, blank lines, indentation, `//` comments and the file's own newline style preserved. Measured over stock data: **1840 / 1840 files identical** (`tools\export_fidelity.py` gate, non-zero exit on any difference); before the change the same run showed 1792 reordered, 12 newline changes, 36 fully identical. `export Vehicles` = 599 files / 2371815 bytes / 0 errors; two consecutive exports give equal sha256 (deterministic); writes only below `to=`, never into the source data.
- **Enums**: reuse `enums_ext.txt`, do not rebuild the 13.2.0.0 enums, warn on unknown values.
- **Project and docs**: `docs\cli.md`, `docs\project-layout.md`, unit tests, tools; the real WW3 project passes a smoke run.
- **Version**: editor 0.1.0 / python 3.12.14.

### 1.2 DSH plugin `dsh-firefight-mod-tools`

- **9 tools**: `ff_list` `ff_show` `ff_get` `ff_find` `ff_stats` `ff_refs` `ff_deps` `ff_check` (8 read-only, concurrency-safe) + `ff_export` (registered only when `enableExport: true`, approved per call through `tools/pre-execute`).
- **Engineering**: Schemastery config (`pythonPath` / `editorRoot` / `cliModule` / `firefightRoot` / `workspace` / `cwd` / `timeoutMs` / `maxOutputChars` / `enableExport`); a whole-line override in `cordis.patch.yml`; payload and error schemas are two mutually exclusive branches pinned by a discriminant.
- **Installed into the local DSH**: `C:\Users\BC_aw\.dsh\profiles\desktop` `package.json` (link dependency + bundles) and `cordis.patch.yml` (nine config keys, `enableExport: false`); after restart the 8 `ff_*` tools appear and answer with correct data (stats 1840/4003531/48, deps 1204).
- **Verification strength**: 60 tests in one process (56 pass, 4 honest skips), real-host bundle checks, end-to-end 318/318, real payloads and error values compiled and validated by the real `defineTool`; 27 approval-bypass attempts, 0 successes.
- **0.1.0 contents**: the CLI is started as a module (`cliModule`, default `core.cli`) instead of a `ff.py` script path, and `editorRoot` is accepted as either the repository root or the release root; README, `cordis.patch.yml` and tests follow.

### 1.3 One-click launcher

- **Actions**: `start` / `stop` / `restart` / `status` / `run` / `web` / `help`; switches `-Quick -KeepOutput -Project -Python -Cli -Root -WorkDir -Scope -Window -NoBrowser -Browser -Port`; environment overrides `FF_PYTHON`/`FF_CLI`/`FF_ROOT`/`FF_PROJECT`/`FF_WORK`/`FF_SCOPE`/`FF_PORT`.
- **In-shell shortcuts**: `ff <CLI args>`, `ff-start`, `stop`, `restart`, `status`, `web`, `web-open` (background server + its own app window), `ff-help` (`start` belongs to PowerShell's own alias, hence `ff-start` for a restart).
- **Guard rails**: the `Firefight` scope gets `root=` filled in automatically; `key=<...>` placeholders are rejected with a usable hint; `web -Window` probes the port first and on a busy port reports `port … is already in use … (pid …)` plus the three ways out, never hijacking someone else's server.
- **Operations**: logs `logs\tool-yyyyMMdd.log`, `state.json`, `web.json` (server pid, port, scope, log paths, app-window pid/profile, watchdog pid, debug port), `out\`; `status` reports the web UI as listening (pid + logs + watchdog) or unresponsive (stale state) and shows `last session`; `stop` ends the web UI process, waits for the watchdog, closes the window it opened, removes the temporary profile and clears leftovers; double-clicking `ff-tool.cmd` opens a `-NoExit` window; `web -Window` leaves no console at all, so stopping it means the page's quit link or `stop`.
- The host is Windows PowerShell 5.1 (`pwsh` absent), so the scripts target 5.1.
- **`.cmd` entries must be pure ASCII (fixed 2026-10-11)**: `cmd.exe` reads a `.cmd` in the OEM code page (cp936 here), so one Chinese `rem` line broke the whole script on double-click. All four `.cmd` files now have zero non-ASCII bytes and carry that rule at the top; `ff-tool.cmd` also uses delayed `!ERRORLEVEL!`.
- **Double-click entry now opens its own window and watches exits (fixed 2026-10-11, user report "web 是单开一个窗口 / 退出监听似乎没生效")**: the release `dist\ff-web.cmd` used to take the `:run` branch — a foreground `python -m core.cli <scope> web port=… browser=1`, so the page opened in an ordinary browser tab and no watchdog existed. It is now a thin wrapper that defaults to `launcher\ff-tool.ps1 web -Window -Scope <name>` (background server + its own app window + watchdog); `-Foreground` restores the old direct path, `-Browser`/`-NoBrowser`/`-Port <n>` pass through. The launcher gained `-Scope` (`FF_SCOPE`) and `Get-WebScope`/`Get-WebRootArgs`/`Get-WebRootText`. Measured: `dist\ff-web.cmd -Port 9051 -NoBrowser` → `scope Mod`, `root (resolved by the editor config)`, listening on 9051 with a watchdog and a `web.json`, homepage 200, `/quit?do=1` 200, state file and port cleared, exit log `… :: the server stopped :: graceful True :: backend exited normally`; `-Scope Firefight -Port 9061` resolves the Steam root and exits as cleanly.

### 1.4 Local web UI (M7 browsing slice, read-only)

- **Run**: `python -m core.cli <scope> web [port=8765] [token=…] [pagesize=200] [browser=1]`; via the launcher `ff-tool.cmd web` (this window), `ff-tool.cmd web -Window` or in-shell `web-open`, or by double-clicking `ff-web.cmd`. `-Window` starts the server hidden (`Start-Process -WindowStyle Hidden`) and redirects stdout/stderr to `logs\web-<port>-out.log` / `-err.log`, and opens the page in its **own Chromium app window** (`msedge --app=<url>`). It binds `127.0.0.1`, serialises page requests across threads, prints the address in a banner and logs every request to stderr.
- **Quit**: every page has a quit link → `/quit` shows a confirmation page (a zero-JS link may be prefetched, hence the second click) → confirming really stops the server. Only the local process ends; no data file is written. The equivalent command line is `stop`.
  - **Automatic cleanup after quit (2026-10-11)**: a hidden **watchdog** verifies the backend exited (process gone, port released, graceful marker in the log), then closes the app window it opened, deletes that window's temporary browser profile and exits; the verdict is appended to `logs\web-<port>-exit.log` and shown by `status` as `last session …`.
  - **Reverse logic, window closed first → server stops (2026-10-11)**: liveness comes from the app window's **profile lock** (the `lockfile` under `--user-data-dir`; the only signal that survives the browser handing a window to another process — pid and process-count checks both lied in measurements). Three consecutive dead checks (about 5 s) mean the window is gone; the watchdog then asks the server to stop through `/quit?do=1`, so the exit log still reads `graceful True … backend exited normally`. The launcher waits up to 15 s for that lock and only then prints `window up, watched through its profile lock`; otherwise it says `did not show up in 15 s - the server is not watched` and degrades to not watching. `-Browser` and `-NoBrowser` never watch.
  - **A busy port is refused (fixed 2026-10-11)**: `HTTPServer` sets `SO_REUSEADDR`, and on Windows a second process could bind the same port successfully. `make_server` now probes with `socket.connect_ex` and raises `cannot listen on 127.0.0.1:<port>: the port is already in use` (`port=0` is always free and is what the tests use).
  - **`stop` does not kill a reused pid (fixed 2026-10-11)**: the recorded pid is checked against the expected process name and skipped with `pid N is … - a reused pid, leaving it alone` when it does not match.
  - **The web server is threaded (fixed 2026-10-11)**: `ThreadingHTTPServer` with daemon threads, because an idle browser pre-connection could block a single-threaded server.
  - **Confirmation-form bug (fixed 2026-10-11)**: a browser drops the action's query string when submitting a GET form, so the confirm button only reloaded the page; the form now carries `do=1` and the other parameters as hidden inputs.
- **Pages**: home (scope/root/counts) · entity list (category and path filters, paging) · entity detail (`toml`/`xml`/`raw` views plus both reference directions) · field lookup · find (tag/value/path/case) · references · reverse references · check · stats · command line · help · quit · raw `/json?...` payloads. Every page shows its equivalent command line and links to its own JSON.
- **Command-line page `/cmd` (2026-10-11)**: one input box taking what would follow `python -m core.cli`, an optional scope prefix, quoted paths, and a JSON checkbox. It goes through the same argparse and command handlers, so its output matches the CLI exactly (a test compares them), and read-only is enforced: `export` and `web` (and the aliases `emit`/`serve`) answer 400. Real-data run: `stats` → 1840, `deps value=WEAPON_PISTOL_P38` → 1204.
- **Shape**: standard-library `http.server` only, no new dependency, no build, **zero JavaScript**, no external resource, no cookie, plain server-rendered HTML with a small inline CSS.
- **Correctness**: pages call the same in-process command handlers, so they cannot drift from the CLI; `/json` returns raw payloads.
- **Security and limits**: loopback only, GET only (POST/PUT/DELETE/PATCH → 501 after draining the body), everything escaped (XSS cases covered), selectors reject absolute paths, drive letters and `..`, an optional `token=` gate, and `pagesize` truncation with a "+N not shown" notice.
- **Verification**: `tests\test_web.py` 57 cases; the full suite is 231. All pages answer 200 on stock data (home 5.1 KB, list 716 rows, reverse lookup 1204 rows paged, check 7.5 KB), slowest page 1.4 s.
- **Docs**: `docs\web.md` (routes, options, design rules, limits, tests); the README gained a quick start and a doc index; `docs\cli.md` documents `web`/`serve` and their options.

### 1.5 Code structure and comments (de-fragmented 2026-10-11)

- **Module merges**: `core/xml.py` ← `xmlmodel.py` + `xmlread.py`; `core/toml.py` ← `tomlmodel.py` + `tomlread.py` + `tomlwrite.py`; `core/cli/commands.py` absorbed `documents.py`; `core/web/server.py` absorbed `pages.py`. `core` went from 18 `.py` files to 11.
- **Method**: a one-off ast-driven script moved top-level definitions, kept `import … as` aliases, stripped qualifiers of the vanished modules and merged duplicate imports. The absorbed body is placed **before** the target body, because `class App` in `core/web/server.py` evaluates the `-> Url` annotation at class creation. `_out\check_merge.py` compared `core/xml.py` and `core/toml.py` against their sources (14/14 and 25/25 definitions, 0 problems).
- **Test files merged**: `tests/test_xml.py` ← `test_xmlread.py`; `tests/test_toml.py` ← `test_tomlread.py` + `test_tomlwrite.py`; 13 test modules became 11.
- **Verification**: `python -m unittest discover -s tests -t .` → `Ran 231 tests … OK` (about 4.2 s); per module 57/37/34/21/20/19/16/7/7/6/6. The merged web UI smoked on real data: `GET /` 200 · 5217 B, `/quit?do=1` 200, port released.
- **Cost of the merge (recorded as it happened)**: one `git checkout -- tests tools/m1_roundtrip.py` discarded uncommitted WIP test additions (`tests/test_textio.py` +34 lines, `tests/test_xmlread.py` +4, about 6 cases) that could not be restored, so the suite went from 236 to 230 and later to 231 with the entry-point test. The three golden fixtures were regenerated through the existing pipeline and the "a repeated table must fail" case became "a repeated table becomes an array plus a warning".
- **Comments and docstrings**: every core module and the entry point carries a three-line module docstring (responsibility / blank / one constraint with a source); `tests/test_*.py` docstrings were shortened the same way. The 14 reasoning-style comment blocks in `tools\launcher\ff-tool.ps1` were rewritten per C1–C7, and its **UTF-8 BOM was restored** (without it PowerShell 5.1 decodes the script as cp936 and the Chinese help text becomes mojibake).
- **Cleanup**: the exploratory scripts (46 files: `tools\probes\`, `compare-remote.mjs`, `gh-read.mjs`, `ffplugin-smoke.mjs`, `edit-probe.ps1`, `_verb-test.ps1`) moved out of the worktree; the 106 launcher log files were deleted and their directory added to `.gitignore` along with `tools/launcher/out/` and `tools/launcher/*.json`.
- **Not done**: `docs/m1-design.md` keeps the module names of its writing time and only carries a "current names" paragraph after the §3.1 tree; the class- and function-level docstrings were not shortened one by one.

---

## 2. Outstanding

### 2.1 M7 local web UI (browsing delivered, see §1.4)

Deliberately not built, with the reasons in `docs\web.md`: a collapsible entity tree, `/` + `j/k` keyboard navigation, and client-side lazy rendering — the "zero JavaScript, simple, few bugs" constraint replaced them with server-side paging, category/path filters and links. Two more: field source line numbers on the detail page and click-to-line on the check page.

**Editing (needs M4 first, then joins the same UI)**

- A type-aware field editor: enum dropdowns, numbers, booleans, strings, multi-select; invalid values rejected in place.
- Staged unsaved changes with a **semantic diff** preview; `--dry-run` writes nothing.
- Saving appends an event-log record; undo/redo (`undo N` / `redo N`) across segments.
- Conflict detection: refuse to overwrite a file changed outside the editor.
- Permission-mode indicator, per-write confirmation, refusal aborts without retry.
- Batch editing (one field across a selection).
- Import/export (`export to=`, mod-zip packaging) and project switching.
- Event-log viewer: timeline, segments, replay, export; baseline snapshot diff.

### 2.2 M4 editing engine

- `set <entity> <field>=<value>`, `add` / `remove` (repeated tables addressed by index, `--dry-run`, idempotent).
- Event log: JSONL under `.editor\log\<segment start>.jsonl`, segments close after 5 idle minutes.
- `undo N` byte-level restore; `.editor\baseline\` snapshots.
- Fidelity: encoding preserved (the 16 UTF-8 files stay UTF-8, cp1252 stays cp1252, CRLF/LF each kept), comments and stray text preserved, unencodable characters fail hard with `ExportEncodingError`.
- Consistency: reference validation and rename chains; atomic writes (temporary file + atomic rename); no interleaved concurrent writes.
- Three permission tiers (DSH semantics) with per-action approval, no retry on refusal, fail-closed.
- Acceptance cases B1–B20 were listed earlier (correct edits, fidelity, reference consistency, rollback and audit, permission failure modes, scale round trip).

### 2.3 M5 / M6 / M8

- **M5 project files**: `mod.toml` (mod metadata), `mod_setting.toml` (the `mod.txt` settings), reference caches (each TOML); project import/export.
- **M6 packaging**: mod-zip with a `Mod/` folder inside and README/licence outside; folder ↔ zip round trip lossless at the `export Vehicles` scale (599 files).
- **M8 distribution**: versioning, update and installation notes.

### 2.4 Known defects and risks

- **A selector containing `=` is swallowed as `key=value`**: zero instances in the 1840 stock files, verified and documented; whether to guard is undecided.
- **The UTF-8 fallback is unverified against the engine**: the 16 files need a check in the running game.
- **Sibling reordering on export**: resolved 2026-10-11 — export now follows the document order and keeps the layout, stock data is byte-identical in 1840/1840 files.
- **Entry point**: the tree has no top-level `ff.py`; the CLI is the module `core.cli` on `main`.
- **`Mod` scope**: `dist\Mods\sample-mod` provides a project with `mod.toml`, and `dist\.ff-editor.local.toml` points at it, so the scope resolves without an explicit `-Project` in that layout.
- **Sandbox limits**: node `spawn` is EPERM inside the sandbox, so live end-to-end cases need a non-sandboxed run.

### 2.5 Decisions still open

1. What to build next: **(a)** the M4 editing engine (`set` + event log + `undo`, then into the web UI); **(b)** refine browsing (field source lines, click-to-line, collapsible tree); **(c)** something else, for example a minimal `mod.toml` fixture so the `Mod` scope is clickable everywhere.
2. Whether the release `dist\` shape and the workspace README should be published as a tagged release.

---

## 3. Settled rulings (do not reopen)

| No. | Content |
|---|---|
| D7 | Export fidelity = **XML semantically equivalent**, not byte-identical (**revised 2026-10-11**: files with source text are reproduced **byte for byte**, stock data 1840/1840; semantic equivalence remains the floor for `.toml` documents without source text) |
| D8 | Local research and measurement scripts stay out of the repository |
| D9 | The schema ships as its own PR |
| — | Do not rebuild the 13.2.0.0 enums; reuse `enums_ext.txt` and warn on unknown values |
| — | AI permissions follow the DSH three tiers with per-action approval, fail-closed, no retry |
| — | Implementation language is Python (compatibility first); one entity per file, mirroring the stock `Data` tree |
| — | Surnames are neither modelled nor packaged; comments state function and outstanding work only |
| — | Until editing exists the CLI is read-only; the only write paths are `export` / `ff_export` |

---

# Firefight 模组编辑器 —— 功能清单（已完成 / 待完成）

> 状态快照：2026-10-11，在编辑器 CLI 与 Web UI 并入 `main`（PR #10）、DSH 插件以 `0.1.0` 并入（PR #1）之后更新。本文件是工作笔记，放在 `m3-cli\docs\m3-notes\`。
> 现状一句话：**只读的查询层已经完全能用，并且有能在浏览器里点的界面了**（CLI + DSH 插件 + 一键启动器 + 本地 Web UI），**写数据的能力一点都还没有**。

---

## 0. 交付面

| 部件 | 位置 | 状态 |
|---|---|---|
| 编辑器 CLI | 仓库 `BiancaoAwa/firefight-mod-editor-open`；本地工作树 `firefight-mod-editor-open\m3-cli`，用 `python -m core.cli` 启动（代码在 `m3-cli\core\`） | 可用（只读 + export） |
| 本地 Web UI | 同一工作树 `firefight-mod-editor-open\m3-cli\core\web\`（`python -m core.cli <scope> web`） | 可用（只读浏览，零 JS，231 条测试全过） |
| DSH 插件 | `firefight-mod-editor-open\ffplugin` → 仓库 `BiancaoAwa/dsh-firefight-mod-tools` | 两侧均为 0.1.0（2026-10-11 合并） |
| 一键启动器 | `firefight-mod-editor-open\m3-cli\tools\launcher\`（`ff-tool.ps1` / `ff-tool.cmd` / `ff-start.cmd` / `ff-stop.cmd` / `ff-web.cmd`），发行版里是 `dist\launcher\`（junction） | 可用；脚本按布局自适应（仓库 / 发行版） |
| AI 接口（无 UI） | `dist\ff-ai.cmd`（以 `python -m core.cli` 运行，退出码 = CLI 退出码）+ `dist\skills\firefight-editor\SKILL.md` | 2026-10-11 新增 |
| 仓库结构 | `m3-cli\` 顶层 = `core\ docs\ tests\ tools\ README.md LICENSE`（**与 GitHub 一致**）；CLI/Web 在 `core\cli\`、`core\web\`，启动器实现在 `tools\launcher\` | 2026-10-11 第四批重整（用户裁决「仓库与 GitHub 对齐」） |
| 工作区布局 | `firefight-mod-editor-open\README.md` —— 顶层 = `m3-cli\`(仓库工作树) `dist\`(发行版形状的测试文件夹) `ffplugin\` `_out\` `README.md` | 2026-10-11 整理（辅助物全部并入仓库的 `tools\ docs\ tests\`） |
| 发行版形状测试文件夹 | `dist\`：`ff-web.cmd` `ff-ai.cmd` + `core\ docs\ launcher\`（junction 指向 `m3-cli`，不复制、不漂移）+ `skills\` + `.ff-editor.local.toml` + `Firefight\` + `Mods\{WW3, sample-mod}\` | `Firefight` 作用域实跑走 `editor copy` 分支、`Mod` 走 config 分支；形态与缓存都记在 `docs\project-layout.md` §12 |
| 游戏数据副本 | `dist\Firefight\Data\|Images\|Sounds\`（1840 文件，对 stock 逐字节 0 mismatch） | 原 `stock\`，现挂在发行版形状里 |
| 模组工程 | `dist\Mods\WW3\`（工程形状：`mod.toml` + `mod_setting.toml`（部分，等 M5 渲染器）+ `Mod\{Data,Images,Sounds}` + README/LICENSE + `.editor\{refs,index}.toml`）、`dist\Mods\sample-mod\`（TOML 实体 + stock 原文 + 全默认 `mod_setting.toml`） | 原 `projects\`；WW3 工程 765 文件 / 1329766 B / 13 列表 |

---

## 1. 已完成

### 1.1 编辑器 CLI（里程碑 M0–M3）

- **形态**：`python -m core.cli <scope> <命令> [选择器] [键=值 …] [--json]`，在编辑器根目录运行；scope = `Firefight`（原版数据）/ `Mod`（有 `mod.toml` 的工程）/ 其他模组文件夹名。退出码：`0` 成功、`1` 已执行的失败（JSON 载荷通常仍有效）、`2` 用法错误。
- **11 个命令**：`list` `show` `get` `find` `stats` `refs` `deps` `check` `export` `web` `version`（别名 `ls`→list、`cat`→show）。除 `export` 外**全部只读**。
- **目录扫描与分类**：原版数据 1840 文件 / 4003531 字节 / 48 个列表；分类 weapon 716、vehicle 599、infantry 307、at_gun 111、aircraft 59、surnames 36、equipment 12。
- **格式与保真读取**：自研特化 TOML（不引 tomlkit）；XML/TXT 双格式；`show` 支持 `raw` / `toml` / `xml` 三种视图并回报警告。
- **读取健壮性**：UTF-8 优先 + cp1252 回退（原版里有 16 个 UTF-8 武器文件，注释带中文）；重复单例表（`squad/vehicle/hull/man/ammo` 同父下出现两次）降级为数组 + 警告，不再报错；`//` 注释与游离文本被识别并警告而不是静默丢弃。
- **交叉引用**：`refs`（本实体指向谁）、`deps`（谁引用我，含 `kind` 过滤与解析结果/未解析标志）。例：`WEAPON_PISTOL_P38` 有 1204 条传入引用。
- **工程体检**：`check` → 加载/跳过/错误/警告总数/警告文件/悬空引用，单文件与整 scope 都行。
- **导出（逐字节对齐原版，2026-10-11 完成）**：`export <选择器> to=<目录>`，按 `Data/...` 原树写 XML；**对有来源文本的文件逐字节复现原版** —— 兄弟顺序按文档出现顺序、空行/缩进/`//` 注释/文件自身换行风格全部保留。实测原版数据 **1840 / 1840 文件完全一致**（`tools\export_fidelity.py` 闸门，有差异即非零退出）；改动前是「顺序变 1792、换行变 12、完全一致 36」。`export Vehicles` = 599 文件 / 2371815 字节 / 0 错误；同一导出连跑 sha256 一致（确定性）；只在 `to=` 下写，不碰源数据。
- **枚举**：复用 `enums_ext.txt`，不重建 13.2.0.0 枚举，未知枚举只警告。
- **工程与文档**：`docs\cli.md`、`docs\project-layout.md`、`tests\` 单测、`tools\` 脚本；WW3 真实模组工程冒烟通过。
- **版本**：editor 0.1.0 / python 3.12.14。

### 1.2 DSH 插件 `dsh-firefight-mod-tools`

- **9 个工具**：`ff_list` `ff_show` `ff_get` `ff_find` `ff_stats` `ff_refs` `ff_deps` `ff_check`（8 个只读、并发安全）+ `ff_export`（仅当 `enableExport: true` 才注册，且经 `tools/pre-execute` 逐次审批）。
- **工程化**：Schemastery 配置（`pythonPath` / `editorRoot` / `cliModule` / `firefightRoot` / `workspace` / `cwd` / `timeoutMs` / `maxOutputChars` / `enableExport`）；`cordis.patch.yml` 整行覆盖；payload 与错误值两个 schema 分支互斥（判别式字段钉死 exactly-one-oneOf）。
- **已装入本机 DSH**：`C:\Users\BC_aw\.dsh\profiles\desktop` 的 `package.json`（link 依赖 + bundles 列表）与 `cordis.patch.yml`（config 九键，`enableExport: false`）；重启后已确认 8 个 `ff_*` 出现在模型工具目录、实际调用返回正确数据（stats 1840/4003531/48、deps 1204）。
- **验证强度**：替身宿主 60 条测试（56 通过 / 4 条诚实跳过）、真实宿主 bundle、端到端校验 318/318、真实 payload 与错误值全部通过真实 `defineTool` 编译与校验；审批门 27 条绕过尝试 0 成功。
- **0.1.0 的内容**：命令行改为以模块启动（`cliModule`，默认 `core.cli`），不再依赖 `ff.py` 脚本路径；`editorRoot` 同时接受仓库根与发行版根；README、`cordis.patch.yml` 与测试同步。

### 1.3 一键启动器

- **动作**：`start` / `stop` / `restart` / `status` / `run` / `web` / `help`；开关 `-Quick -KeepOutput -Project -Python -Cli -Root -WorkDir -Scope -Window -NoBrowser -Browser -Port`；环境变量 `FF_PYTHON`/`FF_CLI`/`FF_ROOT`/`FF_PROJECT`/`FF_WORK`/`FF_SCOPE`/`FF_PORT`。
- **窗口内快捷**：`ff <CLI 参数>`、`ff-start`、`stop`、`restart`、`status`、`web`、`web-open`（后台起服务 + 独立 app 窗口）、`ff-help`（`start` 归 PowerShell 自己的别名，故重启用 `ff-start`）。
- **防呆**：`Firefight` 作用域自动补 `root=<真实游戏目录>`；`键=<...>` 占位符直接拦下并给出可执行提示；`web -Window` 先探端口，被占就报 `port … is already in use … (pid …)` 并给三条出路，绝不劫持别人的服务。
- **可运维**：日志 `logs\tool-yyyyMMdd.log`、`state.json`、`web.json`（服务 pid、端口、作用域、日志路径、app 窗口 pid/profile、watchdog pid、调试端口）、`out\`；`status` 汇报 Web UI 是「正在监听（pid + 日志 + watchdog）/ 端口没响应（陈旧状态）」并给出 `last session`；`stop` 结束 Web UI 进程、等 watchdog 收尾、关掉它开的窗口并删临时 profile、清理残留；双击 `ff-tool.cmd` 进 `-NoExit` 窗口；`web -Window` 不留控制台窗口，所以停 Web UI 只有页面「退出」或 `stop`。
- 本机是 Windows PowerShell 5.1（`pwsh` 未安装），脚本按 5.1 兼容编写。
- **双击入口必须纯 ASCII（2026-10-11 修）**：`cmd.exe` 按 OEM 代码页（本机 cp936）读 `.cmd`，一行中文 `rem` 就会让整段脚本解析坏掉。四个 `.cmd` 现已全部 0 个非 ASCII 字节并在顶部写明该规则；`ff-tool.cmd` 同时改用延迟展开 `!ERRORLEVEL!`。
- **双击入口默认单开窗口 + 退出监听（2026-10-11 修，用户报「web 是单开一个窗口 / 退出监听似乎没生效」）**：发行版 `dist\ff-web.cmd` 原默认走 `:run` 分支 —— 前台跑 `python -m core.cli <scope> web port=… browser=1`，页面开在**普通浏览器标签**里、也没有 watchdog。现在它是薄封装：默认 `launcher\ff-tool.ps1 web -Window -Scope <名字>`（后台服务 + 独立 app 窗口 + watchdog），`-Foreground` 才退回前台直连路径，`-Browser`/`-NoBrowser`/`-Port <n>` 透传。启动器新增 `-Scope`（`FF_SCOPE`）与 `Get-WebScope`/`Get-WebRootArgs`/`Get-WebRootText`。实测：`dist\ff-web.cmd -Port 9051 -NoBrowser` → `scope Mod`、`root (resolved by the editor config)`、9051 上带 watchdog 与 `web.json` 的监听、首页 200、`/quit?do=1` 200、状态文件与端口都清掉、exit log `… :: the server stopped :: graceful True :: backend exited normally`；`-Scope Firefight -Port 9061` 解析出 Steam 根目录并同样干净退出。

### 1.4 本地 Web UI（M7 的浏览部分，只读）

- **跑法**：`python -m core.cli <scope> web [port=8765] [token=…] [pagesize=200] [browser=1]`；启动器里是 `ff-tool.cmd web`（本窗口）、`ff-tool.cmd web -Window` 或窗口内敲 `web-open`，双击 `ff-web.cmd` 也行。`-Window` 用 `Start-Process -WindowStyle Hidden` 起服务，stdout/stderr 重定向到 `logs\web-<端口>-out.log` / `-err.log`，并把页面开在**独立的 Chromium app 窗口**里（`msedge --app=<url>`）；绑 `127.0.0.1`，页面请求在多线程间串行处理，启动横幅打印地址，每个请求打到 stderr。
- **退出**：每页顶栏都有「退出」链接 → `/quit` 先给确认页（零 JS 下链接可能被预取，所以点第二次才真停）→ 确认按钮真的停掉服务并回「已退出」。只结束本地服务进程，不写任何数据文件。等价命令行是 `stop`。
  - **2026-10-11 加：退出后自动收尾**：后台会话多一个隐藏 **watchdog**。服务一停，它先核对后端是否正常退出（进程消失 + 端口释放 + 日志里的优雅退出标记），然后关掉它开的 app 窗口、删掉临时浏览器 profile、自己退出；结论追加到 `logs\web-<端口>-exit.log`，`status` 里显示成 `last session …`。
  - **反向逻辑（先关窗口 → 自动停服务）已实现（2026-10-11）**：活体信号取自那扇 app 窗口的 **profile 锁**（`--user-data-dir` 下浏览器持有的 `lockfile`；这是唯一能扛住「浏览器把窗口交给另一个进程」的信号，实测按 pid 与按进程数判断都会说谎）。连续三次（约 5 秒）判死才认为窗口关了，然后用 `/quit?do=1` 礼貌停服（exit log 仍记 `graceful True … backend exited normally`）。启动器最多等这把锁 15 秒，起来了才打印 `window up, watched through its profile lock`，没起来就明说 `did not show up in 15 s - the server is not watched` 并降级为不监视。`-Browser` 与 `-NoBrowser` 都不做反向。
  - **端口占用是真拒绝（2026-10-11 修）**：`HTTPServer` 默认开 `SO_REUSEADDR`，Windows 上第二个进程能成功再绑同一端口。现在 `make_server` 先用 `socket.connect_ex` 探端口，占用就抛 `cannot listen on 127.0.0.1:<port>: the port is already in use`（`port=0` 永远可用，测试用它）。
  - **`stop` 不误杀复用的 pid（2026-10-11 修）**：状态文件里的 pid 会先核对进程名，不匹配就打印 `pid N is … - a reused pid, leaving it alone` 并跳过。
  - **Web 服务改成多线程（2026-10-11 修）**：`ThreadingHTTPServer` + daemon 线程；单线程会被浏览器的空闲预连接卡住。
  - **确认页表单修好（2026-10-11）**：浏览器提交 GET 表单时会丢掉 action 的查询串，于是点确认只会回到确认页；现在 `do=1` 与其他参数都作为隐藏输入提交。
- **页面**：首页 · 实体列表（分类与路径过滤 + 翻页）· 实体详情（`toml`/`xml`/`raw` 三视图 + 双向引用）· 读取字段 · 查找 · 引用 · 反查 · 体检 · 统计 · 命令行 · 帮助 · 退出 · `/json?...` 原始载荷。每页都显示等价命令行并链到自己的 JSON。
- **命令行页 `/cmd`（2026-10-11 加）**：一个输入框，写 `python -m core.cli` 之后的内容即可，可在最前面写作用域名，路径带空格用双引号，勾「JSON 输出」就是 `--json`。走的是**同一套 argparse 与命令处理器**，输出与 CLI 完全一致（有测试逐字比对）；只读保证：`export`（写文件）与 `web`（会再绑端口）连同别名 `emit`/`serve` 一律 400。真数据实测：`stats` → 1840、`deps value=WEAPON_PISTOL_P38` → 1204。
- **形态**：纯 Python 标准库 `http.server`，零新依赖、零构建、零 JavaScript、零外部资源、零 cookie，老式服务端渲染 HTML（内联一套朴素灰色 CSS）。
- **正确性保证**：页面在同一进程内调用同一批命令处理器，因此与 CLI 不可能漂移（有测试对拍）；`/json` 路由直接给原始载荷。
- **安全与边界**：只绑回环、只支持 GET（POST/PUT/DELETE/PATCH→501 且先排空请求体）、全程转义（有 XSS 用例）、选择器拒绝绝对路径/盘符/`..`、`token=` 门（缺 token→400）、行数按 `pagesize` 截断并提示 "+N 条未显示"。
- **验证**：`tests\test_web.py` 57 条全过；全套 231 条全过；原版真数据全页面 200（首页 5.1 KB / 列表 716 行 / 反查 1204 行已分页 / 体检 7.5 KB），最慢一页 1.4 s。
- **文档**：`docs\web.md`（路由、选项、设计规则、限制、测试）；`README.md` 补了快速开始与文档索引；`docs\cli.md` 补了 `web`/`serve` 命令与选项。

### 1.5 代码结构与注释（2026-10-11 去碎片化）

- **模块合并**：`core/xml.py` ← `xmlmodel.py` + `xmlread.py`；`core/toml.py` ← `tomlmodel.py` + `tomlread.py` + `tomlwrite.py`；`core/cli/commands.py` 吸收 `documents.py`；`core/web/server.py` 吸收 `pages.py`。core 的 `.py` 由 18 个减到 11 个。
- **做法**：一次性 ast 脚本按顶层定义逐段搬运，保留 `import … as` 别名、剥掉已消失模块的限定符、并集重复 import；被吸收模块的 body 放在目标 body **之前**（`core/web/server.py` 里 `class App` 的注解 `-> Url` 会在类创建时求值）。`_out\check_merge.py` 比对 `core/xml.py` / `core/toml.py` 的顶层定义与合并前一致（14/14、25/25，problems 0）。
- **测试文件合并**：`tests/test_xml.py` ← `test_xmlread.py`；`tests/test_toml.py` ← `test_tomlread.py` + `test_tomlwrite.py`；测试模块 13 → 11 个。
- **验证**：`python -m unittest discover -s tests -t .` → `Ran 231 tests … OK`（约 4.2 s）；单模块 57/37/34/21/20/19/16/7/7/6/6。合并后的 Web UI 在真数据上冒烟：`GET /` 200 · 5217 B、`/quit?do=1` 200、端口随即释放。
- **合并的代价（据实记录）**：过程中一次 `git checkout -- tests tools/m1_roundtrip.py` 误丢了未提交的 WIP 测试增量（`tests/test_textio.py` +34 行、`tests/test_xmlread.py` +4 行，约 6 条用例），无法恢复，测试总数因此由 236 变为 230，入口改造后为 231。三个 golden fixture 按现有管线重生成，「重复表必须报错」那条改为符合宽容导入语义的「重复表变成数组 + 警告」。
- **注释与文档串**：core 各模块与入口的模块文档串统一成三行（职责 / 空行 / 一句约束+出处），`tests/test_*.py` 同样压短；`tools\launcher\ff-tool.ps1` 的 14 处推理型长注释按 C1–C7 改写，并**恢复 UTF-8 BOM**（无 BOM 时 PowerShell 5.1 按 cp936 解码，中文帮助会乱码）。
- **清理**：46 个探索脚本（`tools\probes\`、`compare-remote.mjs`、`gh-read.mjs`、`ffplugin-smoke.mjs`、`edit-probe.ps1`、`_verb-test.ps1`）移出工作树；`tools\launcher\logs\` 的 106 个日志删除，该目录与 `tools/launcher/out/`、`tools/launcher/*.json` 一并写入 `.gitignore`。
- **未做**：`docs/m1-design.md` 保留写作时的模块名，只在 §3.1 目录树后加了一段「当前名称」；类/函数级文档串未逐条压缩。

---

## 2. 待完成

### 2.1 M7 本地 Web UI（浏览部分已交付，见 §1.4）

有意没做的三项（理由都写在 `docs\web.md`）：左侧折叠实体树、`/`+`j/k` 键盘导航、客户端惰性渲染 —— 为守住「零 JavaScript、老式简单、少出 BUG」，改用「服务端分页 200 行 + 分类/路径过滤 + 链接跳转」替代。另有两项未做：详情页的**字段来源行号**与体检页的**点击定位到行**。

**编辑（依赖 M4 先落地，之后接进同一个 UI）**

- 类型感知的字段编辑器：枚举下拉、数字、布尔、字符串、多选；非法值就地拒绝。
- 未保存变更暂存 + **语义 diff** 预览；`--dry-run` 预览不写盘。
- 保存 = 追加一条事件日志记录；撤销 / 重做（`undo N` / `redo N`），可跨段。
- 冲突检测：文件被外部改动时提示并拒绝覆盖。
- 权限模式指示（read-only / workspace-write / danger-full-access），写操作逐次确认，拒绝即中止且不重试。
- 批量编辑（多选同字段改同一值）。
- 导入 / 导出（`export to=`、mod-zip 打包）与工程切换。
- 事件日志查看器：时间线、按段、回放与导出；基线快照 diff。

### 2.2 M4 编辑引擎（Web UI 编辑面板的前提）

- `set <实体> <字段>=<值>`，`add` / `remove`（重复单例表用下标寻址，`--dry-run` 不写盘，幂等）。
- 事件日志：JSONL，`.editor\log\<段起始本地时间>.jsonl`，静默 5 分钟封段。
- `undo N` 字节级还原；`.editor\baseline\` 快照。
- 保真：编码保持（UTF-8 那 16 个文件仍是 UTF-8、cp1252 仍是 cp1252、CRLF/LF 各自保持）、注释与游离文本保留、不可编码字符硬错误 `ExportEncodingError`。
- 一致性：引用校验与重命名引用链；写盘原子性（临时文件 + 原子改名）；并发写不交错。
- 权限三级（同 DSH 语义）+ 逐次审批 + 拒绝不重试 + fail-closed。
- 验收用例 B1–B20 已列（改对改准、保真、引用一致、回滚审计、权限失败模式、规模往返）。

### 2.3 M5 / M6 / M8

- **M5 工程文件**：`mod.toml`（模组元数据）、`mod_setting.toml`（对应 `mod.txt` 设置）、交叉引用缓存（各自 TOML）；工程导入 / 导出。
- **M6 打包**：mod-zip —— 包内是 `Mod/` 文件夹，README 与许可放包外；folder ↔ zip 往返无损（`export Vehicles` 599 文件的规模）。
- **M8 分发**：版本、更新与安装说明。

### 2.4 已知缺陷与风险（都在案）

- **选择器里含 `=` 会被 CLI 当成 `键=值` 吞掉**：原版 1840 个数据文件里 0 实例，已按行号核对并文档化；是否加守卫待定。
- **UTF-8 回退是否与引擎一致未验证**：需进游戏确认引擎是否按 UTF-8 读那 16 个文件。
- **导出会重排兄弟顺序**：**2026-10-11 已修** —— 导出改按文档出现顺序并保留布局，原版数据 1840/1840 逐字节一致，此风险消失。
- **入口不再是顶层脚本**：仓库顶层没有 `ff.py`，`main` 上的入口是模块 `core.cli`。
- **`Mod` 作用域**：`dist\Mods\sample-mod` 提供了带 `mod.toml` 的工程，`dist\.ff-editor.local.toml` 指向它，因此该布局下无需显式 `-Project`。
- **本机沙箱限制**：沙箱里 node 的 spawn 一律 EPERM，端到端 live 用例要提权才能跑（非沙箱环境不受影响）。

### 2.5 待决定

1. 下一步做哪件：**(a)** M4 编辑引擎（`set` + 事件日志 + `undo`，然后接进 Web UI）；**(b)** 把浏览部分补细（字段来源行号、体检点击定位到行、左侧折叠树）；**(c)** 别的（例如补一个最小 `mod.toml` fixture，让 `Mod` 作用域在各处都能点）。
2. 发行版 `dist\` 形状与工作区说明是否要打成带标签的发行版发布。

---

## 3. 已定裁决（不要反复推翻）

| 编号 | 内容 |
|---|---|
| D7 | 导出保真 = **XML 语义等价**，不追求字节相同（**2026-10-11 修订**：对有来源文本的文件升级为**逐字节复现原版**，原版数据 1840/1840 一致；语义等价仍是无来源文本 `.toml` 的底线） |
| D8 | 本地研究 / 测量脚本不入库 |
| D9 | schema 单独 PR |
| — | 不重建 13.2.0.0 枚举，复用 `enums_ext.txt`，未知枚举只警告 |
| — | AI 权限仿 DSH 三级 + 逐动作审批，拒绝即 fail-closed 不重试 |
| — | 实现语言 Python（兼容性优先）；一实体一文件，镜像原版 `Data` 树 |
| — | surnames 不建模、不打包；注释只客观注明功能与待实现 |
| — | 不做编辑功能前，CLI 一律只读；唯一写入口是 `export` / `ff_export` |
