"""
Generate Bonsai/IFC annotations (room labels and dimension chains) on the
active PLAN_VIEW drawing.

Bonsai renders plans straight from the IFC - `create_drawing` runs an
ifcopenshell geometry iterator over the elements grouped into the drawing - so
annotations must exist as real `IfcAnnotation` entities. They are not a
rendering-time overlay.

`bpy.ops.bim.add_annotation` is used to create each annotation, because it also
wires up the annotation context, the drawing group and the collection. It only
ever produces a placeholder at a fixed offset from the camera though, so the
geometry is then rewritten directly in IFC:

  * placement  -> ifcopenshell.api geometry.edit_object_placement
  * curve      -> the IfcIndexedPolyCurve's coordinate list

Two traps this works around:
  * add_annotation leaves the new object in EDIT mode on a temporary
    `Item/...` sub-object, so `bpy.context.active_object` is *not* the
    annotation; the annotation is found by diffing bpy.data.objects.
  * the model is authored in millimetres, so metres must be divided by the
    project unit scale before being written into the coordinate list.

Imported by export_bonsai_drawings.py; requires an active drawing.
"""

import bpy
import numpy as np
from mathutils import Vector

import bonsai.tool as tool
from bonsai.bim.module.drawing.annotation import Annotator

from plan_symbols import door_swing_arc

# Where the dimension chains sit relative to the building, in metres.
DIM_OFFSET = 0.6     # inner chain, clear of the wall face
DIM_STEP = 0.6       # extra offset for each chain further out

# Ticks closer together than this are merged: at 1:50 a 100 mm tick is 2 mm on
# paper and its text cannot be read, and the overall chain covers it anyway.
MIN_TICK = 0.35

# Margin left around everything when framing the drawing, in metres.
FRAME_MARGIN = 0.6


def log(*a):
    print("[annotate]", *a, flush=True)


def polygon_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def polygon_centroid(poly):
    """Area centroid; falls back to the vertex mean for degenerate input."""
    a = cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-9:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a))


class Annotator2D:
    def __init__(self):
        self.aprops = tool.Drawing.get_annotation_props()
        self.ifc = tool.Ifc.get()
        self.z = Annotator.get_placeholder_coords(bpy.context.scene.camera)[0].z
        self.counts = {}

    # -- creation ---------------------------------------------------------
    def _add(self, object_type):
        """Create an annotation and return (object, IfcAnnotation)."""
        self.aprops.object_type = object_type
        self.aprops.relating_type_id = "0"
        before = set(bpy.data.objects)
        bpy.ops.bim.add_annotation()
        created = [o for o in bpy.data.objects if o not in before]

        # add_annotation enables item editing, which leaves us in EDIT mode on
        # a throwaway sub-object rather than on the annotation itself.
        active = bpy.context.active_object
        if active is not None and active.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        for obj in created:
            element = tool.Ifc.get_entity(obj)
            if element and element.is_a("IfcAnnotation"):
                self.counts[object_type] = self.counts.get(object_type, 0) + 1
                return obj, element
        raise RuntimeError(f"add_annotation produced no IfcAnnotation for {object_type}")

    # -- geometry ---------------------------------------------------------
    def _place(self, obj, element, x, y):
        matrix = np.eye(4)
        matrix[0][3], matrix[1][3], matrix[2][3] = x, y, self.z
        obj.matrix_world = matrix.T
        tool.Ifc.run("geometry.edit_object_placement", product=element,
                     matrix=matrix, is_si=True)


    def _set_curve(self, obj, points):
        """Rewrite the annotation's line to pass through `points` (metres, in
        model space).

        This has to be done on the *Blender* data, not on the IFC entity:
        `create_drawing(sync=True)` runs `IfcExporter.sync_all_objects()`
        first, which exports every Blender object over the IFC, so any direct
        edit of the IfcIndexedPolyCurve would be silently reverted.
        """
        inv = obj.matrix_world.inverted()
        local = [inv @ Vector((x, y, 0.0)) for x, y in points]
        data = obj.data

        if isinstance(data, bpy.types.Curve):
            data.splines.clear()
            spline = data.splines.new("POLY")
            spline.points.add(len(local) - 1)
            for point, co in zip(spline.points, local):
                point.co = (co.x, co.y, co.z, 1.0)
            return True

        if isinstance(data, bpy.types.Mesh):
            data.clear_geometry()
            data.from_pydata([tuple(co) for co in local],
                             [(i, i + 1) for i in range(len(local) - 1)], [])
            data.update()
            return True

        return False

    @staticmethod
    def _set_classes(element, classes):
        if not classes:
            return
        pset = tool.Ifc.run("pset.add_pset", product=element, name="EPset_Annotation")
        tool.Ifc.run("pset.edit_pset", pset=pset, properties={"Classes": classes})

    # -- annotation kinds -------------------------------------------------
    def text(self, at, lines, classes="regular", alignment="center"):
        """Multi-line label centred on `at` (model XY in metres). Bonsai stacks
        successive IfcTextLiterals on successive lines."""
        obj, element = self._add("TEXT")
        self._place(obj, element, at[0], at[1])
        tool.Drawing.edit_text_literals(
            obj,
            [{"Literal": line, "BoxAlignment": alignment, "Path": "RIGHT"}
             for line in lines],
        )
        self._set_classes(element, classes)
        return obj

    def dimension(self, p1, p2, classes=""):
        """Dimension between two model-space XY points. Bonsai measures the
        line itself, so no text is supplied."""
        obj, element = self._add("DIMENSION")
        self._place(obj, element, 0.0, 0.0)
        if not self._set_curve(obj, [p1, p2]):
            raise RuntimeError("DIMENSION annotation has unsupported geometry data")
        self._set_classes(element, classes)
        return obj

    def polyline(self, points, classes=""):
        """An open polyline through model-space XY points, drawn as plain
        linework (used for door swing arcs)."""
        obj, element = self._add("LINEWORK")
        self._place(obj, element, 0.0, 0.0)
        if not self._set_curve(obj, points):
            raise RuntimeError("LINEWORK annotation has unsupported geometry data")
        self._set_classes(element, classes)
        return obj

    def chain(self, ordinates, axis, offset, min_gap=MIN_TICK):
        """Running dimension chain along `axis` ("x" or "y") at `offset` on the
        other axis. Ordinates closer together than `min_gap` are merged."""
        pts = []
        for p in sorted(set(round(o, 4) for o in ordinates)):
            if not pts or p - pts[-1] >= min_gap:
                pts.append(p)
            else:
                pts[-1] = p
        for a, b in zip(pts, pts[1:]):
            if axis == "x":
                self.dimension((a, offset), (b, offset))
            else:
                self.dimension((offset, a), (offset, b))
        return len(pts) - 1


