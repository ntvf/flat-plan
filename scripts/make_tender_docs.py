"""Generate the Russian tender documents from the as-is and target models.

    python3 scripts/make_tender_docs.py data/as_is.yaml data/target.yaml exports/tender

Writes:
  plans_as_is_target.pdf - A3 1:50 plans of both states with room dimensions,
                           overall dimension chains, areas and an area table.
  work_list_ru.xlsx      - work list with rough quantities, empty price/sum
                           columns (sum is a formula) and a grand total.

Every quantity is derived from model geometry; the few assumptions that the
model does not yet carry (door height, bathroom ceiling, fixture concept) are
named constants below so they stay visible and traceable.
"""

import math
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Arc, Polygon, Rectangle  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_loader import load_model  # noqa: E402

MM = 1 / 25.4
A3 = (297 * MM, 420 * MM)
SCALE = 50

# Assumptions not (yet) carried by the model.
DOOR_HEIGHT = 2.05            # interior door opening height
BATH2_CEILING = 2.50          # suspended ceiling below the AC line extension at 2.63
WATERPROOF_UPSTAND = 0.20     # floor-to-wall waterproofing upstand
SHOWER = (0.90, 0.90, 2.00)   # shower from the recommended concept, wall WP height
TANK_PIPE_PER_LINE = 3.0      # HW_TANK_100L new wall not modeled yet; rough reroute
# Recommended concept (scripts/sketch_bathroom_layouts.py): basin, WC and
# shower along the south wall of bathroom 2, shower in the SH_san corner.
BATH2_FIXTURE_X = {"basin": 5.26 + 1.02 + 0.275, "wc": 5.26 + 1.78 + 0.20}

WALL = "#4d4d4d"
NEW = "#c0392b"
ROOM_FILL = {"bathroom": "#dcecf5", "storage": "#eeeeee"}


def area(pts):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))


def perimeter(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:] + pts[:1]))


def polyline_length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def room_areas(model):
    by_id = {r["id"]: r for r in model["rooms"]}
    result = {}
    for room in model["rooms"]:
        value = abs(area(room["polygon"]))
        for hole in room.get("subtract", []):
            other = by_id[hole]
            value -= abs(area(other.get("footprint") or other["polygon"]))
        result[room["id"]] = value
    return result


def inside(pt, poly):
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def room_name(room, lang="ru"):
    return room.get(f"name_{lang}") or room["name"]


# --------------------------------------------------------------------- plan


def text_angle(dx, dy):
    angle = math.degrees(math.atan2(dy, dx))
    if angle > 90:
        angle -= 180
    elif angle <= -90:
        angle += 180
    return angle


def draw_opening(ax, item, leaf, door=True):
    x, y = item["at"][:2]
    sx, sy = item["size"][:2]
    vertical = sx < sy
    ax.add_patch(Rectangle((x, y), sx, sy, facecolor="white", edgecolor="none", zorder=4))
    if not door:
        # Window: glazing lines along the wall.
        for f in (0.0, 0.5, 1.0):
            if vertical:
                ax.plot([x + sx * f] * 2, [y, y + sy], color="black", lw=0.5 if f != 0.5 else 0.3, zorder=5)
            else:
                ax.plot([x, x + sx], [y + sy * f] * 2, color="black", lw=0.5 if f != 0.5 else 0.3, zorder=5)
        return
    if vertical:
        ax.plot([x, x + sx], [y, y], color="black", lw=0.4, zorder=5)
        ax.plot([x, x + sx], [y + sy, y + sy], color="black", lw=0.4, zorder=5)
    else:
        ax.plot([x, x], [y, y + sy], color="black", lw=0.4, zorder=5)
        ax.plot([x + sx, x + sx], [y, y + sy], color="black", lw=0.4, zorder=5)
    hinge, side = item.get("swing", ["start", "+"])
    if not leaf:
        style = dict(color="black", lw=0.4, ls=(0, (3, 2)), zorder=5)
        if vertical:
            ax.plot([x + sx / 2] * 2, [y, y + sy], **style)
        else:
            ax.plot([x, x + sx], [y + sy / 2] * 2, **style)
        return
    width = max(sx, sy)
    sgn = 1 if side == "+" else -1
    color = NEW if item.get("renovation_status") == "new" else "black"
    if vertical:
        hx = x + sx if side == "+" else x
        hy = y if hinge == "start" else y + sy
        along = 1 if hinge == "start" else -1
        ax.plot([hx, hx + sgn * width], [hy, hy], color=color, lw=1.0, zorder=6)
        start = 0 if sgn > 0 else 180
        end = 90 * along
        theta = sorted([start, start + (end if sgn > 0 else -end)])
    else:
        hy = y + sy if side == "+" else y
        hx = x if hinge == "start" else x + sx
        along = 1 if hinge == "start" else -1
        ax.plot([hx, hx], [hy, hy + sgn * width], color=color, lw=1.0, zorder=6)
        start = 90 if sgn > 0 else 270
        theta = sorted([start, start - 90 * along * sgn])
    ax.add_patch(Arc((hx, hy), 2 * width, 2 * width, theta1=theta[0], theta2=theta[1],
                     color=color, lw=0.4, zorder=6))


