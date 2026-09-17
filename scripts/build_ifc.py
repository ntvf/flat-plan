"""
Build an IFC4 model from a compiled layout JSON.

Unlike the original build_ifc_model.py this creates *real* openings: every door
is an IfcOpeningElement that voids its host wall and is filled by an IfcDoor, so
Bonsai (and any other IFC viewer) can draw proper door symbols and cut the wall.

Run with:
  python3 scripts/yaml_to_json.py data/as_is.yaml build/as_is.json
  blender -b --python scripts/build_ifc.py -- build/as_is.json exports/as_is.ifc
"""

import json
import os
import sys

import ifcopenshell
import ifcopenshell.api
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_symbols import door_leaf, window_panes  # noqa: E402

DOOR_HEIGHT = 2.10


def argv_after_dashes():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def offset_polygon(points, distance):
    """Offset a closed polygon inward, mitring the corners.

    Each edge is shifted along its inward normal and consecutive shifted edges
    are intersected, which keeps corners sharp instead of rounding them.

    `distance` is either a single number for every edge, or a sequence giving
    a separate distance per edge - the exterior envelope is not one uniform
    thickness (the east wall reads 0.47 against 0.40 elsewhere), and mitring
    edges of differing thickness still has to produce a closed polygon.
    """
    pts = [np.array(p, dtype=float) for p in points]
    n = len(pts)
    try:
        dists = [float(d) for d in distance]
    except TypeError:
        dists = [float(distance)] * n
    if len(dists) != n:
        raise ValueError(f"expected {n} offsets, got {len(dists)}")
    area2 = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                for i in range(n))
    sign = 1.0 if area2 > 0 else -1.0

    lines = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        d = b - a
        length = np.linalg.norm(d)
        if length < 1e-9:
            raise ValueError(f"outline edge {i} has zero length")
        d = d / length
        normal = np.array([-d[1], d[0]]) * sign   # inward normal
        lines.append((a + normal * dists[i], d))

    out = []
    m = len(lines)
    for i in range(m):
        p1, d1 = lines[i - 1]
        p2, d2 = lines[i]
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(cross) < 1e-9:          # parallel edges, no corner to mitre
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / cross
        out.append(p1 + d1 * t)
    return [(float(p[0]), float(p[1])) for p in out]


