"""Automatic condition inspection of a straightened card photo (630 x 880).

What it checks (the same things PSA / TAG / CGC graders look at):
  - Corners: zooms into each corner and measures whitening / fraying (light specks where the border
    colour should be) and missing material (background showing where the card should be).
  - Edges:   the same along all four edges; counts separate chips.
  - Surface: scratches (thin bright lines, found with an inverted top-hat filter), print specks / dents
    (small spots), stains (blotches that differ from the border colour), and possible creases / folds
    (long straight lines that cross the card and aren't part of the frame).
  - Fading:  colour saturation and contrast compared with the official image when one is available.
  - Photo quality: sharpness and glare, because a blurry or glare-heavy photo hides defects.
  - Error / misprint check: compares the scan with the official image region by region.

It also produces the inspection views shown in the app: zoomed corners, zoomed edges, inverted colours,
a black-and-white (adaptive threshold) scan, a scratch-enhanced view, and a defect map.

These are measurements from a phone photo, not a grading company's microscope; lighting and glare
matter. Each finding says how sure it is.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

CORNER = 70     # px of each corner inspected (card is 630 px wide ≈ 10 px per mm)
EDGE = 14       # px band along each edge
MARGIN = 5      # px ignored at the very edge (straightening wobble)


@dataclass
class Finding:
    area: str        # corners / edges / surface / centering / photo / error
    where: str       # e.g. "top-left corner"
    what: str        # plain-language description
    severity: float  # 0 (trivial) .. 1 (severe)
    sure: str = "likely"  # likely / possible


@dataclass
class Inspection:
    subgrades: dict = field(default_factory=dict)   # corners / edges / surface -> 1..10
    findings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    views: dict = field(default_factory=dict)       # name -> PIL image
    photo_ok: bool = True
    photo_notes: list = field(default_factory=list)
    error_regions: list = field(default_factory=list)


def _arr(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("RGB"))


def _border_color(a: np.ndarray) -> np.ndarray:
    """Median colour of the border band (a few px in from the edge, avoiding corners)."""
    h, w = a.shape[:2]
    band = np.concatenate([
        a[MARGIN + 4:MARGIN + 14, CORNER:w - CORNER].reshape(-1, 3),
        a[h - MARGIN - 14:h - MARGIN - 4, CORNER:w - CORNER].reshape(-1, 3),
        a[CORNER:h - CORNER, MARGIN + 4:MARGIN + 14].reshape(-1, 3),
        a[CORNER:h - CORNER, w - MARGIN - 14:w - MARGIN - 4].reshape(-1, 3),
    ])
    return np.median(band, axis=0)


def _lab(a: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.int16)


def _whitening_mask(a: np.ndarray, border_rgb: np.ndarray) -> np.ndarray:
    """Pixels that are much lighter and greyer than the border colour: whitening, fraying, chipping."""
    lab = _lab(a)
    b_lab = _lab(border_rgb.reshape(1, 1, 3).astype(np.uint8))[0, 0]
    b_hsv = cv2.cvtColor(border_rgb.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2HSV)[0, 0]
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
    if b_hsv[1] < 50 and b_hsv[2] > 190:  # white / silver border: whitening can't be seen by colour
        return np.zeros(a.shape[:2], bool)
    lighter = (lab[..., 0] - b_lab[0]) > 22
    greyish = hsv[..., 1] < max(55, int(b_hsv[1]) - 70)
    bright = hsv[..., 2] > 185
    return lighter & greyish & bright


def _background_mask(a: np.ndarray) -> np.ndarray:
    """Very dark, flat pixels = the table showing through (missing corner / dinged edge)."""
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
    return hsv[..., 2] < 45


def _corner_boxes(w: int, h: int):
    c = CORNER
    return {"top-left": (0, 0, c, c), "top-right": (w - c, 0, w, c), "bottom-left": (0, h - c, c, h), "bottom-right": (w - c, h - c, w, h)}


def _rounding_expected(c: int) -> np.ndarray:
    """Mask of the area outside a standard rounded corner (radius ≈ 3.2 mm ≈ 32 px), for the top-left box."""
    r = 32
    yy, xx = np.mgrid[0:c, 0:c]
    outside = ((xx < r) & (yy < r) & ((xx - r) ** 2 + (yy - r) ** 2 > r * r))
    return outside


def _sev_to_grade(sev: float) -> float:
    """0 -> 10, 0.1 -> 9, 0.25 -> 8, 0.45 -> 7, 0.6 -> 6, 0.75 -> 5, 0.9 -> 4."""
    for limit, g in ((0.03, 10.0), (0.1, 9.0), (0.25, 8.0), (0.45, 7.0), (0.6, 6.0), (0.75, 5.0), (0.9, 4.0)):
        if sev <= limit:
            return g
    return 3.0


def inspect_card(card: Image.Image, official: Image.Image | None = None, is_back: bool = False) -> Inspection:
    a = _arr(card)
    h, w = a.shape[:2]
    res = Inspection()
    gray = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    side = "back" if is_back else "front"

    # ---------- photo quality ----------
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    glare = float((gray > 250).mean())
    res.metrics.update(sharpness=round(sharp, 1), glare_pct=round(glare * 100, 2))
    if sharp < 60:
        res.photo_ok = False
        res.photo_notes.append("Photo looks soft or blurry; small scratches and whitening may be missed. Hold steady, more light, no zoom.")
    if glare > 0.03:
        res.photo_ok = False
        res.photo_notes.append("Glare on the card; tilt it slightly away from the light so reflections don't hide the surface.")

    border = _border_color(a)
    white_m = _whitening_mask(a, border)
    bg_m = _background_mask(a)

    # ---------- corners ----------
    corner_sev = {}
    exp_tl = _rounding_expected(CORNER)
    for name, (x0, y0, x1, y1) in _corner_boxes(w, h).items():
        wm = white_m[y0:y1, x0:x1]
        bm = bg_m[y0:y1, x0:x1].copy()
        exp = exp_tl
        if "right" in name:
            exp = exp[:, ::-1]
        if "bottom" in name:
            exp = exp[::-1, :]
        # whitening in the outer L-shaped band of the corner
        band = np.zeros_like(wm)
        band[MARGIN:MARGIN + 14, MARGIN:] = True
        band[MARGIN:, MARGIN:MARGIN + 14] = True
        if "right" in name:
            band = band[:, ::-1]
        if "bottom" in name:
            band = band[::-1, :]
        band &= ~exp
        white_frac = float((wm & band).sum()) / max(1, band.sum())
        missing = float((bm & ~exp & band).sum()) / max(1, band.sum())  # band already skips the straightening margin
        sev = min(1.0, white_frac * 6 + missing * 4)
        corner_sev[name] = sev
        if white_frac > 0.01:
            res.findings.append(Finding("corners", f"{name} corner ({side})", f"Whitening / fraying ({white_frac*100:.1f}% of the corner edge)", min(1, white_frac * 6)))
        if missing > 0.04:
            res.findings.append(Finding("corners", f"{name} corner ({side})", "Corner looks rounded, bent or dinged (background showing)", min(1, missing * 4), "possible"))
    worst = max(corner_sev.values())
    second = sorted(corner_sev.values())[-2]
    res.subgrades["corners"] = _sev_to_grade(worst * 0.75 + second * 0.25)
    res.metrics["corner_severity"] = {k: round(v, 3) for k, v in corner_sev.items()}

    # ---------- edges ----------
    edge_boxes = {"top": (CORNER, MARGIN, w - CORNER, MARGIN + EDGE), "bottom": (CORNER, h - MARGIN - EDGE, w - CORNER, h - MARGIN),
                  "left": (MARGIN, CORNER, MARGIN + EDGE, h - CORNER), "right": (w - MARGIN - EDGE, CORNER, w - MARGIN, h - CORNER)}
    chips_total, edge_sev = 0, {}
    for name, (x0, y0, x1, y1) in edge_boxes.items():
        wm = (white_m[y0:y1, x0:x1] | bg_m[y0:y1, x0:x1]).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(wm, 8)
        chips = [s for s in stats[1:] if s[cv2.CC_STAT_AREA] >= 4]
        frac = float(wm.mean())
        edge_sev[name] = min(1.0, frac * 8 + len(chips) * 0.04)
        chips_total += len(chips)
        if chips:
            res.findings.append(Finding("edges", f"{name} edge ({side})", f"{len(chips)} chip{'s' if len(chips) != 1 else ''} / white spot{'s' if len(chips) != 1 else ''} along the edge", edge_sev[name]))
    ev = sorted(edge_sev.values())
    res.subgrades["edges"] = _sev_to_grade(ev[-1] * 0.6 + ev[-2] * 0.25 + ev[-3] * 0.15)
    res.metrics["edge_chips"] = chips_total

    # ---------- surface ----------
    inner = np.zeros_like(gray, bool)
    inner[MARGIN + EDGE:h - MARGIN - EDGE, MARGIN + EDGE:w - MARGIN - EDGE] = True
    # thin bright lines (scratches catch the light): white top-hat, then keep long thin components
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
    lines_m = ((tophat > 40) & inner).astype(np.uint8)
    n, lab_img, stats, _ = cv2.connectedComponentsWithStats(lines_m, 8)
    scratch_len, scratches = 0, []
    scratch_mask = np.zeros_like(lines_m)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        length = float(np.hypot(bw, bh))
        thin = area / max(1.0, length) < 4.5 and (bw * bh) > area * 3  # a line, not a blob or a letter
        if length >= 30 and thin:
            scratch_len += length
            scratches.append((x, y, bw, bh))
            scratch_mask[lab_img == i] = 1
    # small dark specks on light areas (print specks, dents, debris)
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    grad = cv2.blur(np.abs(cv2.Laplacian(cv2.GaussianBlur(gray, (3, 3), 0), cv2.CV_32F)), (25, 25))
    flat = grad < 6
    specks_m = ((blackhat > 45) & inner & (gray > 120) & flat).astype(np.uint8)
    n2, _, st2, _ = cv2.connectedComponentsWithStats(specks_m, 8)
    specks = [s for s in st2[1:] if 4 <= s[cv2.CC_STAT_AREA] <= 60]
    # stains in the border band: patches that differ in colour from the border but aren't whitening
    lab = _lab(a)
    b_lab = _lab(border.reshape(1, 1, 3).astype(np.uint8))[0, 0]
    ring = np.zeros_like(gray, bool)
    ring[MARGIN + 4:MARGIN + 30, :] = True
    ring[h - MARGIN - 30:h - MARGIN - 4, :] = True
    ring[:, MARGIN + 4:MARGIN + 30] = True
    ring[:, w - MARGIN - 30:w - MARGIN - 4] = True
    ring[:CORNER, :CORNER] = ring[:CORNER, -CORNER:] = ring[-CORNER:, :CORNER] = ring[-CORNER:, -CORNER:] = False
    dcol = np.abs(lab[..., 1] - b_lab[1]) + np.abs(lab[..., 2] - b_lab[2]) + np.abs(lab[..., 0] - b_lab[0]) // 2
    borderlike = dcol < 22
    stain_m = ((dcol > 30) & ring & ~white_m).astype(np.uint8)
    stain_m = cv2.morphologyEx(stain_m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n3, lab3, st3, _ = cv2.connectedComponentsWithStats(stain_m, 8)
    stains = []
    keep = np.zeros_like(stain_m)
    for i in range(1, n3):
        if not (40 <= st3[i][cv2.CC_STAT_AREA] <= 3000):
            continue
        blob = (lab3 == i).astype(np.uint8)
        rim = cv2.dilate(blob, np.ones((9, 9), np.uint8)).astype(bool) & ~blob.astype(bool)
        if borderlike[rim].mean() > 0.75:  # surrounded by clean border = a spot, not the artwork frame
            stains.append(st3[i])
            keep[blob.astype(bool)] = 1
    stain_m = keep
    # possible creases / folds: long straight lines that aren't horizontal/vertical frame lines
    edges_c = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    hl = cv2.HoughLinesP(edges_c, 1, np.pi / 180, 70, minLineLength=int(min(w, h) * 0.3), maxLineGap=25)
    creases = []
    for l in (hl if hl is not None else []):
        x1, y1, x2, y2 = l[0]
        ang = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180
        if min(ang, abs(90 - ang), abs(180 - ang)) > 12:  # diagonal-ish: frames and text are straight
            creases.append((x1, y1, x2, y2))

    sev = 0.0
    if scratches:
        s_sev = min(1.0, scratch_len / 900)
        sev = max(sev, s_sev)
        res.findings.append(Finding("surface", side, f"{len(scratches)} possible scratch{'es' if len(scratches) != 1 else ''} (total ~{scratch_len/10:.0f} mm)", s_sev, "possible" if len(scratches) < 3 else "likely"))
    if len(specks) > 6:
        p_sev = min(0.5, len(specks) / 60)
        sev = max(sev, p_sev)
        res.findings.append(Finding("surface", side, f"{len(specks)} small specks / dimples (print dots, debris or dents)", p_sev, "possible"))
    if stains:
        st_sev = min(0.7, sum(s[cv2.CC_STAT_AREA] for s in stains) / 2500)
        sev = max(sev, st_sev)
        res.findings.append(Finding("surface", side, f"{len(stains)} discoloured patch{'es' if len(stains) != 1 else ''} in the border (stain, wax or ink)", st_sev, "possible"))
    if creases:
        sev = max(sev, 0.85)
        res.findings.append(Finding("surface", side, f"Possible crease / fold line ({len(creases)} long straight line{'s' if len(creases) != 1 else ''} across the card)", 0.85, "possible"))
    res.subgrades["surface"] = _sev_to_grade(sev)
    if creases:  # PSA: a light crease caps the card around 4 (VG-EX)
        res.subgrades["surface"] = min(res.subgrades["surface"], 4.0)
    res.metrics.update(scratches=len(scratches), specks=len(specks), stains=len(stains), creases=len(creases))

    # ---------- fading & error check vs the official image ----------
    if official is not None:
        o = _arr(official.convert("RGB").resize((w, h)))
        hs, ho = cv2.cvtColor(a, cv2.COLOR_RGB2HSV), cv2.cvtColor(o, cv2.COLOR_RGB2HSV)
        sat_ratio = float(hs[..., 1].mean() / max(1.0, ho[..., 1].mean()))
        con_ratio = float(gray.std() / max(1.0, cv2.cvtColor(o, cv2.COLOR_RGB2GRAY).std()))
        res.metrics.update(saturation_vs_official=round(sat_ratio, 2), contrast_vs_official=round(con_ratio, 2))
        if sat_ratio < 0.7 and con_ratio < 0.8:
            res.findings.append(Finding("surface", side, f"Colours look faded vs the official card ({sat_ratio*100:.0f}% saturation). Could be sun fading or dim lighting.", 0.5, "possible"))
        res.error_regions = _diff_regions(a, o)
        if res.error_regions:
            res.findings.append(Finding("error", side, f"{len(res.error_regions)} area{'s' if len(res.error_regions) != 1 else ''} look different from the official card: possible misprint / error card, alteration, or a different version", 0.4, "possible"))

    res.views = _views(card, a, gray, white_m, bg_m, scratch_mask, specks_m, stain_m, creases, res.error_regions)
    return res


def _diff_regions(a: np.ndarray, o: np.ndarray, grid=(7, 10)) -> list[tuple[int, int, int, int]]:
    """Cells where the scan differs a lot from the official image after matching overall brightness/colour."""
    h, w = a.shape[:2]
    A = cv2.GaussianBlur(a, (9, 9), 0).astype(np.float32)
    O = cv2.GaussianBlur(o, (9, 9), 0).astype(np.float32)
    A = (A - A.mean((0, 1))) / (A.std((0, 1)) + 1e-3)
    O = (O - O.mean((0, 1))) / (O.std((0, 1)) + 1e-3)
    d = np.abs(A - O).mean(2)
    gx, gy = grid
    cw, ch = w // gx, h // gy
    cells = [(float(d[j * ch:(j + 1) * ch, i * cw:(i + 1) * cw].mean()), i, j) for i in range(gx) for j in range(gy)]
    vals = np.array([c[0] for c in cells])
    med = float(np.median(vals))
    out = []
    for v, i, j in cells:
        if v > max(1.1, med * 2.2):
            out.append((i * cw, j * ch, cw, ch))
    return out if len(out) <= len(cells) * 0.35 else []  # everything different = wrong match, not an error card


def _zoom(im: Image.Image, box, scale=3) -> Image.Image:
    x0, y0, x1, y1 = box
    return im.crop(box).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.LANCZOS)


def _views(card, a, gray, white_m, bg_m, scratch_mask, specks_m, stain_m, creases, err) -> dict:
    h, w = a.shape[:2]
    views = {}
    # zoomed corners, 2x2
    c = _corner_boxes(w, h)
    tiles = [_zoom(card, c[k], 3) for k in ("top-left", "top-right", "bottom-left", "bottom-right")]
    t = tiles[0].size[0]
    grid = Image.new("RGB", (t * 2 + 6, t * 2 + 6), (20, 22, 28))
    for i, im in enumerate(tiles):
        grid.paste(im, ((i % 2) * (t + 6), (i // 2) * (t + 6)))
    views["Corners (3× zoom)"] = grid
    # zoomed edges: stacked strips
    strips = [card.crop((0, 0, w, 40)), card.crop((0, h - 40, w, h)),
              card.crop((0, 0, 40, h)).rotate(90, expand=True), card.crop((w - 40, 0, w, h)).rotate(90, expand=True)]
    strips = [s.resize((s.size[0] * 2, s.size[1] * 2), Image.LANCZOS) for s in strips]
    sw = max(s.size[0] for s in strips)
    edges_im = Image.new("RGB", (sw, sum(s.size[1] + 6 for s in strips)), (20, 22, 28))
    y = 0
    for s in strips:
        edges_im.paste(s, (0, y))
        y += s.size[1] + 6
    views["Edges (2× zoom: top, bottom, left, right)"] = edges_im
    views["Inverted colours"] = Image.fromarray(255 - a)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 9)
    views["Black & white scan"] = Image.fromarray(bw)
    # scratch-enhanced: local contrast (CLAHE) on greyscale + high-pass, so light-catching lines pop
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    hp = cv2.addWeighted(clahe, 1.8, cv2.GaussianBlur(clahe, (0, 0), 6), -0.8, 0)
    views["Surface detail (contrast boosted)"] = Image.fromarray(hp)
    # defect map: the card is dimmed so the marks stand out on any border colour
    over = (a.astype(np.float32) * 0.45).astype(np.uint8)
    marks = [((white_m | bg_m) & _edge_band(h, w), (255, 0, 255)),  # whitening only counts at the edges (scratch_mask.astype(bool), (255, 230, 0)),
             (specks_m.astype(bool), (0, 220, 255)), (stain_m.astype(bool), (120, 255, 0))]
    for m, col in marks:
        m = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)  # make tiny defects visible
        over[m] = col
    for x1, y1, x2, y2 in creases:
        cv2.line(over, (x1, y1), (x2, y2), (255, 255, 255), 3)
    for x, y, cw, ch in err:
        cv2.rectangle(over, (x, y), (x + cw, y + ch), (255, 140, 0), 3)
    views["Defect map"] = Image.fromarray(over)
    return views


def _edge_band(h, w, px=EDGE + MARGIN):
    """The band along the card edge, skipping the few straightening-margin pixels at the very edge."""
    m = np.zeros((h, w), bool)
    m[:px, :] = m[-px:, :] = True
    m[:, :px] = m[:, -px:] = True
    m[:MARGIN, :] = m[-MARGIN:, :] = False
    m[:, :MARGIN] = m[:, -MARGIN:] = False
    return m


LEGEND = "Magenta = whitening / chipping · Yellow = scratches · Cyan = specks / dents · Green = stains · White line = possible crease · Orange box = differs from the official card"


def subgrade_to_option(g: float) -> str:
    """Nearest checklist answer for an automatic subgrade (the person can still change it)."""
    if g >= 10:
        return "Flawless"
    if g >= 9:
        return "One tiny flaw"
    if g >= 7.5:
        return "Light wear"
    if g >= 5.5:
        return "Noticeable wear"
    if g >= 3.5:
        return "Heavy wear"
    return "Crease / damage"
