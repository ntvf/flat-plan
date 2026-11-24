#!/usr/bin/env python3
"""Printable per-room contractor sheets (A4, Ukrainian) for the target state.

    python3 scripts/make_room_sheets.py data/target.yaml exports/rooms/renders \
        exports/rooms/rooms_uk.pdf

Each room gets a dimensioned furnished plan at a standard scale, then a page
with the furniture/fixture schedule and the top/bird's-eye renders from
scripts/render_room_views.py. Finish setting-out pages (floors, bathroom
wall tiles, kitchen backsplash) follow from scripts/finish_sheets.py.
"""

import math
import sys
import textwrap
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Arc, Circle, Ellipse, Polygon, Rectangle  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import room_views as rv  # noqa: E402
from make_tender_docs import area, dim_chain, draw_plan, room_areas  # noqa: E402
from model_loader import load_model  # noqa: E402

MM = 1 / 25.4
PAGE = (297, 210)                      # A4 landscape, mm
SCALES = (20, 25, 40, 50, 75, 100)
PLAN_BOX = (12, 30, 188, 166)          # x, y, w, h in mm
SIDE_X = 206                           # legend and notes column
TABLE_BOX = (12, 30, 273, 62)
TOP_BOX = (12, 96, 134, 100)
BIRD_BOX = (151, 96, 134, 100)
CHAIN_OFFSET = 0.45

FILL = {
    "kitchen": "#e9dcc6", "appliance": "#d9dde3", "sanitary": "#d7ecf6",
    "storage": "#eeeeee", "furniture": "#f3eadb", "glass": "#cfe8f3",
}
KIND_GROUP = {
    "worktop": "kitchen", "hob": "kitchen", "sink": "kitchen", "dishwasher": "kitchen",
    "fridge": "appliance", "oven_tower": "appliance", "washer": "appliance",
    "bath": "sanitary", "basin": "sanitary", "wc": "sanitary", "shower_tray": "sanitary",
    "shower_floor": "sanitary", "install_box": "sanitary",
    "glass": "glass", "closet": "storage", "wardrobe": "storage", "shelving": "storage",
}
SERVICES = {
    "socket": ("Р", "#c77700", "розетка 230 В"),
    "power_hob": ("Е", "#b3261e", "окрема лінія 400 В / 3×16 А (індукція)"),
    "power_oven": ("Д", "#b3261e", "окрема лінія 230 В / 16 А (духова шафа + мікрохвильова)"),
    "water": ("В", "#1f6fb5", "вода ХВ + ГВ"),
    "drain": ("К", "#6b4f2a", "каналізація"),
    "tv": ("ТВ", "#5b3c8c", "ТВ / інтернет"),
}
NOTES = {
    "00_flat": [
        "Кухня — варіант G1: П-подібна кухня за новою стіною вздовж входу.",
        "Ванні кімнати — збалансований варіант розстановки сантехніки.",
        "Меблі в спальнях і вітальні орієнтовні: показують розстановку для розеток і світла.",
    ],
    "01_kitchen": [
        "Нові перегородки ГКЛ (червоні): екран 1,20 м вздовж входу та задня стінка шафи 0,60 м, h = стеля.",
        "Бойлер 100 л демонтується з цієї стіни; нове місце уточнити.",
        "Мийка на існуючому виводі під OB1 (глухе вікно); ПММ від того ж виводу.",
        "Витяжка рециркуляційна. Навісні шафи — за проєктом кухні.",
        "Кутовий корпус і стільниця на скосі — індивідуальний розмір, обміряти на об'єкті.",
        "Робоча зона: 170 см між мийкою і плитою. K01 — висока колона: духова шафа + мікрохвильова.",
    ],
    "02_living": [
        "Меблі орієнтовні. Розетки — біля дивана та ТВ-тумби.",
        "Кондиціонер переноситься на нову стіну ванної 2 над диваном.",
    ],
    "03_bathroom_1": [
        "Підводка до пральної машини в коробі вздовж західної та північної стін.",
        "Розетка пральної машини — IP44, через ПЗВ 30 мА.",
        "Існуючі виводи ванни, умивальника та унітазу перевірити перед демонтажем.",
        "Інсталяція унітазу вже в стіні — лише підвісний унітаз; умивальник B12 підвісний; ванна з екраном у плитці та люком ревізії.",
        "Сушильна машина — на пральній (колона 60×60, h ≈ 1,75), з'єднувальний комплект; 2 розетки IP44.",
    ],
    "04_bathroom_2": [
        "Гідроізоляція: вся підлога + 20 см на стіни, у зоні душу до 2,0 м.",
        "Каналізація до стояка SH_san з ухилом; підвісна стеля h = 2,40 м (8 цілих рядів плитки 30×60, без різів).",
        "Двері 80 см відкриваються назовні. Розетка умивальника — IP44, ПЗВ 30 мА.",
        "Душ: піддон 90×90 урівень з підлогою, одна рама 90 з 2 дверцятами по 45 см назовні; решта — ГКЛ у плитці.",
        "Унітаз підвісний на інсталяції в коробі ГКЛ h 1,20 (труба до SH_san у забудові); умивальник — прямо на стіні.",
    ],
    "05_bedroom_1": ["Меблі орієнтовні: показують розстановку для розеток і світла."],
    "06_bedroom_2": ["Меблі орієнтовні: показують розстановку для розеток і світла."],
    "07_bedroom_3": ["Меблі орієнтовні: показують розстановку для розеток і світла."],
    "08_storage": ["Стелажі 40 см на всю висоту вздовж східної та північної стін."],
}


