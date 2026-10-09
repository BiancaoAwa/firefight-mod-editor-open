"""Tests for core.tomlwrite: canonical order and stable round trips."""

import unittest

from core.tomlmodel import TomlArrayEntry, TomlTable, TomlValue
from core.tomlread import parse
from core.tomlwrite import quote_string, render


class RenderTest(unittest.TestCase):
    def test_order_is_scalars_then_tables_then_arrays(self) -> None:
        table = TomlTable()
        table.entries.append(("man", TomlArrayEntry(items=[TomlTable()])))
        table.entries.append(("description", TomlTable(entries=[("type", TomlValue('"x"', "x"))])))
        table.entries.append(("speed", TomlValue("200", 200)))
        self.assertEqual(render(table).splitlines()[0], "speed = 200")

    def test_scalars_of_a_table_come_before_its_subtables(self) -> None:
        table = parse("[a.b]\nx = 1\n\n[a.c]\ny = 2\n\n[a]\nz = 3\n", "unit")
        text = render(table)
        self.assertLess(text.index("z = 3"), text.index("[a.b]"))
        self.assertLess(text.index("[a.b]"), text.index("[a.c]"))

    def test_array_items_get_one_header_each(self) -> None:
        table = parse('[[squad.man]]\nname = "a"\n\n[[squad.man]]\nname = "b"\n', "unit")
        self.assertEqual(render(table).count("[[squad.man]]"), 2)

    def test_empty_table_is_header_only(self) -> None:
        table = parse("[squad.dimensions]\n", "unit")
        self.assertEqual(render(table), "[squad]\n[squad.dimensions]\n")

    def test_keys_needing_quotes_are_quoted(self) -> None:
        table = parse('[squad.ranks]\n"1" = "Pvt"\n', "unit")
        self.assertIn('"1" = "Pvt"', render(table))

    def test_bare_keys_stay_bare(self) -> None:
        table = parse("[squad.description]\noffsetX = 1\n", "unit")
        self.assertIn("offsetX = 1", render(table))

    def test_labels_and_spacing_are_canonical(self) -> None:
        table = parse("[squad]\nx=1\n", "unit")
        self.assertEqual(render(table), "[squad]\nx = 1\n")

    def test_empty_document_renders_nothing(self) -> None:
        self.assertEqual(render(TomlTable()), "")


class QuoteTest(unittest.TestCase):
    def test_escapes_quote_and_backslash(self) -> None:
        self.assertEqual(quote_string('a"b\\c'), '"a\\"b\\\\c"')

    def test_escapes_control_characters(self) -> None:
        self.assertEqual(quote_string("a\tb\nc"), '"a\\tb\\nc"')

    def test_keeps_cp1252_text(self) -> None:
        self.assertEqual(quote_string("naïve"), '"naïve"')


class StabilityTest(unittest.TestCase):
    def test_render_parse_render_is_idempotent(self) -> None:
        source = (
            "# comment\n"
            '[[squad.man]]\nname = "Pvt"\n\n'
            "[squad.description]\n"
            'type = "TYPE_TANK"\n'
            "speed = 200\n"
            'mask = "30@12"\n'
            "flag = true\n"
            "\n"
            "[squad.vehicle.hull]\n"
            "width = 284\n"
        )
        first = render(parse(source, "unit"))
        second = render(parse(first, "unit2"))
        self.assertEqual(first, second)

    def test_decimal_literal_survives(self) -> None:
        rendered = render(parse("mass = 0.12\n", "unit"))
        self.assertEqual(rendered, "mass = 0.12\n")


if __name__ == "__main__":
    unittest.main()
