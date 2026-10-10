> Language: **English** | [中文](firefight-editor-feature-list.zh-CN.md)

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
- **Documentation languages (2026-10-11)**: each user-facing document is one English file with a Chinese mirror beside it — `README.md` / `README.zh-CN.md`, `docs/<name>.md` / `docs/<name>.zh-CN.md` (`cli`, `web`, `refs`, `project-layout`, `toml-mapping`) and `docs/m3-notes/firefight-editor-feature-list.md` / `.zh-CN.md`. Both files open with a one-line language switcher, the Chinese ones link to the Chinese mirror of every document they cite, and the DSH plugin README follows the same pair.
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

