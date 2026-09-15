# Cloud Layer Explorer

An editable Three.js browser prototype based on the Cinema 4D demo in the active document:

- four horizontal planes, 400 × 400, offset vertically;
- Alpha driven by a procedural Noise shader;
- clip thresholds varied through the stack to imply depth from below.

Run locally from this directory with any static server, for example:

```sh
python3 -m http.server 4173
```

Then open `http://127.0.0.1:4173/`.

The prototype adds coherent animation: all layers sample slices from the same time-evolving 3D noise field, with shared wind and morph/build-thin motion. Configurable negative-height layers contract inward beneath the main stack to round the lower silhouette.

The Lighting controls move a density-aware point source around the cloud using azimuth, elevation, and distance. Intensity, ambient fill, color, a visible marker, and optional automatic orbit can be adjusted live. The effect approximates cloud self-shadowing and edge scattering while keeping the layered renderer interactive.

Use **Export JSON** to save the active controls, animation time, and camera view. Use **Import JSON** to restore a saved look; imported numeric settings are clamped to the current control limits and unknown fields are ignored.

Use **Export DCC Package (.zip)** to create an editable `.cloudpack.zip`. It contains the current versioned settings, animation duration and frame rate, camera and light data, a browser preview, the browser source, a shared OSL density reference, and reconstruction scripts for Blender Cycles and Cinema 4D/Redshift. After extraction, run the appropriate script inside the target DCC to create and save the native scene.

Cloudpack version 1 prioritizes editable procedural reconstruction. Because WebGL, Cycles, and Redshift use different noise and transparency implementations, the native scenes are not expected to be pixel-identical. OpenVDB baking is reserved for a future export mode.

This is intentionally a visual exploration tool rather than a physically based volumetric cloud renderer.