def dim_chain(ax, coords, fixed, horizontal, label_side=1):
    """Dimension chain through `coords` along X (horizontal) or Y."""
    coords = sorted(coords)
    tick = 0.08
    kw = dict(color="black", lw=0.5, zorder=8)
    if horizontal:
        ax.plot([coords[0], coords[-1]], [fixed, fixed], **kw)
    else:
        ax.plot([fixed, fixed], [coords[0], coords[-1]], **kw)
    for c in coords:
        if horizontal:
            ax.plot([c - tick, c + tick], [fixed - tick, fixed + tick], **kw)
            ax.plot([c, c], [fixed - 0.15, fixed + 0.15], **kw)
        else:
            ax.plot([fixed - tick, fixed + tick], [c - tick, c + tick], **kw)
            ax.plot([fixed - 0.15, fixed + 0.15], [c, c], **kw)
    for a, b in zip(coords, coords[1:]):
        mid, text = (a + b) / 2, f"{b - a:.2f}"
        if horizontal:
            ax.text(mid, fixed + 0.12 * label_side, text, ha="center",
                    va="bottom" if label_side > 0 else "top", fontsize=7, zorder=8)
        else:
            ax.text(fixed - 0.12 * label_side, mid, text, ha="center",
                    va="bottom" if label_side > 0 else "top", rotation=90, fontsize=7, zorder=8)


