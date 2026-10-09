"""Tests for the error types."""

import unittest

from core import errors


class ErrorModelTest(unittest.TestCase):
    def test_all_errors_share_one_base(self):
        for cls in (
            errors.TextDecodeError,
            errors.XmlStructureError,
            errors.TomlSyntaxError,
            errors.SchemaError,
            errors.ExportEncodingError,
        ):
            with self.subTest(cls=cls.__name__):
                self.assertTrue(issubclass(cls, errors.FfError))
                self.assertTrue(issubclass(cls, Exception))

    def test_text_decode_error_carries_file_and_offset(self):
        exc = errors.TextDecodeError("Mod/Data/Infantry/x.txt", 42)
        self.assertEqual(exc.file, "Mod/Data/Infantry/x.txt")
        self.assertEqual(exc.offset, 42)
        self.assertIn("x.txt", str(exc))
        self.assertIn("42", str(exc))

    def test_xml_structure_error_carries_file_and_line(self):
        exc = errors.XmlStructureError("a.txt", 7)
        self.assertEqual((exc.file, exc.line), ("a.txt", 7))
        self.assertIn("a.txt:7", str(exc))

    def test_toml_syntax_error_carries_file_line_column_and_hint(self):
        exc = errors.TomlSyntaxError("m.toml", 12, 5, "inline tables are unsupported")
        self.assertEqual((exc.file, exc.line, exc.column), ("m.toml", 12, 5))
        self.assertIn("m.toml:12:5", str(exc))
        self.assertIn("inline tables are unsupported", str(exc))

    def test_toml_syntax_error_hint_is_optional(self):
        exc = errors.TomlSyntaxError("m.toml", 1, 2)
        self.assertEqual(exc.hint, "")
        self.assertNotIn("()", str(exc))

    def test_schema_error_carries_a_tuple_path(self):
        exc = errors.SchemaError(["squad", "man", "job"], "unknown leaf")
        self.assertEqual(exc.path, ("squad", "man", "job"))
        self.assertIsInstance(exc.path, tuple)
        self.assertIn("squad/man/job", str(exc))

    def test_export_encoding_error_carries_file_and_value(self):
        exc = errors.ExportEncodingError("out.txt", "\u2014")
        self.assertEqual(exc.file, "out.txt")
        self.assertEqual(exc.value, "\u2014")
        self.assertIn("cp1252", str(exc))


if __name__ == "__main__":
    unittest.main()
