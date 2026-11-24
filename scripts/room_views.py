"""Per-room contractor sheets: plan crop, scale and render cameras.

Shared by render_room_views.py (Blender) and make_room_sheets.py, so a
sheet's render and its plan always show the same area.
"""

import math

MARGIN = 0.75
# Walls, doors and windows are cut at this height in the bird's-eye views
# so the furnished room is visible from above.
CUT_HEIGHT = 1.25

SHEETS = [
    {"slug": "00_flat", "title": "Загальний план з меблями",
     "crop": (-0.45, -0.45, 9.88, 13.74), "scale": 50, "azimuth": 235, "elevation": 55},
    {"slug": "01_kitchen", "title": "Кухня та вхід", "rooms": [123], "zones": ["kitchen", "hall"],
     "crop": (0.70, 8.00, 4.55, 13.50), "scale": 25, "azimuth": 10, "elevation": 45},
    {"slug": "02_living", "title": "Вітальня та їдальня", "rooms": [123], "zones": ["living"],
     "crop": (0.70, 7.10, 9.65, 13.50), "scale": 50, "azimuth": 250, "elevation": 48},
    {"slug": "03_bathroom_1", "title": "Ванна кімната 1", "rooms": [4], "scale": 20,
     "azimuth": 60, "elevation": 55},
    {"slug": "04_bathroom_2", "title": "Ванна кімната 2", "rooms": [9], "scale": 20,
     "azimuth": 95, "elevation": 68},
    {"slug": "05_bedroom_1", "title": "Спальня 1", "rooms": [5], "scale": 25,
     "azimuth": 60, "elevation": 55},
    {"slug": "06_bedroom_2", "title": "Спальня 2", "rooms": [6], "scale": 25,
     "azimuth": 60, "elevation": 55},
    {"slug": "07_bedroom_3", "title": "Спальня 3", "rooms": [7], "scale": 25,
     "azimuth": 140, "elevation": 55},
    {"slug": "08_storage", "title": "Комора", "rooms": [8], "scale": 25,
     "azimuth": 220, "elevation": 60},
]


def room_bbox(model, room_id):
    room = next(r for r in model["rooms"] if r["id"] == room_id)
    xs = [p[0] for p in room["polygon"]]
    ys = [p[1] for p in room["polygon"]]
    return min(xs), min(ys), max(xs), max(ys)


def sheet_crop(model, sheet):
    if sheet.get("crop"):
        return tuple(sheet["crop"])
    boxes = [room_bbox(model, r) for r in sheet["rooms"]]
    return (min(b[0] for b in boxes) - MARGIN, min(b[1] for b in boxes) - MARGIN,
            max(b[2] for b in boxes) + MARGIN, max(b[3] for b in boxes) + MARGIN)


def sheet_items(model, sheet):
    """Furniture shown and scheduled on a sheet."""
    items = model.get("furniture", [])
    if not sheet.get("rooms"):
        return list(items)
    zones = sheet.get("zones")
    return [i for i in items if i["room"] in sheet["rooms"]
            and (zones is None or i.get("zone") in zones)]


def bird_camera(crop, azimuth, elevation):
    """Camera location and target for an oblique view of the crop."""
    x0, y0, x1, y1 = crop
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    radius = 0.5 * math.hypot(x1 - x0, y1 - y0)
    distance = radius / math.tan(math.radians(25)) * 0.85
    a, e = math.radians(azimuth), math.radians(elevation)
    location = (cx + distance * math.cos(e) * math.cos(a),
                cy + distance * math.cos(e) * math.sin(a),
                0.45 + distance * math.sin(e))
    return location, (cx, cy, 0.45)


def item_rect(item):
    x, y = item["at"]
    w, d = item["size"][:2]
    return x, y, x + w, y + d


def item_back(item, model):
    """Wall side of a rectangular item: explicit, else the touching room edge.

    Where several edges touch (a corner), the longer item edge is the back.
    Chairs turn their backs on the nearest table.
    """
    if item.get("back"):
        return item["back"]
    x0, y0, x1, y1 = item_rect(item)
    if item["kind"] == "chair":
        tables = [t for t in model.get("furniture", []) if t["kind"] == "table"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        tx0, ty0, tx1, ty1 = item_rect(min(tables, key=lambda t: math.dist(
            (cx, cy), ((item_rect(t)[0] + item_rect(t)[2]) / 2, (item_rect(t)[1] + item_rect(t)[3]) / 2))))
        dx, dy = cx - (tx0 + tx1) / 2, cy - (ty0 + ty1) / 2
        if abs(dx) > abs(dy):
            return "E" if dx > 0 else "W"
        return "N" if dy > 0 else "S"
    rx0, ry0, rx1, ry1 = room_bbox(model, item["room"])
    gaps = {"W": x0 - rx0, "E": rx1 - x1, "S": y0 - ry0, "N": ry1 - y1}
    length = {"W": y1 - y0, "E": y1 - y0, "S": x1 - x0, "N": x1 - x0}
    touching = [s for s, g in gaps.items() if g <= 0.02]
    if touching:
        return max(touching, key=lambda s: length[s])
    return min(gaps, key=gaps.get)


def local_box(item, back, u0, u1, v0, v1):
    """Plan rectangle in item coordinates: u along the back, v from back to front."""
    x0, y0, x1, y1 = item_rect(item)
    if back == "S":
        return x0 + u0, y0 + v0, x0 + u1, y0 + v1
    if back == "N":
        return x0 + u0, y1 - v1, x0 + u1, y1 - v0
    if back == "W":
        return x0 + v0, y0 + u0, x0 + v1, y0 + u1
    return x1 - v1, y0 + u0, x1 - v0, y0 + u1


def l_shape(item, model):
    """L-shaped item (corner sofa): ((u0, u1) of the chaise, seat depth) or None.

    `size` is the bounding box; `l_shape: {seat, end, width}` puts a chaise of
    `width` (default: seat depth) at the `start` or `end` of the back."""
    spec = item.get("l_shape")
    if not spec:
        return None
    L, _ = along_depth(item, item_back(item, model))
    seat = spec["seat"]
    width = spec.get("width", seat)
    return ((0.0, width) if spec.get("end", "start") == "start" else (L - width, L)), seat


def item_boxes(item, model):
    """Plan rectangles occupied by a rectangular or L-shaped item."""
    shape = l_shape(item, model)
    if not shape:
        return [item_rect(item)]
    back = item_back(item, model)
    L, D = along_depth(item, back)
    (u0, u1), seat = shape
    return [local_box(item, back, 0.0, L, 0.0, seat), local_box(item, back, u0, u1, seat, D)]


def item_outline(item, model):
    """Plan outline polygon of an L-shaped item (None for rectangles)."""
    shape = l_shape(item, model)
    if not shape:
        return None
    back = item_back(item, model)
    L, D = along_depth(item, back)
    (u0, u1), seat = shape
    pts = [(0, 0), (L, 0), (L, seat), (u1, seat), (u1, D), (u0, D), (u0, seat), (0, seat)]
    out = []
    for u, v in pts:
        x, y = local_box(item, back, u, u, v, v)[:2]
        if not out or (abs(out[-1][0] - x) > 1e-9 or abs(out[-1][1] - y) > 1e-9):
            out.append((x, y))
    return out


def along_depth(item, back):
    """(length along the back, depth from back to front)."""
    w, d = item["size"][:2]
    return (w, d) if back in ("N", "S") else (d, w)
