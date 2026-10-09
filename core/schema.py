"""Path-keyed schema for the three stock XML roots.

The declarations below were derived from the measurement recorded in
``docs/baseline/path-inventory.tsv``; ``tests/test_schema.py`` keeps the two in
agreement.  ``mod.txt`` is outside M1 (see ``docs/m1-design.md`` section 2.7).
"""

from dataclasses import dataclass
from typing import Literal

Shape = Literal["leaf", "table", "array"]
ValueType = Literal["int", "float", "bool", "str", "auto"]

LEAF: Shape = "leaf"
TABLE: Shape = "table"
ARRAY: Shape = "array"


@dataclass(frozen=True)
class Node:
    """One element declaration.  ``children`` is in canonical emission order."""

    name: str
    shape: Shape
    type: ValueType = "auto"
    children: tuple["Node", ...] = ()
    required: bool = False


@dataclass(frozen=True)
class Schema:
    """Lookup wrapper around one root declaration."""

    root: Node

    def lookup(self, path: tuple[str, ...]) -> Node | None:
        """Return the declaration for ``path`` (root name included), else None."""
        if not path or path[0] != self.root.name:
            return None
        node = self.root
        for name in path[1:]:
            for child in node.children:
                if child.name == name:
                    node = child
                    break
            else:
                return None
        return node

    def children(self, path: tuple[str, ...]) -> tuple[Node, ...]:
        """Return the declarations under ``path`` in canonical emission order."""
        node = self.lookup(path)
        return node.children if node else ()


# Children are grouped leaf, table, array, and sorted by name inside each group.
# That is the canonical emission order of the TOML writer (docs/toml-mapping.md
# section 4).

