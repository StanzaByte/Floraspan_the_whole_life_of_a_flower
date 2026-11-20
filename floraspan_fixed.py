#!/usr/bin/env python3
"""
THE WHOLE LIFE OF A FLOWER  -  seed > sprout > growth > bloom > wilt > rebirth

    python floraspan_fixed.py            resizable live window  (needs pygame + a display)
    python floraspan_fixed.py --video    no window, writes flower.mp4   (needs ffmpeg)
    python floraspan_fixed.py --fast     half-resolution rendering for slow devices

With no display (plain Termux, ssh ...) it switches to --video by itself.
Close the window, or press ESC / Q, to quit.
Needs: numpy, pygame   (+ ffmpeg for the video file)

Termux:  pkg install x11-repo
         pkg install python python-numpy clang ffmpeg sdl2 sdl2-gfx sdl2-image sdl2-mixer sdl2-ttf xorgproto
         pip install pygame
         (live window: start Termux:X11, then  export DISPLAY=:0)
"""
import os, sys, math, time, subprocess
import numpy as np

VIDEO = "--video" in sys.argv or (sys.platform.startswith("linux")
        and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"))
if VIDEO:
    os.environ["SDL_VIDEODRIVER"] = "dummy"          # pygame without a window
import pygame

W, H = 720, 672                                      # scene size in pixels
Q = 2 if "--fast" in sys.argv else 1                 # render at 1/Q resolution
CX, GY, S = W / 2, 578.0, 0.57                       # stem root on screen, sim units -> px
EL = 0.30                                            # camera looks down a little (rad)
PINK = np.array([1.00, 0.50, 0.90]); GREY = np.array([0.80, 0.66, 0.88])
TEAL = np.array([0.08, 0.82, 0.12]); FLOWER = np.array([0.96, 0.27, 0.06])
GOLD = np.array([1.00, 0.78, 0.38])
WHITE = np.array([1.0, 1.0, 1.0])
R = np.random.default_rng(3)
life = t = dt = 0.0                                  # globals the 25 lines rely on
window = None
scene = None

# ------------------------------------------------------------------ helpers
STEM_GROW_START = 0.0757
STEM_GROW_END = 0.4
STEM_HEIGHT = 470.0
LIFE_SECONDS = 29.0
BUD_HOLD_SECONDS = 1.5
BLOOM_START = STEM_GROW_END + BUD_HOLD_SECONDS / LIFE_SECONDS
BUTTERFLY_START = BLOOM_START + 0.015

def ease(x):                                         # smoothstep 0..1
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)

def smooth(x, edge, width=0.12):                     # 0 before `edge`, 1 after edge+width
    return ease((x - edge) / width)

def mix(a, b, k):
    return a + (b - a) * k

def growth_height(progress):
    phase = float(np.clip(
        (progress - STEM_GROW_START) / (STEM_GROW_END - STEM_GROW_START), 0.0, 1.0))
    return STEM_HEIGHT * float(ease(phase))

# =====================================================================
#  THE 25 LINES  (as in the video - the engine below is what makes them run)
# =====================================================================
life = 0.0   # 0 = seed, 1 = gone

def stem(life):
    h = growth_height(life)
    y = np.linspace(0, h, 900)
    return 14 * np.sin(y / 80 + t), y

def plant_tip(progress):
    h = growth_height(progress)
    bend = smooth(progress, FLOWER_WILT_START) * (h / STEM_HEIGHT) ** 2
    return 14 * math.sin(h / 80 + t) + 150 * bend, h - 150 * bend

def bloom(life):
    bud_visibility = 1.0 - float(smooth(life, BLOOM_START, 0.10))
    for ring in range(4):
        petals(ring * 6 + 5, 0.08, size_scale=0.9, visibility=1.6 * bud_visibility)
    flower_progress = np.clip((life - BLOOM_START) / 0.12, 0.0, 1.0)
    for ring in range(4):
        open = smooth(flower_progress, ring * 0.06, 0.82)
        petals(ring * 6 + 5, open * 1.3)

def wilt(life):
    droop = smooth(life, FLOWER_WILT_START)
    colour = mix(FLOWER, GREY, droop)
    petals.fall(gravity=9.8 * droop, colour=colour)    # (only change: colour is passed on)

# while True:                                        # <- main() below runs exactly this loop
#     life += dt / 29
#     screen.fill((0, 0, 0))
#     draw(stem(life), bloom(life), wilt(life))
#     pygame.display.flip()

# =====================================================================
#  ENGINE: particles as light -> glow -> picture
# =====================================================================
_nz, _dc = {}, {}
def noise(n):                                        # fixed random offsets, per particle count
    if n not in _nz:
        _nz[n] = R.normal(size=(n, 2)).astype(np.float32)
    return _nz[n]

def disc(n):                                         # evenly spread gaussian cloud (no clumps)
    if n not in _dc:
        p, a = (np.arange(n) + 0.5) / n, np.arange(n) * 2.399963
        r = np.sqrt(-2 * np.log(1 - p))
        _dc[n] = np.stack([r * np.cos(a), r * np.sin(a)], 1).astype(np.float32)
    return _dc[n]

class Canvas:                                        # the `screen`: a pile of light specks
    def fill(self, _=None):
        self.batches, self.soft, self.occluders, self.fg_petals = [], [], [], []
    def add(self, x, y, col, w=1.0, jit=0.0, soft=False):
        x = np.ravel(x).astype(np.float32); y = np.ravel(y).astype(np.float32)
        if jit > 0.5:                                # dissolve into dust
            nz = noise(x.size)
            x = x + nz[:, 0] * jit
            y = y + nz[:, 1] * jit - np.abs(nz[:, 0]) * jit * 0.5
        w = np.broadcast_to(np.asarray(w, np.float32), x.shape)
        c = np.broadcast_to(np.asarray(col, np.float32), (x.size, 3)) * w[:, None]
        (self.soft if soft else self.batches).append((x, y, c))
    def add_occluder(self, x, y, opacity=1.0):
        x = np.ravel(x).astype(np.float32)
        y = np.ravel(y).astype(np.float32)
        op = np.broadcast_to(np.asarray(opacity, np.float32), x.shape)
        self.occluders.append((x, y, op))
    def add_fg_petal(self, x, y, col, w, jit=0.0):
        x = np.ravel(x).astype(np.float32); y = np.ravel(y).astype(np.float32)
        if jit > 0.5:
            nz = noise(x.size)
            x = x + nz[:, 0] * jit
            y = y + nz[:, 1] * jit - np.abs(nz[:, 0]) * jit * 0.5
        w = np.broadcast_to(np.asarray(w, np.float32), x.shape)
        c = np.broadcast_to(np.asarray(col, np.float32), (x.size, 3)) * w[:, None]
        self.fg_petals.append((x, y, c, w))
    def count(self):
        return sum(b[0].size for b in self.batches + self.soft + self.fg_petals)
screen = Canvas()

def blob(x, y, r, col, k, n=300, jit=0.0, hard=False):   # round glow, peak brightness ~k
    s, d = 0.5 * r, disc(n)
    screen.add(x + d[:, 0] * s, y + d[:, 1] * s, col, k * 2 * math.pi * s * s / n, jit, soft=not hard)

def splat(batches, w, h, q):                         # bilinear additive splatting; light per *screen* pixel
    if not batches:
        return np.zeros((h, w, 3), np.float32)
    x = np.concatenate([b[0] for b in batches]) / q
    y = np.concatenate([b[1] for b in batches]) / q
    c = np.concatenate([b[2] for b in batches])
    x0 = np.floor(x).astype(np.int32); y0 = np.floor(y).astype(np.int32)
    fx, fy = x - x0, y - y0
    idx, val = [], []
    for dx, dy, k in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)          # off-screen specks get weight 0
        idx.append(np.clip(yi, 0, h - 1) * w + np.clip(xi, 0, w - 1)); val.append(c * (k * ok / (q * q))[:, None])
    idx, val = np.concatenate(idx), np.concatenate(val)
    return np.stack([np.bincount(idx, val[:, i], w * h) for i in range(3)], 1).reshape(h, w, 3).astype(np.float32)

def apply_butterfly_occlusion(occluders, acc_bg, soft_bg, q):
    if not occluders:
        return
    w4, h4 = W // 4, H // 4
    x = np.concatenate([b[0] for b in occluders]) * np.float32(0.25)
    y = np.concatenate([b[1] for b in occluders]) * np.float32(0.25)
    op = np.concatenate([b[2] for b in occluders])
    ok = (x >= 0.0) & (x < w4 - 1.001) & (y >= 0.0) & (y < h4 - 1.001)
    if not np.any(ok):
        return
    x = x[ok]; y = y[ok]; op = op[ok]
    xi = x.astype(np.int32); yi = y.astype(np.int32)
    x_min = max(0, int(xi.min()) - 4); x_max = min(w4, int(xi.max()) + 5)
    y_min = max(0, int(yi.min()) - 4); y_max = min(h4, int(yi.max()) + 5)
    idx = yi * w4 + xi
    density = np.bincount(idx, op * np.float32(0.0625), w4 * h4).reshape(h4, w4, 1).astype(np.float32)
    sub = blur(density[y_min:y_max, x_min:x_max], r=1, passes=2)
    atten = np.exp(-np.clip(sub * np.float32(2.2), np.float32(0.0), np.float32(1.45)))
    soft_bg[y_min:y_max, x_min:x_max] *= atten
    scale = 4 // q
    atten_full = atten if scale == 1 else np.repeat(np.repeat(atten, scale, axis=0), scale, axis=1)
    acc_bg[y_min * scale : y_max * scale, x_min * scale : x_max * scale] *= atten_full

