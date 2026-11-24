import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import finishes as fin
from model_loader import load_model

MODEL = load_model(Path(__file__).resolve().parents[1] / "data" / "target.yaml")


class FinishesTest(unittest.TestCase):
    def test_open_space_split_into_tile_and_wood_covers_the_room(self):
        zones = {z["id"]: z for z in fin.floors(MODEL)}
        room = fin.room_region(MODEL, 123).area()
        self.assertAlmostEqual(room, zones["FL_OPEN"]["area"] + zones["FL_LIVING"]["area"], places=4)

    def test_bathroom_floor_excludes_bath_but_tiles_the_tray(self):
        zones = {z["id"]: z for z in fin.floors(MODEL)}
        items = {i["id"]: i for i in MODEL["furniture"]}
        w, d = items["B11"]["size"][:2]
        self.assertAlmostEqual(fin.room_region(MODEL, 4).area() - w * d, zones["FL_BATH1"]["area"], places=4)
        self.assertAlmostEqual(fin.room_region(MODEL, 9).area(), zones["FL_BATH2"]["area"], places=4)

    def test_bath_panel_clads_only_its_exposed_sides(self):
        bath = next(c for c in fin.clad_items(MODEL, 4) if c["id"] == "B11")
        self.assertEqual(["N", "E"], [s[0] for s in bath["sides"]])
        self.assertAlmostEqual((1.70 + 0.75) * 0.55, bath["area"], places=4)
        self.assertIn("B11", {c["id"] for c in fin.clad_items(MODEL)})

    def test_floor_tile_cuts_are_not_slivers(self):
        for zone in fin.floors(MODEL):
            if "min_cut" in zone:
                self.assertGreaterEqual(min(zone["min_cut"]), 0.10, zone["id"])

    def test_leaves_wall_is_one_cut_tile_per_row(self):
        face = next(w for w in fin.walls(MODEL) if w["material"] == "tile_leaves")
        self.assertAlmostEqual(0.96, face["face"]["length"], places=3)
        self.assertEqual(4, face["pieces"])

    def test_cut_rows_are_at_the_bottom_and_never_under_half_a_tile(self):
        self.assertEqual((0.0, 0.0, 0.0), fin.row_origin(2.40, 0.30))
        oz, bottom, top = fin.row_origin(2.55, 0.30)
        self.assertAlmostEqual(0.15, bottom)
        self.assertEqual(0.0, top)
        oz, bottom, top = fin.row_origin(2.50, 0.30)
        self.assertAlmostEqual(0.20, bottom)
        self.assertAlmostEqual(0.20, top)

    def test_splash_back_spans_its_band(self):
        for seg in fin.splash(MODEL):
            self.assertAlmostEqual(seg["length"] * (seg["top"] - seg["base"]), seg["area"], places=4)
