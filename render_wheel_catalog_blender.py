"""Render the parametric wheel family as one review image in Blender."""

import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def import_obj(path):
    before = set(bpy.context.scene.objects)
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        bpy.ops.import_scene.obj(filepath=str(path))
    return [obj for obj in bpy.context.scene.objects if obj not in before]


argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
catalog_path = Path(argv[0]).resolve()
output_path = Path(argv[1]).resolve()
catalog = json.loads(catalog_path.read_text())
project_root = catalog_path.parents[1]

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

palette = [
    (0.22, 0.25, 0.29, 1.0),
    (0.20, 0.52, 0.36, 1.0),
    (0.16, 0.39, 0.64, 1.0),
    (0.76, 0.28, 0.20, 1.0),
    (0.86, 0.62, 0.12, 1.0),
]
labels = ["Smooth", "Broad wave", "Low grouser", "Staggered", "Chevron"]

for index, candidate in enumerate(catalog["candidates"]):
    objects = import_obj(project_root / candidate["dem"]["obj"])
    material = bpy.data.materials.new(f"material_{index}")
    material.use_nodes = True
    material.diffuse_color = palette[index]
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = palette[index]
    principled.inputs["Roughness"].default_value = 0.62
    principled.inputs["Metallic"].default_value = 0.08
    for obj in objects:
        obj.location.x = (index - 2) * 0.47
        obj.rotation_euler[2] = math.radians(-13)
        if hasattr(obj.data, "materials"):
            obj.data.materials.append(material)
        if obj.type == "MESH":
            for polygon in obj.data.polygons:
                polygon.use_smooth = True

    bpy.ops.object.text_add(location=((index - 2) * 0.47, -0.45, -0.30))
    text = bpy.context.object
    text.data.body = labels[index]
    text.data.align_x = "CENTER"
    text.data.align_y = "CENTER"
    text.data.size = 0.055
    text.data.extrude = 0.001
    text.rotation_euler[0] = math.radians(90)
    text_material = bpy.data.materials.new(f"label_{index}")
    text_material.diffuse_color = (0.88, 0.90, 0.93, 1.0)
    text.data.materials.append(text_material)

bpy.ops.object.light_add(type="AREA", location=(-1.5, -1.8, 2.4))
bpy.context.object.data.energy = 500
bpy.context.object.data.shape = "DISK"
bpy.context.object.data.size = 2.0
look_at(bpy.context.object, (0, 0, 0))
bpy.ops.object.light_add(type="AREA", location=(1.8, -0.6, 1.0))
bpy.context.object.data.energy = 300
bpy.context.object.data.size = 1.5
look_at(bpy.context.object, (0, 0, 0))

bpy.ops.object.camera_add(location=(0, -3.8, 0.20))
camera = bpy.context.object
look_at(camera, (0, 0, -0.03))
camera.data.type = "ORTHO"
camera.data.ortho_scale = 2.75
bpy.context.scene.camera = camera

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1600
scene.render.resolution_y = 700
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(output_path)
scene.world.color = (0.025, 0.032, 0.045)
scene.render.film_transparent = False
scene.view_settings.look = "AgX - Medium High Contrast"
output_path.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.render.render(write_still=True)