def pool(a, k):
    h, w, c = a.shape
    return a.reshape(h // k, k, w // k, k, c).mean(axis=(1, 3))

def box(a, r, axis):                                 # moving average via cumulative sum
    n = a.shape[axis]
    pad = [(0, 0)] * a.ndim; pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad), axis=axis)
    return (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis) - np.take(c, np.arange(n), axis)) / (2 * r + 1)

def blur(a, r=2, passes=3):
    for _ in range(passes):
        a = box(box(a, r, 0), r, 1)
    return a

def resize(a, h, w):                                 # bilinear
    for axis, n in ((0, h), (1, w)):
        m = a.shape[axis]
        pos = (np.arange(n) + 0.5) * m / n - 0.5
        i0 = np.floor(pos).astype(int)
        f = (pos - i0).astype(np.float32).reshape([n if i == axis else 1 for i in range(a.ndim)])
        a = np.take(a, np.clip(i0, 0, m - 1), axis) * (1 - f) + np.take(a, np.clip(i0 + 1, 0, m - 1), axis) * f
    return a

GLOW = (0.9, 1.0, 1.1)                               # strength of the three glow sizes

def develop(acc, soft):                              # light -> glow -> tone map -> 8 bit
    h, w, _ = acc.shape                              # soft = glow-only light, already at 1/4 of 720x672
    s1 = pool(acc, 4 // Q) * 0.6 + soft; s2 = pool(s1, 2); s3 = pool(s2, 2)
    hh, ww = s1.shape[:2]
    g = blur(s1) * GLOW[0] + resize(blur(s2), hh, ww) * GLOW[1] + resize(blur(s3), hh, ww) * GLOW[2]
    x = resize(g, h, w)
    x *= 2.4; x += acc * 1.5                         # glow + direct light
    np.negative(x, out=x); np.exp(x, out=x)          # 1 - exp(-x) tone map, folded into the 8-bit scaling:
    x *= -247.35                                     # 255 * 0.97 * (1 - e)
    x += (np.array([0.008, 0.006, 0.035], np.float32) * 255 + 247.35 + 0.5)
    return np.clip(x, 0, 255, out=x).astype(np.uint8)

# ------------------------------------------------------- random data, made once
GN = 9000                                            # ground: a flat disc of specks
ga, gr = R.uniform(0, 2 * np.pi, GN), np.sqrt(R.uniform(0, 1, GN))
gx, gy = CX + 335 * gr * np.cos(ga), 568 + 33 * gr * np.sin(ga)
gb, gph = R.uniform(0.2, 1, GN) ** 2, R.uniform(0, 6.28, GN)

NS = 5200                                            # stem specks
su, sr = R.uniform(0, 1, NS), R.normal(0, 1, NS)
sb, sph = R.uniform(0.2, 1, NS) ** 2, R.uniform(0, 6.28, NS)

LEAVES = [(0.10, -1, 50, 12), (0.13, 1, 62, 24), (0.29, -1, 98, 6),
          (0.40, 1, 98, 14), (0.58, -1, 58, 28), (0.62, 1, 66, 18)]   # height, side, px, deg
_LEAF_START_HEIGHTS = [0.0, 0.0] + [
    LEAVES[index - 2][0] * STEM_HEIGHT for index in range(2, len(LEAVES))
]

def leaf_growth(index, progress):
    height = growth_height(progress)
    start_height = _LEAF_START_HEIGHTS[index]
    anchor_height = LEAVES[index][0] * STEM_HEIGHT
    if height < start_height:
        return 0.0
    if height >= anchor_height:
        return 1.0
    amount = (height - start_height) / (anchor_height - start_height)
    return 0.22 + 0.78 * float(ease(amount))

def leaf_is_miniature(index, progress):
    height = growth_height(progress)
    start_height = _LEAF_START_HEIGHTS[index]
    anchor_height = LEAVES[index][0] * STEM_HEIGHT
    return start_height <= height < anchor_height

LN = 600
lu, lk = (np.arange(LN) + R.random(LN)) / LN, R.random(LN)
lu = R.permutation(lu)
lv = np.where(lk < 0.6, R.choice([-1.0, 1.0], LN), np.where(lk < 0.8, 0.0, R.uniform(-1, 1, LN)))
lb = np.where(lk < 0.6, 1.0, np.where(lk < 0.8, 0.9, 0.25))
lph, lj = R.uniform(0, 6.28, LN), R.normal(0, 1.1, LN)

_pd = {}
def petal_data(n):                                   # fixed specks of n petals: edges, veins, fill
    if n not in _pd:
        ring = (n - 5) // 6
        m, mv, mf = 200, 30, 200
        strat = lambda k: (np.arange(k) + R.random((n, k))) / k
        u = np.concatenate([strat(m), strat(m)] + [strat(mv)] * 3 + [R.random((n, mf))], 1)
        v = np.concatenate([np.full((n, m), 1.0), np.full((n, m), -1.0), np.full((n, mv), -0.5),
                            np.zeros((n, mv)), np.full((n, mv), 0.5), R.uniform(-1, 1, (n, mf))], 1)
        b = np.concatenate([np.full((n, 2 * m), 0.9), np.full((n, 3 * mv), 0.8), np.full((n, mf), 0.3)], 1)
        _pd[n] = dict(
            phi=(2 * np.pi * (np.arange(n) + 0.5 * ring) / n + R.normal(0, 0.05, n))[:, None],
            lj=R.uniform(0.92, 1.08, (n, 1)), tj=R.normal(0, 0.05, (n, 1)),
            tau=R.uniform(0.80, 0.95, (n, 1)), drift=R.normal(0, 1, (n, 1)), gl=R.uniform(-8, 12, (n, 1)),
            u=u, v=v, b=b, ph=R.uniform(0, 6.28, u.shape))
    return _pd[n]

ON = 320                                             # orbit-ring specks (3 rings)
oa, ob = R.uniform(0, 2 * np.pi, (3, ON)), 0.35 + 0.65 * R.random((3, ON)) ** 4
DN = 200                                             # drifting dust motes
dxm, dym = R.uniform(0, W, DN), R.uniform(0, 420, DN)
dv, dph = R.uniform(2, 9, DN), R.uniform(0, 6.28, DN)
WN = 700                                             # golden dust of the wilting head
wv, wo = np.stack([R.uniform(0.1, 1.0, WN), R.uniform(0.2, 1.0, WN)], 1), R.random(WN)

def _wing_outline(start, curves):
    outline = [np.asarray(start, dtype=np.float32)]
    point = np.asarray(start, dtype=np.float32)
    samples = np.linspace(0.0, 1.0, 20, endpoint=False, dtype=np.float32)[1:]
    for control1, control2, end in curves:
        c1, c2, end = (np.asarray(p, dtype=np.float32)
                       for p in (control1, control2, end))
        u = samples[:, None]
        segment = ((1 - u) ** 3 * point
                   + 3 * (1 - u) ** 2 * u * c1
                   + 3 * (1 - u) * u ** 2 * c2
                   + u ** 3 * end)
        outline.extend(segment)
        point = end
    return np.asarray(outline, dtype=np.float32)

def _sample_wing(outline, name, count=1200):
    low, high = outline.min(axis=0), outline.max(axis=0)
    points = []
    while sum(len(batch) for batch in points) < count:
        candidates = R.uniform(low, high, size=(count * 2, 2)).astype(np.float32)
        inside = np.zeros(len(candidates), dtype=bool)
        x, y = candidates.T
        for start, end in zip(outline, np.roll(outline, -1, axis=0)):
            crosses = (start[1] > y) != (end[1] > y)
            edge_x = start[0] + (y - start[1]) * (end[0] - start[0]) / (
                end[1] - start[1] + 1e-12)
            inside ^= crosses & (x < edge_x)
        points.append(candidates[inside])
    fill = np.concatenate(points, axis=0)[:count]
    edge_idx = R.integers(0, len(outline), 240)
    edge_t = R.random(240).astype(np.float32)[:, None]
    edge = outline[edge_idx] * (1 - edge_t) + outline[(edge_idx + 1) % len(outline)] * edge_t

    shape_x, shape_y = fill[:, 0], fill[:, 1]
    edge_x, edge_y = edge[:, 0], edge[:, 1]
    shape_z, edge_z = -shape_y, -edge_y

    # Precompute static wing veins and spot markings once at startup
    if name == "fore":
        vein_ends = [
            (3.02 - i / 7 * 1.1, -1.9 + i / 7 * 2.05,
             1.4, -0.85 + i / 7 * 0.85)
            for i in range(8)
        ]
        vein_start = (0.15, -0.15)
    else:
        vein_ends = [
            (2.15 if i == 3 else 2.22 - i / 6 * 1.45,
             2.48 if i == 3 else 0.52 + i / 6 * 1.48,
             1.0, 0.75 + i / 6 * 0.6)
            for i in range(7)
        ]
        vein_start = (0.12, 0.25)

    vein_t = np.linspace(0.0, 1.0, 28, dtype=np.float32)
    vein_mask = np.zeros(shape_x.shape, dtype=bool)
    for end_x, end_z, control_x, control_z in vein_ends:
        curve_x = ((1 - vein_t) ** 2 * vein_start[0]
                   + 2 * (1 - vein_t) * vein_t * control_x
                   + vein_t ** 2 * end_x)
        curve_z = ((1 - vein_t) ** 2 * vein_start[1]
                   + 2 * (1 - vein_t) * vein_t * control_z
                   + vein_t ** 2 * end_z)
        distance = ((shape_x[:, None] - curve_x) ** 2
                    + (shape_z[:, None] - curve_z) ** 2)
        vein_mask |= distance.min(axis=1) < 0.035 ** 2

    spots = []
    if name == "fore":
        fore_mark = np.zeros(shape_x.shape, dtype=bool)
        for i in range(9):
            spot_x, spot_z = 3.05 - i * 1.15 / 8, -1.95 + i * 2.15 / 8
            fore_mark |= ((shape_x - spot_x) / 0.085) ** 2 + ((shape_z - spot_z) / 0.070) ** 2 < 1
        spots.append((fore_mark, (0.94, 0.86, 0.64), 1.15))
    else:
        white_band = (
            (1.98, 0.52, 0.11, 0.07), (1.92, 0.72, 0.14, 0.08),
            (1.82, 0.94, 0.15, 0.09), (1.66, 1.16, 0.16, 0.10),
            (1.44, 1.36, 0.14, 0.09), (1.18, 1.52, 0.12, 0.08),
            (0.90, 1.64, 0.10, 0.07),
        )
        band_mark = np.zeros(shape_x.shape, dtype=bool)
        for spot_x, spot_z, radius_x, radius_z in white_band:
            band_mark |= ((shape_x - spot_x) / radius_x) ** 2 + ((shape_z - spot_z) / radius_z) ** 2 < 1
        spots.append((band_mark, (0.96, 0.85, 0.60), 1.10))

        lunules = ((2.15, 0.65), (2.12, 0.95), (2.04, 1.28),
                   (1.82, 1.62), (1.45, 1.84), (1.05, 1.92), (0.68, 1.88))
        lunule_mark = np.zeros(shape_x.shape, dtype=bool)
        for spot_x, spot_z in lunules:
            lunule_mark |= ((shape_x - spot_x) ** 2 + (shape_z - spot_z) ** 2) < 0.055 ** 2
        spots.append((lunule_mark, (0.92, 0.22, 0.14), 1.15))

        scallops = ((2.24, 0.55), (2.26, 0.85), (2.22, 1.18),
                    (2.06, 1.52), (1.65, 1.92), (1.22, 2.02), (0.80, 1.96))
        scallop_mark = np.zeros(shape_x.shape, dtype=bool)
        for spot_x, spot_z in scallops:
            scallop_mark |= ((shape_x - spot_x) ** 2 + (shape_z - spot_z) ** 2) < 0.040 ** 2
        spots.append((scallop_mark, (0.98, 0.90, 0.70), 1.05))

    # Attenuate hindwing fill weight slightly where forewing overlaps it in chord (`shape_y > -0.35`)
    overlap_weight = np.ones(shape_x.shape, dtype=np.float32)
    if name == "hind":
        overlap_weight = np.where(shape_y > -0.32, 0.52, 1.0).astype(np.float32)

    return {
        "shape_x": shape_x,
        "shape_y": shape_y,
        "shape_z": shape_z,
        "edge_x": edge_x,
        "edge_y": edge_y,
        "edge_z": edge_z,
        "vein_mask": vein_mask,
        "spots": spots,
        "overlap_weight": overlap_weight,
    }

_FOREWING_OUTLINE = _wing_outline((0.05, 0.12), (
    ((0.85, 0.95), (2.05, 1.85), (3.02, 2.12)),
    ((3.15, 2.14), (3.18, 2.02), (3.10, 1.82)),
    ((2.85, 1.15), (2.42, 0.35), (1.92, -0.18)),
    ((1.35, -0.35), (0.55, -0.25), (0.05, -0.08)),
))
_HINDWING_OUTLINE = _wing_outline((0.05, -0.05), (
    ((0.75, -0.12), (1.65, -0.28), (2.22, -0.48)),
    ((2.32, -0.62), (2.30, -0.78), (2.22, -0.88)),
    ((2.32, -1.02), (2.28, -1.18), (2.18, -1.28)),
    ((2.24, -1.42), (2.16, -1.58), (2.04, -1.66)),
    ((2.14, -2.02), (2.22, -2.35), (2.15, -2.46)),
    ((2.08, -2.54), (1.96, -2.46), (1.92, -2.32)),
    ((1.86, -2.08), (1.82, -1.86), (1.78, -1.76)),
    ((1.62, -1.92), (1.44, -1.96), (1.32, -1.86)),
    ((1.16, -2.02), (0.96, -2.04), (0.84, -1.92)),
    ((0.68, -2.02), (0.48, -1.96), (0.38, -1.78)),
    ((0.18, -1.42), (0.08, -0.75), (0.04, -0.18)),
))
BUTTERFLY_WING_DATA = {
    "fore": _sample_wing(_FOREWING_OUTLINE, "fore"),
    "hind": _sample_wing(_HINDWING_OUTLINE, "hind"),
}
BUTTERFLY_SCALE = 2.9 / 3.0
BUTTERFLY_ARRIVAL = 1.2
BUTTERFLY_ORBIT = 1.2
BUTTERFLY_LAND = 0.6
BUTTERFLY_PERCH = 2.2
BUTTERFLY_DEPART = 0.45
BUTTERFLY_FINAL_ORBIT = 0.95
BUTTERFLY_EXIT = 1.0
BUTTERFLY_FLIGHT_DURATION = sum((
    BUTTERFLY_ARRIVAL, BUTTERFLY_ORBIT, BUTTERFLY_LAND,
    BUTTERFLY_PERCH, BUTTERFLY_DEPART, BUTTERFLY_FINAL_ORBIT,
    BUTTERFLY_EXIT,
))
FLOWER_WILT_START = BUTTERFLY_START + BUTTERFLY_FLIGHT_DURATION / LIFE_SECONDS

# ---------------------------------------------------------------------
# BUTTERFLY 3D VIEW / POSE / PATH CONFIGURATION
#
# Local butterfly coordinate system:
#   -local_x : forward (head at -12, thorax at -1.5, abdomen tip at +22)
#   +local_y : dorsal / upward (top of thorax, wings closed upward)
#   +local_z : lateral right wing (+1.0), left wing (-1.0)
#
# Full 3D rotation (yaw, pitch, bank/roll) aligns the butterfly's local frame
# with its 3D trajectory tangent and curvature, then projects onto the 2D screen
# with depth sorting (far wing -> body -> near wing) and subtle background occlusion.
BUTTERFLY_VIEW_YAW_DEG = 0.0
BUTTERFLY_VIEW_PITCH_DEG = 28.0
BUTTERFLY_WING_SPREAD_DEG = None

BUTTERFLY_PERCH_HEIGHT = 24.0
BUTTERFLY_BASKING_SPREAD_MIN_DEG = 12.0
BUTTERFLY_BASKING_SPREAD_MAX_DEG = 38.0
BUTTERFLY_BASKING_FREQUENCY = 1.15
BUTTERFLY_FLIGHT_WING_SPREAD_MIN_DEG = 10.0
BUTTERFLY_FLIGHT_WING_SPREAD_MAX_DEG = 148.0
BUTTERFLY_PATH_SCREEN_SCALE = 70.0
BUTTERFLY_ORBIT_PATH_SCALE = 1.35

# =====================================================================
#  ENGINE: petals, draw(), HUD, main loop
# =====================================================================
def lean(x, y):                                      # the stem bends over while wilting
    k = smooth(life, FLOWER_WILT_START) * (y / 470) ** 2
    return x + 150 * k, y - 150 * k

def alive():                                         # 1 -> 0 while everything turns to dust
    return 1 - smooth(life, 0.93, 0.05)

def dust():                                          # px of scatter
    return 45 * smooth(life, 0.925, 0.05)

def project_butterfly_view(world_x, world_y, world_z=0.0):
    yaw = math.radians(BUTTERFLY_VIEW_YAW_DEG)
    pitch = math.radians(BUTTERFLY_VIEW_PITCH_DEG)
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    cos_pitch, sin_pitch = math.cos(pitch), math.sin(pitch)
    view_x = world_x * cos_yaw + world_z * sin_yaw
    view_depth = -world_x * sin_yaw + world_z * cos_yaw
    view_up = world_y * cos_pitch + view_depth * sin_pitch
    cam_depth = -world_y * sin_pitch + view_depth * cos_pitch
    return view_x, -view_up, cam_depth

def butterfly_body_yaw(heading):
    view_yaw = math.radians(BUTTERFLY_VIEW_YAW_DEG)
    pitch = math.radians(BUTTERFLY_VIEW_PITCH_DEG)
    sin_pitch = max(abs(math.sin(pitch)), 0.35)
    screen_x, screen_y = math.cos(heading), math.sin(heading)
    view_depth = -screen_y / sin_pitch
    world_x = screen_x * math.cos(view_yaw) - view_depth * math.sin(view_yaw)
    world_z = screen_x * math.sin(view_yaw) + view_depth * math.cos(view_yaw)
    return math.atan2(world_z, -world_x)

def _catmull_rom_point(points, progress):
    segment_count = len(points) - 1
    scaled = min(max(progress, 0.0), 1.0) * segment_count
    segment = min(int(scaled), segment_count - 1)
    weight = scaled - segment
    p1, p2 = points[segment], points[segment + 1]
    p0 = points[segment - 1] if segment else 2 * p1 - p2
    p3 = points[segment + 2] if segment + 2 < len(points) else 2 * p2 - p1

    dt0 = max(float(np.linalg.norm(p1 - p0)) ** 0.5, 1e-4)
    dt1 = max(float(np.linalg.norm(p2 - p1)) ** 0.5, 1e-4)
    dt2 = max(float(np.linalg.norm(p3 - p2)) ** 0.5, 1e-4)
    tangent1 = ((p1 - p0) / dt0 - (p2 - p0) / (dt0 + dt1)
                + (p2 - p1) / dt1) * dt1
    tangent2 = ((p2 - p1) / dt1 - (p3 - p1) / (dt1 + dt2)
                + (p3 - p2) / dt1) * dt1
    c2 = -3 * p1 + 3 * p2 - 2 * tangent1 - tangent2
    c3 = 2 * p1 - 2 * p2 + tangent1 + tangent2
    return p1 + tangent1 * weight + c2 * weight ** 2 + c3 * weight ** 3

def _build_butterfly_path(control_points, divisions=240):
    points = np.asarray(control_points, dtype=np.float64)
    samples = np.asarray([
        _catmull_rom_point(points, index / divisions)
        for index in range(divisions + 1)
    ])
    lengths = np.concatenate((
        [0.0],
        np.cumsum(np.linalg.norm(np.diff(samples, axis=0), axis=1)),
    ))
    return samples, lengths

def _expand_butterfly_orbit(control_points, scale):
    points = np.asarray(control_points, dtype=np.float64)
    chord = np.linspace(0.0, 1.0, len(points))[:, None]
    baseline = points[0] + chord * (points[-1] - points[0])
    return baseline + (points - baseline) * scale

def _butterfly_path_point(path, progress):
    samples, lengths = path
    distance = float(np.clip(progress, 0.0, 1.0)) * lengths[-1]
    index = min(int(np.searchsorted(lengths, distance, side="right") - 1),
                len(lengths) - 2)
    segment_length = lengths[index + 1] - lengths[index]
    weight = 0.0 if segment_length == 0 else (distance - lengths[index]) / segment_length
    return samples[index] + (samples[index + 1] - samples[index]) * weight

def _project_butterfly_path_point(point, flower_x, flower_y):
    point_up = point[1] - 0.14 * point[2]
    perch_up = 1.48 - 0.14 * 0.42
    return np.array([
        flower_x + (point[0] - 0.42) * BUTTERFLY_PATH_SCREEN_SCALE,
        flower_y - BUTTERFLY_PERCH_HEIGHT
        - (point_up - perch_up) * BUTTERFLY_PATH_SCREEN_SCALE,
    ])

# Entry path starts inside the left margin of the screen, swoops in a 3D loop around the bloom, and lands on the perch
_BUTTERFLY_ENTRY_PATH = _build_butterfly_path((
    (-5.2, 3.6, -2.5),
    (-3.2, 1.9, 1.8),
    (-0.8, 2.7, 2.5),
    (1.85, 2.2, 1.3),
    (0.85, 1.35, -1.2),
    (-0.70, 1.85, -0.5),
    (0.12, 1.60, 0.60),
    (0.42, 1.48, 0.42),
))

# Single continuous departure + final orbit + exit path so the butterfly never stops mid-air
_ORBIT_EXPANDED = _expand_butterfly_orbit((
    (0.42, 1.48, 0.42),
    (1.15, 2.05, 1.25),
    (0.10, 2.45, 1.55),
    (-1.05, 1.65, 1.15),
    (-0.38, 1.28, 0.52),
), BUTTERFLY_ORBIT_PATH_SCALE)

_BUTTERFLY_DEPART_EXIT_PATH = _build_butterfly_path(np.vstack([
    _ORBIT_EXPANDED,
    np.asarray((
        (0.55, 1.85, -0.95),
        (1.85, 2.65, 1.35),
        (3.60, 3.55, 0.70),
        (5.80, 4.45, -1.80),
    ), dtype=np.float64),
]))

_butterfly_state = {
    "rel_pos": None,
    "forward": None,
    "bank": 0.0,
}

def _build_body_geometry():
    parts = []
    body_col = (0.28, 0.26, 0.24)
    stripe_col = (0.86, 0.78, 0.60)
    eye_col = (0.12, 0.14, 0.16)
    antenna_col = (0.42, 0.39, 0.34)
    club_col = (0.55, 0.48, 0.38)
    leg_col = (0.25, 0.23, 0.21)

    # Volumetric thorax (ellipsoid rings along local_x in [-8, 5])
    tx = np.linspace(-8.0, 5.0, 26)
    t_norm = (tx - (-1.5)) / 6.5
    rad_y = 2.1 * np.sqrt(np.clip(1.0 - t_norm ** 2, 0.0, 1.0))
    rad_z = 1.8 * np.sqrt(np.clip(1.0 - t_norm ** 2, 0.0, 1.0))
    angles = np.linspace(0.0, 2.0 * np.pi, 6, endpoint=False)
    tx_grid, ang_grid = np.meshgrid(tx, angles)
    ry_grid = np.broadcast_to(rad_y, tx_grid.shape)
    rz_grid = np.broadcast_to(rad_z, tx_grid.shape)
    parts.append((
        tx_grid.ravel(),
        0.8 + ry_grid.ravel() * np.sin(ang_grid.ravel()),
        rz_grid.ravel() * np.cos(ang_grid.ravel()),
        body_col,
        np.full(tx_grid.size, 0.85, dtype=np.float32),
        True,
    ))

    # Volumetric abdomen (tapering cylinder along local_x in [4.5, 22.0], drooping slightly ventrally)
    ax = np.linspace(4.5, 22.0, 28)
    at = (ax - 4.5) / 17.5
    ab_center_y = 0.5 - 2.2 * (at ** 1.25)
    ab_rad = 1.65 * np.sin(np.pi * (0.12 + 0.82 * at))
    ax_grid, aang_grid = np.meshgrid(ax, angles)
    acy_grid = np.broadcast_to(ab_center_y, ax_grid.shape)
    ar_grid = np.broadcast_to(ab_rad, ax_grid.shape)
    parts.append((
        ax_grid.ravel(),
        acy_grid.ravel() + ar_grid.ravel() * np.sin(aang_grid.ravel()),
        ar_grid.ravel() * np.cos(aang_grid.ravel()),
        body_col,
        np.broadcast_to(0.95 - 0.30 * at, ax_grid.shape).ravel().astype(np.float32),
        True,
    ))

    # Lateral yellow-cream swallowtail abdomen stripes (at +-local_z, on left & right sides!)
    stripe_t = np.linspace(0.08, 0.88, 18)
    stripe_x = 4.5 + 17.5 * stripe_t
    stripe_cy = 0.5 - 2.2 * (stripe_t ** 1.25)
    stripe_rz = 1.72 * np.sin(np.pi * (0.12 + 0.82 * stripe_t))
    for side in (-1.0, 1.0):
        for dy_off in (-0.35, 0.35):
            parts.append((
                stripe_x,
                stripe_cy + dy_off,
                side * stripe_rz,
                stripe_col,
                np.full(stripe_t.shape, 0.90, dtype=np.float32),
                False,
            ))

    # Spherical head at local_x = -10.5, local_y = 0.9, local_z = 0.0
    head_u = np.linspace(0.0, 2.0 * np.pi, 14, endpoint=False)
    head_v = np.linspace(-0.5 * np.pi, 0.5 * np.pi, 5)
    hu, hv = np.meshgrid(head_u, head_v)
    hx = -10.5 + 2.4 * np.cos(hv) * np.cos(hu)
    hy = 0.9 + 2.2 * np.sin(hv)
    hz = 2.2 * np.cos(hv) * np.sin(hu)
    parts.append((
        hx.ravel(), hy.ravel(), hz.ravel(),
        body_col,
        np.full(hx.size, 0.90, dtype=np.float32),
        True,
    ))

    # Compound eyes on left and right sides of the head (local_z = side * 1.85)
    for side in (-1.0, 1.0):
        parts.append((
            np.array([-11.6, -11.3], dtype=np.float32),
            np.array([1.2, 1.0], dtype=np.float32),
            np.array([side * 1.85, side * 2.05], dtype=np.float32),
            eye_col,
            np.array([1.4, 1.4], dtype=np.float32),
            False,
        ))

        # Paired antennae arching forward (-X), dorsally upward (+Y), and laterally outward (side * +Z)
        ant_t = np.linspace(0.0, 1.0, 24)
        ant_x = -11.8 - 12.5 * ant_t
        ant_y = 1.8 + 5.8 * (ant_t ** 0.85) - 1.2 * (ant_t ** 2.2)
        ant_z = side * (0.8 + 4.8 * (ant_t ** 1.15))
        parts.append((
            ant_x, ant_y, ant_z,
            antenna_col,
            (0.95 * (1.0 - 0.30 * ant_t)).astype(np.float32),
            False,
        ))
        # Antenna club tip
        parts.append((
            np.array([ant_x[-1], ant_x[-2]], dtype=np.float32),
            np.array([ant_y[-1], ant_y[-2]], dtype=np.float32),
            np.array([ant_z[-1], ant_z[-2]], dtype=np.float32),
            club_col,
            np.array([1.25, 1.10], dtype=np.float32),
            False,
        ))

    # Six jointed legs extending ventrally downward (-local_y) and laterally outward (side * local_z)
    leg_t = np.linspace(0.0, 1.0, 10)
    for leg_idx, attach_x in enumerate((-6.2, -2.0, 2.2)):
        reach_x = (-2.8, 0.4, 4.2)[leg_idx]
        for side in (-1.0, 1.0):
            knee_t = np.clip(leg_t * 2.0, 0.0, 1.0)
            foot_t = np.clip((leg_t - 0.5) * 2.0, 0.0, 1.0)
            lx = attach_x + knee_t * (reach_x * 0.45) + foot_t * (reach_x * 0.55)
            ly = -0.6 - knee_t * 3.2 - foot_t * 4.8
            lz = side * (1.0 + knee_t * 2.6 + foot_t * 1.2)
            parts.append((
                lx, ly, lz,
                leg_col,
                (0.80 * (1.0 - 0.30 * leg_t)).astype(np.float32),
                False,
            ))

    return parts

_BUTTERFLY_BODY_PARTS = _build_body_geometry()

def _compute_butterfly_basis(heading, pitch_3d=0.0, bank_3d=0.0):
    """
    Construct an orthonormal 3D basis (forward_axis, dorsal_axis, right_axis)
    for the butterfly in world space.
    In local space:
      -local_x is forward (head), +local_x is backward (tail)
      +local_y is dorsal (up)
      +local_z is right wing (+1), -local_z is left wing (-1)
    """
    yaw = butterfly_body_yaw(heading)
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)

    # Horizontal forward unit vector in world XZ plane (corresponding to -local_x)
    fwd_horiz = np.array([-cos_yaw, 0.0, sin_yaw], dtype=np.float64)
    right_horiz = np.array([-sin_yaw, 0.0, -cos_yaw], dtype=np.float64)
    up_world = np.array([0.0, 1.0, 0.0], dtype=np.float64)

    # Pitch rotation around right_horiz
    cp, sp = math.cos(pitch_3d), math.sin(pitch_3d)
    fwd = fwd_horiz * cp + up_world * sp
    up_pitched = -fwd_horiz * sp + up_world * cp

    # Bank/roll rotation around fwd
    cb, sb = math.cos(bank_3d), math.sin(bank_3d)
    dorsal = up_pitched * cb + right_horiz * sb
    right = -up_pitched * sb + right_horiz * cb

    # Since local +X points from head to tail, axis_x = -fwd
    axis_x = -fwd
    axis_y = dorsal
    axis_z = right
    return axis_x, axis_y, axis_z

