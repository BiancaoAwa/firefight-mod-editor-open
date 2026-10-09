"""Tests for core.textio: cp1252 text I/O and newline policy."""

import shutil
import unittest
from pathlib import Path

from core import textio
from core.errors import ExportEncodingError, TextDecodeError

SCRATCH = Path(__file__).resolve().parent / "_scratch_textio"


class ScratchTest(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        SCRATCH.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)


class ReadSourceTest(ScratchTest):
    def test_decodes_cp1252_and_strips_bom(self) -> None:
        path = SCRATCH / "unit.txt"
        path.write_bytes(b"\xef\xbb\xbfna\xefve")
        source = textio.read_source(path)
        self.assertEqual(source.text, "naïve")
        self.assertTrue(source.had_bom)

    def test_reports_offset_of_undecodable_byte(self) -> None:
        path = SCRATCH / "bad.txt"
        path.write_bytes(b"ab\x81cd")
        with self.assertRaises(TextDecodeError) as caught:
            textio.read_source(path)
        self.assertEqual(caught.exception.offset, 2)
        self.assertIn("bad.txt", str(caught.exception))

    def test_falls_back_to_utf8_and_reports_it(self) -> None:
        path = SCRATCH / "mod.txt"
        path.write_bytes("<squad><name>小机炮</name></squad>".encode("utf-8"))
        warnings: list[str] = []
        source = textio.read_source(path, warnings)
        self.assertEqual(source.encoding, "utf-8")
        self.assertEqual(source.text, "<squad><name>小机炮</name></squad>")
        self.assertTrue(any("decoded as utf-8" in warning for warning in warnings))

    def test_prefers_utf8_when_cp1252_would_also_decode(self) -> None:
        # C3 97 is a multiplication sign in UTF-8 and two letters in cp1252; the
        # retail corpus and mods both ship this shape.
        path = SCRATCH / "calibre.txt"
        path.write_bytes("<name>5.8×42mm</name>".encode("utf-8"))
        warnings: list[str] = []
        source = textio.read_source(path, warnings)
        self.assertEqual(source.encoding, "utf-8")
        self.assertEqual(source.text, "<name>5.8×42mm</name>")

    def test_stock_file_reports_cp1252_and_no_warning(self) -> None:
        path = SCRATCH / "stock.txt"
        path.write_bytes("naïve".encode("cp1252"))
        warnings: list[str] = []
        source = textio.read_source(path, warnings)
        self.assertEqual(source.encoding, "cp1252")
        self.assertEqual(source.text, "naïve")
        self.assertEqual(warnings, [])


class EncodingTest(unittest.TestCase):
    def test_encodes_cp1252(self) -> None:
        self.assertEqual(textio.encode_export("naïve", "unit"), b"na\xefve")

    def test_rejects_characters_outside_cp1252(self) -> None:
        with self.assertRaises(ExportEncodingError) as caught:
            textio.encode_export("arrow →", "unit")
        self.assertEqual(caught.exception.value, "→")

    def test_encodes_utf8_when_the_source_was_utf8(self) -> None:
        self.assertEqual(
            textio.encode_export("小机炮", "unit", "utf-8"),
            "小机炮".encode("utf-8"),
        )


class NewlineTest(ScratchTest):
    def test_normalize_folds_crlf_and_cr(self) -> None:
        self.assertEqual(textio.normalize_newlines("a\r\nb\rc"), "a\nb\nc")

    def test_export_uses_crlf(self) -> None:
        self.assertEqual(textio.to_export_newlines("a\r\nb\rc"), "a\r\nb\r\nc")

    def test_write_source_round_trips(self) -> None:
        path = SCRATCH / "out.txt"
        textio.write_source(path, "<squad>naïve</squad>")
        source = textio.read_source(path)
        self.assertEqual(source.text, "<squad>naïve</squad>")
        self.assertFalse(source.had_bom)


if __name__ == "__main__":
    unittest.main()
