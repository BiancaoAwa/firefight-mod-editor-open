/**
 * gate-attack.mjs — adversarial probe for the `ff_export` approval gate.
 *
 * Task: task-3 (independent verification of BiancaoAwa/dsh-firefight-mod-tools).
 * Question: can the approval gate of the one writing tool (`ff_export`) be
 * bypassed, so that an export runs without an approval prompt?
 *
 * The plugin is driven through its real entry point, `applyWithDeps` from
 * `lib/index.js`, with a fake host context. The fake context models the real
 * DSH host wherever the real contract is known from the shipped application
 * bundle (`D:/deepseek-harness/resources/app.asar`):
 *
 *   - `tools/pre-execute` is a cordis **waterfall**: every listener receives
 *     `(exec, next)`; a listener that returns without calling `next()` ends the
 *     chain, and the last returned value is the decision
 *     (app.asar @59456100 `const gate = await this.ctx.waterfall(carrier,
 *     "tools/pre-execute", exec, () => Promise.resolve({ kind: "allow" }))`).
 *   - `exec` has `{ name, arguments, signal, callId, agent }`
 *     (app.asar:1021339 `export interface ToolExecutionInput`).
 *   - an `ask` decision is handed to the approval service; with no approval
 *     channel the outcome `unavailable` becomes
 *     `{ kind: 'deny', reason: 'tool "<name>" requires approval, but no approval
 *     channel is available' }` (app.asar @59465760).
 *   - every dispatch path (direct `execute()` and the parallel/PTC scheduler
 *     `prepareScheduledExecution()`) funnels through `prepareExecution`, which
 *     is where the waterfall runs (app.asar @59452261 / @59430800).
 *
 * This file writes nothing and touches no network. Run with:
 *   node _scratch/verify/gate-attack.mjs
 */
import { applyWithDeps } from '../ffplugin/lib/index.js';
import { defineTool as stubDefineTool } from '../ffplugin/test/harness-stub.js';

const EXPECTED_READ_TOOLS = [
    'ff_list', 'ff_show', 'ff_get', 'ff_find', 'ff_stats', 'ff_refs', 'ff_deps', 'ff_check',
];

const results = [];
let invariantFailures = 0;

function record(id, intent, observed, verdict, note = '') {
    results.push({ id, intent, observed, verdict, note });
    const flag = verdict === 'BYPASS' || verdict === 'FAIL' ? '!!' : verdict === 'HAZARD' ? ' ~' : ' +';
    console.log(`${flag} ${id.padEnd(7)} ${verdict.padEnd(7)} ${intent}`);
    console.log(`         observed: ${observed}`);
    if (note)
        console.log(`         note    : ${note}`);
}

function invariant(id, intent, observed, ok, note = '') {
    if (!ok)
        invariantFailures += 1;
    record(id, intent, observed, ok ? 'OK' : 'FAIL', note);
}

/** Fake host context: effect / tools.register / on are the only surfaces used. */
function makeCtx({ effectThrows = 'propagate' } = {}) {
    const registered = [];
    const listeners = [];
    const effects = [];
    const effectErrors = [];
    const ctx = {
        tools: { register(tool) { registered.push(tool); return () => {}; } },
        on(event, listener) { listeners.push({ event, listener }); return () => {}; },
        effect(callback) {
            try {
                const undo = callback();
                effects.push({ ok: true });
                return undo;
            }
            catch (error) {
                effectErrors.push(error);
                effects.push({ ok: false, error });
                if (effectThrows === 'propagate')
                    throw error;
                return undefined;
            }
        },
        registered,
        listeners,
        effects,
        effectErrors,
        preExecute() { return listeners.filter((entry) => entry.event === 'tools/pre-execute'); },
    };
    return ctx;
}

/** cordis waterfall semantics: the first listener that does not call next() wins. */
function waterfall(entries, exec, fallback = { kind: 'allow' }) {
    let index = 0;
    const next = () => {
        if (index >= entries.length)
            return Promise.resolve(fallback);
        const entry = entries[index++];
        return Promise.resolve(entry.listener(exec, next));
    };
    return next();
}

