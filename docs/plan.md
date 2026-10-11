> Language: **English** | [中文](plan.zh-CN.md)

# Update plan: the MVP slice first, then the AI MCP surface

This document turns the outstanding items in
[firefight-editor-feature-list.md](m3-notes/firefight-editor-feature-list.md) §2 into an ordered plan and
fixes the smallest complete editing capability the editor ships first. The stage numbers S1–S9 are local
to this document; the milestone table in [project-layout.md](project-layout.md) §9 still defines what
M0–M8 mean, and the mapping is given in §3.

## 1. Goal and MVP definition

**D10 — MVP definition.** The minimum complete capability is one full editing loop: read a document,
change one field, validate the result, leave an audit record, and be able to undo it. The loop must hold
on a real mod project, preserve bytes outside the edited field, and be auditable afterwards. It excludes
packaging, the web editing panel, and batch edits. In milestone terms this is the first slice of M4:
`set` plus the event log plus `undo`.

**D11 — assignment syntax.** The existing parser treats every token containing `=` as a `key=value`
option ([core/cli/main.py](../core/cli/main.py) `parse_argv`), and a selector containing `=` is swallowed
by that rule (known defect, feature list §2.4). The MVP therefore keeps the pure option form:

```
python -m core.cli Mod set <selector> field=<dotted.path> value=<value> [--dry-run] [--write]
```

The inline form shown in [project-layout.md](project-layout.md) §6
(`set Infantry/"…" description.quality=QUALITY_ELITE`) stays unimplemented; it needs a command-aware
parser. The implementation stage (S1) rewrites that §6 example to the form above.

**Decisions added by this document.** D10 and D11 above; D12–D16 are defined in [mcp.md](mcp.md) §2, §3
and §5 and summarised in §3 of this document. D1–D6 remain in
[project-layout.md](project-layout.md) §11, D7–D9 in
[firefight-editor-feature-list.md](m3-notes/firefight-editor-feature-list.md) §3. None of them is
reopened here.

## 2. MVP slice (what S1 + S2 deliver)

| Capability | Detail |
|---|---|
| `set` | Change exactly one field of one entity in one document. Addressing: selector = document path, `field=` = dotted path inside the document. |
| `--dry-run` | Compute and report the result; write nothing, including no log record. |
| Writer fidelity | Encoding and newline of the source are kept (16 UTF-8 documents stay UTF-8, cp1252 stays cp1252, CRLF stays CRLF and bare LF stays LF); comments, stray text and the layout of untouched elements are preserved; a value that the document encoding cannot represent fails hard with `ExportEncodingError` and no file is written. |
| Atomic write | Write to a temporary file in the target directory, then `os.replace` over the original. No partial file is observable. |
| Concurrency | `.editor/lock` (O_EXCL, contains pid and a timestamp) refuses a second writer instead of interleaving. Stale locks are reported, not silently removed. |
| External-change guard | The file fingerprint recorded when staging is re-checked before the write; a file changed outside the editor is refused, never overwritten. |
| Permission gate | The CLI stays read-only by default. `set` and `undo` require `--write` (the workspace-write tier). Writes are confined to the project directory (`Mod/` and `.editor/`); writing into the `Firefight` stock scope is refused unconditionally. A refusal is final: no retry, fail closed. |
| Event log | One JSONL record per write under `.editor/log/<segment start local time>.jsonl`, segments closing after 5 idle minutes (D4): segment, timestamp, actor (`cli` or `mcp`), document, entity, field, before, after, dry-run flag, result. |
| Baseline | The pre-image of each touched document is kept under `.editor/baseline/` so `undo` restores bytes, not a re-serialised approximation. |
| `log` | List segments and the records inside them; read-only. |
| `undo` / `redo` | `undo N` restores the pre-image of the last N writes in reverse order; `redo N` re-applies them. Fidelity criterion: `undo` → `redo` → `undo` returns byte-identical content (sha256 equal). |
| `check` | Runs on the edited project with no new findings caused by the edit (reference consistency). |