# ------------------------------------------------------------------ geometry

def item_edges(item):
    if item.get("polygon"):
        pts = [tuple(p) for p in item["polygon"]]
    else:
        x0, y0, x1, y1 = rv.item_rect(item)
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return list(zip(pts, pts[1:] + pts[:1]))


def reference_segments(model, sheet):
    """Room faces (with outward side) that furniture can be dimensioned from."""
    by_id = {r["id"]: r for r in model["rooms"]}
    segments = []
    for room_id in sheet.get("rooms") or [r["id"] for r in model["rooms"]]:
        room = by_id[room_id]
        poly = room["polygon"]
        ccw = area(poly) > 0
        for a, b in zip(poly, poly[1:] + poly[:1]):
            segments.append((tuple(a), tuple(b), ccw))
        for hole in room.get("subtract", []):
            fp = by_id[hole].get("footprint") or by_id[hole]["polygon"]
            hole_ccw = area(fp) > 0
            for a, b in zip(fp, fp[1:] + fp[:1]):
                segments.append((tuple(a), tuple(b), not hole_ccw))
    for wall in model.get("walls", []):
        if wall.get("renovation_status") != "new":
            continue
        x, y = wall["at"]
        w, d = wall["size"]
        rect = [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]
        for a, b in zip(rect, rect[1:] + rect[:1]):
            segments.append((a, b, True))
    return segments


def chains_for(model, sheet, items):
    """Dimension chains along every face that has furniture standing on it."""
    chains = []
    for a, b, ccw in reference_segments(model, sheet):
        horizontal = abs(a[1] - b[1]) < 1e-6
        vertical = abs(a[0] - b[0]) < 1e-6
        if not (horizontal or vertical):
            continue
        axis = 0 if horizontal else 1
        line = a[1 - axis]
        lo, hi = sorted((a[axis], b[axis]))
        if hi - lo < 0.3:
            continue
        coords = set()
        for item in items:
            for p, q in item_edges(item):
                if abs(p[1 - axis] - line) < 0.005 and abs(q[1 - axis] - line) < 0.005:
                    s0, s1 = sorted((p[axis], q[axis]))
                    if s1 > lo + 0.01 and s0 < hi - 0.01:
                        coords.update((max(s0, lo), min(s1, hi)))
        if not coords:
            continue
        # Measure from the nearer corner; the far one only on short faces.
        if hi - lo <= 2.6 or min(coords) - lo <= hi - max(coords):
            coords.add(lo)
        if hi - lo <= 2.6 or min(coords) - lo > hi - max(coords):
            coords.add(hi)
        merged = []
        for c in sorted(coords):
            if not merged or c - merged[-1] > 0.02:
                merged.append(c)
        coords = merged
        dx, dy = b[0] - a[0], b[1] - a[1]
        # Outward normal of a CCW polygon edge is (dy, -dx).
        nx, ny = (dy, -dx) if ccw else (-dy, dx)
        side = (ny if horizontal else nx) > 0
        fixed = line + (CHAIN_OFFSET if side else -CHAIN_OFFSET)
        chains.append((sorted(round(c, 3) for c in coords), fixed, horizontal, 1 if side else -1))
    unique = {}
    for chain in chains:
        unique[(tuple(chain[0]), round(chain[1], 3), chain[2])] = chain
    return list(unique.values())


