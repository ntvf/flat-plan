"""A4 finish setting-out pages for the contractor (Ukrainian).

Floors (tiles and engineered wood), bathroom wall tile elevations and the
kitchen backsplash, all drawn from scripts/finishes.py so the drawings and
the quantity tables come from the same geometry. Used by make_room_sheets.py.
"""

import math
import textwrap

from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.patches import Circle, Ellipse, Polygon, Rectangle

import finishes as fin
import make_room_sheets as ms
import room_views as rv
from make_tender_docs import dim_chain, draw_plan

CONTENT = (12, 29, 273, 171)           # x, y, w, h in mm above the title block
JOINT = "#6d5c46"
FACE_NAMES = {"Пн": "північна", "Пд": "південна", "Сх": "східна", "Зх": "західна", "скіс": "скіс"}


# ------------------------------------------------------------------ helpers

def lighten(hex_colour, f):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return (r + (1 - r) * f, g + (1 - g) * f, b + (1 - b) * f)


def scaled_axes(fig, x, y, extent, scale):
    """Axes at true scale with its lower-left corner at (x, y) mm."""
    x0, y0, x1, y1 = extent
    w, h = (x1 - x0) * 1000 / scale, (y1 - y0) * 1000 / scale
    ax = ms.mm_axes(fig, x, y, w, h)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    return ax, w, h


def table(fig, box, cols, widths, rows, size=6.0, bold_last=False):
    x, y, w, h = box
    ax = ms.mm_axes(fig, x, y, w, h)
    ax.axis("off")
    chars = [max(4, int(fw * w / (0.7 * size * 0.3528)) - 1) for fw in widths]
    wrapped = [["\n".join(textwrap.wrap(str(v), c)) or "" for v, c in zip(row, chars)] for row in rows]
    lines = [max(v.count("\n") + 1 for v in row) for row in wrapped]
    t = ax.table(cellText=wrapped, colLabels=cols, loc="upper center", cellLoc="left", colWidths=widths)
    t.auto_set_font_size(False)
    t.set_fontsize(size)
    for (r, c), cell in t.get_celld().items():
        n = 1 if r == 0 else lines[r - 1]
        cell.set_height((n * size * 0.3528 * 1.25 + 1.0) / h)
        cell.set_linewidth(0.3)
        if r == 0:
            cell.set_facecolor("#e6e6e6")
            cell.get_text().set_weight("bold")
        if bold_last and r == len(rows):
            cell.get_text().set_weight("bold")
    used = sum((n * size * 0.3528 * 1.25 + 1.0) for n in [1] + lines)
    return y + h - used


def caption(fig, x, y, text, size=7.5):
    fig.text(x / ms.PAGE[0], y / ms.PAGE[1], text, fontsize=size, weight="bold")


def cm(v):
    c = v * 100
    return f"{c:.0f}" if abs(c - round(c)) < 0.05 else f"{c:.1f}".replace(".", ",")


def fmt_m(v):
    return f"{v:.2f}" if abs(v * 100 - round(v * 100)) < 0.05 else f"{v:.3f}"


def clip_texts(ax):
    for t in ax.texts:
        t.set_clip_on(True)


def dims(ax, coords, fixed, scale, size=5.0):
    """Dimension line below a drawing, ticks and text sized for the scale."""
    k = scale / 1000             # metres per mm on paper
    coords = sorted(coords)
    kw = dict(color="black", lw=0.4, zorder=8)
    ax.plot([coords[0], coords[-1]], [fixed, fixed], **kw)
    for c in coords:
        ax.plot([c, c], [fixed - 1.2 * k, fixed + 1.2 * k], **kw)
        ax.plot([c - 0.8 * k, c + 0.8 * k], [fixed - 0.8 * k, fixed + 0.8 * k], **kw)
    for a, b in zip(coords, coords[1:]):
        text = fmt_m(b - a)
        if (b - a) / k < len(text) * size * 0.2:
            continue
        ax.text((a + b) / 2, fixed - 1.2 * k, text, ha="center", va="top", fontsize=size, zorder=8)


# ------------------------------------------------------------------ tiles

