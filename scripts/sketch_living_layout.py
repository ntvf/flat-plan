#!/usr/bin/env python3
"""Furniture layout study for the target-state entrance, kitchen, dining and
living space (room 123).

Room geometry, windows, shafts, finishes and the AC are read from the target
model; the furniture below is a design aid, not authoritative model data.
The script fails if any piece leaves the room or collides with another, and
prints the working clearances it was laid out against.
"""
from pathlib import Path
import sys

from PIL import Image, ImageDraw

from fonts import load_font
from model_loader import load_model

MODEL = Path("data/target.yaml")
OUT = Path("exports/concepts/living_layout/recommended.png")

SCALE = 120                     # px per metre
VIEW = (0.85, 7.05, 9.60, 13.45)  # model-space crop: x0, y0, x1, y1
HEADER = 96
FOOTER = 300
SIDE = 30

COLORS = {
    "paper": "#fffdf8",
    "wall": "#2d333b",
    "room": "#f3ece0",
    "other_room": "#dfe3e6",
    "shaft": "#7d6b8a",
    "window": "#bfe0f2",
    "door": "#a5753d",
    "brick": "#b5562f",
    "worktop": "#d9c7a7",
    "tall": "#9c8a6b",
    "appliance": "#f6f3ec",
    "hall": "#c9b8d9",
    "dining": "#c7d9b8",
    "sofa": "#9fb6c9",
    "living": "#d6e4ee",
    "rug": "#ece4f0",
    "clearance": "#c0392b",
    "text": "#222831",
    "muted": "#616b76",
    "zone": "#a39a8c",
}

# Kitchen worktop as one polygon: west run from the fridge to the NW chamfer,
# a 0.60 m deep counter along the chamfer, then the north run to the dishwasher.
# The chamfer front line is the chamfer wall offset 0.60 m into the room.
WORKTOP = [(1.40, 10.55), (1.40, 12.17), (2.47, 12.89), (4.04, 12.89),
           (4.04, 12.29), (2.652, 12.29), (2.00, 11.851), (2.00, 10.55)]

# (id, x, y, width_x, depth_y, label, colour key, solid)
# `solid` pieces must not overlap each other; rugs and zones may.
FURNITURE = [
    # Hall
    ("SHOE", 3.45, 8.05, 1.60, 0.35, "Shoe cabinet 160×35\nhooks + mirror above", "hall", True),
    # Kitchen
    ("OVEN", 1.40, 9.35, 0.60, 0.60, "Oven +\nmicrowave\ntower", "tall", True),
    ("FRIDGE", 1.40, 9.95, 0.60, 0.60, "Fridge-\nfreezer", "tall", True),
    ("HOB", 1.44, 10.95, 0.52, 0.60, "Hob 60\n+ hood", "appliance", True),
    ("SINK", 2.99, 12.37, 0.60, 0.48, "Sink", "appliance", True),
    ("DW", 3.59, 12.29, 0.45, 0.60, "DW\n45", "appliance", True),
    # Dining
    ("TABLE", 3.10, 9.85, 1.60, 0.90, "Dining table 160×90\n(6 seats)", "dining", True),
    ("CH_N1", 3.35, 10.75, 0.45, 0.50, "", "dining", True),
    ("CH_N2", 4.00, 10.75, 0.45, 0.50, "", "dining", True),
    ("CH_S1", 3.35, 9.35, 0.45, 0.50, "", "dining", True),
    ("CH_S2", 4.00, 9.35, 0.45, 0.50, "", "dining", True),
    # Living
    ("RUG", 6.45, 8.55, 2.00, 2.70, "", "rug", False),
    ("SOFA", 5.85, 8.70, 0.95, 2.40, "Sofa 240\n3-seat", "sofa", True),
    ("COFFEE", 7.25, 9.40, 0.60, 1.00, "Coffee\ntable", "living", True),
    ("TV", 8.55, 8.97, 0.40, 1.80, "TV\n180\n×40", "living", True),
    ("CHAIR", 7.95, 11.75, 0.80, 0.80, "Armchair\n+ lamp", "sofa", True),
    ("SIDEBOARD", 5.50, 7.455, 2.40, 0.40, "Sideboard / bookcase 240×40 (≤1.8 m high, below AC)", "living", True),
]

