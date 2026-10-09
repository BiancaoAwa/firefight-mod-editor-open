"""Tests for core.xmlread: the tolerant stock dialect scanner."""

import unittest

from core import xmlread
from core.errors import XmlStructureError
from core.xmlmodel import XmlElement


class ParseTest(unittest.TestCase):
    def test_reads_nesting_text_and_order(self) -> None:
        doc = xmlread.parse("<squad>\n\t<description>\n\t\t<type>TYPE_TANK</type>\n\t</description>\n</squad>", "unit")
        self.assertEqual(doc.root.tag, "squad")
        description = doc.root.children[0]
        self.assertEqual(description.tag, "description")
        self.assertEqual(description.children[0].value, "TYPE_TANK")

    def test_keeps_bare_ampersand(self) -> None:
        doc = xmlread.parse("<squad><image_view>Image-Panzer IV Ausf D&E.png</image_view></squad>", "unit")
        self.assertEqual(doc.root.children[0].value, "Image-Panzer IV Ausf D&E.png")

    def test_empty_element_has_empty_value(self) -> None:
        doc = xmlread.parse("<weapon><name></name></weapon>", "unit")
        self.assertEqual(doc.root.children[0].value, "")

    def test_self_closing_element_has_no_children(self) -> None:
        doc = xmlread.parse("<weapon><magazine/></weapon>", "unit")
        self.assertEqual(doc.root.children[0].tag, "magazine")
        self.assertEqual(doc.root.children[0].children, [])

    def test_numeric_tag_names(self) -> None:
        doc = xmlread.parse("<squad><ranks><1>Pvt</1></ranks></squad>", "unit")
        self.assertEqual(doc.root.children[0].children[0].tag, "1")

    def test_last_child_is_not_lost(self) -> None:
        doc = xmlread.parse("<weapon>\n\t<name>x</name>\n\t<magazine>\n\t\t<rounds>5</rounds>\n\t</magazine>\n</weapon>", "unit")
        self.assertEqual([child.tag for child in doc.root.children], ["name", "magazine"])
        self.assertEqual(doc.root.children[1].children[0].value, "5")


class CommentTest(unittest.TestCase):
    def test_comment_at_line_end_is_removed(self) -> None:
        text, count = xmlread.strip_comments("<armour>\t\t\t\t// @0 means upright\n\t<side>20</side>\n")
        self.assertEqual(count, 1)
        self.assertNotIn("upright", text)
        self.assertIn("<armour>", text)

    def test_slash_inside_text_is_kept(self) -> None:
        text, count = xmlread.strip_comments("<name>http://example/1</name>")
        self.assertEqual(count, 0)
        self.assertEqual(text, "<name>http://example/1</name>")

    def test_comment_after_markup_is_removed(self) -> None:
        text, count = xmlread.strip_comments("<squad>// note\n</squad>")
        self.assertEqual(count, 1)
        self.assertEqual(text, "<squad>\n</squad>")

    def test_comment_count_is_reported(self) -> None:
        doc = xmlread.parse("<squad>// one\n<name>a</name>\n</squad>", "unit")
        self.assertEqual(doc.comments, 1)
        self.assertTrue(any("comment" in warning for warning in doc.warnings))


class ToleranceTest(unittest.TestCase):
    def test_missing_root_is_an_error(self) -> None:
        with self.assertRaises(XmlStructureError) as caught:
            xmlread.parse("// only a comment\n", "unit")
        self.assertEqual(caught.exception.file, "unit")

    def test_unclosed_element_is_a_warning(self) -> None:
        doc = xmlread.parse("<squad><name>a</name>", "unit")
        self.assertTrue(any("unclosed" in warning for warning in doc.warnings))

    def test_crossed_tags_are_a_warning(self) -> None:
        doc = xmlread.parse("<a><b>x</a></b>", "unit")
        self.assertTrue(any("was open" in warning for warning in doc.warnings))

    def test_second_top_level_element_is_kept_under_the_root(self) -> None:
        doc = xmlread.parse("<squad></squad><weapon></weapon>", "unit")
        self.assertEqual(doc.root.tag, "squad")
        self.assertEqual([child.tag for child in doc.root.children], ["weapon"])

    def test_declaration_is_skipped(self) -> None:
        doc = xmlread.parse("<?xml version=\"1.0\"?><squad><name>a</name></squad>", "unit")
        self.assertEqual(doc.root.tag, "squad")

    def test_by_tag_helper(self) -> None:
        element = XmlElement(tag="squad", line=0)
        element.children = [XmlElement(tag="man", line=0), XmlElement(tag="description", line=0)]
        self.assertEqual([child.tag for child in element.by_tag("man")], ["man"])


if __name__ == "__main__":
    unittest.main()