def _label_anchor(room):
    """Where the room label goes. The open space wraps the storage island, so
    its area centroid can land inside the island; such rooms override the
    anchor via `label_at` in the data file."""
    if room.get("label_at"):
        return tuple(room["label_at"])
    return polygon_centroid(room["polygon"])


def _room_area(room, by_id):
    area = polygon_area(room["polygon"])
    for hole in room.get("subtract", []):
        other = by_id[hole]
        area -= polygon_area(other.get("footprint") or other["polygon"])
    return area


def annotate(data):
    """Create every annotation for the plan described by `data`."""
    ann = Annotator2D()
    by_id = {r["id"]: r for r in data["rooms"]}

    for room in data["rooms"]:
        ann.text(
            _label_anchor(room),
            [f"{room['id']}. {room['name']}", f"{_room_area(room, by_id):.2f} m2"],
        )
    log("room labels:", len(data["rooms"]))

    # Door swing arcs. The leaf solid is built by build_ifc.py from the same
    # swing data, so arc and leaf always agree.
    leaf_doors = [door for door in data.get("doors", [])
                  if door.get("has_leaf", True)]
    for door in leaf_doors:
        ann.polyline(door_swing_arc(door["at"], door["size"], door.get("swing")),
                     classes="thin")
    log("swing arcs:", len(leaf_doors))

    outline = data["outline"]
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    # Outer chains: overall envelope, south and east.
    ann.dimension((x0, y0 - DIM_OFFSET - DIM_STEP), (x1, y0 - DIM_OFFSET - DIM_STEP))
    ann.dimension((x1 + DIM_OFFSET + DIM_STEP, y0), (x1 + DIM_OFFSET + DIM_STEP, y1))

    # Inner chains: the ordinates the rooms actually generate, so the chain
    # reads as a structural grid rather than an arbitrary set of ticks.
    south_x = {x0, x1}
    for room in data["rooms"]:
        if room["id"] in (5, 6, 7):
            south_x.update(round(p[0], 3) for p in room["polygon"])
    log("south chain segments:", ann.chain(south_x, "x", y0 - DIM_OFFSET))

    west_y = {y0, y1}
    for room in data["rooms"]:
        if room["id"] in (5, 4, 123):
            west_y.update(round(p[1], 3) for p in room["polygon"])
    log("west chain segments:", ann.chain(west_y, "y", x0 - DIM_OFFSET))

    log("created:", ann.counts)

    # Everything the sheet has to contain: the building plus the outermost
    # dimension chain, plus a margin. The export script frames the drawing
    # camera on this, otherwise Bonsai keeps its default 50 m view and the
    # plan lands far outside the sheet.
    outer = DIM_OFFSET + DIM_STEP
    bounds = (x0 - outer - FRAME_MARGIN, y0 - outer - FRAME_MARGIN,
              x1 + outer + FRAME_MARGIN, y1 + FRAME_MARGIN)
    log("bounds:", tuple(round(v, 2) for v in bounds))
    return ann.counts, bounds