# Label nudges in metres, where a symbol would sit on top of the text.
LABEL_OFFSET = {"TABLE": (0.0, -0.24)}

# Context labels for the rooms around the open space.
CONTEXT = [("Bathroom 1", 1.90, 7.50), ("to bedrooms\n& bathroom 2", 2.87, 7.45),
           ("Storage", 4.29, 7.50), ("Bathroom 2", 7.00, 7.19)]

# Working clearances: (label, axis, from, to, at) — measured in model metres.
CLEARANCES = [
    ("kitchen aisle", "x", 2.00, 3.10, 10.30, 1.00),
    ("sink aisle", "y", 11.25, 12.29, 3.75, 0.90),
    ("hall path", "y", 8.40, 9.35, 4.70, 0.85),
    ("to balcony", "x", 4.70, 5.85, 11.00, 0.90),
    ("legroom", "x", 6.80, 7.25, 9.20, 0.40),
    ("TV path", "x", 7.85, 8.55, 9.20, 0.60),
]


def font(size, bold=False):
    return load_font(size, bold)


def px(x, y):
    return (SIDE + (x - VIEW[0]) * SCALE, HEADER + (VIEW[3] - y) * SCALE)


def poly(draw, points, fill, outline=None, width=1):
    draw.polygon([px(*p) for p in points], fill=fill, outline=outline, width=width)


def rect_points(x, y, w, d):
    return [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]


def inside(point, polygon):
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def overlaps(a, b, eps=1e-6):
    _, ax, ay, aw, ad, *_ = a
    _, bx, by, bw, bd, *_ = b
    return ax < bx + bw - eps and bx < ax + aw - eps and ay < by + bd - eps and by < ay + ad - eps


def validate(model):
    rooms = {r["id"]: r for r in model["rooms"]}
    space = rooms[123]["polygon"]
    blocked = [rooms[i].get("footprint", rooms[i]["polygon"]) for i in rooms[123].get("subtract", [])]

    def free(p):
        # Nudge sample points just inside each piece so wall-hugging edges pass.
        return inside(p, space) and not any(inside(p, b) for b in blocked)

    errors = []
    for item in FURNITURE:
        fid, x, y, w, d = item[:5]
        samples = [(x + w * u, y + d * v) for u in (0.01, 0.5, 0.99) for v in (0.01, 0.5, 0.99)]
        if not all(free(p) for p in samples):
            errors.append(f"{fid} leaves the open space")
    solid = [f for f in FURNITURE if f[7]]
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if overlaps(a, b):
                errors.append(f"{a[0]} overlaps {b[0]}")
    for label, _axis, start, end, _at, minimum in CLEARANCES:
        if end - start + 1e-6 < minimum:
            errors.append(f"{label} is {end - start:.2f} m, below {minimum:.2f} m")
    if errors:
        sys.exit("living layout invalid:\n  " + "\n  ".join(errors))
    for label, _axis, start, end, _at, minimum in CLEARANCES:
        print(f"  {label:<14} {end - start:.2f} m  (min {minimum:.2f})")


def draw_text_block(draw, x, y, text, size, fill, anchor="mm"):
    draw.multiline_text((x, y), text, font=font(size), fill=fill, anchor=anchor,
                        align="center", spacing=1)


