/**
 * Independent end-to-end verification of dsh-firefight-mod-tools (task-2).
 *
 * Evidence chain: the argv this script computes from lib/specs.js + lib/runner.js
 * is the argv a PowerShell collector ran against the real ff.py (see the --emit-argv
 * mode and the `manual` column below). The real stdout/stderr of those runs lives in
 * export-out/_payloads/; this script validates it against the declared output schemas,
 * re-runs the lib/call.js normalization on the *real* CLI bytes, and drives
 * lib/runner.js through an injected spawn so the timeout/abort branches are covered
 * without spawning a child (this sandbox denies node -> python piped spawn with EPERM).
 *
 * Usage:
 *   node e2e-verify.mjs --emit-argv   # print the plugin-computed argv for the collector
 *   node e2e-verify.mjs               # run every check that does not need a real spawn
 */
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { buildArgs, createRunner, formatOption, resolveScript, resolveTimeoutMs, DEFAULT_TIMEOUT_MS, FfCliError } from '../ffplugin/lib/runner.js';
import { invokeCli, parsePayload } from '../ffplugin/lib/call.js';
import { ALL_SPECS, EXPORT_SPEC, READ_SPECS, discriminatorOf, outputContract } from '../ffplugin/lib/specs.js';
import { ERROR_SCHEMA, errorValue, renderShow } from '../ffplugin/lib/render.js';
import { createTools } from '../ffplugin/lib/tools.js';
import { validateSpec, validateValue } from '../ffplugin/test/harness-stub.js';

/**
 * The real host package, imported by absolute path: this script lives outside the
 * plugin tree, so a bare specifier would not resolve. `test/real-harness.test.js`
 * skips itself when this import fails; here it decides whether the strongest
 * checks (the ones that use the real validator) run at all.
 */
const HOST_TOOLS = 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\ffplugin\\node_modules\\@deepseek-ai\\dsh-tools\\lib\\index.js';
const PLUGIN_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'ffplugin');
let hostImportError;
const host = await import(pathToFileURL(HOST_TOOLS).href).catch((error) => {
    hostImportError = error;
    return undefined;
});

// --- environment constants (from the task description) ----------------------
const PY = 'C:\\Users\\BC_aw\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe';
const CLI = 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\m3-cli\\ff.py';
const M3 = 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\m3-cli';
const STOCK = 'D:\\Program Files (x86)\\Steam\\steamapps\\common\\Firefight';
const PROBE = 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\_probe-scope';
const PAYLOADS = 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\_payloads';
const OUT_DIR = 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out';
const P38 = 'Data/Weapons/WEAPON_PISTOL_P38.txt';

const CFG = {
    pythonPath: PY,
    scriptPath: CLI,
    firefightRoot: STOCK,
    workspace: '',
    cwd: M3,
    timeoutMs: 60000,
    maxOutputChars: 40000,
    enableExport: true,
};

const SPEC = Object.fromEntries(ALL_SPECS.map((spec) => [spec.name, spec]));
const stockRoot = `root=${STOCK}`;
const probeRoot = `root=${PROBE}`;

