"""Autograph check: finds a signature on the card, tells on-card from sticker autos, reads the maker's
certification wording, and estimates the signature's own grade (boldness, skips) the way PSA/DNA and Beckett
describe it. It does NOT authenticate a signature: PSA/DNA, JSA and Beckett do that by comparing with known
exemplars of the person's signature, ink analysis and flow/pressure study under magnification. Research
systems for automated signature verification need genuine reference signatures from the same signer, so the
app only reports what it can see and points to the right service.

PSA autograph grades (psacard.com/services/autographgradingstandards): 10 = bold, no skipping or retracing,
typical of the person's signature; 9 = a very light skip; 8 = more noticeable skip or very slight fading,
flaws on up to 20% of the signature; 7 = even fading or a minor blemish.
"""
from __future__ import annotations

import re

import cv2
import numpy as np
from PIL import Image

CERT = re.compile(
    r"certified\s+auto|authentic\s+(?:auto|signature)|autograph(?:ed)?\s+(?:card|issue)|"
    r"signed\s+(?:by|in\s+person)|guaranteed\s+(?:by|authentic)|topps\s+certified|panini\s+authentic|"
    r"upper\s+deck\s+(?:authenticated|certif)|leaf\s+(?:authentic|certif)|\bauto(?:graph)?\s*(?:#|serial)|on[- ]card\s+auto",
    re.I,
)


def _strokes(card: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    g = cv2.cvtColor(np.array(card.convert("RGB")), cv2.COLOR_RGB2GRAY)
    # thin dark marks on a lighter background (ink), independent of overall brightness
    bh = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    m = (bh > 38).astype("uint8")
    return g, m


def check(card: Image.Image, text: str = "", back_text: str = "", card_type: str = "") -> dict:
    """{'found', 'kind' ('on-card' | 'sticker' | ''), 'certified' (maker's wording seen), 'box' (x,y,w,h in
    card px), 'auto_grade', 'notes', 'verify'}"""
    w, h = card.size
    rgb = np.array(card.convert("RGB"))
    g, m = _strokes(card)
    def search(fill_max, curl_min, same_min, width_max):
        joined = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=1)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
        best = None
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if bw < 0.18 * w or bh < 0.035 * h or bh > 0.3 * h or bw < 2.0 * bh:
                continue  # signatures are long and low
            fill = area / float(bw * bh)
            if fill > fill_max:
                continue  # solid shapes / printed blocks, not pen strokes
            comp = (lab[y:y + bh, x:x + bw] == i).astype("uint8")
            # cursive: one long connected stroke that curls (many direction changes); printed text / straight frame
            # lines break into letters or stay straight
            cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            per = sum(cv2.arcLength(c, True) for c in cs)
            curl = per / (2 * (bw + bh))
            if curl < curl_min:
                continue
            # one pen: the ink is a single colour and the stroke keeps an even, thin width (artwork outlines vary)
            ink = rgb[y:y + bh, x:x + bw][(lab[y:y + bh, x:x + bw] == i) & (m[y:y + bh, x:x + bw] > 0)]
            if len(ink) < 40:
                continue
            labc = cv2.cvtColor(ink.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype("float32")
            same = np.abs(labc[:, 1:] - np.median(labc[:, 1:], axis=0)).max(axis=1) <= 10
            if same.mean() < same_min:
                continue  # most of the stroke must be one ink colour
            raw = m[y:y + bh, x:x + bw] * (lab[y:y + bh, x:x + bw] == i)
            dist = cv2.distanceTransform(raw.astype("uint8"), cv2.DIST_L2, 3)
            widths = dist[dist > 0]
            if not len(widths) or float(np.percentile(widths, 90)) > width_max:
                continue
            score = curl * min(bw / w, 0.6)
            if best is None or score > best[0]:
                best = (score, (int(x), int(y), int(bw), int(bh)), comp, curl)
        return best

    wants = card_type.lower().startswith("auto")
    best = search(0.45, 2.2, 0.6, 4.0)
    if best is None and wants:  # the person says it's signed: look harder (ink crossing busy artwork)
        best = search(0.65, 1.7, 0.4, 6.0)
    certified = bool(CERT.search(f"{text}\n{back_text}"))
    out = {"found": False, "kind": "", "certified": certified, "box": None, "auto_grade": None, "notes": [], "verify": ""}
    if not best and not certified and not wants:
        return out
    if best:
        _, (x, y, bw, bh), comp, curl = best
        out.update(found=True, box=(x, y, bw, bh))
        if not (certified or wants):
            out["notes"].append("Possible autograph spotted (mark the card type as Autograph if it is signed).")
        # sticker: the signature sits on a light, even, rectangular patch with its own straight outline
        pad = int(0.04 * w)
        x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(w, x + bw + pad), min(h, y + bh + pad)
        patch = g[y0:y1, x0:x1].astype("float32")
        ink_near = np.zeros(patch.shape, np.uint8)  # the signature's strokes placed in the padded patch
        ink_near[y - y0:y - y0 + bh, x - x0:x - x0 + bw] = comp[: bh, : bw]
        bg = patch[cv2.dilate(ink_near, np.ones((9, 9), np.uint8)) == 0]
        even = float(np.std(bg)) < 22 and float(np.mean(bg)) > 170
        edges = cv2.Canny(g[max(0, y0 - pad):min(h, y1 + pad), max(0, x0 - pad):min(w, x1 + pad)], 40, 120)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 40, minLineLength=int(bw * 0.8), maxLineGap=6)
        straight = lines is not None and len(np.asarray(lines).reshape(-1, 4)) >= 2
        out["kind"] = "sticker" if even and straight else "on-card"
        # signature grade: ink strength and breaks (skips) along the stroke
        ink = g[y:y + bh, x:x + bw][comp[: bh, : bw] > 0]
        paper = g[y:y + bh, x:x + bw][comp[: bh, : bw] == 0]
        contrast = float(np.median(paper) - np.median(ink)) if len(ink) and len(paper) else 0.0
        pieces = cv2.connectedComponents(m[y:y + bh, x:x + bw])[0] - 1
        if contrast >= 70 and pieces <= 4:
            ag, why = 10, "bold and unbroken"
        elif contrast >= 55 and pieces <= 8:
            ag, why = 9, "strong, with a very light skip at most"
        elif contrast >= 40:
            ag, why = 8, "slight fading or a noticeable skip"
        else:
            ag, why = 7, "faded or broken in places"
        out["auto_grade"] = ag
        out["notes"].append(f"Signature looks {why} in this photo (autograph grade estimate {ag}).")
        out["notes"].append("Sticker auto: signed on a label that was applied at the factory." if out["kind"] == "sticker"
                            else "On-card auto: signed directly on the card.")
    elif wants:
        out["notes"].append("No signature found in this photo. Hold the light at an angle so the ink shows, or retake closer.")
    if certified:
        out["notes"].append("The card carries the maker's certified-autograph wording: the manufacturer guarantees the signature "
                            "(e.g. Topps replaces or credits a certified auto a grader rejects).")
    out["verify"] = ("Manufacturer-certified autos are guaranteed by the maker; check the serial / back wording matches the set." if certified else
                     "Not a certified card: only an authenticator (PSA/DNA, JSA or Beckett) can verify the signature, by comparing it "
                     "with known examples of the person's signature, ink and flow. The app can't confirm it's real.")
    return out
