/**
 * One spec per CLI command: model-facing description, parameter schema, call
 * builder and canonical output schema.
 *
 * Specs are plain data so they can be unit tested without the harness, and
 * `lib/tools.js` is the only place that turns them into registered tools.
 *
 * Output schemas stay OPEN (`additionalProperties: true`) on purpose: a newer
 * editor CLI that adds a field must not turn a valid payload into a failed
 * output validation. The error branch is closed, because this plugin owns it.
 */
import { renderCheck, renderDeps, renderExport, renderFind, renderGet, renderList, renderRefs, renderShow, renderStats } from './render.js';

/** Name of the writing tool; the plugin registers it only when export is enabled. */
export const EXPORT_TOOL_NAME = 'ff_export';

const str = (description) => ({ type: 'string', description });
const num = (description) => ({ type: 'integer', description });
const flag = (description) => ({ type: 'boolean', description });
const json = (description) => ({ type: 'json', description });
const dict = (description) => ({ type: 'object', additionalProperties: true, description });
const arr = (items, description) => ({ type: 'array', items, description });
const obj = (properties, description) => ({ type: 'object', additionalProperties: true, properties, description });

const SCOPE = str('Data scope: "Firefight" (stock game data), "Mod" (the mod project of the working directory) or another mod folder name. Defaults to "Mod".');
const ROOT = str('Scope root override, passed to the CLI as root=<directory>. Defaults to the plugin config: firefightRoot for Firefight, otherwise the editor CLI resolves it.');
const WORKSPACE = str('Directory that holds Mods/, passed as workspace=<directory>. Defaults to the plugin config or the CLI working directory.');
const LIMIT = num('Row cap for the CLI text output (CLI default 200). Some JSON payloads, for example ff_deps, are not limited by it.');
const KIND = str('Reference kind filter, for example weapon or sound.');

const ERROR_LIST = arr(json('One CLI-side diagnostic; usually a message string.'), 'Diagnostics the CLI collected while scanning, if any.');

const ENTITY = obj({
    path: str('Entity path relative to the scope root.'),
    category: str('Editor category, for example weapon.'),
    format: str('On-disk format, for example txt or xml.'),
    bytes: num('File size in bytes.'),
}, 'One entity of the scope.');

const REFERENCE = obj({
    source: str('Document that holds the reference.'),
    kind: str('Reference kind, for example weapon or sound.'),
    value: str('Referenced token.'),
    document_path: str('Path of the element inside its document.'),
}, 'One reference edge.');

const INCOMING = obj({
    source: str('Document that references the token.'),
    kind: str('Reference kind, for example weapon.'),
    document_path: str('Path of the element inside its document.'),
}, 'One incoming reference edge.');

const LIST_OUTPUT = obj({
    scope: str('Resolved scope name.'),
    root: str('Resolved scope root.'),
    count: num('Number of entities listed.'),
    entities: arr(ENTITY, 'Entities of the selection.'),
}, 'Entity listing.');

const SHOW_OUTPUT = obj({
    path: str('Document path.'),
    format: str('On-disk format.'),
    text: str('Document as stored; present when the CLI renders raw.'),
    toml: str('Document as TOML; present for as=toml.'),
    xml: str('Document as normalized XML; present for as=xml.'),
    warnings: arr(json('One conversion warning string.'), 'Conversion warnings, if any.'),
}, 'One rendered document.');

const GET_OUTPUT = obj({
    path: str('Document path.'),
    field: str('Field that was queried.'),
    count: num('Number of values found.'),
    values: arr(obj({
        path: str('Document path of the element that holds the value.'),
        line: num('One-based line in the source file.'),
        value: json('The value itself.'),
    }, 'One field value.'), 'Values in document order.'),
}, 'Field values of one document.');

const FIND_OUTPUT = obj({
    query: obj({
        tag: json('Tag name filter, if given.'),
        value: json('Value text filter, if given.'),
        path: json('Document path prefix filter, if given.'),
        ignore_case: flag('Whether the search ignored case.'),
    }, 'The query the CLI ran.'),
    count: num('Number of matches returned.'),
    truncated: flag('True when the CLI stopped at the limit.'),
    matches: arr(obj({
        path: str('Document that matched.'),
        line: num('One-based line in the source file.'),
        tag: str('Tag that matched.'),
        document_path: str('Path of the element inside its document.'),
        value: json('Value of the matched tag.'),
    }, 'One match.'), 'Matches in document order.'),
}, 'Search result.');

const STATS_OUTPUT = obj({
    scope: str('Resolved scope name.'),
    root: str('Resolved scope root.'),
    files: num('Number of files scanned.'),
    bytes: num('Total size in bytes.'),
    lists: num('Number of list files.'),
    by_category: dict('File count per editor category.'),
    by_format: dict('File count per on-disk format.'),
    by_root: dict('File count per root element.'),
    errors: ERROR_LIST,
}, 'Scope statistics.');

