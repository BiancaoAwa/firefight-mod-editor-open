"""Tests for core.tomlread: the documented TOML subset and its errors."""

import unittest

from core.errors import TomlSyntaxError
from core.tomlmodel import TomlArrayEntry, TomlTable, TomlValue
from core.tomlread import parse


def value_of(table: TomlTable, key: str) -> object:
    entry = table.get(key)
    assert isinstance(entry, TomlValue)
    return entry.value


class ReadTest(unittest.TestCase):
    def test_reads_tables_nested_tables_and_values(self) -> None:
        table = parse('[squad.description]\ntype = "TYPE_TANK"\nweight = 20000\n', "unit")
        squad = table.get("squad")
        assert isinstance(squad, TomlTable)
        description = squad.get("description")
        assert isinstance(description, TomlTable)
        self.assertEqual(value_of(description, "type"), "TYPE_TANK")
        self.assertEqual(value_of(description, "weight"), 20000)

    def test_reads_arrays_of_tables(self) -> None:
        table = parse('[[squad.man]]\nname = "a"\n\n[[squad.man]]\nname = "b"\n', "unit")
        squad = table.get("squad")
        assert isinstance(squad, TomlTable)
        men = squad.get("man")
        assert isinstance(men, TomlArrayEntry)
        self.assertEqual(len(men.items), 2)
        self.assertEqual(value_of(men.items[1], "name"), "b")

    def test_subtable_after_array_binds_to_last_item(self) -> None:
        table = parse('[[squad.man]]\nname = "a"\n\n[squad.man.ammo]\nrounds = 5\n', "unit")
        squad = table.get("squad")
        assert isinstance(squad, TomlTable)
        men = squad.get("man")
        assert isinstance(men, TomlArrayEntry)
        ammo = men.items[-1].get("ammo")
        assert isinstance(ammo, TomlTable)
        self.assertEqual(value_of(ammo, "rounds"), 5)

    def test_key_order_is_preserved(self) -> None:
        table = parse("[a]\nz = 1\na = 2\n", "unit")
        inner = table.get("a")
        assert isinstance(inner, TomlTable)
        self.assertEqual([name for name, _ in inner.entries], ["z", "a"])

    def test_literals_and_escapes(self) -> None:
        table = parse('a = "x\\ty\\u00e9"\nb = \'raw \\n\'\nc = true\nd = -1.5\ne = 0.12\n', "unit")
        self.assertEqual(value_of(table, "a"), "x\tyé")
        self.assertEqual(value_of(table, "b"), "raw \\n")
        self.assertIs(value_of(table, "c"), True)
        self.assertEqual(value_of(table, "d"), -1.5)
        self.assertEqual(value_of(table, "e"), 0.12)

    def test_literal_text_is_kept_next_to_the_value(self) -> None:
        table = parse("mass = 0.12\n", "unit")
        entry = table.get("mass")
        assert isinstance(entry, TomlValue)
        self.assertEqual(entry.raw, "0.12")
        self.assertEqual(entry.line, 1)

    def test_quoted_keys_and_comments(self) -> None:
        table = parse('[squad.ranks]\n"1" = "Pvt"  # rank\n\n# whole line\n"2" = "Cpl"\n', "unit")
        squad = table.get("squad")
        assert isinstance(squad, TomlTable)
        ranks = squad.get("ranks")
        assert isinstance(ranks, TomlTable)
        self.assertEqual(value_of(ranks, "1"), "Pvt")
        self.assertEqual(value_of(ranks, "2"), "Cpl")

    def test_hash_inside_a_string_is_not_a_comment(self) -> None:
        table = parse('a = "x # y"\n', "unit")
        self.assertEqual(value_of(table, "a"), "x # y")

    def test_explicit_empty_table(self) -> None:
        table = parse("[squad.dimensions]\n", "unit")
        squad = table.get("squad")
        assert isinstance(squad, TomlTable)
        self.assertIsInstance(squad.get("dimensions"), TomlTable)


class RejectionTest(unittest.TestCase):
    def assert_rejected(self, text: str, fragment: str) -> None:
        with self.assertRaises(TomlSyntaxError) as caught:
            parse(text, "unit")
        self.assertIn(fragment, caught.exception.hint)
        self.assertIn("unit", str(caught.exception))

    def test_inline_table(self) -> None:
        self.assert_rejected("a = { b = 1 }\n", "inline tables")

    def test_array(self) -> None:
        self.assert_rejected("a = [1, 2]\n", "arrays are unsupported")

    def test_date(self) -> None:
        self.assert_rejected("a = 1979-05-27\n", "dates")

    def test_multi_line_string(self) -> None:
        self.assert_rejected('a = """x"""\n', "multi-line")

    def test_duplicate_key(self) -> None:
        self.assert_rejected("a = 1\na = 2\n", "duplicate key")

    def test_table_declared_twice(self) -> None:
        self.assert_rejected("[a]\nx = 1\n[a]\ny = 2\n", "declared twice")

    def test_missing_equals(self) -> None:
        self.assert_rejected("a 1\n", "expected '='")

    def test_unsupported_escape(self) -> None:
        self.assert_rejected('a = "\\q"\n', "unsupported escape")

    def test_unterminated_string(self) -> None:
        self.assert_rejected('a = "x\n', "unterminated")

    def test_illegal_bare_key(self) -> None:
        self.assert_rejected("a b = 1\n", "unsupported key")

    def test_trailing_text_after_value(self) -> None:
        self.assert_rejected('a = "x" y\n', "trailing text")

    def test_error_carries_a_position(self) -> None:
        with self.assertRaises(TomlSyntaxError) as caught:
            parse("ok = 1\nbad\n", "unit")
        self.assertEqual(caught.exception.line, 2)


if __name__ == "__main__":
    unittest.main()