def draw_plan(ax, model, highlight_new, lang="ru", labels=True, north="С"):
    areas = room_areas(model)
    outline = model["outline"]
    ax.add_patch(Polygon(outline, closed=True, facecolor=WALL, edgecolor="black", lw=0.8, zorder=1))

    holes = {h for r in model["rooms"] for h in r.get("subtract", [])}
    order = [r for r in model["rooms"] if r["id"] not in holes] + \
            [r for r in model["rooms"] if r["id"] in holes]
    for room in order:
        is_new = highlight_new and room.get("renovation_status") == "new"
        if room.get("footprint"):
            ax.add_patch(Polygon(room["footprint"], closed=True, facecolor=WALL, edgecolor="none", zorder=2))
        fill = "#fde2dc" if is_new else ROOM_FILL.get(room["function"], "white")
        ax.add_patch(Polygon(room["polygon"], closed=True, facecolor=fill, edgecolor="black", lw=0.3, zorder=2))

    for wall in model.get("walls", []):
        is_new = highlight_new and wall.get("renovation_status") == "new"
        ax.add_patch(Rectangle(wall["at"], *wall["size"], zorder=3,
                               facecolor=NEW if is_new else WALL,
                               edgecolor="black", lw=0.3, hatch="////" if is_new else None))
    for col in model.get("columns", []):
        ax.add_patch(Rectangle(col["at"], *col["size"], facecolor="black", zorder=3))
    for shaft in model.get("shafts", []):
        ax.add_patch(Rectangle(shaft["at"], *shaft["size"], facecolor="white", edgecolor="black",
                               lw=0.5, hatch="xxxx", zorder=3))
        label = "ВЕНТ" if "vent" in shaft["id"] else "КАН"
        ax.text(shaft["at"][0] + shaft["size"][0] / 2, shaft["at"][1] + shaft["size"][1] / 2, label,
                rotation=90, ha="center", va="center", fontsize=5, zorder=9,
                bbox=dict(facecolor="white", edgecolor="none", pad=0.3))

    for win in model.get("windows", []):
        draw_opening(ax, win, leaf=False, door=win.get("ifc_class") == "IfcDoor")
    for door in model.get("doors", []):
        draw_opening(ax, door, leaf=door.get("has_leaf", True))

    # Clear dimension of every room edge, placed just inside the room. Edges
    # buried under a subtracted room (e.g. the new bathroom) are skipped.
    by_id = {r["id"]: r for r in model["rooms"]}
    for room in model["rooms"]:
        poly = room["polygon"]
        ccw = area(poly) > 0
        hidden = [by_id[h].get("footprint") or by_id[h]["polygon"] for h in room.get("subtract", [])]
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            length = math.hypot(x2 - x1, y2 - y1)
            mid = ((x1 + x2) / 2, (y1 + y2) / 2)
            if length < 0.30 or any(inside(mid, h) for h in hidden):
                continue
            nx, ny = (-(y2 - y1), x2 - x1) if ccw else (y2 - y1, -(x2 - x1))
            nx, ny = nx / length, ny / length
            off = 0.13
            ax.text((x1 + x2) / 2 + nx * off, (y1 + y2) / 2 + ny * off, f"{length:.2f}",
                    rotation=text_angle(x2 - x1, y2 - y1), ha="center", va="center",
                    fontsize=5.5 if length >= 0.6 else 4.5, color="#1a4f8b", zorder=9)

    for room in model["rooms"] if labels else []:
        poly = room["polygon"]
        lx, ly = room.get("label_at") or (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))
        if room["id"] == 123 and not room.get("label_at"):
            lx, ly = 5.4, 10.4
        lines = [f"{room['id']}. {room_name(room, lang)}", f"S = {areas[room['id']]:.2f} м²"]
        if room.get("clear"):
            lines.append(f"{room['clear'][0]:.2f} × {room['clear'][1]:.2f}")
        is_new = highlight_new and room.get("renovation_status") == "new"
        ax.text(lx, ly, "\n".join(lines), ha="center", va="center", fontsize=7, zorder=10,
                color=NEW if is_new else "black", linespacing=1.3,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1.0))

    xs = sorted({p[0] for p in outline})
    ys = sorted({p[1] for p in outline})
    dim_chain(ax, [0.0, 6.09, 9.43], -0.75, True, -1)
    dim_chain(ax, [xs[0], xs[-1]], -1.15, True, -1)
    dim_chain(ax, [1.00, 2.35, 9.43], max(ys) + 0.5, True)
    dim_chain(ax, [0.0, 8.28, 12.38, 13.29], -0.5, False)
    dim_chain(ax, [ys[0], ys[-1]], -0.95, False)
    dim_chain(ax, [0.94, 13.29], 9.43 + 0.5, False, -1)

    # North arrow.
    ax.annotate("", xy=(10.4, 14.25), xytext=(10.4, 13.55),
                arrowprops=dict(arrowstyle="-|>", color="black", lw=1.0))
    ax.text(10.4, 14.35, north, ha="center", va="bottom", fontsize=9, weight="bold")
    return areas