def draw_butterfly(x, y, scale, alpha, flap, heading, show_body=True,
                   fold=0.0, wing_spread_deg=None, pitch_3d=0.0, bank_3d=0.0,
                   perch_blend=0.0, flower_x=None, flower_y=None):
    if alpha <= 0.001:
        return

    if wing_spread_deg is not None and not 4.0 <= wing_spread_deg <= 175.0:
        raise ValueError("wing_spread_deg must be between 4 and 175")
    if BUTTERFLY_WING_SPREAD_DEG is not None and not 4.0 <= BUTTERFLY_WING_SPREAD_DEG <= 175.0:
        raise ValueError("BUTTERFLY_WING_SPREAD_DEG must be between 4 and 175")

    axis_x, axis_y, axis_z = _compute_butterfly_basis(heading, pitch_3d, bank_3d)
    dust_amount = dust()

    # Determine effective 3D wing spread angle (in degrees between left and right wings)
    if wing_spread_deg is not None:
        effective_spread = mix(float(wing_spread_deg), 12.0, float(np.clip(fold, 0.0, 1.0)) * 0.65)
    elif BUTTERFLY_WING_SPREAD_DEG is not None:
        effective_spread = mix(float(BUTTERFLY_WING_SPREAD_DEG), 8.0, float(np.clip(fold, 0.0, 1.0)))
    else:
        flap_spread = 82.0 - 68.0 * math.cos(flap)
        effective_spread = mix(flap_spread, 14.0, float(np.clip(fold, 0.0, 1.0)))

    half_spread = math.radians(np.clip(effective_spread, 4.0, 175.0) / 2.0)
    # Subtle fore-and-aftfeathering / pitch twist during downstroke/upstroke
    stroke_feather = 0.14 * math.sin(flap) * (1.0 - 0.85 * fold)

    def transform_local_to_screen(lx, ly, lz):
        lx = np.asarray(lx, dtype=np.float32)
        ly = np.asarray(ly, dtype=np.float32)
        lz = np.asarray(lz, dtype=np.float32)
        wx = lx * axis_x[0] + ly * axis_y[0] + lz * axis_z[0]
        wy = lx * axis_x[1] + ly * axis_y[1] + lz * axis_z[1]
        wz = lx * axis_x[2] + ly * axis_y[2] + lz * axis_z[2]
        vx, vy, cam_d = project_butterfly_view(wx, wy, wz)
        return x + scale * vx, y + scale * vy, cam_d

    def petal_cup_visibility(sx, sy, ly):
        """
        When the butterfly is perched inside the flower crown (`perch_blend > 0`),
        the front-facing petals rise up around the receptacle and occlude the lower
        (ventral) parts of the butterfly—legs, lower abdomen, ventral thorax, and
        the lower wing bases tucked into the flower cup.
        """
        if perch_blend <= 0.001 or flower_x is None or flower_y is None:
            return np.ones_like(sx, dtype=np.float32), np.ones_like(sx, dtype=np.float32)
        sx_arr = np.asarray(sx, dtype=np.float32)
        dx = sx_arr - np.float32(flower_x)
        sy_arr = np.asarray(sy, dtype=np.float32)
        ly_arr = np.broadcast_to(np.asarray(ly, dtype=np.float32), sx_arr.shape)

        # Curved front petal rim profile across the flower cup width
        horiz_env = np.exp(-0.5 * (dx / np.float32(85.0 * scale)) ** 2).astype(np.float32)
        rim_y = np.float32(flower_y - 31.0) + np.float32(0.0028) * (dx ** 2)

        # Screen-space depth below the front petal rim (positive = deeper inside the petal cup)
        below_rim = (sy_arr - rim_y) / np.float32(9.0 * scale)
        screen_occ = np.clip(below_rim, 0.0, 1.0)
        screen_occ = screen_occ * screen_occ * (np.float32(3.0) - np.float32(2.0) * screen_occ)

        # Local-space ventral depth: legs, abdomen, lower thorax, and lower wing bases (`ly < 8.5`)
        ventral_occ = np.clip((np.float32(8.5) - ly_arr) / np.float32(8.0), 0.0, 1.0)
        ventral_occ = ventral_occ * ventral_occ * (np.float32(3.0) - np.float32(2.0) * ventral_occ)

        cup_hide = np.float32(perch_blend) * horiz_env * np.maximum(screen_occ * np.float32(0.98), ventral_occ * np.float32(0.98))
        # Visibility for butterfly specks: completely hide (`0.0`) parts behind the front petals
        vis_speck = np.clip(np.float32(1.0) - cup_hide * np.float32(1.08), np.float32(0.0), np.float32(1.0))
        # Occluder strength: where perched inside the cup, only the upper exposed wing tips cast a gentle shadow
        vis_occ = np.clip(np.float32(1.0) - cup_hide * np.float32(1.6), np.float32(0.0), np.float32(1.0)) * np.float32(1.0 - 0.72 * perch_blend)
        return vis_speck, vis_occ

    def wing_local_coords(shape_x, shape_z, side, is_fore=True):
        """
        Compute 3D wing coordinates in the butterfly's local frame, attached to
        the dorsal thorax hinge at (local_x = -2.0, local_y = 1.6, local_z = side * 0.85).
        Wings rotate naturally around the thorax hinge in the local YZ plane, with
        graceful spanwise camber and stroke feathering.
        """
        span_scale = 20.0 * (1.0 - 0.08 * fold)
        chord_scale = 21.5
        # Natural spanwise arch (camber) when flapping
        camber = 1.6 * (shape_x / 3.2) ** 2 * math.sin(flap) * (1.0 - 0.8 * fold)
        radial = shape_x * span_scale
        # Forewing sits slightly dorsal/anterior to hindwing so they layer cleanly in 3D
        layer_bias = 0.55 if is_fore else -0.35

        ly = 1.6 + radial * math.cos(half_spread) + camber + layer_bias * math.sin(half_spread)
        lz = side * (0.85 + radial * math.sin(half_spread) + camber * 0.35 - layer_bias * math.cos(half_spread))
        lx = -2.0 + shape_z * chord_scale - radial * stroke_feather * 0.18
        return lx, ly, lz

    # Collect depth-sorted renderable groups: (mean_cam_depth, priority, draw_calls, occluder_calls)
    render_groups = []

    for side in (-1.0, 1.0):
        # Compute mean camera depth of this wing side (using a representative mid-wing point)
        mid_lx, mid_ly, mid_lz = wing_local_coords(1.5, 0.0, side, True)
        _, _, side_cam_depth = transform_local_to_screen(mid_lx, mid_ly, mid_lz)
        side_depth = float(np.mean(side_cam_depth))

        # Depth-based perspective shading: near wing is brighter & crisper, far wing is slightly dimmer
        depth_shade = float(np.clip(1.0 + 0.012 * side_depth, 0.72, 1.22))

        # Order hindwing before forewing on the near side, or by actual 3D depth
        for name in ("hind", "fore"):
            is_fore = (name == "fore")
            wdata = BUTTERFLY_WING_DATA[name]
            shape_x = wdata["shape_x"]
            shape_z = wdata["shape_z"]
            edge_x = wdata["edge_x"]
            edge_z = wdata["edge_z"]
            vein_mask = wdata["vein_mask"]
            overlap_w = wdata["overlap_weight"]

            wing_x, wing_y, wing_z = wing_local_coords(shape_x, shape_z, side, is_fore)
            edge_lx, edge_ly, edge_lz = wing_local_coords(edge_x, edge_z, side, is_fore)

            sx, sy, s_depth = transform_local_to_screen(wing_x, wing_y, wing_z)
            ex, ey, _ = transform_local_to_screen(edge_lx, edge_ly, edge_lz)
            part_depth = float(np.mean(s_depth)) + (0.4 if is_fore else -0.4)

            w_vis, w_occ_vis = petal_cup_visibility(sx, sy, wing_y)
            e_vis, _ = petal_cup_visibility(ex, ey, edge_ly)

            # Swallowtail wing iridescent dark-blue/charcoal sheen that catches the light in 3D
            sheen = (0.88 + 0.22 * (shape_x / 3.2) + 0.09 * np.sin(5.0 * shape_z + flap)) * depth_shade
            sheen[vein_mask] *= 0.42
            # Boosted contrast dark-sapphire/velvet-charcoal wing base so it stands out against the flower
            colour = np.column_stack((0.125 * sheen, 0.148 * sheen, 0.185 * sheen))

            calls = []
            occ = [(sx, sy, 0.85 * alpha * overlap_w * w_occ_vis)]
            calls.append((sx, sy, colour, 0.88 * alpha * overlap_w * w_vis, dust_amount))
            calls.append((ex, ey, (0.22 * depth_shade, 0.25 * depth_shade, 0.28 * depth_shade),
                          np.full(edge_x.shape, 0.90 * alpha, dtype=np.float32) * e_vis, dust_amount))

            for mark, spot_col, spot_w in wdata["spots"]:
                shaded_spot = tuple(min(1.0, c * (0.85 + 0.15 * depth_shade)) for c in spot_col)
                calls.append((
                    sx[mark], sy[mark], shaded_spot,
                    np.full(np.count_nonzero(mark), spot_w * alpha * depth_shade, dtype=np.float32) * w_vis[mark],
                    dust_amount,
                ))

            render_groups.append((part_depth, 1 if is_fore else 0, calls, occ))

    if show_body:
        body_calls = []
        body_occ = []
        body_depths = []
        for lx, ly, lz, col, w_arr, is_occ in _BUTTERFLY_BODY_PARTS:
            bx, by, b_depth = transform_local_to_screen(lx, ly, lz)
            b_vis, b_occ_vis = petal_cup_visibility(bx, by, ly)
            body_depths.append(float(np.mean(b_depth)))
            shade = float(np.clip(1.0 + 0.008 * float(np.mean(b_depth)), 0.82, 1.15))
            shaded_col = tuple(min(1.0, c * shade) for c in col)
            body_calls.append((bx, by, shaded_col, w_arr * alpha * b_vis, dust_amount))
            if is_occ:
                body_occ.append((bx, by, 1.15 * alpha * b_occ_vis))
        mean_body_depth = float(np.mean(body_depths)) if body_depths else 0.0
        render_groups.append((mean_body_depth, 0, body_calls, body_occ))

    # Painter's algorithm sort: back-to-front by camera depth (smaller cam_depth drawn first, larger on top)
    render_groups.sort(key=lambda item: (item[0], item[1]))

    for _, _, calls, occ_list in render_groups:
        for ox, oy, op in occ_list:
            screen.add_occluder(ox, oy, op)
        for sx, sy, col, w_arr, jit_val in calls:
            screen.add(sx, sy, col, w_arr, jit_val)