# ------------------------------------------------------------------ drawing

def draw_item(ax, item, model, number_size):
    kind = item["kind"]
    group = KIND_GROUP.get(kind, "furniture")
    dashed = item.get("indicative", False)
    style = dict(edgecolor="#333333", lw=0.6, ls=(0, (4, 2)) if dashed else "-", zorder=11)
    if item.get("polygon"):
        ax.add_patch(Polygon(item["polygon"], closed=True, facecolor=FILL[group], **style))
        pts = item["polygon"]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
    else:
        x0, y0, x1, y1 = rv.item_rect(item)
        outline = rv.item_outline(item, model)
        if outline:
            ax.add_patch(Polygon(outline, closed=True, facecolor=FILL[group], **style))
            bx0, by0, bx1, by1 = rv.item_boxes(item, model)[0]
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        else:
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=FILL[group], **style))
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        symbol(ax, item, model)
    if kind not in ("glass", "chair"):
        ax.text(cx, cy, item["id"], ha="center", va="center", fontsize=number_size, weight="bold",
                zorder=14, bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.85))
    return cx, cy


def symbol(ax, item, model):
    kind = item["kind"]
    back = rv.item_back(item, model)
    L, D = rv.along_depth(item, back)
    lb = lambda u0, u1, v0, v1: rv.local_box(item, back, u0, u1, v0, v1)  # noqa: E731
    line = dict(edgecolor="#333333", facecolor="none", lw=0.4, zorder=12)

    def rect(r, **kw):
        ax.add_patch(Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], **{**line, **kw}))

    def ell(r, **kw):
        ax.add_patch(Ellipse(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), r[2] - r[0], r[3] - r[1],
                             **{**line, **kw}))

    if kind == "hob":
        g = lb(0.03, L - 0.03, 0.06, D - 0.04)
        rect(g, facecolor="#333333")
        for fu, fv, r in ((0.28, 0.28, 0.09), (0.72, 0.28, 0.07), (0.28, 0.72, 0.07), (0.72, 0.72, 0.09)):
            ax.add_patch(Circle((g[0] + (g[2] - g[0]) * fu, g[1] + (g[3] - g[1]) * fv), r,
                                edgecolor="white", facecolor="none", lw=0.4, zorder=13))
    elif kind == "sink":
        rect(lb(0.08, L - 0.08, 0.12, D - 0.06), facecolor="white")
    elif kind in ("basin",):
        ell(lb(0.06, L - 0.06, 0.10, D - 0.05), facecolor="white")
    elif kind == "wc" and item.get("wall_hung"):
        ell(lb(0.02, L - 0.02, 0.0, D), facecolor="white")
    elif kind == "wc":
        rect(lb(0.03, L - 0.03, 0.0, 0.16))
        ell(lb(0.02, L - 0.02, 0.16, D), facecolor="white")
    elif kind == "install_box":
        rect(lb(0.0, L, 0.0, D), hatch="////", edgecolor="#777777")
    elif kind == "shower_floor":
        rect(lb(0.0, L, 0.0, D), hatch="..", edgecolor="#999999")
        rect(lb(0.08, L - 0.08, 0.03, 0.09), facecolor="#333333")
    elif kind == "glass" and item.get("opens"):
        x0, y0, x1, y1 = rv.item_rect(item)
        w = max(x1 - x0, y1 - y0)
        hx = (x0 + x1) / 2 if y1 - y0 > x1 - x0 else (x0 if item["hinge"] == "W" else x1)
        hy = (y0 + y1) / 2 if x1 - x0 > y1 - y0 else (y0 if item["hinge"] == "S" else y1)
        sx = {"W": -1, "E": 1}.get(item["opens"], 0)
        sy = {"S": -1, "N": 1}.get(item["opens"], 0)
        if sx:
            tip, start = (hx + sx * w, hy), (hx, hy + (w if item["hinge"] == "S" else -w))
        else:
            tip, start = (hx, hy + sy * w), (hx + (w if item["hinge"] == "W" else -w), hy)
        ax.plot([hx, tip[0]], [hy, tip[1]], color="#1f6fb5", lw=0.8, zorder=12)
        a0 = math.degrees(math.atan2(start[1] - hy, start[0] - hx))
        a1 = math.degrees(math.atan2(tip[1] - hy, tip[0] - hx))
        lo, hi = sorted((a0, a1))
        if hi - lo > 180:
            lo, hi = hi, lo + 360
        ax.add_patch(Arc((hx, hy), 2 * w, 2 * w, theta1=lo, theta2=hi, color="#1f6fb5", lw=0.4,
                         ls=(0, (3, 2)), zorder=12))
    elif kind == "bath":
        x0, y0, x1, y1 = rv.item_rect(item)
        ax.add_patch(Rectangle((x0 + 0.08, y0 + 0.08), x1 - x0 - 0.16, y1 - y0 - 0.16,
                               **{**line, "facecolor": "white"}))
    elif kind == "shower_tray":
        x0, y0, x1, y1 = rv.item_rect(item)
        ax.plot([x0, x1], [y0, y1], color="#333333", lw=0.3, zorder=12)
        ax.plot([x0, x1], [y1, y0], color="#333333", lw=0.3, zorder=12)
    elif kind == "bed":
        rect(lb(0.0, L, 0.0, 0.06), facecolor="#b08a5a")
        for k in range(2):
            u0 = 0.08 + k * (L - 0.16) / 2
            rect(lb(u0 + 0.03, u0 + (L - 0.16) / 2 - 0.03, 0.12, 0.55), facecolor="white")
        rect(lb(0.0, L, 0.65, D), facecolor="#dfe6ea")
    elif kind == "sofa" and rv.l_shape(item, model):
        (c0, c1), seat = rv.l_shape(item, model)
        outer = 0.0 if c0 < 1e-9 else L - 0.18
        other = L - 0.18 if outer == 0.0 else 0.0
        rect(lb(0.0, L, 0.0, 0.22))
        rect(lb(outer, outer + 0.18, 0.22, D))
        rect(lb(other, other + 0.18, 0.22, seat))
    elif kind == "sofa":
        rect(lb(0.0, L, 0.0, 0.22))
        rect(lb(0.0, 0.18, 0.22, D))
        rect(lb(L - 0.18, L, 0.22, D))
    elif kind in ("wardrobe", "closet"):
        x0, y0, x1, y1 = rv.item_rect(item)
        ax.plot([x0, x1], [y0, y1], color="#999999", lw=0.3, zorder=12)
        ax.plot([x0, x1], [y1, y0], color="#999999", lw=0.3, zorder=12)
    elif kind == "fridge":
        rect(lb(0.03, L - 0.03, 0.03, D - 0.03))
    elif kind == "oven_tower":
        rect(lb(0.03, L - 0.03, 0.03, D - 0.03))
        rect(lb(0.10, L - 0.10, D - 0.12, D - 0.04), facecolor="#333333")
    elif kind == "washer":
        ell(lb(0.10, L - 0.10, 0.10, D - 0.10))


