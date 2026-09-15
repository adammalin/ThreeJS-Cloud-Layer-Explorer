"""Build an editable Blender Cycles cloud from a Cloud Layer Explorer package."""

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = PACKAGE_ROOT / "cloud-settings.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "CloudLayerExplorer.blend"
COLLECTION_NAME = "CloudLayerExplorer"
MATERIAL_PREFIX = "CLE_Cloud_Layer_"


def read_package():
    with SETTINGS_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("app") != "cloud-layer-explorer":
        raise ValueError("cloud-settings.json is not a Cloud Layer Explorer export")
    return payload, payload["settings"], payload.get("dccExport", {})


def remove_previous_build():
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection:
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)
    for material in list(bpy.data.materials):
        if material.name.startswith(MATERIAL_PREFIX):
            bpy.data.materials.remove(material)
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith("CLE_LayerMesh_") and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    mesh = bpy.data.meshes.get("CLE_Shared_Plane")
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def make_collection():
    collection = bpy.data.collections.new(COLLECTION_NAME)
    bpy.context.scene.collection.children.link(collection)
    return collection


def make_plane_mesh():
    half = 41.0
    mesh = bpy.data.meshes.new("CLE_Shared_Plane")
    mesh.from_pydata(
        [(-half, -half, 0.0), (half, -half, 0.0), (half, half, 0.0), (-half, half, 0.0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for loop, uv in zip(uv_layer.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop.uv = uv
    return mesh


def set_input(node, name, value):
    socket = node.inputs.get(name)
    if socket is not None:
        socket.default_value = value
    return socket


def add_driver(socket, expression, index=None):
    fcurve = socket.driver_add("default_value") if index is None else socket.driver_add("default_value", index)
    fcurve.driver.type = "SCRIPTED"
    fcurve.driver.expression = expression


def layer_color(layer01):
    underside = Vector((0.21, 0.30, 0.40))
    top = Vector((0.88, 0.94, 0.98))
    t = max(0.0, min(1.0, layer01 ** 0.70))
    return (*underside.lerp(top, t), 1.0)


def make_layer_material(settings, slice_index, layer01, fps):
    material = bpy.data.materials.new(f"{MATERIAL_PREFIX}{slice_index:+03d}")
    material.use_nodes = True
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    material.diffuse_color = layer_color(layer01)

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (720, 80)
    mix = nodes.new("ShaderNodeMixShader")
    mix.location = (500, 80)
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.location = (280, -30)
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (270, 150)
    set_input(principled, "Base Color", layer_color(layer01))
    set_input(principled, "Roughness", 0.86)
    set_input(principled, "Specular IOR Level", 0.18)
    set_input(principled, "Emission Color", layer_color(layer01))
    set_input(principled, "Emission Strength", 0.08 + settings["ambientLight"] * 0.22)

    texcoord = nodes.new("ShaderNodeTexCoord")
    texcoord.location = (-900, 80)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-690, 80)
    mapping.vector_type = "POINT"
    set_input(mapping, "Scale", (settings["scale"] * 2.0, settings["scale"] * 2.0, 1.0))
    location = mapping.inputs.get("Location")
    location.default_value[2] = layer01 * settings["coherence"]
    seconds = f"((frame-1.0)/{float(fps):.6f})"
    add_driver(location, f"{settings['windX']:.8f}*{settings['evolution']:.8f}*0.72*{seconds}", 0)
    add_driver(location, f"{settings['windY']:.8f}*{settings['evolution']:.8f}*0.72*{seconds}", 1)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-430, 80)
    noise.noise_dimensions = "4D"
    set_input(noise, "Scale", 1.0)
    set_input(noise, "Detail", float(settings["octaves"]))
    set_input(noise, "Roughness", 0.52)
    set_input(noise, "Distortion", settings["warp"] * 2.2)
    w_socket = noise.inputs.get("W")
    add_driver(w_socket, f"{layer01 * settings['coherence']:.8f}+{settings['evolution']:.8f}*0.085*{seconds}")

    threshold = nodes.new("ShaderNodeMapRange")
    threshold.location = (-120, 65)
    threshold.interpolation_type = "SMOOTHERSTEP"
    set_input(threshold, "To Min", 0.0)
    set_input(threshold, "To Max", 1.0)

    separate = nodes.new("ShaderNodeSeparateXYZ")
    separate.location = (-420, -300)
    edge_axes = []
    for axis_index, axis_name in enumerate(("X", "Y")):
        centered = nodes.new("ShaderNodeMath")
        centered.operation = "SUBTRACT"
        centered.location = (-220, -250 - axis_index * 130)
        centered.inputs[1].default_value = 0.5
        absolute = nodes.new("ShaderNodeMath")
        absolute.operation = "ABSOLUTE"
        absolute.location = (-40, -250 - axis_index * 130)
        doubled = nodes.new("ShaderNodeMath")
        doubled.operation = "MULTIPLY"
        doubled.location = (130, -250 - axis_index * 130)
        doubled.inputs[1].default_value = 2.0
        links.new(separate.outputs[axis_name], centered.inputs[0])
        links.new(centered.outputs[0], absolute.inputs[0])
        links.new(absolute.outputs[0], doubled.inputs[0])
        edge_axes.append(doubled)

    edge_max = nodes.new("ShaderNodeMath")
    edge_max.operation = "MAXIMUM"
    edge_max.location = (300, -300)
    edge_fade = nodes.new("ShaderNodeMapRange")
    edge_fade.location = (470, -210)
    edge_fade.interpolation_type = "SMOOTHERSTEP"
    edge_fade.clamp = True
    set_input(edge_fade, "From Min", 0.72)
    set_input(edge_fade, "From Max", 0.98)
    set_input(edge_fade, "To Min", 1.0)
    set_input(edge_fade, "To Max", 0.0)
    density = nodes.new("ShaderNodeMath")
    density.operation = "MULTIPLY"
    density.location = (310, 25)

    low = settings["lowClip"] + (layer01 - 0.5) * settings["clipRamp"]
    high = settings["highClip"] + (layer01 - 0.5) * settings["clipRamp"]
    lower_depth = max(-slice_index / max(settings["underLayers"], 1), 0.0)
    lower_taper = (lower_depth ** 1.55) * 0.12
    low = max(0.0, min(0.96, low + lower_taper))
    high = max(low + 0.025, min(1.0, high + lower_taper * 0.55))
    threshold.inputs["From Min"].default_value = low
    threshold.inputs["From Max"].default_value = high
    build_cycle = f"sin({seconds}*{settings['evolution']:.8f}*1.7)*0.105*{settings['morph']:.8f}"
    add_driver(threshold.inputs["From Min"], f"{low:.8f}-{build_cycle}")
    add_driver(threshold.inputs["From Max"], f"{high:.8f}-{build_cycle}")

    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], threshold.inputs["Value"])
    links.new(texcoord.outputs["Generated"], separate.inputs["Vector"])
    links.new(edge_axes[0].outputs[0], edge_max.inputs[0])
    links.new(edge_axes[1].outputs[0], edge_max.inputs[1])
    links.new(edge_max.outputs[0], edge_fade.inputs["Value"])
    links.new(threshold.outputs["Result"], density.inputs[0])
    links.new(edge_fade.outputs["Result"], density.inputs[1])
    links.new(density.outputs[0], mix.inputs[0])
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(principled.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs["Surface"])
    return material


