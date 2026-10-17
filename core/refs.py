"""Reference graph over entity documents: collection, index and target resolution.

``TargetIndex`` maps a leaf value onto the asset layout of one scope root (docs/refs.md).
"""

from dataclasses import dataclass
from pathlib import Path

from core.xml import XmlElement


@dataclass(frozen=True)
class RefRule:
    """A leaf tag that carries a target value, and where it is allowed to sit."""

    kind: str
    field: str
    parent: str | None = None
    skip_document_root: bool = False


# A weapon document's own <type> is a category enum, not a file reference, hence
# skip_document_root: only <type> nested below the root <weapon> is a slot.
REFERENCE_RULES: tuple[RefRule, ...] = (
    RefRule("weapon", "type", parent="weapon", skip_document_root=True),
    RefRule("weapon", "for", parent="ammo"),
    RefRule("sound", "sound_shoot"),
    RefRule("sound", "sound_reload"),
    RefRule("sound", "sound_eject_clip"),
    RefRule("image", "image_view"),
    RefRule("image", "image_view_base"),
    RefRule("image", "image_view_gun"),
    RefRule("image", "image_profile"),
    RefRule("image", "uniform_ranks"),
    RefRule("image", "image"),
    RefRule("uniform", "uniform"),
    RefRule("engine_sound", "sound"),
)

# An aircraft <sound> is a symbolic token, not a file stem; stock data contains a
# single token.  Tokens missing from this table stay unresolved.
ENGINE_SOUND_ALIASES: dict[str, str] = {"SOUND_PROPELLER": "Sounds/Engines/plane_propeller.ogg"}

# A plain-text roster names the units a project offers; an entry is a file stem under one
# of the unit folders, so it is a reference like any other and belongs in the same graph.
ROSTER_KIND = "roster"

UNIT_FOLDERS: tuple[str, ...] = ("Infantry", "Vehicles", "AT Guns", "Aircraft")

KINDS: tuple[str, ...] = tuple(dict.fromkeys(rule.kind for rule in REFERENCE_RULES)) + (ROSTER_KIND,)


@dataclass(frozen=True)
class Reference:
    """One value in one document pointing at one target token."""

    source: str
    path: tuple[str, ...]
    kind: str
    value: str


def references_in(root: XmlElement, source: str) -> tuple[Reference, ...]:
    """Every reference of one document, in document order."""
    found: list[Reference] = []
    _visit(root, (), source, found)
    return tuple(found)


def _visit(element: XmlElement, path: tuple[str, ...], source: str, found: list[Reference]) -> None:
    here = path + (element.tag,)
    if element.value:
        parent = here[-2] if len(here) >= 2 else ""
        for rule in REFERENCE_RULES:
            if rule.field != element.tag:
                continue
            if rule.parent is not None and rule.parent != parent:
                continue
            if rule.skip_document_root and len(here) == 2:
                continue
            found.append(Reference(source, here, rule.kind, element.value))
            break
    for child in element.children:
        _visit(child, here, source, found)


class RefGraph:
    """References of a scope, indexed by source document and by target value."""

    def __init__(self) -> None:
        self._references: list[Reference] = []
        self._by_source: dict[str, list[Reference]] = {}
        self._by_target: dict[tuple[str, str], list[Reference]] = {}

    def add(self, source: str, element: XmlElement) -> int:
        """Index one document; returns how many references it contributed."""
        return self.add_references(references_in(element, source))

    def add_references(self, found: tuple[Reference, ...]) -> int:
        """Index prepared references; returns how many were added."""
        for reference in found:
            self._references.append(reference)
            self._by_source.setdefault(reference.source, []).append(reference)
            self._by_target.setdefault((reference.kind, reference.value), []).append(reference)
        return len(found)

    def add_roster(self, source: str, entries: list[tuple[int, str]]) -> int:
        """Index the entries of one plain-text roster as ``roster`` references."""
        return self.add_references(
            tuple(Reference(source, (f"line {line}",), ROSTER_KIND, name) for line, name in entries)
        )

    def references(self) -> tuple[Reference, ...]:
        """Every reference of the scope, in insertion order."""
        return tuple(self._references)

    def for_source(self, source: str) -> tuple[Reference, ...]:
        """What this document points at (its outgoing references)."""
        return tuple(self._by_source.get(source, ()))

    def for_target(self, kind: str, value: str) -> tuple[Reference, ...]:
        """Who points at this target value (its incoming references)."""
        return tuple(self._by_target.get((kind, value), ()))

    def targets(self, kind: str | None = None) -> tuple[tuple[str, str], ...]:
        """Distinct (kind, value) pairs, sorted; optionally one kind only."""
        return tuple(sorted(key for key in self._by_target if kind is None or key[0] == kind))

    def sources(self) -> tuple[str, ...]:
        """Documents that carry at least one reference, sorted."""
        return tuple(sorted(self._by_source))


