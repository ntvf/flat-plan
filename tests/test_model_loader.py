import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from model_loader import load_model


class ModelLoaderTest(unittest.TestCase):
    def test_resolves_target_changes_without_mutating_base(self):
        root = Path(__file__).resolve().parents[1]
        base = load_model(root / "data" / "as_is.yaml")
        target = load_model(root / "data" / "target.yaml")

        self.assertNotIn(9, {room["id"] for room in base["rooms"]})
        self.assertIn(9, {room["id"] for room in target["rooms"]})
        open_living = next(room for room in target["rooms"] if room["id"] == 123)
        self.assertEqual([8, 9], open_living["subtract"])
        self.assertEqual("target", target["meta"]["state"])
        base_doors = {door["id"]: door for door in base["doors"]}
        target_doors = {door["id"]: door for door in target["doors"]}
        self.assertTrue(base_doors["D4"]["has_leaf"])
        self.assertTrue(target_doors["D4"]["has_leaf"])
        self.assertTrue(target_doors["D9"]["has_leaf"])
        self.assertEqual(["start", "+"], base_doors["D4"]["swing"])
        self.assertEqual(["end", "+"], base_doors["D8"]["swing"])
        self.assertEqual(["end", "-"], base_doors["D5"]["swing"])
        self.assertEqual(["start", "-"], base_doors["D6"]["swing"])
        self.assertEqual(["end", "+"], base_doors["D7"]["swing"])
        self.assertEqual([2.32, 6.005], base_doors["D4"]["at"])
        self.assertEqual([3.32, 6.515], base_doors["D8"]["at"])
        self.assertEqual([1.0, 8.28], base_doors["entry"]["at"])
        self.assertEqual(0.80, base_doors["D4"]["nominal_width"])
        self.assertEqual(0.80, base_doors["D8"]["nominal_width"])
        self.assertEqual(0.90, base_doors["D5"]["nominal_width"])
        self.assertEqual(0.80, base_doors["D6"]["nominal_width"])
        self.assertEqual(0.90, base_doors["D7"]["nominal_width"])
        self.assertEqual(0.80, target_doors["D9"]["nominal_width"])
        apertures = {item["id"]: item for item in base["windows"]}
        self.assertEqual("IfcWindow", apertures["OB1"].get("ifc_class", "IfcWindow"))
        self.assertEqual("IfcDoor", apertures["OB2"]["ifc_class"])
        self.assertEqual([4.26, 0.0], apertures["OK6"]["at"])
        self.assertEqual([1.6, 0.4], apertures["OK6"]["size"])
        self.assertEqual([5.69, 0.0], apertures["DK6"]["at"])
        self.assertEqual([0.4, 0.79], apertures["DK6"]["size"])
        self.assertEqual(3, apertures["OK5"]["render_panels"])
        self.assertEqual(2, apertures["OB1"]["render_panels"])
        self.assertEqual("wood", apertures["OB3"]["frame_material"])
        equipment = {item["id"]: item for item in base["equipment"]}
        self.assertEqual([7.09, 5.98, 2.33], equipment["AC_living"]["at"])
        self.assertEqual("open_living", equipment["AC_living"]["faces"])
        self.assertEqual(0.07,
                         equipment["AC_living"]["measured"]["top_below_ceiling"])
        self.assertEqual(100, equipment["HW_TANK_100L"]["capacity_l"])
        self.assertEqual([1.4, 10.17, 0.0], equipment["HW_TANK_100L"]["at"])
        self.assertEqual([0.6, 0.6, 1.15], equipment["HW_TANK_100L"]["size"])
        self.assertEqual("cylinder", equipment["HW_TANK_100L"]["shape"])
        self.assertEqual(1.29, equipment["HW_TANK_100L"]["measured"]
                         ["offset_from_entry_door"])
        self.assertEqual("tank centre", equipment["HW_TANK_100L"]["measured"]
                         ["offset_to"])
        self.assertEqual([0.6, 10.55, 1.45],
                         equipment["GAS_HEATER_ENTRY"]["at"])
        self.assertEqual("IfcBoiler",
                         equipment["GAS_HEATER_ENTRY"]["ifc_class"])
        self.assertEqual("exterior",
                         equipment["GAS_HEATER_ENTRY"]["room"])
        self.assertEqual(
            {
                "B4_BATH", "B4_BATH_FAUCET", "B4_BASIN",
                "B4_BASIN_FAUCET", "B4_WC", "B4_WC_FLUSH", "B4_WASHER",
            },
            {item_id for item_id in equipment if item_id.startswith("B4_")},
        )
        self.assertEqual("north", equipment["B4_WC"]["back"])
        self.assertEqual("wall", equipment["B4_WC"]["mounting"])
        self.assertEqual("concealed", equipment["B4_WC"]["cistern"])
        self.assertEqual([0.70, 7.25, 0.18], equipment["B4_WC"]["at"])
        self.assertEqual([0.40, 0.70, 0.24], equipment["B4_WC"]["size"])
        self.assertEqual("rectangular", equipment["B4_BASIN"]["shape"])
        self.assertEqual("faucet", equipment["B4_BATH_FAUCET"]["category"])
        self.assertEqual("flush_plate", equipment["B4_WC_FLUSH"]["category"])
        routes = {route["id"]: route for route in base["service_routes"]}
        self.assertFalse(routes["B4_WATER_BOX"]["geometry_visible"])
        self.assertFalse(routes["B4_DRAIN_BOX"]["geometry_visible"])
        self.assertFalse(routes["B4_WASHER_SERVICES"]["geometry_visible"])
        self.assertEqual("OB3", routes["AC_living_lines"]["destination"])
        self.assertEqual([6.765, 12.89, 0.05],
                         routes["AC_living_lines"]["points"][-1])
        target_equipment = {item["id"]: item for item in target["equipment"]}
        self.assertEqual([7.09, 7.455, 2.33],
                         target_equipment["AC_living"]["at"])
        self.assertEqual("relocated",
                         target_equipment["AC_living"]["renovation_status"])
        self.assertEqual([0.4, 10.375, 0.0],
                         target_equipment["HW_TANK_100L"]["at"])
        self.assertEqual("relocated",
                         target_equipment["HW_TANK_100L"]["renovation_status"])
        self.assertEqual("exterior",
                         target_equipment["HW_TANK_100L"]["room"])
        self.assertEqual(
            equipment["GAS_HEATER_ENTRY"],
            target_equipment["GAS_HEATER_ENTRY"],
        )
        self.assertEqual([1.52, 7.35, 0.85],
                         target_equipment["B4_WASHER"]["at"])
        self.assertEqual("stacked_on_dryer",
                         target_equipment["B4_WASHER"]["mounting"])
        self.assertEqual([1.52, 7.35, 0.0],
                         target_equipment["B4_DRYER"]["at"])
        self.assertEqual("dryer", target_equipment["B4_DRYER"]["category"])
        target_routes = {route["id"]: route for route in target["service_routes"]}
        self.assertEqual("retained_and_reused",
                         target_routes["AC_living_lines"]["renovation_status"])
        self.assertEqual("refrigerant_and_control",
                         target_routes["AC_living_extension_bath_ceiling"]["system"])
        extension = target_routes["AC_living_extension_bath_ceiling"]
        self.assertTrue(all(point[0] == 7.49 for point in extension["points"]))
        self.assertEqual([7.49, 7.3925, 2.48], extension["points"][-1])
        self.assertEqual(0.02, target_routes["B9_WC_DRAIN"]["slope"])
        self.assertEqual("IfcDuctSegment",
                         target_routes["B9_EXTRACT"]["ifc_class"])
        self.assertEqual(
            {
                "B9_BASIN", "B9_BASIN_FAUCET", "B9_WC", "B9_SHOWER",
                "B9_SHOWER_FAUCET",
            },
            {item_id for item_id in target_equipment if item_id.startswith("B9_")},
        )
        self.assertEqual("south", target_equipment["B9_WC"]["back"])
        target_wall = next(wall for wall in target["walls"]
                           if wall["id"] == "W_bath2_n")
        self.assertEqual([3.38, 0.125], target_wall["size"])
        finishes = {item["id"]: item for item in base["wall_finishes"]}
        self.assertEqual([[2.47, 12.88], [1.4, 12.17]],
                         finishes["BRICK_NW_CHAMFER"]["segment"])
        self.assertEqual([[1.4, 12.17], [1.4, 10.77]],
                         finishes["BRICK_WEST_TO_TANK"]["segment"])
        self.assertEqual([[8.95, 9.12], [8.95, 10.62]],
                         finishes["BRICK_EAST"]["segment"])
        self.assertEqual(0.8, finishes["BRICK_NORTH_OB1"]["base_height"])
        self.assertEqual(base["wall_finishes"], target["wall_finishes"])
        terminals = {item["id"]: item for item in base["service_terminals"]}
        self.assertEqual([0.4, 5.46], terminals["B4_BATH_CONNECTION"]["at"])
        self.assertEqual(
            0.30,
            terminals["B4_BATH_CONNECTION"]["connections"][0]["height"],
        )
        self.assertEqual([0.4, 6.455], terminals["B4_BASIN_CONNECTION"]["at"])
        self.assertEqual(
            0.35,
            terminals["B4_BASIN_CONNECTION"]["connections"][1]["height"],
        )
        self.assertEqual([1.0, 7.95], terminals["B4_WC_DRAIN"]["at"])
        self.assertEqual([1.82, 7.65],
                         terminals["B4_WASHER_CONNECTION"]["at"])
        self.assertEqual([3.29, 12.89],
                         terminals["KITCHEN_SINK_CONNECTION"]["at"])
        target_terminals = {
            item["id"]: item for item in target["service_terminals"]
        }
        self.assertEqual(
            terminals,
            {item_id: target_terminals[item_id] for item_id in terminals},
        )
        self.assertEqual(
            {"B9_BASIN_CONNECTION", "B9_WC_CONNECTION", "B9_SHOWER_CONNECTION"},
            {item_id for item_id in target_terminals if item_id.startswith("B9_")},
        )
        floor = base["floor_assemblies"][0]
        self.assertEqual(0.10, floor["total_thickness"])
        self.assertEqual(
            [0.05, 0.05],
            [layer["thickness"] for layer in floor["layers_top_down"]],
        )

    def test_bedroom_partitions_are_model_data(self):
        root = Path(__file__).resolve().parents[1]
        walls = {wall["id"]: wall for wall in load_model(root / "data" / "as_is.yaml")["walls"]}
        # Each bedroom wall fills the 0.10 gap between the clear room polygons.
        self.assertEqual(([0.40, 4.86], [2.97, 0.10]), (walls["W_bed5_n"]["at"], walls["W_bed5_n"]["size"]))
        self.assertEqual(([3.47, 4.86], [2.78, 0.10]), (walls["W_bed6_n"]["at"], walls["W_bed6_n"]["size"]))
        self.assertEqual(([3.37, 0.40], [0.10, 4.46]), (walls["W_bed5_6"]["at"], walls["W_bed5_6"]["size"]))
        self.assertEqual(([6.25, 1.34], [0.10, 4.54]), (walls["W_bed7_w"]["at"], walls["W_bed7_w"]["size"]))

    def test_furniture_is_target_only_design_data(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual([], load_model(root / "data" / "as_is.yaml")["furniture"])
        furniture = {item["id"]: item for item in load_model(root / "data" / "target.yaml")["furniture"]}
        self.assertEqual("corner_sofa", furniture["L_SOFA"]["category"])
        self.assertNotIn("L_ARMCHAIR", furniture)
        self.assertEqual([1.20, 0.60, 0.75], furniture["W_DESK"]["size"])
        self.assertEqual([0.60, 1.20, 0.90], furniture["K_ISLAND"]["size"])
        self.assertEqual([1.80, 0.90, 0.75], furniture["D_TABLE"]["size"])
        self.assertEqual("bench", furniture["D_BENCH"]["category"])
        # The sink stays centred on the surveyed connection under OB1.
        sink = furniture["K_SINK"]
        self.assertAlmostEqual(3.29, sink["at"][0] + sink["size"][0] / 2)
        rooms = {room["id"]: room for room in load_model(root / "data" / "target.yaml")["rooms"]}
        self.assertEqual(["parents", "boy", "grandmother"],
                         [rooms[i]["occupant"] for i in (5, 6, 7)])
        self.assertEqual({5: "B5_BED", 6: "B6_BED", 7: "B7_BED"},
                         {item["room"]: item["id"] for item in furniture.values()
                          if item["category"] == "bed"})

    def test_rejects_duplicate_addition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "base.yaml").write_text("rooms:\n  - {id: 1}\n", encoding="utf-8")
            (root / "target.yaml").write_text(
                "extends: base.yaml\nchanges:\n  add:\n    rooms:\n      - {id: 1}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cannot add existing id"):
                load_model(root / "target.yaml")


if __name__ == "__main__":
    unittest.main()
