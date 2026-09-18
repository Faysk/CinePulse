# CinePulse 1.2.1

CinePulse 1.2.1 is a usability-focused update for the Overlay Composer / Music Visualizer introduced in 1.2.0.

## Composer visual direto

The previous form-heavy editor exposed implementation-level controls such as normalized X/Y coordinates and manual audio/stem routing in the default workflow. 1.2.1 replaces that surface with direct manipulation:

- choose an image or video as the background;
- add GIF/image/video-alpha overlays;
- add Spectrum, Waveform or Circular visualizers;
- click a layer on the canvas and drag it to reposition;
- drag a corner handle to resize while preserving aspect ratio;
- use compact opacity, music-reaction, loop and layer-order controls;
- keep rotation, spin and blend under **Mais opções** instead of the primary workflow.

## Image background + project music

A still image can now be the actual Composer background. CinePulse no longer requires the user to manufacture a source video first.

For a still background:

- duration follows the music already selected in the CinePulse project;
- FPS follows the current project FPS;
- canvas dimensions follow the current output resolution;
- the still is cover-fitted to the output canvas;
- the selected project music is used automatically for visualizer analysis and final output audio.

If no music is selected, preview remains available with a bounded fallback duration; normal music projects automatically adopt the selected track as soon as it is present.

## Compatibility and safety

Composer project schema is now 3 and persists `background_source`. Schemas 1 and 2 remain readable.

The deterministic CPU/NumPy compositor remains the correctness reference. GPU compositor routes remain evidence-gated and fall back safely. Export remains cancellable and atomic.

This release does not claim new physical RTX/CUDA/TensorRT/8K/12K performance acceptance; those hardware-specific gates remain separate.