def plan_page(pdf, model, title, sheet, highlight_new):
    fig = plt.figure(figsize=A3)
    xlim, ylim = (-1.6, 10.9), (-1.6, 14.8)
    w_mm = (xlim[1] - xlim[0]) * 1000 / SCALE
    h_mm = (ylim[1] - ylim[0]) * 1000 / SCALE
    left = (297 - w_mm) / 2
    ax = fig.add_axes([left / 297, 82 / 420, w_mm / 297, h_mm / 420])
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.axis("off")
    areas = draw_plan(ax, model, highlight_new)
    total = sum(areas.values())

    # Legend and title block.
    fig.add_artist(Rectangle((10 * MM / A3[0], 10 * MM / A3[1]), 277 / 297, 400 / 420,
                             transform=fig.transFigure, fill=False, lw=1.0))
    tb_y = 12
    fig.add_artist(Rectangle((10 / 297, tb_y / 420), 277 / 297, 48 / 420,
                             transform=fig.transFigure, fill=False, lw=0.8))
    put = lambda x, y, s, **kw: fig.text(x / 297, y / 420, s, **kw)  # noqa: E731
    put(15, tb_y + 38, "Ремонт квартиры, Варшава", fontsize=10)
    put(15, tb_y + 26, title, fontsize=14, weight="bold")
    put(15, tb_y + 16, "Масштаб 1:50 (A3). Размеры в метрах, в чистоте стен (без отделки).", fontsize=8)
    put(15, tb_y + 10, f"Общая площадь помещений: {total:.2f} м²   ·   высота потолка "
        f"{model['meta'].get('ceiling_height', 2.7):.2f} м", fontsize=8)
    put(15, tb_y + 4, "Размеры и сети проверить на объекте до начала работ.", fontsize=7, style="italic")
    put(255, tb_y + 38, f"Лист {sheet}", fontsize=10, weight="bold")
    put(255, tb_y + 30, date.today().isoformat(), fontsize=8)

    legend = [("white", "black", None, "помещение / размер стены в чистоте (синим)"),
              (WALL, "black", None, "существующие стены"),
              ("white", "black", "xxxx", "вентиляционная / канализационная шахта")]
    if highlight_new:
        legend += [(NEW, "black", "////", "новые перегородки (ГКЛ)"),
                   ("#fde2dc", "black", None, "новое помещение")]
    for i, (fc, ec, hatch, text) in enumerate(legend):
        y = tb_y + 39 - i * 5.5
        fig.add_artist(Rectangle((160 / 297, y / 420), 7 / 297, 3.5 / 420, transform=fig.transFigure,
                                 facecolor=fc, edgecolor=ec, hatch=hatch, lw=0.4))
        put(170, y + 0.5, text, fontsize=7)
    pdf.savefig(fig)
    plt.close(fig)
    return areas


def area_table_page(pdf, as_is, target, a_areas, t_areas):
    fig = plt.figure(figsize=A3)
    fig.add_artist(Rectangle((10 / 297, 10 / 420), 277 / 297, 400 / 420,
                             transform=fig.transFigure, fill=False, lw=1.0))
    fig.text(20 / 297, 395 / 420, "ЭКСПЛИКАЦИЯ ПОМЕЩЕНИЙ", fontsize=16, weight="bold")
    fig.text(20 / 297, 387 / 420, "Площади рассчитаны по геометрии модели (в чистоте стен), м²", fontsize=9)
    rooms = {r["id"]: r for r in as_is["rooms"]}
    rooms.update({r["id"]: r for r in target["rooms"]})
    rows = []
    for rid, room in rooms.items():
        a, t = a_areas.get(rid), t_areas.get(rid)
        dims = f"{room['clear'][0]:.2f} × {room['clear'][1]:.2f}" if room.get("clear") else "—"
        rows.append([str(rid), room_name(room), dims,
                     f"{a:.2f}" if a is not None else "—",
                     f"{t:.2f}" if t is not None else "—",
                     f"{(t or 0) - (a or 0):+.2f}"])
    ta, tt = sum(a_areas.values()), sum(t_areas.values())
    rows.append(["", "ИТОГО", "", f"{ta:.2f}", f"{tt:.2f}", f"{tt - ta:+.2f}"])
    ax = fig.add_axes([20 / 297, 230 / 420, 257 / 297, 150 / 420])
    ax.axis("off")
    table = ax.table(cellText=rows, loc="upper center", cellLoc="center",
                     colLabels=["№", "Помещение", "Размеры, м", "Существующее", "Проектное", "Изменение"],
                     colWidths=[0.06, 0.40, 0.16, 0.13, 0.13, 0.12])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.8)
    for (r, c), cell in table.get_celld().items():
        if r == 0 or r == len(rows):
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#e8e8e8")
        if c == 1 and r > 0:
            cell.set_text_props(ha="left")
    notes = [
        "Примечания:",
        "• Новая ванная 2 (4.87 м²) устраивается в части открытой зоны восточнее кладовой,",
        "  между перегородкой 2.58 м и вентиляционной шахтой; дверь 0.80 м открывается в коридор.",
        "• Площадь холла/кухни/гостиной уменьшается на площадь ванной 2 вместе с новыми перегородками.",
        "• Кондиционер переносится на северную стену ванной 2 (сторона гостиной).",
        "• В существующие проёмы D4–D8 устанавливаются дверные полотна.",
        "• Площадь балкона (4.26 м²) в итог не включена.",
    ]
    fig.text(20 / 297, 300 / 420, "\n".join(notes), fontsize=9, va="top", linespacing=1.6)
    pdf.savefig(fig)
    plt.close(fig)


