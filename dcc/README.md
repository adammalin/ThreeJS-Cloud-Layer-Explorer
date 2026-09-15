# Cloud Layer Explorer DCC Package

This package reconstructs the browser cloud as editable native scene elements. `cloud-settings.json` is the source of truth.

## Blender Cycles

1. Extract the complete ZIP without changing its internal folders.
2. In Blender, open the Scripting workspace.
3. Open `blender/build_cloud.py` and choose **Run Script**.
4. The script creates a `CloudLayerExplorer` collection and saves `blender/CloudLayerExplorer.blend`.

The Blender build uses native Noise Texture nodes, transparent/principled shading, animated density thresholds and wind, a camera, and a point light. Existing scene content outside the named collection is preserved.

## Cinema 4D / Redshift

1. Extract the complete ZIP without changing its internal folders.
2. Open Cinema 4D's Script Manager.
3. Open and run `cinema4d/build_cloud.py`.
4. The script creates a `CloudLayerExplorer` hierarchy and saves `cinema4d/CloudLayerExplorer.c4d`.

The Cinema 4D build uses native planes, procedural Noise alpha materials, animated clip thresholds, a camera, and a native light that Redshift can consume. Select Redshift in Render Settings for final rendering; the script deliberately does not modify existing renderer/video-post configuration.

## Fidelity

The reconstruction is editable and parameter-faithful, but not pixel-identical. Three.js, Blender Cycles, and Cinema 4D Redshift use different noise and transparency implementations. The included `shaders/cloud_density.osl` documents a shared density approximation for advanced OSL workflows.

No external textures are required for the editable build. The package includes the browser preview image and all procedural source needed to recreate the materials and animation. An OpenVDB bake is a separate future export mode.
