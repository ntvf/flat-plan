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
        apertures = {item["id"]: item for item in base["windows"]}
        self.assertEqual("IfcWindow", apertures["OB1"].get("ifc_class", "IfcWindow"))
        self.assertEqual("IfcDoor", apertures["OB2"]["ifc_class"])
        self.assertEqual([4.26, 0.0], apertures["OK6"]["at"])
        self.assertEqual([1.6, 0.4], apertures["OK6"]["size"])
        self.assertEqual([5.69, 0.0], apertures["DK6"]["at"])
        self.assertEqual([0.4, 0.79], apertures["DK6"]["size"])

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
