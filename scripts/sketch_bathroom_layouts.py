#!/usr/bin/env python3
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT = Path("exports/concepts/bathroom_layouts")
SCALE = 245
ROOM_TOP = 300
OLD_LEFT = 170
NEW_LEFT = 1020

COLORS = {
    "background": "#f5f2eb",
    "paper": "#fffdf8",
    "wall": "#30343b",
    "room": "#e8edf0",
    "door": "#a57a45",
    "stack": "#b75d47",
    "water": "#3d7fc4",
    "drain": "#b44848",
    "service_box": "#ead8b6",
    "clear_min": "#f4c66a",
    "clear_comfort": "#a7d7a0",
    "bath": "#8ec5dc",
    "shower": "#78b8d1",
    "basin": "#b7dce8",
    "wc": "#d5e8ee",
    "laundry": "#c4c8ce",
    "text": "#222831",
    "muted": "#5f6872",
    "warning": "#b43d32",
}

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def box(draw, xy, fill, outline=COLORS["wall"], width=3, radius=8):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def local_box(left, bottom, x, y, w, d):
    return (
        left + x * SCALE,
        bottom - (y + d) * SCALE,
        left + (x + w) * SCALE,
        bottom - y * SCALE,
    )


def label_center(draw, xy, text, size=22, fill=COLORS["text"]):
    f = font(size, True)
    bounds = draw.textbbox((0, 0), text, font=f)
    x = (xy[0] + xy[2] - (bounds[2] - bounds[0])) / 2
    y = (xy[1] + xy[3] - (bounds[3] - bounds[1])) / 2
    draw.text((x, y), text, font=f, fill=fill)


def fixture(draw, left, bottom, item):
    x, y, w, d = item["rect"]
    xy = local_box(left, bottom, x, y, w, d)
    box(draw, xy, COLORS[item["kind"]], width=2)
    label_center(draw, xy, item["label"], 18)

    clearance = item.get("clearance")
    if clearance:
        cx, cy, cw, cd, quality = clearance
        cxy = local_box(left, bottom, cx, cy, cw, cd)
        color = COLORS["clear_comfort"] if quality == "comfort" else COLORS["clear_min"]
        draw.rectangle(cxy, outline=color, width=4)


def dashed_line(draw, points, fill, width=3, dash=12, gap=8):
    for start, end in zip(points, points[1:]):
        x1, y1 = start
        x2, y2 = end
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** .5
        if not length:
            continue
        dx = (x2 - x1) / length
        dy = (y2 - y1) / length
        distance = 0
        while distance < length:
            segment_end = min(distance + dash, length)
            draw.line(
                (
                    x1 + dx * distance,
                    y1 + dy * distance,
                    x1 + dx * segment_end,
                    y1 + dy * segment_end,
                ),
                fill=fill,
                width=width,
            )
            distance += dash + gap


def draw_service_box(draw, left, bottom, room_width, room_depth, sides):
    depth = .08
    for side in sides:
        if side == "west":
            rect = local_box(left, bottom, 0, 0, depth, room_depth)
        elif side == "east":
            rect = local_box(left, bottom, room_width - depth, 0, depth, room_depth)
        elif side == "south":
            rect = local_box(left, bottom, 0, 0, room_width, depth)
        else:
            rect = local_box(left, bottom, 0, room_depth - depth, room_width, depth)
        draw.rectangle(rect, fill=COLORS["service_box"], outline=COLORS["door"], width=1)


def draw_new_service_routes(draw, left, bottom, fixtures, stack):
    stack_px = (left + stack[0] * SCALE, bottom - stack[1] * SCALE)
    trunk_y = bottom - 1.29 * SCALE
    trunk_start = left + .10 * SCALE
    draw.line((trunk_start, trunk_y, stack_px[0], trunk_y),
              fill=COLORS["drain"], width=5)
    draw.line((stack_px[0], trunk_y, stack_px[0], stack_px[1]),
              fill=COLORS["drain"], width=5)
    initials = {"shower": "P", "basin": "L", "wc": "WC", "laundry": "W/D", "bath": "B"}
    markers = []
    for entry in fixtures:
        x, y, w, d = entry["rect"]
        start = (left + (x + w / 2) * SCALE, bottom - (y + d / 2) * SCALE)
        dashed_line(draw, [start, (start[0], trunk_y)], COLORS["drain"], width=3)
        markers.append(((start[0], trunk_y), initials.get(entry["kind"], "?")))
    return markers


