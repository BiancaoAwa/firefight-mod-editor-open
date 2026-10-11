> Language: **English** | [中文](mcp.zh-CN.md)

# AI MCP surface

This document specifies the MCP server that ships inside the editor repository. It describes the delivery
surfaces and how they overlap (§1), the transport and protocol revisions the server answers (§2), the tool
surface and its single source of truth (§3), resources and prompts (§4), permissions (§5), error mapping
(§6), entry point and client wiring (§7), how the server is tested (§8), and what it deliberately does not
do (§9). The server lands in implementation pull requests of its own.

## 1. Delivery surfaces and their boundaries

| Surface | Where it lives | How it reaches the editor | Intended use |
|---|---|---|---|
| Editor CLI | this repository, `core/cli/` | direct invocation | scripts, humans, the launcher `.cmd` files |
| DSH plugin `dsh-firefight-mod-tools` | separate repository | spawns the CLI as a subprocess | Day-to-day agent use inside DSH |
| MCP server | this repository, `core/mcp/` | in-process call of `run_command` | MCP clients outside DSH, and DSH itself through an MCP client entry |
| Skill (`SKILL.md`) | editor folder, not in the repository | prompt-level workflow over either of the above | reusable agent procedure |

**Ownership and shape.** The MCP server is part of the editor repository, under `core/mcp/`, with the
entry point `python -m core.mcp`. It is standard-library only, speaks stdio JSON-RPC, and calls
`core.cli.commands.run_command` in-process with a constructed `Context`, reusing `Result`. It never spawns
the CLI: an in-process call keeps the permission gate, the exit-code semantics and the JSON payload
identical to the command line.

**Overlap rule.** Tool names are the same across surfaces, so an MCP client that also installs the DSH
plugin exposes duplicate tool names. Do not enable both in one DSH session; use the plugin or the MCP
server, and say which one a workflow assumes.

## 2. Transport and protocol revision

**Revisions.** The server is stdio-only. It answers both protocol families, deciding from the first
request:

* **`initialize`** (revisions 2025-06-18 and 2025-11-25): the classic handshake, followed by
  `notifications/initialized`. The negotiated revision is echoed in the `initialize` result.
* **`server/discover`** (revision 2026-07-28, stateless): no handshake and no session identifier. Every
  request carries `_meta` with `io.modelcontextprotocol/protocolVersion`, `clientCapabilities` and
  `clientInfo`; every result carries `_meta.serverInfo` and an explicit `resultType` (`"complete"`, and
  `"input_required"` when the server needs more input). An unsupported version is answered with
  `UnsupportedProtocolVersionError` (`-32022`).

Implemented subset: `tools`, `resources` and `prompts`. Not implemented, and reported as
method-not-found rather than silently ignored: Streamable HTTP and SSE transports, OAuth or any other
authentication, `sampling`, `roots` and `logging` (deprecated upstream), tasks, and
`subscriptions/listen`. The accepted revision of any real client is a measured fact, recorded in §8.

## 3. Tool surface and the single source of truth

**Naming.** Tool names are byte-identical to the plugin table in `dsh-firefight-mod-tools`
`lib/specs.js`, and parameters keep the plugin's camelCase spelling, so one prompt or skill can move
between surfaces without renaming anything.

| Tool | Parameters | Writes | Registered |
|---|---|---|---|
| `ff_list` | `scope`, `selector`, `type`, `root`, `workspace` | no | always |
| `ff_show` | `scope`, `selector`, `as`, `root`, `workspace` | no | always |
| `ff_get` | `scope`, `selector`, `field`, `root`, `workspace` | no | always |
| `ff_find` | `scope`, `selector`, `tag`, `value`, `path`, `ignoreCase`, `limit`, `root`, `workspace` | no | always |
| `ff_stats` | `scope`, `selector`, `root`, `workspace` | no | always |
| `ff_refs` | `scope`, `selector`, `kind`, `root`, `workspace` | no | always |
| `ff_deps` | `scope`, `selector`, `kind`, `root`, `workspace` | no | always |
| `ff_check` | `scope`, `selector`, `root`, `workspace` | no | always |
| `ff_export` | `scope`, `selector`, `to`, `as`, `root`, `workspace` | yes | always (export is the existing write path) |
| `ff_set` | `scope`, `selector`, `field`, `value`, `dryRun`, `root`, `workspace` | yes | only with `--write` |
| `ff_undo` | `scope`, `selector`, `count`, `root`, `workspace` | yes | only with `--write` |

Later work adds `ff_add` and `ff_remove` with the same rule.

**One specification.** The CLI help, the web UI and the MCP tool table read one Python specification
table (candidate `core/cli/specs.py`) instead of three hand-written lists. A snapshot test asserts that
`tools/list` names, parameter names and required-ness equal the plugin table, and that read-only mode
exposes no write tool. Cross-repository consistency is enforced by that test plus this document; no shared
build is introduced.