def draw_tiles(ax, region, origin, size, colour, z=2.5, lw=0.3, motif=None, clip=None):
    """Tile pieces (cut ones lighter) and joints clipped exactly to the region."""
    (ox, oy), (tx, ty) = origin, size
    x0, y0, x1, y1 = region.bbox()
    full, cut = [], []
    for cell in fin.grid_cells(region, origin, size):
        pieces = region.trapezoids(*cell[:4])
        (full if cell[4] > tx * ty - 1e-4 else cut).extend(pieces)
    ax.add_collection(PolyCollection(full, facecolors=colour, edgecolors="none", zorder=z))
    ax.add_collection(PolyCollection(cut, facecolors=[lighten(colour, 0.2 if motif else 0.5)],
                                     edgecolors="none", zorder=z))
    joints(ax, region, ox, tx, x0, x1, False, lw, z)
    joints(ax, region, oy, ty, y0, y1, True, lw, z)
    if motif:
        before = len(ax.patches)
        for cell in fin.grid_cells(region, origin, size):
            motif(ax, cell, region, z)
        if clip is not None:
            for patch in ax.patches[before:]:
                patch.set_clip_path(clip)


def joints(ax, region, o, t, lo, hi, horizontal, lw, z, colour=JOINT):
    probe = region.transposed() if horizontal else region
    segs = []
    k = math.ceil((lo - o) / t - 1e-9)
    while o + k * t < hi - 1e-9:
        c = o + k * t
        for a, b in probe.intervals(c + 1e-7):
            segs.append([(a, c), (b, c)] if horizontal else [(c, a), (c, b)])
        k += 1
    ax.add_collection(LineCollection(segs, colors=colour, linewidths=lw, zorder=z + 0.1))


def draw_planks(ax, region, colour, z=2.5, lw=0.15):
    x0, y0, x1, y1 = region.bbox()
    ax.add_collection(PolyCollection(region.trapezoids(x0, y0, x1, y1), facecolors=colour,
                                     edgecolors="none", zorder=z))
    joints(ax, region, 0.0, 0.20, x0, x1, False, lw, z, "#7a5a36")
    # Staggered butt joints, a third of a plank between rows.
    segs = []
    for i, x in enumerate(frange(math.floor(x0 / 0.2) * 0.2, x1, 0.2)):
        y = y0 + (i % 3) * 0.4 + 0.15
        while y < y1:
            cx = x + 0.1
            if region.contains(cx, y):
                segs.append([(max(x, x0), y), (min(x + 0.2, x1), y)])
            y += 1.2
    ax.add_collection(LineCollection(segs, colors="#7a5a36", linewidths=lw, zorder=z + 0.1))


def frange(a, b, step):
    out, k = [], 0
    while a + k * step < b - 1e-9:
        out.append(a + k * step)
        k += 1
    return out


def cut_labels(ax, entry, size=4.5):
    """Width of the cut tile against each wall, in cm, inside the zone."""
    tx, ty = entry["spec"]["size"]
    for axis, (edges, o, t) in enumerate(((entry["edges"][0], entry["origin"][0], tx),
                                          (entry["edges"][1], entry["origin"][1], ty))):
        for c, sign, _length, along in edges:
            piece = fin.first_piece(o, c, sign, t)
            if piece > t - 1e-3:
                continue
            pos = c + sign * min(piece, t) / 2
            x, y = (pos, along) if axis == 0 else (along, pos)
            ax.text(x, y, cm(piece), ha="center", va="center", fontsize=size, color="#8a1c1c",
                    rotation=90 if axis == 0 else 0, zorder=9, weight="bold",
                    bbox=dict(boxstyle="round,pad=0.08", facecolor="white", edgecolor="none", alpha=0.75))