def connection_point(draw, point, label):
    px, py = point
    draw.ellipse((px - 11, py - 11, px + 11, py + 11),
                 fill=COLORS["paper"], outline=COLORS["drain"], width=3)
    draw.text((px, py), label, font=font(11, True), fill=COLORS["warning"], anchor="mm")


def draw_box_detail(draw, x, y):
    """Cross-section of the surface service box used instead of floor routing."""
    draw.text((x, y), "SERVICE BOX - TYPICAL SECTION (no pipes in the floor)",
              font=font(24, True), fill=COLORS["text"])
    top = y + 45
    wall_x = x + 20
    draw.rectangle((wall_x, top, wall_x + 55, top + 300),
                   fill="#d9d3c6", outline=COLORS["wall"], width=3)
    for offset in range(0, 300, 22):
        draw.line((wall_x, top + offset, wall_x + 55, top + offset + 18),
                  fill=COLORS["muted"], width=1)
    box_left = wall_x + 55
    draw.rectangle((box_left, top + 40, box_left + 210, top + 300),
                   fill=COLORS["service_box"], outline=COLORS["door"], width=3)
    draw.ellipse((box_left + 30, top + 175, box_left + 180, top + 285),
                 fill=COLORS["paper"], outline=COLORS["drain"], width=4)
    draw.text((box_left + 105, top + 230), "DN110/50", font=font(15, True),
              fill=COLORS["warning"], anchor="mm")
    for index, (cx, temp) in enumerate(((box_left + 60, "ZW"), (box_left + 150, "CW"))):
        draw.ellipse((cx - 22, top + 80, cx + 22, top + 124),
                     fill=COLORS["paper"], outline=COLORS["water"], width=4)
        draw.text((cx, top + 102), temp, font=font(14, True),
                  fill=COLORS["water"], anchor="mm")
    draw.line((box_left, top + 300, box_left + 210, top + 300),
              fill=COLORS["wall"], width=5)
    draw.text((box_left + 240, top + 40),
              "Tiled plasterboard / brick casing on the wall face.",
              font=font(19), fill=COLORS["muted"])
    draw.text((box_left + 240, top + 70),
              "Waste DN110 (WC) or DN50 (basin, shower, W/D) at the bottom,",
              font=font(19), fill=COLORS["muted"])
    draw.text((box_left + 240, top + 100),
              "kept in continuous gravity fall towards SH_san.",
              font=font(19), fill=COLORS["muted"])
    draw.text((box_left + 240, top + 140),
              "Cold (ZW) and hot (CW) water run above the waste,",
              font=font(19), fill=COLORS["muted"])
    draw.text((box_left + 240, top + 170),
              "insulated, with an access/inspection panel at each branch.",
              font=font(19), fill=COLORS["muted"])
    draw.text((box_left + 240, top + 215),
              "Indicative box envelope: approx. 250 mm deep x 350 mm high;",
              font=font(19), fill=COLORS["warning"])
    draw.text((box_left + 240, top + 245),
              "confirm after pipe sizing, falls and product selection.",
              font=font(19), fill=COLORS["warning"])