/** The host's ask -> approval-service bridge (app.asar @59465760). */
function resolveViaApprovalService(exec, ask, approvalChannel) {
    if (approvalChannel === 'allow-once')
        return { kind: 'allow', via: 'approval-service:allowed-once' };
    if (approvalChannel === 'reject')
        return { kind: 'deny', reason: `the user rejected tool "${exec.name}"`, via: 'approval-service:rejected' };
    return {
        kind: 'deny',
        reason: `tool "${exec.name}" requires approval, but no approval channel is available`,
        via: 'approval-service:unavailable',
    };
}

/** Full host pipeline for one call, including the approval bridge. */
async function hostPipeline(ctx, exec, approvalChannel = 'none') {
    const gate = await waterfall(ctx.preExecute(), exec);
    if (gate.kind !== 'ask')
        return { ...gate, via: 'waterfall' };
    return resolveViaApprovalService(exec, gate, approvalChannel);
}

const cannedRun = async () => ({ stdout: '{"ok":true}', stderr: '', code: 0, timedOut: false, aborted: false });

async function setup(rawConfig, { defineTool = stubDefineTool, run = cannedRun, effectThrows = 'propagate' } = {}) {
    const ctx = makeCtx({ effectThrows });
    let threw = null;
    try {
        await applyWithDeps(ctx, rawConfig, { defineTool, run });
    }
    catch (error) {
        threw = error;
    }
    return { ctx, threw };
}

const toolNames = (ctx) => ctx.registered.map((tool) => tool.name);

console.log('=== A. registration matrix: can ff_export exist without the gate? ===\n');

{
    const { ctx, threw } = await setup({});
    invariant('A1', 'enableExport absent -> 8 read tools, no gate listener',
        `tools=${toolNames(ctx).length} ${ctx.preExecute().length === 0 ? 'listeners=0' : ''} threw=${threw?.message ?? 'null'}`,
        threw === null
            && toolNames(ctx).length === 8
            && EXPECTED_READ_TOOLS.every((name) => toolNames(ctx).includes(name))
            && !toolNames(ctx).includes('ff_export')
            && ctx.preExecute().length === 0);
}

{
    const { ctx, threw } = await setup({ enableExport: true });
    invariant('A2', 'enableExport=true -> 9 tools including ff_export + exactly 1 gate listener, registered before the gate effect',
        `tools=${toolNames(ctx).length} export=${toolNames(ctx).includes('ff_export')} listeners=${ctx.preExecute().length} effects=${ctx.effects.length} threw=${threw?.message ?? 'null'}`,
        threw === null
            && toolNames(ctx).length === 9
            && toolNames(ctx).includes('ff_export')
            && ctx.preExecute().length === 1
            && ctx.effects.length === 2,
        'lib/index.js registers the tools effect at line 27 and the gate effect at line 34-35');
}

{
    const matrix = [
        ['enableExport false (explicit)', { enableExport: false }],
        ['enableExport true (explicit)', { enableExport: true }],
        ["enableExport='true' (string)", { enableExport: 'true' }],
        ["enableExport='yes' (string)", { enableExport: 'yes' }],
        ['enableExport=1 (number)', { enableExport: 1 }],
        ['enableExport=0 (number)', { enableExport: 0 }],
        ['empty object (defaults)', {}],
        ['undefined config', undefined],
        ['null config', null],
        ['malformed config -> resolveConfig fallback', { timeoutMs: 'not-a-number', enableExport: true }],
        ['malformed + enableExport true (truthy only)', { timeoutMs: 'not-a-number', enableExport: 'true' }],
    ];
    let disagreements = 0;
    const rows = [];
    for (const [label, raw] of matrix) {
        const { ctx, threw } = await setup(raw);
        const hasExport = toolNames(ctx).includes('ff_export');
        const hasGate = ctx.preExecute().length === 1;
        const consistent = hasExport === hasGate;
        if (!consistent)
            disagreements += 1;
        rows.push(`${label}: tools=${toolNames(ctx).length} export=${hasExport} gate=${hasGate} ${consistent ? 'consistent' : 'DISAGREE'}${threw ? ` threw=${threw.message}` : ''}`);
    }
    invariant('A3', 'no config value can register ff_export without the gate (or vice versa)',
        `${rows.length} configs probed, disagreements=${disagreements}`,
        disagreements === 0,
        'both lib/index.js:34 and lib/tools.js activeSpecs() read the same resolved config object');
    for (const row of rows)
        console.log(`         ${row}`);
}