def service_markers(ax, item, model, radius):
    services = item.get("services") or []
    if not services:
        return
    if item.get("polygon"):
        pts = [p for p in item["polygon"]]
        back_pts = [p for p in pts if abs(p[0] - 1.40) < 0.01] or pts
        bx = sum(p[0] for p in back_pts) / len(back_pts) + 0.12
        by = sum(p[1] for p in back_pts) / len(back_pts)
        anchors, step = (bx, by), (0.0, 1.0)
    else:
        back = rv.item_back(item, model)
        L, _ = rv.along_depth(item, back)
        r = rv.local_box(item, back, 0.0, L, 0.0, 0.0)
        anchors = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        step = (1.0, 0.0) if back in ("N", "S") else (0.0, 1.0)
        inward = {"N": (0, -1), "S": (0, 1), "W": (1, 0), "E": (-1, 0)}[back]
        anchors = (anchors[0] + inward[0] * radius * 1.3, anchors[1] + inward[1] * radius * 1.3)
    n = len(services)
    for k, service in enumerate(services):
        letter, colour, _ = SERVICES[service]
        off = (k - (n - 1) / 2) * radius * 2.3
        x, y = anchors[0] + step[0] * off, anchors[1] + step[1] * off
        ax.add_patch(Circle((x, y), radius, facecolor="white", edgecolor=colour, lw=0.8, zorder=15))
        ax.text(x, y, letter, ha="center", va="center", fontsize=4.2 if len(letter) > 1 else 5,
                color=colour, weight="bold", zorder=16)