def setting_out_dims(ax, entry, scale):
    """Red datum joints through the zone and their distance to the nearest wall."""
    region = entry["region"]
    x0, y0, x1, y1 = region.bbox()
    (ox, oy), (tx, ty) = entry["origin"], entry["spec"]["size"]
    ex, ey = entry["edges"]
    cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2
    jx = ox + round((cxm - ox) / tx) * tx
    jy = oy + round((cym - oy) / ty) * ty
    for a, b in region.intervals(jx + 1e-7):
        ax.plot([jx, jx], [a, b], color="#c0392b", lw=0.9, zorder=8)
    for a, b in region.transposed().intervals(jy + 1e-7):
        ax.plot([a, b], [jy, jy], color="#c0392b", lw=0.9, zorder=8)
    # Distance to the longest wall on each axis, measured along the datum.
    if ex:
        wall = max(ex, key=lambda e: e[2])
        dim_chain(ax, [wall[0], jx], jy + 0.22 * scale / 50, True, 1)
    if ey:
        wall = max(ey, key=lambda e: e[2])
        dim_chain(ax, [wall[0], jy], jx - 0.22 * scale / 50, False, 1)
    ax.text(jx, jy, "  0", color="#c0392b", fontsize=5, ha="left", va="bottom", zorder=9, weight="bold")


def leaves_motif(ax, cell, region, z):
    x0, y0, x1, y1, _a = cell
    xs = [max(x0, 0.0), min(x1, region.bbox()[2])]
    for k in range(3):
        cx = xs[0] + (xs[1] - xs[0]) * (0.2 + 0.3 * k)
        cy = y0 + (y1 - y0) * (0.35 + 0.3 * (k % 2))
        if xs[0] < cx < xs[1] and region.contains(cx, cy):
            ax.add_patch(Ellipse((cx, cy), 0.28, 0.12, angle=35 + 40 * k, facecolor="#3f6e3a",
                                 edgecolor="none", alpha=0.6, zorder=z + 0.05))


def circles_motif(ax, cell, region, z):
    x0, y0, x1, y1, _a = cell
    for fx in (0.25, 0.75):
        cx, cy = x0 + (x1 - x0) * fx, (y0 + y1) / 2
        if region.contains(cx, cy):
            ax.add_patch(Circle((cx, cy), 0.17, facecolor="none", edgecolor="#9c7f55", lw=0.6, zorder=z + 0.05))
            ax.add_patch(Circle((cx, cy), 0.09, facecolor="none", edgecolor="#9c7f55", lw=0.4, zorder=z + 0.05))


MOTIFS = {"tile_leaves": leaves_motif, "tile_circles": circles_motif}


def draw_floor(ax, entry):
    spec = entry["spec"]
    if spec["kind"] == "tile":
        draw_tiles(ax, entry["region"], entry["origin"], spec["size"], spec["colour"], lw=0.25)
    else:
        draw_planks(ax, entry["region"], spec["colour"])


def finish_legend(fig, x, y, model, materials, chars=60):
    spec = model["finishes"]["materials"]
    for name in materials:
        mat = spec[name]
        fig.add_artist(Rectangle((x / ms.PAGE[0], y / ms.PAGE[1]), 6 / ms.PAGE[0], 3 / ms.PAGE[1],
                                 transform=fig.transFigure, facecolor=mat["colour"], edgecolor="#333", lw=0.4))
        lines = textwrap.wrap(mat["name_uk"], chars)
        fig.text((x + 8) / ms.PAGE[0], (y + 3) / ms.PAGE[1], "\n".join(lines), fontsize=5.8, va="top")
        y -= max(4.5, len(lines) * 2.6 + 1.5)
    fig.add_artist(Rectangle((x / ms.PAGE[0], y / ms.PAGE[1]), 6 / ms.PAGE[0], 3 / ms.PAGE[1],
                             transform=fig.transFigure, facecolor=lighten("#d9c9ac", 0.5), edgecolor="#333", lw=0.4))
    lines = textwrap.wrap("світліший тон — різана плитка; червоні числа — ширина різу, см", chars)
    fig.text((x + 8) / ms.PAGE[0], (y + 3) / ms.PAGE[1], "\n".join(lines), fontsize=5.8, va="top")
    return y - len(lines) * 2.6 - 4


# ------------------------------------------------------------------ pages

