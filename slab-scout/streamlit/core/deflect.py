"""LAB (not used by the app yet): surface shape from reflected stripes (phase-measuring deflectometry).

A card's surface is glossy, so it mirrors whatever is in front of it. A laptop / monitor shows black-white stripes that
shift step by step (first stripes running one way, then the other); the phone films the card, which reflects them.
For every pixel, the brightness over the N shifted steps traces a cosine whose phase says WHICH part of the screen that
pixel reflects. On a flat card that changes smoothly from pixel to pixel; anything that tilts the surface (a dent, a
crease, a bend, an indentation, the groove of a scratch) moves the reflected point, so the phase jumps locally.
Anything that roughens the surface (scuffs, scratches, worn gloss) blurs the reflection, so the stripes' contrast
there drops. The printed artwork only adds a constant brightness per pixel, which the phase calculation ignores.

Method (standard N-step phase shifting, then only local comparisons, so no phase unwrapping is needed):
  phase  = atan2(-sum I_k sin(2 pi k/N), sum I_k cos(2 pi k/N)),   contrast = |...| * 2/N
  slope  = wrapped phase difference to the neighbouring pixel (local stripe frequency), in both directions,
           for both stripe directions; damage = how far it departs from its smoothed surroundings
  gloss  = contrast relative to its surroundings (a drop = scuffed / scratched)

analyse(frames_x, frames_y) -> {"damage": map 0..1, "maps": {...}, "info": {...}}
"""
from __future__ import annotations

import cv2
import numpy as np


def phase(frames: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Phase, stripe contrast and mean brightness from N equally shifted frames (grayscale float)."""
    N = len(frames)
    I = np.stack([f.astype(np.float32) for f in frames])
    k = np.arange(N, dtype=np.float32)[:, None, None]
    s = (I * np.sin(2 * np.pi * k / N)).sum(0)
    c = (I * np.cos(2 * np.pi * k / N)).sum(0)
    return np.arctan2(-s, c), np.hypot(s, c) * 2 / N, I.mean(0)


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def _grad(ph):
    gx = np.zeros_like(ph)
    gy = np.zeros_like(ph)
    gx[:, 1:-1] = _wrap(ph[:, 2:] - ph[:, :-2]) / 2
    gy[1:-1] = _wrap(ph[2:] - ph[:-2]) / 2
    return gx, gy


def _z(m, valid, floor=1e-6):
    v = m[valid]
    med = np.median(v)
    mad = max(np.median(np.abs(v - med)) * 1.4826, floor)
    return np.where(valid, (m - med) / mad, 0)


def _trend(m, k):
    """Robust local trend (median over k x k), computed at quarter resolution in float so it stays exact enough."""
    from scipy.ndimage import median_filter
    h, w = m.shape
    small = cv2.resize(m.astype(np.float32), (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA)
    t = median_filter(small, size=max(3, k // 4) | 1, mode="nearest")
    return cv2.resize(t, (w, h), interpolation=cv2.INTER_LINEAR)


def analyse(frames_x: list[np.ndarray], frames_y: list[np.ndarray], k_smooth: int = 31, min_contrast: float = 6.0) -> dict:
    gray = lambda f: cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) if f.ndim == 3 else f
    px, bx, ax = phase([gray(f) for f in frames_x])
    py, by, ay = phase([gray(f) for f in frames_y])
    contrast = np.minimum(bx, by)
    valid = cv2.erode((contrast > min_contrast).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    valid[:4], valid[-4:], valid[:, :4], valid[:, -4:] = False, False, False, False   # gradients undefined at the border
    # local stripe frequency in both directions, for both stripe sets: four slope-like maps
    res = np.zeros(px.shape, np.float32)
    for ph in (px, py):
        for g in _grad(ph):
            g = g.astype(np.float32)
            res += (g - _trend(g, k_smooth)) ** 2
    slope = np.sqrt(res)
    # gloss: stripe contrast against its surroundings (contrast also depends on the print's darkness only weakly,
    # since the reflection sits on top of the print; normalise by the local median)
    gloss_drop = np.clip(1 - contrast / (_trend(contrast, k_smooth) + 1e-3), 0, 1)
    # spreads have floors: a perfectly even card would otherwise turn camera noise into huge scores
    zs, zg = _z(slope, valid, floor=0.02), _z(gloss_drop, valid, floor=0.02)
    score = np.clip(zs, 0, None) + 0.5 * np.clip(zg, 0, None)
    score = cv2.morphologyEx(score.astype(np.float32), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    damage = np.clip((score - 5) / 8, 0, 1)
    info = {"steps": [len(frames_x), len(frames_y)], "valid_pct": round(float(valid.mean() * 100), 1),
            "damage_pct": round(float((damage > 0.3).mean() * 100), 2)}
    return {"ok": True, "damage": damage, "info": info,
            "maps": {"score": score, "z_slope": zs, "z_gloss": zg, "contrast": contrast, "valid": valid, "phase_x": px, "phase_y": py}}