Out of scope for the MVP: `add` / `remove`, batch editing, rename chains, the web editing panel, project
import/export, mod-zip packaging, distribution.

## 3. Stages

Every stage is one pull request on top of the previous one, with its own tests and documentation update.
Stages S3–S6 have no dependency on S7–S9 and may be reordered if the project owner prefers.

| Stage | Content | Milestone | Depends on |
|---|---|---|---|
| **S1** | `set` engine: addressing, validation against the schema, fidelity writer, atomic write, lock, external-change guard, permission gate. No log yet. | M4 (first slice) | — |
| **S2** | Event log, `.editor/baseline/`, `log`, `undo`, `redo`. | M4 | S1 |
| **S3** | MCP server, read-only tools (`ff_list` … `ff_check`), single-source tool spec, protocol transcript tests. | M4/M7 aid | S1 (only for the spec table) |
| **S4** | MCP write tools `ff_set` and `ff_undo`, registered only when the server starts with `--write`. | M4 | S3 |
| **S5** | Web UI editing panel: staging, semantic diff preview, per-write confirmation, permission indicator, event-log viewer. | M7 | S2 |
| **S6** | `add` / `remove` on repeated tables by index, idempotency, batch edit of one field across a selection. | M4 | S2 |
| **S7** | M5 project files: `mod.toml`, `mod_setting.toml`, reference caches, project import/export. | M5 | S2 |
| **S8** | M6 packaging: mod-zip with `Mod/` inside, README/licence outside, folder ↔ zip round trip at the `export Vehicles` scale (599 files). | M6 | S7 |
| **S9** | M8 distribution: versioning, update and installation notes, release shape. | M8 | S8 |

**S1.** New command in [core/cli/commands.py](../core/cli/commands.py) plus a writer module that reuses
`_export_text` ([core/cli/commands.py](../core/cli/commands.py)) so the write path and the export path
agree byte for byte. Validation uses `core/schema.py`; a value outside an enumerated set is rejected
before any file is touched, with exit code 2. Acceptance: B1–B11, B17–B19, and B20 at reduced scale.

**S2.** Log records are appended with `jsonlines`-style writes under `.editor/log/`; the segment filename
is the local start time in the D4 format (`20261009T012000.jsonl`), so filename order is time order.
`undo` reads the log backwards, restores the recorded pre-image with the same atomic write, and appends
its own record with `actor` and `undone` pointing at the reverted record. Acceptance: B12–B16.

**S3.** `core/mcp/` is a stdio JSON-RPC server that imports `core.cli.commands.run_command` and calls it
in-process; it never spawns the CLI. Tools, resources and prompts are described in [mcp.md](mcp.md). A
snapshot test asserts that `tools/list` names and parameter names equal the plugin table in
`dsh-firefight-mod-tools` `lib/specs.js`. Acceptance: protocol transcripts, snapshot, read-only mode
exposes no write tool.

**S4.** Adds `ff_set` and `ff_undo`; they exist in `tools/list` only when the server was started with
`--write`. Refusal semantics are identical to the CLI: no partial write, no retry, error returned to the
caller with the CLI exit code preserved in the payload.

**S5.** Server-side rendering only, no JavaScript, matching the rules in [web.md](web.md): a form per
field type, a diff view computed from the staged document, and a confirmation step before the write.
The event-log viewer shows segments, records and a baseline comparison.

**S6.** `add` / `remove` address repeated tables by index; a repeated invocation with identical arguments
is a no-op; batch edit applies one field to a selection and produces one log record per document.

**S7–S9.** Project files, packaging and distribution follow
[project-layout.md](project-layout.md) §3–§5 and are otherwise unchanged by this plan.

## 4. Acceptance cases B1–B20

