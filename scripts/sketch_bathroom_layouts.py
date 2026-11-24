#!/usr/bin/env python3
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT = Path("exports/concepts/bathroom_layouts/balanced.png")
SCALE = 260
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

COLORS = {
    "background": "#f4f1ea",
    "paper": "#fffdf8",
    "wall": "#2d333b",
    "room": "#e8eef1",
    "dimension": "#59636e",
    "door": "#a5753d",
    "bath": "#86bfd7",
    "basin": "#acd5e4",
    "wc": "#d0e5eb",
    "laundry": "#bdc2c9",
    "shower": "#72b2ce",
    "shaft": "#b85b45",
    "water": "#327dc1",
    "waste": "#b84949",
    "service_box": "#ead8b6",
    "text": "#222831",
    "muted": "#616b76",
}


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def point(origin, x, y):
    return origin[0] + x * SCALE, origin[1] - y * SCALE


def polygon(draw, origin, coordinates, fill, outline=COLORS["wall"], width=10):
    pixels = [point(origin, x, y) for x, y in coordinates]
    draw.polygon(pixels, fill=fill)
    draw.line(pixels + [pixels[0]], fill=outline, width=width, joint="curve")


def rectangle(draw, origin, x, y, width, depth, fill, label):
    left, bottom = point(origin, x, y)
    right, top = point(origin, x + width, y + depth)
    box = (left, top, right, bottom)
    draw.rounded_rectangle(box, radius=7, fill=fill, outline=COLORS["wall"], width=2)
    draw.text(
        ((left + right) / 2, (top + bottom) / 2),
        label,
        font=font(17, True),
        fill=COLORS["text"],
        anchor="mm",
        align="center",
    )


def dashed_line(draw, coordinates, fill, width=3, dash=11, gap=7):
    for start, end in zip(coordinates, coordinates[1:]):
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


def connection_point(draw, origin, x, y, label):
    px, py = point(origin, x, y)
    draw.ellipse((px - 9, py - 9, px + 9, py + 9), fill=COLORS["paper"], outline=COLORS["waste"], width=3)
    draw.text((px, py), label, font=font(9, True), fill=COLORS["waste"], anchor="mm")


def old_pipe_routes(draw, origin):
    west_x = .055
    north_y = 2.935
    box = [
        point(origin, 0, 0),
        point(origin, .08, 0),
        point(origin, .08, 2.91),
        point(origin, 1.92, 2.91),
        point(origin, 1.92, 2.99),
        point(origin, 0, 2.99),
    ]
    draw.polygon(box, fill=COLORS["service_box"])

    bath = point(origin, 0, .50)
    basin = point(origin, 0, 1.495)
    wc = point(origin, .60, 2.99)
    washer = point(origin, 1.42, 2.69)
    west_basin = point(origin, west_x, 1.495)
    north_basin = point(origin, west_x, north_y)
    north_washer = point(origin, 1.42, north_y)

    draw.line((bath, point(origin, .16, .50)), fill=COLORS["water"], width=4)
    dashed_line(draw, [bath, point(origin, .16, .50)], COLORS["waste"], width=3)
    draw.line((basin, point(origin, .16, 1.495)), fill=COLORS["water"], width=4)
    dashed_line(draw, [basin, point(origin, .16, 1.495)], COLORS["waste"], width=3)
    dashed_line(draw, [wc, point(origin, .50, 2.82)], COLORS["waste"], width=4)
    draw.line((west_basin, north_basin, north_washer, washer), fill=COLORS["water"], width=4)
    dashed_line(draw, [west_basin, north_basin, north_washer, washer], COLORS["waste"], width=3)

def horizontal_dimension(draw, origin, x1, x2, y, label):
    start = point(origin, x1, y)
    end = point(origin, x2, y)
    draw.line((start, end), fill=COLORS["dimension"], width=2)
    for x, _ in (start, end):
        draw.line((x, start[1] - 8, x, start[1] + 8), fill=COLORS["dimension"], width=2)
    draw.text(
        ((start[0] + end[0]) / 2, start[1] - 9),
        label,
        font=font(15, True),
        fill=COLORS["dimension"],
        anchor="ms",
    )