def floors_page(model, floors):
    fig, put, finish = ms.new_page("Підлоги — схема покриттів і кількості", ["квартира, проєктний стан"], "1:100")
    ax, w, h = scaled_axes(fig, 12, 31, (-1.0, -1.05, 10.2, 14.1), 100)
    draw_plan(ax, model, False, lang="uk", labels=False, north="Пн")
    for f in floors:
        draw_floor(ax, f)
        x0, y0, x1, y1 = f["region"].bbox()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if f["id"] == "FL_OPEN":
            cx, cy = 3.6, 10.9
        if not f["region"].contains(cx, cy):
            cx, cy = x0 + 0.4, (y0 + y1) / 2
        ax.text(cx, cy, f"{f['id']}\n{f['area']:.2f} м²", ha="center", va="center", fontsize=5, zorder=9,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none", alpha=0.85))
    tile = next((f for f in floors if f["id"] == "FL_OPEN"), None)
    if tile and tile["zone"].get("within"):
        # Tile/wood transition: edges of the tile rectangle that run through the open room.
        room = fin.room_region(model, tile["zone"]["room"])
        wx0, wy0, wx1, wy1 = tile["zone"]["within"]
        for (ax0, ay0), (ax1, ay1) in (((wx1, wy0), (wx1, wy1)), ((wx0, wy0), (wx1, wy0))):
            n = 200
            pts = [(ax0 + (ax1 - ax0) * k / n, ay0 + (ay1 - ay0) * k / n) for k in range(n + 1)]
            run = []
            for px, py in pts + [(None, None)]:
                inside = px is not None and room.contains(px + 1e-3, py + 1e-3) and room.contains(px - 1e-3, py - 1e-3)
                if inside:
                    run.append((px, py))
                elif len(run) > 1:
                    ax.plot([run[0][0], run[-1][0]], [run[0][1], run[-1][1]], color="#c0392b", lw=1.0, zorder=8)
                    run = []
                else:
                    run = []
        ax.text(wx1 + 0.08, (wy0 + wy1) / 2, "перехід x = " + f"{wx1:.2f}".replace(".", ","),
                color="#c0392b", fontsize=4.5, rotation=90, ha="left", va="center", zorder=9,
                bbox=dict(boxstyle="round,pad=0.1", facecolor="white", edgecolor="none", alpha=0.8))
    clip_texts(ax)
    x = 12 + w + 4
    rows = []
    for f in floors:
        mat = f["spec"]
        if mat["kind"] == "tile":
            how = f"60×60, різ ≥ {cm(min(f['min_cut']))} см; {f['pieces']} шт сітки"
        else:
            how = "дошки вздовж Пн–Пд, розбіжка ⅓"
        rows.append([f["id"], f["zone"].get("name_uk", ""), "плитка" if mat["kind"] == "tile" else "дерево",
                     f"{f['area']:.2f}", how])
    y = table(fig, (x, 60, 283 - x, 138), ["Зона", "Приміщення", "Покриття", "м²", "Укладання"],
              [0.12, 0.33, 0.13, 0.09, 0.33], rows, 6.0)
    caption(fig, x, y - 6, "Матеріали оздоблення — разом по квартирі (підлоги, стіни, фартух)")
    qrows = [[q["name_uk"], f"{q['area']:.2f}", f"{q['waste'] * 100:.0f}%", f"{q['order_area']:.2f}",
              f"{q['order_pieces']}"] for q in fin.quantities(model)]
    y = table(fig, (x, 30, 283 - x, y - 9 - 30), ["Матеріал", "Нетто, м²", "Запас", "Замовити, м²", "шт"],
              [0.52, 0.12, 0.1, 0.15, 0.11], qrows, 5.8)
    ms.notes_block(fig, x, y - 3, [
        "Плитка 60×60 лише у вході й кухні (x ≤ 4,13, y ≥ 8,05); решта відкритого простору й коридор — дерево.",
        "Перехід плитка/дерево по лініях x = 4,13 та y = 8,05: профіль-компенсатор урівень.",
        "Дерево — плаваюче або на клей згідно з вимогами виробника; компенсаційний шов 10 мм по периметру.",
        "Під ванною та піддоном плитку не кладемо (екран ванни — у плитці, піддон урівень з підлогою).",
    ], width=95, size=5.8)
    return fig, finish


def zone_plan_page(model, entry, title, scale, extent, notes, items=None, room_ids=()):
    fig, put, finish = ms.new_page(title, [f"{entry['zone'].get('name_uk', '')}: {entry['area']:.2f} м²"],
                                   f"1:{scale}")
    ax, w, h = scaled_axes(fig, 14, CONTENT[1] + (CONTENT[3] - (extent[3] - extent[1]) * 1000 / scale) / 2,
                           extent, scale)
    draw_plan(ax, model, False, lang="uk", labels=False, north="Пн")
    draw_floor(ax, entry)
    for item in items or []:
        x0, y0, x1, y1 = rv.item_rect(item)
        tiled = item.get("tiled")
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="none" if tiled else "white",
                               edgecolor="#333", lw=0.6 if tiled else 0.5, ls=(0, (3, 2)), zorder=7))
        label = "піддон під плитку,\nлінійний трап" if tiled else "без плитки"
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, f"{item['id']}\n{label}", ha="center", va="center",
                fontsize=5, zorder=8, bbox=dict(facecolor="white", edgecolor="none", pad=0.5) if tiled else None)
    cut_labels(ax, entry, 5 if scale <= 25 else 4.3)
    setting_out_dims(ax, entry, scale)
    clip_texts(ax)
    x = 14 + w + 8
    y = finish_legend(fig, x, 192, model, [entry["material"]])
    t = entry
    rows = [["Площа нетто", f"{t['area']:.2f} м²"],
            ["Плиток у сітці (шт)", f"{t['pieces']} (цілих {t['full']}, різаних {t['cut']})"],
            ["Замовити (+{:.0f}%)".format(t["spec"]["waste"] * 100), f"{t['order_area']:.2f} м², "
             f"{math.ceil(t['pieces'] * (1 + t['spec']['waste']))} шт"],
            ["Мінімальний різ", f"{cm(t['min_cut'][0])} см (X) / {cm(t['min_cut'][1])} см (Y)"]]
    y = table(fig, (x, 30, 283 - x, y - 33), ["Підлога", ""], [0.45, 0.55], rows, 6.0)
    ms.notes_block(fig, x, y - 4, [
        "Червоні лінії «0» — осі укладання: від них шви йдуть кроком 60 см. Розмір до стіни — від чистої стіни.",
        "Сітка розрахована так, щоб найменший різ біля стін був якомога більшим.",
        "Шов 2 мм, плитка шов у шов (без зміщення).",
    ] + notes, width=int((283 - x) / 1.75), size=5.8)
    return fig, finish