def draw_old_service_connections(draw, left, bottom, fixtures):
    terminals = {
        "bath": ((.06, .50), "B"),
        "basin": ((.06, 1.495), "L"),
        "wc": ((.60, 2.93), "WC"),
        "laundry": ((.06, 1.495), None),
    }
    for entry in fixtures:
        if entry["kind"] not in terminals:
            continue
        (tx, ty), _label = terminals[entry["kind"]]
        x, y, w, d = entry["rect"]
        start = (left + (x + w / 2) * SCALE, bottom - (y + d / 2) * SCALE)
        terminal = (left + tx * SCALE, bottom - ty * SCALE)
        distances = {
            "west": x + w / 2,
            "east": 1.92 - (x + w / 2),
            "south": y + d / 2,
            "north": 2.99 - (y + d / 2),
        }
        side = min(distances, key=distances.get)
        if side == "west":
            edge = (left + .04 * SCALE, start[1])
            path = [start, edge, (edge[0], terminal[1]), terminal]
        elif side == "east":
            edge = (left + 1.88 * SCALE, start[1])
            corner = (edge[0], bottom - 2.95 * SCALE)
            path = [start, edge, corner, (terminal[0], corner[1]), terminal]
        elif side == "south":
            edge = (start[0], bottom - .04 * SCALE)
            corner = (left + .04 * SCALE, edge[1])
            path = [start, edge, corner, (corner[0], terminal[1]), terminal]
        else:
            edge = (start[0], bottom - 2.95 * SCALE)
            path = [start, edge, (terminal[0], edge[1]), terminal]
        dashed_line(draw, path, COLORS["drain"], width=3)
        if entry["kind"] != "wc":
            draw.line(path, fill=COLORS["water"], width=2)
    markers = []
    for (tx, ty), label in terminals.values():
        if not label:
            continue
        markers.append(((left + tx * SCALE, bottom - ty * SCALE), label))
    return markers


def draw_door(draw, room, left, bottom):
    if room == "old":
        y0 = bottom - 1.945 * SCALE
        y1 = bottom - 1.045 * SCALE
        draw.line((left + 1.92 * SCALE, y0, left + 1.92 * SCALE, y1),
                  fill=COLORS["paper"], width=10)
        draw.line((left + 1.92 * SCALE, y0, left + 1.02 * SCALE, y0),
                  fill=COLORS["door"], width=5)
        draw.arc((left + 1.02 * SCALE, y0, left + 1.92 * SCALE, y0 + .90 * SCALE),
                 270, 360, fill=COLORS["door"], width=3)
    else:
        x0 = left + .10 * SCALE
        x1 = left + .90 * SCALE
        draw.line((x0, bottom, x1, bottom), fill=COLORS["paper"], width=10)
        draw.line((x0, bottom, x0, bottom + .80 * SCALE), fill=COLORS["door"], width=5)
        draw.arc((x0, bottom, x1, bottom + .80 * SCALE), 0, 90,
                 fill=COLORS["door"], width=3)


def draw_old_room(draw, fixtures):
    left = OLD_LEFT
    bottom = ROOM_TOP + 2.99 * SCALE
    room = local_box(left, bottom, 0, 0, 1.92, 2.99)
    draw.rectangle(room, fill=COLORS["room"], outline=COLORS["wall"], width=9)
    draw_service_box(draw, left, bottom, 1.92, 2.99,
                     ("west", "north", "east", "south"))
    draw_door(draw, "old", left, bottom)
    markers = draw_old_service_connections(draw, left, bottom, fixtures)
    for item in fixtures:
        fixture(draw, left, bottom, item)
    for point, label in markers:
        connection_point(draw, point, label)
    draw.text((left, ROOM_TOP - 88), "OLD BATHROOM  1.92 x 2.99 m",
              font=font(28, True), fill=COLORS["text"])
    draw.text((left, ROOM_TOP - 50), "Surface routes in perimeter wall/plinth box to surveyed points",
              font=font(19), fill=COLORS["muted"])
    return bottom


