"""Build an editable Cinema 4D cloud from a Cloud Layer Explorer package."""

import json
import math
from pathlib import Path

import c4d


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = PACKAGE_ROOT / "cloud-settings.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "CloudLayerExplorer.c4d"
ROOT_NAME = "CloudLayerExplorer"
MATERIAL_PREFIX = "CLE_Cloud_Layer_"


def read_package():
    with SETTINGS_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("app") != "cloud-layer-explorer":
        raise ValueError("cloud-settings.json is not a Cloud Layer Explorer export")
    return payload, payload["settings"], payload.get("dccExport", {})


def set_if(node, constant_name, value):
    parameter = getattr(c4d, constant_name, None)
    if parameter is not None:
        try:
            node[parameter] = value
            return parameter
        except (AttributeError, TypeError):
            pass
    return None


def add_user_data(target, name, value):
    if isinstance(value, bool):
        dtype = c4d.DTYPE_BOOL
    elif isinstance(value, int):
        dtype = c4d.DTYPE_LONG
    elif isinstance(value, float):
        dtype = c4d.DTYPE_REAL
    else:
        dtype = c4d.DTYPE_STRING
        value = str(value)
    descriptor = c4d.GetCustomDataTypeDefault(dtype)
    descriptor[c4d.DESC_NAME] = name
    descriptor[c4d.DESC_DEFAULT] = value
    desc_id = target.AddUserData(descriptor)
    target[desc_id] = value


def remove_previous_build(doc):
    old = doc.SearchObject(ROOT_NAME)
    if old:
        old.Remove()
    material = doc.GetFirstMaterial()
    while material:
        next_material = material.GetNext()
        if material.GetName().startswith(MATERIAL_PREFIX):
            material.Remove()
        material = next_material


def key_scalar(node, parameter, frame, fps, value, interpolation=c4d.CINTERPOLATION_SPLINE):
    if parameter is None:
        return
    desc_id = c4d.DescID(c4d.DescLevel(parameter, c4d.DTYPE_REAL, 0))
    track = node.FindCTrack(desc_id)
    if track is None:
        track = c4d.CTrack(node, desc_id)
        node.InsertTrackSorted(track)
    curve = track.GetCurve()
    result = curve.AddKey(c4d.BaseTime(frame, fps))
    key = result.get("key") if isinstance(result, dict) else None
    if key is None:
        return
    key.SetValue(curve, float(value))
    key.SetInterpolation(curve, interpolation)


def key_vector_component(node, parameter, component, frame, fps, value):
    component_id = (c4d.VECTOR_X, c4d.VECTOR_Y, c4d.VECTOR_Z)[component]
    desc_id = c4d.DescID(
        c4d.DescLevel(parameter, c4d.DTYPE_VECTOR, 0),
        c4d.DescLevel(component_id, c4d.DTYPE_REAL, 0),
    )
    track = node.FindCTrack(desc_id)
    if track is None:
        track = c4d.CTrack(node, desc_id)
        node.InsertTrackSorted(track)
    curve = track.GetCurve()
    result = curve.AddKey(c4d.BaseTime(frame, fps))
    key = result.get("key") if isinstance(result, dict) else None
    if key:
        key.SetValue(curve, float(value))
        key.SetInterpolation(curve, c4d.CINTERPOLATION_LINEAR)


def layer_color(layer01):
    underside = c4d.Vector(0.21, 0.30, 0.40)
    top = c4d.Vector(0.88, 0.94, 0.98)
    t = max(0.0, min(1.0, layer01 ** 0.70))
    return underside * (1.0 - t) + top * t


