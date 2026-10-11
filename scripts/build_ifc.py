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
import math
import os
import sys

import ifcopenshell
import ifcopenshell.api
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_symbols import (door_frame, door_leaf, window_frame, window_handles,
                          window_panes)  # noqa: E402

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

    @staticmethod
    def box_mesh(x, y, z, w, d, h):
        vertices = [(x, y, z), (x + w, y, z), (x + w, y + d, z),
                    (x, y + d, z), (x, y, z + h), (x + w, y, z + h),
                    (x + w, y + d, z + h), (x, y + d, z + h)]
        faces = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1],
                 [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
        return vertices, faces

    @staticmethod
    def cylinder_mesh(x, y, z, rx, ry, length, axis="z", segments=32):
        """Create an elliptical cylinder along one local axis."""
        vertices = []
        for offset in (0.0, length):
            for index in range(segments):
                angle = 2.0 * math.pi * index / segments
                a = rx * math.cos(angle)
                b = ry * math.sin(angle)
                if axis == "x":
                    vertices.append((x + offset, y + a, z + b))
                elif axis == "y":
                    vertices.append((x + a, y + offset, z + b))
                else:
                    vertices.append((x + a, y + b, z + offset))
        faces = [list(range(segments - 1, -1, -1)),
                 list(range(segments, 2 * segments))]
        for index in range(segments):
            next_index = (index + 1) % segments
            faces.append([index, next_index, next_index + segments,
                          index + segments])
        return vertices, faces

    @staticmethod
    def bowl_mesh(x, y, z, rx, ry, height, rim, segments=32):
        """Create an open elliptical bowl with a sloped inner surface."""
        inner_rx = max(rx - rim, rx * 0.55)
        inner_ry = max(ry - rim, ry * 0.55)
        rings = (
            (rx * 0.82, ry * 0.82, z),
            (rx, ry, z + height),
            (inner_rx, inner_ry, z + height),
            (inner_rx * 0.38, inner_ry * 0.38, z + height * 0.18),
        )
        vertices = []
        for ring_rx, ring_ry, ring_z in rings:
            for index in range(segments):
                angle = 2.0 * math.pi * index / segments
                vertices.append((
                    x + ring_rx * math.cos(angle),
                    y + ring_ry * math.sin(angle),
                    ring_z,
                ))
        faces = []
        for first_ring, second_ring in ((0, 1), (1, 2), (2, 3)):
            first = first_ring * segments
            second = second_ring * segments
            for index in range(segments):
                next_index = (index + 1) % segments
                faces.append([first + index, first + next_index,
                              second + next_index, second + index])
        faces.append(list(range(segments - 1, -1, -1)))
        faces.append(list(range(3 * segments, 4 * segments)))
        return vertices, faces

    def meshes(self, ifc_class, name, origin, meshes):
        el = ifcopenshell.api.run("root.create_entity", self.model,
                                  ifc_class=ifc_class, name=name)
        vertices = []
        faces = []
        for mesh_vertices, mesh_faces in meshes:
            offset = len(vertices)
            vertices.extend(mesh_vertices)
            faces.extend([[index + offset for index in face]
                          for face in mesh_faces])
        rep = ifcopenshell.api.run("geometry.add_mesh_representation", self.model,
                                   context=self.body, vertices=[vertices],
                                   faces=[faces])
        ifcopenshell.api.run("geometry.assign_representation", self.model,
                             product=el, representation=rep)
        x, y, z = origin
        self.place(el, np.array([[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z],
                                 [0, 0, 0, 1]], dtype=float))
        return el

    def boxes(self, ifc_class, name, origin, parts):
        """An element made of one or more boxes.

        `parts` are (x, y, z, w, d, h) tuples in coordinates local to
        `origin`. Multiple parts are needed for things whose plan symbol is
        not a solid block - a window is two panes with a gap between them,
        not a filled rectangle.
        """
        return self.meshes(
            ifc_class, name, origin,
            [self.box_mesh(px, py, pz, w, d, h)
             for px, py, pz, w, d, h in parts],
        )

    def equipment_geometry(self, item):
        """Return recognizable geometry within the item's exact size envelope."""
        w, d, h = (float(value) for value in item["size"])
        category = item.get("category")

        if category == "bath":
            rim = min(0.075, w * 0.08, d * 0.10)
            return [
                self.box_mesh(0, 0, 0, w, d, 0.08),
                self.box_mesh(0, 0, 0.08, w, rim, h - 0.08),
                self.box_mesh(0, d - rim, 0.08, w, rim, h - 0.08),
                self.box_mesh(0, rim, 0.08, rim, d - 2 * rim, h - 0.08),
                self.box_mesh(w - rim, rim, 0.08, rim, d - 2 * rim, h - 0.08),
            ]

        if category == "basin":
            bowl_height = min(h, 0.14)
            if item.get("shape") == "rectangular":
                rim = min(0.055, w * 0.12, d * 0.10)
                base = min(0.025, bowl_height * 0.25)
                meshes = [
                    self.box_mesh(rim, rim, 0, w - 2 * rim, d - 2 * rim, base),
                    self.box_mesh(0, 0, base, w, rim, bowl_height - base),
                    self.box_mesh(0, d - rim, base, w, rim,
                                  bowl_height - base),
                    self.box_mesh(0, rim, base, rim, d - 2 * rim,
                                  bowl_height - base),
                    self.box_mesh(w - rim, rim, base, rim, d - 2 * rim,
                                  bowl_height - base),
                ]
            else:
                meshes = [
                    self.bowl_mesh(w / 2, d / 2, h - bowl_height,
                                   w / 2, d / 2, bowl_height, 0.045),
                    self.box_mesh(0, 0, h - 0.05, w, min(0.07, d), 0.05),
                ]
            if item.get("mounting") == "floor":
                meshes.append(self.cylinder_mesh(
                    w / 2, d * 0.42, 0, w * 0.16, d * 0.16,
                    max(0.0, h - bowl_height),
                ))
            return meshes

        if category == "wc":
            back = item.get("back", "south")
            if item.get("mounting") == "wall":
                if back in ("south", "north"):
                    bowl_y = d * 0.46 if back == "south" else d * 0.54
                    mount_y = 0 if back == "south" else d - 0.10
                    return [
                        self.bowl_mesh(w / 2, bowl_y, 0,
                                       w / 2, d * 0.46, h, 0.04),
                        self.box_mesh(w * 0.15, mount_y, h * 0.18,
                                      w * 0.70, 0.10, h * 0.55),
                    ]
                bowl_x = w * 0.46 if back == "west" else w * 0.54
                mount_x = 0 if back == "west" else w - 0.10
                return [
                    self.bowl_mesh(bowl_x, d / 2, 0,
                                   w * 0.46, d / 2, h, 0.04),
                    self.box_mesh(mount_x, d * 0.15, h * 0.18,
                                  0.10, d * 0.70, h * 0.55),
                ]
            tank_depth = min(0.22, d * 0.32)
            tank_width = w * 0.88
            bowl_height = min(0.42, h * 0.54)
            pedestal_height = bowl_height * 0.72
            meshes = []
            if back in ("south", "north"):
                tank_y = 0 if back == "south" else d - tank_depth
                bowl_y = tank_depth + (d - tank_depth) / 2 if back == "south" \
                    else (d - tank_depth) / 2
                meshes.extend([
                    self.box_mesh((w - tank_width) / 2, tank_y, 0,
                                  tank_width, tank_depth, h),
                    self.bowl_mesh(w / 2, bowl_y, pedestal_height,
                                   w / 2, (d - tank_depth) / 2,
                                   bowl_height - pedestal_height, 0.04),
                    self.cylinder_mesh(w / 2, bowl_y, 0,
                                       w * 0.28, (d - tank_depth) * 0.28,
                                       pedestal_height),
                ])
            else:
                tank_depth = min(0.22, w * 0.32)
                tank_x = 0 if back == "west" else w - tank_depth
                bowl_x = tank_depth + (w - tank_depth) / 2 if back == "west" \
                    else (w - tank_depth) / 2
                meshes.extend([
                    self.box_mesh(tank_x, (d - tank_width) / 2, 0,
                                  tank_depth, tank_width, h),
                    self.bowl_mesh(bowl_x, d / 2, pedestal_height,
                                   (w - tank_depth) / 2, d / 2,
                                   bowl_height - pedestal_height, 0.04),
                    self.cylinder_mesh(bowl_x, d / 2, 0,
                                       (w - tank_depth) * 0.28, d * 0.28,
                                       pedestal_height),
                ])
            return meshes

        if category == "shower":
            kerb = min(0.055, w * 0.08, d * 0.08)
            return [
                self.box_mesh(0, 0, 0, w, d, min(0.025, h)),
                self.box_mesh(0, 0, 0.025, w, kerb, h - 0.025),
                self.box_mesh(0, d - kerb, 0.025, w, kerb, h - 0.025),
                self.box_mesh(0, kerb, 0.025, kerb, d - 2 * kerb, h - 0.025),
                self.box_mesh(w - kerb, kerb, 0.025, kerb, d - 2 * kerb,
                              h - 0.025),
                self.cylinder_mesh(w / 2, d / 2, h - 0.008,
                                   0.035, 0.035, 0.008),
            ]

        if category in ("washer", "dryer"):
            body_depth = max(0.0, d - 0.025)
            return [
                self.box_mesh(0, 0.025, 0, w, body_depth, h),
                self.box_mesh(0.04, 0.005, h * 0.78, w - 0.08, 0.025, h * 0.15),
                self.cylinder_mesh(w / 2, 0, h * 0.44,
                                   w * 0.29, h * 0.22, 0.035, axis="y"),
                self.cylinder_mesh(w * 0.83, 0, h * 0.865,
                                   0.025, 0.025, 0.04, axis="y"),
            ]

        if category == "faucet":
            back = item.get("back", "south")
            radius = min(w, d, h) * 0.10
            meshes = []
            if back in ("south", "north"):
                stem_y = d * (0.25 if back == "south" else 0.75)
                spout_y = d * (0.25 if back == "south" else 0.15)
                meshes.extend([
                    self.cylinder_mesh(w / 2, stem_y, 0, radius, radius,
                                       h * 0.72),
                    self.cylinder_mesh(w / 2, spout_y, h * 0.70,
                                       radius * 0.72, radius * 0.72,
                                       d * 0.60, axis="y"),
                    self.cylinder_mesh(w * 0.72, stem_y, h * 0.67,
                                       radius * 0.55, radius * 0.55,
                                       h * 0.22),
                ])
            else:
                stem_x = w * (0.25 if back == "west" else 0.75)
                spout_x = w * (0.25 if back == "west" else 0.15)
                meshes.extend([
                    self.cylinder_mesh(stem_x, d / 2, 0, radius, radius,
                                       h * 0.72),
                    self.cylinder_mesh(spout_x, d / 2, h * 0.70,
                                       radius * 0.72, radius * 0.72,
                                       w * 0.60, axis="x"),
                    self.cylinder_mesh(stem_x, d * 0.72, h * 0.67,
                                       radius * 0.55, radius * 0.55,
                                       h * 0.22),
                ])
            return meshes

        if category == "shower_faucet":
            radius = min(w, d) * 0.08
            return [
                self.cylinder_mesh(w * 0.72, d / 2, 0, radius, radius,
                                   h * 0.88),
                self.cylinder_mesh(w * 0.10, d / 2, h * 0.86,
                                   radius, radius, w * 0.62, axis="x"),
                self.cylinder_mesh(w * 0.10, d / 2, h * 0.80,
                                   min(w, d) * 0.22, min(w, d) * 0.22,
                                   h * 0.04),
                self.cylinder_mesh(w * 0.58, d * 0.10, h * 0.10,
                                   radius, radius, d * 0.80, axis="y"),
                self.cylinder_mesh(w * 0.42, d * 0.32, h * 0.10,
                                   radius * 0.75, radius * 0.75,
                                   w * 0.32, axis="x"),
            ]

        if category == "flush_plate":
            return [
                self.box_mesh(0, 0, 0, w, d, h),
                self.cylinder_mesh(w * 0.38, 0, h * 0.52,
                                   w * 0.12, h * 0.20, d * 1.35, axis="y"),
                self.cylinder_mesh(w * 0.68, 0, h * 0.52,
                                   w * 0.08, h * 0.14, d * 1.35, axis="y"),
            ]

        return None

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

    def panel(self, ifc_class, name, p1, p2, thickness, z, height):
        run = ifcopenshell.api.run
        product = run("root.create_entity", self.model, ifc_class=ifc_class,
                      name=name)
        a, b = np.array(p1, dtype=float), np.array(p2, dtype=float)
        length = float(np.linalg.norm(b - a))
        if length < 1e-6:
            raise ValueError(f"panel {name} has zero length")
        rep = run("geometry.add_wall_representation", self.model, context=self.body,
                  length=length, height=height, thickness=thickness,
                  offset=-thickness / 2.0)
        run("geometry.assign_representation", self.model, product=product,
            representation=rep)
        v = (b - a) / length
        self.place(product, np.array([[v[0], -v[1], 0, a[0]],
                                      [v[1], v[0], 0, a[1]],
                                      [0, 0, 1, z],
                                      [0, 0, 0, 1]]))
        return product, length

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
            wall = self.mitred_wall(quad, centre[i], centre[j], thick[i],
                                    f"Ściana zewnętrzna {i + 1}")
            self.add_properties(wall, "ModelWall", {
                "WallId": f"EXT_{i + 1}",
                "Kind": "exterior",
                "RenovationStatus": "existing",
                "Length": round(float(np.linalg.norm(np.subtract(centre[j], centre[i]))), 3),
                "Thickness": thick[i],
            })

    def build_partitions(self):
        for w in self.data.get("walls", []):
            x, y = w["at"]
            ww, wh = w["size"]
            name = w.get("name", w["id"])
            if ww >= wh:                       # horizontal run
                wall = self.wall((x, y + wh / 2), (x + ww, y + wh / 2), wh, name)
                length, thickness = ww, wh
            else:
                wall = self.wall((x + ww / 2, y), (x + ww / 2, y + wh), ww, name)
                length, thickness = wh, ww
            # Walls inherited unchanged from the survey are existing by definition.
            self.add_properties(wall, "ModelWall", {
                "WallId": w["id"],
                "Kind": "partition",
                "Material": w.get("material"),
                "RenovationStatus": w.get("renovation_status", "existing"),
                "Length": length,
                "Thickness": thickness,
                "Note": w.get("note"),
            })

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
            self.add_properties(space, "ModelSpace", {
                "RoomId": str(room["id"]),
                "Function": room.get("function"),
                "RenovationStatus": room.get("renovation_status", "existing"),
            })

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

    def add_properties(self, product, name, properties):
        properties = {key: value for key, value in properties.items()
                      if value is not None}
        if not properties:
            return
        pset = ifcopenshell.api.run("pset.add_pset", self.model, product=product,
                                    name=name)
        ifcopenshell.api.run("pset.edit_pset", self.model, pset=pset,
                             properties=properties)

    def build_equipment_and_routes(self):
        run = ifcopenshell.api.run
        equipment_count = 0
        route_segment_count = 0
        for item in self.data.get("equipment", []):
            x, y, z = item["at"]
            w, d, h = item["size"]
            detailed_geometry = self.equipment_geometry(item)
            if detailed_geometry:
                el = self.meshes(
                    item.get("ifc_class", "IfcBuildingElementProxy"),
                    f"{item['id']} {item['name']}", (x, y, z),
                    detailed_geometry,
                )
            elif item.get("shape") == "cylinder":
                if abs(w - d) > 1e-9:
                    raise ValueError(f"cylindrical equipment {item['id']} needs equal width and depth")
                radius = w / 2.0
                polygon = [
                    (x + radius + radius * math.cos(2 * math.pi * i / 32),
                     y + radius + radius * math.sin(2 * math.pi * i / 32))
                    for i in range(32)
                ]
                el = self.prism(item.get("ifc_class", "IfcBuildingElementProxy"),
                                f"{item['id']} {item['name']}", polygon, z, h)
            else:
                el = self.box(item.get("ifc_class", "IfcBuildingElementProxy"),
                              f"{item['id']} {item['name']}", x, y, z, w, d, h)
            run("spatial.assign_container", self.model, relating_structure=self.storey,
                products=[el])
            self.add_properties(el, "ModelEquipment", {
                "AssetId": item["id"],
                "Category": item.get("category"),
                "Manufacturer": item.get("manufacturer"),
                "CapacityLitres": item.get("capacity_l"),
                "Shape": item.get("shape", "box"),
                "DetailedGeometry": bool(detailed_geometry),
                "BackOrientation": item.get("back"),
                "Mounting": item.get("mounting"),
                "Host": item.get("host"),
                "Room": str(item.get("room")) if item.get("room") is not None else None,
                "RenovationStatus": item.get("renovation_status"),
                "SurveyNote": item.get("note"),
            })
            equipment_count += 1

        for route in self.data.get("service_routes", []):
            if not route.get("geometry_visible", True):
                continue
            diameter = float(route["nominal_diameter"])
            points = route["points"]
            for index, (start, end) in enumerate(zip(points, points[1:]), 1):
                x1, y1, z1 = (float(v) for v in start)
                x2, y2, z2 = (float(v) for v in end)
                dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
                axes = sum(abs(v) > 1e-9 for v in (dx, dy, dz))
                if axes != 1:
                    raise ValueError(
                        f"service route {route['id']} segment {index} must be axis-aligned"
                    )
                x = min(x1, x2) - (diameter / 2 if abs(dx) < 1e-9 else 0)
                y = min(y1, y2) - (diameter / 2 if abs(dy) < 1e-9 else 0)
                z = min(z1, z2) - (diameter / 2 if abs(dz) < 1e-9 else 0)
                w = abs(dx) or diameter
                d = abs(dy) or diameter
                h = abs(dz) or diameter
                el = self.box(route.get("ifc_class", "IfcPipeSegment"),
                              f"{route['id']} {index}", x, y, z, w, d, h)
                run("spatial.assign_container", self.model,
                    relating_structure=self.storey, products=[el])
                self.add_properties(el, "ModelServiceRoute", {
                    "RouteId": route["id"],
                    "System": route.get("system"),
                    "Installation": route.get("installation"),
                    "RenovationStatus": route.get("renovation_status"),
                    "Destination": route.get("destination"),
                    "NominalDiameter": diameter,
                    "NominalSlope": route.get("slope"),
                    "SurveyNote": route.get("note"),
                })
                route_segment_count += 1
        return equipment_count, route_segment_count

    def build_service_terminals_and_floor_data(self):
        run = ifcopenshell.api.run
        terminal_count = 0
        for terminal in self.data.get("service_terminals", []):
            x, y = (float(value) for value in terminal["at"])
            for index, connection in enumerate(terminal.get("connections", []), 1):
                raw_height = connection.get("height")
                height = float(raw_height) if isinstance(raw_height, (int, float)) else 0.02
                marker = self.box(
                    "IfcBuildingElementProxy",
                    f"{terminal['id']} {connection['service']}",
                    x - 0.03, y - 0.03, max(0.0, height - 0.03),
                    0.06, 0.06, 0.06,
                )
                run("spatial.assign_container", self.model,
                    relating_structure=self.storey, products=[marker])
                self.add_properties(marker, "SurveyedServiceTerminal", {
                    "TerminalId": terminal["id"],
                    "ConnectionIndex": index,
                    "Service": connection["service"],
                    "HeightAboveFinishedFloor": (
                        raw_height if isinstance(raw_height, (int, float))
                        else str(raw_height or "not_surveyed")
                    ),
                    "Installation": connection.get("installation"),
                    "Mounting": connection.get("mounting"),
                    "Host": terminal.get("host"),
                    "Room": str(terminal.get("room")),
                    "SurveyNote": terminal.get("name"),
                })
                terminal_count += 1

        for assembly in self.data.get("floor_assemblies", []):
            layers = assembly.get("layers_top_down", [])
            self.add_properties(self.project, f"SurveyedFloorAssembly_{assembly['id']}", {
                "AssemblyId": assembly["id"],
                "Status": assembly.get("status"),
                "Scope": assembly.get("scope"),
                "TotalThickness": assembly.get("total_thickness"),
                "LayersTopDown": " | ".join(
                    f"{layer['material']} {float(layer['thickness']):.3f} m"
                    for layer in layers
                ),
                "SurveyNote": assembly.get("note"),
            })
        return terminal_count

    def build_wall_finishes(self):
        run = ifcopenshell.api.run
        count = 0
        for finish in self.data.get("wall_finishes", []):
            base = float(finish["base_height"])
            top = float(finish["top_height"])
            if top <= base:
                raise ValueError(f"wall finish {finish['id']} has invalid heights")
            product, length = self.panel(
                finish.get("ifc_class", "IfcCovering"),
                f"{finish['id']} {finish['material']}",
                finish["segment"][0], finish["segment"][1],
                float(finish["thickness"]), base, top - base,
            )
            run("spatial.assign_container", self.model,
                relating_structure=self.storey, products=[product])
            area = length * (top - base)
            self.add_properties(product, "SurveyedWallFinish", {
                "FinishId": finish["id"],
                "Material": finish["material"],
                "BaseHeight": base,
                "TopHeight": top,
                "GrossArea": round(area, 3),
                "SurveyNote": finish.get("note"),
            })
            qto = run("pset.add_qto", self.model, product=product,
                      name="Qto_CoveringBaseQuantities")
            run("pset.edit_qto", self.model, qto=qto,
                properties={"GrossArea": round(area, 3),
                            "NetArea": round(area, 3)})
            count += 1
        return count

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
        openings, leaves, orphaned = 0, 0, []
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
            openings += 1

            if not door.get("has_leaf", True):
                continue

            nominal_width = float(door.get("nominal_width", max(w, d)))
            height = float(door.get("height", DOOR_HEIGHT))
            leaf = self.boxes("IfcDoor", f"Drzwi {door['id']}", (x, y, 0.0),
                              door_leaf(w, d, height, door.get("swing"),
                                        nominal_width))
            run("spatial.assign_container", self.model, relating_structure=self.storey,
                products=[leaf])
            run("feature.add_filling", self.model, opening=opening, element=leaf)
            frame = self.boxes(
                "IfcMember", f"Door frame {door['id']}", (x, y, 0.0),
                door_frame(w, d, height),
            )
            run("spatial.assign_container", self.model, relating_structure=self.storey,
                products=[frame])
            swing = door.get("swing") or ["start", "+"]
            self.add_properties(leaf, "DoorLayout", {
                "DoorId": door["id"],
                "NominalLeafWidth": nominal_width,
                "NominalLeafHeight": height,
                "FrameMaterial": door.get("frame_material", "wood"),
                "HingeEnd": swing[0],
                "SwingSide": swing[1],
                "RenovationStatus": door.get("renovation_status"),
                "DesignNote": door.get("note"),
            })
            leaves += 1
        return openings, leaves, orphaned

    def build_windows(self):
        run = ifcopenshell.api.run
        placed = {"IfcWindow": 0, "IfcDoor": 0}
        orphaned = []
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

            ifc_class = win.get("ifc_class", "IfcWindow")
            name = "Drzwi" if ifc_class == "IfcDoor" else "Okno"
            panel_count = int(win.get("render_panels", 1 if ifc_class == "IfcDoor" else 2))
            leaf = self.boxes(ifc_class, f"{name} {win['id']}", (x, y, sill),
                              window_panes(w, d, height, panel_count))
            run("spatial.assign_container", self.model,
                relating_structure=self.storey, products=[leaf])
            run("feature.add_filling", self.model, opening=opening, element=leaf)
            frame = self.boxes(
                "IfcMember", f"Window frame {win['id']}", (x, y, sill),
                window_frame(w, d, height, panel_count),
            )
            handles = self.boxes(
                "IfcDiscreteAccessory", f"Window handles {win['id']}",
                (x, y, sill), window_handles(w, d, height, panel_count),
            )
            run("spatial.assign_container", self.model,
                relating_structure=self.storey, products=[frame, handles])
            self.add_properties(leaf, "WindowLayout", {
                "ApertureId": win["id"],
                "WindowType": win.get("window_type", "default"),
                "FrameMaterial": win.get("frame_material", "wood"),
                "RenderPanelCount": panel_count,
                "RenderHandles": True,
                "Room": str(win.get("room")) if win.get("room") is not None else None,
                "SillHeight": sill,
                "HeadHeight": head,
            })
            placed[ifc_class] = placed.get(ifc_class, 0) + 1
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
    b.build_spaces()
    b.build_columns_and_shafts()
    equipment, route_segments = b.build_equipment_and_routes()
    terminals = b.build_service_terminals_and_floor_data()
    finishes = b.build_wall_finishes()
    openings, placed, orphaned = b.build_doors()
    aperture_counts, win_orphaned = b.build_windows()
    b.write(dst)

    total_doors = placed + aperture_counts.get("IfcDoor", 0)
    print(f"[build_ifc] walls={len(b.walls)} openings={openings} doors={total_doors} "
          f"windows={aperture_counts.get('IfcWindow', 0)} spaces={len(data['rooms'])} "
          f"equipment={equipment} route_segments={route_segments} "
          f"service_terminals={terminals} wall_finishes={finishes}")
    if orphaned:
        print(f"[build_ifc] WARNING no host wall for doors: {orphaned}")
    if win_orphaned:
        print(f"[build_ifc] WARNING no host wall for windows: {win_orphaned}")
    print(f"[build_ifc] wrote {dst}")


if __name__ == "__main__":
    main()