def draw_butterfly_flight():
    elapsed = life * LIFE_SECONDS - BUTTERFLY_START * LIFE_SECONDS
    total = BUTTERFLY_FLIGHT_DURATION
    if elapsed < 0 or elapsed >= total:
        _butterfly_state["rel_pos"] = None
        _butterfly_state["forward"] = None
        _butterfly_state["bank"] = 0.0
        return

    hx, hy = plant_tip(life)
    flower_x, flower_y = CX + S * hx, GY - S * hy
    entry_duration = BUTTERFLY_ARRIVAL + BUTTERFLY_ORBIT + BUTTERFLY_LAND
    perched_start = entry_duration
    perched_end = perched_start + BUTTERFLY_PERCH
    depart_exit_duration = BUTTERFLY_DEPART + BUTTERFLY_FINAL_ORBIT + BUTTERFLY_EXIT

    perch_3d = _BUTTERFLY_ENTRY_PATH[0][-1]
    is_perched = False

    # Sample 3D position and 3D tangent along the flower-relative path (eliminating stem-sway jitter!)
    if elapsed < perched_start:
        u = elapsed / entry_duration
        # Smooth ease-out landing so entry flight flows continuously into the perch
        progress = float(u * (1.0 - 0.35 * u * u) / 0.65) if u < 0.72 else float(ease(u))
        # Blend smoothly across the entire entry path
        progress = float(0.65 * u + 0.35 * ease(u))
        # Ensure gentle deceleration right at landing (last 0.4s)
        land_window = min(max((elapsed - (perched_start - 0.5)) / 0.5, 0.0), 1.0)
        if land_window > 0.0:
            p_linear = 0.65 * u + 0.35 * float(ease(u))
            p_eased = float(ease(u))
            progress = mix(p_linear, p_eased, land_window)

        pt_3d = _butterfly_path_point(_BUTTERFLY_ENTRY_PATH, progress)
        ahead_3d = _butterfly_path_point(_BUTTERFLY_ENTRY_PATH, min(1.0, progress + 0.025))
        behind_3d = _butterfly_path_point(_BUTTERFLY_ENTRY_PATH, max(0.0, progress - 0.025))
        tangent_3d = ahead_3d - behind_3d
    elif elapsed < perched_end:
        is_perched = True
        pt_3d = perch_3d.copy()
        perch_elapsed = elapsed - perched_start
        # Briefly perch facing right just long enough to be clearly seen, then snap-turn to face left
        turn_k = smooth(perch_elapsed, 0.22, 0.05)
        angle_xz = mix(0.28, math.pi - 0.42, turn_k)
        tangent_3d = np.array([
            math.cos(angle_xz),
            0.12 + 0.08 * math.sin(math.pi * turn_k),
            -0.38 * math.sin(angle_xz),
        ], dtype=np.float64)
    else:
        # Single continuous C1 trajectory from departure through the final orbit and into the exit!
        u = (elapsed - perched_end) / depart_exit_duration
        # Smooth takeoff acceleration over first 0.25s, then steady continuous flight (never stopping mid-air!)
        takeoff_ease = u * u / (u * u + (1.0 - u) * 0.12 + 1e-6)
        progress = float(np.clip(mix(takeoff_ease, u, smooth(u, 0.15, 0.25)), 0.0, 1.0))

        pt_3d = _butterfly_path_point(_BUTTERFLY_DEPART_EXIT_PATH, progress)
        ahead_3d = _butterfly_path_point(_BUTTERFLY_DEPART_EXIT_PATH, min(1.0, progress + 0.02))
        behind_3d = _butterfly_path_point(_BUTTERFLY_DEPART_EXIT_PATH, max(0.0, progress - 0.02))
        tangent_3d = ahead_3d - behind_3d

    # Smooth in flower-relative 3D space so the butterfly stays locked to the swaying flower when perched
    pos_alpha = 1.0 - (1.0 - (0.35 if is_perched else 0.24)) ** (max(dt, 0.0) * 60.0)
    if _butterfly_state["rel_pos"] is None:
        _butterfly_state["rel_pos"] = pt_3d.copy()
    else:
        _butterfly_state["rel_pos"] += (pt_3d - _butterfly_state["rel_pos"]) * pos_alpha

    rel_pos = _butterfly_state["rel_pos"]
    pos = _project_butterfly_path_point(rel_pos, flower_x, flower_y)

    # Compute screen-space forward direction from the flower-relative 3D tangent (head leads movement!)
    pos_ahead = _project_butterfly_path_point(rel_pos + tangent_3d, flower_x, flower_y)
    dir_2d = pos_ahead - pos
    dir_norm = float(np.linalg.norm(dir_2d))
    if dir_norm > 1e-5:
        target_fwd = dir_2d / dir_norm
    elif _butterfly_state["forward"] is not None:
        target_fwd = _butterfly_state["forward"]
    else:
        target_fwd = np.array([-1.0, 0.0], dtype=np.float64)

    fwd_alpha = 1.0 - (1.0 - (0.75 if is_perched else 0.16)) ** (max(dt, 0.0) * 60.0)
    if _butterfly_state["forward"] is None:
        _butterfly_state["forward"] = target_fwd.copy()
        turn_rate = 0.0
    else:
        prev_fwd = _butterfly_state["forward"]
        prev_ang = math.atan2(prev_fwd[1], prev_fwd[0])
        targ_ang = math.atan2(target_fwd[1], target_fwd[0])
        ang_delta = (targ_ang - prev_ang + math.pi) % (2.0 * math.pi) - math.pi
        turn_rate = ang_delta / max(dt, 1.0 / 60.0)
        new_ang = prev_ang + ang_delta * fwd_alpha
        _butterfly_state["forward"] = np.array([math.cos(new_ang), math.sin(new_ang)], dtype=np.float64)

    fwd = _butterfly_state["forward"]
    # True forward heading (NO +pi reversal: head leads the movement trajectory!)
    heading = math.atan2(fwd[1], fwd[0])

    # Compute natural 3D pitch (climbing/diving) and bank/roll (leaning into turns)
    t3_norm = float(np.linalg.norm(tangent_3d))
    if is_perched:
        target_pitch = 0.18
        target_bank = 0.08 * math.sin(1.5 * t)
    elif t3_norm > 1e-5:
        climb = float(tangent_3d[1]) / t3_norm
        target_pitch = float(np.clip(math.asin(np.clip(climb * 0.75, -0.65, 0.65)), -0.55, 0.55))
        target_bank = float(np.clip(-turn_rate * 0.08, -0.52, 0.52))
    else:
        target_pitch = 0.0
        target_bank = 0.0

    bank_alpha = 1.0 - (1.0 - 0.14) ** (max(dt, 0.0) * 60.0)
    _butterfly_state["bank"] += (target_bank - _butterfly_state["bank"]) * bank_alpha
    bank_3d = _butterfly_state["bank"]
    pitch_3d = target_pitch

    fade = 1.0
    # Perspective depth scale based on 3D Z coordinate (`rel_pos[2]`)
    depth_perspective = float(np.clip(1.0 + 0.045 * (rel_pos[2] - 0.42), 0.78, 1.22))
    scale = BUTTERFLY_SCALE * depth_perspective
    if elapsed >= total - BUTTERFLY_EXIT:
        k = (elapsed - total + BUTTERFLY_EXIT) / BUTTERFLY_EXIT
        fade = 1.0 - float(ease(k))
        scale *= (1.0 - 0.35 * k)

    fold_start = perched_start - 0.22
    fold = float(ease((elapsed - fold_start) / 0.22))
    if elapsed >= perched_end:
        fold = 1.0 - float(ease((elapsed - perched_end) / 0.16))

    flap = 2 * math.pi * (1.25 if is_perched else 11.5) * t
    if is_perched:
        perch_elapsed = elapsed - perched_start
        angle_from_up = (BUTTERFLY_BASKING_SPREAD_MIN_DEG
                         + (BUTTERFLY_BASKING_SPREAD_MAX_DEG
                            - BUTTERFLY_BASKING_SPREAD_MIN_DEG)
                         * (0.5 - 0.5 * math.cos(
                             2 * math.pi * BUTTERFLY_BASKING_FREQUENCY * perch_elapsed)))
        wing_spread = 2.0 * angle_from_up
    else:
        spread_midpoint = (BUTTERFLY_FLIGHT_WING_SPREAD_MIN_DEG
                           + BUTTERFLY_FLIGHT_WING_SPREAD_MAX_DEG) / 2.0
        spread_amplitude = (BUTTERFLY_FLIGHT_WING_SPREAD_MAX_DEG
                            - BUTTERFLY_FLIGHT_WING_SPREAD_MIN_DEG) / 2.0
        wing_spread = spread_midpoint + spread_amplitude * math.cos(flap)

    # Vertical thorax bob synchronized with wing downstrokes during flight
    flap_bob = (1.0 - fold) * 3.2 * math.sin(flap) * scale
    draw_y = pos[1] + flap_bob

    # While perched in the flower cup, fade out the blue aura and occlude lower butterfly parts behind front petals
    if 1.0 - fold > 0.02:
        blob(pos[0], draw_y, 20 * scale, (0.28, 0.58, 1.0),
             0.16 * ((1.0 - fold) ** 2) * fade * alive(), 100, dust())
    draw_butterfly(pos[0], draw_y, scale, fade * alive(), flap, heading, True,
                   fold, wing_spread, pitch_3d=pitch_3d, bank_3d=bank_3d,
                   perch_blend=fold, flower_x=flower_x, flower_y=flower_y)
    return fold

