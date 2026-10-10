/**
 * Turns specs into registered tools. Kept apart from `index.js` so the tool shape
 * can be inspected in tests without loading the whole plugin.
 *
 * `@deepseek-ai/dsh-tools` is a peer the DSH host provides. It is imported
 * lazily so the repository stays testable on a machine where that peer's own peer
 * tree cannot be installed, and so a missing host package fails with a clear
 * message instead of a bare module-resolution error.
 */
import { invokeCli } from './call.js';
import { ERROR_SCHEMA, renderValue } from './render.js';
import { EXPORT_SPEC, READ_SPECS } from './specs.js';

let hostDefineTool;
try {
    ({ defineTool: hostDefineTool } = await import('@deepseek-ai/dsh-tools'));
}
catch {
    hostDefineTool = undefined;
}

/** Specs that are live for the current config. */
export function activeSpecs(config) {
    return config.enableExport === true ? [...READ_SPECS, EXPORT_SPEC] : [...READ_SPECS];
}

/**
 * Build the tool definitions.
 * @param state - `{ config, run }`; `run` is the CLI runner.
 * @param defineTool - harness tool factory; defaults to the host package.
 */
export function createTools(state, defineTool = hostDefineTool) {
    if (typeof defineTool !== 'function')
        throw new Error('@deepseek-ai/dsh-tools is unavailable: the DSH host provides this peer dependency');
    return activeSpecs(state.config).map((spec) => defineTool({
        name: spec.name,
        description: spec.description,
        parameters: spec.parameters,
        output: {
            schema: { oneOf: [spec.output, ERROR_SCHEMA] },
            render: (args, value) => renderValue(args, value, spec.render, state.config.maxOutputChars),
        },
        isConcurrencySafe: () => spec.concurrencySafe === true,
        execute: async (args, exec) => invokeCli(state.run, state.config, spec.build(args, state.config), exec),
    }));
}