def mask_other_rooms(ax, model, sheet):
    if not sheet.get("rooms"):
        return
    for room in model["rooms"]:
        if room["id"] in sheet["rooms"]:
            continue
        poly = room.get("footprint") or room["polygon"]
        ax.add_patch(Polygon(poly, closed=True, facecolor="white", edgecolor="none", alpha=0.55, zorder=13))


def fit_chains(crop, chains, pad=0.3):
    """Grow the crop so every dimension chain and its labels stay on the sheet."""
    x0, y0, x1, y1 = crop
    for coords, fixed, horizontal, _side in chains:
        lo, hi = (fixed - pad, fixed + pad)
        if horizontal:
            x0, x1 = min(x0, coords[0] - 0.1), max(x1, coords[-1] + 0.1)
            y0, y1 = min(y0, lo), max(y1, hi)
        else:
            y0, y1 = min(y0, coords[0] - 0.1), max(y1, coords[-1] + 0.1)
            x0, x1 = min(x0, lo), max(x1, hi)
    return x0, y0, x1, y1


def choose_scale(crop, preferred):
    w, h = crop[2] - crop[0], crop[3] - crop[1]
    for scale in SCALES:
        if scale < preferred:
            continue
        if w * 1000 / scale <= PLAN_BOX[2] and h * 1000 / scale <= PLAN_BOX[3]:
            return scale
    raise ValueError(f"crop {crop} does not fit the plan box")


def mm_axes(fig, x, y, w, h):
    return fig.add_axes([x / PAGE[0], y / PAGE[1], w / PAGE[0], h / PAGE[1]])


def place_image(fig, box, path, caption):
    x, y, w, h = box
    if not Path(path).exists():
        fig.text((x + w / 2) / PAGE[0], (y + h / 2) / PAGE[1], f"немає візуалізації\n{path}",
                 ha="center", va="center", fontsize=7, color="#999999")
        return
    img = mpimg.imread(path)
    ih, iw = img.shape[:2]
    fit = min(w / iw, (h - 6) / ih)
    dw, dh = iw * fit, ih * fit
    ax = mm_axes(fig, x + (w - dw) / 2, y + 6 + (h - 6 - dh) / 2, dw, dh)
    ax.imshow(img)
    ax.axis("off")
    fig.text((x + w / 2) / PAGE[0], (y + 1.5) / PAGE[1], caption, ha="center", fontsize=7.5, style="italic")


def size_text(item, model):
    if item.get("polygon"):
        return f"скіс 1,29 м × 60 × {item['size'][2] * 100:.0f}"
    back = rv.item_back(item, model)
    L, D = rv.along_depth(item, back)
    if item["kind"] in ("table", "coffee_table", "shower_tray", "glass"):
        L, D = sorted(item["size"][:2], reverse=True)
    corner = ", кутовий" if rv.l_shape(item, model) else ""
    return f"{L * 100:.0f} × {D * 100:.0f} × {item['size'][2] * 100:.0f}{corner}"