## 4. Resources and prompts

| Kind | URI or name | Content |
|---|---|---|
| Resource | `firefight://{scope}/entity/{path}` | The document at `path`, rendered the same way `ff_show` renders it |
| Resource | `firefight://{scope}/list/{category}` | The entity paths of one category, as `ff_list` returns them |
| Resource | `firefight://{scope}/log` | The event-log segments of a project scope, read-only |
| Prompt | `firefight-editor-workflow` | The procedure in the editor-folder `skills/firefight-editor/SKILL.md`: locate the document, read it, stage a change, validate, confirm, write, verify |

Resources are read-only. Subscriptions are not implemented (2026-07-28 moved them to a long-lived
`subscriptions/listen` stream), so clients re-read a resource when they need it. Prompt arguments: `scope`,
`selector` and an optional `goal`.

## 5. Permissions and approval

**Permission gate.** The server starts read-only. `--write` puts it in the workspace-write tier.

* Read-only server: `tools/list` contains no write tool, and a direct call to one is refused as an unknown
  tool, not silently downgraded.
* Write-enabled server: writes are confined to the project directory (`Mod/` and `.editor/`). A write
  aimed at the `Firefight` stock scope is refused unconditionally; the installation is never modified.
* A refusal is final. The server does not retry, does not ask again in the same call, and reports the
  refusal to the caller; fail-closed behaviour matches the CLI.
* Every write appends an event-log record whose `actor` is `mcp`, so an audit trail distinguishes agent
  writes from command-line writes.
* Per-action approval belongs to the client: the MCP protocol has no approval primitive. DSH asks before
  each write; other clients are expected to gate the `ff_set`/`ff_undo` calls themselves, and the server's
  `--write` flag is the second, server-side gate.
* Moving to `danger-full-access` is out of scope for this plan.

## 6. Error mapping

| Situation | Response |
|---|---|
| Malformed JSON-RPC envelope | `-32600` invalid request |
| Unknown method or unknown tool name | `-32601` method not found |
| Missing or invalid parameter, resource not found | `-32602` invalid params (2026-07-28 moved resource-not-found here from `-32002`) |
| Unexpected server fault | `-32603` internal error |
| Write refused by the permission gate or by the scope rule | `-32000` |
| `.editor/lock` held by another writer | `-32001` |
| Document changed on disk after staging | `-32003` |
| Value not representable in the document encoding | `-32004` |
| Value rejected by the schema | `-32005` |

`-32000`–`-32019` are reserved for implementation-defined codes; `-32020`–`-32099` are specification
codes and are not reused. Errors raised by a command itself (a dangling reference, a syntax error) are
tool-level failures: the result carries `isError: true` and the payload keeps the CLI shape, including the
exit code (`0` success, `1` command failure, `2` usage refusal). The protocol channel and the tool channel
therefore stay distinguishable: a client can tell "the call failed" from "the call ran and reported a
problem".

## 7. Entry point and distribution

* Repository: `python -m core.mcp` (`core/mcp/__main__.py`), the same shape as `core/cli`.
* Editor folder (a release, not the repository): `ff-mcp.cmd` next to `ff-ai.cmd` and `ff-web.cmd`. It
  forwards its arguments to the module, writes nothing to stdout beyond the protocol, and never waits for
  a keypress.
* DSH wiring uses the MCP client entry of the profile: `transport: stdio`, `serverName`,
  `command` (the interpreter), `cwd` (the editor folder) and `args` (`-m core.mcp`, plus `--write` only
  when writes are wanted).
* Generic clients take the same three values in their own configuration block: command, working directory
  and arguments. No network listener, port or token is involved.

## 8. Tests and verification

1. **Transcript tests.** The suite starts the server as a subprocess, writes a scripted request sequence to
   its stdin and asserts the stdout lines: handshake in both protocol families, `tools/list`, one read-only
   tool call, one refused write, one malformed request.
2. **Snapshot test.** `tools/list` names, parameter names and required-ness equal
   `dsh-firefight-mod-tools` `lib/specs.js`; the tool-name set is asserted exactly, so a rename in either
   repository fails the test.
3. **Read-only mode.** No write tool appears in `tools/list`, and a direct write call is refused.
4. **Fail-closed.** A refused write leaves the file, the lock directory and the event log untouched.
5. **Live client check.** One manual session against a real MCP client, recording which protocol revision
   was accepted and the exact startup configuration. The result is appended to this section once that
   session runs; until then the accepted revision is unverified.

## 9. Non-goals

* No HTTP listener, SSE transport, port or token; no remote access.
* No authentication or authorisation layer beyond the `--write` gate.
* No sampling, roots, logging or task support.
* No resource subscriptions.
* No packaging of the server into a standalone binary; it runs from the editor folder with the bundled
  Python runtime.
