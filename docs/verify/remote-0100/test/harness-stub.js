/**
 * Contract-faithful stand-in for `defineTool` and its schema validator.
 *
 * The real `@deepseek-ai/dsh-tools` is a host-provided peer whose own peer tree
 * is not installable from the public mirror, so the wiring tests run against this
 * module instead of skipping away. It is strict on purpose: it accepts exactly
 * the option shape the real definition declares (`lib/types/index.d.ts` of
 * 0.2.1-alpha.1) and rejects anything else, so a renamed or misspelled option
 * fails these tests rather than passing them.
 */

const ALLOWED_OPTIONS = new Set([
    'name', 'description', 'parameters', 'output', 'deferLoading', 'timeoutMs',
    'isConcurrencySafe', 'execute', 'projectContent', 'finalizeContent', 'presentCall', 'presentResult',
]);

const SCALAR_TYPES = new Set(['string', 'number', 'integer', 'boolean', 'null']);
const ALLOWED_TYPES = new Set([...SCALAR_TYPES, 'array', 'object', 'json']);

/** Validate one ValueSchemaSpec; returns a list of problems. */
export function validateSpec(spec, where) {
    const problems = [];
    if (spec === null || typeof spec !== 'object' || Array.isArray(spec)) {
        problems.push(`${where}: a value spec must be an object`);
        return problems;
    }
    if (typeof spec.description !== 'string' && spec.description !== undefined)
        problems.push(`${where}: description must be a string`);
    if (spec.oneOf !== undefined) {
        if (!Array.isArray(spec.oneOf) || spec.oneOf.length < 2)
            problems.push(`${where}: oneOf needs at least two branches`);
        else
            spec.oneOf.forEach((branch, index) => problems.push(...validateSpec(branch, `${where}.oneOf[${index}]`)));
        return problems;
    }
    if (!ALLOWED_TYPES.has(spec.type))
        problems.push(`${where}: unknown type ${JSON.stringify(spec.type)}`);
    if (spec.type === 'object' && typeof spec.additionalProperties !== 'boolean')
        problems.push(`${where}: an object spec must declare additionalProperties`);
    if (spec.type === 'array' && spec.items !== undefined)
        problems.push(...validateSpec(spec.items, `${where}.items`));
    if (spec.type === 'object' && spec.properties !== undefined) {
        for (const [key, child] of Object.entries(spec.properties))
            problems.push(...validateSpec(child, `${where}.properties.${key}`));
    }
    return problems;
}

/** Validate a value against a ValueSchemaSpec; returns a list of problems. */
export function validateValue(spec, value, where = 'value') {
    if (spec.oneOf !== undefined) {
        const branches = spec.oneOf.map((branch) => validateValue(branch, value, where));
        return branches.some((problems) => problems.length === 0) ? [] : [`${where}: matches no oneOf branch (${branches.map((problems) => problems[0]).join(' | ')})`];
    }
    if (spec.const !== undefined && value !== spec.const)
        return [`${where}: expected const ${JSON.stringify(spec.const)}`];
    if (Array.isArray(spec.enum) && !spec.enum.includes(value))
        return [`${where}: ${JSON.stringify(value)} is not one of ${spec.enum.join(', ')}`];
    switch (spec.type) {
        case 'json':
            return [];
        case 'string':
            return typeof value === 'string' ? [] : [`${where}: expected a string`];
        case 'boolean':
            return typeof value === 'boolean' ? [] : [`${where}: expected a boolean`];
        case 'number':
            return typeof value === 'number' ? [] : [`${where}: expected a number`];
        case 'integer':
            return Number.isInteger(value) ? [] : [`${where}: expected an integer`];
        case 'null':
            return value === null ? [] : [`${where}: expected null`];
        case 'array':
            if (!Array.isArray(value))
                return [`${where}: expected an array`];
            return spec.items === undefined ? [] : value.flatMap((item, index) => validateValue(spec.items, item, `${where}[${index}]`));
        case 'object': {
            if (value === null || typeof value !== 'object' || Array.isArray(value))
                return [`${where}: expected an object`];
            if (spec.additionalProperties === false) {
                const unknown = Object.keys(value).filter((key) => !(key in (spec.properties ?? {})));
                if (unknown.length > 0)
                    return [`${where}: unexpected properties ${unknown.join(', ')}`];
            }
            const problems = [];
            for (const [key, child] of Object.entries(spec.properties ?? {})) {
                if (!(key in value)) {
                    if (child.required === true)
                        problems.push(`${where}.${key}: missing required property`);
                    continue;
                }
                problems.push(...validateValue(child, value[key], `${where}.${key}`));
            }
            return problems;
        }
        default:
            return [`${where}: unknown type ${JSON.stringify(spec.type)}`];
    }
}

/**
 * The option shape the real `defineTool` accepts: `{ name, description,
 * parameters, output: { schema, render }, execute, isConcurrencySafe? }`.
 * @returns a tool definition object.
 */
export function defineTool(options) {
    if (options === null || typeof options !== 'object')
        throw new TypeError('defineTool needs an options object');
    for (const key of Object.keys(options)) {
        if (!ALLOWED_OPTIONS.has(key))
            throw new TypeError(`defineTool received an unknown option: ${key}`);
    }
    if (typeof options.name !== 'string' || !/^[a-z][a-z0-9_]*$/.test(options.name))
        throw new TypeError('defineTool needs a snake_case name');
    if (typeof options.description !== 'string' || options.description.length === 0)
        throw new TypeError(`${options.name} needs a description`);
    if (options.parameters === null || typeof options.parameters !== 'object')
        throw new TypeError(`${options.name} needs a parameters object`);
    const problems = [];
    for (const [key, spec] of Object.entries(options.parameters)) {
        problems.push(...validateSpec(spec, `${options.name}.parameters.${key}`));
        if (spec.required !== undefined && spec.required !== true)
            problems.push(`${options.name}.parameters.${key}: required is only allowed as true`);
    }
    if (options.output === null || typeof options.output !== 'object')
        throw new TypeError(`${options.name} needs an output object`);
    if (options.output.schema === undefined)
        throw new TypeError(`${options.name} needs output.schema`);
    problems.push(...validateSpec(options.output.schema, `${options.name}.output.schema`));
    if (typeof options.output.render !== 'function' || options.output.render.length < 2)
        problems.push(`${options.name}.output.render must be a function of (args, value)`);
    if (typeof options.execute !== 'function')
        throw new TypeError(`${options.name} needs an execute function`);
    if (options.isConcurrencySafe !== undefined && typeof options.isConcurrencySafe !== 'function')
        problems.push(`${options.name}.isConcurrencySafe must be a function`);
    if (problems.length > 0)
        throw new TypeError(`invalid tool definition:\n  ${problems.join('\n  ')}`);
    return {
        name: options.name,
        description: options.description,
        parameters: options.parameters,
        output: { schema: options.output.schema, render: options.output.render },
        isConcurrencySafe: options.isConcurrencySafe ?? (() => false),
        execute: options.execute,
    };
}