class TargetIndex:
    """Maps reference values onto files under one scope root."""

    def __init__(self, root: Path, *, unit_folders: tuple[str, ...] = UNIT_FOLDERS) -> None:
        self.root = Path(root)
        self.unit_folders = tuple(unit_folders)
        self._images: tuple[dict[str, tuple[Path, ...]], dict[str, tuple[Path, ...]]] | None = None
        self._units: dict[str, tuple[Path, ...]] | None = None

    def find(self, kind: str, value: str) -> tuple[Path, ...]:
        """Targets for one value; empty means the reference is unresolved."""
        if kind == "weapon":
            folder = self.root / "Data" / "Weapons"
            return tuple(path for name in (f"{value}.toml", f"{value}.txt") if (path := folder / name).is_file())
        if kind == "sound":
            path = self.root / "Sounds" / f"{value}.ogg"
            return (path,) if path.is_file() else ()
        if kind == "image":
            exact, folded = self._image_index()
            return exact.get(value) or folded.get(value.casefold(), ())
        if kind == "uniform":
            path = self.root / "Images" / "Uniforms" / f"uniform_{value}"
            return (path,) if path.exists() else ()
        if kind == "engine_sound":
            relative = ENGINE_SOUND_ALIASES.get(value)
            if relative is None:
                return ()
            path = self.root / relative
            return (path,) if path.is_file() else ()
        if kind == ROSTER_KIND:
            return self._unit_index().get(value, ())
        raise ValueError(f"unknown reference kind: {kind}")

    def expected(self, kind: str, value: str) -> tuple[str, ...]:
        """The relative paths a value would need under this root, for a report.

        ``find`` answers where a target is; this answers where it would have to be, so a
        missing asset can be named as a file rather than as a value that did not match
        (docs/cli.md section 4.6).
        """
        if kind == "weapon":
            return (f"Data/Weapons/{value}.toml", f"Data/Weapons/{value}.txt")
        if kind == "sound":
            return (f"Sounds/{value}.ogg",)
        if kind == "image":
            return (f"Images/**/{value}", f"Images/**/{value}.*")
        if kind == "uniform":
            return (f"Images/Uniforms/uniform_{value}",)
        if kind == "engine_sound":
            relative = ENGINE_SOUND_ALIASES.get(value)
            return (relative,) if relative else ()
        if kind == ROSTER_KIND:
            return (f"Data/**/{value}.toml", f"Data/**/{value}.txt")
        raise ValueError(f"unknown reference kind: {kind}")

    def _unit_index(self) -> dict[str, tuple[Path, ...]]:
        """Files of the unit folders, keyed by the name a roster entry would carry.

        Only units live in a roster: a weapon is pulled in by the document that uses it, so
        resolving an entry against the weapons folder would answer a name no roster can mean.
        """
        if self._units is None:
            found: dict[str, list[Path]] = {}
            for folder in self.unit_folders:
                base = self.root / "Data" / folder
                for path in sorted(base.rglob("*")) if base.is_dir() else ():
                    if path.is_file():
                        found.setdefault(path.stem, []).append(path)
            self._units = {name: tuple(paths) for name, paths in found.items()}
        return self._units

    def _image_index(self) -> tuple[dict[str, tuple[Path, ...]], dict[str, tuple[Path, ...]]]:
        """Exact and casefolded name/stem indexes over ``Images/``, built once.

        Stock aircraft data spells some file names with a different case than the
        file on disk (``Il-10`` vs ``IL-10``), so a folded index backs up the
        exact one.
        """
        if self._images is None:
            images = self.root / "Images"
            exact: dict[str, list[Path]] = {}
            folded: dict[str, list[Path]] = {}
            for path in sorted(images.rglob("*")) if images.is_dir() else ():
                if not path.is_file():
                    continue
                for key in {path.name, path.stem}:
                    exact.setdefault(key, []).append(path)
                    folded.setdefault(key.casefold(), []).append(path)
            self._images = (
                {key: tuple(paths) for key, paths in exact.items()},
                {key: tuple(paths) for key, paths in folded.items()},
            )
        return self._images


def unresolved(graph: RefGraph, index: TargetIndex, kind: str | None = None) -> tuple[Reference, ...]:
    """References whose target does not exist under the index root."""
    return tuple(
        reference
        for reference in graph.references()
        if (kind is None or reference.kind == kind) and not index.find(reference.kind, reference.value)
    )


def summary(graph: RefGraph, index: TargetIndex) -> dict[str, dict[str, int]]:
    """Per-kind counts: references, distinct targets, unresolved references."""
    report: dict[str, dict[str, int]] = {}
    for kind in KINDS:
        targets = graph.targets(kind)
        report[kind] = {
            "references": sum(1 for reference in graph.references() if reference.kind == kind),
            "targets": len(targets),
            "unresolved": len(unresolved(graph, index, kind)),
        }
    return report
