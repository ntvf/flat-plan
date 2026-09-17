"""
Quick visual check of a layout YAML against the original survey scan.

Draws the exterior outline and room polygons to a PNG at a fixed scale and
prints the computed areas, so the transcription can be eyeballed next to the
source drawing before any IFC/PDF work is done.

Usage: python3 scripts/check_layout.py data/as_is.yaml /tmp/check.png
"""

import sys

from PIL import Image, ImageDraw, ImageFont
from model_loader import load_model

PX_PER_M = 80
MARGIN = 60

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

ROOM_FILL = {
    "bedroom": (214, 232, 214),
    "bathroom": (198, 224, 240),
    "storage": (232, 226, 206),
    "open_living": (245, 232, 214),
}


def polygon_area(pts):
    """Shoelace area of a closed-by-implication polygon."""
    total = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def main(src, dst):
    data = load_model(src)
    outline = data["outline"]
    rooms = data["rooms"]

    max_x = max(p[0] for p in outline)
    max_y = max(p[1] for p in outline)
    w = int(max_x * PX_PER_M) + 2 * MARGIN
    h = int(max_y * PX_PER_M) + 2 * MARGIN

    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)

    def tp(pt):
        """Model metres -> image pixels, flipping Y so north is up."""
        return (MARGIN + pt[0] * PX_PER_M, h - MARGIN - pt[1] * PX_PER_M)

    try:
        font = ImageFont.truetype(FONT_PATHS[0], 15)
        font_b = ImageFont.truetype(FONT_PATHS[1], 17)
    except OSError:
        font = font_b = ImageFont.load_default()

    d.polygon([tp(p) for p in outline], fill=(170, 170, 170), outline=(0, 0, 0))

    total = 0.0
    by_id = {r["id"]: r for r in rooms}
    holes = {h for r in rooms for h in r.get("subtract", [])}
    # Islands must be painted after the space that surrounds them.
    draw_order = [r for r in rooms if r["id"] not in holes] + \
                 [r for r in rooms if r["id"] in holes]
    print(f"{'id':>5}  {'name':38s} {'area m2':>8}")
    labels = []  # drawn last so walls and openings never cover the text
    for room in draw_order:
        poly = room["polygon"]
        area = polygon_area(poly)
        # An enclosed room sitting inside this one (e.g. the storage island)
        # is a hole, not floor area.
        for hole_id in room.get("subtract", []):
            other = by_id[hole_id]
            area -= polygon_area(other.get("footprint") or other["polygon"])
        total += area
        fill = ROOM_FILL.get(room["function"], (235, 235, 235))
        d.polygon([tp(p) for p in poly], fill=fill, outline=(40, 40, 40))

        if room.get("label_edges"):
            for i in range(len(poly)):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % len(poly)]
                length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                # Nudge the text off the edge, towards the room's interior.
                cx0 = sum(p[0] for p in poly) / len(poly)
                cy0 = sum(p[1] for p in poly) / len(poly)
                vx, vy = cx0 - mx, cy0 - my
                norm = (vx * vx + vy * vy) ** 0.5 or 1.0
                labels.append((tp((mx + 0.22 * vx / norm, my + 0.22 * vy / norm)),
                               f"{length:.2f}", (190, 0, 0), font_b))

        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        label = f"{room['id']}\n{room['name']}\n{area:.2f} m²"
        labels.append((tp((cx, cy)), label, (0, 0, 0), font))
        print(f"{room['id']:>5}  {room['name'][:38]:38s} {area:8.2f}")

    for wall in data.get("walls", []):
        x, y = wall["at"]
        ww, wh = wall["size"]
        d.rectangle([tp((x, y + wh)), tp((x + ww, y))], fill=(150, 150, 150),
                    outline=(40, 40, 40))

    for col in data.get("columns", []):
        x, y = col["at"]
        cw, ch = col["size"]
        d.rectangle([tp((x, y + ch)), tp((x + cw, y))], fill=(90, 90, 90),
                    outline=(0, 0, 0))

    for shaft in data.get("shafts", []):
        x, y = shaft["at"]
        sw, sh = shaft["size"]
        d.rectangle([tp((x, y + sh)), tp((x + sw, y))], fill=(120, 110, 140),
                    outline=(0, 0, 0))
        d.text(tp((x + sw / 2, y + sh / 2)), shaft["id"].replace("SH_", ""),
               fill=(255, 255, 255), font=font, anchor="mm")

    for win in data.get("windows", []):
        x, y = win["at"]
        ww, wh = win["size"]
        is_door = win.get("ifc_class") == "IfcDoor"
        aperture_colour = (180, 40, 160) if is_door else (0, 90, 200)
        d.rectangle([tp((x, y + wh)), tp((x + ww, y))], fill=(215, 240, 255),
                    outline=aperture_colour)
        # Glazing line down the middle of the reveal.
        if ww >= wh:
            d.line([tp((x, y + wh / 2)), tp((x + ww, y + wh / 2))],
                   fill=aperture_colour, width=2)
        else:
            d.line([tp((x + ww / 2, y)), tp((x + ww / 2, y + wh))],
                   fill=aperture_colour, width=2)
        d.text(tp((x + ww / 2, y + wh / 2)), win["id"],
               fill=(150, 20, 130) if is_door else (0, 60, 150),
               font=font, anchor="mm")

    for door in data.get("doors", []):
        x, y = door["at"]
        dw, dh = door["size"]
        has_leaf = door.get("has_leaf", True)
        colour = (200, 0, 0) if has_leaf else (210, 120, 0)
        d.rectangle([tp((x, y + dh)), tp((x + dw, y))], fill=(255, 255, 255),
                    outline=colour)
        d.text(tp((x + dw / 2, y + dh / 2)), door["id"], fill=colour, font=font,
               anchor="mm")

    # Room names, areas and edge lengths go on top of everything, with a white
    # halo so they stay legible over walls, columns and openings.
    for pos, text, colour, fnt in labels:
        for ox in (-2, -1, 0, 1, 2):
            for oy in (-2, -1, 0, 1, 2):
                if ox or oy:
                    d.multiline_text((pos[0] + ox, pos[1] + oy), text,
                                     fill=(255, 255, 255), font=fnt,
                                     anchor="mm", align="center")
        d.multiline_text(pos, text, fill=colour, font=fnt, anchor="mm",
                         align="center")

    stated = data["meta"]["stated_total_area"]
    gross = polygon_area(outline)
    summary = (
        f"rooms total {total:.2f} m²   |   stated {stated:.2f} m²   "
        f"|   gross footprint {gross:.2f} m²"
    )
    d.text((MARGIN, 20), summary, fill=(0, 0, 0), font=font_b)
    print("\n" + summary)

    img.save(dst)
    print("wrote", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