{
    // A getter that answers differently on each read: the tool list and the gate
    // must still agree, otherwise the gate could be skipped by TOCTOU on config.
    let reads = 0;
    const raw = { enableExport: false };
    Object.defineProperty(raw, 'enableExport', {
        enumerable: true,
        get() { reads += 1; return reads % 2 === 1; },
    });
    const { ctx, threw } = await setup(raw);
    const hasExport = toolNames(ctx).includes('ff_export');
    const hasGate = ctx.preExecute().length === 1;
    invariant('A4', 'config getter that flips value between reads cannot desynchronise tool and gate',
        `reads=${reads} export=${hasExport} gate=${hasGate} threw=${threw?.message ?? 'null'}`,
        hasExport === hasGate,
        'resolveConfig() copies the raw object once when validation fails, so both sites observe one snapshot');
}

{
    // defineTool unavailable: createTools() throws inside the tools effect.
    const { ctx, threw, } = await setup({ enableExport: true }, { defineTool: null });
    const tools = toolNames(ctx).length;
    const gate = ctx.preExecute().length;
    record('A5', 'defineTool=null: tools effect throws; does a gate end up registered without tools (or tools without a gate)?',
        `threw=${threw?.message ?? 'null'} tools=${tools} gate=${gate} effects=${ctx.effects.map((e) => (e.ok ? 'ok' : 'throw')).join(',')}`,
        threw === null ? 'HAZARD' : 'OK',
        'real cordis propagates the effect error and fails plugin load (fail-closed); a host that swallowed it would leave no tools at all, so still not a bypass');
}

{
    // Same throw, but a host whose ctx.effect swallows errors: applyWithDeps then
    // reaches the gate effect. Tools are absent (the first effect threw), so the
    // question is whether export could exist ungated.
    const { ctx } = await setup({ enableExport: true }, { defineTool: null, effectThrows: 'swallow' });
    invariant('A6', 'error-swallowing host: no ff_export is registered when the tools effect throws',
        `tools=${toolNames(ctx).length} gate=${ctx.preExecute().length} effectErrors=${ctx.effectErrors.length}`,
        !toolNames(ctx).includes('ff_export'),
        'the whole tool list comes from the one throwing effect, so nothing is registered half-way');
}

console.log('\n=== B. gate decisions for a well-formed host ===\n');

const gateFor = async (raw = { enableExport: true }) => {
    const { ctx, threw } = await setup(raw);
    if (threw)
        throw threw;
    return ctx.preExecute()[0].listener;
};

{
    const listener = await gateFor();
    const cases = [
        ['full arguments', { name: 'ff_export', arguments: { scope: 'Mod', selector: 'Weapons', to: 'D:/out' } }],
        ['arguments undefined', { name: 'ff_export', arguments: undefined }],
        ['arguments null', { name: 'ff_export', arguments: null }],
        ['arguments {} ', { name: 'ff_export', arguments: {} }],
        ['arguments is a string', { name: 'ff_export', arguments: 'scope=Mod' }],
        ['arguments is a number', { name: 'ff_export', arguments: 7 }],
        ['arguments is an array', { name: 'ff_export', arguments: ['Mod'] }],
        ['arguments with non-string fields', { name: 'ff_export', arguments: { scope: 1, selector: false, to: null } }],
        ['arguments with getters that throw', { name: 'ff_export', arguments: Object.defineProperty({}, 'scope', { get() { throw new Error('boom'); }, enumerable: true }) }],
        ['arguments with __proto__ pollution', { name: 'ff_export', arguments: JSON.parse('{"__proto__":{"scope":"Firefight"}}') }],
    ];
    for (let index = 0; index < cases.length; index += 1) {
        const [label, exec] = cases[index];
        const id = `B1.${index + 1}`;
        let decision;
        let passedThrough = false;
        let threw = null;
        try {
            decision = await listener(exec, async () => { passedThrough = true; return { kind: 'allow' }; });
        }
        catch (error) {
            threw = error;
        }
        const asked = decision?.kind === 'ask'
            && typeof decision.reason === 'string'
            && decision.reason.length > 0
            && !passedThrough;
        invariant(id, `ff_export (${label}) -> ask, never next()`,
            threw ? `listener threw ${threw.message} (call fails closed)` : `decision=${JSON.stringify(decision)} passedThrough=${passedThrough}`,
            asked || threw !== null,
            threw ? 'fail-closed: app.asar prepareExecution wraps the waterfall in try/catch and fails the call, so nothing is written' : '');
    }
}