SQUAD = Node("squad", TABLE, children=(
    Node("atgun", TABLE, children=(
        Node("AA", LEAF, type="bool"),
        Node("image_profile", LEAF),
        Node("image_view_base", LEAF),
        Node("image_view_gun", LEAF),
        Node("mass", LEAF),
        Node("moveable", LEAF, type="bool"),
        Node("rotate_left", LEAF),
        Node("rotate_right", LEAF),
        Node("trail_length", LEAF),
        Node("weapon", TABLE, children=(
            Node("type", LEAF),
        )),
        Node("ammo", ARRAY, children=(
            Node("flavour", LEAF),
            Node("for", LEAF),
            Node("rounds", LEAF),
        )),
    )),
    Node("availability", TABLE, children=(
        Node("data", ARRAY, children=(
            Node("month", LEAF),
            Node("number", LEAF),
            Node("year", LEAF),
        )),
    )),
    Node("description", TABLE, children=(
        Node("comment", LEAF),
        Node("language", LEAF),
        Node("long_name", LEAF),
        Node("nationality", LEAF),
        Node("quality", LEAF),
        Node("short_name", LEAF),
        Node("type", LEAF),
        Node("uniform", LEAF),
        Node("uniform_ranks", LEAF),
    )),
    Node("hmg", TABLE, children=(
        Node("image_profile", LEAF),
        Node("image_view_base", LEAF),
        Node("image_view_gun", LEAF),
        Node("rotate_left", LEAF),
        Node("rotate_right", LEAF),
        Node("ammo", TABLE, children=(
            Node("for", LEAF),
            Node("rounds", LEAF),
        )),
        Node("weapon", TABLE, children=(
            Node("type", LEAF),
        )),
    )),
    Node("mortar", TABLE, children=(
        Node("image_profile", LEAF),
        Node("image_view_base", LEAF),
        Node("rotate_left", LEAF),
        Node("rotate_right", LEAF),
        Node("weapon", TABLE, children=(
            Node("type", LEAF),
        )),
        Node("ammo", ARRAY, children=(
            Node("flavour", LEAF),
            Node("for", LEAF),
            Node("rounds", LEAF),
        )),
    )),
    Node("recoilless_rifle", TABLE, children=(
        Node("image_profile", LEAF),
        Node("image_view_base", LEAF),
        Node("image_view_gun", LEAF),
        Node("rotate_left", LEAF),
        Node("rotate_right", LEAF),
        Node("weapon", TABLE, children=(
            Node("type", LEAF),
        )),
        Node("ammo", ARRAY, children=(
            Node("flavour", LEAF),
            Node("for", LEAF),
            Node("rounds", LEAF),
        )),
    )),
    Node("vehicle", TABLE, children=(
        Node("attributes", TABLE, children=(
            Node("can_mount_infantry", LEAF, type="bool"),
            Node("image_profile", LEAF),
            Node("is_amphibious", LEAF, type="bool"),
            Node("weight", LEAF),
        )),
        Node("drive", TABLE, children=(
            Node("can_make_smoke_screen", LEAF, type="bool"),
            Node("steering", LEAF),
            Node("engine", TABLE, children=(
                Node("horsepower", LEAF),
                Node("mount", LEAF),
                Node("name", LEAF),
                Node("reliability", LEAF),
                Node("rpm_idle", LEAF),
                Node("rpm_limit", LEAF),
            )),
            Node("gears", TABLE, children=(
                Node("forwards", LEAF),
                Node("reverse", LEAF),
            )),
            Node("exhaust_pipe", ARRAY, children=(
                Node("angle", LEAF),
                Node("offsetX", LEAF),
                Node("offsetY", LEAF),
                Node("vertical_angle", LEAF),
            )),
        )),
        Node("hull", TABLE, children=(
            Node("height", LEAF),
            Node("image_view", LEAF),
            Node("length", LEAF),
            Node("width", LEAF),
            Node("armour", TABLE, children=(
                Node("bottom", LEAF, type="str"),
                Node("front", LEAF, type="str"),
                Node("lower_front", LEAF, type="str"),
                Node("lower_rear", LEAF, type="str"),
                Node("lower_side", LEAF, type="str"),
                Node("rear", LEAF, type="str"),
                Node("side", LEAF, type="str"),
                Node("side_spaced", LEAF, type="str"),
                Node("top", LEAF, type="str"),
                Node("upper_front", LEAF, type="str"),
                Node("upper_rear", LEAF, type="str"),
                Node("upper_side", LEAF, type="str"),
            )),
            Node("man", ARRAY, children=(
                Node("job", LEAF),
                Node("ammo", TABLE, children=(
                    Node("for", LEAF),
                    Node("rounds", LEAF),
                )),
                Node("weapon", TABLE, children=(
                    Node("type", LEAF),
                )),
            )),
            Node("smoke_discharger", ARRAY, children=(
                Node("ammo", LEAF),
                Node("angle", LEAF),
                Node("elevation", LEAF),
                Node("offsetX", LEAF),
                Node("offsetY", LEAF),
                Node("reload", LEAF),
                Node("speed", LEAF),
            )),
        )),
        Node("fixed_weapon", ARRAY, children=(
            Node("AA", LEAF, type="bool"),
            Node("image_view", LEAF),
            Node("offsetX", LEAF),
            Node("offsetY", LEAF),
            Node("offsetZ", LEAF),
            Node("offset_angle", LEAF),
            Node("rotate_left", LEAF),
            Node("rotate_right", LEAF),
            Node("rotate_time", LEAF),
            Node("ammo", ARRAY, children=(
                Node("flavour", LEAF),
                Node("for", LEAF),
                Node("rounds", LEAF),
            )),
            Node("man", ARRAY, children=(
                Node("job", LEAF),
                Node("ammo", TABLE, children=(
                    Node("for", LEAF),
                    Node("rounds", LEAF),
                )),
                Node("weapon", TABLE, children=(
                    Node("type", LEAF),
                )),
            )),
            Node("weapon", ARRAY, children=(
                Node("mount", LEAF),
                Node("type", LEAF),
            )),
        )),
        Node("superstructure", ARRAY, children=(
            Node("height", LEAF),
            Node("length", LEAF),
            Node("offsetX", LEAF),
            Node("offsetY", LEAF),
            Node("width", LEAF),
            Node("armour", TABLE, children=(
                Node("front", LEAF, type="str"),
                Node("lower_front", LEAF, type="str"),
                Node("lower_rear", LEAF, type="str"),
                Node("lower_side", LEAF, type="str"),
                Node("rear", LEAF, type="str"),
                Node("side", LEAF, type="str"),
                Node("side_spaced", LEAF, type="str"),
                Node("top", LEAF, type="str"),
                Node("upper_front", LEAF, type="str"),
                Node("upper_rear", LEAF, type="str"),
                Node("upper_side", LEAF, type="str"),
            )),
            Node("smoke_discharger", ARRAY, children=(
                Node("ammo", LEAF),
                Node("angle", LEAF),
                Node("elevation", LEAF),
                Node("offsetX", LEAF),
                Node("offsetY", LEAF),
                Node("reload", LEAF),
                Node("speed", LEAF),
            )),
        )),
        Node("turret", ARRAY, children=(
            Node("AA", LEAF, type="bool"),
            Node("diameter", LEAF),
            Node("height", LEAF),
            Node("image_view", LEAF),
            Node("offsetX", LEAF),
            Node("offsetY", LEAF),
            Node("offset_angle", LEAF),
            Node("rotate_left", LEAF),
            Node("rotate_right", LEAF),
            Node("rotate_time", LEAF),
            Node("armour", TABLE, children=(
                Node("front", LEAF, type="str"),
                Node("lower_front", LEAF, type="str"),
                Node("lower_rear", LEAF, type="str"),
                Node("lower_side", LEAF, type="str"),
                Node("mantlet", LEAF),
                Node("rear", LEAF, type="str"),
                Node("rear_spaced", LEAF, type="str"),
                Node("side", LEAF, type="str"),
                Node("side_spaced", LEAF, type="str"),
                Node("top", LEAF, type="str"),
                Node("upper_front", LEAF, type="str"),
                Node("upper_rear", LEAF, type="str"),
                Node("upper_side", LEAF, type="str"),
            )),
            Node("ammo", ARRAY, children=(
                Node("flavour", LEAF),
                Node("for", LEAF),
                Node("rounds", LEAF),
            )),
            Node("man", ARRAY, children=(
                Node("job", LEAF),
                Node("weapon", TABLE, children=(
                    Node("type", LEAF),
                )),
                Node("ammo", ARRAY, children=(
                    Node("for", LEAF),
                    Node("rounds", LEAF),
                )),
            )),
            Node("smoke_discharger", ARRAY, children=(
                Node("ammo", LEAF),
                Node("angle", LEAF),
                Node("elevation", LEAF),
                Node("offsetX", LEAF),
                Node("offsetY", LEAF),
                Node("reload", LEAF),
                Node("speed", LEAF),
            )),
            Node("weapon", ARRAY, children=(
                Node("mount", LEAF),
                Node("offsetX", LEAF),
                Node("offsetY", LEAF),
                Node("offset_angle", LEAF),
                Node("type", LEAF),
            )),
        )),
    )),
    Node("man", ARRAY, children=(
        Node("body_armour", LEAF, type="bool"),
        Node("job", LEAF),
        Node("ammo", ARRAY, children=(
            Node("flavour", LEAF),
            Node("for", LEAF),
            Node("rounds", LEAF),
        )),
        Node("weapon", ARRAY, children=(
            Node("type", LEAF),
        )),
    )),
))


