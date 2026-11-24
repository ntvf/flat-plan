import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import room_views as rv
from make_room_sheets import chains_for, fit_chains, validate_furniture
from model_loader import load_model

MODEL = load_model(Path(__file__).resolve().parents[1] / "data" / "target.yaml")


class RoomSheetsTest(unittest.TestCase):
    def test_target_furniture_fits_rooms_without_overlaps(self):
        self.assertEqual([], validate_furniture(MODEL))

    def test_corner_sofa_overlap_is_checked_on_its_l_footprint(self):
        sofa = next(i for i in MODEL["furniture"] if i.get("l_shape"))
        main, chaise = rv.item_boxes(sofa, MODEL)
        x0, y0, x1, y1 = rv.item_rect(sofa)
        self.assertAlmostEqual((x1 - x0) * (y1 - y0) - (x1 - main[2]) * (y1 - chaise[3]),
                               sum((b[2] - b[0]) * (b[3] - b[1]) for b in (main, chaise)))
        probe = {"id": "P", "kind": "table", "room": sofa["room"],
                 "at": [x1 - 0.10, y1 - 0.10], "size": [0.05, 0.05, 0.4]}
        self.assertEqual([], validate_furniture({**MODEL, "furniture": [sofa, probe]}))
        probe["at"] = [x1 - 0.10, y0 + 0.05]
        self.assertIn("L09 overlaps P", validate_furniture({**MODEL, "furniture": [sofa, probe]}))

    def test_chains_measure_from_a_corner_and_stay_on_the_sheet(self):
        for sheet in rv.SHEETS:
            if not sheet.get("rooms"):
                continue
            with self.subTest(sheet=sheet["slug"]):
                chains = chains_for(MODEL, sheet, rv.sheet_items(MODEL, sheet))
                x0, y0, x1, y1 = fit_chains(rv.sheet_crop(MODEL, sheet), chains)
                for coords, fixed, horizontal, _side in chains:
                    self.assertTrue(all(b - a > 0.02 for a, b in zip(coords, coords[1:])))
                    lo, hi = (x0, x1) if horizontal else (y0, y1)
                    self.assertTrue(lo <= coords[0] and coords[-1] <= hi)
                    self.assertTrue((y0 if horizontal else x0) < fixed < (y1 if horizontal else x1))


if __name__ == "__main__":
    unittest.main()