def schedule(fig, items, model, box=TABLE_BOX):
    x, y, w, h = box
    rows = []
    seen = {}
    for item in items:
        key = (item["name_uk"], size_text(item, model))
        if item["kind"] == "chair" and key in seen:
            seen[key][0] += f", {item['id']}"
            continue
        services = "; ".join(SERVICES[s][2] for s in item.get("services", []))
        note = item.get("note", "")
        if item.get("indicative"):
            note = "орієнтовно, не входить у роботи" + (f"; {note}" if note else "")
        row = [item["id"], item["name_uk"], size_text(item, model), services, note]
        seen[key] = row
        rows.append(row)
    if not rows:
        return
    ax = mm_axes(fig, x, y, w, h)
    ax.axis("off")
    cols = ["Поз.", "Найменування", "Ш × Г × В, см", "Підключення", "Примітка"]
    widths = [0.07, 0.30, 0.12, 0.25, 0.26]
    size = 5.6
    while True:
        # Average DejaVu glyph is ~0.55 em wide; 1 pt = 0.3528 mm.
        chars = [max(6, int(fw * w / (0.62 * size * 0.3528)) - 1) for fw in widths]
        wrapped = [["\n".join(textwrap.wrap(str(v), c)) or "" for v, c in zip(row, chars)] for row in rows]
        lines = [max(v.count("\n") + 1 for v in row) for row in wrapped]
        line_mm = size * 0.3528 * 1.25 + 0.9
        if (sum(lines) + 1) * line_mm <= h or size <= 4.2:
            break
        size -= 0.3
    table = ax.table(cellText=wrapped, colLabels=cols, loc="upper center", cellLoc="left",
                     colWidths=widths)
    table.auto_set_font_size(False)
    table.set_fontsize(size)
    for (r, c), cell in table.get_celld().items():
        n = 1 if r == 0 else lines[r - 1]
        cell.set_height((n * size * 0.3528 * 1.25 + 0.9) / h)
        cell.set_linewidth(0.3)
        text = cell.get_text()
        if r == 0:
            cell.set_facecolor("#e6e6e6")
            text.set_weight("bold")


def legend(fig, x, y):
    """Vertical legend in the side column; returns the y below it."""
    entries = [(FILL["kitchen"], "-", "кухонні меблі"), (FILL["sanitary"], "-", "сантехніка"),
               (FILL["storage"], "-", "шафи / стелажі"), (FILL["furniture"], (0, (4, 2)), "орієнтовні меблі"),
               ("#c0392b", "-", "нові перегородки ГКЛ")]
    for i, (fc, ls, text) in enumerate(entries):
        yy = y - i * 4.2
        fig.add_artist(Rectangle((x / PAGE[0], yy / PAGE[1]), 6 / PAGE[0], 2.8 / PAGE[1],
                                 transform=fig.transFigure, facecolor=fc, edgecolor="#333333",
                                 lw=0.5, ls=ls))
        fig.text((x + 8) / PAGE[0], (yy + 0.4) / PAGE[1], text, fontsize=6)
    y -= len(entries) * 4.2 + 2
    for i, (letter, colour, text) in enumerate(SERVICES.values()):
        yy = y - i * 4.2
        fig.add_artist(Circle(((x + 3) / PAGE[0], (yy + 1.4) / PAGE[1]), 1.5 / PAGE[0],
                              transform=fig.transFigure, facecolor="white", edgecolor=colour, lw=0.8))
        fig.text((x + 3) / PAGE[0], (yy + 1.4) / PAGE[1], letter, fontsize=4, color=colour,
                 weight="bold", ha="center", va="center")
        fig.text((x + 8) / PAGE[0], (yy + 0.4) / PAGE[1], "\n".join(textwrap.wrap(text, 42)),
                 fontsize=6, va="bottom" if len(text) <= 42 else "center")
    return y - len(SERVICES) * 4.2


