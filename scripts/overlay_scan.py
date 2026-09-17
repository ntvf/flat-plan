#!/usr/bin/env python3
"""Overlay the transcribed layout on the original surveyed plan photo.

The photo is a to-scale drawing, so the outer wall poche gives an independent
check of every contour.  The scan is anisotropic, so X and Y are calibrated
separately from the bounding box of the wall poche.

    python3 scripts/overlay_scan.py data/as_is.yaml <scan.jfif> out.png
"""
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from model_loader import load_model

POCHE_LO, POCHE_HI = 100, 185


def wall_mask(img):
    """Isolate the solid wall poche, dropping thin dimension lines and text."""
    g = img.convert("L")
    m = g.point(lambda v: 255 if POCHE_LO <= v <= POCHE_HI else 0)
    m = m.filter(ImageFilter.MinFilter(5))   # erode away hairlines / glyphs
    m = m.filter(ImageFilter.MaxFilter(5))   # dilate the survivors back
    return m


def mask_bbox(mask, min_run=40):
    """Bounding box of the poche, ignoring rows/cols with only a few pixels."""
    a = np.asarray(mask) > 127
    xs = np.flatnonzero(a.sum(axis=0) >= min_run)
    ys = np.flatnonzero(a.sum(axis=1) >= min_run)
    return int(xs[0]), int(ys[0]), int(xs[-1]), int(ys[-1])


