"""LAB: simulated test of core/lightsweep.py.

Renders a glossy card with busy artwork and known damage (a dent, a crease, a fine scratch, a scuffed patch), then a
2-3 s "light sweep": the light moves across while the hand-held phone wobbles a little (each frame gets a small random
perspective shift, so alignment is tested too). Checks that each defect is found and how much clean card is flagged,
next to what the app's single-photo surface check finds on one frame.
"""
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, ".")
from core import condition, lightsweep

rng = np.random.default_rng(3)
H, W = 880, 630


def artwork():
    a = np.zeros((H, W, 3), np.uint8)
    for _ in range(260):   # busy art: blobs, lines and text-like marks (also gives the aligner features)
        c = rng.uniform(30, 230, 3)
        x, y = rng.integers(0, W), rng.integers(0, H)
        k = rng.integers(0, 3)
        if k == 0:
            cv2.circle(a, (int(x), int(y)), int(rng.integers(4, 40)), c.tolist(), -1)
        elif k == 1:
            cv2.line(a, (int(x), int(y)), (int(x + rng.integers(-80, 80)), int(y + rng.integers(-80, 80))), c.tolist(), int(rng.integers(1, 5)))
        else:
            cv2.putText(a, "AB12"[: rng.integers(1, 5)], (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, rng.uniform(0.4, 1.2), c.tolist(), 2)
    a = cv2.GaussianBlur(a, (3, 3), 0).astype(np.float32)
    a[:28], a[-28:], a[:, :28], a[:, -28:] = (230, 200, 60), (230, 200, 60), (230, 200, 60), (230, 200, 60)   # yellow border
    return a


def damage():
    hgt = np.zeros((H, W), np.float32)
    rough = np.full((H, W), 0.06, np.float32)
    truth = {}
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # dent: shallow round depression
    d = -1.6 * np.exp(-((xx - 180) ** 2 + (yy - 250) ** 2) / (2 * 12 ** 2))
    hgt += d
    truth["dent"] = ((xx - 180) ** 2 + (yy - 250) ** 2) < 22 ** 2
    # crease: a V-shaped fold line across the lower card
    dist = np.abs((yy - 620) - 0.35 * (xx - 300)) / np.hypot(1, 0.35)
    hgt += -1.2 * np.clip(1 - dist / 6, 0, None)
    truth["crease"] = (dist < 8) & (xx > 60) & (xx < 570)
    # fine scratch: thin groove that scatters light
    sd = np.abs((xx - 420) - 0.9 * (yy - 380)) / np.hypot(1, 0.9)
    on = (sd < 1.5) & (yy > 330) & (yy < 470)
    hgt -= 0.4 * on
    rough[on] = 0.5
    truth["scratch"] = cv2.dilate(on.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    # scuffed patch: matte area (no shape change)
    sc = ((xx - 470) ** 2 / 40 ** 2 + (yy - 160) ** 2 / 25 ** 2) < 1
    rough[sc] = 0.35
    truth["scuff"] = sc
    return hgt, rough, truth


def render(albedo, hgt, rough, light_x, light_y=300):
    gy, gx = np.gradient(cv2.GaussianBlur(hgt, (5, 5), 0))
    n = np.dstack([-gx, -gy, np.ones_like(hgt)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    L = np.dstack([light_x - xx, light_y - yy, np.full_like(xx, 700)])   # point light moving left to right, 70 cm-ish up
    L /= np.linalg.norm(L, axis=2, keepdims=True)
    V = np.array([0, 0, 1.0])
    Hh = L + V
    Hh /= np.linalg.norm(Hh, axis=2, keepdims=True)
    ndh = np.clip((n * Hh).sum(2), 0, 1)
    ang = np.arccos(ndh)
    spec = np.exp(-(ang / rough) ** 2) * (0.06 / rough) ** 0.5
    diff = np.clip((n * L).sum(2), 0, 1)
    img = albedo * (0.35 + 0.55 * diff[..., None]) + 200 * spec[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def wobble(img):
    pad = 40
    big = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(20, 20, 20))
    h, w = big.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src + rng.normal(0, 4, src.shape).astype(np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(big, M, (w, h), borderValue=(20, 20, 20))
    return np.clip(out + rng.normal(0, 2.0, out.shape), 0, 255).astype(np.uint8)


albedo = artwork()
hgt, rough, truth = damage()
# the person tilts the card both ways (a slow zig-zag), so the highlight crosses every part of the card
path = [(lx if r % 2 == 0 else W - lx, ly) for r, ly in enumerate(np.linspace(-200, H + 200, 4)) for lx in np.linspace(-400, W + 400, 10)]
frames = [wobble(render(albedo, hgt, rough, lx, ly)) for lx, ly in path]
res = lightsweep.analyse(frames)
print("info", res["info"])
pad = 40
dmg = res["damage"]
# the result is on the first frame's (padded, wobbled) grid at work size; map truth the same way: approximate by
# warping truth with the first frame's own placement (re-render frame 0's transform is unknown) -> use the scale only
s = dmg.shape[0] / (H + 2 * pad)
T = {k: cv2.resize(cv2.copyMakeBorder(v.astype(np.uint8), pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0), (dmg.shape[1], dmg.shape[0]), interpolation=cv2.INTER_NEAREST) > 0 for k, v in truth.items()}
T = {k: cv2.dilate(v.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0 for k, v in T.items()}
anyd = np.logical_or.reduce(list(T.values()))
card = cv2.resize(cv2.copyMakeBorder(np.ones((H - 60, W - 60), np.uint8), pad + 30, pad + 30, pad + 30, pad + 30, cv2.BORDER_CONSTANT, value=0), (dmg.shape[1], dmg.shape[0])) > 0
for k, m in T.items():
    print(f"{k:8s} found: {(dmg[m] > 0.3).mean()*100:5.1f}% of its area flagged, strongest {dmg[m].max():.2f}")
print(f"clean card flagged: {(dmg[card & ~anyd] > 0.3).mean()*100:.2f}%")

# baseline: the app's single-photo surface check on one frame (the middle one, where the light is overhead)
mid = render(albedo, hgt, rough, W / 2)
ins = condition.inspect_card(Image.fromarray(mid))
print("single photo surface subgrade", ins.subgrades.get("surface"), [f.what for f in ins.findings if f.area == "surface"])