def notes_block(fig, x, y, notes, width=48, size=6.2):
    """Bulleted, wrapped notes downward from y; returns the y below them."""
    put = lambda yy, s: fig.text(x / PAGE[0], yy / PAGE[1], s, fontsize=size, va="top")  # noqa: E731
    for note in notes:
        lines = textwrap.wrap(note, width)
        put(y, "• " + "\n   ".join(lines))
        y -= len(lines) * size * 0.3528 * 1.3 + 1.5
    return y


def new_page(title, info, scale_text=None):
    """A4 page with frame and title block; returns (fig, put, finish(number, total))."""
    fig = plt.figure(figsize=(PAGE[0] * MM, PAGE[1] * MM))
    put = lambda x, y, s, **kw: fig.text(x / PAGE[0], y / PAGE[1], s, **kw)  # noqa: E731
    fig.add_artist(Rectangle((8 / PAGE[0], 8 / PAGE[1]), 281 / PAGE[0], 194 / PAGE[1],
                             transform=fig.transFigure, fill=False, lw=0.9))
    fig.add_artist(Rectangle((8 / PAGE[0], 8 / PAGE[1]), 281 / PAGE[0], 18 / PAGE[1],
                             transform=fig.transFigure, fill=False, lw=0.7))
    put(12, 21, "Ремонт квартири, Варшава — проєктний стан", fontsize=6.5)
    put(12, 14.5, title, fontsize=11.5, weight="bold")
    line = "   ".join(info + ([f"масштаб {scale_text} (A4)"] if scale_text else []))
    put(12, 10, line, fontsize=6.2)
    put(150, 21, "Розміри в метрах, у чистоті стін без оздоблення. Перевірити на об'єкті до початку робіт.",
        fontsize=5.6, style="italic")

    def finish(number, total):
        put(255, 19, f"Аркуш {number}/{total}", fontsize=8.5, weight="bold")
        put(255, 12.5, f"{date.today().isoformat()}  стан: проєкт", fontsize=5.8)
    return fig, put, finish


def room_info(model, sheet):
    areas = room_areas(model)
    info = []
    for room_id in sheet.get("rooms") or []:
        room = next(r for r in model["rooms"] if r["id"] == room_id)
        info.append(f"S = {areas[room_id]:.2f} м²" + (f", {room['clear'][0]:.2f} × {room['clear'][1]:.2f} м"
                                                       if room.get("clear") else ""))
    return info + [f"висота стелі {model['meta'].get('ceiling_height', 2.7):.2f} м"]


def plan_page(model, sheet):
    overview = not sheet.get("rooms")
    items = rv.sheet_items(model, sheet)
    chains = [] if overview else chains_for(model, sheet, items)
    crop = fit_chains(rv.sheet_crop(model, sheet), chains)
    scale = choose_scale(crop, sheet["scale"])
    fig, put, finish = new_page(f"{sheet['title']} — план меблів і підключень", room_info(model, sheet),
                                f"1:{scale}")
    w_mm = (crop[2] - crop[0]) * 1000 / scale
    h_mm = (crop[3] - crop[1]) * 1000 / scale
    px, py, pw, ph = PLAN_BOX
    ax = mm_axes(fig, px + (pw - w_mm) / 2, py + (ph - h_mm) / 2, w_mm, h_mm)
    ax.set_xlim(crop[0], crop[2])
    ax.set_ylim(crop[1], crop[3])
    ax.set_aspect("equal")
    ax.axis("off")
    draw_plan(ax, model, True, lang="uk", labels=overview, north="Пн")
    number_size = 4.5 if scale >= 50 else 6
    for item in model.get("furniture", []):
        draw_item(ax, item, model, number_size if item in items else 0.1)
    mask_other_rooms(ax, model, sheet)
    if not overview:
        for item in items:
            service_markers(ax, item, model, 0.045 if scale <= 25 else 0.07)
        before = set(ax.lines) | set(ax.texts)
        for coords, fixed, horizontal, side in chains:
            dim_chain(ax, coords, fixed, horizontal, side)
        for artist in (set(ax.lines) | set(ax.texts)) - before:
            artist.set_zorder(14)
            if hasattr(artist, "set_fontsize"):
                artist.set_fontsize(6)
    for artist in ax.texts:
        artist.set_clip_on(True)
    y = legend(fig, SIDE_X, 190)
    put(SIDE_X, y - 2, "Примітки", fontsize=7, weight="bold", va="top")
    notes = list(model["meta"].get("notes_uk", {}).get(sheet["slug"], NOTES.get(sheet["slug"], [])))
    if overview:
        notes.append("Детальні розміри, специфікації та розкладка плитки — на наступних аркушах.")
    notes_block(fig, SIDE_X, y - 7, notes)
    return fig, finish


