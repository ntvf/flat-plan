"""Render per-room top-down and bird's-eye views of the furnished target model.

    /snap/bin/blender -b --python scripts/render_room_views.py -- \
        exports/target.ifc build/target.json exports/rooms/renders [slug,slug...]

Architecture comes from the IFC (Bonsai); furniture is rebuilt here with
more detail from the same model data, so renders match the room sheets.
"""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import room_views as rv  # noqa: E402
from render_textured_views import (  # noqa: E402
    argv_after_dashes, assign_material, assign_wall_uv, brick_material, look_at,
)

TOP_PX = 1800
BIRD_PX = (1600, 1100)


def material(name, colour, roughness=0.6, metallic=0.0, alpha=1.0):
    """Principled material, optionally translucent."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*colour, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    if alpha < 1.0:
        shader.inputs["Alpha"].default_value = alpha
    return mat


def wall_material():
    """Warm white sides, charcoal tops so walls read as a plan from above."""
    mat = material("Wall", (0.86, 0.84, 0.80), 0.85)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    geometry = nodes.new("ShaderNodeNewGeometry")
    split = nodes.new("ShaderNodeSeparateXYZ")
    top = nodes.new("ShaderNodeMath")
    top.operation = "GREATER_THAN"
    top.inputs[1].default_value = 0.9
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (0.86, 0.84, 0.80, 1.0)
    mix.inputs["B"].default_value = (0.16, 0.17, 0.19, 1.0)
    links.new(geometry.outputs["True Normal"], split.inputs["Vector"])
    links.new(split.outputs["Z"], top.inputs[0])
    links.new(top.outputs["Value"], mix.inputs["Factor"])
    links.new(mix.outputs["Result"], shader.inputs["Base Color"])
    return mat


def pattern_material(name, colour1, colour2, mortar, width, row, mortar_size):
    """Plank or tile floor from a brick texture in world (object) coordinates."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = 0.55
    coords = nodes.new("ShaderNodeTexCoord")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (*colour1, 1.0)
    brick.inputs["Color2"].default_value = (*colour2, 1.0)
    brick.inputs["Mortar"].default_value = (*mortar, 1.0)
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = mortar_size
    brick.inputs["Brick Width"].default_value = width
    brick.inputs["Row Height"].default_value = row
    links.new(coords.outputs["Object"], brick.inputs["Vector"])
    links.new(brick.outputs["Color"], shader.inputs["Base Color"])
    return mat


# ---------------------------------------------------------------- finishes