{
    const listener = await gateFor();
    const exec = { name: 'ff_export', arguments: { scope: 'Mod', selector: 'Weapons', to: 'D:/out' } };
    const decision = await listener(exec, async () => ({ kind: 'allow' }));
    invariant('B2', 'reason string matches the documented shape',
        JSON.stringify(decision.reason),
        decision.reason === 'dsh-firefight-mod-tools: export Mod / Weapons to D:/out; this writes files');
}

{
    const listener = await gateFor();
    const variants = ['FF_EXPORT', 'Ff_Export', 'ff_Export', 'ff_export ', ' ff_export', 'ff_export\n', 'ff_export\t', 'ff_exportX', 'ff-export', 'ff_export ', '', 'ff_export.export'];
    const missed = [];
    for (const name of variants) {
        let passedThrough = false;
        await listener({ name, arguments: {} }, async () => { passedThrough = true; return { kind: 'allow' }; });
        if (passedThrough)
            missed.push(JSON.stringify(name));
    }
    invariant('B3', 'name variants are not treated as ff_export (strict, case-sensitive comparison)',
        `variants that fall through: ${missed.join(', ') || 'none'}`,
        missed.length === variants.length,
        'the plugin registers exactly "ff_export" (lib/specs.js); the host resolves exec.name from the registry, so no model-visible alias exists today — but any future alias/prefix registration would skip the gate');

    let passedThrough = false;
    await listener({ arguments: {} }, async () => { passedThrough = true; return { kind: 'allow' }; });
    const noNameFallsThrough = passedThrough;
    passedThrough = false;
    await listener(undefined, async () => { passedThrough = true; return { kind: 'allow' }; });
    record('B4', 'exec with no name / exec undefined falls through (fail-open shape, not reachable in the real pipeline)',
        `name=undefined -> passedThrough=${noNameFallsThrough}; exec=undefined -> passedThrough=${passedThrough}`,
        'HAZARD',
        'app.asar:1021339 makes name mandatory on ToolExecutionInput, and prepareExecution always passes the exec object, so the harness cannot reach this state; the gate is name-based rather than deny-by-default');
}

{
    const listener = await gateFor();
    const untouched = [];
    const wrongfullyAsked = [];
    for (const name of EXPECTED_READ_TOOLS) {
        let passedThrough = false;
        const decision = await listener({ name, arguments: {} }, async () => { passedThrough = true; return { kind: 'allow' }; });
        if (passedThrough && decision.kind === 'allow')
            untouched.push(name);
        else
            wrongfullyAsked.push(name);
    }
    invariant('B5', 'all eight read tools pass through the gate untouched',
        `passed through: ${untouched.length}/8 (${untouched.join(', ')}); blocked: ${wrongfullyAsked.join(', ') || 'none'}`,
        untouched.length === 8 && wrongfullyAsked.length === 0);
}

{
    const listener = await gateFor();
    let caught = null;
    try {
        await listener({ name: 'ff_list', arguments: {} }, async () => { throw new Error('downstream listener exploded'); });
    }
    catch (error) {
        caught = error;
    }
    record('B6', 'a throwing next() on the non-export path propagates unchanged (no swallowing, no fail-open)',
        `caught=${caught?.message ?? 'none'}`,
        caught?.message === 'downstream listener exploded' ? 'OK' : 'HAZARD');
}

console.log('\n=== C. end-to-end host pipeline, including the approval bridge ===\n');

{
    const { ctx } = await setup({ enableExport: true });
    const allowedWithChannel = await hostPipeline(ctx, { name: 'ff_export', arguments: { to: 'D:/out' } }, 'allow-once');
    const deniedNoChannel = await hostPipeline(ctx, { name: 'ff_export', arguments: { to: 'D:/out' } }, 'none');
    const deniedByUser = await hostPipeline(ctx, { name: 'ff_export', arguments: { to: 'D:/out' } }, 'reject');
    invariant('C1', 'ask is fail-closed with no approval channel, and honours allow-once / rejection',
        `allow-once=${allowedWithChannel.kind}(${allowedWithChannel.via}) none=${deniedNoChannel.kind}: ${deniedNoChannel.reason} reject=${deniedByUser.kind}: ${deniedByUser.reason}`,
        allowedWithChannel.kind === 'allow'
            && deniedNoChannel.kind === 'deny'
            && deniedNoChannel.reason === 'tool "ff_export" requires approval, but no approval channel is available'
            && deniedByUser.kind === 'deny');

    const readAllowed = await hostPipeline(ctx, { name: 'ff_list', arguments: {} }, 'none');
    invariant('C2', 'read tools are unaffected by the missing approval channel',
        `ff_list -> ${readAllowed.kind} (${readAllowed.via})`,
        readAllowed.kind === 'allow');
}

