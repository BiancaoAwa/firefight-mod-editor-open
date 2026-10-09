"""Golden fixtures: committed TOML must be what the pipeline produces.

Each fixture is a small hand-written `stock.txt` plus the `mapped.toml` that
`core/convert.py` derives from it.  Regenerating the TOML is a deliberate edit,
so an accidental change in the writer fails here (docs/m1-design.md section 4).
"""

import unittest
from pathlib import Path

from core import textio, xmlread
from core.convert import toml_to_xml, xml_to_toml
from core.schema import schema_for
from core.tomlread import parse as toml_parse
from core.tomlwrite import render as toml_render
from core.xmlmodel import signature

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read_fixture(folder: Path, name: str) -> str:
    """Read a fixture as UTF-8 without newline translation."""
    return (folder / name).read_bytes().decode("utf-8")


class GoldenTest(unittest.TestCase):
    def folders(self) -> list[Path]:
        return sorted(path for path in FIXTURES.iterdir() if path.is_dir())

    def test_fixtures_exist(self):
        self.assertEqual([path.name for path in self.folders()], ["aircraft", "squad", "weapon"])

    def test_xml_to_toml_matches_committed(self):
        for folder in self.folders():
            with self.subTest(fixture=folder.name):
                stock = read_fixture(folder, "stock.txt")
                document = xmlread.parse(stock, str(folder / "stock.txt"))
                self.assertEqual([w for w in document.warnings if "unknown" in w], [])
                schema = schema_for(document.root.tag)
                self.assertIsNotNone(schema)
                self.assertEqual(toml_render(xml_to_toml(document, schema)), read_fixture(folder, "mapped.toml"))

    def test_toml_to_xml_restores_the_source_tree(self):
        for folder in self.folders():
            with self.subTest(fixture=folder.name):
                stock = read_fixture(folder, "stock.txt")
                schema = schema_for(xmlread.parse(stock, "").root.tag)
                table = toml_parse(read_fixture(folder, "mapped.toml"), str(folder / "mapped.toml"))
                exported = toml_to_xml(table, schema, str(folder / "mapped.toml"))
                self.assertEqual(signature(xmlread.parse(exported, "").root), signature(xmlread.parse(stock, "").root))

    def test_toml_survives_a_full_cycle(self):
        for folder in self.folders():
            with self.subTest(fixture=folder.name):
                committed = read_fixture(folder, "mapped.toml")
                schema = schema_for(toml_parse(committed, "").entries[0][0])
                exported = toml_to_xml(toml_parse(committed, ""), schema, str(folder / "mapped.toml"))
                again = xml_to_toml(xmlread.parse(exported, ""), schema)
                self.assertEqual(toml_render(again), committed)

    def test_exported_text_is_cp1252_and_crlf(self):
        for folder in self.folders():
            with self.subTest(fixture=folder.name):
                table = toml_parse(read_fixture(folder, "mapped.toml"), "")
                exported = toml_to_xml(table, schema_for(table.entries[0][0]), "")
                textio.encode_export(exported, folder.name)
                self.assertEqual(textio.normalize_newlines(exported).count("\n"), exported.count("\r\n"))

    def test_fixtures_are_lf_and_ascii(self):
        for folder in self.folders():
            for name in ("stock.txt", "mapped.toml"):
                with self.subTest(fixture=f"{folder.name}/{name}"):
                    raw = (folder / name).read_bytes()
                    self.assertNotIn(b"\r", raw)
                    self.assertFalse(raw.startswith(textio.BOM))
                    raw.decode("ascii")
