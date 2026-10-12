#!/usr/bin/env python3
"""Plan and ergonomics check of the designed furniture in the target model.

Room geometry and every furniture item come from data/target.yaml. The script
fails if a floor-standing piece leaves its room or collides with another, or
if a working clearance, the kitchen work triangle or the TV viewing distance
falls outside its ergonomic range; otherwise it draws the checked plan.
"""
from pathlib import Path
import math
import sys

from PIL import Image, ImageDraw

from fonts import load_font
from model_loader import load_model
from plan_symbols import door_swing_arc

MODEL = Path("data/target.yaml")
OUT = Path("exports/concepts/living_layout/recommended.png")

SCALE = 100                       # px per metre
VIEW = (-0.15, -0.15, 9.60, 13.45)  # model-space crop: x0, y0, x1, y1
HEADER = 96
FOOTER = 360
SIDE = 30

# Minimum gaps between named items: (label, from id, to id, axis, minimum m,
# and optionally the coordinate on the other axis to measure along, for
# shapes such as the corner sofa whose bounding box would mislead).
CLEARANCES = [
    ("kitchen aisle", "K_BASE_W1", "K_ISLAND", "x", 1.00),
    ("sink aisle", "K_ISLAND", "K_SINK_CABINET", "y", 1.00),
    ("hall", "H_SHOE_BENCH", "D_CHAIR_2", "y", 0.90),
    ("balcony route", "D_TABLE", "L_SOFA", "x", 0.80, 10.65),
    ("pantry front", "K_PANTRY", "D_CHAIR_3", "y", 0.90),
    ("sideboard", "D_SIDEBOARD", "L_SOFA", "y", 0.65, 7.50),
    ("desk chair", "L_SOFA", "W_DESK", "y", 0.75),
    ("legroom", "L_SOFA", "L_COFFEE_TABLE", "x", 0.35, 10.40),
    ("chaise", "L_SOFA", "L_COFFEE_TABLE", "y", 0.35, 7.90),
    ("TV front", "L_COFFEE_TABLE", "L_TV_CONSOLE", "x", 0.45),
    ("entry", "H_SHOE_CABINET", "K_OVEN_TOWER", "y", 0.90),
    ("closet", "S_CLOSET_SHOES", "S_CLOSET_SHELVES", "y", 0.90),
    ("wardrobe aisle", "B5_BED", "B5_WARDROBE", "y", 0.70),
    ("desk chair", "B5_CHAIR", "B5_DRESSER", "x", 0.75),
    ("desk chair", "B6_BED", "B6_CHAIR", "x", 0.50),
    ("bed access", "B7_DRESSER", "B7_BED", "x", 0.90),
    ("bed foot", "B7_WARDROBE", "B7_BED", "y", 0.75),
]
WORK_TRIANGLE = ("K_FRIDGE", "K_HOB", "K_SINK")
TRIANGLE_LEG = (1.20, 2.70)      # NKBA: 4-9 ft per leg
TRIANGLE_SUM = 7.90              # NKBA: at most 26 ft in total
TV_DIAGONAL = 70 * 0.0254
TV_DISTANCE = (1.2, 1.6)         # x diagonal, for 4K at 30-40 degrees
SEATED_EYE = 0.35                # eye position in front of the sofa back