def aim_object(obj, target, track_axis="-Z", up_axis="Y"):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat(track_axis, up_axis).to_euler()


def three_to_blender(position):
    return (position[0], -position[2], position[1])


def hex_color(name):
    colors = {
        "daylight": (0.91, 0.94, 1.0),
        "warm": (1.0, 0.75, 0.45),
        "moonlight": (0.48, 0.68, 1.0),
    }
    return colors.get(name, colors["daylight"])


def build_light(collection, root, settings, frame_end, fps):
    center_z = ((settings["layers"] - 1 - settings["underLayers"]) * settings["spacing"]) * 0.5
    light_data = bpy.data.lights.new("CLE_Key_Light", type="POINT")
    light_data.energy = max(0.0, settings["lightIntensity"]) * 50000.0
    light_data.color = hex_color(settings["lightColor"])
    light_data.shadow_soft_size = 7.0
    light = bpy.data.objects.new("CLE_Key_Light", light_data)
    collection.objects.link(light)
    light.parent = root

    def set_position(frame):
        time_seconds = (frame - 1) / fps
        angle = settings["lightAzimuth"]
        if settings.get("lightOrbit"):
            angle += time_seconds * settings["lightOrbitSpeed"] * 30.0
        azimuth = math.radians(angle)
        elevation = math.radians(settings["lightElevation"])
        radius = settings["lightDistance"]
        light.location = (
            math.sin(azimuth) * math.cos(elevation) * radius,
            -math.cos(azimuth) * math.cos(elevation) * radius,
            center_z + math.sin(elevation) * radius,
        )

    if settings.get("lightOrbit"):
        for frame in range(1, frame_end + 1, max(1, fps // 2)):
            set_position(frame)
            light.keyframe_insert(data_path="location", frame=frame)
        set_position(frame_end)
        light.keyframe_insert(data_path="location", frame=frame_end)
        for curve in light.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    else:
        set_position(1)
    return light


def build_camera(collection, root, payload):
    camera_state = payload.get("camera", {})
    position = camera_state.get("position", [40.0, -36.0, 74.0])
    target = camera_state.get("target", [0.0, 9.0, 0.0])
    camera_data = bpy.data.cameras.new("CLE_Camera")
    camera_data.angle = math.radians(42.0)
    camera = bpy.data.objects.new("CLE_Camera", camera_data)
    collection.objects.link(camera)
    camera.parent = root
    camera.location = three_to_blender(position)
    aim_object(camera, three_to_blender(target))
    bpy.context.scene.camera = camera
    return camera


def configure_scene(settings, export_settings):
    scene = bpy.context.scene
    fps = int(export_settings.get("fps", 24))
    duration = float(export_settings.get("durationSeconds", 10.0))
    frame_end = max(2, int(round(duration * fps)))
    scene.frame_start = 1
    scene.frame_end = frame_end
    scene.render.fps = fps
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    try:
        scene.render.engine = "CYCLES"
    except TypeError as exc:
        raise RuntimeError("Cycles is required to build this cloud package") from exc
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.008, 0.014, 0.025, 1.0)
        background.inputs["Strength"].default_value = 0.18 + settings["ambientLight"] * 1.35
    return frame_end, fps


def main():
    payload, settings, export_settings = read_package()
    remove_previous_build()
    collection = make_collection()
    frame_end, fps = configure_scene(settings, export_settings)

    root = bpy.data.objects.new("CLE_Cloud_Root", None)
    root.empty_display_type = "PLAIN_AXES"
    collection.objects.link(root)
    root["cloud_settings_json"] = json.dumps(settings, separators=(",", ":"))
    root["source"] = "Cloud Layer Explorer cloudpack"
    for key, value in settings.items():
        if isinstance(value, (bool, int, float, str)):
            root[key] = value

    mesh = make_plane_mesh()
    total_layers = int(settings["layers"] + settings["underLayers"])
    for slice_index in range(-int(settings["underLayers"]), int(settings["layers"])):
        layer01 = (slice_index + settings["underLayers"]) / max(total_layers - 1, 1)
        lower_depth = max(-slice_index / max(settings["underLayers"], 1), 0.0)
        lower_scale = 1.0 - settings["underInset"] * (lower_depth ** 0.72)
        layer_mesh = mesh.copy()
        layer_mesh.name = f"CLE_LayerMesh_{slice_index:+03d}"
        obj = bpy.data.objects.new(f"CLE_Layer_{slice_index:+03d}", layer_mesh)
        collection.objects.link(obj)
        obj.parent = root
        obj.location.z = slice_index * settings["spacing"]
        obj.scale = (lower_scale, lower_scale, 1.0)
        obj["slice_index"] = slice_index
        obj["layer_fraction"] = layer01
        layer_mesh.materials.append(make_layer_material(settings, slice_index, layer01, fps))

    build_light(collection, root, settings, frame_end, fps)
    build_camera(collection, root, payload)
    bpy.context.scene.frame_set(1)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_PATH))
    print(f"Cloud Layer Explorer: created {total_layers} layers and saved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