# --------------------------------------------------------------- quantities


def work_items(as_is, target):
    t_rooms = {r["id"]: r for r in target["rooms"]}
    bath = t_rooms[9]
    a9, p9 = abs(area(bath["polygon"])), perimeter(bath["polygon"])
    h = target["meta"].get("ceiling_height", 2.70)
    doors = {d["id"]: d for d in target["doors"]}
    d9 = doors["D9"]
    d9_w = max(d9["size"])
    new_walls = [w for w in target["walls"] if w.get("renovation_status") == "new"]
    bath_walls = [w for w in new_walls if w["id"].startswith("W_bath2_")]
    kitchen_walls = [w for w in new_walls if w not in bath_walls]
    wall_len = sum(max(w["size"]) for w in bath_walls)
    kitchen_partition = sum(max(w["size"]) for w in kitchen_walls) * h
    partition = wall_len * h - d9_w * DOOR_HEIGHT
    tiles_wall = p9 * BATH2_CEILING - d9_w * DOOR_HEIGHT
    wp = a9 + p9 * WATERPROOF_UPSTAND + (SHOWER[0] + SHOWER[1]) * SHOWER[2]
    paint_outside = partition  # outer faces of the new partitions
    leafs = [d for d in target["doors"] if d.get("has_leaf") and d["id"] != "entry"
             and d.get("renovation_status") != "new"]
    routes = {r["id"]: r for r in target["service_routes"]}
    ac_ext = polyline_length(routes["AC_living_extension_bath_ceiling"]["points"])
    shafts = {s["id"]: s for s in target["shafts"]}
    san = shafts["SH_san"]
    san_c = (san["at"][0], san["at"][1] + san["size"][1] / 2)
    ac = next(e for e in target["equipment"] if e["id"] == "AC_living")
    tank = next(e for e in as_is["equipment"] if e["id"] == "HW_TANK_100L")
    condensate = abs(ac["at"][0] - san_c[0]) + abs(ac["at"][1] - san_c[1])
    d110 = san_c[0] - BATH2_FIXTURE_X["wc"] + 0.5
    d50 = san_c[0] - BATH2_FIXTURE_X["basin"] + 0.5
    terms = {t["id"]: t for t in target["service_terminals"]}
    src = terms["B4_BASIN_CONNECTION"]["at"]
    water_line = abs(d9["at"][0] - src[0]) + abs(d9["at"][1] - src[1]) + (san_c[0] - BATH2_FIXTURE_X["basin"])
    corridor_strip = d9["at"][0] - 2.42  # corridor floor between bathroom 1 and 2
    open_living = room_areas(target)[123]
    r = lambda v, step=0.5: math.ceil(v / step) * step  # noqa: E731

    return [
        ("Подготовительные и демонтажные работы", [
            ("Защита существующих полов, окон и мебели плёнкой/картоном", "м²", r(open_living, 1),
             "площадь холла/кухни/гостиной"),
            ("Защита кабины лифта (пол, стены, двери) на время работ", "компл", 1,
             "по требованиям администрации дома"),
            ("Демонтаж напольного покрытия в зоне новой ванной", "м²", r(a9), "площадь ванной 2"),
            ("Вскрытие стяжки 50 мм и утеплителя 50 мм в зоне ванной 2 под канализацию", "м²", r(a9),
             "FLOOR_EXISTING"),
            ("Штробление стяжки в коридоре под трубы ХВС/ГВС с последующим восстановлением", "м.п.",
             r(corridor_strip), "от ванной 1 до ванной 2"),
            ("Демонтаж внутреннего блока кондиционера", "шт", 1, "AC_living"),
            ("Вынос строительного мусора и утилизация", "компл", 1, ""),
            ("Аренда контейнера для строительного мусора с вывозом", "шт", 1,
             "объём уточнить; место установки согласовать"),
        ]),
        ("Перегородки и потолки", [
            ("Монтаж перегородки из влагостойкого ГКЛ на металлокаркасе с минватой, 2×12.5 мм с каждой стороны",
             "м²", r(partition), f"W_bath2_n + W_bath2_door, h={h:.2f} м, за вычетом проёма"),
            ("Усиление каркаса и закладная (фанера/OSB 18 мм) под кондиционер", "шт", 1, "W_bath2_n"),
            ("Монтаж перегородки из ГКЛ на металлокаркасе с минватой, 2×12.5 мм с каждой стороны",
             "м²", r(kitchen_partition), " + ".join(w["id"] for w in kitchen_walls) + f", h={h:.2f} м"),
            ("Устройство дверного проёма с усиленным профилем", "шт", 1, f"D9, {d9_w:.2f} м"),
            ("Подвесной потолок из влагостойкого ГКЛ с ревизионным люком", "м²", r(a9),
             f"h={BATH2_CEILING:.2f} м, над потолком трасса кондиционера"),
        ]),
        ("Сантехника и канализация (ванная 2)", [
            ("Прокладка канализации ПП Ø110 мм (унитаз) с уклоном к стояку", "м.п.", r(d110),
             "к шахте SH_san"),
            ("Прокладка канализации ПП Ø50 мм (умывальник, душ) с уклоном", "м.п.", r(d50), "к шахте SH_san"),
            ("Врезка в канализационный стояк (тройник)", "шт", 1, "SH_san; согласовать с администрацией"),
            ("Прокладка труб ХВС и ГВС (PEX/PP) в изоляции", "м.п.", r(2 * water_line, 1),
             "от точки умывальника ванной 1, 2 линии"),
            ("Установка коллектора / запорной арматуры", "шт", 2, "ХВС + ГВС"),
            ("Монтаж водорозеток и выводов под приборы", "точка", 6, "умывальник, унитаз, душ × ХВС/ГВС"),
            ("Установка подвесного унитаза на инсталляции в коробе ГКЛ h 1,20", "шт", 1, "короб до SH_san, в душе — полка"),
            ("Установка подвесного умывальника на стене и смесителя", "шт", 1, "подводка в штробе"),
            ("Устройство душа: встроенный поддон 90×90 вровень с полом, смеситель, рама 90 с 2 дверцами по 45", "компл", 1,
             "у SH_san"),
        ]),
        ("Перенос водонагревателя (кухня)", [
            (f"Демонтаж бойлера {tank['name'].split()[-2]} л с отключением и сливом", "шт", 1, tank["id"]),
            ("Перенос подводки ХВС/ГВС к новому месту установки", "м.п.", r(2 * TANK_PIPE_PER_LINE, 1),
             "2 линии; новое место уточнить"),
            ("Установка бойлера на новой стене, подключение, опрессовка", "шт", 1,
             f"напольный, Ø{tank['size'][0]:.2f} м, h={tank['size'][2]:.2f} м"),
            ("Перенос электропитания / подключения к котлу (при необходимости)", "компл", 1, "уточнить на объекте"),
            ("Заделка отверстий и ремонт стены на старом месте", "шт", 1, "стена у входа"),
        ]),
        ("Вентиляция", [
            ("Устройство отверстия и подключение к вентиляционной шахте", "шт", 1,
             "SH_vent; согласовать с администрацией"),
            ("Монтаж канального/бытового вентилятора с обратным клапаном", "шт", 1, ""),
            ("Прокладка воздуховода над подвесным потолком", "м.п.", 1.5, "до SH_vent"),
        ]),
        ("Кондиционер", [
            ("Удлинение фреоновых трасс и кабеля управления (пайка, изоляция)", "м.п.", r(ac_ext),
             "AC_living_extension_bath_ceiling"),
            ("Прокладка отдельного дренажа конденсата к стояку", "м.п.", r(condensate), "до SH_san"),
            ("Монтаж внутреннего блока на новом месте, вакуумирование, проверка", "шт", 1,
             "W_bath2_n, сторона гостиной"),
            ("Заделка и выравнивание стены после снятия кондиционера", "шт", 1, "W_258"),
        ]),
        ("Электромонтажные работы", [
            ("Прокладка отдельной линии от щита в ванную 2 с УЗО 30 мА", "компл", 1, "трасса ориент."),
            ("Установка светильников (потолок, IP44)", "точка", 2, ""),
            ("Установка выключателя", "шт", 1, "у двери D9 снаружи"),
            ("Установка розетки IP44 у умывальника", "шт", 1, ""),
            ("Подключение вентилятора (с таймером/от света)", "шт", 1, ""),
            ("Система уравнивания потенциалов", "компл", 1, ""),
        ]),
        ("Гидроизоляция, стяжка, плитка (ванная 2)", [
            ("Устройство стяжки с уклоном к трапу после прокладки канализации", "м²", r(a9), ""),
            ("Обмазочная гидроизоляция пола и стен с лентой в углах", "м²", r(wp),
             f"пол + {WATERPROOF_UPSTAND:.2f} м по периметру + стены душа"),
            ("Укладка напольной плитки", "м²", r(a9), ""),
            ("Облицовка стен плиткой до потолка", "м²", r(tiles_wall),
             f"периметр {p9:.2f} м × {BATH2_CEILING:.2f} м за вычетом двери"),
            ("Затирка швов, силиконовые швы, уголки", "м²", r(a9 + tiles_wall, 1), ""),
        ]),
        ("Двери", [
            ("Установка дверного блока 0.80 м в ванную 2 (с порогом/вентрешёткой)", "шт", 1, "D9"),
            *[(f"Установка межкомнатного дверного блока {w:.2f} м в существующий проём", "шт",
               sum(1 for d in leafs if max(d["size"]) == w),
               ", ".join(d["id"] for d in leafs if max(d["size"]) == w) + "; ширину проверить")
              for w in sorted({max(d["size"]) for d in leafs})],
        ]),
        ("Отделочные работы", [
            ("Шпаклёвка и покраска новых перегородок со стороны гостиной/коридора", "м²", r(paint_outside),
             "наружные стороны W_bath2_n, W_bath2_door"),
            ("Покраска потолка ванной 2 влагостойкой краской", "м²", r(a9), ""),
            ("Восстановление напольного покрытия в коридоре после штробления", "м.п.", r(corridor_strip), ""),
            ("Финальная уборка", "м²", r(sum(room_areas(target).values()), 1), "вся квартира"),
        ]),
    ]


