"""Tests for core.refs: reference collection, indexing and target resolution."""

import shutil
import unittest
from pathlib import Path

from core import refs, xmlread

SCRATCH = Path(__file__).resolve().parent / "_scratch_refs"

SQUAD = """<squad>
	<description>
		<uniform>american_marines</uniform>
	</description>
	<man>
		<job>JOB_SQUAD_LEADER</job>
		<weapon><type>WEAPON_LMG_M1919</type></weapon>
		<ammo><for>WEAPON_LMG_M1919</for><rounds>2000</rounds></ammo>
	</man>
</squad>
"""

VEHICLE = """<squad>
	<vehicle>
		<turret>
			<image_view>Image-M2 Medium Tank turret.png</image_view>
			<weapon><type>WEAPON_CANNON_37_M6</type><offsetX>-2</offsetX></weapon>
			<ammo><for>WEAPON_MISSING</for><rounds>10</rounds></ammo>
		</turret>
	</vehicle>
</squad>
"""

WEAPON = """<weapon>
	<name>Bazooka M9</name>
	<type>WEAPON_RPG</type>
	<shoot>
		<sound_shoot>shoot_bazooka</sound_shoot>
	</shoot>
	<magazine>
		<sound_reload>reload_bazooka</sound_reload>
		<sound_eject_clip>eject_clip</sound_eject_clip>
	</magazine>
</weapon>
"""

AIRCRAFT = """<aircraft>
	<description>
		<image>Plane-Ilyushin IL-10.png</image>
	</description>
	<sound>SOUND_PROPELLER</sound>
	<armament>
		<weapon><type>WEAPON_LMG_M1919</type></weapon>
	</armament>
</aircraft>
"""

AT_GUN = """<squad>
	<vehicle>
		<hull>
			<image_view_base>Image-105mm Howitzer base.png</image_view_base>
			<image_view_gun>Image-105mm Howitzer gun.png</image_view_gun>
		</hull>
	</vehicle>
</squad>
"""


def parse(text: str, origin: str = "unit.txt"):
    return xmlread.parse(text, origin).root