COLORS = {
    "paper": "#fffdf8",
    "wall": "#2d333b",
    "room": "#f3ece0",
    "other_room": "#dfe3e6",
    "shaft": "#7d6b8a",
    "window": "#bfe0f2",
    "door": "#a5753d",
    "brick": "#b5562f",
    "kitchen": "#d9c7a7",
    "dining": "#c7d9b8",
    "living": "#b9cddd",
    "work": "#e3d3a8",
    "hall": "#d3c4e3",
    "bedroom_parents": "#e8c9b5",
    "bedroom_boy": "#bfd8c9",
    "bedroom_granny": "#e6d9b0",
    "appliance": "#4a4f57",
    "rug": "#ece4f0",
    "clearance": "#c0392b",
    "triangle": "#1f7a4d",
    "text": "#222831",
    "muted": "#616b76",
}
ON_TOP = {"hob", "sink"}                       # drawn over the cabinet below
WALL_MOUNTED = {"hood", "shelf", "rail", "mirror", "tv", "pendant", "wall_cabinet"}
SHORT = {
    "K_OVEN_TOWER": "oven\ntower", "K_FRIDGE": "fridge", "K_BASE_W1": "drawers",
    "K_HOB_CABINET": "", "K_CORNER": "prep", "K_BASE_N1": "", "K_SINK_CABINET": "",
    "K_DISHWASHER": "DW", "K_ISLAND": "island\n120×60", "D_TABLE": "table 180×90",
    "D_BENCH": "bench", "K_PANTRY": "pantry 120×60", "D_SIDEBOARD": "sideboard",
    "L_SOFA": "corner sofa", "L_COFFEE_TABLE": "coffee\ntable", "L_TV_CONSOLE": "TV\n70\"",
    "W_DESK": "desk 120×60", "W_CHAIR": "", "H_SHOE_BENCH": "shoe bench",
    "H_SHOE_CABINET": "shoes", "S_CLOSET_HANGING": "hang-\ning", "S_CLOSET_SHELVES": "shelves",
    "S_CLOSET_SHOES": "", "K_HOB": "hob", "K_SINK": "sink", "B5_DESK": "desk", "B5_CHAIR": "",
    "B5_BED": "bed 180×200", "B5_WARDROBE": "wardrobe 200", "B5_DRESSER": "chest",
    "B6_BED": "bed\n90", "B6_DESK": "desk\n120", "B6_WARDROBE": "ward-\nrobe", "B6_BOOKCASE": "",
    "B6_LOW_SHELF": "toys", "B7_BED": "bed\n120", "B7_WARDROBE": "ward-\nrobe", "B7_DRESSER": "chest",
    "B7_ARMCHAIR": "armchair",
}


def font(size, bold=False):
    return load_font(size, bold)


def px(x, y):
    return (SIDE + (x - VIEW[0]) * SCALE, HEADER + (VIEW[3] - y) * SCALE)


def poly(draw, points, fill, outline=None, width=1):
    draw.polygon([px(*p) for p in points], fill=fill, outline=outline, width=width)


def rect_points(x, y, w, d):
    return [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]


def to_world(item, u, v):
    """Map a front-relative point (u along the front, v from front to back)."""
    x, y, _ = item["at"]
    w, d, _ = item["size"]
    return {"S": (x + u, y + v), "N": (x + u, y + d - v),
            "E": (x + w - v, y + u), "W": (x + v, y + u)}[item.get("facing", "S")]


def footprint(item):
    if item["category"] == "corner_sofa":
        w, d, _ = item["size"]
        along, depth = (d, w) if item.get("facing", "S") in ("E", "W") else (w, d)
        front = depth - item["main_depth"]
        cw = item["chaise"]["width"]
        if item["chaise"]["side"] == "start":
            uv = [(0, 0), (cw, 0), (cw, front), (along, front), (along, depth), (0, depth)]
        else:
            uv = [(along - cw, 0), (along, 0), (along, depth), (0, depth), (0, front), (along - cw, front)]
        return [to_world(item, u, v) for u, v in uv]
    if "polygon" in item:
        return [tuple(p) for p in item["polygon"]]
    x, y, _ = item["at"]
    w, d, _ = item["size"]
    return rect_points(x, y, w, d)


def bounds(item):
    pts = footprint(item)
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def front_centre(item):
    x0, y0, x1, y1 = bounds(item)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return {"S": (cx, y0), "N": (cx, y1), "E": (x1, cy), "W": (x0, cy)}[item.get("facing", "S")]


def inside(point, polygon):
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def samples(item, n=9, inset=0.01):
    """Grid points just inside the item's footprint."""
    pts = footprint(item)
    x0, y0, x1, y1 = bounds(item)
    grid = [(x0 + inset + (x1 - x0 - 2 * inset) * i / (n - 1),
             y0 + inset + (y1 - y0 - 2 * inset) * j / (n - 1))
            for i in range(n) for j in range(n)]
    return [p for p in grid if inside(p, pts)]


def floor_standing(item):
    return (item["at"][2] < 0.05 and item["category"] not in ON_TOP | WALL_MOUNTED
            and item["category"] != "rug")