def write_xlsx(path, as_is, target, a_areas, t_areas):
    wb = Workbook()
    ws = wb.active
    ws.title = "Ведомость работ"
    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="D9D9D9")
    sect_fill = PatternFill("solid", fgColor="EDF3F8")
    wrap = Alignment(wrap_text=True, vertical="center")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws["A1"] = "Ведомость работ: устройство второй ванной комнаты, квартира в Варшаве"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = ("Количества ориентировочные, рассчитаны по модели квартиры (data/as_is.yaml, data/target.yaml). "
                f"Дата: {date.today().isoformat()}. Подрядчик заполняет цены; суммы считаются автоматически.")
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.merge_cells("A1:G1")
    ws.merge_cells("A2:G2")
    ws.row_dimensions[2].height = 30

    headers = ["№", "Наименование работ", "Ед. изм.", "Кол-во (ориент.)", "Цена за ед., PLN",
               "Сумма, PLN", "Примечание / источник"]
    ws.append([])
    ws.append(headers)
    hr = ws.max_row
    for c in range(1, 8):
        cell = ws.cell(hr, c)
        cell.font, cell.fill, cell.alignment, cell.border = bold, head_fill, center, border

    first = None
    for s_no, (section, items) in enumerate(work_items(as_is, target), 1):
        ws.append([f"{s_no}.", section])
        row = ws.max_row
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)
        for c in range(1, 8):
            ws.cell(row, c).fill, ws.cell(row, c).border = sect_fill, border
            ws.cell(row, c).font = bold
        for i_no, (name, unit, qty, note) in enumerate(items, 1):
            ws.append([f"{s_no}.{i_no}", name, unit, qty, None, None, note])
            row = ws.max_row
            first = first or row
            ws.cell(row, 6).value = f'=IF(E{row}="","",D{row}*E{row})'
            for c in range(1, 8):
                cell = ws.cell(row, c)
                cell.border = border
                cell.alignment = center if c in (1, 3, 4) else wrap
            ws.cell(row, 4).number_format = "0.0#"
            ws.cell(row, 5).number_format = "#,##0.00"
            ws.cell(row, 6).number_format = "#,##0.00"
    last = ws.max_row
    ws.append(["", "ИТОГО", "", "", "", f"=SUM(F{first}:F{last})", ""])
    tr = ws.max_row
    for c in range(1, 8):
        cell = ws.cell(tr, c)
        cell.font, cell.fill, cell.border = Font(bold=True, size=12), head_fill, border
    ws.cell(tr, 6).number_format = "#,##0.00"

    for col, width in zip("ABCDEFG", (6, 62, 9, 12, 14, 15, 42)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = ws.cell(hr + 1, 1)
    ws.print_title_rows = f"{hr}:{hr}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    ws2 = wb.create_sheet("Площади")
    ws2.append(["№", "Помещение", "Существующее, м²", "Проектное, м²", "Изменение, м²"])
    rooms = {r["id"]: r for r in as_is["rooms"]}
    rooms.update({r["id"]: r for r in target["rooms"]})
    for rid, room in rooms.items():
        a, t = a_areas.get(rid), t_areas.get(rid)
        ws2.append([rid, room_name(room), round(a, 2) if a is not None else None,
                    round(t, 2) if t is not None else None])
        ws2.cell(ws2.max_row, 5).value = f"=N(D{ws2.max_row})-N(C{ws2.max_row})"
    n = ws2.max_row
    ws2.append(["", "ИТОГО", f"=SUM(C2:C{n})", f"=SUM(D2:D{n})", f"=SUM(E2:E{n})"])
    for row in ws2.iter_rows():
        for cell in row:
            cell.border = border
            if cell.column > 2:
                cell.number_format = "0.00"
    for c in range(1, 6):
        ws2.cell(1, c).font = ws2.cell(n + 1, c).font = bold
        ws2.cell(1, c).fill = head_fill
    for col, width in zip("ABCDE", (6, 40, 18, 16, 16)):
        ws2.column_dimensions[col].width = width
    wb.save(path)


def main(as_is_path, target_path, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    as_is, target = load_model(as_is_path), load_model(target_path)
    pdf_path = out / "plans_as_is_target.pdf"
    with PdfPages(pdf_path) as pdf:
        a_areas = plan_page(pdf, as_is, "ПЛАН — СУЩЕСТВУЮЩЕЕ СОСТОЯНИЕ", "1", False)
        t_areas = plan_page(pdf, target, "ПЛАН — ПРОЕКТНОЕ СОСТОЯНИЕ", "2", True)
        area_table_page(pdf, as_is, target, a_areas, t_areas)
        meta = pdf.infodict()
        meta["Title"] = "План квартиры: существующее и проектное состояние"
    xlsx_path = out / "work_list_ru.xlsx"
    write_xlsx(xlsx_path, as_is, target, a_areas, t_areas)
    print(f"wrote {pdf_path}\nwrote {xlsx_path}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