def face_projection(model, room_id, face):
    """Fixtures standing against a face: (u0, u1, height, id)."""
    out = []
    (sx, sy), (ex, ey) = face["start"], face["end"]
    for item in model.get("furniture", []):
        if item["room"] != room_id or item.get("polygon") or item["kind"] in ("glass", "shower_floor"):
            continue
        x0, y0, x1, y1 = rv.item_rect(item)
        if abs(sy - ey) < 1e-6 and min(abs(y0 - sy), abs(y1 - sy)) < 0.01:
            us = sorted(fin._along(face, (x, sy))[0] for x in (x0, x1))
        elif abs(sx - ex) < 1e-6 and min(abs(x0 - sx), abs(x1 - sx)) < 0.01:
            us = sorted(fin._along(face, (sx, y))[0] for y in (y0, y1))
        else:
            continue
        u0, u1 = max(us[0], 0.0), min(us[1], face["length"])
        if u1 - u0 > 0.05:
            out.append((u0, u1, item["size"][2], item["id"]))
    return out


def draw_face(ax, entry, scale, label_size=4.6):
    L, H = entry["face"]["length"] if "face" in entry else entry["length"], entry["height"]
    spec = entry["spec"]
    tu, tz = spec["size"]
    frame = Rectangle((0, 0), L, H, transform=ax.transData)
    draw_tiles(ax, entry["region"], (entry["origin"], entry.get("origin_z", 0.0)), spec["size"], spec["colour"], lw=0.3,
               motif=MOTIFS.get(entry["material"]), clip=frame)
    ax.add_patch(Rectangle((0, 0), L, H, fill=False, edgecolor="black", lw=0.8, zorder=6))
    for u0, u1, z0, z1, door in entry.get("openings", []):
        ax.add_patch(Rectangle((u0, z0), u1 - u0, z1 - z0, facecolor="white", edgecolor="black", lw=0.6, zorder=6))
        ax.text((u0 + u1) / 2, z1 / 2, f"{door}\nпроріз", ha="center", va="center", fontsize=label_size, zorder=7)
    # Widths of the bottom-row pieces and heights of the cut rows.
    cells = sorted((c for c in entry["cells"] if c[1] < 1e-6), key=lambda c: c[0])
    for c in cells:
        w = min(c[2], L) - max(c[0], 0)
        if w < tu - 1e-3:
            ax.text((max(c[0], 0) + min(c[2], L)) / 2, min(c[3], H) / 2, cm(w), ha="center", va="center",
                    fontsize=label_size, color="#8a1c1c", weight="bold", zorder=7,
                    rotation=90 if w < 0.12 else 0)
    for z, row in ((H - entry["top_row"] / 2, entry["top_row"]), (entry.get("bottom_row", 0) / 2,
                                                                     entry.get("bottom_row", 0))):
        if row > 1e-3:
            ax.text(L + 0.04, z, f"{cm(row)}", fontsize=label_size, color="#8a1c1c", weight="bold",
                    va="center", zorder=7)
    joints_u = [c[0] for c in cells if c[0] > 1e-6] + [c[2] for c in cells if c[2] < L - 1e-6]
    chain = sorted({0.0, L, *(round(j, 4) for j in joints_u)})
    if len(chain) > 7:
        chain = [0.0, chain[1], chain[-2], L]
    dims(ax, chain, -2 * scale / 1000, scale)
    dims(ax, [0.0, L], -6.5 * scale / 1000, scale)