def draw_new_room(draw, fixtures):
    left = NEW_LEFT
    bottom = ROOM_TOP + 1.35 * SCALE
    polygon = [
        (left, bottom),
        (left + 3.38 * SCALE, bottom),
        (left + 3.38 * SCALE, bottom - .39 * SCALE),
        (left + 3.70 * SCALE, bottom - .39 * SCALE),
        (left + 3.70 * SCALE, bottom - 1.35 * SCALE),
        (left, bottom - 1.35 * SCALE),
    ]
    draw.polygon(polygon, fill=COLORS["room"], outline=COLORS["wall"])
    draw.line(polygon + [polygon[0]], fill=COLORS["wall"], width=9, joint="curve")
    draw_service_box(draw, left, bottom, 3.38, 1.35, ("north",))
    stack = local_box(left, bottom, 3.38, 0, .32, .39)
    draw.rectangle(stack, fill=COLORS["stack"], outline=COLORS["wall"], width=2)
    label_center(draw, stack, "S", 18, "white")
    draw_door(draw, "new", left, bottom)
    markers = draw_new_service_routes(draw, left, bottom, fixtures, (3.54, .195))
    for item in fixtures:
        fixture(draw, left, bottom, item)
    for point, label in markers:
        connection_point(draw, point, label)

    water_y = bottom - 1.22 * SCALE
    draw.line((left - 55, water_y, left + 3.38 * SCALE, water_y),
              fill=COLORS["water"], width=5)
    draw.polygon([(left - 55, water_y), (left - 35, water_y - 10),
                  (left - 35, water_y + 10)], fill=COLORS["water"])
    draw.text((left, ROOM_TOP - 88), "NEW BATHROOM  3.38 x 1.35 m",
              font=font(28, True), fill=COLORS["text"])
    draw.text((left, ROOM_TOP - 50), "All new pipes in north-wall service box; waste falls east to SH_san",
              font=font(19), fill=COLORS["muted"])
    return bottom


def item(kind, label, rect, clearance=None):
    return {"kind": kind, "label": label, "rect": rect, "clearance": clearance}


