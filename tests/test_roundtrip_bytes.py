"""Byte-for-byte fidelity: an untouched stock file exports exactly as it was.

CRLF and LF, no trailing newline, group-separating blank lines, inline branches, multi-line
leaves and ``//`` comments are covered; the corpus check is ``tools/export_fidelity.py``.
"""

import contextlib
import io
import json
import shutil
import unittest
from pathlib import Path

from core.cli.main import main
from core import convert, textio, xml

CRLF = "\r\n"
SCRATCH = Path(__file__).resolve().parent / "_scratch_roundtrip"

CASES = {
    "crlf_groups": (
        "<weapon>\r\n"
        "\r\n"
        "\t<name>P38 Pistol</name>\r\n"
        "\t<type>WEAPON_PISTOL</type>\r\n"
        "\r\n"
        "\t<shoot>\r\n"
        "\t\t<sound_shoot>shoot_pistol</sound_shoot>\r\n"
        "\t</shoot>\r\n"
        "</weapon>\r\n"
    ),
    "lf_only": (
        "<weapon>\n"
        "\t<name>P38 Pistol</name>\n"
        "\t<type>WEAPON_PISTOL</type>\n"
        "</weapon>\n"
    ),
    "no_trailing_newline": "<weapon>\r\n\t<name>3KG Explosive</name>\r\n\t<type>WEAPON_RPG</type>\r\n</weapon>",
    "trailing_blank_line": "<weapon>\r\n\t<name>X</name>\r\n</weapon>\r\n\r\n",
    "trailing_comment": "<weapon>\r\n\t<name>X</name>\r\n</weapon>\r\n// end of file\r\n",
    "comment_before_element": (
        "<squad>\r\n"
        "\t// @0 means vertically upright, @90 is horizontal\r\n"
        "\t<armour>\r\n"
        "\t\t<side>20</side>\r\n"
        "\t</armour>\r\n"
        "</squad>\r\n"
    ),
    "inline_branch": (
        "<weapon>\r\n"
        "\t<ammo>\r\n"
        "\t\t<type><flavour>FLAVOUR_HE</flavour><speed>745</speed><mass>0.6</mass><name>Sprgr. 34</name></type>\r\n"
        "\t\t<type><flavour>FLAVOUR_AP</flavour><speed>745</speed></type>\r\n"
        "\t</ammo>\r\n"
        "</weapon>\r\n"
    ),
    "multiline_leaf": (
        "<weapon>\r\n"
        "\t<comments>\r\n"
        "\tThis has been renamed and will be deleted at some point - so don't use it!\r\n"
        "\t</comments>\r\n"
        "</weapon>\r\n"
    ),
    "self_closing": "<weapon>\r\n\t<magazine/>\r\n\t<name>X</name>\r\n</weapon>\r\n",
    "declaration": '<?xml version="1.0" encoding="utf-8"?>\r\n<weapon>\r\n\t<name>X</name>\r\n</weapon>\r\n',
    "deep_indentation": (
        "<squad>\r\n"
        "\t<vehicle>\r\n"
        "\t\t<hull>\r\n"
        "\t\t\t<man>\r\n"
        "\t\t\t\t<ammo>\r\n"
        "\t\t\t\t\t<for>WEAPON_PISTOL_P38</for>\r\n"
        "\t\t\t\t</ammo>\r\n"
        "\t\t\t</man>\r\n"
        "\t\t</hull>\r\n"
        "\t</vehicle>\r\n"
        "</squad>\r\n"
    ),
    "cp1252_text": "<weapon>\r\n\t<name>75mm Sprgr. \xfc</name>\r\n\t<calibre>5.8\xd742mm</calibre>\r\n</weapon>\r\n",
    "stray_text": "<squad>\r\n\t<availability>\r\n\t\t<data>1</data>>\r\n\t</availability>\r\n</squad>\r\n",
}


def render(document) -> str:
    """Write a parsed document back out with the layout it carries."""
    return convert.tree_to_xml(document.root, document.header, document.footer, document.newline, document.indent)


class RoundTripBytesTest(unittest.TestCase):
    """Fixtures live next to the tests: the harness sandbox cannot clean %TEMP%."""

    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def scope_with(self, relative: str, text: str) -> tuple[Path, Path]:
        """Write one stock entity and return (scope root, entity path)."""
        root = SCRATCH / "stock"
        entity = root / relative
        entity.parent.mkdir(parents=True, exist_ok=True)
        entity.write_bytes(text.encode("cp1252"))
        return root, entity

    def test_every_fixture_round_trips_byte_for_byte(self):
        for name, text in CASES.items():
            with self.subTest(case=name):
                document = xml.parse(text, name)
                encoded = textio.encode_export(render(document), name, newline="")
                self.assertEqual(encoded, text.encode("cp1252"))

    def test_newline_style_is_reported(self):
        self.assertEqual(xml.parse(CASES["crlf_groups"], "x").newline, CRLF)
        self.assertEqual(xml.parse(CASES["lf_only"], "x").newline, "\n")

    def test_editing_a_leaf_keeps_every_other_byte(self):
        text = CASES["crlf_groups"]
        document = xml.parse(text, "edit")
        name = document.root.by_tag("name")[0]
        name.value = "P38 Pistol (modded)"
        name.raw_value = None
        self.assertEqual(
            render(document),
            text.replace("<name>P38 Pistol</name>", "<name>P38 Pistol (modded)</name>"),
        )

    def test_a_canonical_render_is_used_when_there_is_no_layout(self):
        table = convert.xml_to_toml(xml.parse(CASES["lf_only"], "x"))
        rendered = convert.toml_to_xml(table)
        self.assertEqual(rendered, CASES["lf_only"].replace("\n", CRLF))

    def test_export_writes_the_source_bytes(self):
        for name, text in CASES.items():
            with self.subTest(case=name):
                relative = "Data/Weapons/WEAPON_TEST.txt"
                root, _ = self.scope_with(relative, text)
                out = SCRATCH / "out"
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    code = main(["Firefight", "export", f"root={root}", f"to={out}", "--json"])
                payload = json.loads(captured.getvalue())
                self.assertEqual(code, 0, payload)
                self.assertEqual(payload["errors"], [])
                self.assertEqual((out / relative).read_bytes(), text.encode("cp1252"))

    def test_show_xml_of_a_stock_file_is_the_file(self):
        relative = "Data/Vehicles/Hungarian-TK3.txt"
        text = CASES["comment_before_element"]
        root, _ = self.scope_with(relative, text)
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = main(["Firefight", "show", relative, "as=xml", f"root={root}", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(captured.getvalue())["xml"], text)


if __name__ == "__main__":
    unittest.main()