def srgb(hex_colour, factor=1.0):
    """Hex sRGB -> linear RGB for shader inputs."""
    h = hex_colour.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = min(1.0, int(h[i:i + 2], 16) / 255 * factor)
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def finish_material(name, spec, origin=None):
    """Tile/plank finish whose joints sit where the setting-out puts them.

    Floors use object (= world) coordinates shifted by the zone origin; wall
    faces use a UV map that already starts at a joint. Beige tiles get a faint
    scratch texture, feature tiles a procedural motif."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = 0.5 if spec["kind"] == "plank" else 0.35
    coords = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    comb = nodes.new("ShaderNodeCombineXYZ")
    vec = coords.outputs["UV" if origin is None and not spec.get("box") else "Object"]
    if origin is not None:
        shift = nodes.new("ShaderNodeVectorMath")
        shift.operation = "SUBTRACT"
        shift.inputs[1].default_value = (origin[0], origin[1], 0.0)
        links.new(vec, shift.inputs[0])
        vec = shift.outputs["Vector"]
    links.new(vec, sep.inputs[0])
    w, h = spec["size"]
    plank = spec["kind"] == "plank"
    if spec.get("box"):
        # Tiled boxes: along-face (x + y) by height, so every vertical face tiles.
        along = nodes.new("ShaderNodeMath")
        along.operation = "ADD"
        links.new(sep.outputs["X"], along.inputs[0])
        links.new(sep.outputs["Y"], along.inputs[1])
        links.new(along.outputs["Value"], comb.inputs["X"])
        links.new(sep.outputs["Z"], comb.inputs["Y"])
    elif plank:
        # Planks run N-S: lay the brick texture along Y.
        links.new(sep.outputs["Y"], comb.inputs["X"])
        links.new(sep.outputs["X"], comb.inputs["Y"])
        w, h = h, w
    else:
        links.new(sep.outputs["X"], comb.inputs["X"])
        links.new(sep.outputs["Y"], comb.inputs["Y"])

    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5 if plank else 0.0
    brick.offset_frequency = 2
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Brick Width"].default_value = w
    brick.inputs["Row Height"].default_value = h
    brick.inputs["Mortar Size"].default_value = 0.0015 if plank else 0.002
    brick.inputs["Bias"].default_value = 0.0
    brick.inputs["Color1"].default_value = (*srgb(spec["colour"], 0.93 if plank else 0.98), 1.0)
    brick.inputs["Color2"].default_value = (*srgb(spec["colour"], 1.06 if plank else 1.02), 1.0)
    brick.inputs["Mortar"].default_value = (*srgb(spec["colour"], 0.62 if plank else 0.80), 1.0)
    links.new(comb.outputs["Vector"], brick.inputs["Vector"])
    colour = brick.outputs["Color"]

    motif = spec.get("motif")
    if motif in ("leaves", "circles"):
        # Local tile coordinates (0..w, 0..h) -> motif mask.
        local = []
        for axis, size in (("X", w), ("Y", h)):
            mod = nodes.new("ShaderNodeMath")
            mod.operation = "FLOORED_MODULO"
            mod.inputs[1].default_value = size
            links.new(sep.outputs[axis], mod.inputs[0])
            local.append(mod)
        lc = nodes.new("ShaderNodeCombineXYZ")
        links.new(local[0].outputs[0], lc.inputs["X"])
        links.new(local[1].outputs[0], lc.inputs["Y"])
        ramp = nodes.new("ShaderNodeValToRGB")
        if motif == "circles":
            d = nodes.new("ShaderNodeVectorMath")
            d.operation = "DISTANCE"
            d.inputs[1].default_value = (w / 2, h / 2, 0.0)
            links.new(lc.outputs["Vector"], d.inputs[0])
            wave = nodes.new("ShaderNodeMath")
            wave.operation = "SINE"
            mul = nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            mul.inputs[1].default_value = 2 * math.pi / 0.12
            links.new(d.outputs["Value"], mul.inputs[0])
            links.new(mul.outputs[0], wave.inputs[0])
            fac = wave.outputs[0]
            ramp.color_ramp.elements[0].position = 0.80
            ramp.color_ramp.elements[0].color = (*srgb("#e8dcc6"), 1.0)
            ramp.color_ramp.elements[1].position = 0.88
            ramp.color_ramp.elements[1].color = (*srgb("#b89468"), 1.0)
        else:
            voro = nodes.new("ShaderNodeTexVoronoi")
            voro.feature = "DISTANCE_TO_EDGE"
            voro.inputs["Scale"].default_value = 3.2
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 4.0
            mix = nodes.new("ShaderNodeVectorMath")
            mix.operation = "MULTIPLY_ADD"
            mix.inputs[1].default_value = (0.25, 0.25, 0.0)
            links.new(noise.outputs["Color"], mix.inputs[0])
            links.new(lc.outputs["Vector"], mix.inputs[2])
            links.new(mix.outputs["Vector"], voro.inputs["Vector"])
            links.new(lc.outputs["Vector"], noise.inputs["Vector"])
            fac = voro.outputs["Distance"]
            ramp.color_ramp.elements[0].position = 0.02
            ramp.color_ramp.elements[0].color = (*srgb("#e6eadb"), 1.0)
            ramp.color_ramp.elements[1].position = 0.06
            ramp.color_ramp.elements[1].color = (*srgb(spec["colour"]), 1.0)
            ramp.color_ramp.elements.new(0.30).color = (*srgb(spec["colour"], 0.72), 1.0)
        links.new(fac, ramp.inputs["Fac"])
        # Keep the joints from the brick texture: multiply motif by a joint mask.
        mask = nodes.new("ShaderNodeMix")
        mask.data_type = "RGBA"
        mask.blend_type = "MULTIPLY"
        mask.inputs["Factor"].default_value = 1.0
        links.new(ramp.outputs["Color"], mask.inputs["A"])
        joints = nodes.new("ShaderNodeTexBrick")
        joints.offset = 0.0
        joints.inputs["Scale"].default_value = 1.0
        joints.inputs["Brick Width"].default_value = w
        joints.inputs["Row Height"].default_value = h
        joints.inputs["Mortar Size"].default_value = 0.002
        joints.inputs["Color1"].default_value = (1, 1, 1, 1)
        joints.inputs["Color2"].default_value = (1, 1, 1, 1)
        joints.inputs["Mortar"].default_value = (0.7, 0.7, 0.7, 1)
        links.new(comb.outputs["Vector"], joints.inputs["Vector"])
        links.new(joints.outputs["Color"], mask.inputs["B"])
        colour = mask.outputs["Result"]
    elif not plank and spec.get("scratched", True):
        # Faint directional scratches on the beige/green glazes.
        stretch = nodes.new("ShaderNodeMapping")
        stretch.inputs["Scale"].default_value = (90.0, 4.0, 1.0)
        stretch.inputs["Rotation"].default_value = (0.0, 0.0, 0.5)
        links.new(comb.outputs["Vector"], stretch.inputs["Vector"])
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 1.0
        noise.inputs["Detail"].default_value = 4.0
        links.new(stretch.outputs["Vector"], noise.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.62
        ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
        ramp.color_ramp.elements[1].position = 0.70
        ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "SCREEN"
        mix.inputs["Factor"].default_value = 0.10
        links.new(brick.outputs["Color"], mix.inputs["A"])
        links.new(ramp.outputs["Color"], mix.inputs["B"])
        colour = mix.outputs["Result"]
    elif plank:
        grain = nodes.new("ShaderNodeTexWave")
        grain.wave_type = "BANDS"
        grain.bands_direction = "Y"
        grain.inputs["Scale"].default_value = 18.0
        grain.inputs["Distortion"].default_value = 1.5
        grain.inputs["Detail"].default_value = 3.0
        links.new(comb.outputs["Vector"], grain.inputs["Vector"])
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 0.07
        links.new(brick.outputs["Color"], mix.inputs["A"])
        links.new(grain.outputs["Color"], mix.inputs["B"])
        colour = mix.outputs["Result"]
    links.new(colour, shader.inputs["Base Color"])
    return mat


def face_mesh(name, pieces, to3d, uv_of, mat):
    """Flat mesh from 2-D trapezoids mapped into 3-D, with a UV layer."""
    verts, faces, uvs = [], [], []
    for quad in pieces:
        idx = []
        for p in quad:
            verts.append(to3d(p))
            uvs.append(uv_of(p))
            idx.append(len(verts) - 1)
        faces.append(idx)
    obj = add_mesh(name, verts, faces, mat)
    layer = obj.data.uv_layers.new(name="UVMap")
    for poly in obj.data.polygons:
        for li in poly.loop_indices:
            layer.data[li].uv = uvs[obj.data.loops[li].vertex_index]
    return obj


FLOOR_Z = 0.021
CLAD = 0.006


def build_finishes(model):
    """Finished floors, bathroom wall tiling and kitchen splash-back."""
    import finishes as fin
    spec = model["finishes"]
    mats = {}

    def mat_for(key, origin=None):
        tag = (key, origin)
        if tag not in mats:
            entry = dict(spec["materials"][key])
            entry.setdefault("motif", {"tile_leaves": "leaves", "tile_circles": "circles"}.get(key))
            mats[tag] = finish_material(f"Finish {key} {origin or ''}", entry, origin)
        return mats[tag]

    for zone in fin.floors(model):
        region = zone["region"]
        pieces = region.trapezoids(*region.bbox())
        origin = tuple(zone.get("origin", (0.0, 0.0)))
        face_mesh(f"Finish floor {zone['id']}", pieces, lambda p: (p[0], p[1], FLOOR_Z),
                  lambda p: (p[0], p[1]), mat_for(zone["material"], origin))

    def wall_surface(name, start, end, normal, z0, entry, top):
        (sx, sy), (ex, ey) = start, end
        ux, uy = (ex - sx), (ey - sy)
        n = math.hypot(ux, uy)
        ux, uy = ux / n, uy / n
        ox, oy = normal[0] * CLAD, normal[1] * CLAD
        clip = min(top - z0, rv.CUT_HEIGHT - z0)
        pieces = entry["region"].trapezoids(0.0, 0.0, n, clip)
        ou, oz = entry["origin"], entry.get("origin_z", 0.0)
        face_mesh(name, pieces,
                  lambda p: (sx + ux * p[0] + ox, sy + uy * p[0] + oy, z0 + p[1]),
                  lambda p: (p[0] - ou, p[1] - oz), mat_for(entry["material"]))

    for entry in fin.walls(model):
        face = entry["face"]
        wall_surface(f"Finish wall {entry['room']}-{entry['index']}", face["start"], face["end"],
                     face["normal"], FLOOR_Z, entry, entry["height"])

    open_room = fin.room_region(model, 123)
    for entry in fin.splash(model):
        a, b = entry["segment"]["from"], entry["segment"]["to"]
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy)
        normal = (-dy / n, dx / n)
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        if not open_room.contains(mx + normal[0] * 0.05, my + normal[1] * 0.05):
            normal = (-normal[0], -normal[1])
        # Seen from the room, the face runs with the room on its left-hand normal side.
        wall_surface(f"Finish splash {entry['id']}", a, b, normal, entry["base"], entry, entry["top"])


def make_materials():
    m = {
        "wall": wall_material(),
        "frame": material("Window frame", (0.92, 0.92, 0.90), 0.4),
        "glass_arch": material("Window glass", (0.55, 0.72, 0.85), 0.05, alpha=0.35),
        "door": material("Door leaf", (0.93, 0.92, 0.88), 0.5),
        "shaft": material("Shaft casing", (0.70, 0.71, 0.70), 0.8),
        "column": material("Column", (0.55, 0.55, 0.55), 0.8),
        "equipment": material("Equipment", (0.95, 0.95, 0.95), 0.35),
        "wood_floor": pattern_material("Oak planks", (0.62, 0.45, 0.28), (0.55, 0.39, 0.23),
                                       (0.45, 0.32, 0.19), 1.20, 0.18, 0.002),
        "tile_floor": pattern_material("Floor tiles 60x60", (0.74, 0.74, 0.72), (0.70, 0.70, 0.68),
                                       (0.55, 0.55, 0.53), 0.60, 0.60, 0.003),
        "white": material("Matt white", (0.92, 0.92, 0.90), 0.55),
        "front": material("Kitchen fronts", (0.30, 0.36, 0.33), 0.5),
        "oak": material("Oak", (0.60, 0.43, 0.25), 0.5),
        "stone": material("Quartz worktop", (0.86, 0.85, 0.82), 0.35),
        "walnut": material("Walnut", (0.33, 0.21, 0.13), 0.5),
        "dark": material("Dark", (0.08, 0.08, 0.09), 0.3),
        "black_glass": material("Black glass", (0.02, 0.02, 0.025), 0.12),
        "ring": material("Hob ring", (0.35, 0.35, 0.37), 0.3),
        "steel": material("Steel", (0.75, 0.76, 0.78), 0.25, 0.9),
        "ceramic": material("Ceramic", (0.97, 0.97, 0.97), 0.15),
        "fridge": material("Fridge", (0.82, 0.83, 0.84), 0.3, 0.3),
        "fabric": material("Sofa fabric", (0.42, 0.47, 0.50), 0.9),
        "cushion": material("Cushion", (0.52, 0.57, 0.60), 0.9),
        "linen": material("Bed linen", (0.95, 0.94, 0.91), 0.9),
        "duvet": material("Duvet", (0.62, 0.68, 0.72), 0.9),
        "glass": material("Shower glass", (0.70, 0.85, 0.92), 0.05, alpha=0.35),
        "tile_box": material("Tiled box", (0.84, 0.78, 0.68), 0.45),
        "shelf": material("Shelf", (0.80, 0.70, 0.55), 0.6),
        "brick": brick_material(),
    }
    for key in ("glass", "glass_arch"):
        m[key].surface_render_method = "BLENDED"
    return m


# --------------------------------------------------------------------- mesh

def add_mesh(name, verts, faces, mat):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def box(name, rect, z0, z1, mat):
    x0, y0, x1, y1 = rect
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return add_mesh(name, verts, faces, mat)


def prism(name, polygon, z0, z1, mat):
    bm = bmesh.new()
    bottom = [bm.verts.new((x, y, z0)) for x, y in polygon]
    face = bm.faces.new(bottom)
    bmesh.ops.reverse_faces(bm, faces=[face])
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    top_verts = [v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top_verts, vec=(0, 0, z1 - z0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def ellipse(name, cx, cy, rx, ry, z0, z1, mat, segments=40):
    poly = [(cx + rx * math.cos(2 * math.pi * i / segments),
             cy + ry * math.sin(2 * math.pi * i / segments)) for i in range(segments)]
    return prism(name, poly, z0, z1, mat)


def inset(rect, d):
    x0, y0, x1, y1 = rect
    return x0 + d, y0 + d, x1 - d, y1 - d


def centre(rect):
    return (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2


# ---------------------------------------------------------------- furniture

def base_unit(item, back, m, top=0.90):
    rect = rv.item_rect(item)
    box(f"{item['id']} carcass", rv.local_box(item, back, 0.0, along_depth(item, back)[0], 0.0,
                                              along_depth(item, back)[1] - 0.02), 0.0, top - 0.04, m["front"])
    box(f"{item['id']} worktop", rect, top - 0.04, top, m["stone"])
    return rect


def along_depth(item, back):
    return rv.along_depth(item, back)


def build_item(item, model, m):
    before = set(bpy.data.objects)
    build_parts(item, model, m)
    return [obj for obj in bpy.data.objects if obj not in before]


def build_parts(item, model, m):
    kind, iid = item["kind"], item["id"]
    height = float(item["size"][2])
    if item.get("polygon"):
        prism(f"{iid} carcass", item["polygon"], 0.0, height - 0.04, m["front"])
        prism(f"{iid} worktop", item["polygon"], height - 0.04, height, m["stone"])
        return
    back = rv.item_back(item, model)
    L, D = along_depth(item, back)
    lb = lambda u0, u1, v0, v1: rv.local_box(item, back, u0, u1, v0, v1)  # noqa: E731
    rect = rv.item_rect(item)

    if kind in ("worktop", "dishwasher"):
        base_unit(item, back, m, height)
    elif kind == "hob":
        base_unit(item, back, m, height)
        glass = lb(0.02, L - 0.02, 0.05, D - 0.05)
        box(f"{iid} hob", glass, height, height + 0.006, m["black_glass"])
        gx0, gy0, gx1, gy1 = glass
        for i, (fx, fy, r) in enumerate(((0.28, 0.28, 0.10), (0.72, 0.28, 0.08),
                                         (0.28, 0.72, 0.08), (0.72, 0.72, 0.10))):
            ellipse(f"{iid} ring {i}", gx0 + (gx1 - gx0) * fx, gy0 + (gy1 - gy0) * fy, r, r,
                    height + 0.006, height + 0.008, m["ring"])
    elif kind == "sink":
        base_unit(item, back, m, height)
        box(f"{iid} bowl", lb(0.06, L - 0.06, 0.12, D - 0.06), height, height + 0.004, m["steel"])
        cx, cy = centre(lb(L / 2 - 0.03, L / 2 + 0.03, 0.03, 0.09))
        ellipse(f"{iid} tap", cx, cy, 0.025, 0.025, height, height + 0.30, m["steel"])
    elif kind == "oven_tower":
        box(iid, rect, 0.0, height, m["front"])
        box(f"{iid} column", rect, height, 2.40, m["front"])
        box(f"{iid} oven", lb(0.03, L - 0.03, D - 0.01, D + 0.005), 0.80, 1.40, m["black_glass"])
        box(f"{iid} microwave", lb(0.03, L - 0.03, D - 0.01, D + 0.005), 1.42, 1.80, m["dark"])
    elif kind == "fridge":
        box(iid, rect, 0.0, height, m["fridge"])
        box(f"{iid} column", rect, height, 2.40, m["front"])
    elif kind in ("closet", "wardrobe"):
        box(iid, rect, 0.0, height, m["white"])
        for k in range(1, max(2, round(L / 0.6))):
            u = L * k / max(2, round(L / 0.6))
            box(f"{iid} joint {k}", lb(u - 0.003, u + 0.003, D - 0.01, D), 0.05, height - 0.02, m["dark"])
    elif kind == "shelving":
        for k, z in enumerate((0.30, 0.75, 1.20, 1.65, 2.10)):
            box(f"{iid} shelf {k}", rect, z, z + 0.025, m["shelf"])
        for u in (0.0, L - 0.02):
            box(f"{iid} side", lb(u, u + 0.02, 0.0, D), 0.0, height, m["shelf"])
    elif kind in ("table", "desk", "coffee_table"):
        top = height
        box(f"{iid} top", rect, top - 0.03, top, m["oak"])
        for lx, ly in ((0, 0), (1, 0), (0, 1), (1, 1)):
            x = rect[0] + 0.04 + lx * (rect[2] - rect[0] - 0.12)
            y = rect[1] + 0.04 + ly * (rect[3] - rect[1] - 0.12)
            box(f"{iid} leg", (x, y, x + 0.04, y + 0.04), 0.0, top - 0.03, m["walnut"])
    elif kind == "chair":
        box(f"{iid} seat", inset(rect, 0.02), 0.43, 0.46, m["walnut"])
        box(f"{iid} back", lb(0.04, L - 0.04, 0.02, 0.06), 0.46, height, m["walnut"])
        for u, v in ((0.04, 0.04), (L - 0.08, 0.04), (0.04, D - 0.08), (L - 0.08, D - 0.08)):
            box(f"{iid} leg", lb(u, u + 0.04, v, v + 0.04), 0.0, 0.43, m["walnut"])
    elif kind == "sideboard":
        box(iid, rect, 0.10, height, m["walnut"])
    elif kind == "sofa" and rv.l_shape(item, model):
        (c0, c1), seat = rv.l_shape(item, model)
        outer = 0.0 if c0 < 1e-9 else L - 0.18
        other = L - 0.18 if outer == 0.0 else 0.0
        for k, part in enumerate(rv.item_boxes(item, model)):
            box(f"{iid} base {k}", part, 0.08, 0.40, m["fabric"])
        box(f"{iid} back", lb(0.0, L, 0.0, 0.22), 0.40, height, m["fabric"])
        box(f"{iid} arm", lb(outer, outer + 0.18, 0.0, D), 0.40, 0.62, m["fabric"])
        box(f"{iid} arm", lb(other, other + 0.18, 0.0, seat), 0.40, 0.62, m["fabric"])
        s0, s1 = 0.18, L - 0.18
        n = 2
        for k in range(n):
            u0 = s0 + (s1 - s0) * k / n
            box(f"{iid} cushion {k}", lb(u0 + 0.01, u0 + (s1 - s0) / n - 0.01, 0.22, seat - 0.02),
                0.40, 0.47, m["cushion"])
        cu0, cu1 = (max(c0, 0.18), min(c1, L - 0.18))
        box(f"{iid} chaise", lb(cu0 + 0.01, cu1 - 0.01, seat, D - 0.02), 0.40, 0.47, m["cushion"])
    elif kind == "sofa":
        box(f"{iid} base", rect, 0.08, 0.40, m["fabric"])
        box(f"{iid} back", lb(0.0, L, 0.0, 0.22), 0.40, height, m["fabric"])
        for u in (0.0, L - 0.18):
            box(f"{iid} arm", lb(u, u + 0.18, 0.0, D), 0.40, 0.62, m["fabric"])
        n = 2
        for k in range(n):
            u0 = 0.18 + (L - 0.36) * k / n
            box(f"{iid} cushion {k}", lb(u0 + 0.01, u0 + (L - 0.36) / n - 0.01, 0.22, D - 0.02),
                0.40, 0.47, m["cushion"])
    elif kind == "tv_unit":
        box(iid, lb(0.0, L, 0.0, D), 0.10, height, m["walnut"])
        box(f"{iid} tv", lb(0.05, L - 0.05, 0.0, 0.04), 0.85, 1.50, m["dark"])
    elif kind == "bath":
        if item.get("panel") == "tiled":
            box(f"{iid} panel", rect, 0.0, height - 0.03, m["tile_box"])
            box(iid, rect, height - 0.03, height, m["ceramic"])
        else:
            box(iid, rect, 0.0, height, m["ceramic"])
        tub = inset(rect, 0.08)
        box(f"{iid} tub", tub, height, height + 0.003, m["steel"])
        ellipse(f"{iid} water", *centre(tub), (tub[2] - tub[0]) / 2 - 0.02,
                (tub[3] - tub[1]) / 2 - 0.02, height + 0.003, height + 0.005, m["ceramic"])
    elif kind == "basin":
        if item.get("wall_hung"):
            box(f"{iid} body", lb(0.0, L, 0.0, D), height - 0.15, height, m["ceramic"])
        else:
            box(f"{iid} vanity", lb(0.0, L, 0.0, D - 0.02), 0.20, height - 0.05, m["oak"])
            box(f"{iid} top", rect, height - 0.05, height, m["ceramic"])
        cx, cy = centre(lb(0.05, L - 0.05, 0.12, D - 0.05))
        rx, ry = ((L - 0.14) / 2, (D - 0.20) / 2) if back in ("N", "S") else ((D - 0.20) / 2, (L - 0.14) / 2)
        ellipse(f"{iid} bowl", cx, cy, rx, ry, height, height + 0.004, m["steel"])
        tx, ty = centre(lb(L / 2 - 0.02, L / 2 + 0.02, 0.03, 0.07))
        ellipse(f"{iid} tap", tx, ty, 0.02, 0.02, height, height + 0.20, m["steel"])
    elif kind == "wc" and item.get("wall_hung"):
        cx, cy = centre(lb(0.0, L, 0.0, D))
        rx, ry = ((L / 2 - 0.01), D / 2 - 0.01) if back in ("N", "S") else (D / 2 - 0.01, L / 2 - 0.01)
        ellipse(f"{iid} bowl", cx, cy, rx, ry, 0.22, height, m["ceramic"])
        box(f"{iid} neck", lb(L / 2 - 0.12, L / 2 + 0.12, 0.0, 0.20), 0.22, height, m["ceramic"])
        ellipse(f"{iid} seat", cx, cy, rx - 0.04, ry - 0.05, height, height + 0.01, m["steel"])
    elif kind == "install_box":
        box(iid, rect, 0.0, height, m["tile_box"])
        if item.get("flush_u") is not None:
            u = item["flush_u"]
            box(f"{iid} flush", lb(u - 0.12, u + 0.12, D, D + 0.01), 1.00, 1.16, m["steel"])
    elif kind == "shower_floor":
        box(f"{iid} drain", lb(0.08, L - 0.08, 0.03, 0.09), 0.021, 0.026, m["steel"])
        cx, cy = centre(lb(L / 2 - 0.04, L / 2 + 0.04, 0.0, 0.04))
        ellipse(f"{iid} mixer", cx, cy, 0.03, 0.03, 1.00, 1.10, m["steel"])
        box(f"{iid} rain", lb(L / 2 - 0.15, L / 2 + 0.15, 0.15, 0.45), 2.10, 2.12, m["steel"])
    elif kind == "wc":
        box(f"{iid} cistern", lb(0.02, L - 0.02, 0.0, 0.16), 0.0, 0.80, m["white"])
        cx, cy = centre(lb(0.0, L, 0.16, D))
        rx, ry = ((L / 2 - 0.02), (D - 0.16) / 2) if back in ("N", "S") else ((D - 0.16) / 2, L / 2 - 0.02)
        ellipse(f"{iid} bowl", cx, cy, rx, ry, 0.0, height, m["ceramic"])
        ellipse(f"{iid} seat", cx, cy, rx - 0.05, ry - 0.06, height, height + 0.01, m["steel"])
    elif kind == "washer" and item.get("stacked"):
        for k, (z0, z1) in enumerate(((0.0, 0.85), (0.90, height))):
            box(f"{iid} unit {k}", rect, z0, z1, m["ceramic"])
            box(f"{iid} panel {k}", lb(0.03, L - 0.03, 0.02, 0.10), z1, z1 + 0.004, m["dark"])
        box(f"{iid} kit", inset(rect, 0.02), 0.85, 0.90, m["steel"])
    elif kind == "washer":
        box(iid, rect, 0.0, height, m["ceramic"])
        box(f"{iid} panel", lb(0.03, L - 0.03, 0.02, 0.10), height, height + 0.004, m["dark"])
    elif kind == "shower_tray" and item.get("tiled"):
        # Tile-ready tray: the floor tiles run over it, only the linear drain shows.
        box(f"{iid} drain", lb(0.08, L - 0.08, D - 0.10, D - 0.04), 0.004, 0.008, m["steel"])
    elif kind == "shower_tray":
        box(iid, rect, 0.0, height, m["ceramic"])
        ellipse(f"{iid} drain", *centre(rect), 0.05, 0.05, height, height + 0.003, m["steel"])
    elif kind == "glass":
        box(iid, rect, 0.05, height, m["glass"])
    elif kind == "bed":
        box(f"{iid} frame", rect, 0.05, 0.30, m["oak"])
        box(f"{iid} headboard", lb(0.0, L, 0.0, 0.06), 0.05, 1.00, m["oak"])
        box(f"{iid} mattress", lb(0.02, L - 0.02, 0.06, D - 0.02), 0.30, 0.50, m["linen"])
        box(f"{iid} duvet", lb(0.0, L, 0.65, D), 0.50, 0.54, m["duvet"])
        for k in range(2):
            u0 = 0.08 + k * (L - 0.16) / 2
            box(f"{iid} pillow {k}", lb(u0 + 0.03, u0 + (L - 0.16) / 2 - 0.03, 0.12, 0.55), 0.50, 0.62,
                m["linen"])
    elif kind == "nightstand":
        box(iid, rect, 0.0, height, m["oak"])
    else:
        raise ValueError(f"no render builder for kind {kind!r} ({iid})")


# ---------------------------------------------------------------- scene

def classify_ifc(m, rooms, finished=()):
    for obj in list(bpy.context.scene.objects):
        name = obj.name
        cls = name.split("/", 1)[0]
        if obj.type != "MESH":
            continue
        if cls in ("IfcFurniture", "IfcSanitaryTerminal", "IfcElectricAppliance",
                   "IfcPipeSegment", "IfcAnnotation", "IfcOpeningElement"):
            obj.hide_render = True
        elif cls == "IfcSpace":
            room_id = name.split("/", 1)[1].split()[0]
            function = rooms.get(room_id, {}).get("function")
            if room_id in finished:
                obj.hide_render = True
                continue
            assign_material(obj, m["tile_floor" if function == "bathroom" else "wood_floor"])
            if function == "bathroom":
                # Bathroom 2 is carved out of the living space: lift it clear of z-fighting.
                obj.location.z += 0.003
        elif name.startswith("IfcCovering/BRICK_"):
            assign_material(obj, m["brick"])
            assign_wall_uv(obj)
        elif cls == "IfcWall":
            assign_material(obj, m["wall"])
        elif cls == "IfcWindow":
            assign_material(obj, m["glass_arch"])
        elif cls == "IfcDoor":
            assign_material(obj, m["glass_arch"] if ("OB2" in name or "DK6" in name) else m["door"])
        elif cls == "IfcColumn":
            assign_material(obj, m["column"])
        elif cls == "IfcBuildingElementProxy":
            assign_material(obj, m["shaft"])
        elif cls in ("IfcUnitaryEquipment", "IfcTank"):
            assign_material(obj, m["equipment"])
        else:
            obj.hide_render = True


def add_cut_box():
    """Boolean cutter removing architecture above CUT_HEIGHT (bird's-eye views)."""
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    cutter = bpy.context.active_object
    cutter.name = "Section cutter"
    cutter.scale = (200.0, 200.0, 20.0)
    cutter.location = (0.0, 0.0, rv.CUT_HEIGHT + 10.0)
    cutter.hide_render = True
    cutter.hide_viewport = True
    mods = []
    for obj in bpy.context.scene.objects:
        cls = obj.name.split("/", 1)[0]
        if obj.type != "MESH" or obj.hide_render or obj is cutter:
            continue
        if cls in ("IfcWall", "IfcColumn", "IfcBuildingElementProxy", "IfcWindow",
                   "IfcDoor", "IfcCovering", "IfcUnitaryEquipment"):
            mod = obj.modifiers.new("Section cut", "BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.solver = "EXACT"
            mod.object = cutter
            mods.append(mod)
    return mods


def configure_scene():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_percentage = 100
    scene.eevee.taa_render_samples = 32
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.0
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.96, 0.96, 0.95, 1.0)
    background.inputs["Strength"].default_value = 0.7

    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.2
    sun.angle = math.radians(12)
    sun_obj = bpy.data.objects.new("Sun", sun)
    scene.collection.objects.link(sun_obj)
    return sun_obj


def render(path, camera, resolution):
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print(f"[render_room_views] wrote {path}")


def main():
    args = argv_after_dashes()
    ifc, json_path, out_dir = args[:3]
    only = set(args[3].split(",")) if len(args) > 3 else None
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    model = json.loads(Path(json_path).read_text(encoding="utf-8"))

    bpy.ops.bim.load_project(filepath=str(Path(ifc).resolve()))
    sun = configure_scene()
    m = make_materials()
    rooms = {str(r["id"]): r for r in model["rooms"]}
    finished = {str(z["room"]) for z in model.get("finishes", {}).get("floors", [])}
    classify_ifc(m, rooms, finished)
    if finished:
        build_finishes(model)
        m["tile_box"] = finish_material("Tiled box", {**model["finishes"]["materials"]["tile_wall"], "box": True})
    cut_mods = add_cut_box()
    parts = {item["id"]: build_item(item, model, m) for item in model.get("furniture", [])}

    cam_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", cam_data)
    bpy.context.scene.collection.objects.link(camera)

    for sheet in rv.SHEETS:
        if only and sheet["slug"] not in only:
            continue
        crop = rv.sheet_crop(model, sheet)
        x0, y0, x1, y1 = crop
        w, h = x1 - x0, y1 - y0

        for mod in cut_mods:
            mod.show_render = False
        for objects in parts.values():
            for obj in objects:
                obj.hide_render = False
        # Near-vertical sun: no wall shadow stripes across the plan view.
        sun.rotation_euler = (math.radians(4), math.radians(3), 0.0)
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = max(w, h)
        cam_data.clip_end = 100
        camera.location = ((x0 + x1) / 2, (y0 + y1) / 2, 20.0)
        camera.rotation_euler = (0.0, 0.0, 0.0)
        res = (TOP_PX, round(TOP_PX * h / w)) if w >= h else (round(TOP_PX * w / h), TOP_PX)
        render(out_dir / f"{sheet['slug']}_top.png", camera, res)

        for mod in cut_mods:
            mod.show_render = True
        shown = {item["id"] for item in rv.sheet_items(model, sheet)} if sheet.get("rooms") else set(parts)
        if sheet.get("rooms"):
            shown |= {i["id"] for i in model["furniture"] if i["room"] in sheet["rooms"]}
        for iid, objects in parts.items():
            for obj in objects:
                obj.hide_render = iid not in shown
        sun.rotation_euler = (math.radians(30), math.radians(10), math.radians(35))
        cam_data.type = "PERSP"
        cam_data.lens = 30
        cam_data.sensor_width = 36
        location, target = rv.bird_camera(crop, sheet["azimuth"], sheet["elevation"])
        camera.location = location
        look_at(camera, target)
        render(out_dir / f"{sheet['slug']}_3d.png", camera, BIRD_PX)


if __name__ == "__main__":
    main()