def draw_plan(draw, model):
    rooms = {r["id"]: r for r in model["rooms"]}

    poly(draw, model["outline"], COLORS["wall"])
    for room in model["rooms"]:
        if room["id"] != 123:
            poly(draw, room.get("footprint", room["polygon"]), COLORS["wall"])
    poly(draw, rooms[123]["polygon"], COLORS["room"])
    for rid in rooms[123].get("subtract", []):
        poly(draw, rooms[rid].get("footprint", rooms[rid]["polygon"]), COLORS["wall"])
    for room in model["rooms"]:
        if room["id"] != 123:
            poly(draw, room["polygon"], COLORS["other_room"])
    for text, x, y in CONTEXT:
        draw_text_block(draw, *px(x, y), text, 13, COLORS["muted"])

    for shaft in model["shafts"]:
        x, y = shaft["at"]
        w, d = shaft["size"]
        poly(draw, rect_points(x, y, w, d), COLORS["shaft"])

    for win in model["windows"]:
        if win["id"] in ("OB1", "OB2", "OB3"):
            x, y = win["at"]
            w, d = win["size"]
            poly(draw, rect_points(x, y, w, d), COLORS["window"], COLORS["wall"])
            draw_text_block(draw, *px(x + w / 2, y + d / 2), win["id"], 13, COLORS["text"])

    for fin in model["wall_finishes"]:
        (x1, y1), (x2, y2) = fin["segment"]
        draw.line([px(x1, y1), px(x2, y2)], fill=COLORS["brick"], width=7)

    entry = next(d for d in model["doors"] if d["id"] == "entry")
    ex, ey = entry["at"]
    ew, ed = entry["size"]
    poly(draw, rect_points(ex, ey, ew, ed), COLORS["room"])
    hinge = px(1.40, ey)
    r = 0.90 * SCALE
    draw.arc((hinge[0] - r, hinge[1] - r, hinge[0] + r, hinge[1] + r), 270, 360, fill=COLORS["door"], width=2)
    draw.line([hinge, px(2.30, ey)], fill=COLORS["door"], width=5)
    draw_text_block(draw, *px(0.93, ey + 0.45), "ENTRY", 13, COLORS["text"])

    # Balcony door: hinge side not surveyed, so keep its whole sweep clear.
    x0, x1 = 4.13, 5.59
    for xa, xb in ((x0, x0 + 0.73), (x1 - 0.73, x1)):
        poly(draw, rect_points(xa, 12.16, xb - xa, 0.73), None, COLORS["door"])
    draw_text_block(draw, *px((x0 + x1) / 2, 12.50), "balcony door\nkeep clear", 12, COLORS["door"])

    ac = next(e for e in model["equipment"] if e["id"] == "AC_living")
    ax, ay, _ = ac["at"]
    aw, ad, _ = ac["size"]
    box = [px(ax, ay + ad + 0.42), px(ax + aw, ay + 0.42)]
    draw.rectangle(box, outline=COLORS["muted"], width=2)
    draw_text_block(draw, (box[0][0] + box[1][0]) / 2, (box[0][1] + box[1][1]) / 2, "AC (2.3 m)", 11, COLORS["muted"])


def draw_furniture(draw):
    poly(draw, WORKTOP, COLORS["worktop"], COLORS["wall"], 2)
    draw_text_block(draw, *px(2.05, 12.32), "prep\ncorner", 12, COLORS["text"])

    for fid, x, y, w, d, label, colour, solid in FURNITURE:
        outline = COLORS["wall"] if solid else None
        poly(draw, rect_points(x, y, w, d), COLORS[colour], outline, 2 if solid else 1)
        if label:
            dx, dy = LABEL_OFFSET.get(fid, (0.0, 0.0))
            draw_text_block(draw, *px(x + w / 2 + dx, y + d / 2 + dy), label, 12, COLORS["text"])

    # Dining pendant over the table centre.
    cx, cy = px(3.90, 10.30)
    draw.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), outline=COLORS["text"], width=2)
    draw.line([(cx - 13, cy), (cx + 13, cy)], fill=COLORS["text"], width=1)
    draw.line([(cx, cy - 13), (cx, cy + 13)], fill=COLORS["text"], width=1)