LAYOUTS = [
    {
        "title": "01 - BALANCED / RECOMMENDED",
        "rating": "Best overall: comfortable old bathroom; compact but workable new bathroom.",
        "old": [
            item("bath", "BATH 170x75", (.10, .08, 1.70, .75), (.10, .83, 1.70, .65, "comfort")),
            item("wc", "WC", (.40, 2.29, .40, .70), (.32, 1.69, .56, .60, "comfort")),
            item("basin", "BASIN", (.00, 1.22, .45, .55), (.45, 1.17, .70, .65, "comfort")),
        ],
        "new": [
            item("laundry", "W/D", (.05, .75, .60, .60), (.05, .05, .60, .70, "comfort")),
            item("basin", "BASIN", (.78, .90, .55, .45), (.78, .25, .55, .65, "comfort")),
            item("wc", "WC", (1.50, .65, .40, .70), (1.42, .05, .56, .60, "comfort")),
            item("shower", "SHOWER 90", (2.48, .45, .90, .90), (1.88, .45, .60, .90, "comfort")),
        ],
    },
    {
        "title": "02 - BASIN FIRST AT NEW ENTRY",
        "rating": "Good daily access to the new basin; laundry remains away from the shower.",
        "old": [
            item("bath", "BATH 170x75", (.10, .08, 1.70, .75), (.10, .83, 1.70, .60, "comfort")),
            item("wc", "WC", (.40, 2.29, .40, .70), (.32, 1.69, .56, .60, "comfort")),
            item("basin", "BASIN", (.00, 1.22, .45, .55), (.45, 1.17, .70, .65, "comfort")),
        ],
        "new": [
            item("basin", "BASIN", (.05, .90, .55, .45), (.05, .25, .55, .65, "comfort")),
            item("laundry", "W/D", (.72, .75, .60, .60), (.72, .10, .60, .65, "comfort")),
            item("wc", "WC", (1.50, .65, .40, .70), (1.42, .05, .56, .60, "comfort")),
            item("shower", "SHOWER 90", (2.48, .45, .90, .90), (1.88, .45, .60, .90, "comfort")),
        ],
    },
    {
        "title": "03 - LAUNDRY IN OLD BATHROOM",
        "rating": "New bathroom feels calmer; old bathroom circulation is only minimum.",
        "old": [
            item("bath", "BATH 170x75", (.05, .10, .75, 1.70), (.80, .10, .62, 1.70, "minimum")),
            item("laundry", "W/D", (.05, 2.02, .60, .60), (.65, 2.02, .60, .60, "minimum")),
            item("wc", "WC", (.82, 2.29, .70, .40), (.82, 1.69, .70, .60, "minimum")),
            item("basin", "BASIN", (1.37, .10, .45, .55), (.77, .10, .60, .55, "minimum")),
        ],
        "new": [
            item("basin", "BASIN", (.18, .90, .60, .45), (.18, .20, .60, .70, "comfort")),
            item("wc", "WC", (1.30, .65, .40, .70), (1.22, .05, .56, .60, "comfort")),
            item("shower", "SHOWER 90", (2.48, .45, .90, .90), (1.78, .45, .70, .90, "comfort")),
        ],
    },
    {
        "title": "04 - SHOWER OLD / BATH NEW",
        "rating": "Separates quick shower from bathing; new-bath aisle is minimum beside the tub.",
        "old": [
            item("shower", "SHOWER 90", (.05, .05, .90, .90), (.95, .05, .65, .90, "comfort")),
            item("laundry", "W/D", (.05, 1.28, .60, .60), (.65, 1.28, .65, .60, "comfort")),
            item("wc", "WC", (.30, 2.29, .70, .40), (1.00, 2.12, .65, .65, "comfort")),
            item("basin", "BASIN", (1.30, 2.49, .52, .45), (1.20, 1.84, .62, .65, "comfort")),
        ],
        "new": [
            item("basin", "BASIN", (.05, .90, .55, .45), (.05, .25, .55, .65, "comfort")),
            item("wc", "WC", (.72, .65, .40, .70), (.64, .05, .56, .60, "comfort")),
            item("bath", "BATH 170x75", (1.50, .60, 1.70, .75), (1.50, .05, 1.70, .55, "minimum")),
        ],
    },
    {
        "title": "05 - SHOWER + LAUNDRY OLD",
        "rating": "Most open new-bath entrance; old room works, but appliance access is tighter.",
        "old": [
            item("shower", "SHOWER 90", (.05, .05, .90, .90), (.95, .05, .60, .90, "comfort")),
            item("laundry", "W/D", (.05, 1.22, .60, .60), (.65, 1.22, .60, .60, "minimum")),
            item("wc", "WC", (.30, 2.29, .70, .40), (1.00, 2.10, .62, .65, "comfort")),
            item("basin", "BASIN", (1.35, .10, .47, .55), (.75, .10, .60, .55, "minimum")),
        ],
        "new": [
            item("basin", "BASIN", (.10, .90, .60, .45), (.10, .20, .60, .70, "comfort")),
            item("wc", "WC", (.90, .65, .40, .70), (.82, .05, .56, .60, "comfort")),
            item("bath", "BATH 170x75", (1.55, .60, 1.70, .75), (1.55, .05, 1.70, .55, "minimum")),
        ],
    },
    {
        "title": "06 - SHORTEST NEW DRAINAGE",
        "rating": "Keeps shower and WC closest to the new riser; least tolerant of product-size changes.",
        "old": [
            item("bath", "BATH 170x75", (.10, .08, 1.70, .75), (.10, .83, 1.70, .65, "comfort")),
            item("wc", "WC", (.40, 2.29, .40, .70), (.32, 1.69, .56, .60, "comfort")),
            item("basin", "BASIN", (.00, 1.22, .45, .55), (.45, 1.17, .70, .65, "comfort")),
        ],
        "new": [
            item("laundry", "W/D", (.05, .75, .60, .60), (.05, .05, .60, .70, "comfort")),
            item("basin", "BASIN", (.76, .90, .50, .45), (.76, .25, .50, .65, "comfort")),
            item("wc", "WC", (1.38, .65, .40, .70), (1.30, .05, .56, .60, "comfort")),
            item("shower", "SHOWER 90", (2.48, .45, .90, .90), (1.88, .45, .60, .90, "comfort")),
        ],
    },
]