def make_material(doc, settings, slice_index, layer01, frame_end, fps):
    material = c4d.BaseMaterial(c4d.Mmaterial)
    material.SetName(f"{MATERIAL_PREFIX}{slice_index:+03d}")
    material[c4d.MATERIAL_USE_COLOR] = True
    material[c4d.MATERIAL_COLOR_COLOR] = layer_color(layer01)
    material[c4d.MATERIAL_USE_REFLECTION] = False
    material[c4d.MATERIAL_USE_ALPHA] = True

    noise = c4d.BaseShader(c4d.Xnoise)
    noise.SetName(f"CLE_Noise_{slice_index:+03d}")
    material.InsertShader(noise)
    material[c4d.MATERIAL_ALPHA_SHADER] = noise

    set_if(noise, "SLA_NOISE_SEED", int(settings["seed"]))
    set_if(noise, "SLA_NOISE_OCTAVES", float(settings["octaves"]))
    set_if(noise, "SLA_NOISE_GLOBAL_SCALE", max(1.0, 100.0 / max(settings["scale"], 0.01)))
    set_if(noise, "SLA_NOISE_ABSOLUTE", True)
    speed_parameter = (
        set_if(noise, "SLA_NOISE_ANIMATE_SPEED", settings["evolution"])
        or set_if(noise, "SLA_NOISE_ANIMATION_SPEED", settings["evolution"])
    )
    movement = c4d.Vector(settings["windX"], 0.085, settings["windY"])
    set_if(noise, "SLA_NOISE_MOVEMENT", movement)

    lower_depth = max(-slice_index / max(settings["underLayers"], 1), 0.0)
    lower_taper = (lower_depth ** 1.55) * 0.12
    base_low = max(0.0, min(0.96, settings["lowClip"] + (layer01 - 0.5) * settings["clipRamp"] + lower_taper))
    base_high = max(base_low + 0.025, min(1.0, settings["highClip"] + (layer01 - 0.5) * settings["clipRamp"] + lower_taper * 0.55))
    low_parameter = set_if(noise, "SLA_NOISE_LOW_CLIP", base_low)
    high_parameter = set_if(noise, "SLA_NOISE_HIGH_CLIP", base_high)

    sample_step = max(1, fps // 4)
    sampled_frames = list(range(0, frame_end + 1, sample_step))
    if sampled_frames[-1] != frame_end:
        sampled_frames.append(frame_end)
    for frame in sampled_frames:
        seconds = frame / fps
        cycle = math.sin(seconds * settings["evolution"] * 1.7) * 0.105 * settings["morph"]
        key_scalar(noise, low_parameter, frame, fps, max(0.0, min(0.96, base_low - cycle)))
        key_scalar(noise, high_parameter, frame, fps, max(base_low + 0.025, min(1.0, base_high - cycle)))

    if speed_parameter is not None:
        key_scalar(noise, speed_parameter, 0, fps, settings["evolution"], c4d.CINTERPOLATION_LINEAR)
    doc.InsertMaterial(material)
    material.Message(c4d.MSG_UPDATE)
    return material


def add_texture_tag(obj, material):
    tag = c4d.BaseTag(c4d.Ttexture)
    tag.SetMaterial(material)
    obj.InsertTag(tag)


def light_position(settings, center_y, frame, fps):
    seconds = frame / fps
    angle = settings["lightAzimuth"]
    if settings.get("lightOrbit"):
        angle += seconds * settings["lightOrbitSpeed"] * 30.0
    azimuth = math.radians(angle)
    elevation = math.radians(settings["lightElevation"])
    radius = settings["lightDistance"]
    return c4d.Vector(
        math.sin(azimuth) * math.cos(elevation) * radius,
        center_y + math.sin(elevation) * radius,
        math.cos(azimuth) * math.cos(elevation) * radius,
    )


def make_light(doc, root, settings, center_y, frame_end, fps):
    light = c4d.BaseObject(c4d.Olight)
    light.SetName("CLE_Key_Light")
    set_if(light, "LIGHT_TYPE", getattr(c4d, "LIGHT_TYPE_OMNI", 0))
    set_if(light, "LIGHT_COLOR", {
        "daylight": c4d.Vector(0.91, 0.94, 1.0),
        "warm": c4d.Vector(1.0, 0.75, 0.45),
        "moonlight": c4d.Vector(0.48, 0.68, 1.0),
    }.get(settings["lightColor"], c4d.Vector(0.91, 0.94, 1.0)))
    set_if(light, "LIGHT_BRIGHTNESS", max(0.0, settings["lightIntensity"]))
    doc.InsertObject(light, parent=root)

    if settings.get("lightOrbit"):
        step = max(1, fps // 2)
        frames = list(range(0, frame_end + 1, step))
        if frames[-1] != frame_end:
            frames.append(frame_end)
        for frame in frames:
            position = light_position(settings, center_y, frame, fps)
            light.SetRelPos(position)
            for component, value in enumerate((position.x, position.y, position.z)):
                key_vector_component(light, c4d.ID_BASEOBJECT_REL_POSITION, component, frame, fps, value)
    else:
        light.SetRelPos(light_position(settings, center_y, 0, fps))
    return light


def make_camera(doc, root, payload):
    camera_state = payload.get("camera", {})
    position_values = camera_state.get("position", [40.0, -36.0, 74.0])
    target_values = camera_state.get("target", [0.0, 9.0, 0.0])
    position = c4d.Vector(*position_values)
    target = c4d.Vector(*target_values)
    forward = (target - position).GetNormalized()
    up = c4d.Vector(0.0, 1.0, 0.0)
    right = up.Cross(forward).GetNormalized()
    true_up = forward.Cross(right).GetNormalized()
    camera = c4d.BaseObject(c4d.Ocamera)
    camera.SetName("CLE_Camera")
    camera.SetMg(c4d.Matrix(position, right, true_up, forward))
    doc.InsertObject(camera, parent=root)
    doc.GetActiveBaseDraw().SetSceneCamera(camera)
    return camera


def main():
    payload, settings, export_settings = read_package()
    doc = c4d.documents.GetActiveDocument()
    remove_previous_build(doc)

    fps = int(export_settings.get("fps", 24))
    duration = float(export_settings.get("durationSeconds", 10.0))
    frame_end = max(2, int(round(duration * fps)))
    doc.SetFps(fps)
    doc.SetMinTime(c4d.BaseTime(0, fps))
    doc.SetMaxTime(c4d.BaseTime(frame_end, fps))
    doc.SetLoopMinTime(c4d.BaseTime(0, fps))
    doc.SetLoopMaxTime(c4d.BaseTime(frame_end, fps))

    root = c4d.BaseObject(c4d.Onull)
    root.SetName(ROOT_NAME)
    doc.InsertObject(root)
    add_user_data(root, "Cloud Settings JSON", json.dumps(settings, separators=(",", ":")))
    add_user_data(root, "Source", "Cloud Layer Explorer cloudpack")
    for key, value in settings.items():
        if isinstance(value, (bool, int, float, str)):
            add_user_data(root, key, value)

    total_layers = int(settings["layers"] + settings["underLayers"])
    for slice_index in range(-int(settings["underLayers"]), int(settings["layers"])):
        layer01 = (slice_index + settings["underLayers"]) / max(total_layers - 1, 1)
        lower_depth = max(-slice_index / max(settings["underLayers"], 1), 0.0)
        lower_scale = 1.0 - settings["underInset"] * (lower_depth ** 0.72)
        plane = c4d.BaseObject(c4d.Oplane)
        plane.SetName(f"CLE_Layer_{slice_index:+03d}")
        set_if(plane, "PRIM_PLANE_WIDTH", 82.0)
        set_if(plane, "PRIM_PLANE_HEIGHT", 82.0)
        set_if(plane, "PRIM_PLANE_SUBW", 1)
        set_if(plane, "PRIM_PLANE_SUBH", 1)
        set_if(plane, "PRIM_AXIS", getattr(c4d, "PRIM_AXIS_YP", 2))
        plane.SetRelPos(c4d.Vector(0.0, slice_index * settings["spacing"], 0.0))
        plane.SetRelScale(c4d.Vector(lower_scale, 1.0, lower_scale))
        doc.InsertObject(plane, parent=root)
        material = make_material(doc, settings, slice_index, layer01, frame_end, fps)
        add_texture_tag(plane, material)

    center_y = ((settings["layers"] - 1 - settings["underLayers"]) * settings["spacing"]) * 0.5
    make_light(doc, root, settings, center_y, frame_end, fps)
    make_camera(doc, root, payload)
    doc.SetTime(c4d.BaseTime(0, fps))
    c4d.EventAdd()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    flags = getattr(c4d, "SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST", c4d.SAVEDOCUMENTFLAGS_NONE)
    if not c4d.documents.SaveDocument(doc, str(OUTPUT_PATH), flags, c4d.FORMAT_C4DEXPORT):
        raise RuntimeError(f"Cinema 4D could not save {OUTPUT_PATH}")
    print(f"Cloud Layer Explorer: created {total_layers} layers and saved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
