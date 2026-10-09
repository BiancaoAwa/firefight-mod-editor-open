"""Scope resolution: ``Mod``, ``Firefight`` or a named mod folder to a data root.

A scope root is the directory that holds ``Data/``, ``Images/`` and ``Sounds/``,
the same shape for stock data and for a mod project, so one scope serves both.
Resolution order per scope is explicit option, environment, local config, then a
built-in default (docs/cli.md section 2).
"""

import os
from dataclasses import dataclass
from pathlib import Path

from core import tomlread
from core.tomlmodel import TomlTable, TomlValue

CONFIG_NAME = ".ff-editor.local.toml"
ENV_DATA = "FIREFIGHT_DATA"
ENV_MODS = "FIREFIGHT_MODS"
PROJECT_FILE = "mod.toml"
MOD_FOLDER = "Mod"
DATA_FOLDER = "Data"


class UsageError(Exception):
    """Bad invocation: unknown scope, missing option, unresolvable path."""


@dataclass(frozen=True)
class Scope:
    """One data root plus how it was found."""

    name: str
    root: Path
    origin: str

    @property
    def data(self) -> Path:
        return self.root / DATA_FOLDER

    def describe(self) -> str:
        return f"{self.name}: {self.root} ({self.origin})"


def load_config(cwd: Path) -> tuple[TomlTable | None, Path | None]:
    """Local config from the nearest ancestor directory, if any."""
    for directory in (cwd, *cwd.parents):
        path = directory / CONFIG_NAME
        if path.is_file():
            return tomlread.parse(path.read_text(encoding="utf-8"), str(path)), path
    return None, None


def config_value(config: TomlTable | None, key: str) -> str | None:
    """Read one string leaf out of the local config."""
    if config is None:
        return None
    entry = config.get(key)
    if isinstance(entry, TomlValue) and isinstance(entry.value, str):
        return entry.value
    return None


def resolve_scope(name: str, options: dict[str, str], cwd: Path) -> Scope:
    """Resolve one scope name into a data root."""
    config, config_path = load_config(cwd)
    if name == "Firefight":
        return _stock_scope(options, config, config_path, cwd)
    if name == "Mod":
        return _mod_scope(options, config, config_path, cwd)
    return _named_scope(name, options, config, cwd)


def resolve_all(options: dict[str, str], cwd: Path) -> dict[str, Scope]:
    """Every scope the invocation can name; missing ones stay absent."""
    found: dict[str, Scope] = {}
    for name in ("Mod", "Firefight"):
        try:
            found[name] = resolve_scope(name, options, cwd)
        except UsageError:
            continue
    workspace = _workspace_root(options, None, cwd)
    if workspace is not None:
        for directory in sorted((workspace / "Mods").glob("*")) if (workspace / "Mods").is_dir() else ():
            if directory.is_dir():
                try:
                    found[directory.name] = resolve_scope(directory.name, options, cwd)
                except UsageError:
                    continue
    return found


def _stock_scope(options: dict[str, str], config: TomlTable | None, config_path: Path | None, cwd: Path) -> Scope:
    explicit = options.get("root") or options.get("firefight")
    if explicit:
        return Scope("Firefight", _data_root(Path(explicit), "root="), "option root=")
    candidate = os.environ.get(ENV_DATA)
    if candidate:
        return Scope("Firefight", _data_root(Path(candidate), ENV_DATA), f"environment {ENV_DATA}")
    from_config = config_value(config, "firefight")
    if from_config:
        return Scope("Firefight", _data_root(Path(from_config), CONFIG_NAME), f"config {config_path}")
    editor = _editor_root(cwd)
    if editor is not None:
        bundled = editor / "Firefight" / DATA_FOLDER
        if bundled.is_dir():
            return Scope("Firefight", bundled.parent, f"editor copy {editor / 'Firefight'}")
    raise UsageError(
        "cannot find the stock Firefight data; set one of:\n"
        f"  root=<game directory>            (option, this invocation)\n"
        f"  {ENV_DATA}=<game directory>       (environment)\n"
        f"  firefight = \"<game directory>\"    (in {CONFIG_NAME})"
    )


