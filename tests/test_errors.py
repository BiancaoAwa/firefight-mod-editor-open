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


class ErrorRuleTest(unittest.TestCase):
    """The exit code and the page status of an error come from the table."""

    def test_a_usage_error_is_a_bad_request_and_exit_two(self):
        from core.cli.scope import UsageError

        rule = errors.rule_for(UsageError("scope Mod needs a command"))
        self.assertEqual((rule.exit_code, rule.http_status), (2, 400))
        self.assertEqual(rule.title, "用法错误")
        self.assertTrue(rule.usage_hint)

    def test_an_editor_error_is_exit_one_and_a_server_error(self):
        rule = errors.rule_for(errors.FfError("cannot read the file"))
        self.assertEqual((rule.exit_code, rule.http_status), (1, 500))
        self.assertEqual(rule.title, "读取失败")
        self.assertFalse(rule.usage_hint)

    def test_a_subclass_inherits_the_rule_of_its_base(self):
        rule = errors.rule_for(errors.TextDecodeError("a.txt", 3))
        self.assertEqual(rule, errors.rule_for(errors.FfError("x")))

    def test_an_unexpected_error_falls_back_without_a_usage_hint(self):
        rule = errors.rule_for(ValueError("not a number"))
        self.assertEqual(rule, errors.FALLBACK)
        self.assertEqual((rule.exit_code, rule.http_status), (1, 500))
        self.assertFalse(rule.usage_hint)

    def test_every_title_is_translated(self):
        from core.web import i18n

        titles = [rule.title for _, rule in errors.RULES] + [errors.FALLBACK.title]
        for title in titles:
            with self.subTest(title=title):
                self.assertIn(title, i18n.ENGLISH)


if __name__ == "__main__":
    unittest.main()
