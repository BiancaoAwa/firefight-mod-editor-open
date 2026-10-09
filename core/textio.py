"""Single text I/O exit point.

Most stock sources are cp1252 without a BOM, but the corpus also ships UTF-8 files
whose bytes are all valid cp1252 (for example ``5.8<C3><97>42mm`` for a
multiplication sign), so UTF-8 is tried first and cp1252 is the fallback.  The
chosen encoding is remembered per file.  In-memory text is LF; exported text is
CRLF with tab indentation (docs/m0-baseline.md section 2.2, docs/toml-mapping.md
section 5).
"""

from dataclasses import dataclass
from pathlib import Path

from core.errors import ExportEncodingError, TextDecodeError

CODE_PAGE = "cp1252"
FALLBACK_ENCODING = "utf-8"
BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class SourceText:
    """One decoded source file."""

    path: Path
    text: str
    had_bom: bool
    encoding: str = CODE_PAGE


def normalize_newlines(text: str) -> str:
    """CRLF and lone CR become LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def to_export_newlines(text: str) -> str:
    """LF becomes CRLF (decision D3)."""
    return normalize_newlines(text).replace("\n", "\r\n")


def decode_source(data: bytes, file: str) -> tuple[str, str]:
    """Decode bytes as UTF-8, falling back to cp1252; returns (text, encoding).

    UTF-8 wins ties because cp1252 also accepts UTF-8 byte pairs and would turn
    them into mojibake; a real cp1252 file with umlauts fails UTF-8 and falls back.
    """
    try:
        text = data.decode(FALLBACK_ENCODING)
    except UnicodeDecodeError:
        pass
    else:
        # ASCII is encoding-neutral, and cp1252 is the export default.
        return (text, CODE_PAGE) if data.isascii() else (text, FALLBACK_ENCODING)
    try:
        return data.decode(CODE_PAGE), CODE_PAGE
    except UnicodeDecodeError as exc:
        raise TextDecodeError(file, exc.start) from None


def read_source(path: Path, warnings: list[str] | None = None) -> SourceText:
    """Decode one file, stripping a BOM; a non-default encoding is reported as a warning."""
    data = path.read_bytes()
    had_bom = data.startswith(BOM)
    if had_bom:
        data = data[len(BOM):]
    text, encoding = decode_source(data, str(path))
    if encoding != CODE_PAGE and warnings is not None:
        warnings.append(f"{path}: decoded as {encoding} (not {CODE_PAGE})")
    return SourceText(path=path, text=normalize_newlines(text), had_bom=had_bom, encoding=encoding)


def encode_export(text: str, file: str = "<export>", encoding: str = CODE_PAGE) -> bytes:
    """Encode export text in the file encoding with CRLF, or raise ExportEncodingError."""
    try:
        return to_export_newlines(text).encode(encoding)
    except UnicodeEncodeError as exc:
        raise ExportEncodingError(file, text[exc.start:exc.end]) from exc


def write_source(path: Path, text: str, encoding: str = CODE_PAGE) -> None:
    """Write text with CRLF and no BOM in the given encoding."""
    path.write_bytes(encode_export(text, str(path), encoding))