const REFS_OUTPUT = obj({
    scope: str('Resolved scope name.'),
    count: num('Number of outgoing references.'),
    by_kind: dict('Reference count per kind.'),
    references: arr(REFERENCE, 'Outgoing references.'),
    errors: ERROR_LIST,
}, 'Outgoing references of one selection.');

const DEPS_OUTPUT = obj({
    scope: str('Resolved scope name.'),
    value: str('Token that was queried.'),
    count: num('Number of incoming references.'),
    references: arr(INCOMING, 'Incoming references. This array is not limited by limit=.'),
    resolved: arr(str('Path of an entity the token resolved to.'), 'Entities the token resolved to; empty when it resolves to nothing.'),
    unresolved: flag('True when the token resolves to no entity.'),
    errors: ERROR_LIST,
}, 'Incoming references of one token.');

const CHECK_OUTPUT = obj({
    scope: str('Resolved scope name.'),
    files: num('Number of files considered.'),
    loaded: num('Number of files loaded successfully.'),
    skipped: num('Number of files skipped.'),
    errors: ERROR_LIST,
    warnings_total: num('Total number of warnings.'),
    warning_files: num('Number of files with warnings.'),
    warning_samples: arr(json('One warning sample.'), 'Sample warnings.'),
    dangling: arr(json('One dangling reference.'), 'References that point at nothing.'),
    ok: flag('True when the selection loaded without errors.'),
}, 'Load report.');

const EXPORT_OUTPUT = obj({
    scope: str('Resolved scope name.'),
    to: str('Destination directory, resolved by the CLI.'),
    count: num('Number of files written.'),
    files: arr(obj({
        path: str('Entity path inside the scope.'),
        out: str('Absolute path that was written.'),
        bytes: num('Bytes written.'),
        warnings: arr(json('One conversion warning.'), 'Warnings for this file.'),
    }, 'One written file.'), 'Written files.'),
    errors: ERROR_LIST,
}, 'Export result.');

/** Default scope of every tool: the mod the caller is working on. */
function scopeOf(args) {
    return typeof args.scope === 'string' && args.scope.length > 0 ? args.scope : 'Mod';
}

/**
 * `root=` is the scope root, so the configured stock directory only applies to the
 * `Firefight` scope; for `Mod` the CLI resolves the root from its working directory.
 */
function rootOption(args, config) {
    if (typeof args.root === 'string' && args.root.length > 0)
        return args.root;
    if (scopeOf(args) === 'Firefight' && typeof config?.firefightRoot === 'string' && config.firefightRoot.length > 0)
        return config.firefightRoot;
    return undefined;
}

/** Options shared by every command; empty values are dropped by the runner. */
function baseOptions(args, config) {
    return {
        root: rootOption(args, config),
        workspace: typeof args.workspace === 'string' && args.workspace.length > 0 ? args.workspace : config?.workspace,
    };
}