WEAPON = Node("weapon", TABLE, children=(
    Node("comments", LEAF),
    Node("name", LEAF),
    Node("type", LEAF),
    Node("ammo", TABLE, children=(
        Node("type", ARRAY, children=(
            Node("HE", LEAF),
            Node("era", LEAF),
            Node("explode_in", LEAF),
            Node("flavour", LEAF),
            Node("guided", LEAF),
            Node("mass", LEAF),
            Node("name", LEAF),
            Node("smoke_trail", LEAF, type="bool"),
            Node("speed", LEAF),
        )),
    )),
    Node("dimensions", TABLE, children=(
        Node("barrel_length", LEAF),
        Node("calibre", LEAF),
        Node("number_barrels", LEAF),
    )),
    Node("magazine", TABLE, children=(
        Node("capacity", LEAF),
        Node("single_shot", LEAF, type="bool"),
        Node("sound_eject_clip", LEAF),
        Node("sound_reload", LEAF),
    )),
    Node("shoot", TABLE, children=(
        Node("muzzle_flash", LEAF, type="bool"),
        Node("range", LEAF),
        Node("reload", LEAF),
        Node("rof", LEAF),
        Node("sound_shoot", LEAF),
    )),
    Node("usage", TABLE, children=(
        Node("countries", LEAF),
        Node("period", LEAF),
    )),
))


AIRCRAFT = Node("aircraft", TABLE, children=(
    Node("armament", TABLE, children=(
        Node("ammo", ARRAY, children=(
            Node("flavour", LEAF),
            Node("for", LEAF),
            Node("rounds", LEAF),
        )),
        Node("weapon", ARRAY, children=(
            Node("offsetX", LEAF),
            Node("offsetY", LEAF),
            Node("type", LEAF),
        )),
    )),
    Node("availability", TABLE, children=(
        Node("data", ARRAY, children=(
            Node("month", LEAF),
            Node("number", LEAF),
            Node("year", LEAF),
        )),
    )),
    Node("description", TABLE, children=(
        Node("comment", LEAF),
        Node("image", LEAF),
        Node("long_name", LEAF),
        Node("nationality", LEAF),
        Node("short_name", LEAF),
        Node("sound", LEAF),
        Node("speed", LEAF),
        Node("type", LEAF),
    )),
))


SCHEMAS: dict[str, Schema] = {
    "squad": Schema(SQUAD),
    "weapon": Schema(WEAPON),
    "aircraft": Schema(AIRCRAFT),
}


def schema_for(root_tag: str) -> Schema | None:
    """Return the schema for a root tag, or None when the root is not covered."""
    return SCHEMAS.get(root_tag)