def main():
    layout_path, scan_path, out_path = sys.argv[1:4]
    data = load_model(layout_path)

    scan = Image.open(scan_path).convert("RGB")
    mask = wall_mask(scan)
    x0, y0, x1, y1 = mask_bbox(mask)
    print(f"scan poche bbox px: x {x0}..{x1} ({x1 - x0})  y {y0}..{y1} ({y1 - y0})")

    outline = data["outline"]
    mx0 = min(p[0] for p in outline)
    mx1 = max(p[0] for p in outline)
    my0 = min(p[1] for p in outline)
    my1 = max(p[1] for p in outline)
    print(f"model outer extents m: {mx1 - mx0:.2f} x {my1 - my0:.2f}")

    # The raw poche bbox is contaminated by the balcony and entrance porch,
    # which sit outside the flat, and the drawn poche is schematic, so fit the
    # scale and offset on habitable space: the model's rooms against the white
    # space the scan leaves inside the plan.
    def rooms_mask_at(sx, sy, tx, ty, size, ss=1.0):
        img = Image.new("L", size, 0)
        dd = ImageDraw.Draw(img)

        def t(p):
            return ((tx + (p[0] - mx0) * sx) * ss, (ty - (p[1] - my0) * sy) * ss)

        for room in data["rooms"]:
            dd.polygon([t(p) for p in room["polygon"]], fill=255)
        return np.asarray(img) > 127

    SS = 0.5  # fit at half resolution for speed
    small = mask.resize((int(scan.width * SS), int(scan.height * SS)),
                        Image.NEAREST)
    ref = np.zeros((small.height, small.width), dtype=bool)
    ref[int(y0 * SS):int(y1 * SS), int(x0 * SS):int(x1 * SS)] = True
    ref &= ~(np.asarray(small) > 127)

    def iou(params):
        m = rooms_mask_at(*params, size=small.size, ss=SS)
        inter = np.count_nonzero(m & ref)
        union = np.count_nonzero(m | ref)
        return inter / union if union else 0.0

    best = (x0, y1)
    guess = [(x1 - x0) / (mx1 - mx0), (y1 - y0) / (my1 - my0), best[0], best[1]]
    step = [3.0, 3.0, 24.0, 24.0]
    score = iou(guess)
    for _ in range(40):
        improved = False
        for i in range(4):
            for sign in (1, -1):
                cand = list(guess)
                cand[i] += sign * step[i]
                s = iou(cand)
                if s > score:
                    score, guess, improved = s, cand, True
        if not improved:
            step = [v / 2 for v in step]
            if max(step) < 0.05:
                break
    sx, sy, tx, ty = guess
    print(f"fitted calibration: {sx:.1f} px/m in X, {sy:.1f} px/m in Y "
          f"({100 * (sx / sy - 1):+.1f}% anisotropy), fit IoU {score:.1%}")
    print(f"fit params: sx={sx:.4f} sy={sy:.4f} tx={tx:.2f} ty={ty:.2f} "
          f"mx0={mx0} my0={my0}")

    def T(p):
        """Model metres -> scan pixels (model Y is up, image Y is down)."""
        return (tx + (p[0] - mx0) * sx, ty - (p[1] - my0) * sy)

    def rect(at, size):
        ax, ay = at
        w, h = size
        return [(ax, ay), (ax + w, ay), (ax + w, ay + h), (ax, ay + h)]

    ov = Image.new("RGBA", scan.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    d.polygon([T(p) for p in outline], fill=(255, 0, 0, 55),
              outline=(255, 0, 0, 255), width=4)

    for group, colour in (("walls", (0, 90, 255, 200)),
                          ("columns", (255, 0, 255, 220)),
                          ("shafts", (0, 160, 0, 220))):
        for item in data.get(group) or []:
            d.polygon([T(p) for p in rect(item["at"], item["size"])],
                      fill=colour[:3] + (90,), outline=colour, width=3)

    for door in data.get("doors") or []:
        d.polygon([T(p) for p in rect(door["at"], door["size"])],
                  fill=(255, 200, 0, 170), outline=(220, 150, 0, 255), width=2)

    for win in data.get("windows") or []:
        d.polygon([T(p) for p in rect(win["at"], win["size"])],
                  fill=(0, 200, 255, 150), outline=(0, 90, 220, 255), width=3)

    for item in data.get("equipment") or []:
        corners = [T(p) for p in rect(item["at"][:2], item["size"][:2])]
        if item.get("shape") == "cylinder":
            xs, ys = zip(*corners)
            d.ellipse((min(xs), min(ys), max(xs), max(ys)),
                      fill=(255, 190, 0, 100), outline=(180, 110, 0, 255), width=2)
        else:
            d.polygon(corners, fill=(255, 190, 0, 100),
                      outline=(180, 110, 0, 255), width=2)

    for route in data.get("service_routes") or []:
        d.line([T(point[:2]) for point in route["points"]],
               fill=(0, 150, 130, 255), width=3)

    for finish in data.get("wall_finishes") or []:
        d.line([T(point) for point in finish["segment"]],
               fill=(165, 70, 25, 255), width=5)

    for room in data["rooms"]:
        d.polygon([T(p) for p in room["polygon"]],
                  outline=(255, 0, 0, 220), width=3)

    Image.alpha_composite(scan.convert("RGBA"), ov).convert("RGB").save(out_path)
    print("wrote", out_path)

    # --- contour agreement -------------------------------------------------
    # The scan draws its poche schematically (the east wall is drawn at ~0.17
    # although it is labelled 0.40), so comparing wall bodies is meaningless.
    # What is dimensionally real is the clear inner face of each room, so the
    # check is: does the model's habitable area cover the scan's white space?
    rooms_mask = Image.new("L", scan.size, 0)
    rd = ImageDraw.Draw(rooms_mask)
    for room in data["rooms"]:
        rd.polygon([T(p) for p in room["polygon"]], fill=255)
    for room in data["rooms"]:
        for hole in room.get("subtract") or []:
            other = next(r for r in data["rooms"] if r["id"] == hole)
            rd.polygon([T(p) for p in other["polygon"]], fill=255)
    a = np.asarray(rooms_mask) > 127

    envelope = Image.new("L", scan.size, 0)
    ImageDraw.Draw(envelope).polygon([T(p) for p in outline], fill=255)
    poche = np.asarray(mask) > 127
    # Scan's habitable space = inside the envelope and not drawn as wall.
    b = (np.asarray(envelope) > 127) & ~poche

    inter = np.count_nonzero(a & b)
    union = np.count_nonzero(a | b)
    only_model = np.count_nonzero(a & ~b)
    only_scan = np.count_nonzero(b & ~a)

    diff = np.full(a.shape + (3,), 255, dtype=np.uint8)
    diff[a & b] = (170, 170, 170)
    diff[a & ~b] = (255, 0, 0)
    diff[b & ~a] = (0, 140, 255)
    print(f"habitable-area agreement: IoU {inter / union:.1%}   "
          f"model-only {only_model / union:.1%} (red)   "
          f"scan-only {only_scan / union:.1%} (blue)")
    diff_path = out_path.replace(".png", "_diff.png")
    Image.fromarray(diff).save(diff_path)
    print("wrote", diff_path)

    # --- inner-face deviation ---------------------------------------------
    # Walk scanlines and pair up every model room edge with the nearest scan
    # wall face, reporting the residual in millimetres.
    px_m = (sx + sy) / 2
    devs = []
    for axis in (0, 1):
        n = a.shape[axis]
        for i in range(int(0.08 * n), int(0.92 * n), 7):
            av = a[i] if axis == 0 else a[:, i]
            bv = b[i] if axis == 0 else b[:, i]
            ae = np.flatnonzero(np.diff(av.astype(np.int8)) != 0)
            be = np.flatnonzero(np.diff(bv.astype(np.int8)) != 0)
            if not len(ae) or not len(be):
                continue
            for e in ae:
                devs.append(abs(int(e) - int(be[np.argmin(np.abs(be - e))])))
    devs = np.array(devs) / px_m
    print(f"inner-face deviation: median {1000 * np.median(devs):.0f} mm, "
          f"90th pct {1000 * np.percentile(devs, 90):.0f} mm, "
          f"max {1000 * devs.max():.0f} mm  (n={len(devs)})")


if __name__ == "__main__":
    main()
