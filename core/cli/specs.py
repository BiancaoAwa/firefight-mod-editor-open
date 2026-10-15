"""The tool table shared by both AI surfaces: one specification per tool.

Tool names and parameter names are byte-identical to the plugin table in
``dsh-firefight-mod-tools`` ``lib/specs.js``, so one prompt or skill moves between the two
surfaces; ``tests/test_mcp.py`` compares the two tables (docs/mcp.md section 3).  The name
written down here is the canonical one; each surface exposes it behind its own prefix, so
this server answers to ``mcp_<name>`` and the plugin registers ``dsh_<name>``.  Each entry
is data: ``tools/list`` is rendered from it and a call turns the arguments into the Context
``core.cli.commands.run_command`` expects.
"""

from dataclasses import dataclass

SCOPE_DEFAULT = "Mod"
CONTENT_TYPES = ("string", "integer", "boolean")
TOOL_PREFIX = "mcp_"


@dataclass(frozen=True)
class Parameter:
    """One tool argument and where it lands in the CLI call.

    ``target`` is the positional slot (``scope``, ``selector``) or the option key the value
    is passed as; an empty target would name the option after the parameter.  ``allow_empty``
    marks the arguments whose empty string is a value rather than an omission.
    """

    name: str
    type: str
    description: str
    target: str = ""
    required: bool = False
    enum: tuple[str, ...] = ()
    allow_empty: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """One tool: the command it runs, its arguments and whether it writes.

    ``available`` marks a specification that is already written down but not exposed yet;
    a server refuses such a tool as unknown.
    """

    name: str
    command: str
    description: str
    parameters: tuple[Parameter, ...]
    writes: bool = False
    concurrency_safe: bool = True
    available: bool = True

    def inputs(self) -> dict:
        """The JSON Schema a client validates the arguments against."""
        properties = {}
        for parameter in self.parameters:
            schema: dict = {"type": parameter.type, "description": parameter.description}
            if parameter.enum:
                schema["enum"] = list(parameter.enum)
            properties[parameter.name] = schema
        return {
            "type": "object",
            "properties": properties,
            "required": [parameter.name for parameter in self.parameters if parameter.required],
            "additionalProperties": False,
        }

    def call(self, arguments: dict, *, defaults: dict | None = None) -> tuple[str, str, dict[str, str]]:
        """Turn tool arguments into the scope name, selector and options of one CLI call."""
        values = dict(defaults or {})
        values.update({name: value for name, value in arguments.items() if value is not None})
        scope = str(values.get("scope") or SCOPE_DEFAULT)
        selector = ""
        options: dict[str, str] = {}
        for parameter in self.parameters:
            if parameter.name not in values:
                continue
            value = values[parameter.name]
            if value is None or (value == "" and not parameter.allow_empty):
                continue
            if parameter.target == "scope":
                continue
            if parameter.target == "selector":
                selector = str(value)
                continue
            options[parameter.target] = _option_value(parameter, value)
        return scope, selector, options


def _option_value(parameter: Parameter, value) -> str:
    """One option as the CLI parses it: a bare flag is ``1``, everything else is text."""
    if parameter.type == "boolean":
        return "1" if value else "0"
    return str(value)


