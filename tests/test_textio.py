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


class EncodingTest(unittest.TestCase):
    def test_encodes_cp1252(self) -> None:
        self.assertEqual(textio.encode_export("naïve", "unit"), b"na\xefve")

    def test_rejects_characters_outside_cp1252(self) -> None:
        with self.assertRaises(ExportEncodingError) as caught:
            textio.encode_export("arrow →", "unit")
        self.assertEqual(caught.exception.value, "→")


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
