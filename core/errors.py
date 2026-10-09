"""Exception types that carry file and position context.

Only unrecoverable conditions raise.  Recoverable ones (ragged close tags,
unknown tags, unknown enum-shaped values, dropped comments) are collected on the
document as warnings and never reach this module; see ``docs/m1-design.md``
section 3.9.
"""


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


class ExportEncodingError(FfError):
    """A string cannot be encoded to the export code page (cp1252)."""

    def __init__(self, file: str, value: str) -> None:
        self.file = file
        self.value = value
        super().__init__(f"{file}: value is not encodable as cp1252: {value!r}")
