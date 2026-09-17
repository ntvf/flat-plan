"""
Compile a layout YAML into JSON so it can be consumed by Blender's bundled
Python, which has ifcopenshell but no PyYAML.

Usage: python3 scripts/yaml_to_json.py data/as_is.yaml build/as_is.json
"""

import json
import os
import sys

from model_loader import load_model


def main(src, dst):
    data = load_model(src)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"{src} -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