def elevations_page(model, title, faces, scale, notes, room_id):
    fig, put, finish = ms.new_page(title, [f"розгортка стін, висота облицювання {faces[0]['height']:.2f} м"],
                                   f"1:{scale}")
    k = 1000 / scale
    below = 10 * scale / 1000            # room for the dimension lines, m
    rows, row, width = [], [], 0
    for f in faces:
        fw = f["face"]["length"] * k + 14
        if row and width + fw > CONTENT[2] - 75:
            rows.append(row)
            row, width = [], 0
        row.append(f)
        width += fw
    rows.append(row)
    y = 199
    for row in rows:
        narrow = any(f["face"]["length"] * k < 45 for f in row)
        h_row = (max(f["height"] for f in row) + 0.05 + below) * k
        y -= h_row + (9 if narrow else 5)
        x = 16
        for f in row:
            L = f["face"]["length"]
            ax, w, h = scaled_axes(fig, x, y, (-0.03, -below, L + 0.25, f["height"] + 0.05), scale)
            draw_face(ax, f, scale)
            for u0, u1, hh, item_id in face_projection(model, room_id, f["face"]):
                ax.add_patch(Rectangle((u0, 0), u1 - u0, hh, fill=False, edgecolor="#1f4f8b", lw=0.6,
                                       ls=(0, (3, 2)), zorder=7))
                ax.text((u0 + u1) / 2, hh + 0.03, item_id, ha="center", fontsize=4.6, color="#1f4f8b", zorder=7)
            for t in ax.texts:
                t.set_fontsize(min(t.get_fontsize(), 5.2))
            mat = "декор " if f["material"] != "tile_wall" else ""
            head = f"Стіна {f['index']} — {FACE_NAMES[f['name']]} {mat}({f['face']['length']:.2f} м)"
            if w < 45:
                head = f"Стіна {f['index']}\n{FACE_NAMES[f['name']]} {mat}\n{f['face']['length']:.2f} м"
            fig.text((x + 1) / ms.PAGE[0], (y + h + 1) / ms.PAGE[1], head, fontsize=6.2, weight="bold")
            x += w + 14
    x = CONTENT[0] + CONTENT[2] - 68
    yy = finish_legend(fig, x, 192, model, sorted({f["material"] for f in faces}, key=lambda m: m != "tile_wall"), 40)
    rows = [[f"{f['index']} {f['name']}", f"{f['area']:.2f}", f"{f['pieces']}", cm(f["min_cut"])] for f in faces]
    clad = fin.clad_items(model, room_id)
    rows += [[f"{c['id']} облиц.", f"{c['area']:.2f}", f"{c['pieces']}", ""] for c in clad]
    rows.append(["Разом", f"{sum(f['area'] for f in faces) + sum(c['area'] for c in clad):.2f}",
                 f"{sum(f['pieces'] for f in faces) + sum(c['pieces'] for c in clad)}", ""])
    yy = table(fig, (x, 30, 68, yy - 33), ["Стіна", "м²", "шт", "мін. різ"], [0.3, 0.25, 0.2, 0.25], rows,
               5.8, bold_last=True)
    ms.notes_block(fig, x, yy - 4, [
        "Вигляд зсередини приміщення. Плитка 30×60 лежить горизонтально, шов у шов.",
        "Цілі ряди від стелі вниз, різаний ряд — внизу біля підлоги (рейка-упор під 2-й ряд). "
        "Жоден різ не менше 50 % плитки: якщо залишок менший — ділимо його на верхній і нижній ряди порівну.",
        "Числа внизу — ширина крайніх плиток, справа — висота різаних рядів, см.",
        "Синій пунктир — сантехніка біля стіни (облицювання суцільне, за нею теж).",
    ] + [f"{c['id']} облицювання ({', '.join(f'{n} {l:.2f}×{h:.2f}' for n, l, h in c['sides'])}"
         f"{' + верх' if c['top'] else ''}) — тією ж плиткою." for c in clad] + notes, width=38, size=5.6)
    return fig, finish


