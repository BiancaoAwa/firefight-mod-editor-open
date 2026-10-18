"""Exception types that carry file and position context.

Only unrecoverable conditions raise; recoverable ones become warnings (docs/toml-mapping.md).

How an error is presented is a table, not a decision spread over the faces: the
exit code the command line returns and the status and title the pages show come
from ``RULES`` below. A new error type needs its class and, when it is presented
differently, one rule; neither the command line nor the pages need editing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorRule:
    """How one kind of error looks outside the code that raised it."""

    exit_code: int
    http_status: int
    title: str
    usage_hint: bool = False


class FfError(Exception):
    """Base class for every error raised by this editor."""


class TextDecodeError(FfError):
    """A source file cannot be decoded as cp1252 without a BOM."""

    def __init__(self, file: str, offset: int) -> None:
        self.file = file
        self.offset = offset
        super().__init__(f"{file}: undecodable byte at offset {offset}")


class XmlStructureError(FfError):
    """XML structure that the tolerant reader cannot recover from."""

    def __init__(self, file: str, line: int, message: str = "unrecoverable XML structure") -> None:
        self.file = file
        self.line = line
        self.message = message
        super().__init__(f"{file}:{line}: {message}")


class TomlSyntaxError(FfError):
    """Input outside the TOML subset documented in docs/toml-mapping.md section 6."""

    def __init__(self, file: str, line: int, column: int, hint: str = "") -> None:
        self.file = file
        self.line = line
        self.column = column
        self.hint = hint
        detail = f" ({hint})" if hint else ""
        super().__init__(f"{file}:{line}:{column}: TOML syntax{detail}")


class SchemaError(FfError):
    """A value or element contradicts the path-keyed schema."""

    def __init__(self, path: tuple[str, ...], message: str) -> None:
        self.path = tuple(path)
        self.message = message
        super().__init__(f"{'/'.join(self.path)}: {message}")


class EditRefused(FfError):
    """A write the editor refuses; the CLI reports it as a usage error (exit code 2)."""


class ExportEncodingError(FfError):
    """A string cannot be encoded to the export code page (cp1252)."""

    def __init__(self, file: str, value: str) -> None:
        self.file = file
        self.value = value
        super().__init__(f"{file}: value is not encodable as cp1252: {value!r}")


RULES: tuple[tuple[object, ErrorRule], ...] = (
    # UsageError is defined next to the scope resolver; it is resolved lazily
    # in rule_for so this module keeps no import of core.cli.
    ("UsageError", ErrorRule(exit_code=2, http_status=400, title="用法错误", usage_hint=True)),
    (FfError, ErrorRule(exit_code=1, http_status=500, title="读取失败")),
)

FALLBACK = ErrorRule(exit_code=1, http_status=500, title="内部错误")


def rule_for(error: BaseException) -> ErrorRule:
    """The rule that governs how this exception is presented."""
    for kind, rule in RULES:
        resolved = _resolve(kind) if isinstance(kind, str) else kind
        if resolved is not None and isinstance(error, resolved):
            return rule
    return FALLBACK


def _resolve(name: str) -> type[BaseException] | None:
    if name != "UsageError":
        return None
    from core.cli.scope import UsageError

    return UsageError