def views_page(model, sheet, renders):
    overview = not sheet.get("rooms")
    items = rv.sheet_items(model, sheet)
    fig, put, finish = new_page(f"{sheet['title']} — специфікація і візуалізація", room_info(model, sheet))
    top, bird = TOP_BOX, BIRD_BOX
    if overview:
        top, bird = (12, 30, 134, 166), (151, 30, 134, 166)
    else:
        schedule(fig, items, model)
    place_image(fig, top, renders / f"{sheet['slug']}_top.png", "Вигляд згори")
    place_image(fig, bird, renders / f"{sheet['slug']}_3d.png", "Аксонометрія (стіни зрізані на 1,25 м)")
    return fig, finish


def validate_furniture(model):
    """Furniture stays inside its room and items do not overlap."""
    by_id = {r["id"]: r for r in model["rooms"]}
    problems = []
    items = model.get("furniture", [])
    for item in items:
        room = by_id[item["room"]]
        pts = item.get("polygon") or [list(p) for p in (
            rv.item_rect(item)[:2], rv.item_rect(item)[2:])]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        rx0, ry0, rx1, ry1 = rv.room_bbox(model, item["room"])
        if min(xs) < rx0 - 1e-6 or max(xs) > rx1 + 1e-6 or min(ys) < ry0 - 1e-6 or max(ys) > ry1 + 1e-6:
            problems.append(f"{item['id']} outside room {room['id']}")
    rects = [(i, r) for i in items if not i.get("polygon") and i["kind"] != "glass"
             for r in rv.item_boxes(i, model)]
    for k, (a, ra) in enumerate(rects):
        for b, rb in rects[k + 1:]:
            if a is b:
                continue
            if ra[0] < rb[2] - 1e-6 and rb[0] < ra[2] - 1e-6 and ra[1] < rb[3] - 1e-6 and rb[1] < ra[3] - 1e-6:
                problems.append(f"{a['id']} overlaps {b['id']}")
    for wall in model.get("walls", []):
        x, y = wall["at"]
        w, d = wall["size"]
        for item, r in rects:
            if r[0] < x + w - 1e-6 and x < r[2] - 1e-6 and r[1] < y + d - 1e-6 and y < r[3] - 1e-6:
                problems.append(f"{item['id']} overlaps wall {wall['id']}")
    return problems


def main(model_path, renders, out_pdf):
    model = load_model(model_path)
    problems = validate_furniture(model)
    if problems:
        raise SystemExit("furniture problems:\n  " + "\n  ".join(problems))
    renders, out_pdf = Path(renders), Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    import finish_sheets  # noqa: E402  (imports this module's helpers)
    builders = []
    for sheet in rv.SHEETS:
        builders.append(lambda sheet=sheet: plan_page(model, sheet))
        builders.append(lambda sheet=sheet: views_page(model, sheet, renders))
    builders += finish_sheets.pages(model, renders)
    with PdfPages(out_pdf) as pdf:
        for number, build in enumerate(builders, 1):
            fig, finish = build()
            finish(number, len(builders))
            pdf.savefig(fig)
            plt.close(fig)
        info = pdf.infodict()
        info["Title"] = "Ремонт квартири — аркуші приміщень і оздоблення (A4)"
    print(f"[make_room_sheets] wrote {out_pdf} ({len(builders)} A4 pages)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or ["data/target.yaml", "exports/rooms/renders", "exports/rooms/rooms_uk.pdf"]))