def vertical_dimension(draw, origin, x, y1, y2, label):
    start = point(origin, x, y1)
    end = point(origin, x, y2)
    draw.line((start, end), fill=COLORS["dimension"], width=2)
    for _, y in (start, end):
        draw.line((start[0] - 8, y, start[0] + 8, y), fill=COLORS["dimension"], width=2)
    draw.text(
        (start[0] - 10, (start[1] + end[1]) / 2),
        label,
        font=font(15, True),
        fill=COLORS["dimension"],
        anchor="ms",
    )


def old_door(draw, origin):
    lower = point(origin, 1.92, 1.045)
    upper = point(origin, 1.92, 1.945)
    draw.line((lower, upper), fill=COLORS["room"], width=14)
    leaf_end = point(origin, 2.82, 1.045)
    draw.line((lower, leaf_end), fill=COLORS["door"], width=4)
    draw.arc(
        (lower[0] - .90 * SCALE, lower[1] - .90 * SCALE, lower[0] + .90 * SCALE, lower[1] + .90 * SCALE),
        270,
        360,
        fill=COLORS["door"],
        width=3,
    )
    draw.text((lower[0] + 112, lower[1] - 10), "90 cm plan opening", font=font(14), fill=COLORS["muted"])


def new_door(draw, origin):
    left = point(origin, .10, 0)
    right = point(origin, .90, 0)
    draw.line((left, right), fill=COLORS["room"], width=14)
    leaf_end = point(origin, .10, -.80)
    draw.line((left, leaf_end), fill=COLORS["door"], width=4)
    draw.arc(
        (left[0], left[1], left[0] + .80 * SCALE, left[1] + .80 * SCALE),
        0,
        90,
        fill=COLORS["door"],
        width=3,
    )
    draw.text(((left[0] + right[0]) / 2, left[1] + 26), "80 cm door", font=font(14), fill=COLORS["muted"], anchor="ms")


def draw_old_bathroom(draw):
    origin = (150, 1010)
    polygon(draw, origin, [(0, 0), (1.92, 0), (1.92, 2.99), (0, 2.99)], COLORS["room"])
    old_door(draw, origin)
    old_pipe_routes(draw, origin)

    rectangle(draw, origin, 0, 0, 1.70, .75, COLORS["bath"], "BATH\n170 × 75")
    rectangle(draw, origin, .30, 2.29, .40, .70, COLORS["wc"], "WC\n40 × 70")
    rectangle(draw, origin, 1.12, 2.39, .60, .60, COLORS["laundry"], "WASHER\n60 × 60")
    rectangle(draw, origin, 0, 1.22, .45, .55, COLORS["basin"], "BASIN\n45 × 55")
    connection_point(draw, origin, 0, .50, "B")
    connection_point(draw, origin, 0, 1.495, "L")
    connection_point(draw, origin, .60, 2.99, "WC")

    horizontal_dimension(draw, origin, 0, 1.92, -.16, "1.92 m CLEAR INTERNAL")
    vertical_dimension(draw, origin, -.16, 0, 2.99, "2.99 m")
    horizontal_dimension(draw, origin, 0, 1.70, .91, "170")
    horizontal_dimension(draw, origin, 1.70, 1.92, .91, "22 cm")

    draw.text((150, 105), "EXISTING BATHROOM", font=font(28, True), fill=COLORS["text"])
    draw.text((150, 142), "Plan clear polygon: 1.92 × 2.99 m · 5.74 m²", font=font(18), fill=COLORS["muted"])
    draw.line((150, 170, 210, 170), fill=COLORS["water"], width=4)
    draw.text((220, 170), "water", font=font(14), fill=COLORS["muted"], anchor="lm")
    dashed_line(draw, [(300, 170), (360, 170)], COLORS["waste"], width=3)
    draw.text((370, 170), "waste", font=font(14), fill=COLORS["muted"], anchor="lm")
    draw.rectangle((450, 159, 480, 181), fill=COLORS["service_box"], outline=COLORS["door"])
    draw.text((490, 170), "boxed perimeter route", font=font(14), fill=COLORS["muted"], anchor="lm")


