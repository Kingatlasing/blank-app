"""LAB (not used by the app yet): surface damage from a short "light sweep" video.

The person tilts the card slowly under one light (or moves the phone's light over it) for 2-3 seconds. Every frame is
lined up with the first (multiframe.align). Each spot on the card then has a brightness curve over time: the glossy
surface reflects the light most strongly at the moment its surface faces halfway between the light and the camera.

On a flat, undamaged card that moment changes smoothly across the card. Damage breaks it:
  - dents, creases, bends and indentations tilt the surface, so their peak comes earlier or later than their
    surroundings (peak-time residual);
  - scratches and scuffs scatter the light, so their peak is lower and wider and they stay bright for longer
    (peak sharpness and gloss residuals).
The print / artwork changes the brightness level but not when the peak happens, which is why this sees damage
over holo foil and busy art where a single photo can't. (Reflectance transformation imaging, used by museums to
read worn coins and inscriptions, works on the same principle.)

analyse(frames) -> {"maps": {...}, "damage": HxW float map 0..1, "info": {...}}
"""
from __future__ import annotations

import cv2
import numpy as np

from core import multiframe


def _stack(frames: list[np.ndarray], work: int = 900) -> tuple[np.ndarray, dict]:
    base = frames[0]
    s = work / max(base.shape[:2])
    size = (int(base.shape[1] * s), int(base.shape[0] * s))
    out, used = [cv2.resize(base, size, interpolation=cv2.INTER_AREA)], 1
    for f in frames[1:]:
        w = multiframe.align(base, f)
        if w is None:
            continue
        out.append(cv2.resize(w, size, interpolation=cv2.INTER_AREA))
        used += 1
    return np.stack(out), {"frames": used, "offered": len(frames)}


def _smooth_surface(m: np.ndarray, valid: np.ndarray, k: int = 61) -> np.ndarray:
    """Large-scale trend of a map (what a flat card would give), ignoring invalid pixels."""
    v = valid.astype(np.float32)
    num = cv2.GaussianBlur(np.where(valid, m, 0).astype(np.float32), (k, k), 0)
    den = cv2.GaussianBlur(v, (k, k), 0)
    return num / np.maximum(den, 1e-3)


def analyse(frames: list[np.ndarray]) -> dict:
    S, info = _stack([np.asarray(f) for f in frames])
    n = len(S)
    info["frames_used"] = n
    if n < 6:
        return {"ok": False, "info": info}
    V = np.stack([cv2.cvtColor(f, cv2.COLOR_RGB2HSV)[..., 2] for f in S]).astype(np.float32)   # n,h,w brightness
    V = cv2.GaussianBlur(V.transpose(1, 2, 0), (5, 5), 1.5).transpose(2, 0, 1)   # forgive sub-pixel alignment error
    lo = np.percentile(V, 10, axis=0)        # diffuse (print) level
    hi = V.max(0)
    spec = hi - lo                            # how strongly the spot reflects the light
    valid = spec > max(12.0, float(np.percentile(spec, 30)) * 0.5)   # the highlight actually crossed this spot
    valid = cv2.erode(valid.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0   # not right at the card edge / gaps
    # Each frame's highlight on an undamaged card is a broad, smooth patch. A median filter keeps that patch and
    # drops anything small, so the difference between a spot's curve and the filtered curves around it is the
    # light it reflects differently from a flat glossy surface: tilted (dent / crease) or scattering (scratch / scuff).
    # Separate the highlight from the print: as the light moves, the print's (diffuse) brightness changes slowly,
    # while the glossy highlight flashes past in a few frames. Taking away a running minimum over time leaves only
    # the highlight, whatever colour the print under it is.
    from scipy.ndimage import grey_opening, median_filter
    Sp = V - grey_opening(V, size=(9, 1, 1))
    nrm = np.sqrt((Sp ** 2).sum(0)) + 1e-3
    Cn = Sp / nrm                                # shape of each spot's highlight curve (its size cancels out)
    ref = median_filter(Cn, size=(1, 21, 21))    # what the flat card around it does
    ref /= np.sqrt((ref ** 2).sum(0)) + 1e-3
    r_peak = 1 - (Cn * ref).sum(0)               # 0 = same highlight timing as around it, up to 2 = opposite
    r_mean = np.log((nrm + 5) / (median_filter(nrm, size=21) + 5))   # highlight weaker / stronger than around it
    r_mean = np.abs(r_mean)
    r_gloss = _smooth_surface(spec, valid) - spec   # less gloss than around it (matte scuff)

    def z(m):
        mv = m[valid]
        med = np.median(mv)
        mad = np.median(np.abs(mv - med)) * 1.4826 + 1e-3
        return np.where(valid, (m - med) / mad, 0)
    zp, zm, zs = z(r_peak), z(r_mean), z(r_gloss)
    score = np.maximum.reduce([zp, zm, np.clip(zs, 0, None)])
    score = cv2.morphologyEx(score.astype(np.float32), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))   # single-pixel noise
    damage = np.clip((score - 4) / 6, 0, 1)
    info.update(valid_pct=round(float(valid.mean() * 100), 1), damage_pct=round(float((damage > 0.3).mean() * 100), 2))
    return {"ok": True, "info": info, "damage": damage, "maps": {"score": score, "gloss": spec, "valid": valid, "z_peak": zp, "z_mean": zm, "z_gloss": zs}}
