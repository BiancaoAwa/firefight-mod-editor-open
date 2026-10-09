"""Single text I/O exit point.

Sources are cp1252 without a BOM; in-memory text is LF; exported text is CRLF
with tab indentation (docs/m0-baseline.md section 2.2, docs/toml-mapping.md
section 5).
"""

from dataclasses import dataclass
from pathlib import Path

from core.errors import ExportEncodingError, TextDecodeError

CODE_PAGE = "cp1252"
BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class SourceText:
    """One decoded source file."""

    path: Path
    text: str
    had_bom: bool


def normalize_newlines(text: str) -> str:
    """CRLF and lone CR become LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def to_export_newlines(text: str) -> str:
    """LF becomes CRLF (decision D3)."""
    return normalize_newlines(text).replace("\n", "\r\n")


def read_source(path: Path) -> SourceText:
    """Decode a cp1252 file, stripping a BOM if one is present."""
    data = path.read_bytes()
    had_bom = data.startswith(BOM)
    if had_bom:
        data = data[len(BOM):]
    try:
        text = data.decode(CODE_PAGE)
    except UnicodeDecodeError as exc:
        raise TextDecodeError(str(path), exc.start) from exc
    return SourceText(path=path, text=normalize_newlines(text), had_bom=had_bom)


def encode_export(text: str, file: str = "<export>") -> bytes:
    """Encode export text to cp1252 plus CRLF, or raise ExportEncodingError."""
    try:
        return to_export_newlines(text).encode(CODE_PAGE)
    except UnicodeEncodeError as exc:
        raise ExportEncodingError(file, text[exc.start:exc.end]) from exc


def write_source(path: Path, text: str) -> None:
    """Write text as cp1252 + CRLF with no BOM."""
    path.write_bytes(encode_export(text, str(path)))