def door_sweep(door):
    """The swept quarter disc as a polygon: hinge, then the arc."""
    arc = door_swing_arc(door["at"], door["size"], door.get("swing"),
                         leaf_width=door.get("nominal_width"))
    open_tip, shut_tip = arc[0], arc[-1]
    # The hinge is the corner of the square spanned by the two leaf tips.
    mid = arc[len(arc) // 2]
    candidates = [(open_tip[0], shut_tip[1]), (shut_tip[0], open_tip[1])]
    hinge = max(candidates, key=lambda c: math.dist(c, mid))
    return [hinge] + arc


def line_extent(item, axis, at, pick):
    """min or max coordinate of the item's footprint along one line."""
    x0, y0, x1, y1 = bounds(item)
    lo, hi = (x0, x1) if axis == "x" else (y0, y1)
    steps = [lo + (hi - lo) * k / 400 for k in range(401)]
    hits = [t for t in steps if inside((t, at) if axis == "x" else (at, t), footprint(item))]
    if not hits:
        raise ValueError(f"clearance line at {at} misses {item['id']}")
    return pick(hits)


def clearance_span(a, b, axis, at=None):
    """Start and end of the clear gap from a to b along an axis.

    Without `at` the bounding boxes are used; with it, the gap is measured
    along the line at that coordinate of the other axis.
    """
    i = 0 if axis == "x" else 1
    if at is None:
        return bounds(a)[i + 2], bounds(b)[i]
    return line_extent(a, axis, at, max), line_extent(b, axis, at, min)


def balcony_sweeps(model):
    """Swing zone of OB2's inward-opening leaf (both sides if not recorded)."""
    ob2 = next(w for w in model["windows"] if w["id"] == "OB2")
    x, y = ob2["at"]
    w, _ = ob2["size"]
    leaf = ob2["opening_leaf_width"]
    starts = {"west": [x], "east": [x + w - leaf]}.get(ob2.get("opening_leaf_side"),
                                                        [x, x + w - leaf])
    return [rect_points(x0, y - leaf, leaf, leaf) for x0 in starts]


def obstacles(model):
    """Fixed structure inside rooms that furniture must not cut into."""
    return ([(c["id"], rect_points(*c["at"], *c["size"])) for c in model.get("columns", [])]
            + [(sh["id"], rect_points(*sh["at"], *sh["size"])) for sh in model.get("shafts", [])])


def gap(a, b, axis, at=None):
    start, end = clearance_span(a, b, axis, at)
    return end - start


def validate(model):
    rooms = {r["id"]: r for r in model["rooms"]}
    items = {f["id"]: f for f in model["furniture"]}
    errors = []

    for item in items.values():
        room = rooms[item.get("room", 123)]
        blocked = [rooms[i].get("footprint", rooms[i]["polygon"]) for i in room.get("subtract", [])]
        if not all(inside(p, room["polygon"]) and not any(inside(p, b) for b in blocked)
                   for p in samples(item)):
            errors.append(f"{item['id']} leaves room {room['id']}")

    solid = [f for f in items.values() if floor_standing(f)]
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if (any(inside(p, footprint(b)) for p in samples(a))
                    or any(inside(p, footprint(a)) for p in samples(b))):
                errors.append(f"{a['id']} overlaps {b['id']}")

    for name, shape in obstacles(model):
        for f in solid:
            if any(inside(p, shape) for p in samples(f)):
                errors.append(f"{f['id']} cuts into {name}")
    for sweep in balcony_sweeps(model):
        for f in solid:
            if any(inside(p, sweep) for p in samples(f)):
                errors.append(f"{f['id']} blocks the OB2 balcony leaf")

    for door in model["doors"]:
        if not door.get("has_leaf", door["id"] == "entry"):
            continue
        sweep = door_sweep(door)
        for f in solid:
            if any(inside(p, sweep) for p in samples(f)):
                errors.append(f"{f['id']} blocks the swing of door {door['id']}")

    report = []
    for label, a, b, axis, minimum, *at in CLEARANCES:
        try:
            value = gap(items[a], items[b], axis, *at)
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
            continue
        report.append(f"{label:<14} {value:.2f} m  (min {minimum:.2f})")
        if value + 1e-6 < minimum:
            errors.append(f"{label} is {value:.2f} m, below {minimum:.2f} m")

    corners = [front_centre(items[i]) for i in WORK_TRIANGLE]
    legs = [math.dist(corners[i], corners[(i + 1) % 3]) for i in range(3)]
    report.append("work triangle  " + " + ".join(f"{leg:.2f}" for leg in legs)
                  + f" = {sum(legs):.2f} m  (legs {TRIANGLE_LEG[0]}-{TRIANGLE_LEG[1]}, sum <= {TRIANGLE_SUM})")
    if not all(TRIANGLE_LEG[0] <= leg <= TRIANGLE_LEG[1] for leg in legs) or sum(legs) > TRIANGLE_SUM:
        errors.append("kitchen work triangle outside NKBA ranges")

    eye = bounds(items["L_SOFA"])[0] + SEATED_EYE
    distance = bounds(items["L_TV"])[0] - eye
    low, high = (k * TV_DIAGONAL for k in TV_DISTANCE)
    report.append(f"TV distance    {distance:.2f} m  (70\": {low:.2f}-{high:.2f})")
    if not low <= distance <= high:
        errors.append(f"TV viewing distance {distance:.2f} m outside {low:.2f}-{high:.2f}")

    if errors:
        sys.exit("furniture layout invalid:\n  " + "\n  ".join(errors))
    for line in report:
        print("  " + line)
    return corners, items


def draw_text_block(draw, x, y, text, size, fill):
    draw.multiline_text((x, y), text, font=font(size), fill=fill, anchor="mm",
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
            poly(draw, room["polygon"],
                 COLORS["other_room"] if room["function"] == "bathroom" else COLORS["room"])
    for text, x, y in (("Bathroom 1", 1.36, 6.6), ("to bedrooms", 2.87, 6.3),
                       ("walk-in\ncloset", 4.20, 6.95), ("Bathroom 2", 7.6, 6.75),
                       ("PARENTS", 1.88, 0.62), ("BOY", 4.86, 4.55), ("GRANNY", 7.25, 2.55)):
        draw_text_block(draw, *px(x, y), text, 13, COLORS["muted"])

    for shaft in model["shafts"]:
        x, y = shaft["at"]
        w, d = shaft["size"]
        poly(draw, rect_points(x, y, w, d), COLORS["shaft"])
    for win in model["windows"]:
        if True:
            x, y = win["at"]
            w, d = win["size"]
            poly(draw, rect_points(x, y, w, d), COLORS["window"], COLORS["wall"])
            draw_text_block(draw, *px(x + w / 2, y + d / 2), win["id"], 13, COLORS["text"])
    for fin in model["wall_finishes"]:
        (x1, y1), (x2, y2) = fin["segment"]
        draw.line([px(x1, y1), px(x2, y2)], fill=COLORS["brick"], width=7)

    for door in model["doors"]:
        x, y = door["at"]
        w, d = door["size"]
        poly(draw, rect_points(x, y, w, d), COLORS["room"])
    for door in model["doors"]:
        if door.get("has_leaf", door["id"] == "entry"):
            hinge, *arc = door_sweep(door)
            draw.line([px(*p) for p in arc], fill=COLORS["door"], width=2)
            draw.line([px(*hinge), px(*arc[0])], fill=COLORS["door"], width=4)
    entry = next(d for d in model["doors"] if d["id"] == "entry")
    draw_text_block(draw, *px(2.75, entry["at"][1] + 0.40), "ENTRY", 13, COLORS["text"])
    for sweep in balcony_sweeps(model):
        poly(draw, sweep, None, COLORS["door"])


def draw_furniture(draw, items):
    order = sorted(items.values(), key=lambda f: (f["category"] != "rug",
                                                  f["category"] in ON_TOP | WALL_MOUNTED))
    for item in order:
        category = item["category"]
        pts = footprint(item)
        if category == "rug":
            poly(draw, pts, COLORS["rug"])
            continue
        if category in WALL_MOUNTED:
            if category == "tv":
                poly(draw, pts, COLORS["appliance"])
            elif category == "pendant":
                x0, y0, x1, y1 = bounds(item)
                a, b = px(x0, y1), px(x1, y0)
                draw.ellipse((a[0], a[1], b[0], b[1]), outline=COLORS["appliance"], width=2)
            else:
                draw.line([px(*p) for p in pts + pts[:1]], fill=COLORS["muted"], width=1)
            continue
        fill = COLORS["appliance"] if category in ON_TOP else COLORS[item.get("zone", "living")]
        poly(draw, pts, fill, COLORS["wall"], 2)
        label = SHORT.get(item["id"])
        if label:
            x0, y0, x1, y1 = bounds(item)
            colour = "#ffffff" if category in ON_TOP else COLORS["text"]
            draw_text_block(draw, *px((x0 + x1) / 2, (y0 + y1) / 2), label, 12, colour)


def draw_checks(draw, items, corners):
    tri = [px(*p) for p in corners]
    draw.line(tri + tri[:1], fill=COLORS["triangle"], width=2)
    for p in tri:
        draw.ellipse((p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4), fill=COLORS["triangle"])
    for _label, a, b, axis, _minimum, *at in CLEARANCES:
        ab, bb = bounds(items[a]), bounds(items[b])
        start, end = clearance_span(items[a], items[b], axis, *at)
        if axis == "x":
            mid = at[0] if at else (max(ab[1], bb[1]) + min(ab[3], bb[3])) / 2
            p1, p2 = px(start, mid), px(end, mid)
        else:
            mid = at[0] if at else (max(ab[0], bb[0]) + min(ab[2], bb[2])) / 2
            p1, p2 = px(mid, start), px(mid, end)
        draw.line([p1, p2], fill=COLORS["clearance"], width=2)
        for p in (p1, p2):
            draw.ellipse((p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3), fill=COLORS["clearance"])
        offset = (0, -10) if axis == "x" else (22, 0)
        draw.text(((p1[0] + p2[0]) / 2 + offset[0], (p1[1] + p2[1]) / 2 + offset[1]),
                  f"{end - start:.2f}", font=font(13, True),
                  fill=COLORS["clearance"], anchor="mm")


def draw_frame(draw, width, height):
    draw.text((SIDE, 22), "Furniture design — open space and bedrooms",
              font=font(24, True), fill=COLORS["text"])
    draw.text((SIDE, 58), "Target model furniture (data/target.yaml) · red = clearances (m) · "
              "green = kitchen work triangle", font=font(15), fill=COLORS["muted"])
    nx, ny = width - 60, HEADER + 40
    draw.polygon([(nx, ny - 26), (nx - 11, ny + 8), (nx + 11, ny + 8)], fill=COLORS["text"])
    draw.text((nx, ny + 22), "N", font=font(16, True), fill=COLORS["text"], anchor="mm")
    notes = [
        "Kitchen: oven tower and fridge to the ceiling, landing drawers with an upper above, hob and hood on the brick, prep corner",
        "      with uppers along the chamfer, sink under OB1 (low tap), 45 DW; 120×60 island with 1.05 m aisles; 120×60 pantry in the recess.",
        "Dining: 180×90 table for six on the island: backless bench with drawers on the north (slides under, balcony route stays clear),",
        "      three chairs on the south; linear pendant over the table; crockery sideboard under the AC.",
        "Living: corner sofa facing the 70\" TV on the brick strip (~2.2 m), chaise along the south; floor lamp; no armchair.",
        "Desk: 120×60 on the pier east of OB3, facing the wall with daylight from the left.",
        "Entrance: door opens outward; slim shoe cabinet inside it, bench, coat rail and mirror; storage becomes a walk-in closet.",
        "Parents: 180 bed, desk by OK5 with daylight from the left, 200 sliding wardrobe, chest.   Boy: 90 bed, desk side-on to OK6.",
        "Granny: 120 raised bed from the door, nightstand outside the door swing, armchair and lamp by OK7, chest, 160 wardrobe.",
    ]
    y = height - FOOTER + 24
    for line in notes:
        draw.text((SIDE, y), line, font=font(15), fill=COLORS["text"])
        y += 28


def main():
    model = load_model(MODEL)
    corners, items = validate(model)
    width = SIDE * 2 + int((VIEW[2] - VIEW[0]) * SCALE)
    height = HEADER + int((VIEW[3] - VIEW[1]) * SCALE) + FOOTER
    image = Image.new("RGB", (width, height), COLORS["paper"])
    draw = ImageDraw.Draw(image)
    draw_plan(draw, model)
    draw_furniture(draw, items)
    draw_checks(draw, items, corners)
    draw.rectangle((0, 0, width, HEADER - 1), fill=COLORS["paper"])
    draw.rectangle((0, height - FOOTER, width, height), fill=COLORS["paper"])
    draw_frame(draw, width, height)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, optimize=True)
    print(f"Generated furniture plan: {OUT}")


if __name__ == "__main__":
    main()
