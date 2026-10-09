"""Tests for the path-keyed schema.

The coverage test reads ``docs/baseline/path-inventory.tsv``, so the committed
declarations stay tied to the committed measurement.
"""

import csv
import dataclasses
import unittest
from pathlib import Path

from core.schema import ARRAY, LEAF, SCHEMAS, TABLE, Node, Schema, schema_for

INVENTORY = Path(__file__).resolve().parents[1] / "docs" / "baseline" / "path-inventory.tsv"
SHAPE_ORDER = {LEAF: 0, TABLE: 1, ARRAY: 2}


def inventory_rows():
    with INVENTORY.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


def walk_paths(node, prefix=()):
    path = (*prefix, node.name)
    yield path, node
    for child in node.children:
        yield from walk_paths(child, path)


class InventoryCoverageTest(unittest.TestCase):
    """Every measured path resolves, with the shape the measurement implies."""

    def test_every_inventory_path_resolves_with_the_measured_shape(self):
        rows = inventory_rows()
        self.assertGreater(len(rows), 0)
        for row in rows:
            with self.subTest(path=row["path"]):
                schema = schema_for(row["root"])
                self.assertIsNotNone(schema)
                node = schema.lookup(tuple(row["path"].split("/")))
                self.assertIsNotNone(node)
                if row["shape"] == "mixed":
                    # weapon/dimensions: the schema fixes one shape for the
                    # field; the empty instances render as empty tables.
                    expected = TABLE
                elif row["shape"] == "branch":
                    expected = ARRAY if int(row["max_per_instance"]) > 1 else TABLE
                else:
                    expected = LEAF
                self.assertEqual(node.shape, expected)

    def test_every_root_in_the_inventory_has_a_schema(self):
        roots = {row["root"] for row in inventory_rows()}
        self.assertEqual(roots, set(SCHEMAS))

    def test_array_nodes_match_the_rows_that_repeat(self):
        expected = {
            tuple(row["path"].split("/"))
            for row in inventory_rows()
            if row["shape"] == "branch" and int(row["max_per_instance"]) > 1
        }
        actual = {
            path
            for schema in SCHEMAS.values()
            for path, node in walk_paths(schema.root)
            if node.shape == ARRAY
        }
        self.assertEqual(actual, expected)


class StructureTest(unittest.TestCase):
    def test_every_root_is_a_table(self):
        for name, schema in SCHEMAS.items():
            with self.subTest(root=name):
                self.assertEqual(schema.root.name, name)
                self.assertEqual(schema.root.shape, TABLE)

    def test_child_names_are_unique_and_non_empty(self):
        for schema in SCHEMAS.values():
            for node in walk(schema.root):
                names = [child.name for child in node.children]
                with self.subTest(path=node.name):
                    self.assertEqual(len(names), len(set(names)))
                    for name in names:
                        self.assertNotEqual(name, "")
                        self.assertNotIn("/", name)

    def test_leaf_has_no_children_and_branches_have_children(self):
        for schema in SCHEMAS.values():
            for node in walk(schema.root):
                with self.subTest(path=node.name, shape=node.shape):
                    if node.shape == LEAF:
                        self.assertEqual(node.children, ())
                    else:
                        self.assertGreater(len(node.children), 0)

    def test_required_is_unused_in_m1(self):
        for schema in SCHEMAS.values():
            for node in walk(schema.root):
                self.assertFalse(node.required)

    def test_children_are_in_canonical_emission_order(self):
        for schema in SCHEMAS.values():
            for node in walk(schema.root):
                keys = [(SHAPE_ORDER[c.shape], c.name) for c in node.children]
                with self.subTest(path=node.name):
                    self.assertEqual(keys, sorted(keys))


class LookupTest(unittest.TestCase):
    def test_lookup_returns_the_root_for_the_bare_root_name(self):
        schema = schema_for("squad")
        self.assertIs(schema.lookup(("squad",)), schema.root)

    def test_lookup_rejects_an_empty_path_and_a_foreign_root(self):
        schema = schema_for("squad")
        self.assertIsNone(schema.lookup(()))
        self.assertIsNone(schema.lookup(("weapon", "type")))

    def test_lookup_rejects_an_unknown_child_at_any_depth(self):
        schema = schema_for("squad")
        self.assertIsNone(schema.lookup(("squad", "nope")))
        self.assertIsNone(schema.lookup(("squad", "vehicle", "hull", "nope")))

    def test_children_of_an_unknown_path_is_empty(self):
        schema = schema_for("squad")
        self.assertEqual(schema.children(("squad", "nope")), ())
        self.assertEqual(len(schema.children(("squad", "description"))), 9)

    def test_mod_is_not_covered_in_m1(self):
        self.assertIsNone(schema_for("mod"))
        self.assertIsNone(schema_for("Mod"))
        self.assertIsNone(schema_for(""))

    def test_schemas_are_immutable_declarations(self):
        node = schema_for("weapon").lookup(("weapon", "ammo", "type"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            node.name = "other"


class LiteralDeclarationTest(unittest.TestCase):
    """Spot checks that pin the decisions the tests above cannot see."""

    def test_armour_leaves_stay_text(self):
        armour = schema_for("squad").lookup(("squad", "vehicle", "hull", "armour"))
        self.assertIsNotNone(armour)
        for child in armour.children:
            with self.subTest(child=child.name):
                self.assertEqual(child.shape, LEAF)
                self.assertEqual(child.type, "str")

    def test_boolean_leaves(self):
        squad = schema_for("squad")
        self.assertEqual(squad.lookup(("squad", "man", "body_armour")).type, "bool")
        self.assertEqual(squad.lookup(("squad", "atgun", "AA")).type, "bool")
        self.assertEqual(squad.lookup(("squad", "atgun", "moveable")).type, "bool")
        weapon = schema_for("weapon")
        self.assertEqual(weapon.lookup(("weapon", "magazine", "single_shot")).type, "bool")
        self.assertEqual(weapon.lookup(("weapon", "shoot", "muzzle_flash")).type, "bool")

    def test_mixed_shape_path_is_a_table(self):
        self.assertEqual(schema_for("weapon").lookup(("weapon", "dimensions")).shape, TABLE)

    def test_same_tag_has_different_shapes_by_path(self):
        weapon = schema_for("weapon")
        self.assertEqual(weapon.lookup(("weapon", "type")).shape, LEAF)
        self.assertEqual(weapon.lookup(("weapon", "ammo", "type")).shape, ARRAY)
        squad = schema_for("squad")
        self.assertEqual(squad.lookup(("squad", "description", "type")).shape, LEAF)
        self.assertEqual(squad.lookup(("squad", "atgun", "weapon")).shape, TABLE)
        self.assertEqual(squad.lookup(("squad", "man", "weapon")).shape, ARRAY)

    def test_schema_is_a_plain_lookup_wrapper(self):
        schema = Schema(Node("root", TABLE))
        self.assertIsNone(schema.lookup(("root", "child")))
        self.assertEqual(schema.children(("root",)), ())


if __name__ == "__main__":
    unittest.main()