def _mod_scope(options: dict[str, str], config: TomlTable | None, config_path: Path | None, cwd: Path) -> Scope:
    explicit = options.get("root") or options.get("mod")
    if explicit:
        return Scope("Mod", _project_data(Path(explicit)), "option root=")
    from_config = config_value(config, "mod")
    if from_config:
        return Scope("Mod", _project_data(Path(from_config)), f"config {config_path}")
    project = _project_root(cwd)
    if project is None:
        raise UsageError(
            f"cannot find a mod project here; run inside a project ({PROJECT_FILE}), "
            "or pass root=<project directory>"
        )
    return Scope("Mod", _project_data(project), f"project {project}")


def _named_scope(name: str, options: dict[str, str], config: TomlTable | None, cwd: Path) -> Scope:
    explicit = options.get("root")
    if explicit:
        return Scope(name, _data_root(Path(explicit), "root="), "option root=")
    direct = Path(name)
    if direct.is_dir():
        return Scope(name, _data_root(direct, name), "directory")
    workspace = _workspace_root(options, config, cwd)
    if workspace is None:
        raise UsageError(
            f"unknown scope {name!r}; known scopes are Mod and Firefight, and workspace mods need "
            f"workspace=<directory> or {ENV_MODS}"
        )
    for candidate in (workspace / "Mods" / name, workspace / name):
        if candidate.is_dir():
            return Scope(name, _data_root(candidate, name), f"workspace {workspace}")
    raise UsageError(f"mod {name!r} not found under {workspace / 'Mods'}")


def _workspace_root(options: dict[str, str], config: TomlTable | None, cwd: Path) -> Path | None:
    explicit = options.get("workspace") or os.environ.get(ENV_MODS)
    if explicit:
        return Path(explicit)
    from_config = config_value(config, "workspace")
    if from_config:
        return Path(from_config)
    return cwd


def _editor_root(cwd: Path) -> Path | None:
    """Nearest ancestor that looks like an editor checkout."""
    for directory in (cwd, *cwd.parents):
        if (directory / "core" / "__init__.py").is_file() and (directory / "cli" / "__init__.py").is_file():
            return directory
    return None


def _project_root(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if (directory / PROJECT_FILE).is_file():
            return directory
    return None


def _project_data(project: Path) -> Path:
    """A project keeps its data either under ``Mod/`` or at the project root."""
    if (project / MOD_FOLDER / DATA_FOLDER).is_dir():
        return project / MOD_FOLDER
    return _data_root(project, str(project))


def _data_root(path: Path, origin: str) -> Path:
    """Accept a data root, or the ``Data/`` directory itself."""
    resolved = path.resolve()
    if (resolved / DATA_FOLDER).is_dir():
        return resolved
    if resolved.name.lower() == DATA_FOLDER.lower() and (resolved / "Weapons").is_dir():
        return resolved.parent
    raise UsageError(f"{origin}: no {DATA_FOLDER}/ directory under {resolved}")


def split_spec(spec: str, scopes: dict[str, Scope] | None = None) -> tuple[str, str, tuple[str, ...]]:
    """Split ``Scope/path/to/file.toml/tag/tag`` into scope, path and document path."""
    parts = [part for part in spec.split("/") if part != ""]
    if not parts:
        raise UsageError("empty path")
    scope = parts[0]
    for index, part in enumerate(parts[1:], start=1):
        if part.endswith(".toml") or part.endswith(".txt"):
            return scope, "/".join(parts[1 : index + 1]), tuple(parts[index + 1 :])
    return scope, "/".join(parts[1:]), ()


def entity_files(scope: Scope, selector: str = "all") -> list[Path]:
    """Every entity file a selector names, sorted; empty selector means all."""
    data = scope.data
    if not data.is_dir():
        return []
    files = sorted(
        path for path in list(data.rglob("*.toml")) + list(data.rglob("*.txt"))
        if path.is_file()
    )
    if selector in ("", "all"):
        return files
    wanted = _selector_path(scope, selector)
    if wanted.is_file():
        return [wanted]
    if wanted.is_dir():
        return [path for path in files if wanted in path.parents or path.parent == wanted]
    return [path for path in files if _relative(scope, path).startswith(selector.strip("/"))]


def _selector_path(scope: Scope, selector: str) -> Path:
    for candidate in (scope.root / selector, scope.data / selector, scope.root / DATA_FOLDER / selector):
        if candidate.exists():
            return candidate
    return scope.data / selector


def _relative(scope: Scope, path: Path) -> str:
    try:
        return path.relative_to(scope.root).as_posix()
    except ValueError:
        return path.as_posix()
