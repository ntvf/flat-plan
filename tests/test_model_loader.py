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
        self.assertFalse(base_doors["D4"]["has_leaf"])
        self.assertTrue(target_doors["D4"]["has_leaf"])
        self.assertTrue(target_doors["D9"]["has_leaf"])
        self.assertEqual([2.32, 6.005], base_doors["D4"]["at"])
        self.assertEqual([3.32, 6.515], base_doors["D8"]["at"])
        self.assertEqual([1.0, 8.28], base_doors["entry"]["at"])
        apertures = {item["id"]: item for item in base["windows"]}
        self.assertEqual("IfcWindow", apertures["OB1"].get("ifc_class", "IfcWindow"))
        self.assertEqual("IfcDoor", apertures["OB2"]["ifc_class"])
        self.assertEqual([4.26, 0.0], apertures["OK6"]["at"])
        self.assertEqual([1.6, 0.4], apertures["OK6"]["size"])
        self.assertEqual([5.69, 0.0], apertures["DK6"]["at"])
        self.assertEqual([0.4, 0.79], apertures["DK6"]["size"])
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
        routes = {route["id"]: route for route in base["service_routes"]}
        self.assertEqual("OB3", routes["AC_living_lines"]["destination"])
        self.assertEqual([6.765, 12.89, 0.05],
                         routes["AC_living_lines"]["points"][-1])
        target_equipment = {item["id"]: item for item in target["equipment"]}
        self.assertEqual([7.09, 7.455, 2.33],
                         target_equipment["AC_living"]["at"])
        self.assertEqual("relocated",
                         target_equipment["AC_living"]["renovation_status"])
        target_routes = {route["id"]: route for route in target["service_routes"]}
        self.assertEqual("retained_and_reused",
                         target_routes["AC_living_lines"]["renovation_status"])
        self.assertEqual("refrigerant_and_control",
                         target_routes["AC_living_extension_bath_ceiling"]["system"])
        extension = target_routes["AC_living_extension_bath_ceiling"]
        self.assertTrue(all(point[0] == 7.49 for point in extension["points"]))
        self.assertEqual([7.49, 7.3925, 2.48], extension["points"][-1])
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
