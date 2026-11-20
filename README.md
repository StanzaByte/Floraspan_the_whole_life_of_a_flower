# FloraSpan — The Whole Life of a Flower

A self-contained, particle-based 2D/3D visual simulation written in Python using **NumPy** and **Pygame**[cite: 1]. FloraSpan renders the complete, continuous life cycle of a flower (`SEED` → `SPROUT` → `GROWTH` → `BLOOM` → `WILT` → `REBIRTH`), complete with a 3D swallowtail butterfly visit, volumetric particle lighting, depth-sorted occlusion, and headless MP4 video export via **FFmpeg**[cite: 1].

---

## Table of Contents

- [Overview & Visual Architecture](#overview--visual-architecture)
- [Features](#features)
  - [Life Cycle Stages](#life-cycle-stages)
  - [3D Butterfly Flight & Occlusion Engine](#3d-butterfly-flight--occlusion-engine)
  - [Particle Lighting & Post-Processing Pipeline](#particle-lighting--post-processing-pipeline)
- [Prerequisites & Setup](#prerequisites--setup)
  - [Windows](#windows)
  - [Linux (Ubuntu / Debian)](#linux-ubuntu--debian)
  - [Termux (Android / Headless Linux)](#termux-android--headless-linux)
- [Usage & CLI Flags](#usage--cli-flags)
- [Controls](#controls)
- [Configuration & Tuning](#configuration--tuning)
- [Troubleshooting](#troubleshooting)
- [Support](#support)

---

## Overview & Visual Architecture

Unlike traditional sprite- or mesh-based animations, every visual element in **FloraSpan**—the ground, stem, leaves, multi-ring petals, ambient dust motes, orbit comets, and the 3D swallowtail butterfly—is synthesized from thousands of individual light-emitting particles[cite: 1].

The simulation operates on a deterministic `29.0`-second life cycle (`life` from `0.0` to `1.0`, mapped to `DAY 001` through `DAY 090` on the HUD) that seamlessly loops into rebirth[cite: 1].

---

## Features

## Demo Preview

https://github.com/user-attachments/assets/3e4ea8cd-101b-456c-98fe-175312517251

### Life Cycle Stages

The simulation transitions smoothly across six distinct botanical phases[cite: 1]:

| Stage | Progress (`life`) | Description |
| --- | --- | --- |
| **SEED** | `0.000 – 0.070` | A luminous seed descends from mid-air, impacts the ground with an expanding light ripple, and bursts into an energy sphere[cite: 1]. |
| **SPROUT** | `0.070 – 0.206` | The primary stem emerges from the burst point with a tapered root flare and begins swaying sinusoidally[cite: 1]. |
| **GROWTH** | `0.206 – 0.452` | Six paired leaves sprout as miniatures along the rising apex and expand to full botanical size as each node is reached[cite: 1]. |
| **BLOOM** | `0.452 – 0.764` | Four concentric petal rings (`5, 11, 17, 23` petals) unfurl gradually while three orbital comet rings illuminate the canopy[cite: 1]. |
| **WILT** | `0.764 – 0.931` | The stem bends under gravity, foliage desaturates, golden pollen dust drifts away, and petals detach to fall onto the ground plane[cite: 1]. |
| **REBIRTH** | `0.931 – 1.000` | The entire plant dissolves into ascending light dust as a new seed materializes, resetting the cycle (`"then it all begins again"`)[cite: 1]. |

### 3D Butterfly Flight & Occlusion Engine

- **Catmull-Rom 3D Spline Pathing**: A swallowtail butterfly enters along a smooth 3D trajectory, orbits the open bloom, lands inside the flower cup, basks, and departs continuously without mid-air stops[cite: 1].
- **Full 3D Orientation & Wing Kinematics**: Computes orthonormal 3D basis vectors (`yaw`, `pitch`, and turn-induced `bank/roll`) with spanwise wing camber, stroke feathering, and painter's-algorithm depth sorting[cite: 1].
- **Petal-Cup & Background Occlusion**:
  - Background plant and glow layers are attenuated behind the butterfly's silhouette[cite: 1].
  - When perched inside the flower crown (`Z > 4.0`), front-facing petals dynamically occlude the butterfly's lower abdomen, legs, and wing bases so it sits naturally *inside* the bloom[cite: 1].

### Particle Lighting & Post-Processing Pipeline

- **Bilinear Additive Splatting**: Sub-pixel particle coordinates are accumulated onto floating-point light buffers (`acc` and `soft`)[cite: 1].
- **Multi-Scale Bloom / Glow**: Hierarchical box-blur pyramids (`s1`, `s2`, `s3`) generate a three-tier atmospheric glow around bright light sources[cite: 1].
- **Exponential Tone Mapping**: Applies `1 - exp(-x)` HDR compression onto a deep midnight-blue background (`[0.008, 0.006, 0.035]`) before 8-bit RGB quantization[cite: 1].
- **Aspect-Preserving Resizable Window**: Renders internally at `720×672` and scales smoothly with letterboxing to fit any window size[cite: 1].

---

## Prerequisites & Setup

**Python 3.8+** is required[cite: 1]. The script depends on:

| Dependency | Purpose | Required? |
| --- | --- | --- |
| `numpy` | Vectorized particle physics, spline math, splatting, and blur kernels[cite: 1] | **Yes** |
| `pygame` | Resizable display window, surface blitting, HUD typography, and event loop[cite: 1] | **Yes** |
| `ffmpeg` | Encoding raw RGB frames into `flower.mp4` in `--video` / headless mode[cite: 1] | Optional (for MP4 export) |

### Windows

1. **Install Python**:
   - Download Python from [python.org](https://www.python.org/downloads/) and make sure to check **"Add Python to PATH"** during setup.
2. **Install Python Libraries**:
   Open **Command Prompt** or **PowerShell** and run:
   ```cmd
   pip install numpy pygame
   ```
3. **Install FFmpeg (Optional — required only for `--video` export)**:
   - Install via `winget`:
     ```cmd
     winget install Gyan.FFmpeg
     ```
   - Alternatively, download a build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), extract it, and add its `bin\` directory to your **System Environment Variables (`PATH`)**.
   - Restart your terminal and verify with `ffmpeg -version`.

### Linux (Ubuntu / Debian)

1. **Install System Dependencies & FFmpeg**:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-numpy ffmpeg \
     libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
   ```
2. **Install Pygame**:
   ```bash
   pip install pygame
   ```

### Termux (Android / Headless Linux)

When neither `DISPLAY` nor `WAYLAND_DISPLAY` is set on Linux (such as over SSH or a plain Termux shell), FloraSpan automatically sets `SDL_VIDEODRIVER=dummy` and switches to `--video` mode[cite: 1].

```bash
pkg install x11-repo
pkg install python python-numpy clang ffmpeg sdl2 sdl2-gfx sdl2-image sdl2-mixer sdl2-ttf xorgproto
pip install pygame
```

> **Tip for Live Window on Termux:** Start **Termux:X11**, run `export DISPLAY=:0`, and launch `python floraspan_fixed.py`[cite: 1].

---

## Usage & CLI Flags

Clone the repository and navigate into the project directory:

```bash
git clone [https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git)
cd YOUR_REPO_NAME
```

| Command | Mode | Description |
| --- | --- | --- |
| `python floraspan_fixed.py` | **Live Window** | Opens a resizable interactive Pygame window running at up to 60 FPS[cite: 1]. |
| `python floraspan_fixed.py --video` | **MP4 Export** | Runs headless (no window) and renders one complete `29s` cycle at `30 FPS` (`CRF 18`, `yuv420p`) into `flower.mp4`[cite: 1]. |
| `python floraspan_fixed.py --fast` | **Half-Res Mode** | Renders the particle buffer at `1/2` resolution (`Q = 2`) and upscales smoothly—ideal for low-power devices or VMs[cite: 1]. |
| `python floraspan_fixed.py --video --fast` | **Fast Video Export** | Exports `flower.mp4` using half-resolution rendering for faster encoding[cite: 1]. |

*(Note: Use `python3` instead of `python` on Linux/macOS systems where Python 3 is mapped to `python3`.)*

While running, live telemetry is printed in-place to the terminal[cite: 1]:
```text
life 0.512   day 047   particles 42,810   fps 60
```

---

## Controls

| Input | Action |
| --- | --- |
| **`ESC`** or **`Q`** | Exit the simulation cleanly[cite: 1] |
| **Window Close (`×`)** | Exit the simulation cleanly[cite: 1] |
| **Window Drag / Maximize** | Dynamically scales the rendered scene while preserving the `720:672` aspect ratio[cite: 1] |

---

## Configuration & Tuning

All core simulation constants are defined near the top of `floraspan_fixed.py` and can be adjusted directly[cite: 1]:

- **Canvas & Resolution**: `W, H = 720, 672` controls base scene dimensions[cite: 1].
- **Cycle Duration**: `LIFE_SECONDS = 29.0` sets the total duration (in seconds) of one full seed-to-rebirth cycle[cite: 1].
- **Palette**: `PINK`, `GREY`, `TEAL`, `FLOWER`, and `GOLD` define the normalized RGB color vectors for foliage, petals, and dust[cite: 1].
- **Butterfly Behavior**: `BUTTERFLY_VIEW_PITCH_DEG`, `BUTTERFLY_BASKING_FREQUENCY`, and `BUTTERFLY_ORBIT_PATH_SCALE` tune the camera angle, basking wing motion, and flight loop radius[cite: 1].

---

## Troubleshooting

- **`ffmpeg not found` when using `--video`**:
  Ensure `ffmpeg` is installed and accessible in your system `PATH`[cite: 1]. Test by running `ffmpeg -version` in your terminal.
- **Low FPS on older hardware or virtual machines**:
  Run with the `--fast` flag (`python floraspan_fixed.py --fast`) to cut pixel-splatting overhead by `4×`[cite: 1].
- **No window appears on Linux / SSH**:
  Verify that `echo $DISPLAY` or `echo $WAYLAND_DISPLAY` is non-empty[cite: 1]. Without a display server, the script intentionally falls back to rendering `flower.mp4`[cite: 1].

---

## Support

If you find this project useful, consider buying me a coffee! ☕

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/YOUR_USERNAME)