def draw_new_bathroom(draw):
    origin = (920, 650)
    room = [(0, 0), (3.38, 0), (3.38, .39), (3.70, .39), (3.70, 1.35), (0, 1.35)]
    polygon(draw, origin, room, COLORS["room"])
    new_door(draw, origin)

    rectangle(draw, origin, 1.02, 0, .55, .45, COLORS["basin"], "BASIN\n55 × 45")
    rectangle(draw, origin, 1.78, 0, .40, .70, COLORS["wc"], "WC\n40 × 70")
    rectangle(draw, origin, 2.80, .45, .90, .90, COLORS["shower"], "SHOWER\n90 × 90")
    rectangle(draw, origin, 3.38, 0, .32, .39, COLORS["shaft"], "SH_san\n32 × 39")

    horizontal_dimension(draw, origin, 0, 3.38, -.16, "3.38 m CLEAR TO SH_san")
    horizontal_dimension(draw, origin, 0, 3.70, 1.53, "3.70 m CLEAR NORTH FACE")
    vertical_dimension(draw, origin, -.16, 0, 1.35, "1.35 m")
    vertical_dimension(draw, origin, 3.86, 0, .39, "39 cm")
    vertical_dimension(draw, origin, 3.86, .39, 1.35, "96 cm")
    horizontal_dimension(draw, origin, 3.38, 3.70, .30, "32 cm")

    draw.text((920, 105), "NEW BATHROOM", font=font(28, True), fill=COLORS["text"])
    draw.text(
        (920, 142),
        "Plan clear polygon: 4.87 m² with fixed SH_san notch",
        font=font(18),
        fill=COLORS["muted"],
    )
    draw.text(
        (920, 182),
        "South wall: basin → WC. Shower occupies the corner directly above SH_san.",
        font=font(17),
        fill=COLORS["muted"],
    )


def validate():
    fixtures = {
        "old": [
            (0, 0, 1.70, .75),
            (.30, 2.29, .40, .70),
            (1.12, 2.39, .60, .60),
            (0, 1.22, .45, .55),
        ],
        "new": [
            (1.02, 0, .55, .45),
            (1.78, 0, .40, .70),
            (2.80, .45, .90, .90),
        ],
    }
    for x, y, width, depth in fixtures["old"]:
        assert x >= 0 and y >= 0 and x + width <= 1.92 and y + depth <= 2.99
    for x, y, width, depth in fixtures["new"]:
        assert x >= 0 and y >= 0 and y + depth <= 1.35
        assert x + width <= (3.70 if y >= .39 else 3.38)
    for room in fixtures.values():
        for index, (ax, ay, aw, ad) in enumerate(room):
            for bx, by, bw, bd in room[index + 1:]:
                assert not (ax < bx + bw and ax + aw > bx and ay < by + bd and ay + ad > by)


def main():
    validate()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (2000, 1180), COLORS["background"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((35, 30, 1965, 1145), radius=24, fill=COLORS["paper"])
    draw.text((90, 50), "BATHROOM FIXTURE STUDY — FIXED PLAN GEOMETRY", font=font(34, True), fill=COLORS["text"])
    draw.text(
        (90, 1090),
        "Walls, internal faces, doors and shafts are unchanged. Dimensions are metres unless marked cm.",
        font=font(18),
        fill=COLORS["muted"],
    )
    draw_old_bathroom(draw)
    draw_new_bathroom(draw)
    image.save(OUT, optimize=True)
    print(f"Generated plan-based bathroom layout: {OUT}")


if __name__ == "__main__":
    main()