class Petals:
    g, col = 0.0, FLOWER
    def __call__(self, n, open, size_scale=1.0, visibility=1.0):
        last_leaf_height = LEAVES[-1][0] * STEM_HEIGHT
        bud = np.clip((growth_height(life) - last_leaf_height) /
                      (STEM_HEIGHT - last_leaf_height), 0.0, 1.0)
        if bud <= 0.001 or open <= 0.001: return
        D, ring, dr = petal_data(n), (n - 5) // 6, smooth(life, FLOWER_WILT_START)
        o = open / 1.3 * (1 + 0.02 * math.sin(1.3 * t + ring))       # 0 closed .. 1 wide open
        hx, hy = plant_tip(life)
        drop_start = FLOWER_WILT_START + D["tau"] - 0.80
        f = np.clip(life - drop_start, 0, None) * LIFE_SECONDS      # seconds since this petal let go
        rel = np.clip(f / 1.1, 0, 1)                                 # 0 attached .. 1 lying on the ground
        base = open * (0.62 + 0.09 * ring)
        th = (base + (2.3 - base) * 0.85 * smooth(life, FLOWER_WILT_START, 0.10)) * (1 - rel) + 1.9 * rel   # petals droop, then flatten
        L = (110 + 6.5 * n) * (0.42 + 0.58 * o) * bud * size_scale * D["lj"]
        u, v = D["u"], D["v"]
        tb = th * (0.55 + 0.38 * u) + D["tj"]
        rad = L * u * np.sin(tb) + 0.07 * L + (1 - o) * 0.16 * L * np.sin(np.pi * u)
        wd = 0.17 * L * np.sin(np.pi * u ** 0.7) ** 0.8 * v
        phi = D["phi"] + 0.04 * t
        Z = rad * np.sin(phi) + wd * np.cos(phi)
        Yh = L * u * np.cos(tb) * math.cos(EL) - Z * math.sin(EL)    # height as seen on screen
        X = rad * np.cos(phi) - wd * np.sin(phi)
        psi = math.atan2(0.64 * dr, 1 - 0.64 * dr) * (1 - np.clip(f / 0.5, 0, 1))   # head tilts with the stem
        xs, ys = X * np.cos(psi) + Yh * np.sin(psi), Yh * np.cos(psi) - X * np.sin(psi)
        Y = np.maximum(hy + ys - 0.5 * self.g * 14 * f ** 2, D["gl"] - Z * math.sin(EL))
        col = mix(np.array([1.0, 0.72, 0.24]), self.col, (u ** 0.4)[..., None])
        w = D["b"] * (0.75 + 0.25 * np.sin(D["ph"] + 4 * t)) * o * bud * 0.40 * visibility * alive() * (0.3 + 0.7 * u ** 0.5) * (1 - 0.35 * dr)
        px_all = (CX + S * (hx + xs + D["drift"] * f * 40)).ravel()
        py_all = (GY - S * Y).ravel()
        col_all = col.reshape(-1, 3)
        w_all = w.ravel()
        z_all = Z.ravel()
        # Separate front-facing petal specks (Z > 4.0) from back/side petal specks so the butterfly sits INSIDE the flower cup
        front_mask = z_all > 4.0
        if np.any(~front_mask):
            screen.add(px_all[~front_mask], py_all[~front_mask], col_all[~front_mask], w_all[~front_mask], dust())
        if np.any(front_mask):
            screen.add_fg_petal(px_all[front_mask], py_all[front_mask], col_all[front_mask], w_all[front_mask], dust())
    def fall(self, gravity, colour):
        self.g, self.col = gravity, colour