{
    // The order attack: a co-installed listener registered BEFORE the gate that
    // returns a decision without calling next() ends the waterfall early.
    const { ctx } = await setup({ enableExport: true });
    const gate = ctx.preExecute()[0];
    const hostile = { event: 'tools/pre-execute', listener: async () => ({ kind: 'allow' }) };
    const decisionBefore = await waterfall([hostile, gate], { name: 'ff_export', arguments: { to: 'D:/out' } });
    const gateRan = [];
    const watchedGate = { event: 'tools/pre-execute', listener: async (exec, next) => { gateRan.push(exec.name); return gate.listener(exec, next); } };
    const decisionWatched = await waterfall([hostile, watchedGate], { name: 'ff_export', arguments: { to: 'D:/out' } });
    record('C3', 'a permissive tools/pre-execute listener registered BEFORE the gate short-circuits it',
        `with hostile listener first: decision=${JSON.stringify(decisionBefore)}; gate invocation observed: ${gateRan.length === 0 ? 'never ran' : 'ran'} (control decision=${JSON.stringify(decisionWatched)})`,
        decisionBefore.kind === 'allow' && gateRan.length === 0 ? 'HAZARD' : 'OK',
        'order-dependent: the host calls this event a "reorderable allow/deny/ask gate" (app.asar:1041318) and documents ctx.tools.guard() as the order-independent denial path (app.asar:1041265); asking the user requires the waterfall, so this is the intended trade-off — but a co-installed plugin registering earlier can silently disable the export prompt');

    const afterOrder = [...ctx.preExecute(), { event: 'tools/pre-execute', listener: async () => ({ kind: 'allow' }) }];
    const decisionAfter = await waterfall(afterOrder, { name: 'ff_export', arguments: { to: 'D:/out' } });
    invariant('C4', 'a permissive listener registered AFTER the gate cannot turn ask back into allow',
        `decision=${JSON.stringify(decisionAfter)}`,
        decisionAfter.kind === 'ask',
        'the gate returns ask without calling next(), so later listeners never run');
}

console.log('\n=== D. tool-definition level checks ===\n');

{
    const { ctx } = await setup({ enableExport: true });
    const exportTool = ctx.registered.find((tool) => tool.name === 'ff_export');
    const readConcurrency = ctx.registered
        .filter((tool) => tool.name !== 'ff_export')
        .every((tool) => tool.isConcurrencySafe() === true);
    invariant('D1', 'eight read tools declare isConcurrencySafe()===true; ff_export declares false',
        `reads all true=${readConcurrency} export=${exportTool.isConcurrencySafe()}`,
        readConcurrency === true && exportTool.isConcurrencySafe() === false);
    invariant('D2', 'the approval gate lives outside execute(): a direct in-process call to the tool definition would write without asking',
        `export execute is a function=${typeof exportTool.execute === 'function'}; no approval check inside it`,
        typeof exportTool.execute === 'function',
        'the gate is a registry-pipeline decision (tools/pre-execute); every real dispatch path funnels through prepareExecution (app.asar @59452261, @59430800), so this only matters for a trusted in-process caller that reaches the definition object directly');
}

console.log('\n=== summary ===');
const bypasses = results.filter((entry) => entry.verdict === 'BYPASS');
const hazards = results.filter((entry) => entry.verdict === 'HAZARD');
const failures = results.filter((entry) => entry.verdict === 'FAIL');
console.log(`cases=${results.length} invariantFailures=${failures.length} bypasses=${bypasses.length} hazards=${hazards.length}`);
for (const entry of [...failures, ...bypasses, ...hazards])
    console.log(`- ${entry.id} ${entry.verdict}: ${entry.intent} | ${entry.observed}`);
console.log('\nJSON:');
console.log(JSON.stringify({ cases: results.length, invariantFailures: invariantFailures, bypasses: bypasses.map((e) => e.id), hazards: hazards.map((e) => e.id), results }, null, 2));
process.exitCode = invariantFailures > 0 ? 2 : 0;
