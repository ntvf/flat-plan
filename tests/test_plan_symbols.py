import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from plan_symbols import (door_frame, door_leaf, door_swing_arc, window_frame,
                          window_handles, window_panes)


class PlanSymbolsTest(unittest.TestCase):
    def test_standard_leaf_is_centered_in_rough_opening(self):
        leaf = door_leaf(0.10, 0.90, 2.10, ["start", "+"], 0.80)
        self.assertEqual((0.10, 0.80, 0.04, 2.10),
                         (leaf[0][0], leaf[0][3], leaf[0][4], leaf[0][5]))
        self.assertAlmostEqual(0.05, leaf[0][1])
        arc = door_swing_arc(
            (2.32, 6.005), (0.10, 0.90), ["start", "+"],
            leaf_width=0.80,
        )
        self.assertAlmostEqual(6.055, arc[0][1])
        self.assertAlmostEqual(6.855, arc[-1][1])

    def test_door_frame_has_two_jambs_and_a_head(self):
        self.assertEqual(3, len(door_frame(0.90, 0.10, 2.10)))

    def test_three_panel_window_has_split_glazing_frame_and_handles(self):
        self.assertEqual(6, len(window_panes(1.60, 0.40, 1.30, 3)))
        self.assertEqual(6, len(window_frame(1.60, 0.40, 1.30, 3)))
        self.assertEqual(6, len(window_handles(1.60, 0.40, 1.30, 3)))


if __name__ == "__main__":
    unittest.main()