def splash_page(model, segments):
    fig, put, finish = ms.new_page("Кухня — фартух з зеленої плитки 8×25", [
        f"висота {segments[0]['base']:.2f}–{segments[0]['top']:.2f} м від підлоги"], "1:20")
    scale, k = 20, 50
    by_id = {s["id"]: s for s in segments}
    order = [[sid for sid in row if sid in by_id] for row in (["SP1", "SP2", "SP3"], ["SP4", "SP5"])]
    order = [row for row in order if row]
    y = 143
    for row in order:
        x = 16
        for sid in row:
            s = by_id[sid]
            H = s["top"] - s["base"]
            ax, w, h = scaled_axes(fig, x, y, (-0.03, -0.25, s["length"] + 0.15, H + 0.05), scale)
            draw_face(ax, {**s, "height": H, "face": {"length": s["length"]}}, scale, 5)
            fig.text((x + 1) / ms.PAGE[0], (y + h + 1.5) / ms.PAGE[1], f"{sid} — {s['length']:.2f} м",
                     fontsize=6.2, weight="bold")
            x += w + 12
            if sid == "SP4":
                fig.text((x - 6) / ms.PAGE[0], (y + h / 2) / ms.PAGE[1], "вікно OB1\n0,90 м\nбез плитки",
                         fontsize=5.5, ha="left", va="center", style="italic")
                x += 22
        y -= 52
    # Key plan.
    ax, w, h = scaled_axes(fig, 16, 31, (0.9, 8.9, 4.5, 13.2), 75)
    draw_plan(ax, model, True, lang="uk", labels=False, north="Пн")
    for item in model.get("furniture", []):
        if item.get("zone") == "kitchen" or item["id"] == "H01":
            ms.draw_item(ax, item, model, 3.5)
    clip_texts(ax)
    for s in segments:
        (ax_, ay), (bx, by) = s["segment"]["from"], s["segment"]["to"]
        ax.plot([ax_, bx], [ay, by], color="#2e6b3f", lw=2.4, zorder=12, solid_capstyle="butt")
        ax.text((ax_ + bx) / 2, (ay + by) / 2, s["id"], fontsize=4.5, color="white", weight="bold",
                ha="center", va="center", zorder=13,
                bbox=dict(boxstyle="round,pad=0.1", facecolor="#2e6b3f", edgecolor="none"))
    fig.text(16 / ms.PAGE[0], (31 + h + 1.5) / ms.PAGE[1], "Схема ділянок фартуха, 1:75", fontsize=6.2, weight="bold")
    rows = [[s["id"], s["segment"]["name_uk"], f"{s['length']:.2f}", f"{len({round(c[0], 3) for c in s['cells']})}",
             f"{s['pieces']}", f"{s['area']:.2f}"] for s in segments]
    total = sum(s["pieces"] for s in segments)
    waste = segments[0]["spec"]["waste"]
    rows.append(["Разом", f"замовити +{waste * 100:.0f}%: {math.ceil(total * (1 + waste))} шт",
                 f"{sum(s['length'] for s in segments):.2f}", "", f"{total}", f"{sum(s['area'] for s in segments):.2f}"])
    x = 16 + w + 10
    yy = table(fig, (x, 31, 140, 52), ["Ділянка", "Місце", "Довжина, м", "Стовпчиків", "шт", "м²"],
               [0.12, 0.38, 0.14, 0.14, 0.09, 0.13], rows, 5.8, bold_last=True)
    ms.notes_block(fig, x + 145, 82, [
        "Плитка 8×25 вертикально, шов у шов: ряди 17,5 + 25 + 17,5 см (залишок 10 см < 50 % ділимо порівну низ/верх).",
        "Крайні стовпчики однакові з обох боків ділянки (числа внизу, см).",
        "Цегляну плитку на цих стінах демонтувати, стіну вирівняти; вище фартуха — фарба.",
        "Цегляна плитка за ТВ (BRICK_EAST) демонтується, стіна — фарба.",
    ], width=33, size=5.6)
    return fig, finish


