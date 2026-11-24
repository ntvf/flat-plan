"""Floor and wall finishes: tile setting-out and quantities.

Reads the `finishes` section of the resolved model (data/target.yaml) and
derives every zone from room geometry, so areas and piece counts are
traceable to the model. Pure Python: also imported by Blender.

    python3 scripts/finishes.py data/target.yaml     # print quantities
"""

import math

STEP = 0.005          # setting-out search step, m
MIN_EDGE = 0.5        # only edges at least this long drive the setting-out
TINY = 1e-4           # grid cells with less tile than this (m²) are not counted


# ------------------------------------------------------------------ geometry

def signed_area(poly):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1])) / 2


def rect_poly(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _crossings(poly, x):
    ys = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        (ax, ay), (bx, by) = a, b
        if (ax <= x < bx) or (bx <= x < ax):
            ys.append(ay + (x - ax) * (by - ay) / (bx - ax))
    ys.sort()
    return [(ys[i], ys[i + 1]) for i in range(0, len(ys) - 1, 2)]


def _union(intervals):
    out = []
    for lo, hi in sorted(intervals):
        if out and lo <= out[-1][1] + 1e-12:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def _subtract(base, cuts):
    out = []
    for lo, hi in base:
        pieces = [(lo, hi)]
        for c0, c1 in cuts:
            nxt = []
            for p0, p1 in pieces:
                if c1 <= p0 or c0 >= p1:
                    nxt.append((p0, p1))
                    continue
                if c0 > p0:
                    nxt.append((p0, c0))
                if c1 < p1:
                    nxt.append((c1, p1))
            pieces = nxt
        out.extend(pieces)
    return out


class Region:
    """Inside any `outer` polygon, inside `within` (x0, y0, x1, y1) if given,
    and outside every `holes` polygon. Areas are exact for polygons whose
    edges do not cross each other inside a slab."""

    def __init__(self, outer, holes=(), within=None):
        self.outer = [[tuple(p) for p in poly] for poly in outer]
        self.holes = [[tuple(p) for p in poly] for poly in holes]
        self.within = within

    def polygons(self):
        return self.outer + self.holes + ([rect_poly(*self.within)] if self.within else [])

    def bbox(self):
        xs = [p[0] for poly in self.outer for p in poly]
        ys = [p[1] for poly in self.outer for p in poly]
        box = [min(xs), min(ys), max(xs), max(ys)]
        if self.within:
            box = [max(box[0], self.within[0]), max(box[1], self.within[1]),
                   min(box[2], self.within[2]), min(box[3], self.within[3])]
        return tuple(box)

    def intervals(self, x):
        if self.within and not (self.within[0] <= x < self.within[2]):
            return []
        inside = _union([iv for poly in self.outer for iv in _crossings(poly, x)])
        if self.within:
            inside = [(max(a, self.within[1]), min(b, self.within[3])) for a, b in inside]
            inside = [(a, b) for a, b in inside if b > a]
        holes = _union([iv for poly in self.holes for iv in _crossings(poly, x)])
        return _subtract(inside, holes)

    def contains(self, x, y):
        return any(a <= y < b for a, b in self.intervals(x))

    def _breaks(self, x0, y0, x1, y1):
        xs = {x0, x1}
        for poly in self.polygons():
            for a, b in zip(poly, poly[1:] + poly[:1]):
                if x0 < a[0] < x1:
                    xs.add(a[0])
                if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9:
                    for yy in (y0, y1):
                        t = (yy - a[1]) / (b[1] - a[1])
                        if 0 < t < 1:
                            xx = a[0] + t * (b[0] - a[0])
                            if x0 < xx < x1:
                                xs.add(xx)
        return sorted(xs)

    def area_in(self, x0, y0, x1, y1):
        xs = self._breaks(x0, y0, x1, y1)
        total = 0.0
        for a, b in zip(xs, xs[1:]):
            for lo, hi in self.intervals((a + b) / 2):
                lo, hi = max(lo, y0), min(hi, y1)
                if hi > lo:
                    total += (b - a) * (hi - lo)
        return total

    def area(self):
        return self.area_in(*self.bbox())

    def trapezoids(self, x0, y0, x1, y1):
        """Exact pieces of the region inside a rectangle, for drawing/meshing."""
        out = []
        xs = self._breaks(x0, y0, x1, y1)
        for a, b in zip(xs, xs[1:]):
            if b - a < 1e-9:
                continue
            e = min(1e-7, (b - a) / 4)
            mid = self.intervals((a + b) / 2)
            left, right = self.intervals(a + e), self.intervals(b - e)
            if not len(left) == len(right) == len(mid):
                left = right = mid
            for (p0, p1), (q0, q1) in zip(left, right):
                p0, p1, q0, q1 = max(p0, y0), min(p1, y1), max(q0, y0), min(q1, y1)
                if p1 - p0 <= 1e-9 and q1 - q0 <= 1e-9:
                    continue
                out.append([(a, p0), (b, q0), (b, max(q0, q1)), (a, max(p0, p1))])
        return out

    def transposed(self):
        swap = lambda poly: [(p[1], p[0]) for p in poly]  # noqa: E731
        w = self.within
        return Region([swap(p) for p in self.outer], [swap(p) for p in self.holes],
                      (w[1], w[0], w[3], w[2]) if w else None)

    def boundary_edges(self, axis, min_len=MIN_EDGE, sample=0.05):
        """Axis-aligned boundary edges perpendicular to `axis` (0: x, 1: y).

        Returns (coordinate, inside_sign, boundary_length, along_position)."""
        found = {}
        for poly in self.polygons():
            for a, b in zip(poly, poly[1:] + poly[:1]):
                if abs(a[axis] - b[axis]) > 1e-9:
                    continue
                c = a[axis]
                lo, hi = sorted((a[1 - axis], b[1 - axis]))
                n = max(1, int((hi - lo) / sample))
                for k in range(n):
                    t = lo + (k + 0.5) * (hi - lo) / n
                    pt = lambda d: (c + d, t) if axis == 0 else (t, c + d)  # noqa: E731
                    plus, minus = self.contains(*pt(1e-4)), self.contains(*pt(-1e-4))
                    if plus != minus:
                        entry = found.setdefault((round(c, 4), 1 if plus else -1), [0.0, []])
                        entry[0] += (hi - lo) / n
                        entry[1].append(t)
        return [(c, s, length, sorted(ts)[len(ts) // 2])
                for (c, s), (length, ts) in found.items() if length >= min_len - 1e-6]


# ------------------------------------------------------------------ setting-out

def first_piece(origin, edge, sign, period):
    """Width of the tile cut against `edge` when joints sit at origin + k*period."""
    piece = ((origin - edge) if sign > 0 else (edge - origin)) % period
    return period if piece < 1e-6 or period - piece < 1e-6 else piece


def best_origin(edges, period, step=STEP):
    """Joint offset for (coord, sign, weight, ...) edges.

    Cuts at full-weight edges (wall ends) come first and count as good once
    they reach half a tile; then the smallest cut overall is maximised, then
    the weighted mean."""
    if not edges:
        return 0.0
    best, best_key = 0.0, None
    primary = [k for k, e in enumerate(edges) if e[2] >= 1.0] or list(range(len(edges)))
    for k in range(int(round(period / step))):
        o = k * step
        pieces = [first_piece(o, e[0], e[1], period) for e in edges]
        weight = sum(e[2] for e in edges)
        key = (round(min(min(pieces[i] for i in primary), period / 2), 4), round(min(pieces), 4),
               sum(p * e[2] for p, e in zip(pieces, edges)) / weight)
        if best_key is None or key > best_key:
            best, best_key = o, key
    return round(best, 4)


def grid_cells(region, origin, size):
    """Tile grid cells (x0, y0, x1, y1, area) that hold tile in `region`."""
    x0, y0, x1, y1 = region.bbox()
    (ox, oy), (tx, ty) = origin, size
    i0, i1 = math.floor((x0 - ox) / tx + 1e-9), math.ceil((x1 - ox) / tx - 1e-9)
    j0, j1 = math.floor((y0 - oy) / ty + 1e-9), math.ceil((y1 - oy) / ty - 1e-9)
    cells = []
    for i in range(i0, i1):
        for j in range(j0, j1):
            cx0, cy0 = ox + i * tx, oy + j * ty
            a = region.area_in(cx0, cy0, cx0 + tx, cy0 + ty)
            if a > TINY:
                cells.append((cx0, cy0, cx0 + tx, cy0 + ty, a))
    return cells


def summarise(cells, size):
    full_area = size[0] * size[1]
    full = sum(1 for c in cells if c[4] > full_area - 1e-4)
    return {"area": sum(c[4] for c in cells), "pieces": len(cells), "full": full, "cut": len(cells) - full}


def min_cut(edges, origin, period):
    return min((first_piece(origin, e[0], e[1], period) for e in edges), default=period)


# ------------------------------------------------------------------ model zones

def _room(model, room_id):
    return next(r for r in model["rooms"] if r["id"] == room_id)


def _rect_of(entry):
    x, y = entry["at"]
    w, d = entry["size"][:2]
    return rect_poly(x, y, x + w, y + d)


def room_region(model, room_id):
    """Room floor: polygon minus subtracted rooms and solid walls/columns/shafts inside it."""
    room = _room(model, room_id)
    holes = [_room(model, h).get("footprint") or _room(model, h)["polygon"] for h in room.get("subtract", [])]
    base = Region([room["polygon"]], holes)
    for section in ("walls", "columns", "shafts"):
        for entry in model.get(section, []):
            if "at" not in entry or "size" not in entry:
                continue
            poly = _rect_of(entry)
            cx = sum(p[0] for p in poly) / 4
            cy = sum(p[1] for p in poly) / 4
            if base.contains(cx, cy):
                holes.append(poly)
    return Region([room["polygon"]], holes)


def _item_rect(item):
    x, y = item["at"]
    w, d = item["size"][:2]
    return rect_poly(x, y, x + w, y + d)


def floor_zone(model, zone):
    region = room_region(model, zone["room"])
    holes = list(region.holes)
    items = {i["id"]: i for i in model.get("furniture", [])}
    for item_id in zone.get("exclude_items", []):
        holes.append(_item_rect(items[item_id]))
    if zone.get("exclude"):
        holes.append(rect_poly(*zone["exclude"]))
    return Region(region.outer, holes, zone.get("within"))


def floors(model):
    """Floor zones with setting-out origin, grid cells and quantities."""
    spec = model["finishes"]
    out = []
    for zone in spec["floors"]:
        mat = spec["materials"][zone["material"]]
        region = floor_zone(model, zone)
        entry = {"id": zone["id"], "zone": zone, "material": zone["material"], "spec": mat,
                 "region": region, "area": region.area()}
        if mat["kind"] == "tile":
            ex, ey = region.boundary_edges(0), region.boundary_edges(1)
            tx, ty = mat["size"]
            origin = (best_origin(ex, tx), best_origin(ey, ty))
            cells = grid_cells(region, origin, mat["size"])
            entry.update(origin=origin, cells=cells, edges=(ex, ey),
                         min_cut=(min_cut(ex, origin[0], tx), min_cut(ey, origin[1], ty)),
                         **{k: v for k, v in summarise(cells, mat["size"]).items() if k != "area"})
        else:
            entry["pieces"] = math.ceil(entry["area"] / (mat["size"][0] * mat["size"][1]))
        entry["order_area"] = entry["area"] * (1 + mat.get("waste", 0))
        out.append(entry)
    return out


def room_faces(model, room_id):
    """Room wall faces, collinear edges merged. Each face runs left to right
    as seen from inside the room: (start, end, inward_normal)."""
    poly = [tuple(p) for p in _room(model, room_id)["polygon"]]
    if signed_area(poly) < 0:
        poly = poly[::-1]
    edges = list(zip(poly, poly[1:] + poly[:1]))
    merged = []
    for a, b in edges:
        if merged:
            pa, pb = merged[-1]
            d1 = (pb[0] - pa[0], pb[1] - pa[1])
            d2 = (b[0] - a[0], b[1] - a[1])
            if abs(d1[0] * d2[1] - d1[1] * d2[0]) < 1e-9 and d1[0] * d2[0] + d1[1] * d2[1] > 0:
                merged[-1] = (pa, b)
                continue
        merged.append((a, b))
    faces = []
    for a, b in merged:
        # CCW polygon: interior on the left of a->b; seen from inside, b is on the left.
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        faces.append({"start": b, "end": a, "length": length,
                      "normal": (-dy / length, dx / length)})
    return faces


def face_name(face):
    nx, ny = face["normal"]
    # The wall is on the opposite side of the inward normal.
    if abs(ny) > 0.9:
        return "Пд" if ny > 0 else "Пн"
    if abs(nx) > 0.9:
        return "Зх" if nx > 0 else "Сх"
    return "скіс"


def _along(face, point):
    (sx, sy), (ex, ey) = face["start"], face["end"]
    ux, uy = (ex - sx) / face["length"], (ey - sy) / face["length"]
    return (point[0] - sx) * ux + (point[1] - sy) * uy, ux, uy


def face_openings(model, face, head):
    """Door openings on a face as (u0, u1, z0, z1)."""
    out = []
    (sx, sy), (ex, ey) = face["start"], face["end"]
    for door in model.get("doors", []):
        x0, y0 = door["at"]
        x1, y1 = x0 + door["size"][0], y0 + door["size"][1]
        horizontal = abs(sy - ey) < 1e-6
        vertical = abs(sx - ex) < 1e-6
        if horizontal and (y0 - 1e-6 <= sy <= y1 + 1e-6) and door["size"][0] > door["size"][1]:
            us = sorted(_along(face, (x, sy))[0] for x in (x0, x1))
        elif vertical and (x0 - 1e-6 <= sx <= x1 + 1e-6) and door["size"][1] > door["size"][0]:
            us = sorted(_along(face, (sx, y))[0] for y in (y0, y1))
        else:
            continue
        u0, u1 = max(us[0], 0.0), min(us[1], face["length"])
        if u1 - u0 > 0.05:
            out.append((u0, u1, 0.0, head, door["id"]))
    return out


def _same_segment(face, segment):
    pts = {tuple(round(v, 3) for v in p) for p in segment}
    return pts == {tuple(round(v, 3) for v in face["start"]), tuple(round(v, 3) for v in face["end"])}


def row_origin(height, tz, cut="bottom"):
    """Height of the first horizontal joint and the cut rows (bottom, top).

    Full rows run from the `cut`-free edge; the leftover goes to the other
    edge. If it would be under half a tile it is shared equally by a bottom
    and a top row, so no cut row is below 50 %."""
    rest = height - math.floor(height / tz + 1e-9) * tz
    if rest < 1e-6 or tz - rest < 1e-6:
        return 0.0, 0.0, 0.0
    if rest >= tz / 2 - 1e-9:
        return (rest, rest, 0.0) if cut == "bottom" else (0.0, 0.0, rest)
    half = (rest + tz) / 2
    return half, half, half


def tile_face(length, height, openings, size, edges_extra=(), cut="bottom"):
    """Setting-out of one wall face in its own (u, z) coordinates."""
    tu, tz = size
    edges = [(0.0, 1, 1.0), (length, -1, 1.0)]
    for u0, u1, *_ in openings:
        edges += [(u0, -1, 0.5), (u1, 1, 0.5)]
    edges += list(edges_extra)
    ou = best_origin(edges, tu) if length > 1e-6 else 0.0
    region = Region([rect_poly(0, 0, length, height)], [rect_poly(o[0], o[2], o[1], o[3]) for o in openings])
    oz, bottom, top = row_origin(height, tz, cut)
    cells = grid_cells(region, (ou, oz), size)
    return {"origin": ou, "origin_z": oz, "cells": cells, "region": region,
            "min_cut": min(min_cut(edges, ou, tu), length),
            "bottom_row": bottom, "top_row": top, **summarise(cells, size)}


def walls(model):
    """Tiled wall faces per room with setting-out and quantities."""
    spec = model["finishes"]
    head = spec.get("door_head", 2.05)
    out = []
    for zone in spec.get("walls", []):
        for k, face in enumerate(room_faces(model, zone["room"])):
            material = zone["material"]
            for feature in zone.get("features", []):
                if _same_segment(face, feature["segment"]):
                    material = feature["material"]
            mat = spec["materials"][material]
            openings = face_openings(model, face, head)
            tiled = tile_face(face["length"], zone["height"], openings, mat["size"])
            out.append({"zone": zone, "room": zone["room"], "index": k + 1, "face": face,
                        "name": face_name(face), "material": material, "spec": mat,
                        "height": zone["height"], "openings": openings, **tiled})
    return out


def clad_items(model, room_id=None):
    """Boxes clad in the room's wall tile: tiled bath panels and install boxes.

    Each exposed side (not against the room edge or another clad box) is set
    out like a wall; an install box lower than the wall tiling also gets its top."""
    spec = model["finishes"]
    zones = {z["room"]: z for z in spec.get("walls", [])}
    items = [i for i in model.get("furniture", []) if i["room"] in zones
             and (room_id is None or i["room"] == room_id)
             and (i.get("panel") == "tiled" or i["kind"] == "install_box")]
    out = []
    for item in items:
        zone = zones[item["room"]]
        mat = spec["materials"][zone["material"]]
        region = room_region(model, item["room"])
        others = [_item_rect(o) for o in items if o is not item and o["room"] == item["room"]]
        x0, y0 = item["at"]
        w, d, h = item["size"]
        x1, y1 = x0 + w, y0 + d
        sides = []
        for name, length, (mx, my) in (("N", w, ((x0 + x1) / 2, y1 + 0.05)), ("S", w, ((x0 + x1) / 2, y0 - 0.05)),
                                       ("E", d, (x1 + 0.05, (y0 + y1) / 2)), ("W", d, (x0 - 0.05, (y0 + y1) / 2))):
            inside_other = any(r[0][0] < mx < r[2][0] and r[0][1] < my < r[2][1] for r in others)
            if region.contains(mx, my) and not inside_other:
                sides.append((name, length, h))
        area = pieces = 0
        for _name, length, height in sides:
            t = tile_face(length, height, [], mat["size"])
            area += t["area"]
            pieces += t["pieces"]
        top = item["kind"] == "install_box" and h < zone["height"] - 0.01
        if top:
            area += w * d
            pieces += math.ceil(w / mat["size"][0]) * math.ceil(d / mat["size"][1])
        out.append({"id": item["id"], "room": item["room"], "material": zone["material"], "sides": sides,
                    "top": top, "area": area, "pieces": pieces})
    return out


def splash(model):
    spec = model["finishes"]
    block = spec.get("splash")
    if not block:
        return []
    mat = spec["materials"][block["material"]]
    height = block["top"] - block["base"]
    out = []
    for seg in block["segments"]:
        a, b = seg["from"], seg["to"]
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        # A single cut row would go under the wall units, but a leftover under
        # 50 % is shared between the worktop and the top edge.
        tiled = tile_face(length, height, [], mat["size"], cut="top")
        out.append({"id": seg["id"], "segment": seg, "length": length, "base": block["base"],
                    "top": block["top"], "material": block["material"], "spec": mat, **tiled})
    return out


def quantities(model):
    """Bill of finish materials: per material area and pieces, net and with waste."""
    spec = model["finishes"]
    totals = {}

    def add(material, area, pieces):
        row = totals.setdefault(material, {"area": 0.0, "pieces": 0})
        row["area"] += area
        row["pieces"] += pieces

    for f in floors(model):
        add(f["material"], f["area"], f["pieces"])
    for w in walls(model):
        add(w["material"], w["area"], w["pieces"])
    for s in splash(model):
        add(s["material"], s["area"], s["pieces"])
    for c in clad_items(model):
        add(c["material"], c["area"], c["pieces"])
    rows = []
    for material, row in totals.items():
        mat = spec["materials"][material]
        waste = mat.get("waste", 0)
        rows.append({"material": material, "name_uk": mat["name_uk"], "area": row["area"],
                     "pieces": row["pieces"], "waste": waste,
                     "order_area": row["area"] * (1 + waste),
                     "order_pieces": math.ceil(row["pieces"] * (1 + waste))})
    return rows


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from model_loader import load_model

    m = load_model(sys.argv[1] if len(sys.argv) > 1 else "data/target.yaml")
    for f in floors(m):
        extra = (f" origin {f['origin']} min cut {f['min_cut'][0]:.3f}/{f['min_cut'][1]:.3f}"
                 if "origin" in f else "")
        print(f"{f['id']:10} {f['material']:12} {f['area']:7.2f} m² {f['pieces']:4} pcs{extra}")
    for w in walls(m):
        print(f"room {w['room']} face {w['index']} {w['name']:4} L={w['face']['length']:.2f} "
              f"{w['material']:12} {w['area']:6.2f} m² {w['pieces']:3} pcs origin {w['origin']:.3f} "
              f"min cut {w['min_cut']:.3f} openings {[o[4] for o in w['openings']]}")
    for s in splash(m):
        print(f"{s['id']} L={s['length']:.2f} {s['area']:.3f} m² {s['pieces']} pcs origin {s['origin']:.3f}")
    for q in quantities(m):
        print(f"{q['material']:12} {q['area']:7.2f} m² net, order {q['order_area']:7.2f} m² / {q['order_pieces']} pcs")