def draw_legend(draw):
    y = 1300
    draw.text((170, y), "CLEARANCE GUIDE", font=font(24, True), fill=COLORS["text"])
    draw.rectangle((170, y + 42, 225, y + 77), outline=COLORS["clear_comfort"], width=4)
    draw.text((240, y + 43), "comfortable target: generally 65-75 cm",
              font=font(20), fill=COLORS["muted"])
    draw.rectangle((650, y + 42, 705, y + 77), outline=COLORS["clear_min"], width=4)
    draw.text((720, y + 43), "minimum / tight: generally 55-60 cm",
              font=font(20), fill=COLORS["muted"])
    draw.rectangle((1120, y + 42, 1175, y + 77), fill=COLORS["service_box"],
                   outline=COLORS["door"])
    draw.text((1190, y + 43), "wall / plinth service box", font=font(20), fill=COLORS["muted"])
    draw.line((1510, y + 60, 1580, y + 60), fill=COLORS["water"], width=5)
    draw.text((1595, y + 43), "water", font=font(20), fill=COLORS["muted"])
    dashed_line(draw, [(1715, y + 60), (1785, y + 60)], COLORS["drain"], width=3)
    draw.text((1800, y + 43), "waste", font=font(20), fill=COLORS["muted"])
    draw.rectangle((1930, y + 42, 1985, y + 77), fill=COLORS["stack"])
    draw.text((2000, y + 43), "SH_san", font=font(20), fill=COLORS["muted"])
    connection_point(draw, (182, y + 120), "L")
    draw.text((210, y + 108),
              "connection point: fixture waste/water branch position on the box run",
              font=font(19), fill=COLORS["muted"])
    draw.text((170, y + 145),
              "Surveyed old-bath terminals: B bath west +0.50 m (W h=.30 / S floor); "
              "L basin mid-west (W h=.85 / S h=.35); WC north +0.60 m (S height verify).",
              font=font(17), fill=COLORS["muted"])
    draw.text((170, y + 172),
              "No new pipes in the floor: use accessible low wall/plinth boxes for waste and a "
              "service wall/upper box for water; keep gravity fall continuously to SH_san.",
              font=font(17), fill=COLORS["muted"])
    draw.text((170, y + 199),
              "Concept only. Size the box after selecting DN110 WC / DN50 branchwork and checking falls, "
              "existing connection inverts, door swings, products, and Polish requirements.",
              font=font(17), fill=COLORS["warning"])


def render_layout(index, layout):
    image = Image.new("RGB", (2200, 1620), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((45, 35, 2155, 1580), radius=24, fill=COLORS["paper"])
    draw.text((110, 70), layout["title"], font=font(40, True), fill=COLORS["text"])
    draw.text((110, 125), layout["rating"], font=font(23), fill=COLORS["muted"])
    draw_old_room(draw, layout["old"])
    draw_new_room(draw, layout["new"])
    draw_box_detail(draw, NEW_LEFT, 900)
    draw_legend(draw)
    path = OUT / f"{index:02d}_{layout['title'].split(' - ', 1)[1].lower().replace(' ', '_').replace('/', '_')}.png"
    image.save(path, optimize=True)
    return image, path


def make_contact_sheet(images):
    thumb_w, thumb_h = 1100, 810
    sheet = Image.new("RGB", (2200, 2430), COLORS["background"])
    for index, image in enumerate(images):
        thumb = image.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(thumb, ((index % 2) * thumb_w, (index // 2) * thumb_h))
    path = OUT / "bathroom_layouts_overview.png"
    sheet.save(path, optimize=True)
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    images = []
    paths = []
    for index, layout in enumerate(LAYOUTS, 1):
        image, path = render_layout(index, layout)
        images.append(image)
        paths.append(path)
    overview = make_contact_sheet(images)
    print(f"Generated {len(paths)} layouts and overview: {overview}")


if __name__ == "__main__":
    main()