petals = Petals()

def draw(stem_xy, *_):
    sx, sy = stem_xy
    x, y = lean(sx, sy)                              # stem centre line (sim units)
    h = sy[-1]
    al, dis, droop = alive(), dust(), smooth(life, FLOWER_WILT_START)
    born = smooth(life, 0.0757, 0.012)               # the stem exists only after the seed has burst
    hx, hy = x[-1], y[-1]
    lcol = mix(mix(TEAL, FLOWER, smooth(life, 0.40, 0.10)), GREY, smooth(life, FLOWER_WILT_START, 0.15))
    lit = smooth(life, 0.07, 0.03) * al
    # ground (lit by the plant)
    k = gb * (0.8 + 0.2 * np.sin(gph + 3 * t)) * (0.05 + 0.7 * lit * np.exp(-((gx - CX - S * hx * 0.4) / 150) ** 2))
    screen.add(gx, gy, mix(np.array([0.78, 0.84, 1.0]), lcol, 0.4), k)
    # seed: falls, lands, bursts - and returns at the very end
    fall = float(np.clip(life / 0.062, 0, 1))
    sy0 = 237.0 if life > 0.5 else 237 + 318 * fall ** 1.8
    sa = (1 - smooth(life, 0.0757, 0.004)) if life < 0.5 else smooth(life, 0.975, 0.02)
    if sa > 0.01:
        blob(CX, sy0, 6, (1.0, 0.93, 0.76), 3.0 * sa, 150, hard=True)
        blob(CX, sy0, 40, (1.0, 0.82, 0.5), 0.30 * sa, 200)
    q = (life - 0.060) / 0.022
    if 0 < q < 1:                                    # ripple of light where it lands
        a = np.linspace(0, 2 * np.pi, 120)
        screen.add(CX + (10 + 70 * q) * np.cos(a), 556 + (3 + 13 * q) * np.sin(a), GOLD, 0.6 * (1 - q))
    b = smooth(life, 0.0757, 0.006) * (1 - smooth(life, 0.10, 0.10))
    if b > 0.01:                                     # the seed bursts into a glow ball
        blob(CX, GY - 8 - 0.25 * S * h, 28 - 14 * smooth(life, 0.0757, 0.09), (0.4, 1.0, 0.95), 2.2 * b, 400)
    # stem: realistic botanical taper from a sturdy, rooted base to a slender upper stem and delicate apex
    i = (su * 899).astype(int)
    col = mix(TEAL, np.array([0.72, 1.0, 0.62]), (0.55 * su ** 3)[:, None])
    col = mix(col, np.array([0.85, 1.0, 0.88]), 0.7 * droop)
    wid = 6.5 + 6 * (1 - h / 470) ** 2
    root_flare = 0.36 * np.exp(-su / 0.075)
    stem_taper = (1.0 - 0.66 * (su ** 0.78) + root_flare) * (0.28 + 0.72 * np.clip((1.0 - su) / 0.055, 0, 1))
    w_taper = (1.12 - 0.34 * (su ** 0.85)) * (0.35 + 0.65 * np.clip((1.0 - su) / 0.055, 0, 1))
    w = sb * (0.75 + 0.25 * np.sin(sph + 5 * t)) * np.exp(-0.5 * (sr / 1.4) ** 2) * (h / 470 + 0.02) * (1.7 + 3.0 * (1 - h / 470) ** 2) * al * born * (1 - 0.6 * droop) * w_taper
    screen.add(CX + S * (x[i] + sr * wid * stem_taper), GY - S * y[i], col, w, dis)
    screen.add(CX + S * (x[i] + sr * 2.4 * stem_taper), GY - S * y[i], col, w * 0.7, dis)  # bright core
    # Each pair starts as miniatures; each leaf reaches full size at its node.
    for leaf_idx, (frac, side, px, ang) in enumerate(LEAVES):
        anchor = frac * 470
        g = leaf_growth(leaf_idx, life)
        miniature = leaf_is_miniature(leaf_idx, life)
        L = px / S * g
        root_y = h if miniature else anchor
        ax, ay = np.interp(root_y, sy, x), root_y
        dl = droop * (0.25 + 0.75 * frac / 0.62)                     # low leaves droop less
        a, c = math.radians(ang) - dl * 0.55, 0.25 + 0.3 * dl
        cx_, cy_ = side * L * lu * math.cos(a), L * lu * math.sin(a) - c * L * lu ** 2
        tx, ty = side * math.cos(a) * np.ones(LN), math.sin(a) - 2 * c * lu
        nrm = np.hypot(tx, ty); nx, ny = -ty / nrm, tx / nrm
        wd = (0.06 + 0.05 * g) * L * np.sin(np.pi * lu ** 0.8) ** 0.9 * lv + (lj / S) * g
        wl = lb * (0.8 + 0.2 * np.sin(lph + 5 * t)) * g * 1.3 * al * born * (1 - 0.55 * droop)
        screen.add(CX + S * (ax + cx_ + nx * wd), GY - S * np.maximum(ay + cy_ + ny * wd, 2), mix(mix(TEAL, np.array([0.42, 1.0, 0.22]), 0.32), np.array([0.8, 1.0, 0.72]), droop), wl, dis)
    # orbit rings + comets around the bloom
    ov = smooth(life, 0.47, 0.08) * (1 - smooth(life, 0.74, 0.05))
    if ov > 0.01:
        for j in range(3):
            ang = oa[j] + (0.25 + 0.12 * j) * t * (-1 if j == 1 else 1)
            Rr, rot, sq = 245 + 20 * j, 0.7 * j - 0.4, math.cos(0.5 + 0.55 * j)
            for aa, wt in ((ang, ob[j] * 0.5 * ov), (ang[0] - np.arange(18) * 0.03, 1.8 * ov * (1 - np.arange(18) / 18))):
                ex, ey = Rr * np.cos(aa), Rr * np.sin(aa) * sq
                screen.add(CX + S * (hx + ex * math.cos(rot) - ey * math.sin(rot)),
                           GY - S * (hy + 40 + ex * math.sin(rot) + ey * math.cos(rot)), (0.9, 0.78, 1.0), wt)
    # gold dust leaving the wilting head
    s = float(np.clip((life - FLOWER_WILT_START) / 0.15, 0, 1))
    if s > 0:
        age = np.clip(s * 1.5 - wo * 0.5, 0, 1)
        screen.add(CX + S * (hx + wv[:, 0] * age * 140 + noise(WN)[:, 0] * 10), GY - S * (hy + wv[:, 1] * age * 100 + noise(WN)[:, 1] * 8),
                   GOLD, 1.6 * (1 - age) * smooth(s, 0.0, 0.2) * (1 - smooth(life, 0.94, 0.04)))
    # drifting dust motes
    screen.add(dxm + 14 * np.sin(dph + 0.4 * t), 180 + (dym - dv * t) % 420, (0.7, 0.8, 1.0), 0.22 * (0.5 + 0.5 * np.sin(dph * 3 + 2 * t)))

    # Splat background plant & back petals first, then composite the 3D butterfly, then front petals over the perched butterfly!
    bg_batches = list(screen.batches)
    bg_soft = list(screen.soft)
    fg_petal_batches = list(screen.fg_petals)
    screen.batches, screen.soft, screen.occluders = [], [], []

    perch_fold = draw_butterfly_flight() or 0.0

    bf_batches = screen.batches
    bf_soft = screen.soft
    bf_occ = screen.occluders
    screen.batches = bg_batches + bf_batches
    screen.soft = bg_soft + bf_soft

    acc_bg = splat(bg_batches, W // Q, H // Q, Q)
    soft_bg = splat(bg_soft, W // 4, H // 4, 4)
    if bf_batches or bf_soft:
        apply_butterfly_occlusion(bf_occ, acc_bg, soft_bg, Q)
        acc_bf = splat(bf_batches, W // Q, H // Q, Q)
        soft_bf = splat(bf_soft, W // 4, H // 4, 4)
        if fg_petal_batches and perch_fold > 0.01:
            # Front-facing petals (Z > 4) occlude the lower perched butterfly parts behind them!
            fg_occ_list = [(b[0], b[1], b[3] * np.float32(3.8 * perch_fold)) for b in fg_petal_batches]
            apply_butterfly_occlusion(fg_occ_list, acc_bf, soft_bf, Q)
        acc = acc_bg + acc_bf
        soft_acc = soft_bg + soft_bf
        if fg_petal_batches:
            acc += splat([(b[0], b[1], b[2]) for b in fg_petal_batches], W // Q, H // Q, Q)
    else:
        acc = acc_bg
        soft_acc = soft_bg
        if fg_petal_batches:
            acc += splat([(b[0], b[1], b[2]) for b in fg_petal_batches], W // Q, H // Q, Q)

    # light -> pixels -> window
    img = develop(acc, soft_acc)
    buf = img.tobytes()
    surf = pygame.image.frombuffer(buf, (W // Q, H // Q), "RGB")
    if Q > 1: surf = pygame.transform.smoothscale(surf, (W, H))
    scene.blit(surf, (0, 0))
    hud()
    display_width, display_height = window.get_size()
    scale = min(display_width / W, display_height / H)
    scaled_size = (max(1, round(W * scale)), max(1, round(H * scale)))
    scaled = pygame.transform.smoothscale(scene, scaled_size)
    window.fill((0, 0, 0))
    window.blit(scaled, ((display_width - scaled_size[0]) // 2,
                         (display_height - scaled_size[1]) // 2))

STAGES = [(0.0, "SEED", (255, 224, 161)), (0.07, "SPROUT", (160, 243, 223)), (0.206, "GROWTH", (123, 219, 196)),
          (BLOOM_START, "BLOOM", (252, 148, 191)), (FLOWER_WILT_START, "WILT", (199, 169, 175)), (0.931, "REBIRTH", (254, 228, 171))]
TITLE = "THE WHOLE LIFE OF A FLOWER"
_fonts = {}
def font(px):                                        # sizes relative to the title width
    if px not in _fonts:
        base = lambda s: pygame.font.SysFont("helvetica,arial,dejavusans", s, bold=True)
        _fonts[px] = base(max(8, round(px * 548 / base(36).size(TITLE)[0])))
    return _fonts[px]

def text(s, px, col, x, y, align="c"):
    img = font(px).render(s, True, col)
    r = img.get_rect()
    setattr(r, {"l": "midleft", "c": "center", "r": "midright"}[align], (int(x), int(y)))
    scene.blit(img, r)

def hud():
    name, col = [(n, c) for e, n, c in STAGES if life >= e][-1]
    a1 = smooth(life, 0.005, 0.025) * (1.0 - smooth(life, 0.085, 0.045))       # opening title fades in, holds, then dissolves
    a2 = smooth(life, 0.95, 0.04)                                              # closing line fades in
    if a1 > 0:
        text(TITLE, 36, tuple(int(c * a1) for c in (250, 250, 255)), W / 2, 93)
    if a2 > 0:
        text("then it all begins again", 27, tuple(int(c * a2) for c in (253, 228, 176)), W / 2, 133)
    text("DAY %03d" % min(int(life * 90) + 1, 90), 23, (250, 250, 255), 40, 619, "l")
    text(name, 23, col, 680, 619, "r")
    px = int(40 + 640 * life)
    pygame.draw.line(scene, (38, 39, 47), (40, 648), (680, 648), 3)
    pygame.draw.line(scene, tuple(int(c * 0.76) for c in col), (40, 648), (px, 648), 3)
    for e, _, _ in STAGES:
        pygame.draw.circle(scene, (253, 245, 247) if life >= e else (59, 61, 71), (int(40 + 640 * e), 648), 4)
    pygame.draw.circle(scene, (255, 255, 255), (px, 648), 7)

def main():
    global life, t, dt, window, scene
    pygame.init()
    desktop = pygame.display.Info()
    initial_size = (min(W, int(desktop.current_w * 0.9)),
                    min(H, int(desktop.current_h * 0.8)))
    window = pygame.display.set_mode(initial_size, pygame.RESIZABLE)
    scene = pygame.Surface((W, H))
    pygame.display.set_caption("the whole life of a flower")
    for px in (36, 27, 23):
        font(px)
    for ring in range(4):
        petal_data(ring * 6 + 5)
    clock, pipe = pygame.time.Clock(), None
    if VIDEO:
        print("no window: rendering flower.mp4 (one full life, 29 s) ...")
        try:
            pipe = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                     "-s", f"{W}x{H}", "-r", "30", "-i", "-", "-an", "-c:v", "libx264",
                                     "-pix_fmt", "yuv420p", "-crf", "18", "flower.mp4"], stdin=subprocess.PIPE)
        except FileNotFoundError:
            sys.exit("ffmpeg not found  (Termux: pkg install ffmpeg)")
    tobytes = getattr(pygame.image, "tobytes", None) or pygame.image.tostring
    life = t = 0.0
    running, last = True, time.perf_counter()
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_q)):
                running = False
            elif e.type == pygame.VIDEORESIZE:
                window = pygame.display.set_mode(e.size, pygame.RESIZABLE)
        dt = 1 / 30 if VIDEO else min(clock.tick(60) / 1000, 0.05)
        t += dt
        life += dt / LIFE_SECONDS
        if life >= 1:
            if VIDEO: break
            life -= 1                                # ...and it all begins again
        screen.fill((0, 0, 0))
        scene.fill((0, 0, 0))
        draw(stem(life), bloom(life), wilt(life))
        pygame.display.flip()
        if pipe: pipe.stdin.write(tobytes(scene, "RGB"))
        now = time.perf_counter()
        print("\rlife %.3f   day %03d   particles %s   fps %d " % (life, min(int(life * 90) + 1, 90),
              format(screen.count(), ","), 1 / max(now - last, 1e-3)), end="", flush=True)
        last = now
    if pipe:
        pipe.stdin.close(); pipe.wait(); print("\nsaved flower.mp4")
    pygame.quit()

if __name__ == "__main__":
    main()