/** One captured case: plugin intent, the hand-written CLI equivalent, observed exit code. */
const CASES = [
    { name: 'list_weapons', tool: 'ff_list', exit: 0, args: { scope: 'Firefight', selector: 'Data/Weapons' }, manual: [CLI, 'Firefight', 'list', 'Data/Weapons', stockRoot, '--json'] },
    { name: 'list_missing_dir', tool: 'ff_list', exit: 0, args: { scope: 'Firefight', selector: 'Data/NoSuchDir' }, manual: [CLI, 'Firefight', 'list', 'Data/NoSuchDir', stockRoot, '--json'] },
    { name: 'list_garbage', tool: 'ff_list', exit: 0, args: { scope: 'Firefight', selector: 'zzz-nothing-matches' }, manual: [CLI, 'Firefight', 'list', 'zzz-nothing-matches', stockRoot, '--json'] },
    // 0.1.1 follow-up: ff_list no longer declares `limit` (the CLI ignores it). The case name and
    // its captured payload are kept for continuity; `args` still carries a stale `limit` to prove
    // the plugin drops it, and `prefixManual`/`prefixOption` record the only intentional delta.
    { name: 'list_weapons_limit5', tool: 'ff_list', exit: 0, args: { scope: 'Firefight', selector: 'Data/Weapons', limit: 5 }, manual: [CLI, 'Firefight', 'list', 'Data/Weapons', stockRoot, '--json'], prefixManual: [CLI, 'Firefight', 'list', 'Data/Weapons', stockRoot, 'limit=5', '--json'], prefixOption: 'limit=5' },
    { name: 'list_type_weapon', tool: 'ff_list', exit: 0, args: { scope: 'Firefight', type: 'weapon' }, manual: [CLI, 'Firefight', 'list', stockRoot, 'type=weapon', '--json'] },
    { name: 'list_file_spaces', tool: 'ff_list', exit: 0, args: { scope: 'Firefight', selector: 'Data/Vehicles/British-A13 Cruiser Mk III.txt' }, manual: [CLI, 'Firefight', 'list', 'Data/Vehicles/British-A13 Cruiser Mk III.txt', stockRoot, '--json'] },
    { name: 'show_raw', tool: 'ff_show', exit: 0, args: { scope: 'Firefight', selector: P38 }, manual: [CLI, 'Firefight', 'show', P38, stockRoot, '--json'] },
    { name: 'show_toml', tool: 'ff_show', exit: 0, args: { scope: 'Firefight', selector: P38, as: 'toml' }, manual: [CLI, 'Firefight', 'show', P38, stockRoot, 'as=toml', '--json'] },
    { name: 'show_xml', tool: 'ff_show', exit: 0, args: { scope: 'Firefight', selector: P38, as: 'xml' }, manual: [CLI, 'Firefight', 'show', P38, stockRoot, 'as=xml', '--json'] },
    { name: 'show_bad_as', tool: 'ff_show', exit: 2, args: { scope: 'Firefight', selector: P38, as: 'json' }, manual: [CLI, 'Firefight', 'show', P38, stockRoot, 'as=json', '--json'] },
    { name: 'show_list_file', tool: 'ff_show', exit: 0, config: { firefightRoot: PROBE }, args: { scope: 'Firefight', selector: 'Data/Surnames/surnames_probe.txt' }, manual: [CLI, 'Firefight', 'show', 'Data/Surnames/surnames_probe.txt', probeRoot, '--json'] },
    { name: 'get_name', tool: 'ff_get', exit: 0, args: { scope: 'Firefight', selector: P38, field: 'name' }, manual: [CLI, 'Firefight', 'get', P38, stockRoot, 'field=name', '--json'] },
    { name: 'get_ammo_type', tool: 'ff_get', exit: 0, args: { scope: 'Firefight', selector: P38, field: 'ammo.type' }, manual: [CLI, 'Firefight', 'get', P38, stockRoot, 'field=ammo.type', '--json'] },
    { name: 'get_missing_field', tool: 'ff_get', exit: 2, args: { scope: 'Firefight', selector: P38, field: 'no.such.field' }, manual: [CLI, 'Firefight', 'get', P38, stockRoot, 'field=no.such.field', '--json'] },
    { name: 'get_nothing', tool: 'ff_get', exit: 2, args: { scope: 'Firefight', selector: P38 }, manual: [CLI, 'Firefight', 'get', P38, stockRoot, '--json'] },
    { name: 'find_tag', tool: 'ff_find', exit: 0, args: { scope: 'Firefight', tag: 'name' }, manual: [CLI, 'Firefight', 'find', stockRoot, 'tag=name', '--json'] },
    { name: 'find_value', tool: 'ff_find', exit: 0, args: { scope: 'Firefight', value: 'WEAPON_PISTOL_P38' }, manual: [CLI, 'Firefight', 'find', stockRoot, 'value=WEAPON_PISTOL_P38', '--json'] },
    { name: 'find_path', tool: 'ff_find', exit: 0, args: { scope: 'Firefight', path: 'weapon/ammo' }, manual: [CLI, 'Firefight', 'find', stockRoot, 'path=weapon/ammo', '--json'] },
    { name: 'find_limit', tool: 'ff_find', exit: 0, args: { scope: 'Firefight', tag: 'name', limit: 5 }, manual: [CLI, 'Firefight', 'find', stockRoot, 'tag=name', 'limit=5', '--json'] },
    { name: 'find_ignorecase', tool: 'ff_find', exit: 0, args: { scope: 'Firefight', value: 'weapon_pistol_p38', ignoreCase: true }, manual: [CLI, 'Firefight', 'find', stockRoot, 'value=weapon_pistol_p38', 'ignore_case=1', '--json'] },
    { name: 'find_noselector', tool: 'ff_find', exit: 2, args: { scope: 'Firefight' }, manual: [CLI, 'Firefight', 'find', stockRoot, '--json'] },
    { name: 'stats_full', tool: 'ff_stats', exit: 0, args: { scope: 'Firefight' }, manual: [CLI, 'Firefight', 'stats', stockRoot, '--json'] },
    { name: 'stats_missing', tool: 'ff_stats', exit: 0, args: { scope: 'Firefight', selector: 'Data/NoSuchDir' }, manual: [CLI, 'Firefight', 'stats', 'Data/NoSuchDir', stockRoot, '--json'] },
    { name: 'refs_file', tool: 'ff_refs', exit: 0, args: { scope: 'Firefight', selector: P38 }, manual: [CLI, 'Firefight', 'refs', P38, stockRoot, '--json'] },
    { name: 'refs_dir', tool: 'ff_refs', exit: 0, args: { scope: 'Firefight', selector: 'Data/Weapons' }, manual: [CLI, 'Firefight', 'refs', 'Data/Weapons', stockRoot, '--json'] },
    { name: 'refs_kind', tool: 'ff_refs', exit: 0, args: { scope: 'Firefight', selector: P38, kind: 'weapon' }, manual: [CLI, 'Firefight', 'refs', P38, stockRoot, 'kind=weapon', '--json'] },
    { name: 'deps_resolved', tool: 'ff_deps', exit: 0, args: { scope: 'Firefight', value: 'WEAPON_PISTOL_P38' }, manual: [CLI, 'Firefight', 'deps', stockRoot, 'value=WEAPON_PISTOL_P38', '--json'] },
    // CORRECTION (task-4): the CLI really does filter on `kind` (`cli/commands.py`: `kind =
    // ctx.options.get("kind")` and `if reference.value == value and (kind is None or
    // reference.kind == kind)`), and the follow-up first dropped it — which the Lead reverted.
    // The vector is therefore back to the task-2 shape, `kind=weapon` included.
    { name: 'deps_kind', tool: 'ff_deps', exit: 0, args: { scope: 'Firefight', value: 'WEAPON_PISTOL_P38', kind: 'weapon' }, manual: [CLI, 'Firefight', 'deps', stockRoot, 'value=WEAPON_PISTOL_P38', 'kind=weapon', '--json'] },
    { name: 'deps_unresolved', tool: 'ff_deps', exit: 0, args: { scope: 'Firefight', value: 'NO_SUCH_TOKEN_XYZ' }, manual: [CLI, 'Firefight', 'deps', stockRoot, 'value=NO_SUCH_TOKEN_XYZ', '--json'] },
    { name: 'deps_novalue', tool: 'ff_deps', exit: 2, args: { scope: 'Firefight' }, manual: [CLI, 'Firefight', 'deps', stockRoot, '--json'] },
    { name: 'check_file', tool: 'ff_check', exit: 0, args: { scope: 'Firefight', selector: P38 }, manual: [CLI, 'Firefight', 'check', P38, stockRoot, '--json'] },
    { name: 'check_full', tool: 'ff_check', exit: 1, args: { scope: 'Firefight' }, manual: [CLI, 'Firefight', 'check', stockRoot, '--json'] },
    { name: 'export_file', tool: 'ff_export', exit: 0, args: { scope: 'Firefight', selector: P38, to: 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\single' }, manual: [CLI, 'Firefight', 'export', P38, stockRoot, 'to=D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\single', '--json'] },
    { name: 'probe_stats', tool: 'ff_stats', exit: 0, config: { firefightRoot: PROBE }, args: { scope: 'Firefight' }, manual: [CLI, 'Firefight', 'stats', probeRoot, '--json'] },
    { name: 'probe_check', tool: 'ff_check', exit: 1, config: { firefightRoot: PROBE }, args: { scope: 'Firefight' }, manual: [CLI, 'Firefight', 'check', probeRoot, '--json'] },
    { name: 'probe_refs', tool: 'ff_refs', exit: 0, config: { firefightRoot: PROBE }, args: { scope: 'Firefight', selector: 'Data/Good/ok.toml' }, manual: [CLI, 'Firefight', 'refs', 'Data/Good/ok.toml', probeRoot, '--json'] },
    { name: 'refs_probe_all', tool: 'ff_refs', exit: 0, config: { firefightRoot: PROBE }, args: { scope: 'Firefight', selector: 'Data' }, manual: [CLI, 'Firefight', 'refs', 'Data', probeRoot, '--json'] },
    { name: 'probe_find', tool: 'ff_find', exit: 0, config: { firefightRoot: PROBE }, args: { scope: 'Firefight', tag: 'name' }, manual: [CLI, 'Firefight', 'find', probeRoot, 'tag=name', '--json'] },
    { name: 'probe_export', tool: 'ff_export', exit: 1, config: { firefightRoot: PROBE }, args: { scope: 'Firefight', to: 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\probe-export' }, manual: [CLI, 'Firefight', 'export', probeRoot, 'to=D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\probe-export', '--json'] },
    { name: 'mod_no_project', tool: 'ff_list', exit: 2, args: { scope: 'Mod' }, manual: [CLI, 'Mod', 'list', '--json'] },
    // collected after the 0.1.1 fix, so they are excluded from the pre-fix golden vector below
    { name: 'list_selector_equals', tool: 'ff_list', exit: 0, postfix: true, config: { firefightRoot: PROBE }, args: { scope: 'Firefight', selector: 'Data/Good/eq=file.toml' }, manual: [CLI, 'Firefight', 'list', 'Data/Good/eq=file.toml', probeRoot, '--json'] },
    { name: 'list_good_dir', tool: 'ff_list', exit: 0, postfix: true, config: { firefightRoot: PROBE }, args: { scope: 'Firefight', selector: 'Data/Good' }, manual: [CLI, 'Firefight', 'list', 'Data/Good', probeRoot, '--json'] },
    { name: 'show_subtree', tool: 'ff_show', exit: 0, postfix: true, args: { scope: 'Firefight', selector: `${P38}/ammo` }, manual: [CLI, 'Firefight', 'show', `${P38}/ammo`, stockRoot, '--json'] },
    { name: 'show_as_raw', tool: 'ff_show', exit: 0, postfix: true, args: { scope: 'Firefight', selector: P38, as: 'raw' }, manual: [CLI, 'Firefight', 'show', P38, stockRoot, 'as=raw', '--json'] },
    // 0.1.1 follow-up: ff_export no longer declares `limit` (the CLI ignores it).
    { name: 'export_probe_limit1', tool: 'ff_export', exit: 1, postfix: true, config: { firefightRoot: PROBE }, args: { scope: 'Firefight', limit: 1, to: 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\probe-export-limit1' }, manual: [CLI, 'Firefight', 'export', probeRoot, 'to=D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\probe-export-limit1', '--json'], prefixManual: [CLI, 'Firefight', 'export', probeRoot, 'to=D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\probe-export-limit1', 'limit=1', '--json'], prefixOption: 'limit=1' },
    // Replays collected with the argv the 0.1.1 follow-up now computes (no limit=/kind= at all).
    // They are byte-compared against the pre-fix captures in section 6 to prove the CLI ignored them.
    { name: 'replay_list_dataweapons', tool: 'ff_list', exit: 0, postfix: true, args: { scope: 'Firefight', selector: 'Data/Weapons' }, manual: [CLI, 'Firefight', 'list', 'Data/Weapons', stockRoot, '--json'] },
    { name: 'replay_deps_value', tool: 'ff_deps', exit: 0, postfix: true, args: { scope: 'Firefight', value: 'WEAPON_PISTOL_P38' }, manual: [CLI, 'Firefight', 'deps', stockRoot, 'value=WEAPON_PISTOL_P38', '--json'] },
    { name: 'replay_export_probe', tool: 'ff_export', exit: 1, postfix: true, config: { firefightRoot: PROBE }, args: { scope: 'Firefight', to: 'D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\probe-export-limit1' }, manual: [CLI, 'Firefight', 'export', probeRoot, 'to=D:\\deepseek-harness\\WorkSpace\\firefight-mod-editor-open\\verify\\export-out\\probe-export-limit1', '--json'] },
    { name: 'show_equals_selector', tool: null, exit: 2, postfix: true, args: null, manual: [CLI, 'Firefight', 'show', 'Data/Good/eq=file.toml', probeRoot, '--json'] },
    { name: 'show_probe_noselector', tool: null, exit: 2, postfix: true, args: null, manual: [CLI, 'Firefight', 'show', probeRoot, '--json'] },
    { name: 'deps_kind_sound', tool: null, exit: 0, postfix: true, args: null, manual: [CLI, 'Firefight', 'deps', stockRoot, 'value=WEAPON_PISTOL_P38', 'kind=sound', '--json'] },
    { name: 'deps_kind_none', tool: null, exit: 0, postfix: true, args: null, manual: [CLI, 'Firefight', 'deps', stockRoot, 'value=WEAPON_PISTOL_P38', 'kind=__none__', '--json'] },
    { name: 'unknown_command', tool: null, exit: 2, args: null, manual: [CLI, 'Firefight', 'nosuchcmd', stockRoot, '--json'] },
    { name: 'help_json', tool: null, exit: 0, args: null, manual: [CLI, 'help', '--json'] },
    { name: 'no_positionals_json', tool: null, exit: 0, args: null, manual: [CLI, '--json'] },
];

// --- helpers ----------------------------------------------------------------
const results = [];
function check(name, ok, detail) {
    results.push({ name, ok: Boolean(ok), detail });
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail === undefined ? '' : ` — ${detail}`}`);
}
const notRun = [];
/** Record a check that could not run in this environment; it counts as neither pass nor fail. */
function skip(name, reason) {
    notRun.push({ name, reason });
    console.log(`SKIP  ${name} — ${reason}`);
}
function cfgOf(entry) {
    return { ...CFG, ...(entry.config ?? {}) };
}
function readCaptured(entry, kind) {
    const file = path.join(PAYLOADS, `${entry.name}.${kind === 'out' ? 'out.json' : 'err.txt'}`);
    if (!fs.existsSync(file))
        return undefined;
    const buffer = fs.readFileSync(file);
    if (buffer.length >= 2 && buffer[0] === 0xff && buffer[1] === 0xfe)
        return buffer.subarray(2).toString('utf16le');
    if (buffer.length >= 3 && buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf)
        return buffer.subarray(3).toString('utf8');
    return buffer.toString('utf8');
}
function schemaOf(tool) {
    return outputContract(SPEC[tool]);
}
function deepEqual(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
}
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

// --- mode: emit the argv the collector should run ---------------------------
if (process.argv.includes('--emit-argv')) {
    const emitted = CASES.map((entry) => {
        if (entry.args === null)
            return { name: entry.name, pyArgs: entry.manual };
        const call = SPEC[entry.tool].build(entry.args, cfgOf(entry));
        return { name: entry.name, pyArgs: buildArgs(resolveScript(cfgOf(entry)), call) };
    });
    console.log(JSON.stringify(emitted, null, 2));
    process.exit(0);
}

// --- mode: the one check this sandbox cannot run (needs a real child process) --
// `node e2e-verify.mjs --live` runs a REAL python process that outlives timeoutMs=1 and
// asserts that the timeout message reports the value the runner actually used. Node cannot
// spawn in the confined sandbox (EPERM at ChildProcess.spawn), so the Lead must run this.
if (process.argv.includes('--live')) {
    const sleepScript = path.join(OUT_DIR, 'sleep-probe.py');
    fs.writeFileSync(sleepScript, 'import time\ntime.sleep(5)\n', 'utf8');
    const liveCfg = { ...CFG, scriptPath: sleepScript, timeoutMs: 1 };
    const startedAt = Date.now();
    try {
        const live = await invokeCli(createRunner(liveCfg), liveCfg, { scope: 'Firefight', command: 'list', options: {} }, undefined);
        const elapsed = Date.now() - startedAt;
        const ok = live?.code === 'timeout' && live?.message === 'the editor CLI did not answer within 1 ms' && elapsed < 3000;
        console.log(`LIVE code=${live?.code} message=${JSON.stringify(live?.message)} elapsed=${elapsed}ms -> ${ok ? 'PASS' : 'FAIL'}`);
        process.exit(ok ? 0 : 1);
    }
    catch (error) {
        console.log(`LIVE could not run: ${error.name}: ${error.message}`);
        process.exit(2);
    }
}

// --- 1. argv assembly vs the hand-written CLI equivalent --------------------
console.log('\n=== 1. argv assembly (plugin buildArgs vs hand-written command) ===');
for (const entry of CASES) {
    if (entry.args === null) {
        check(`argv/hand ${entry.name} (CLI-only sample)`, true, entry.manual.join(' '));
        continue;
    }
    const cfg = cfgOf(entry);
    const call = SPEC[entry.tool].build(entry.args, cfg);
    const argv = buildArgs(resolveScript(cfg), call);
    check(`argv==hand ${entry.name}`, deepEqual(argv, entry.manual), deepEqual(argv, entry.manual) ? argv.slice(1).join(' ') : `plugin=${JSON.stringify(argv)} hand=${JSON.stringify(entry.manual)}`);
    check(`argv/--json-last ${entry.name}`, argv[argv.length - 1] === '--json');
}
const findFalse = buildArgs(CLI, SPEC.ff_find.build({ scope: 'Firefight', value: 'x', ignoreCase: false }, CFG));
check('argv/boolean-false -> ignore_case=0', findFalse.includes('ignore_case=0'), findFalse.slice(1).join(' '));
const findEmpty = buildArgs(CLI, SPEC.ff_find.build({ scope: 'Firefight', tag: 'x', selector: '', path: '', limit: undefined }, CFG));
check('argv/empty-values-dropped', !findEmpty.some((a) => a === 'path=' || a === 'limit=') && !findEmpty.includes(''), findEmpty.slice(1).join(' '));
const listDefault = buildArgs(CLI, SPEC.ff_list.build({ scope: 'Mod' }, CFG));
check('argv/Mod-nocarries-root', !listDefault.some((a) => a.startsWith('root=')), listDefault.slice(1).join(' '));
const listFF = buildArgs(CLI, SPEC.ff_list.build({ scope: 'Firefight' }, CFG));
check('argv/Firefight-injects-config-root', listFF.includes(stockRoot), listFF.slice(1).join(' '));
const namedRoot = buildArgs(CLI, SPEC.ff_list.build({ scope: 'SomeMod', root: 'D:\\mods\\SomeMod' }, CFG));
check('argv/explicit-root-wins-over-scope', namedRoot.includes('root=D:\\mods\\SomeMod') && !namedRoot.includes(stockRoot), namedRoot.slice(1).join(' '));
const wsCfg = { ...CFG, workspace: 'D:\\mods' };
const wsArgs = buildArgs(CLI, SPEC.ff_list.build({ scope: 'Mod' }, wsCfg));
check('argv/config-workspace-injected', wsArgs.includes('workspace=D:\\mods'), wsArgs.slice(1).join(' '));
check('argv/formatOption-boolean', formatOption(true) === '1' && formatOption(false) === '0' && formatOption(5) === '5');
for (const tool of Object.keys(SPEC)) {
    const problems = Object.entries(SPEC[tool].parameters).flatMap(([key, spec]) => validateSpec(spec, `${tool}.${key}`));
    check(`parameters/spec ${tool}`, problems.length === 0, problems.join('; ') || 'ok');
}

/*
 * Two argv freezes, deliberately kept apart.
 *
 * task-2 froze the whole pre-0.1.1 argv table as `70d089d8a7b8d3ab` and proved it was
 * byte-identical after the output-contract fix. The 0.1.1 follow-up changed argv on purpose
 * for two cases (`ff_list`/`ff_export` dropped `limit`, which the CLI ignores — proven with
 * discriminating values in section 6). `ff_deps` also lost `kind` for a while, but that was a
 * mistake (the CLI filters on `kind`) and it has been restored, so `deps_kind` is back in the
 * stable set. The table is re-frozen here with an exact delta record:
 *
 *   - `prefixManual`/`prefixOption` on a case is the pre-follow-up vector and the single
 *     option the follow-up removed. The delta check asserts the new vector equals the old
 *     one minus exactly that token.
 *   - the historical digest is *reconstructed* from the frozen prefix vectors plus those
 *     recorded deltas and must still equal `70d089d8a7b8d3ab`: that proves no other vector
 *     moved, and that the delta set is exactly the three recorded cases.
 *   - the current table is re-frozen under a new digest, so any future change is loud.
 */
const sha256 = (text) => createHash('sha256').update(text).digest('hex').slice(0, 16);
const preFixCases = CASES.filter((entry) => entry.postfix !== true);
const deltaCases = CASES.filter((entry) => entry.prefixManual !== undefined);
const stableCases = preFixCases.filter((entry) => entry.prefixManual === undefined);
const argvOf = (entry) => (entry.args === null ? entry.manual : buildArgs(resolveScript(cfgOf(entry)), SPEC[entry.tool].build(entry.args, cfgOf(entry))));
const entryOf = (name) => CASES.find((item) => item.name === name);
const FROZEN_PREFIX_VECTOR_SHA = '70d089d8a7b8d3ab';
const RE_FROZEN_PREFIX_VECTOR_SHA = 'd83bc31f25d7aef8';
const stableVector = JSON.stringify(stableCases.map((entry) => entry.manual));
check(`argv/prefix-vectors-stable (${stableCases.length} of ${preFixCases.length} pre-fix cases byte-identical to the task-2 golden)`, stableVector === JSON.stringify(stableCases.map(argvOf)), `plugin=${sha256(JSON.stringify(stableCases.map(argvOf)))}`);
for (const entry of deltaCases) {
    const argv = argvOf(entry);
    const without = entry.prefixManual.filter((token) => token !== entry.prefixOption);
    const removed = entry.prefixManual.length - argv.length;
    check(`argv/delta-${entry.name} (0.1.1 follow-up dropped ${entry.prefixOption})`, deepEqual(argv, entry.manual) && deepEqual(without, argv) && removed === 1, removed === 1 ? `only ${entry.prefixOption} removed` : `unexpected delta: removed=${removed}`);
}
const historicalVector = JSON.stringify(preFixCases.map((entry) => entry.prefixManual ?? entry.manual));
check(`argv/historical-prefix-golden-sha256 (${preFixCases.length} pre-fix cases, reconstructed)`, sha256(historicalVector) === FROZEN_PREFIX_VECTOR_SHA, `reconstructed=${sha256(historicalVector)} frozen=${FROZEN_PREFIX_VECTOR_SHA}`);
const currentVector = JSON.stringify(preFixCases.map(argvOf));
check(`argv/re-frozen-prefix-vector-sha256 (${preFixCases.length} pre-fix cases)`, sha256(currentVector) === RE_FROZEN_PREFIX_VECTOR_SHA, `plugin=${sha256(currentVector)} re-frozen=${RE_FROZEN_PREFIX_VECTOR_SHA}`);
for (const [tool, removed] of [['ff_list', 'limit'], ['ff_export', 'limit']])
    check(`parameters/${tool} no longer declares ${removed}`, SPEC[tool].parameters[removed] === undefined, `parameters=[${Object.keys(SPEC[tool].parameters).join(',')}]`);
check('parameters/ff_find still declares limit (the CLI honours it)', SPEC.ff_find.parameters.limit !== undefined);
check('parameters/ff_refs still declares kind (the CLI honours it)', SPEC.ff_refs.parameters.kind !== undefined);
check('parameters/ff_deps still declares kind (the CLI honours it, see the correction in section 6)', SPEC.ff_deps.parameters.kind !== undefined);
for (const spec of ALL_SPECS) {
    const keys = discriminatorOf(spec);
    check(`schema/discriminator ${spec.name}`, keys.length === 1 && !['status', 'code', 'message', 'guidance', 'detail'].includes(keys[0]), keys.join(',') || 'none');
}

// --- 2. output schema vs the real payloads ---------------------------------
console.log('\n=== 2. declared output schema vs real ff.py payload ===');
const captured = new Map();
for (const entry of CASES) {
    const stdout = readCaptured(entry, 'out');
    const stderr = readCaptured(entry, 'err');
    if (stdout === undefined)
        captured.set(entry.name, { missing: true });
    else
        captured.set(entry.name, { stdout, stderr: stderr ?? '', payload: parsePayload(stdout) });
}
let populated = 0;
for (const entry of CASES) {
    if (entry.tool === null)
        continue;
    const record = captured.get(entry.name);
    const label = `schema/${entry.name}`;
    if (record.missing) {
        check(label, false, 'no captured payload file');
        continue;
    }
    if (record.payload === undefined) {
        check(label, record.stdout.trim() === '', `stdout is not JSON and not empty? bytes=${record.stdout.length} (empty stdout -> handled by the error branch)`);
        continue;
    }
    populated += 1;
    const problems = validateValue(schemaOf(entry.tool), record.payload);
    check(label, problems.length === 0, problems.join('; ') || `accepted (exit ${entry.exit})`);
}
console.log(`captured payload files: ${[...captured.values()].filter((r) => r.missing).length} missing, ${populated} JSON payloads validated`);

// --- 3. lib/call.js normalization on the real CLI bytes ---------------------
console.log('\n=== 3. lib/call.js on the real captured stdout/stderr/exit ===');
for (const entry of CASES) {
    const record = captured.get(entry.name);
    if (record.missing)
        continue;
    const call = entry.args === null
        ? { scope: 'Firefight', command: 'help', selector: undefined, options: {} }
        : SPEC[entry.tool].build(entry.args, cfgOf(entry));
    const run = async () => ({ code: entry.exit, stdout: record.stdout, stderr: record.stderr, timedOut: false, aborted: false, argv: [] });
    const value = await invokeCli(run, CFG, call, undefined);
    const label = `call/${entry.name}`;
    if (record.payload !== undefined) {
        const ok = !deepEqual(value, undefined) && JSON.stringify(value) === JSON.stringify(record.payload);
        check(label, ok, ok ? `payload-first (exit ${entry.exit})` : `expected the JSON payload, got ${JSON.stringify(value).slice(0, 160)}`);
        continue;
    }
    const expected = entry.exit === 2 ? 'usage' : entry.exit === 0 ? 'empty-output' : 'cli-error';
    check(label, value?.status === 'error' && value.code === expected, `code=${value?.code} (expected ${expected}), detail=${JSON.stringify(value?.detail ?? '').slice(0, 90)}`);
}
// synthetic branches that the real CLI cannot produce in this sandbox
const runFrom = (result) => async () => result;
await (async () => {
    let thrown;
    try {
        await invokeCli(runFrom({ failure: new Error('spawn EPERM'), argv: [] }), CFG, { scope: 'Mod', command: 'list', options: {} }, undefined);
    }
    catch (error) {
        thrown = error;
    }
    check('call/spawn-failure-throws-FfCliError', thrown instanceof FfCliError, thrown?.message);
})();
const abortedValue = await invokeCli(runFrom({ aborted: true, code: null, stdout: '{}', stderr: '', timedOut: false, argv: [] }), CFG, { scope: 'Mod', command: 'list', options: {} });
check('call/aborted -> cancelled', abortedValue?.code === 'cancelled', JSON.stringify(abortedValue));
const timedOutValue = await invokeCli(runFrom({ timedOut: true, code: null, stdout: '', stderr: '', aborted: false, argv: [] }), CFG, { scope: 'Mod', command: 'list', options: {} });
check('call/timedOut -> timeout', timedOutValue?.code === 'timeout' && timedOutValue.message.includes('60000 ms'), JSON.stringify(timedOutValue));
const interrupt = await invokeCli(runFrom({ code: 130, stdout: '', stderr: 'interrupted', timedOut: false, aborted: false, argv: [] }), CFG, { scope: 'Mod', command: 'list', options: {} });
check('call/exit-130 -> cli-error (not cancelled)', interrupt?.code === 'cli-error', JSON.stringify(interrupt));
check('call/non-JSON stdout is never a result', parsePayload('ff <scope> <command>') === undefined && parsePayload('') === undefined && parsePayload('null') === null);

// --- 4. lib/runner.js timeout / abort / spawn-failure branches -------------
console.log('\n=== 4. lib/runner.js with an injected spawn ===');
function fakeSpawn(behavior = {}) {
    const calls = [];
    const spawnImpl = (command, args, options) => {
        calls.push({ command, args, options });
        if (behavior.throwError)
            throw new Error(behavior.throwError);
        const child = new EventEmitter();
        child.stdout = new EventEmitter();
        child.stderr = new EventEmitter();
        let closed = false;
        const close = (code) => {
            if (closed)
                return;
            closed = true;
            queueMicrotask(() => child.emit('close', code));
        };
        child.killed = false;
        child.kill = () => {
            child.killed = true;
            if (behavior.closeOnKill !== false)
                close(behavior.killCode ?? null);
        };
        if (behavior.stderr !== undefined)
            queueMicrotask(() => child.stderr.emit('data', behavior.stderr));
        if (behavior.stdout !== undefined)
            queueMicrotask(() => child.stdout.emit('data', behavior.stdout));
        if (behavior.errorOnStart !== undefined)
            queueMicrotask(() => child.emit('error', new Error(behavior.errorOnStart)));
        if (behavior.closeCode !== undefined)
            queueMicrotask(() => child.emit('close', behavior.closeCode));
        return child;
    };
    return { spawnImpl, calls };
}
{
    const { spawnImpl } = fakeSpawn({ throwError: 'spawn EPERM' });
    const run = createRunner(CFG, spawnImpl);
    const result = await run({ scope: 'Mod', command: 'list', options: {} });
    check('runner/spawn-throw -> failure not rejection', result.failure?.message === 'spawn EPERM' && Array.isArray(result.argv), JSON.stringify(result.argv));
}
{
    const { spawnImpl, calls } = fakeSpawn({ stdout: '{"a":1}', stderr: 'warn', closeCode: 0 });
    const result = await createRunner(CFG, spawnImpl)(SPEC.ff_list.build({ scope: 'Firefight' }, CFG));
    check('runner/captures stdout+stderr+code', result.code === 0 && result.stdout === '{"a":1}' && result.stderr === 'warn');
    check('runner/argv[0]=script, argv[1]=scope, argv[2]=command', calls[0].args[0] === CLI && calls[0].args[1] === 'Firefight' && calls[0].args[2] === 'list', calls[0].args.join(' '));
    check('runner/env pins utf-8', calls[0].options.env.PYTHONIOENCODING === 'utf-8' && calls[0].options.env.PYTHONUTF8 === '1');
    check('runner/stdio has no stdin and pipes the rest', deepEqual(calls[0].options.stdio, ['ignore', 'pipe', 'pipe']) && calls[0].options.windowsHide === true && calls[0].options.cwd === M3);
}
{
    const { spawnImpl } = fakeSpawn({ stdout: 'quiet', killCode: null });
    const result = await createRunner({ ...CFG, timeoutMs: 1 }, spawnImpl)({ scope: 'Mod', command: 'list', options: {} });
    check('runner/timeoutMs=1 -> timedOut', result.timedOut === true && result.aborted === false, JSON.stringify({ timedOut: result.timedOut, code: result.code }));
}
{
    const controller = new AbortController();
    controller.abort();
    const { spawnImpl } = fakeSpawn({ stdout: '', killCode: null });
    const result = await createRunner(CFG, spawnImpl)({ scope: 'Mod', command: 'list', options: {} }, { signal: controller.signal });
    check('runner/already-aborted signal -> aborted', result.aborted === true, JSON.stringify({ aborted: result.aborted, timedOut: result.timedOut }));
}
{
    const controller = new AbortController();
    const { spawnImpl } = fakeSpawn({ stdout: 'later', killCode: null });
    const promise = createRunner(CFG, spawnImpl)({ scope: 'Mod', command: 'list', options: {} }, { signal: controller.signal });
    controller.abort();
    const result = await promise;
    check('runner/abort-after-start -> aborted', result.aborted === true, JSON.stringify({ aborted: result.aborted }));
}
{
    const { spawnImpl } = fakeSpawn({ errorOnStart: 'EPERM', closeCode: undefined, closeOnKill: false });
    const result = await createRunner(CFG, spawnImpl)({ scope: 'Mod', command: 'list', options: {} });
    check('runner/child error event -> failure', result.failure?.message === 'EPERM', JSON.stringify(result.failure?.message));
}
{
    const { spawnImpl } = fakeSpawn({ stdout: '{"x":1}', closeCode: 0 });
    let failure;
    try {
        await createRunner({ ...CFG, scriptPath: '', editorRoot: '' }, spawnImpl)({ scope: 'Mod', command: 'list', options: {} });
    }
    catch (error) {
        failure = error;
    }
    check('runner/no script configured -> FfCliError', failure instanceof FfCliError, failure?.message);
}
{
    let failure;
    try {
        const run = createRunner(CFG, () => { throw new Error('unused'); });
        await run({ scope: 'Mod', command: 'list', options: {} });
    }
    catch (error) {
        failure = error;
    }
    check('runner/injected spawn is really used', failure === undefined);
}

// --- 5. the real host validator: the 0.1.1 output-contract fix ---------------
console.log('\n=== 5. @deepseek-ai/dsh-tools (real host) on the pre-fix and post-fix contracts ===');
const REAL_LIB = path.dirname(HOST_TOOLS);
if (host === undefined)
    skip('host/real-validator-importable', `the real host package could not be imported (${hostImportError?.code}: ${hostImportError?.message}); test/real-harness.test.js skips itself for the same reason, so no real-validator check could run in this sandbox`);
else {
    check('host/real-validator-importable', typeof host.validateJsonSchemaValue === 'function' && typeof host.defineTool === 'function', HOST_TOOLS);
    /** Compile one value schema with the real factory, exactly as lib/tools.js registers it. */
    const compile = (schema) => host.defineTool({
        name: 'ff_probe',
        description: 'contract probe',
        parameters: {},
        output: { schema, render: () => [] },
        execute: async () => undefined,
    }).output.schema;
    const violations = (schema, value) => host.validateJsonSchemaValue(schema, value, 'value');

    const openBoth = compile({ oneOf: [{ type: 'object', additionalProperties: true }, ERROR_SCHEMA] });
    const emptyOpen = violations(openBoth, { anything: 1 });
    check('host/oneOf demands exactly one branch (open object accepts anything)', emptyOpen.length === 0, emptyOpen.join('; ') || 'accepted');
    const probeError = errorValue('cli-error', 'x', 'y', 'z');
    const openError = violations(openBoth, probeError);
    check('host/an error value matches the open payload branch too (=> 2 branches)', openError.length > 0 && openError.join('; ').includes('must match exactly one oneOf branch'), openError.join('; '));

    /** The pre-0.1.1 payload branch: open object with no required property. */
    const legacyOutput = (spec) => ({
        ...spec.output,
        properties: Object.fromEntries(Object.entries(spec.output.properties).map(([key, child]) => {
            const { required, ...rest } = child;
            return [key, rest];
        })),
    });

    const registeredNames = [];
    for (const spec of ALL_SPECS) {
        const post = compile(outputContract(spec));
        const pre = compile({ oneOf: [legacyOutput(spec), ERROR_SCHEMA] });
        const discriminator = discriminatorOf(spec);
        check(`host/defineTool-compiles-discriminator ${spec.name}`, deepEqual(post.oneOf[0].required, discriminator), `compiled required=${JSON.stringify(post.oneOf[0].required)} declared=${JSON.stringify(discriminator)}`);
        const preError = violations(pre, probeError);
        check(`host/prefix-contract-rejects-the-plugin's-own-error-value ${spec.name}`, preError.length > 0, preError.join('; '));
        check(`host/postfix-contract-accepts-the-error-value ${spec.name}`, violations(post, probeError).length === 0, violations(post, probeError).join('; ') || 'accepted');
        const userCases = CASES.filter((entry) => entry.tool === spec.name);
        const payloads = userCases.map((entry) => captured.get(entry.name)).filter((record) => record !== undefined && record.payload !== undefined);
        const bad = payloads.flatMap((record) => violations(post, record.payload));
        check(`host/postfix-contract-accepts-real-payloads ${spec.name}`, bad.length === 0, bad.join('; ') || `${payloads.length} payload(s) accepted`);
    }

    const tools = createTools({ config: CFG, run: async () => ({ code: 0, stdout: '{}', stderr: '', timedOut: false, aborted: false, argv: [] }) }, host.defineTool);
    for (const tool of tools)
        registeredNames.push(tool.name);
    check('host/createTools registers 8 read tools + export with the real factory', registeredNames.length === 9 && registeredNames.includes('ff_export'), registeredNames.join(', '));
}

/*
 * 5b. Executable proof of the defect and of the fix, against the bundled stub.
 * The stub's oneOf rule ("exactly one branch") is the plugin's own model of the
 * host; 5c pins that model to the real validator source, which is why this is
 * evidence even though the real package cannot be imported here.
 */
{
    const probeError = errorValue('cli-error', 'probe failed', 'guidance text', 'detail text');
    /** The pre-0.1.1 payload branch: the open object with no required property. */
    const legacyOutput = (spec) => ({
        ...spec.output,
        properties: Object.fromEntries(Object.entries(spec.output.properties).map(([key, child]) => {
            const { required, ...rest } = child;
            return [key, rest];
        })),
    });
    for (const spec of ALL_SPECS) {
        const pre = validateValue({ oneOf: [legacyOutput(spec), ERROR_SCHEMA] }, probeError, spec.name);
        const post = validateValue(outputContract(spec), probeError, spec.name);
        const payloads = CASES.filter((entry) => entry.tool === spec.name).map((entry) => captured.get(entry.name)).filter((record) => record?.payload !== undefined);
        const bad = payloads.flatMap((record) => validateValue(outputContract(spec), record.payload, spec.name));
        check(`stub/prefix-contract-rejects-the-plugin's-own-error-value ${spec.name}`, pre.some((problem) => problem.includes('must match exactly one oneOf branch (matched 2)')), pre.join('; '));
        check(`stub/postfix-contract-accepts-the-error-value ${spec.name}`, post.length === 0, post.join('; ') || 'accepted');
        check(`stub/postfix-contract-accepts-real-payloads ${spec.name}`, bad.length === 0, bad.join('; ') || `${payloads.length} payload(s) accepted`);
        const empty = validateValue(outputContract(spec), {}, spec.name);
        check(`stub/postfix-contract-rejects-an-empty-object ${spec.name}`, empty.length > 0, empty.join('; '));
    }
}

/*
 * 5c. Pin the stub's rule to the real validator source (read, not executed —
 * the package needs peers that are not installed in this workspace).
 */
{
    const read = (file) => fs.readFileSync(path.join(REAL_LIB, file), 'utf8');
    const indexSrc = read('index.js');
    const validatorSrc = read(path.join('types', 'json-schema.js'));
    const authorSrc = read(path.join('types', 'schema.js'));
    const exactlyOne = 'frame.matches === 1 ? [] :';
    check('host-source/oneOf really means exactly one branch', validatorSrc.includes(exactlyOne) && indexSrc.includes(exactlyOne) && indexSrc.includes('must match exactly one oneOf branch'), 'lib/types/json-schema.js + lib/index.js');
    check('host-source/required is not a legal sibling of oneOf', /ONE_OF_SIBLING_KEYWORDS\s*=\s*\[[\s\S]{0,400}?"required"/.test(indexSrc) && /is not supported beside oneOf/.test(indexSrc), 'lib/index.js ONE_OF_SIBLING_KEYWORDS');
    check('host-source/the pipeline validates every tool output with that validator', indexSrc.includes('validateJsonSchemaValue(tool.output.schema'), 'lib/index.js');
    check('host-source/property-level required is hoisted into the parent', authorSrc.includes('task.property.required === true') && authorSrc.includes('task.required.push(task.key)') && authorSrc.includes('task.compiled.required = task.required'), 'lib/types/schema.js');
    check('host-source/the real README documents exact-one oneOf', fs.readFileSync(path.resolve(REAL_LIB, '..', 'README.md'), 'utf8').includes('exact-one `oneOf`'), 'node_modules/@deepseek-ai/dsh-tools/README.md');
}

// --- 6. independently reproduced findings (PASS means "confirmed", not "green") ---
console.log('\n=== 6. findings reproduced from the captured bytes (PASS = confirmed) ===');
{
    const full = captured.get('list_weapons');
    const limited = captured.get('list_weapons_limit5');
    check('finding/ff_list limit= has no effect (CLI ignores it)', full.stdout === limited.stdout && limited.payload.count === 716, `stdout identical (${full.stdout.length} bytes), count=${limited.payload.count} — a honoured limit=5 would have returned 5 rows`);
    const replay = captured.get('replay_list_dataweapons');
    check('fix/ff_list replay without limit= reproduces the same payload', replay.stdout === limited.stdout && replay.stdout === full.stdout, `replay sha16=${sha256(replay.stdout)}`);
}
{
    const limited = captured.get('export_probe_limit1');
    check('finding/ff_export limit= has no effect on what is written', limited.payload.count === 3, `limit=1 but count=${limited.payload.count}, files=${limited.payload.files.length}`);
    const replay = captured.get('replay_export_probe');
    check('fix/ff_export replay without limit= reproduces the same payload', replay.stdout === limited.stdout && replay.payload.count === 3, `replay sha16=${sha256(replay.stdout)} count=${replay.payload.count}`);
}
{
    // CORRECTION (task-4, raised by the Lead). `kind=weapon` vs "no kind" is NOT a discriminating
    // control: every one of the 1204 incoming references of this token is a weapon reference, so
    // identical bytes prove nothing about whether the CLI reads `kind`. Discriminating values
    // (`kind=sound`, `kind=__none__`) drop the count to 0 — the CLI does filter on `kind`.
    const withKind = captured.get('deps_kind');
    const withoutKind = captured.get('deps_resolved');
    const sound = captured.get('deps_kind_sound');
    const none = captured.get('deps_kind_none');
    check('finding/kind=weapon vs no kind shares sha256 but is NOT discriminating (all 1204 refs are weapon)', withKind.stdout === withoutKind.stdout && withKind.payload.count === 1204, `both ${withKind.stdout.length} bytes, count=${withKind.payload.count}`);
    check('finding/ff_deps kind= IS honoured (discriminating values change the count)', sound.payload.count === 0 && none.payload.count === 0 && withKind.payload.count === 1204 && withoutKind.payload.count === 1204, `kind=sound -> ${sound.payload.count}, kind=__none__ -> ${none.payload.count}, kind=weapon -> ${withKind.payload.count}, no kind -> ${withoutKind.payload.count}`);
    const replay = captured.get('replay_deps_value');
    check('fix/ff_deps without kind= still reproduces the no-kind payload', replay.stdout === withoutKind.stdout && replay.payload.count === 1204, `replay sha16=${sha256(replay.stdout)} count=${replay.payload.count}`);
    const argv = argvOf(entryOf('deps_kind'));
    check('fix/ff_deps keeps kind= in argv (the CLI filters on it)', argv.includes('kind=weapon'), argv.slice(1).join(' '));
}
{
    // CORRECTION (task-4): "read a `=`-named file with ff_show" is wrong advice — ff_show swallows
    // the `=` exactly like every other command, so it fails with the same "no selector" error.
    const eqShow = captured.get('show_equals_selector');
    const noSelector = captured.get('show_probe_noselector');
    const message = 'expected one file, got 4';
    check('finding/ff_show cannot read a "="-named file either (advice must be "rename")', entryOf('show_equals_selector').exit === 2 && eqShow.stdout === '' && eqShow.stderr.includes(message) && noSelector.stderr.includes(message), `show Data/Good/eq=file.toml -> exit ${entryOf('show_equals_selector').exit}, stderr=${JSON.stringify(eqShow.stderr.split('\n')[0])}`);
}
{
    const eq = captured.get('list_selector_equals');
    const control = captured.get('list_good_dir');
    check('finding/a selector containing "=" is swallowed as a key=value option', eq.payload.count === 4 && control.payload.count === 2 && eq.stderr === '', `Data/Good/eq=file.toml -> count=${eq.payload.count} (whole scope, expected 1); control Data/Good -> count=${control.payload.count}; CLI stderr=${JSON.stringify(eq.stderr)}`);
}
{
    // Confirmed defect in task-2, fixed by the 0.1.1 follow-up: the subtree answer is now declared
    // and rendered instead of printing `(undefined)` with an empty body.
    const sub = captured.get('show_subtree');
    const declared = Object.keys(SPEC.ff_show.output.properties ?? {});
    const rendered = renderShow({ selector: `${P38}/ammo` }, sub.payload);
    const lines = rendered.split('\n');
    const rows = lines.slice(1);
    const expectedHeader = `${sub.payload.path} ${sub.payload.key} · ${sub.payload.count} element · ${sub.payload.values.length} values`;
    check('fix/ff_show subtree branch is declared (key/count/values)', declared.includes('key') && declared.includes('count') && declared.includes('values') && declared.includes('path'), `declared=[${declared.join(',')}]`);
    check('fix/ff_show subtree renders elements and values', lines[0] === expectedHeader && rows.length === sub.payload.values.length && rows.every((row) => /^ {2}\S+:\d+ = /.test(row)) && !rendered.includes('undefined'), `header=${JSON.stringify(lines[0])} rows=${rows.length}`);
    check('fix/ff_show subtree payload still matches exactly one output branch', validateValue(schemaOf('ff_show'), sub.payload).length === 0, `count=${sub.payload.count} values=${sub.payload.values.length}`);
}
{
    // task-2 recorded: the message printed the RAW config.timeoutMs (so `undefined ms`).
    // The fix hoists the resolution into `resolveTimeoutMs(config)` and both `createRunner`
    // and the message use it, so the printed value can never disagree with the timer again.
    const timedOutRun = () => runFrom({ timedOut: true, code: null, stdout: '', stderr: '', aborted: false, argv: [] });
    const call = { scope: 'Mod', command: 'list', options: {} };
    const bare = { ...CFG, timeoutMs: undefined };
    const bareValue = await invokeCli(timedOutRun(), bare, call, undefined);
    check('fix/timeout message reports the resolved default instead of the raw config', bareValue?.code === 'timeout' && bareValue?.message === `the editor CLI did not answer within ${DEFAULT_TIMEOUT_MS} ms` && !String(bareValue?.message).includes('undefined'), JSON.stringify(bareValue?.message));
    const explicit = await invokeCli(timedOutRun(), { ...CFG, timeoutMs: 4321 }, call, undefined);
    check('fix/timeout message follows an explicit config.timeoutMs', explicit?.message === 'the editor CLI did not answer within 4321 ms' && explicit?.code === 'timeout', JSON.stringify(explicit?.message));
    const zero = await invokeCli(timedOutRun(), { ...CFG, timeoutMs: 0 }, call, undefined);
    const negative = await invokeCli(timedOutRun(), { ...CFG, timeoutMs: -5 }, call, undefined);
    const notNumber = await invokeCli(timedOutRun(), { ...CFG, timeoutMs: '60000' }, call, undefined);
    check('fix/non-positive or non-numeric timeoutMs falls back to the default in the message', zero?.message === `the editor CLI did not answer within ${DEFAULT_TIMEOUT_MS} ms` && negative?.message === `the editor CLI did not answer within ${DEFAULT_TIMEOUT_MS} ms` && notNumber?.message === `the editor CLI did not answer within ${DEFAULT_TIMEOUT_MS} ms`, `0="${zero?.message}" -5="${negative?.message}" "60000"="${notNumber?.message}"`);
    check('fix/resolveTimeoutMs is exported and matches the message path', resolveTimeoutMs({ timeoutMs: 250 }) === 250 && resolveTimeoutMs({}) === DEFAULT_TIMEOUT_MS && resolveTimeoutMs(undefined) === DEFAULT_TIMEOUT_MS && resolveTimeoutMs({ timeoutMs: NaN }) === DEFAULT_TIMEOUT_MS, `250->${resolveTimeoutMs({ timeoutMs: 250 })} none->${resolveTimeoutMs({})} NaN->${resolveTimeoutMs({ timeoutMs: NaN })}`);
    // The message and the timer must come from the same helper. Two independent pieces of
    // evidence: (1) a runner built with a fake child still fires the REAL 1 ms timer, and the
    // message reports exactly that value; (2) both call sites use `resolveTimeoutMs` in source.
    const { spawnImpl } = fakeSpawn({});
    const shortCfg = { ...CFG, timeoutMs: 1 };
    const liveStarted = Date.now();
    const live = await invokeCli(createRunner(shortCfg, spawnImpl), shortCfg, { scope: 'Firefight', command: 'list', options: {} }, undefined);
    const liveElapsed = Date.now() - liveStarted;
    check('fix/timeoutMs=1: the message reports what the runner actually used, and the real timer fired at 1 ms', live?.code === 'timeout' && live?.message === 'the editor CLI did not answer within 1 ms' && resolveTimeoutMs(shortCfg) === 1 && liveElapsed < 3000, `message=${JSON.stringify(live?.message)} code=${live?.code} resolveTimeoutMs=${resolveTimeoutMs(shortCfg)} elapsed=${liveElapsed}ms`);
    const runnerSrc = fs.readFileSync(path.resolve(PLUGIN_DIR, 'lib', 'runner.js'), 'utf8');
    const callSrc = fs.readFileSync(path.resolve(PLUGIN_DIR, 'lib', 'call.js'), 'utf8');
    check('fix/runner timer and call.js message share resolveTimeoutMs (no second resolution path)', /const timeoutMs = resolveTimeoutMs\(config\);/.test(runnerSrc) && /resolveTimeoutMs\(config\)\} ms/.test(callSrc) && /export function resolveTimeoutMs\(config\)/.test(runnerSrc), 'lib/runner.js:71 + lib/call.js:50 read the same exported helper');
    // The true live call needs a real child process, which the confined sandbox refuses.
    const sleepScript = path.join(OUT_DIR, 'sleep-probe.py');
    fs.writeFileSync(sleepScript, 'import time\ntime.sleep(5)\n', 'utf8');
    const liveCfg = { ...CFG, scriptPath: sleepScript, timeoutMs: 1 };
    const startedAt = Date.now();
    try {
        const spawned = await invokeCli(createRunner(liveCfg), liveCfg, { scope: 'Firefight', command: 'list', options: {} }, undefined);
        const elapsed = Date.now() - startedAt;
        check('fix/live timeoutMs=1 with a real python child', spawned?.code === 'timeout' && spawned?.message === 'the editor CLI did not answer within 1 ms' && elapsed < 3000, `message=${JSON.stringify(spawned?.message)} elapsed=${elapsed}ms`);
    }
    catch (error) {
        skip('fix/live timeoutMs=1 with a real python child', `node cannot spawn here (${error.name}: ${error.message}); run \`node e2e-verify.mjs --live\` with spawn permission`);
    }
}
{
    // The "=" gap is documented, and the documented workaround must be "rename only":
    // `ff_show` swallows the same selector (see the finding above), so advising it would be wrong.
    const paragraphOf = (text, needle) => {
        const line = text.split(/\r?\n/).find((item) => item.includes(needle)) ?? '';
        return line;
    };
    const readmeGap = paragraphOf(fs.readFileSync(path.resolve(PLUGIN_DIR, 'README.md'), 'utf8'), 'silently widens');
    const specGap = paragraphOf(fs.readFileSync(path.resolve(PLUGIN_DIR, 'lib', 'specs.js'), 'utf8'), 'silently widens');
    check('doc/the "=" gap is documented as rename-only, not "read it with ff_show"', readmeGap.includes('rename such a folder') && !readmeGap.includes('ff_show') && specGap.includes('rename such a folder') && !specGap.includes('ff_show'), `README=${JSON.stringify(readmeGap.trim().slice(-80))} specs.js=${JSON.stringify(specGap.trim().slice(-80))}`);
}
console.log('  (a PASS in this section confirms the described behaviour; it is not evidence that the plugin is correct)');

// --- summary ----------------------------------------------------------------
const failed = results.filter((item) => !item.ok);
console.log(`\nSUMMARY checks=${results.length} passed=${results.length - failed.length} failed=${failed.length} notRun=${notRun.length}`);
for (const item of failed)
    console.log(`  FAILED: ${item.name} — ${item.detail}`);
for (const item of notRun)
    console.log(`  NOT RUN: ${item.name} — ${item.reason}`);
process.exit(failed.length === 0 ? 0 : 1);
