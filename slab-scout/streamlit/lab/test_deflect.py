"""LAB: simulated test of core/deflect.py (reflected-stripe surface check).

A glossy card with busy artwork and known damage reflects a screen showing shifted stripes (8 steps one way, 8 the
other). Small-angle mirror model: the screen point a pixel reflects moves by 2 * D * surface slope; surface roughness
blurs the reflected stripes (less contrast). The phone adds noise. Compares, at matched false-alarm rates, how much
of each defect is flagged, next to the light-sweep check's numbers on the same kinds of defects.
"""
import sys

import cv2
import numpy as np

sys.path.insert(0, ".")
from core import deflect

rng = np.random.default_rng(5)
H, W = 880, 630


def artwork():
    a = np.zeros((H, W, 3), np.uint8)
    for _ in range(260):
        c = rng.uniform(30, 230, 3).tolist()
        x, y = int(rng.integers(0, W)), int(rng.integers(0, H))
        k = rng.integers(0, 3)
        if k == 0:
            cv2.circle(a, (x, y), int(rng.integers(4, 40)), c, -1)
        elif k == 1:
            cv2.line(a, (x, y), (x + int(rng.integers(-80, 80)), y + int(rng.integers(-80, 80))), c, int(rng.integers(1, 5)))
        else:
            cv2.putText(a, "AB12"[: rng.integers(1, 5)], (x, y), cv2.FONT_HERSHEY_SIMPLEX, rng.uniform(0.4, 1.2), c, 2)
    a[:28], a[-28:], a[:, :28], a[:, -28:] = (230, 200, 60), (230, 200, 60), (230, 200, 60), (230, 200, 60)
    return cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32)


yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
hgt = np.zeros((H, W), np.float32)
rough = np.zeros((H, W), np.float32)   # extra blur of the reflection (px), 0 = mirror-like
truth = {}
hgt += -1.6 * np.exp(-((xx - 180) ** 2 + (yy - 250) ** 2) / (2 * 12 ** 2))
truth["dent"] = ((xx - 180) ** 2 + (yy - 250) ** 2) < 22 ** 2
dist = np.abs((yy - 620) - 0.35 * (xx - 300)) / np.hypot(1, 0.35)
hgt += -1.2 * np.clip(1 - dist / 6, 0, None)
truth["crease"] = (dist < 8) & (xx > 60) & (xx < 570)
sd = np.abs((xx - 420) - 0.9 * (yy - 380)) / np.hypot(1, 0.9)
on = (sd < 1.5) & (yy > 330) & (yy < 470)
hgt -= 0.4 * on
rough[on] = 3.0
truth["scratch"] = cv2.dilate(on.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
sc = ((xx - 470) ** 2 / 40 ** 2 + (yy - 160) ** 2 / 25 ** 2) < 1
rough[sc] = 2.0
truth["scuff"] = sc
# a gentle overall warp (cards are rarely perfectly flat) - must NOT be flagged
hgt += 3.0 * ((xx - W / 2) / W) ** 2 + 2.0 * ((yy - H / 2) / H) ** 2

alb = artwork()
gy_, gx_ = np.gradient(cv2.GaussianBlur(hgt, (5, 5), 0))
D = 60.0            # screen distance in pixel units (amplifies slope into stripe displacement)
period = 14.0       # stripe period as seen in the image (px)


def frames(direction, N=8):
    out = []
    shift = 2 * D * (gx_ if direction == "x" else gy_)
    base = (xx if direction == "x" else yy) + 0.15 * (yy if direction == "x" else xx)   # screen slightly rotated
    u = base + shift
    for k in range(N):
        stripe = 0.5 + 0.5 * np.cos(2 * np.pi * u / period + 2 * np.pi * k / N)
        # roughness blurs the reflected stripes: contrast factor for a Gaussian blur of sigma = rough
        fac = np.exp(-2 * (np.pi * rough / period) ** 2)
        refl = 0.5 + (stripe - 0.5) * fac
        img = 0.35 * alb + 120 * refl + rng.normal(0, 2.0, alb.shape)
        out.append(np.clip(img, 0, 255).astype(np.uint8))
    return out


res = deflect.analyse(frames("x"), frames("y"))
print("info", res["info"])
sc_ = res["maps"]["score"]
T = {k: cv2.dilate(v.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0 for k, v in truth.items()}
anyd = np.logical_or.reduce(list(T.values()))
card = np.zeros((H, W), bool)
card[30:-30, 30:-30] = True
clean = sc_[card & ~anyd]
for fpr in (0.5, 1, 2):
    th = np.percentile(clean, 100 - fpr)
    print(f"at {fpr}% clean false alarms: " + ", ".join(f"{k} {(sc_[m] > th).mean()*100:.0f}%" for k, m in T.items()))
ge = cv2.dilate((cv2.Canny(alb.astype(np.uint8), 40, 120) > 0).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
th = np.percentile(clean, 99)
print(f"false alarms at 1%: on print edges {(sc_[ge & card & ~anyd] > th).mean()*100:.1f}%, elsewhere {(sc_[~ge & card & ~anyd] > th).mean()*100:.2f}%")

# per signal: how strongly each defect stands out (strongest point vs the clean card's 99.9th percentile)
for name in ("z_slope", "z_gloss", "score"):
    m = res["maps"][name]
    th = np.percentile(m[card & ~anyd], 99.9)
    print(f"{name:8s} clean 99.9th pct {th:6.1f} | " + ", ".join(f"{k} max {m[t].max():6.1f} ({(m[t] > th).mean()*100:.0f}% of area)" for k, t in T.items()))