SCOPE = Parameter(
    "scope",
    "string",
    'Data scope: "Firefight" (stock game data), "Mod" (the mod project of the working '
    'directory) or another mod folder name. Defaults to "Mod".',
    target="scope",
)
ROOT = Parameter(
    "root",
    "string",
    "Scope root override, passed as root=<directory>. Defaults to the server option root=, "
    "otherwise the editor resolves the scope itself.",
    target="root",
)
WORKSPACE = Parameter(
    "workspace",
    "string",
    "Directory that holds Mod/, passed as workspace=<directory>. Defaults to the server "
    "option workspace= or the working directory.",
    target="workspace",
)
KIND = Parameter("kind", "string", "Reference kind filter, for example weapon or sound.", target="kind")
LIMIT = Parameter(
    "limit",
    "integer",
    "Row cap for the CLI text output (default 200; 0 prints every row).",
    target="limit",
)
DRY_RUN = Parameter(
    "dryRun",
    "boolean",
    "Report what would happen without writing anything, not even EditorCache/.",
    target="dry-run",
)
OVERWRITE = Parameter(
    "overwrite",
    "boolean",
    "Replace a file that is already there. The default belongs to the command: export and pack replace, convert and settings keep what is there.",
    target="overwrite",
)
STRICT = Parameter(
    "strict",
    "boolean",
    "pack: refuse to write the archive while the project has load errors or dangling references. Without it both are reported and the archive is still written.",
    target="strict",
)
ASSETS = Parameter(
    "assets",
    "boolean",
    "convert: also copy the scope's Images/ and Sounds/ trees into the project, byte for byte. Off by default, because a stock scope carries the game's own artwork.",
    target="assets",
)
SELECTOR = Parameter("selector", "string", "Optional folder or path prefix, for example Weapons or Data/Weapons.", target="selector")


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="ff_list",
        command="list",
        description=(
            "List the entities of a Firefight data scope with their category, on-disk format "
            "and size. Use it to find entity paths before ff_show, ff_get, ff_check or ff_export."
        ),
        parameters=(
            SCOPE,
            Parameter(
                "selector",
                "string",
                'Optional folder or path prefix, for example Weapons or Data/Weapons. A selector '
                'that contains "=" is read as key=value and widens the listing; rename such a folder.',
                target="selector",
            ),
            Parameter("type", "string", "Optional editor category filter, passed as type=<category>, for example weapon.", target="type"),
            ROOT,
            WORKSPACE,
        ),
    ),
    ToolSpec(
        name="ff_show",
        command="show",
        description=(
            "Show one Firefight entity as stored, or converted to TOML/XML. Warnings list every "
            "conversion the editor had to guess."
        ),
        parameters=(
            SCOPE,
            Parameter(
                "selector",
                "string",
                "Entity path, for example Data/Weapons/WEAPON_PISTOL_P38.txt, a category name, or a "
                "document path inside the file, for example Data/Weapons/WEAPON_PISTOL_P38.txt/ammo "
                "for a subtree.",
                target="selector",
                required=True,
            ),
            Parameter(
                "as",
                "string",
                "Rendering: raw is the file as stored, toml and xml are conversions. Defaults to raw.",
                target="as",
                enum=("raw", "toml", "xml"),
            ),
            ROOT,
            WORKSPACE,
        ),
    ),
    ToolSpec(
        name="ff_get",
        command="get",
        description="Read the values of one field from a Firefight document, with the document path and source line of each value.",
        parameters=(
            SCOPE,
            Parameter(
                "selector",
                "string",
                "Entity path, for example Data/Weapons/WEAPON_PISTOL_P38.txt; it may already end in "
                "the field path.",
                target="selector",
                required=True,
            ),
            Parameter("field", "string", "Dot-separated field path relative to the document root element, for example name or ammo.type.", target="field"),
            ROOT,
            WORKSPACE,
        ),
    ),
    ToolSpec(
        name="ff_find",
        command="find",
        description="Search the scope for a tag name, a value text or a document path prefix. Use it to locate where a token or tag is used.",
        parameters=(
            SCOPE,
            SELECTOR,
            Parameter("tag", "string", "Tag name to match, for example flavour.", target="tag"),
            Parameter("value", "string", "Value text to match, for example FLAVOUR_BALL.", target="value"),
            Parameter("path", "string", "Document path prefix to match, for example weapon/ammo.", target="path"),
            Parameter("ignoreCase", "boolean", "Match value text case-insensitively.", target="ignore_case"),
            LIMIT,
            ROOT,
            WORKSPACE,
        ),
    ),
    ToolSpec(
        name="ff_stats",
        command="stats",
        description="Count the files of a Firefight data scope by category, on-disk format and root element. Use it for an overview before a deep read.",
        parameters=(
            SCOPE,
            Parameter("selector", "string", "Optional folder or entity to measure instead of the whole scope.", target="selector"),
            ROOT,
            WORKSPACE,
        ),
    ),
    ToolSpec(
        name="ff_refs",
        command="refs",
        description="List the outgoing references of one entity or folder: which tokens it points at, with the document path of each reference.",
        parameters=(
            SCOPE,
            Parameter("selector", "string", "Entity path or folder, for example Data/Weapons/WEAPON_PISTOL_P38.txt.", target="selector", required=True),
            KIND,
            ROOT,
            WORKSPACE,
        ),
    ),
    ToolSpec(
        name="ff_deps",
        command="deps",
        description="List the incoming references of one token: every document that points at it. Use it before renaming or deleting an entity.",
        parameters=(
            SCOPE,
            Parameter("value", "string", "The token to look up, for example WEAPON_PISTOL_P38.", target="value", required=True, allow_empty=True),
            KIND,
            ROOT,
            WORKSPACE,
        ),
    ),
    ToolSpec(
        name="ff_check",
        command="check",
        description=(
            "Load a scope (or one entity or folder) and report load errors, conversion warnings "
            "and dangling references. A non-empty report is a result, not a tool failure."
        ),
        parameters=(
            SCOPE,
            Parameter("selector", "string", "Optional entity or folder to check instead of the whole scope.", target="selector"),
            ROOT,
            WORKSPACE,
        ),
    ),
    ToolSpec(
        name="ff_export",
        command="export",
        description="Render the entities of a Firefight scope as stock XML under a destination directory. This writes files; narrow it with selector and check the result.",
        parameters=(
            SCOPE,
            Parameter("selector", "string", "Optional entity or folder to export instead of the whole scope.", target="selector"),
            Parameter("to", "string", "Destination directory, passed as to=<directory>. The editor resolves relative paths against its working directory.", target="to", required=True),
            OVERWRITE,
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_set",
        command="set",
        description=(
            "Change one field of one project document, or add and remove one entry of an array "
            "of tables. This writes; a document that changed on disk is refused rather than "
            "overwritten."
        ),
        parameters=(
            SCOPE,
            Parameter("selector", "string", "Entity path of the document to change, for example Data/Weapons/WEAPON_PISTOL_P38.txt.", target="selector", required=True),
            Parameter("field", "string", "Dot-separated field path relative to the document root element, for example description.quality; an array entry is named by its index, for example ammo.type.0.", target="field", required=True),
            Parameter("value", "string", "Value to write, spelled the way the document spells it. Omit it when op is append or delete.", target="value", allow_empty=True),
            Parameter("op", "string", "append adds one entry to the array of tables field names, delete removes the entry the index in field names. Without it the value replaces the field.", target="op", enum=("append", "delete")),
            Parameter("from", "integer", "append only: copy the entry at this index instead of writing an empty one.", target="from"),
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_add",
        command="add",
        description="Create one project document, either empty for its root element or as the entry the index names. This writes; an existing document is refused.",
        parameters=(
            SCOPE,
            Parameter("selector", "string", "Path of the document to create, for example Data/Weapons/WEAPON_DEMO.toml.", target="selector", required=True),
            Parameter("type", "string", "Root tag of the new document, for example weapon. Defaults to the fixture a known stock path implies.", target="type"),
            Parameter("from", "integer", "Copy the entry at this index of the array of tables instead of writing an empty one.", target="from"),
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_remove",
        command="remove",
        description="Delete one project document and record its bytes so undo can put it back. This writes; a missing document is refused.",
        parameters=(
            SCOPE,
            Parameter("selector", "string", "Path of the document to delete, for example Data/Weapons/WEAPON_DEMO.toml.", target="selector", required=True),
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_index",
        command="index",
        description=(
            "Build the cross-reference tables of a project, EditorCache/index.toml and "
            "EditorCache/refs.toml, and report what ``check`` would find. This writes; without it "
            "ff_refs and ff_deps answer from a graph built on each run."
        ),
        parameters=(
            SCOPE,
            Parameter("selector", "string", "Optional entity or folder to index instead of the whole project.", target="selector"),
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_convert",
        command="convert",
        description=(
            "Turn the stock files of a scope into project working files under to=, one .toml per "
            "entity. This writes; a working file that is already there is skipped unless "
            "overwrite is true."
        ),
        parameters=(
            SCOPE,
            Parameter("selector", "string", "Optional entity or folder to convert instead of the whole scope.", target="selector"),
            Parameter("to", "string", "Destination project directory, passed as to=<directory>.", target="to", required=True),
            OVERWRITE,
            ASSETS,
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_settings",
        command="settings",
        description=(
            "Translate between the stock mod.txt of a project and its ModSetting.toml. "
            "op=render reads the stock file and writes the project file, op=emit writes the "
            "stock file back. This writes; a target that is already there is skipped unless "
            "overwrite is true."
        ),
        parameters=(
            SCOPE,
            Parameter(
                "op",
                "string",
                "render (default) for stock mod.txt to ModSetting.toml, emit for the other direction.",
                target="op",
                enum=("render", "emit"),
            ),
            OVERWRITE,
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_undo",
        command="undo",
        description="Put back what the last writes of a project replaced, newest change first. This writes; an undo past the log is refused.",
        parameters=(
            SCOPE,
            Parameter("count", "integer", "How many applied changes to revert; defaults to 1.", target="selector"),
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_redo",
        command="redo",
        description="Replay the changes the last undos put back, oldest first. This writes; a redo past the log is refused.",
        parameters=(
            SCOPE,
            Parameter("count", "integer", "How many undone changes to replay; defaults to 1.", target="selector"),
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_init",
        command="init",
        description=(
            "Create a project in a directory that need not be one yet: ModInformation.toml from the schema "
            "skeleton and an empty Data/. This writes; a directory that already carries a "
            "ModInformation.toml is refused."
        ),
        parameters=(
            SCOPE,
            Parameter("name", "string", "The mod name the new ModInformation.toml carries; the directory name otherwise.", target="name"),
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
    ToolSpec(
        name="ff_pack",
        command="pack",
        description=(
            "Build the installable mod-zip of a project: every document back as stock XML under "
            "the Mod/ prefix, ModSetting.toml written out as Mod/mod.txt, the project README and "
            "LICENSE at the archive root, EditorCache/ left out. This writes; an archive that is "
            "already there is replaced unless overwrite is false."
        ),
        parameters=(
            SCOPE,
            Parameter("to", "string", "Directory the archive goes into, passed as to=<directory>; the project directory by default.", target="to"),
            OVERWRITE,
            STRICT,
            DRY_RUN,
            ROOT,
            WORKSPACE,
        ),
        writes=True,
        concurrency_safe=False,
    ),
)


def tool_named(name: str) -> ToolSpec | None:
    """The specification of one tool, else ``None``."""
    for spec in TOOLS:
        if spec.name == name:
            return spec
    return None


def exposed_name(name: str) -> str:
    """The name a client sees: the canonical tool name behind this surface's prefix."""
    return f"{TOOL_PREFIX}{name}"


def canonical_name(name: str) -> str | None:
    """The canonical tool name an exposed one stands for, else ``None``."""
    if not name.startswith(TOOL_PREFIX):
        return None
    return name[len(TOOL_PREFIX):]


def registered(*, write: bool) -> tuple[ToolSpec, ...]:
    """The tools a server exposes: every reading tool, and the writing ones only with ``--write``."""
    return tuple(spec for spec in TOOLS if spec.available and (write or not spec.writes))