def draw_clearances(draw):
    for label, axis, start, end, at, _minimum in CLEARANCES:
        if axis == "x":
            a, b = px(start, at), px(end, at)
        else:
            a, b = px(at, start), px(at, end)
        draw.line([a, b], fill=COLORS["clearance"], width=2)
        for p in (a, b):
            draw.ellipse((p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3), fill=COLORS["clearance"])
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        offset = (0, -10) if axis == "x" else (22, 0)
        draw.text((mx + offset[0], my + offset[1]), f"{end - start:.2f}", font=font(13, True),
                  fill=COLORS["clearance"], anchor="mm")


def draw_zones(draw):
    for text, x, y in (("HALL", 2.25, 8.55), ("KITCHEN", 2.75, 11.35),
                       ("DINING", 3.90, 11.45), ("LIVING", 7.30, 12.30)):
        draw.text(px(x, y), text, font=font(20, True), fill=COLORS["zone"], anchor="mm")


def draw_frame(draw, width, height):
    draw.text((SIDE, 22), "Entrance, kitchen, dining & living — recommended layout",
              font=font(24, True), fill=COLORS["text"])
    draw.text((SIDE, 58), "Target state, room 123 · geometry from data/target.yaml · "
              "furniture is a concept · red = clearances (m)",
              font=font(15), fill=COLORS["muted"])
    # North arrow (Y grows north, up the page).
    nx, ny = width - 60, HEADER + 40
    draw.polygon([(nx, ny - 26), (nx - 11, ny + 8), (nx + 11, ny + 8)], fill=COLORS["text"])
    draw.text((nx, ny + 22), "N", font=font(16, True), fill=COLORS["text"], anchor="mm")

    notes = [
        "Hall: land on clear floor; shoes and guests' coats at the 160×35 cabinet with hooks and mirror on the storage wall;",
        "      family coats, vacuum and bulky items go in the storage room (Schowek), 3 m from the door.",
        "Kitchen: stays on the existing NW plumbing. Tall oven tower and fridge on the plain wall freed by moving the hot-water tank out;",
        "      hob on the brick wall (fit a glass splashback behind it), prep in the chamfer corner, sink centred under OB1 on the",
        "      existing connection, 45 cm dishwasher beside it, stopping clear of the balcony door. Use a low or folding tap under the OB1 sash.",
        "Dining: 160×90 table for 6 between kitchen and living, pendant on its centre; 1.0+ m to the counters on two sides.",
        "Living: 240 sofa as the room divider facing the brick strip on the east wall; 65\" TV at ~2.5 m. Armchair reading corner by OB3;",
        "      the 0.6 m alcove along the new bathroom wall takes a low sideboard or bookcase (or a desk). No through-traffic past the TV.",
        "Verify on site: radiator positions under OB1/OB3, balcony door hinge side, cooking fuel (gas vs induction), socket positions.",
    ]
    y = height - FOOTER + 26
    for line in notes:
        draw.text((SIDE, y), line, font=font(15), fill=COLORS["text"])
        y += 28


def main():
    model = load_model(MODEL)
    validate(model)
    width = SIDE * 2 + int((VIEW[2] - VIEW[0]) * SCALE)
    height = HEADER + int((VIEW[3] - VIEW[1]) * SCALE) + FOOTER
    image = Image.new("RGB", (width, height), COLORS["paper"])
    draw = ImageDraw.Draw(image)
    draw_plan(draw, model)
    draw_zones(draw)
    draw_furniture(draw)
    draw_clearances(draw)
    # Mask anything drawn outside the plan crop.
    draw.rectangle((0, 0, width, HEADER - 1), fill=COLORS["paper"])
    draw.rectangle((0, height - FOOTER, width, height), fill=COLORS["paper"])
    draw_frame(draw, width, height)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, optimize=True)
    print(f"Generated living layout study: {OUT}")


if __name__ == "__main__":
    main()