class Builder:
    def __init__(self, data):
        self.data = data
        self.height = float(data["meta"]["ceiling_height"])
        self.model = ifcopenshell.api.run("project.create_file", version="IFC4")
        run = ifcopenshell.api.run

        self.project = run("root.create_entity", self.model, ifc_class="IfcProject",
                           name=data["meta"]["title"])
        run("unit.assign_unit", self.model)
        ctx = run("context.add_context", self.model, context_type="Model")
        self.body = run("context.add_context", self.model, context_type="Model",
                        context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)

        site = run("root.create_entity", self.model, ifc_class="IfcSite", name="Site")
        building = run("root.create_entity", self.model, ifc_class="IfcBuilding",
                       name="Budynek")
        self.storey = run("root.create_entity", self.model,
                          ifc_class="IfcBuildingStorey", name="Kondygnacja")
        run("aggregate.assign_object", self.model, relating_object=self.project,
            products=[site])
        run("aggregate.assign_object", self.model, relating_object=site,
            products=[building])
        run("aggregate.assign_object", self.model, relating_object=building,
            products=[self.storey])

        self.walls = []     # (entity, x0, y0, x1, y1, thickness)

    # -- geometry helpers ---------------------------------------------------
    def place(self, product, matrix):
        ifcopenshell.api.run("geometry.edit_object_placement", self.model,
                             product=product, matrix=matrix)

    def box(self, ifc_class, name, x, y, z, w, d, h):
        return self.boxes(ifc_class, name, (x, y, z), [(0.0, 0.0, 0.0, w, d, h)])

    def boxes(self, ifc_class, name, origin, parts):
        """An element made of one or more boxes.

        `parts` are (x, y, z, w, d, h) tuples in coordinates local to
        `origin`. Multiple parts are needed for things whose plan symbol is
        not a solid block - a window is two panes with a gap between them,
        not a filled rectangle.
        """
        el = ifcopenshell.api.run("root.create_entity", self.model,
                                  ifc_class=ifc_class, name=name)
        faces = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1],
                 [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
        all_verts, all_faces = [], []
        for px, py, pz, w, d, h in parts:
            all_verts.append([(px, py, pz), (px + w, py, pz),
                              (px + w, py + d, pz), (px, py + d, pz),
                              (px, py, pz + h), (px + w, py, pz + h),
                              (px + w, py + d, pz + h), (px, py + d, pz + h)])
            all_faces.append([list(f) for f in faces])
        rep = ifcopenshell.api.run("geometry.add_mesh_representation", self.model,
                                   context=self.body, vertices=all_verts,
                                   faces=all_faces)
        ifcopenshell.api.run("geometry.assign_representation", self.model,
                             product=el, representation=rep)
        x, y, z = origin
        self.place(el, np.array([[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z], [0, 0, 0, 1]],
                                dtype=float))
        return el

    def prism(self, ifc_class, name, polygon, z, height):
        """An element extruded vertically from an arbitrary plan polygon.

        `add_wall_representation` can only sweep a rectangle, so mitred wall
        joints - where the ends are cut back to the corner bisector rather
        than left square - need a general prism instead.
        """
        el = ifcopenshell.api.run("root.create_entity", self.model,
                                  ifc_class=ifc_class, name=name)
        n = len(polygon)
        bottom = [(float(x), float(y), 0.0) for x, y in polygon]
        top = [(float(x), float(y), float(height)) for x, y in polygon]
        verts = bottom + top
        faces = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))]
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, j + n, i + n])
        rep = ifcopenshell.api.run("geometry.add_mesh_representation", self.model,
                                   context=self.body, vertices=[verts], faces=[faces])
        ifcopenshell.api.run("geometry.assign_representation", self.model,
                             product=el, representation=rep)
        self.place(el, np.array([[1, 0, 0, 0.0], [0, 1, 0, 0.0], [0, 0, 1, z],
                                 [0, 0, 0, 1]], dtype=float))
        return el

    def mitred_wall(self, quad, p1, p2, thickness, name):
        """A wall whose plan shape is given explicitly, so corners close cleanly."""
        wall = self.prism("IfcWall", name, quad, 0.0, self.height)
        ifcopenshell.api.run("spatial.assign_container", self.model,
                             relating_structure=self.storey, products=[wall])
        a, b = np.array(p1, dtype=float), np.array(p2, dtype=float)
        self.walls.append((wall, a[0], a[1], b[0], b[1], thickness))
        return wall

    def wall(self, p1, p2, thickness, name):
        run = ifcopenshell.api.run
        wall = run("root.create_entity", self.model, ifc_class="IfcWall", name=name)
        run("spatial.assign_container", self.model, relating_structure=self.storey,
            products=[wall])

        a, b = np.array(p1, dtype=float), np.array(p2, dtype=float)
        length = float(np.linalg.norm(b - a))
        if length < 1e-6:
            return None
        rep = run("geometry.add_wall_representation", self.model, context=self.body,
                  length=length, height=self.height, thickness=thickness,
                  offset=-thickness / 2.0)
        run("geometry.assign_representation", self.model, product=wall,
            representation=rep)
        v = (b - a) / length
        self.place(wall, np.array([[v[0], -v[1], 0, a[0]],
                                   [v[1], v[0], 0, a[1]],
                                   [0, 0, 1, 0.0],
                                   [0, 0, 0, 1]]))
        self.walls.append((wall, a[0], a[1], b[0], b[1], thickness))
        return wall

    # -- model parts --------------------------------------------------------
    def exterior_thicknesses(self):
        """Per-edge thickness of the exterior envelope."""
        default = float(self.data["thickness"]["exterior"])
        overrides = self.data.get("outline_thickness") or {}
        n = len(self.data["outline"])
        return [float(overrides.get(i, overrides.get(str(i), default)))
                for i in range(n)]

    def build_exterior(self):
        outer = [tuple(p) for p in self.data["outline"]]
        thick = self.exterior_thicknesses()
        centre = offset_polygon(outer, [t / 2.0 for t in thick])
        inner = offset_polygon(outer, thick)
        n = len(outer)
        for i in range(n):
            j = (i + 1) % n
            # Cut both ends back to the mitre line by taking the matching
            # corners of the outer and inner offset polygons, so consecutive
            # walls meet flush instead of leaving a notched, stepped corner.
            quad = [outer[i], outer[j], tuple(inner[j]), tuple(inner[i])]
            self.mitred_wall(quad, centre[i], centre[j], thick[i],
                             f"Ściana zewnętrzna {i + 1}")

    def build_partitions(self):
        for w in self.data.get("walls", []):
            x, y = w["at"]
            ww, wh = w["size"]
            if ww >= wh:                       # horizontal run
                self.wall((x, y + wh / 2), (x + ww, y + wh / 2), wh, w["id"])
            else:
                self.wall((x + ww / 2, y), (x + ww / 2, y + wh), ww, w["id"])

    def build_bedroom_walls(self):
        """Walls implied by the bedroom polygons but not listed explicitly."""
        t = float(self.data["thickness"]["partition"])
        implied = [
            ((0.40, 4.91), (3.37, 4.91), "Ściana sypialnia 1 / korytarz"),
            ((3.47, 4.91), (6.25, 4.91), "Ściana sypialnia 2 / korytarz"),
            ((3.42, 0.40), (3.42, 4.86), "Ściana sypialnia 1 / 2"),
            ((6.30, 1.34), (6.30, 5.88), "Ściana sypialnia 3 / korytarz"),
            ((6.35, 5.93), (8.96, 5.93), "Ściana sypialnia 3 / salon"),
        ]
        for p1, p2, name in implied:
            self.wall(p1, p2, t, name)

    def build_spaces(self):
        run = ifcopenshell.api.run
        by_id = {r["id"]: r for r in self.data["rooms"]}
        for room in self.data["rooms"]:
            poly = room["polygon"]
            area = polygon_area(poly)
            for hole in room.get("subtract", []):
                other = by_id[hole]
                area -= polygon_area(other.get("footprint") or other["polygon"])

            space = run("root.create_entity", self.model, ifc_class="IfcSpace",
                        name=f"{room['id']} {room['name']}")
            run("aggregate.assign_object", self.model, relating_object=self.storey,
                products=[space])

            verts = [(x, y, 0.0) for x, y in poly] + [(x, y, 0.02) for x, y in poly]
            n = len(poly)
            faces = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
            for i in range(n):
                j = (i + 1) % n
                faces.append([i, i + n, j + n, j])
            rep = run("geometry.add_mesh_representation", self.model, context=self.body,
                      vertices=[verts], faces=[faces])
            run("geometry.assign_representation", self.model, product=space,
                representation=rep)

            qto = run("pset.add_qto", self.model, product=space,
                      name="Qto_SpaceBaseQuantities")
            run("pset.edit_qto", self.model, qto=qto,
                properties={"NetFloorArea": round(area, 2),
                            "GrossFloorArea": round(area, 2),
                            "Height": self.height})

    def build_columns_and_shafts(self):
        run = ifcopenshell.api.run
        for col in self.data.get("columns", []):
            x, y = col["at"]
            w, d = col["size"]
            el = self.box("IfcColumn", col.get("id", "Słup"), x, y, 0.0, w, d,
                          self.height)
            run("spatial.assign_container", self.model, relating_structure=self.storey,
                products=[el])
        for shaft in self.data.get("shafts", []):
            x, y = shaft["at"]
            w, d = shaft["size"]
            el = self.box("IfcBuildingElementProxy", f"{shaft['id']} {shaft['service']}",
                          x, y, 0.0, w, d, self.height)
            run("spatial.assign_container", self.model, relating_structure=self.storey,
                products=[el])

    def host_wall_for(self, cx, cy):
        """Find the wall whose centreline passes closest to a point."""
        best, best_d = None, 1e9
        for wall, x0, y0, x1, y1, t in self.walls:
            px, py = x1 - x0, y1 - y0
            seg = px * px + py * py
            if seg < 1e-12:
                continue
            u = max(0.0, min(1.0, ((cx - x0) * px + (cy - y0) * py) / seg))
            dx, dy = x0 + u * px - cx, y0 + u * py - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < best_d:
                best, best_d = wall, dist
        return best if best_d < 0.45 else None

    def build_doors(self):
        run = ifcopenshell.api.run
        placed, orphaned = 0, []
        for door in self.data.get("doors", []):
            x, y = door["at"]
            w, d = door["size"]
            cx, cy = x + w / 2.0, y + d / 2.0
            host = self.host_wall_for(cx, cy)
            if host is None:
                orphaned.append(door["id"])
                continue

            # Oversize the void across the wall so the boolean cuts cleanly.
            if w >= d:
                ox, oy, ow, od = x, y - 0.15, w, d + 0.30
            else:
                ox, oy, ow, od = x - 0.15, y, w + 0.30, d
            opening = self.box("IfcOpeningElement", f"Otwór {door['id']}",
                               ox, oy, 0.0, ow, od, DOOR_HEIGHT)
            run("feature.add_feature", self.model, feature=opening, element=host)

            leaf = self.boxes("IfcDoor", f"Drzwi {door['id']}", (x, y, 0.0),
                              door_leaf(w, d, DOOR_HEIGHT, door.get("swing")))
            run("spatial.assign_container", self.model, relating_structure=self.storey,
                products=[leaf])
            run("feature.add_filling", self.model, opening=opening, element=leaf)
            placed += 1
        return placed, orphaned

    def build_windows(self):
        run = ifcopenshell.api.run
        placed, orphaned = 0, []
        for win in self.data.get("windows", []):
            x, y = win["at"]
            w, d = win["size"]
            cx, cy = x + w / 2.0, y + d / 2.0
            host = self.host_wall_for(cx, cy)
            if host is None:
                orphaned.append(win["id"])
                continue

            sill = float(win.get("sill", 0.90))
            head = float(win.get("head", 2.20))
            height = head - sill

            if w >= d:
                ox, oy, ow, od = x, y - 0.25, w, d + 0.50
            else:
                ox, oy, ow, od = x - 0.25, y, w + 0.50, d
            opening = self.box("IfcOpeningElement", f"Otwór {win['id']}",
                               ox, oy, sill, ow, od, height)
            run("feature.add_feature", self.model, feature=opening, element=host)

            leaf = self.boxes("IfcWindow", f"Okno {win['id']}", (x, y, sill),
                              window_panes(w, d, height))
            run("spatial.assign_container", self.model,
                relating_structure=self.storey, products=[leaf])
            run("feature.add_filling", self.model, opening=opening, element=leaf)
            placed += 1
        return placed, orphaned

    def write(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.model.write(path)


def polygon_area(pts):
    total = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def main():
    args = argv_after_dashes()
    src, dst = args[0], args[1]
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    b = Builder(data)
    b.build_exterior()
    b.build_partitions()
    b.build_bedroom_walls()
    b.build_spaces()
    b.build_columns_and_shafts()
    placed, orphaned = b.build_doors()
    win_placed, win_orphaned = b.build_windows()
    b.write(dst)

    print(f"[build_ifc] walls={len(b.walls)} doors={placed} "
          f"windows={win_placed} spaces={len(data['rooms'])}")
    if orphaned:
        print(f"[build_ifc] WARNING no host wall for doors: {orphaned}")
    if win_orphaned:
        print(f"[build_ifc] WARNING no host wall for windows: {win_orphaned}")
    print(f"[build_ifc] wrote {dst}")


if __name__ == "__main__":
    main()