/** The eight read-only tools, in the order they are registered. */
export const READ_SPECS = [
    {
        name: 'ff_list',
        command: 'list',
        description: 'List the entities of a Firefight data scope with their category, on-disk format and size. Use it to find entity paths before ff_show, ff_get, ff_check or ff_export.',
        parameters: {
            scope: SCOPE,
            selector: str('Optional folder or path prefix, for example Weapons or Data/Weapons.'),
            type: str('Optional editor category filter, passed as type=<category>, for example weapon.'),
            limit: LIMIT,
            root: ROOT,
            workspace: WORKSPACE,
        },
        output: LIST_OUTPUT,
        render: renderList,
        concurrencySafe: true,
        build: (args, config) => ({ scope: scopeOf(args), command: 'list', selector: args.selector, options: { ...baseOptions(args, config), type: args.type, limit: args.limit } }),
    },
    {
        name: 'ff_show',
        command: 'show',
        description: 'Show one Firefight entity as stored, or converted to TOML/XML. Warnings list every conversion the editor had to guess.',
        parameters: {
            scope: SCOPE,
            selector: { ...str('Entity path, for example Data/Weapons/WEAPON_PISTOL_P38.txt, or a category name.'), required: true },
            as: { type: 'string', enum: ['raw', 'toml', 'xml'], description: 'Rendering: raw is the file as stored, toml and xml are conversions. Defaults to raw.' },
            root: ROOT,
            workspace: WORKSPACE,
        },
        output: SHOW_OUTPUT,
        render: renderShow,
        concurrencySafe: true,
        build: (args, config) => ({ scope: scopeOf(args), command: 'show', selector: args.selector, options: { ...baseOptions(args, config), as: args.as } }),
    },
    {
        name: 'ff_get',
        command: 'get',
        description: 'Read the values of one field from a Firefight document, with the document path and source line of each value.',
        parameters: {
            scope: SCOPE,
            selector: { ...str('Entity path, for example Data/Weapons/WEAPON_PISTOL_P38.txt; it may already end in the field path.'), required: true },
            field: str('Dot-separated field path relative to the document root element, for example name or ammo.type.'),
            root: ROOT,
            workspace: WORKSPACE,
        },
        output: GET_OUTPUT,
        render: renderGet,
        concurrencySafe: true,
        build: (args, config) => ({ scope: scopeOf(args), command: 'get', selector: args.selector, options: { ...baseOptions(args, config), field: args.field } }),
    },
    {
        name: 'ff_find',
        command: 'find',
        description: 'Search the scope for a tag name, a value text or a document path prefix. Use it to locate where a token or tag is used.',
        parameters: {
            scope: SCOPE,
            selector: str('Optional folder or entity to search inside.'),
            tag: str('Tag name to match, for example flavour.'),
            value: str('Value text to match, for example FLAVOUR_BALL.'),
            path: str('Document path prefix to match, for example weapon/ammo.'),
            ignoreCase: flag('Match value text case-insensitively.'),
            limit: LIMIT,
            root: ROOT,
            workspace: WORKSPACE,
        },
        output: FIND_OUTPUT,
        render: renderFind,
        concurrencySafe: true,
        build: (args, config) => ({ scope: scopeOf(args), command: 'find', selector: args.selector, options: { ...baseOptions(args, config), tag: args.tag, value: args.value, path: args.path, ignore_case: args.ignoreCase, limit: args.limit } }),
    },
    {
        name: 'ff_stats',
        command: 'stats',
        description: 'Count the files of a Firefight data scope by category, on-disk format and root element. Use it for an overview before a deep read.',
        parameters: {
            scope: SCOPE,
            selector: str('Optional folder or entity to measure instead of the whole scope.'),
            root: ROOT,
            workspace: WORKSPACE,
        },
        output: STATS_OUTPUT,
        render: renderStats,
        concurrencySafe: true,
        build: (args, config) => ({ scope: scopeOf(args), command: 'stats', selector: args.selector, options: baseOptions(args, config) }),
    },
    {
        name: 'ff_refs',
        command: 'refs',
        description: 'List the outgoing references of one entity or folder: which tokens it points at, with the document path of each reference.',
        parameters: {
            scope: SCOPE,
            selector: { ...str('Entity path or folder, for example Data/Weapons/WEAPON_PISTOL_P38.txt.'), required: true },
            kind: KIND,
            root: ROOT,
            workspace: WORKSPACE,
        },
        output: REFS_OUTPUT,
        render: renderRefs,
        concurrencySafe: true,
        build: (args, config) => ({ scope: scopeOf(args), command: 'refs', selector: args.selector, options: { ...baseOptions(args, config), kind: args.kind } }),
    },
    {
        name: 'ff_deps',
        command: 'deps',
        description: 'List the incoming references of one token: every document that points at it. Use it before renaming or deleting an entity.',
        parameters: {
            scope: SCOPE,
            value: { ...str('The token to look up, for example WEAPON_PISTOL_P38.'), required: true },
            kind: KIND,
            root: ROOT,
            workspace: WORKSPACE,
        },
        output: DEPS_OUTPUT,
        render: renderDeps,
        concurrencySafe: true,
        build: (args, config) => ({ scope: scopeOf(args), command: 'deps', selector: undefined, options: { ...baseOptions(args, config), value: args.value, kind: args.kind } }),
    },
    {
        name: 'ff_check',
        command: 'check',
        description: 'Load a scope (or one entity or folder) and report load errors, conversion warnings and dangling references. A non-empty report is a result, not a tool failure.',
        parameters: {
            scope: SCOPE,
            selector: str('Optional entity or folder to check instead of the whole scope.'),
            root: ROOT,
            workspace: WORKSPACE,
        },
        output: CHECK_OUTPUT,
        render: renderCheck,
        concurrencySafe: true,
        build: (args, config) => ({ scope: scopeOf(args), command: 'check', selector: args.selector, options: baseOptions(args, config) }),
    },
];

/** The one writing tool; registered only when `enableExport` is true, and always behind an approval prompt. */
export const EXPORT_SPEC = {
    name: EXPORT_TOOL_NAME,
    command: 'export',
    description: 'Render the entities of a Firefight scope as stock XML under a destination directory. This WRITES files; narrow it with selector and check the result.',
    parameters: {
        scope: SCOPE,
        selector: str('Optional entity or folder to export instead of the whole scope.'),
        to: { ...str('Destination directory, passed as to=<directory>. The CLI resolves relative paths against its working directory.'), required: true },
        limit: LIMIT,
        root: ROOT,
        workspace: WORKSPACE,
    },
    output: EXPORT_OUTPUT,
    render: renderExport,
    concurrencySafe: false,
    build: (args, config) => ({ scope: scopeOf(args), command: 'export', selector: args.selector, options: { ...baseOptions(args, config), to: args.to, limit: args.limit } }),
};

/** Every spec, whatever the current `enableExport` says. */
export const ALL_SPECS = [...READ_SPECS, EXPORT_SPEC];