| No. | Case | Expected |
|---|---|---|
| B1 | `set` a string field on a project TOML document | Only that field changes; the rest of the file is byte-identical |
| B2 | `set` an enum field to a legal value from `enums_ext.txt` | Accepted; `check` reports no new findings |
| B3 | `set` an enum field to an illegal value | Rejected in place, exit code 2, file unchanged |
| B4 | `set` a numeric field | Value written in the document's own numeric style; untouched siblings keep layout |
| B5 | `set` a boolean field | Same as B4 for `true`/`false` |
| B6 | `set` on a cp1252 document | Bytes outside the edited field identical |
| B7 | `set` on a UTF-8 document | Stays UTF-8 without BOM |
| B8 | `set` on a CRLF document and on a bare-LF document | Newline style preserved in both |
| B9 | `set` beside comments and stray text | Comments and stray text survive verbatim |
| B10 | `set` a value unrepresentable in the document encoding | `ExportEncodingError`, exit code 1, nothing written |
| B11 | `--dry-run` | No file, no lock file and no log record is created (mtime and bytes unchanged) |
| B12 | Successful `set` | Exactly one JSONL record under `.editor/log/`, segment name per D4, all fields populated |
| B13 | `undo 1` after one `set` | sha256 of the document equals the pre-edit value |
| B14 | `undo` → `redo` → `undo` | Returns byte-identical content each time |
| B15 | `undo N` across a segment boundary | Records reverted in reverse chronological order, one log record per revert |
| B16 | Edit that changes a reference field | `check` stays clean, no dangling reference is introduced |
| B17 | Second writer while `.editor/lock` is held | Refused with a message naming the lock holder; no write |
| B18 | Document modified on disk after staging | Write refused; the on-disk change is preserved |
| B19 | `set` without `--write`, and any write aimed at the `Firefight` scope | Refused, exit code 2, no write, no log record |
| B20 | `set` on one field of a 599-file project | 598 files byte-identical, the edited file changed in one place, `check` clean |

## 5. Risks, hard constraints and assumptions

* **Baseline disk usage.** Keeping a pre-image per event grows `.editor/baseline/` linearly with edit
  count. `.editor/` travels with the project, is not packaged and is not committed (D5), so the growth is
  local; the 599-file project is the measuring case. If it becomes a problem, the fallback is one
  baseline per segment rather than per event.
* **Redo byte precision.** `redo` is specified as re-applying the recorded post-image. The criterion in
  B14 is byte equality; if an implementation cannot reach it, the plan requires recording post-images
  explicitly instead of recomputing them.
* **MCP protocol revision.** The revision a real client accepts is unverified. D14 prescribes a server
  that answers both the `initialize` handshake (2025-06-18, 2025-11-25) and the stateless 2026-07-28
  revision; the actual accepted revision is confirmed in S3 against a live client, and the result is
  recorded in [mcp.md](mcp.md).
* **Engine verification.** No case in B1–B20 can be verified inside the game from this environment; the
  UTF-8 fallback on the 16 documents remains unverified against the running engine (feature list §2.4).
* **Sandbox limits.** Node `spawn` is EPERM inside the sandbox, so live end-to-end cases run outside it;
  the MCP server therefore calls `run_command` in-process rather than spawning the CLI (D12).
* **No CI.** The repository has no workflow; every PR's evidence is a local run of
  `python -m unittest discover -s tests -t .` plus the diff.
* **Assumption.** Editing stays single-writer and interactive; multi-process concurrency is handled by
  refusal (B17), not by merging.

## 6. Definition of done per stage

1. The command or server entry point exists, with English comments limited to purpose, outstanding work
   (`# TODO(<milestone>):`) and known defects (`# KNOWN:`).
2. Tests cover the acceptance cases named for the stage; `python -m unittest discover -s tests -t .` is
   green and the count is recorded in the PR body.
3. Both language versions of the affected documents are updated in the same PR.
4. The PR body records the exact commands run and their observed results.
5. No absolute local path, user name, credential or machine-specific value enters the repository; the
   write paths are confined to a project directory.
