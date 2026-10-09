"""Tests for core.convert: XML -> TOML -> XML over the schema."""

import unittest

from core.convert import toml_to_xml, xml_to_toml
from core.errors import SchemaError
from core.schema import schema_for
from core.tomlmodel import TomlArrayEntry, TomlTable, TomlValue
from core.xmlmodel import XmlElement
from core.xmlread import parse as xml_parse

SQUAD = """<squad>
\t<description>
\t\t<type>TYPE_TANK</type>
\t\t<image_view>Image-Panzer IV Ausf D&E.png</image_view>
\t\t<weight>20000</weight>
\t\t<comment></comment>
\t</description>
\t<availability>
\t\t<data><month>11</month><year>1939</year><number>50</number></data>
\t\t<data><month>1</month><year>1940</year><number>100</number></data>
\t</availability>
\t<vehicle>
\t\t<attributes><is_amphibious>no</is_amphibious></attributes>
\t\t<hull><armour><upper_front>30@12</upper_front><side>20</side></armour></hull>
\t</vehicle>
\t<man><name>Pvt</name><type>TYPE_RIFLE</type></man>
\t<man><name>Cpl</name></man>
</squad>
"""


def signature(element: XmlElement) -> tuple:
    groups: dict[str, list[XmlElement]] = {}
    for child in element.children:
        groups.setdefault(child.tag, []).append(child)
    parts = tuple((tag, tuple(signature(kid) for kid in kids)) for tag, kids in sorted(groups.items()))
    return element.tag, element.value, parts


def table_of(table: TomlTable, key: str) -> TomlTable:
    entry = table.get(key)
    assert isinstance(entry, TomlTable)
    return entry


def scalar_of(table: TomlTable, key: str) -> TomlValue:
    entry = table.get(key)
    assert isinstance(entry, TomlValue)
    return entry


class TableShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = xml_parse(SQUAD, "unit")
        self.table = xml_to_toml(self.document)
        self.squad = table_of(self.table, "squad")

    def test_root_tag_becomes_a_top_level_table(self) -> None:
        self.assertEqual([name for name, _ in self.table.entries], ["squad"])

    def test_leaf_and_nested_table(self) -> None:
        description = table_of(self.squad, "description")
        type_entry = description.get("type")
        assert isinstance(type_entry, TomlValue)
        self.assertEqual(type_entry.value, "TYPE_TANK")
        self.assertEqual(type_entry.raw, '"TYPE_TANK"')

    def test_integer_keeps_its_literal(self) -> None:
        weight = table_of(self.squad, "description").get("weight")
        assert isinstance(weight, TomlValue)
        self.assertEqual((weight.raw, weight.value), ("20000", 20000))

    def test_empty_leaf_is_an_empty_string(self) -> None:
        comment = table_of(self.squad, "description").get("comment")
        assert isinstance(comment, TomlValue)
        self.assertEqual(comment.value, "")

    def test_repeated_element_becomes_an_array_of_tables(self) -> None:
        men = self.squad.get("man")
        assert isinstance(men, TomlArrayEntry)
        self.assertEqual(len(men.items), 2)
        name = scalar_of(men.items[0], "name")
        self.assertEqual((name.raw, name.value), ('"Pvt"', "Pvt"))

    def test_nested_repeat_keeps_parent_as_a_table(self) -> None:
        availability = table_of(self.squad, "availability")
        data = availability.get("data")
        assert isinstance(data, TomlArrayEntry)
        self.assertEqual(len(data.items), 2)

    def test_pinned_string_field_keeps_its_text(self) -> None:
        armour = table_of(table_of(table_of(self.squad, "vehicle"), "hull"), "armour")
        upper = armour.get("upper_front")
        assert isinstance(upper, TomlValue)
        self.assertEqual((upper.raw, upper.value), ('"30@12"', "30@12"))
        side = armour.get("side")
        assert isinstance(side, TomlValue)
        self.assertEqual((side.raw, side.value), ('"20"', "20"))

    def test_pinned_boolean_field_becomes_a_boolean(self) -> None:
        attributes = table_of(table_of(self.squad, "vehicle"), "attributes")
        flag = attributes.get("is_amphibious")
        assert isinstance(flag, TomlValue)
        self.assertIs(flag.value, False)