def pages(model, renders):
    """Page builders (callables returning (fig, finish)) for the finish section."""
    if not model.get("finishes"):
        return []
    floors = {f["id"]: f for f in fin.floors(model)}
    walls = fin.walls(model)
    splash = fin.splash(model)
    items = {i["id"]: i for i in model.get("furniture", [])}
    out = [lambda: floors_page(model, list(floors.values()))]
    if "FL_OPEN" in floors:
        out.append(lambda: zone_plan_page(
            model, floors["FL_OPEN"], "Плитка 60×60 — вхід і кухня", 40,
            (0.85, 7.55, 4.75, 13.2), floors["FL_OPEN"]["zone"].get("notes_uk") or [
                "Під кухонними меблями та шафою H01 плитку кладемо.",
                "Межа плитка/паркет: x = 4,13 (укіс балконних дверей OB2) "
                "та y = 8,05 (вхід у коридор); поріг-профіль в одному рівні."]))
    if splash:
        out.append(lambda: splash_page(model, splash))
    for fid, wid, room, title, extent, hole_items, notes in (
            ("FL_BATH1", "WT_BATH1", 4, "Ванна кімната 1", (0.0, 4.55, 2.75, 8.35), ["B11"],
             ["Південна стіна за ванною — декор 120×60 з бежевими колами, шов по центру стіни."]),
            ("FL_BATH2", "WT_BATH2", 9, "Ванна кімната 2", (5.0, 5.55, 9.35, 7.75), ["B23"],
             ["Східна стіна душу — декор 120×60 «великі листки», одна плитка на ряд, різати до 96 см.",
              "Піддон 90×90 урівень з підлогою; рама 90 з 2 дверцятами по 45 — після облицювання; гідроізоляція до 2,0 м.",
              "Забудова ГКЛ біля душу (до стелі) і короб WC h 1,20 — облицювати тією ж плиткою 30×60."])):
        if fid not in floors:
            continue
        faces = [w for w in walls if w["room"] == room]
        out.append(lambda fid=fid, title=title, extent=extent, hole_items=hole_items: zone_plan_page(
            model, floors[fid], f"{title} — підлога 60×60", 25, extent, [],
            [items[i] for i in hole_items]))
        out.append(lambda faces=faces, title=title, notes=notes, room=room: elevations_page(
            model, f"{title} — плитка на стінах", faces, 40, notes, room))
    return out
