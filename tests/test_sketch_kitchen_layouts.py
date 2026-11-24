import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sketch_kitchen_layouts import OPTIONS, analyse, load_model


class KitchenLayoutsTest(unittest.TestCase):
    def test_prep_excludes_square_corners_but_runs_round_the_chamfer(self):
        model = load_model(Path(__file__).resolve().parents[1] / "data" / "target.yaml")
        for slug, main, secondary, total in (
            ("A_existing_nw_corner", "110 cm", "0 cm", "110 cm"),
            ("B_open_L_bathroom2_wall", "110 cm", "60 cm", "170 cm"),
            ("D_open_east_wall", "120 cm", "60 cm", "180 cm"),
            ("E_nw_connected_peninsula", "180 cm", "0 cm", "180 cm"),
            ("F_galley_with_180_wall", "120 cm", "60 cm", "180 cm"),
            ("G_nw_U_behind_entrance_wall", "170 cm", "60 cm", "230 cm"),
            ("G2_nw_U_with_entrance_wardrobe", "110 cm", "60 cm", "170 cm"),
            ("H_nw_U_corner_sink_window_prep", "79 cm", "80 cm", "159 cm"),
        ):
            with self.subTest(slug=slug):
                option = copy.deepcopy(next(o for o in OPTIONS if o["slug"] == slug))
                checks = {name: (value, ok) for name, value, ok, _ in
                          analyse(option, model)["analysis"]["checks"]}
                self.assertEqual(main, checks["Main straight prep sink↔hob"][0])
                self.assertEqual((secondary, True), checks["Secondary straight prep"])
                self.assertEqual((total, int(total.split()[0]) >= 160), checks["Total straight prep"])
                self.assertTrue(checks["Narrowest work aisle"][1])
                if slug == "E_nw_connected_peninsula":
                    self.assertEqual(("0 / 45 cm", False), checks["Sink straight landings"])