class ExportTest(unittest.TestCase):
    def test_round_trip_is_semantically_equivalent(self) -> None:
        document = xml_parse(SQUAD, "unit")
        table = xml_to_toml(document)
        exported = xml_parse(toml_to_xml(table), "export")
        self.assertEqual(signature(exported.root), signature(document.root))

    def test_export_uses_tabs_and_crlf(self) -> None:
        document = xml_parse(SQUAD, "unit")
        exported = toml_to_xml(xml_to_toml(document))
        self.assertIn("\r\n", exported)
        self.assertIn("\n\t<description>", exported)
        self.assertNotIn("  <", exported)

    def test_bare_ampersand_is_written_back_unescaped(self) -> None:
        document = xml_parse(SQUAD, "unit")
        exported = toml_to_xml(xml_to_toml(document))
        self.assertIn("Image-Panzer IV Ausf D&E.png", exported)
        self.assertNotIn("&amp;", exported)

    def test_empty_leaf_renders_as_an_empty_element(self) -> None:
        document = xml_parse(SQUAD, "unit")
        exported = toml_to_xml(xml_to_toml(document))
        self.assertIn("<comment></comment>", exported)

    def test_branch_puts_its_child_on_its_own_line(self) -> None:
        document = xml_parse("<squad><description><type>X</type></description></squad>", "unit")
        table = xml_to_toml(document)
        exported = toml_to_xml(table)
        self.assertIn("<type>X</type>", exported)

    def test_document_without_a_single_root_is_rejected(self) -> None:
        empty = TomlTable()
        with self.assertRaises(SchemaError):
            toml_to_xml(empty)


class EdgeCaseTest(unittest.TestCase):
    def test_unknown_element_is_kept_and_warned(self) -> None:
        document = xml_parse("<squad><mystery>7</mystery></squad>", "unit")
        table = xml_to_toml(document)
        squad = table_of(table, "squad")
        mystery = squad.get("mystery")
        assert isinstance(mystery, TomlValue)
        self.assertEqual(mystery.value, 7)
        self.assertTrue(any("unknown element" in warning for warning in document.warnings))

    def test_unknown_branch_element_is_kept_as_a_table(self) -> None:
        document = xml_parse("<squad><mystery><inner>1</inner></mystery></squad>", "unit")
        table = xml_to_toml(document)
        squad = table_of(table, "squad")
        mystery = squad.get("mystery")
        assert isinstance(mystery, TomlTable)
        inner = scalar_of(mystery, "inner")
        self.assertEqual((inner.raw, inner.value), ("1", 1))

    def test_repeated_leaf_is_rejected(self) -> None:
        document = xml_parse("<squad><description><type>a</type><type>b</type></description></squad>", "unit")
        with self.assertRaises(SchemaError) as caught:
            xml_to_toml(document)
        self.assertEqual(caught.exception.path, ("squad", "description", "type"))

    def test_repeated_single_instance_table_is_rejected(self) -> None:
        document = xml_parse("<squad><description></description><description></description></squad>", "unit")
        with self.assertRaises(SchemaError):
            xml_to_toml(document)

    def test_unknown_root_has_no_schema(self) -> None:
        document = xml_parse("<mod><name>x</name></mod>", "unit")
        self.assertIsNone(schema_for(document.root.tag))
        table = xml_to_toml(document)
        self.assertIsInstance(table_of(table, "mod"), TomlTable)

    def test_schema_children_and_lookup(self) -> None:
        schema = schema_for("squad")
        assert schema is not None
        node = schema.lookup(("squad", "vehicle", "hull", "armour", "upper_front"))
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.type, "str")
        self.assertIsNone(schema.lookup(("squad", "nope")))


if __name__ == "__main__":
    unittest.main()
