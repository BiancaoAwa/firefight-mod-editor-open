"""Single text I/O exit point.

UTF-8 before cp1252; exports keep their line endings, text without a source is CRLF with tabs (docs/m0-baseline.md section 2.2).
"""

from dataclasses import dataclass
from pathlib import Path

from core.errors import ExportEncodingError, TextDecodeError

CODE_PAGE = "cp1252"
FALLBACK_ENCODING = "utf-8"
BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class SourceText:
    """One decoded source file.

    ``text`` is newline-normalised for parsing; ``raw`` keeps the file's own
    line endings so an untouched file can be written back byte for byte.
    """

    path: Path
    text: str
    had_bom: bool
    encoding: str = CODE_PAGE
    raw: str = ""


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
    return SourceText(path=path, text=normalize_newlines(text), had_bom=had_bom, encoding=encoding, raw=text)


def encode_export(text: str, file: str = "<export>", encoding: str = CODE_PAGE, newline: str = "\r\n") -> bytes:
    """Encode export text in the file encoding, or raise ExportEncodingError.

    ``newline`` is the line ending to write; an empty string keeps the line
    endings the text already carries, which is how a stock file keeps its own
    style (decision D3 as amended, docs/toml-mapping.md section 5).
    """
    if newline:
        text = normalize_newlines(text).replace("\n", newline)
    try:
        return text.encode(encoding)
    except UnicodeEncodeError as exc:
        raise ExportEncodingError(file, text[exc.start:exc.end]) from exc


def write_source(path: Path, text: str, encoding: str = CODE_PAGE) -> None:
    """Write text with CRLF and no BOM in the given encoding."""
    path.write_bytes(encode_export(text, str(path), encoding))