class ScratchTest(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        (SCRATCH / "Data" / "Weapons").mkdir(parents=True)
        (SCRATCH / "Sounds" / "Engines").mkdir(parents=True)
        (SCRATCH / "Images" / "Units" / "Vehicles" / "Turrets").mkdir(parents=True)
        (SCRATCH / "Images" / "Units" / "Aircraft").mkdir(parents=True)
        (SCRATCH / "Images" / "Uniforms" / "uniform_american_marines").mkdir(parents=True)
        (SCRATCH / "Data" / "Weapons" / "WEAPON_CANNON_37_M6.toml").write_text("<weapon>", encoding="utf-8")
        (SCRATCH / "Data" / "Weapons" / "WEAPON_LMG_M1919.txt").write_text("<weapon>", encoding="utf-8")
        (SCRATCH / "Sounds" / "shoot_bazooka.ogg").write_bytes(b"OggS")
        (SCRATCH / "Sounds" / "eject_clip.ogg").write_bytes(b"OggS")
        (SCRATCH / "Sounds" / "Engines" / "plane_propeller.ogg").write_bytes(b"OggS")
        (SCRATCH / "Images" / "Units" / "Vehicles" / "Turrets" / "Image-M2 Medium Tank turret.png").write_bytes(b"\x89PNG")
        (SCRATCH / "Images" / "Units" / "Aircraft" / "Plane-Ilyushin IL-10.png").write_bytes(b"\x89PNG")
        (SCRATCH / "Images" / "Uniforms" / "uniform_ranks_german_waffen_SS.png").write_bytes(b"\x89PNG")

    def tearDown(self) -> None:
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def graph(self, *documents: tuple[str, str]) -> refs.RefGraph:
        graph = refs.RefGraph()
        for source, text in documents:
            graph.add(source, parse(text, source))
        return graph


class CollectionTest(ScratchTest):
    def test_finds_slot_ammo_and_uniform(self) -> None:
        found = refs.references_in(parse(SQUAD, "squad.txt"), "squad.txt")
        self.assertEqual(
            [(r.kind, r.value, r.path) for r in found],
            [
                ("uniform", "american_marines", ("squad", "description", "uniform")),
                ("weapon", "WEAPON_LMG_M1919", ("squad", "man", "weapon", "type")),
                ("weapon", "WEAPON_LMG_M1919", ("squad", "man", "ammo", "for")),
            ],
        )

    def test_weapon_document_type_is_a_category_not_a_reference(self) -> None:
        found = refs.references_in(parse(WEAPON, "weapon.txt"), "weapon.txt")
        self.assertEqual([r.kind for r in found], ["sound", "sound", "sound"])
        self.assertEqual([r.value for r in found], ["shoot_bazooka", "reload_bazooka", "eject_clip"])

    def test_aircraft_carries_image_engine_sound_and_weapon_slots(self) -> None:
        found = refs.references_in(parse(AIRCRAFT, "plane.txt"), "plane.txt")
        self.assertEqual(
            [(r.kind, r.value, r.path) for r in found],
            [
                ("image", "Plane-Ilyushin IL-10.png", ("aircraft", "description", "image")),
                ("engine_sound", "SOUND_PROPELLER", ("aircraft", "sound")),
                ("weapon", "WEAPON_LMG_M1919", ("aircraft", "armament", "weapon", "type")),
            ],
        )

    def test_at_gun_base_and_gun_images_are_references(self) -> None:
        found = refs.references_in(parse(AT_GUN, "at_gun.txt"), "at_gun.txt")
        self.assertEqual(
            [(r.kind, r.value) for r in found],
            [
                ("image", "Image-105mm Howitzer base.png"),
                ("image", "Image-105mm Howitzer gun.png"),
            ],
        )

    def test_uniform_ranks_is_a_full_file_name_reference(self) -> None:
        root = parse("<squad><description><uniform_ranks>uniform_ranks_german_waffen_SS.png</uniform_ranks></description></squad>")
        self.assertEqual(
            [(r.kind, r.value) for r in refs.references_in(root, "squad.txt")],
            [("image", "uniform_ranks_german_waffen_SS.png")],
        )

    def test_empty_leaf_is_not_a_reference(self) -> None:
        root = parse("<squad><description><uniform></uniform></description></squad>")
        self.assertEqual(refs.references_in(root, "squad.txt"), ())

    def test_unknown_leaf_is_not_a_reference(self) -> None:
        root = parse("<squad><description><type>TYPE_TANK</type></description></squad>")
        self.assertEqual(refs.references_in(root, "squad.txt"), ())


class GraphTest(ScratchTest):
    def test_indexes_both_directions(self) -> None:
        graph = self.graph(("squad.txt", SQUAD), ("vehicle.txt", VEHICLE))
        self.assertEqual(graph.sources(), ("squad.txt", "vehicle.txt"))
        self.assertEqual(len(graph.for_source("vehicle.txt")), 3)
        incoming = graph.for_target("weapon", "WEAPON_LMG_M1919")
        self.assertEqual([r.source for r in incoming], ["squad.txt", "squad.txt"])
        self.assertEqual(incoming[0].path, ("squad", "man", "weapon", "type"))

    def test_targets_are_distinct_and_sorted_by_kind(self) -> None:
        graph = self.graph(("squad.txt", SQUAD), ("vehicle.txt", VEHICLE))
        self.assertEqual(
            graph.targets("weapon"),
            (("weapon", "WEAPON_CANNON_37_M6"), ("weapon", "WEAPON_LMG_M1919"), ("weapon", "WEAPON_MISSING")),
        )
        self.assertEqual(graph.targets(), tuple(sorted(graph.targets())))

    def test_add_reports_how_many_references_were_added(self) -> None:
        graph = refs.RefGraph()
        self.assertEqual(graph.add("squad.txt", parse(SQUAD, "squad.txt")), 3)


class TargetIndexTest(ScratchTest):
    def test_resolves_each_kind_from_its_layout(self) -> None:
        index = refs.TargetIndex(SCRATCH)
        self.assertEqual(index.find("weapon", "WEAPON_CANNON_37_M6"), (SCRATCH / "Data" / "Weapons" / "WEAPON_CANNON_37_M6.toml",))
        self.assertEqual(index.find("weapon", "WEAPON_LMG_M1919"), (SCRATCH / "Data" / "Weapons" / "WEAPON_LMG_M1919.txt",))
        self.assertEqual(index.find("sound", "shoot_bazooka"), (SCRATCH / "Sounds" / "shoot_bazooka.ogg",))
        self.assertEqual(index.find("uniform", "american_marines"), (SCRATCH / "Images" / "Uniforms" / "uniform_american_marines",))

    def test_matches_images_by_file_name(self) -> None:
        index = refs.TargetIndex(SCRATCH)
        self.assertEqual(
            index.find("image", "Image-M2 Medium Tank turret.png"),
            (SCRATCH / "Images" / "Units" / "Vehicles" / "Turrets" / "Image-M2 Medium Tank turret.png",),
        )

    def test_matches_images_by_stem(self) -> None:
        index = refs.TargetIndex(SCRATCH)
        self.assertEqual(len(index.find("image", "Image-M2 Medium Tank turret")), 1)

    def test_image_lookup_ignores_case(self) -> None:
        # Stock aircraft data writes "Plane-Ilyushin Il-10.png" for a file named
        # "Plane-Ilyushin IL-10.png".
        index = refs.TargetIndex(SCRATCH)
        self.assertEqual(
            index.find("image", "Plane-Ilyushin Il-10.png"),
            (SCRATCH / "Images" / "Units" / "Aircraft" / "Plane-Ilyushin IL-10.png",),
        )

    def test_engine_sound_uses_the_alias_table(self) -> None:
        index = refs.TargetIndex(SCRATCH)
        self.assertEqual(index.find("engine_sound", "SOUND_PROPELLER"), (SCRATCH / "Sounds" / "Engines" / "plane_propeller.ogg",))
        self.assertEqual(index.find("engine_sound", "SOUND_UNKNOWN"), ())

    def test_missing_target_returns_nothing(self) -> None:
        index = refs.TargetIndex(SCRATCH)
        self.assertEqual(index.find("weapon", "WEAPON_MISSING"), ())
        self.assertEqual(index.find("sound", "shoot_missing"), ())

    def test_unknown_kind_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            refs.TargetIndex(SCRATCH).find("mesh", "x")

    def test_toml_is_preferred_over_txt(self) -> None:
        (SCRATCH / "Data" / "Weapons" / "WEAPON_BOTH.txt").write_text("<weapon>", encoding="utf-8")
        (SCRATCH / "Data" / "Weapons" / "WEAPON_BOTH.toml").write_text("<weapon>", encoding="utf-8")
        found = refs.TargetIndex(SCRATCH).find("weapon", "WEAPON_BOTH")
        self.assertEqual([path.suffix for path in found], [".toml", ".txt"])


class ReportTest(ScratchTest):
    def test_unresolved_lists_only_missing_targets(self) -> None:
        graph = self.graph(("squad.txt", SQUAD), ("vehicle.txt", VEHICLE))
        index = refs.TargetIndex(SCRATCH)
        self.assertEqual(
            [(r.source, r.kind, r.value) for r in refs.unresolved(graph, index)],
            [("vehicle.txt", "weapon", "WEAPON_MISSING")],
        )

    def test_unresolved_can_be_filtered_by_kind(self) -> None:
        graph = self.graph(("vehicle.txt", VEHICLE))
        index = refs.TargetIndex(SCRATCH)
        self.assertEqual(len(refs.unresolved(graph, index, "image")), 0)

    def test_summary_counts_per_kind(self) -> None:
        graph = self.graph(("squad.txt", SQUAD), ("vehicle.txt", VEHICLE), ("weapon.txt", WEAPON))
        report = refs.summary(graph, refs.TargetIndex(SCRATCH))
        self.assertEqual(report["weapon"], {"references": 4, "targets": 3, "unresolved": 1})
        self.assertEqual(report["sound"], {"references": 3, "targets": 3, "unresolved": 1})
        self.assertEqual(report["image"], {"references": 1, "targets": 1, "unresolved": 0})
        self.assertEqual(report["uniform"], {"references": 1, "targets": 1, "unresolved": 0})
        self.assertEqual(report["engine_sound"], {"references": 0, "targets": 0, "unresolved": 0})


if __name__ == "__main__":
    unittest.main()
