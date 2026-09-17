#!/usr/bin/env python3
"""Detect window openings in the surveyed plan photo.

Windows are drawn as a break in the wall poche, so walking a band along each
exterior wall and looking for runs with no poche gives their true positions.
Emits a YAML `windows:` block ready to paste into the layout file.

    python3 scripts/detect_windows.py <scan.jfif>
"""
import sys

import numpy as np
from PIL import Image

from overlay_scan import wall_mask

# Calibration fitted by scripts/overlay_scan.py (habitable-area alignment).
SX, SY, TX, TY = 98.8796, 99.9101, 88.0, 1419.0
MIN_WIDTH = 0.50  # ignore breaks narrower than this; they are door reveals

# (id, axis, band start/end across the wall, run start/end along the wall)
BANDS = [
    ("south_56", "x", (-0.20, 0.60), (0.00, 6.09)),
    ("south_7", "x", (0.74, 1.54), (6.09, 9.43)),
    ("north", "x", (12.69, 13.49), (2.14, 9.43)),
    ("east", "y", (9.03, 9.63), (0.94, 13.29)),
    ("west_low", "y", (-0.20, 0.60), (0.00, 7.20)),
    ("west_up", "y", (0.80, 1.60), (8.09, 12.15)),
]


def px(x):
    return int(round(TX + x * SX))


def py(y):
    return int(round(TY - y * SY))


def runs_below(counts, thresh):
    out, start = [], None
    for i, c in enumerate(counts):
        if c <= thresh and start is None:
            start = i
        elif c > thresh and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(counts)))
    return out


def main():
    scan = Image.open(sys.argv[1]).convert("RGB")
    m = np.asarray(wall_mask(scan)) > 127

    print("windows:")
    for name, axis, band, span in BANDS:
        if axis == "x":
            sub = m[py(band[1]):py(band[0]), px(span[0]):px(span[1])]
            counts = sub.sum(axis=0)
            to_m = lambda i: span[0] + i / SX  # noqa: E731
        else:
            sub = m[py(span[1]):py(span[0]), px(band[0]):px(band[1])]
            counts = sub.sum(axis=1)[::-1]  # walk south -> north
            to_m = lambda i: span[0] + i / SY  # noqa: E731

        solid = int(np.median(counts[counts > 0])) if (counts > 0).any() else 0
        found = []
        for a, b in runs_below(counts, max(1, solid // 4)):
            lo, hi = to_m(a), to_m(b)
            if hi - lo >= MIN_WIDTH:
                found.append((lo, hi))

        print(f"  # {name}: wall poche {solid} px thick")
        for lo, hi in found:
            if axis == "x":
                print(f"  - {{ id: W_{name}_{len(found)}, wall: {name}, "
                      f"at: [{lo:.2f}, {band[0] + 0.20:.2f}], "
                      f"size: [{hi - lo:.2f}, 0.40] }}")
            else:
                print(f"  - {{ id: W_{name}_{len(found)}, wall: {name}, "
                      f"at: [{band[0] + 0.20:.2f}, {lo:.2f}], "
                      f"size: [0.40, {hi - lo:.2f}] }}")
        if not found:
            print("  #   (no openings detected)")


if __name__ == "__main__":
    main()
