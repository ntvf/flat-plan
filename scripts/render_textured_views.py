"""Render fixed interior views from an IFC model with simple finish materials."""

import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def argv_after_dashes():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def principled_material(name, colour, roughness=0.6, metallic=0.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*colour, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return material


def glass_material():
    material = bpy.data.materials.new("Glass")
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (0.055, 0.28, 0.52, 1.0)
    shader.inputs["Roughness"].default_value = 0.16
    shader.inputs["Metallic"].default_value = 0.08
    shader.inputs["IOR"].default_value = 1.45
    transmission = shader.inputs.get("Transmission Weight")
    if transmission:
        transmission.default_value = 0.28
    return material


def brick_material():
    material = bpy.data.materials.new("Brick tiles")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = 0.72

    coordinates = nodes.new("ShaderNodeTexCoord")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (0.20, 0.012, 0.004, 1.0)
    brick.inputs["Color2"].default_value = (0.52, 0.055, 0.012, 1.0)
    brick.inputs["Mortar"].default_value = (0.42, 0.32, 0.23, 1.0)
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = 0.008
    brick.inputs["Mortar Smooth"].default_value = 0.004
    brick.inputs["Brick Width"].default_value = 0.24
    brick.inputs["Row Height"].default_value = 0.065

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.24
    bump.inputs["Distance"].default_value = 0.035
    links.new(coordinates.outputs["UV"], brick.inputs["Vector"])
    links.new(brick.outputs["Color"], shader.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return material


def assign_material(obj, material):
    if obj.type != "MESH":
        return
    obj.data.materials.clear()
    obj.data.materials.append(material)


def assign_wall_uv(obj):
    mesh = obj.data
    uv_layer = mesh.uv_layers.get("Brick UV") or mesh.uv_layers.new(name="Brick UV")
    world_points = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    best_pair = (world_points[0], world_points[1])
    best_distance = -1.0
    for index, first in enumerate(world_points):
        for second in world_points[index + 1:]:
            distance = (Vector((second.x - first.x, second.y - first.y))).length
            if distance > best_distance:
                best_distance = distance
                best_pair = first, second
    tangent = Vector((best_pair[1].x - best_pair[0].x,
                      best_pair[1].y - best_pair[0].y)).normalized()
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            point = world_points[mesh.loops[loop_index].vertex_index]
            uv_layer.data[loop_index].uv = (
                point.x * tangent.x + point.y * tangent.y,
                point.z,
            )


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area_light(name, location, target, energy, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.use_shadow = False
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)


def add_ceiling_light(name, location, material):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32, radius=0.11, depth=0.025,
        location=(location[0], location[1], 2.675),
    )
    fixture = bpy.context.object
    fixture.name = f"{name} fixture"
    assign_material(fixture, material)

    data = bpy.data.lights.new(name, "POINT")
    data.energy = 180
    data.color = (1.0, 0.72, 0.48)
    data.shadow_soft_size = 0.42
    light = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(light)
    light.location = (location[0], location[1], 2.55)


def configure_scene():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.7
    scene.world.color = (0.055, 0.07, 0.10)

    world = scene.world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.13, 0.18, 0.26, 1.0)
    background.inputs["Strength"].default_value = 0.35


def main():
    src, output_dir = argv_after_dashes()
    src = str(Path(src).resolve())
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.bim.load_project(filepath=src)
    configure_scene()

    materials = {
        "wall": principled_material("Warm white plaster", (0.78, 0.75, 0.69), 0.82),
        "partition": principled_material("White plasterboard", (0.90, 0.89, 0.84), 0.78),
        "floor": principled_material("Light oak floor", (0.42, 0.25, 0.11), 0.62),
        "door": principled_material("Door timber", (0.20, 0.075, 0.025), 0.58),
        "metal": principled_material("Equipment white", (0.82, 0.84, 0.84), 0.32),
        "pipe": principled_material("Copper pipe", (0.58, 0.19, 0.06), 0.32, 0.55),
        "shaft": principled_material("Service casing", (0.46, 0.48, 0.47), 0.8),
        "light": principled_material("Light fixture", (1.0, 0.88, 0.62), 0.18),
        "brick": brick_material(),
        "glass": glass_material(),
    }

    for obj in bpy.context.scene.objects:
        name = obj.name
        if name.startswith("IfcCovering/BRICK_"):
            assign_material(obj, materials["brick"])
            if "BRICK_NORTH_OB1" in name:
                obj.location.y -= 0.060
            elif "BRICK_NW_CHAMFER" in name:
                obj.location.x += 0.045
                obj.location.y -= 0.045
            elif "BRICK_WEST_TO_TANK" in name:
                obj.location.x += 0.060
            elif "BRICK_EAST" in name:
                obj.location.x -= 0.060
            assign_wall_uv(obj)
        elif name.startswith("IfcWindow/") or "/Drzwi OB2" in name or "/Drzwi DK6" in name:
            assign_material(obj, materials["glass"])
        elif name.startswith("IfcSpace/"):
            assign_material(obj, materials["floor"])
        elif name.startswith("IfcWall/W_bath2_"):
            assign_material(obj, materials["partition"])
        elif name.startswith("IfcWall/"):
            assign_material(obj, materials["wall"])
        elif name.startswith("IfcDoor/"):
            assign_material(obj, materials["door"])
        elif name.startswith("IfcPipeSegment/"):
            assign_material(obj, materials["pipe"])
            obj.hide_render = True
        elif name.startswith("IfcUnitaryEquipment/") or name.startswith("IfcTank/"):
            assign_material(obj, materials["metal"])
        elif name.startswith("IfcBuildingElementProxy/"):
            assign_material(obj, materials["shaft"])

    bpy.ops.mesh.primitive_cube_add(location=(4.715, 6.645, 2.725),
                                    scale=(4.715, 6.645, 0.025))
    ceiling = bpy.context.object
    ceiling.name = "Render ceiling"
    assign_material(ceiling, materials["partition"])

    add_area_light("Window daylight", (5.4, 12.65, 2.1), (5.4, 9.0, 1.2), 260, 4.5)
    for index, location in enumerate((
        (2.7, 10.6), (5.4, 10.6), (7.7, 10.2), (5.8, 8.2),
    ), 1):
        add_ceiling_light(f"Ceiling light {index}", location, materials["light"])

    camera_data = bpy.data.cameras.new("Render Camera")
    camera = bpy.data.objects.new("Render Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.data.lens = 24
    camera.data.sensor_width = 36

    views = [
        ("01_northwest_brick_and_windows", (6.40, 8.85, 1.55), (2.25, 12.05, 1.45)),
        ("02_east_brick_wall", (4.75, 10.55, 1.55), (8.88, 9.82, 1.40)),
        ("03_new_bathroom_ac_wall", (4.80, 9.65, 1.55), (7.49, 7.42, 1.72)),
    ]
    for filename, location, target in views:
        camera.location = location
        look_at(camera, target)
        bpy.context.scene.render.filepath = str(output_dir / f"{filename}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[render] wrote {bpy.context.scene.render.filepath}")

    blend_path = output_dir / "target_textured_views.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"[render] wrote {blend_path}")


if __name__ == "__main__":
    main()
