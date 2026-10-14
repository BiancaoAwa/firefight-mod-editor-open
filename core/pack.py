"""Build the mod-zip out of one project.

The package carries the layout the game installs: every managed document is rendered back
to stock XML, files the editor does not manage are copied byte for byte,
``mod_setting.toml`` becomes ``Mod/mod.txt``, and the project's ``README.md`` and
``LICENSE`` sit at the archive root (docs/project-layout.md section 5).  ``.editor/`` never
enters the package.

Members are written with a fixed timestamp, so packing the same project twice produces the
same bytes; the packaging tests compare archives.

# TODO(pack): the stock-baseline comparison and APK packaging of docs/project-layout.md
# section 5 are not implemented; this builds the mod-zip only.
# KNOWN: a document that exists only as TOML is re-emitted canonically (tabs, CRLF, UTF-8);
# a stock .txt twin supplies the encoding but not the layout (impact: a source file whose
# endings or indentation differ from the canonical form is not reproduced byte for byte).
"""

from dataclasses import dataclass
import re
import zipfile
from pathlib import Path

from core.toml import TomlTable, TomlValue

ARCHIVE_SUFFIX = ".zip"
MOD_FOLDER = "Mod"
MOD_TXT = "mod.txt"
SETTING_FILE = "mod_setting.toml"
MANIFEST = "mod.toml"
ROOT_FILES = ("README.md", "LICENSE")
SKIP_DIRS = frozenset({".editor", "EditorCache"})
PROJECT_ONLY = frozenset({".ff-editor.local.toml", ".gitignore", ".gitattributes", "mod.toml"})
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class Piece:
    """One member of the package: its archive path and where the bytes come from."""

    name: str
    path: Path
    rendered: bool = False


def safe_name(text: str) -> str:
    """A single path component both Windows and the game accept, or ``""``."""
    cleaned = UNSAFE.sub("-", text).strip().strip(".")
    return re.sub(r"-{2,}", "-", cleaned)


def archive_name(name: str, version: str = "") -> str:
    """``<mod name>-<version>.zip`` (docs/project-layout.md section 5)."""
    base = f"{safe_name(name)}-{safe_name(version)}".strip("-")
    if not base:
        raise ValueError("the archive needs a mod name")
    return f"{base}{ARCHIVE_SUFFIX}"


def metadata(table: TomlTable) -> dict[str, str]:
    """``name`` and ``version_name`` out of a parsed ``mod.toml``."""
    section = table.get("mod")
    if not isinstance(section, TomlTable):
        return {}
    found: dict[str, str] = {}
    for key in ("name", "version_name"):
        value = section.get(key)
        if isinstance(value, TomlValue):
            found[key] = str(value.value)
    return found


def plan(project: Path) -> tuple[tuple[Piece, ...], tuple[dict[str, str], ...]]:
    """Classify a project into the members of its package and what was left out.

    A ``.toml`` document goes in as the stock ``.txt`` it stands for; a ``.txt`` beside a
    document is that document's stale twin and stays out; ``Mod/mod.txt`` is rendered from
    ``mod_setting.toml`` by the caller and is not a copy either; everything else under
    ``Mod/`` is copied as it stands.
    """
    root = project / MOD_FOLDER
    pieces: list[Piece] = []
    skipped: list[dict[str, str]] = []
    if root.is_dir():
        documents = {
            path.relative_to(root).with_suffix("").as_posix()
            for path in root.rglob("*")
            if path.suffix.lower() == ".toml"
        }
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            parts = relative.parts
            if any(part in SKIP_DIRS or part.startswith(".") for part in parts[:-1]):
                continue
            if path.name.startswith(".") or path.name in PROJECT_ONLY:
                skipped.append({"path": relative.as_posix(), "reason": "the editor's own file"})
                continue
            if path.suffix.lower() == ".toml":
                stem = relative.with_suffix("").as_posix()
                pieces.append(Piece(f"{MOD_FOLDER}/{stem}.txt", path, True))
                continue
            if relative.as_posix() == MOD_TXT:
                skipped.append(
                    {"path": relative.as_posix(), "reason": f"rendered from {SETTING_FILE}"}
                )
                continue
            if path.suffix.lower() == ".txt" and relative.with_suffix("").as_posix() in documents:
                skipped.append({"path": relative.as_posix(), "reason": "a toml document covers it"})
                continue
            pieces.append(Piece(f"{MOD_FOLDER}/{relative.as_posix()}", path, False))
    for name in ROOT_FILES:
        path = project / name
        if path.is_file():
            pieces.append(Piece(name, path, False))
    pieces.sort(key=lambda piece: piece.name)
    return tuple(pieces), tuple(skipped)


def build(members: list[tuple[str, bytes]], archive: Path) -> int:
    """Write the zip and return its size; the caller has already rendered every member."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, data)
    return archive.stat().st_size
