"""Grade estimates from measured centering + a condition checklist (no AI needed).

PSA centering limits (front / back), from PSA's published grading standards:
  10: 55/45 / 75/25   9: 60/40 / 90/10   8: 65/35 / 90/10   7: 70/30 / 90/10
   6: 80/20 / 90/10   5: 85/15 / 90/10   4: 85/15 / 90/10   3: 90/10 / 90/10
TAG score bands (taggrading.com/pages/scale): 990-1000 Pristine 10, 950-989 Gem Mint 10, 900-949 9,
then 50-point bands per half grade down to 100-149 = 1. TAG front centering: Pristine ~51/49,
Gem Mint ~55/45, 9 ~60/40, 8.5 ~62.5/37.5, 8 ~65/35, then +2.5 per half grade. How TAG turns its
8 subgrades into a score isn't published, so the TAG number here is an estimate.
"""
from __future__ import annotations

import math
import re

PSA_CENTER = [(10, 55, 75), (9, 60, 90), (8, 65, 90), (7, 70, 90), (6, 80, 90), (5, 85, 90), (4, 85, 90), (3, 90, 90), (2, 90, 90), (1, 100, 100)]
PSA_LABELS = {10: "GEM MT", 9: "MINT", 8: "NM-MT", 7: "NM", 6: "EX-MT", 5: "EX", 4: "VG-EX", 3: "VG", 2: "GOOD", 1.5: "FAIR", 1: "POOR"}

# Checklist answers -> subgrade (1-10)
CONDITION_OPTIONS = {
    "Flawless": 10.0,
    "One tiny flaw": 9.0,
    "Light wear": 8.0,
    "Noticeable wear": 6.5,
    "Heavy wear": 4.0,
    "Crease / damage": 2.0,
}
CONDITION_HELP = {
    "corners": "Look for white specks or rounding on all four corners, front and back.",
    "edges": "Look for white chipping along the edges, especially on the back.",
    "surface": "Tilt under a light: scratches, print lines, dents, stains, holo scuffs.",
}

TAG_BANDS = [(990, "10", "Pristine"), (950, "10", "Gem Mint"), (900, "9", "Mint"), (850, "8.5", "NM-MT+"),
             (800, "8", "NM-MT"), (750, "7.5", "NM+"), (700, "7", "NM"), (650, "6.5", "EX-MT+"), (600, "6", "EX-MT"),
             (550, "5.5", "EX+"), (500, "5", "EX"), (450, "4.5", "VG-EX+"), (400, "4", "VG-EX"), (350, "3.5", "VG+"),
             (300, "3", "VG"), (250, "2.5", "Good+"), (200, "2", "Good"), (150, "1.5", "Fair"), (0, "1", "Poor")]
# TAG front centering limit (larger side %) per grade
TAG_CENTER = [(10.5, 51), (10, 55), (9, 60), (8.5, 62.5), (8, 65), (7.5, 67.5), (7, 70), (6.5, 72.5), (6, 75),
              (5.5, 77.5), (5, 80), (4.5, 82.5), (4, 85), (3.5, 87.5), (3, 90), (2, 95), (1.5, 98.33)]


# Centering limits per grading company: (grade label, front max %, back max %). Larger side of the split,
# so 55 means 55/45. Sources: PSA grading standards; CGC cgccards.com/card-grading/grading-scale; TAG
# taggrading.com/pages/rubric (separate TCG / sports back limits); BGS Pristine from beckett.com/grading-standards
# (50/50 front, 55/45 back), the other BGS rows and SGC from published secondary guides. None = the company publishes no back figure for that grade.
GRADERS: dict[str, list[tuple[str, float, float | None]]] = {
    "PSA": [("10", 55, 75), ("9", 60, 90), ("8", 65, 90), ("7", 70, 90), ("6", 80, 90), ("5", 85, 90), ("4", 85, 90), ("3", 90, 90), ("2", 90, 90)],
    "BGS": [("10 Pristine", 50, 55), ("9.5", 55, 60), ("9", 55, 70), ("8", 60, 80), ("7", 65, 90), ("6", 70, 95)],
    "SGC": [("10 Pristine", 50, None), ("10", 55, None), ("9", 60, None), ("8", 65, None), ("7", 70, None), ("6", 75, None)],
    "CGC": [("10 Pristine", 50, None), ("10", 55, 75), ("9", 60, 90), ("8", 65, None), ("7.5", 65, None), ("7", 70, None), ("6", 75, None), ("4.5", 85, None), ("3.5", 90, None)],
    "TAG": [("10 Pristine", 51, None), ("10", 55, None), ("9", 60, None), ("8.5", 62.5, None), ("8", 65, None), ("7", 70, None), ("6", 75, None), ("5", 80, None)],
}
TAG_BACK = {"tcg": {"10 Pristine": 52, "10": 65, "9": 75, "8.5": 85, "8": 95}, "sports": {"10 Pristine": 54.5, "10": 70, "9": 90, "8.5": 95}}

# Card styles: how centering / corners are judged. No grader publishes a die-cut or full-art centering rule;
# the approach below is the common practice (measure to the printed frame; don't penalise the cut shape).
CARD_STYLES = {
    "Standard (bordered)": "Centering = the printed border on each side, card edge to the inner frame.",
    "Full art / borderless": "No border to measure: centering is judged by the design (text box, frame lines) or not at all. Graders are more forgiving here since there is no border contrast to show a shift.",
    "Die-cut": "The outline is cut to a shape, so centering is measured from the printed design to the cut edge where the design has a frame; the shaped edges and points are held to the same corner/edge standard (a die-cut has received BGS Pristine 10). No grader publishes a separate die-cut rule.",
    "Vintage / square corners": "Some vintage and tobacco cards are cut square or to a different size: square corners are not a flaw on those sets.",
    "Slabbed (graded)": "Already graded: the label grade is read; the card is measured through the case.",
}


def grader_caps(front_worst: float | None, back_worst: float | None, tcg: bool = True) -> dict[str, str]:
    """Best grade each company allows for this centering alone (larger-side % front / back)."""
    out = {}
    for comp, rows in GRADERS.items():
        best = "below scale"
        for label, f, b in rows:
            if comp == "TAG":
                b = TAG_BACK["tcg" if tcg else "sports"].get(label, 100)
            if (front_worst is None or front_worst <= f) and (back_worst is None or b is None or back_worst <= b):
                best = label
                break
        out[comp] = best
    return out


def psa_centering_cap(front_worst: int | None, back_worst: int | None) -> int:
    if front_worst is None:
        return 10
    back_worst = back_worst or 50
    for grade, f, b in PSA_CENTER:
        if front_worst <= f and back_worst <= b:
            return grade
    return 1


def centering_subgrade(front_worst: int | None, back_worst: int | None) -> float:
    """TAG-style centering subgrade from the front split (10.5 stands for Pristine)."""
    if front_worst is None:
        return 9.0
    for g, lim in TAG_CENTER:
        if front_worst <= lim:
            return min(g, 10.0) if g <= 10 else 10.0
    return 1.0


def tag_from_subs(subs: dict[str, float]) -> tuple[int, str, str]:
    # TAG's score follows the weakest area closely: on 60 TAG-graded cards the best fit was 70% weakest area,
    # 30% weighted average (surface and corners count most in the average).
    w = {"centering": 0.2, "corners": 0.3, "edges": 0.2, "surface": 0.3}
    avg = sum(subs[k] * w[k] for k in w)
    low = min(subs.values())
    score = int(round((0.3 * avg + 0.7 * low) * 100))
    score = max(100, min(1000, score))
    for floor, grade, label in TAG_BANDS:
        if score >= floor:
            return score, grade, label
    return score, "1", "Poor"


HALF_LABELS = {
    "BGS": {10: "Pristine", 9.5: "Gem Mint", 9: "Mint", 8.5: "NM-MT+", 8: "NM-MT", 7.5: "NM+", 7: "NM", 6.5: "EX-MT+", 6: "EX-MT",
            5.5: "EX+", 5: "EX", 4.5: "VG-EX+", 4: "VG-EX", 3.5: "VG+", 3: "VG", 2.5: "G+", 2: "Good", 1.5: "Fair", 1: "Poor"},
    "CGC": {10: "Gem Mint", 9.5: "Mint+", 9: "Mint", 8.5: "NM/Mint+", 8: "NM/Mint", 7.5: "Near Mint+", 7: "Near Mint", 6.5: "Ex/NM+",
            6: "Ex/NM", 5.5: "Excellent+", 5: "Excellent", 4.5: "VG/Ex+", 4: "VG/Ex", 3.5: "Very Good+", 3: "Very Good",
            2.5: "Good+", 2: "Good", 1.5: "Fair", 1: "Poor"},
    "SGC": {10: "Gem Mint", 9.5: "Mint+", 9: "Mint", 8.5: "NM-MT+", 8: "NM-MT", 7.5: "NM+", 7: "NM", 6.5: "EX-NM+", 6: "EX-NM",
            5.5: "EX+", 5: "EX", 4.5: "VG-EX+", 4: "VG-EX", 3.5: "VG+", 3: "VG", 2.5: "G+", 2: "Good", 1.5: "Fair", 1: "Poor"},
}


def _half(x: float) -> float:
    return max(1.0, min(10.0, round(x * 2) / 2))


def _centering_cap(company: str, front_worst, back_worst, tcg: bool = True) -> float:
    """Best numeric grade the centering allows at this company (10.5 = Pristine / Black Label possible)."""
    if front_worst is None:
        return 10.0
    for label, f, b in GRADERS[company]:
        if company == "TAG":
            b = TAG_BACK["tcg" if tcg else "sports"].get(label, 100)
        if front_worst <= f and (back_worst is None or b is None or back_worst <= b):
            return 10.5 if "Pristine" in label else float(label.split()[0])
    return 4.0


def _bgs_centering_sub(front_worst, back_worst) -> float:
    """BGS centering subgrade: 10 = 50/50 front + 55/45 back ... (Beckett's published centering table)."""
    rows = [(10, 50, 55), (9.5, 55, 60), (9, 55, 70), (8.5, 60, 80), (8, 60, 80), (7, 65, 90), (6, 70, 95), (5, 75, 95), (4, 80, 100)]
    if front_worst is None:
        return 9.5
    for g, f, b in rows:
        if front_worst <= f and (back_worst is None or back_worst <= b):
            return float(g)
    return 3.0


def bgs_overall(subs: dict[str, float]) -> tuple[float, str]:
    """Beckett's overall from 4 subgrades: not an average. Black Label = four 10s; Pristine 10 = all 9.5+ with three
    10s; Gem Mint 9.5 = all 9+ with three 9.5+; otherwise the lowest subgrade sets the floor and the second-lowest
    caps it (at most half a grade above the lowest)."""
    v = sorted(subs.values())
    if all(x >= 10 for x in v):
        return 10.0, "Pristine (Black Label)"
    if v[0] >= 9.5 and sum(x >= 10 for x in v) >= 3:
        return 10.0, "Pristine"
    if v[0] >= 9 and sum(x >= 9.5 for x in v) >= 3:
        return 9.5, "Gem Mint"
    # the lowest subgrade anchors the grade; strong other subgrades lift it, at most a full grade (Beckett's own
    # examples: 9.5/9.5/9/8 -> 8.5, 9.5/9.5/8.5/9 -> 9, 10/6/10/10 -> 7), never above the second-lowest
    lift = min(1.0, max(0.0, (sum(v[1:]) / 3 - v[0]) * 0.65))
    g = min(v[1], v[0] + math.floor(lift * 2) / 2)
    g = _half(g)
    return g, HALF_LABELS["BGS"].get(g, "")


ACE_LABELS = {10: "GEM MINT", 9: "MINT", 8: "NM-MT", 7: "NM", 6: "EX-MT", 5: "EX", 4: "VG-EX", 3: "VG", 2: "GOOD", 1: "POOR"}


def ace_overall(subs: dict[str, float]) -> int:
    """ACE (UK): whole-number subgrades; the overall is their average rounded (a .5 rounds down), never more than one
    above the lowest. Matches every published ACE cert checked (e.g. 10/10/10/9 -> 10, 10/10/9/9 -> 9, 9/10/8/7 -> 8,
    7/10/10/9 -> 8)."""
    v = [int(round(x)) for x in subs.values()]
    avg = sum(v) / len(v)
    return int(max(1, min(min(v) + 1, math.ceil(avg - 0.5))))


def all_graders(subs: dict[str, float], front_worst, back_worst, tcg: bool = True) -> dict[str, dict]:
    """Estimated grade at each company from the same measurements (centering split + corners / edges / surface).
    Each company's own centering table caps its grade; condition follows its scale (PSA whole grades, the others
    half grades). Estimates from photos, not what a grader under magnification will give."""
    cond = {k: float(subs[k]) for k in ("corners", "edges", "surface")}
    worst = min(cond.values())
    blended = _half(0.75 * worst + 0.25 * (sum(cond.values()) / 3))  # weakest area decides, the rest nudge it
    out: dict[str, dict] = {}
    # PSA: whole grades, weakest attribute, PSA centering table
    cap = psa_centering_cap(front_worst, back_worst)
    psa = min(cap, 10 if worst >= 10 else int(max(1, worst)))
    out["PSA"] = {"grade": f"{psa}", "label": PSA_LABELS.get(psa, ""), "note": f"centering allows up to {cap}"}
    # BGS: four subgrades, overall by Beckett's rule
    bsub = {"centering": _bgs_centering_sub(front_worst, back_worst), **{k: _half(v) for k, v in cond.items()}}
    g, lab = bgs_overall(bsub)
    out["BGS"] = {"grade": f"{g:g}", "label": lab, "sub": bsub}
    # CGC and SGC: half grades; Pristine needs a flawless card and near-perfect (50/50 / 51/49) centering
    for comp in ("CGC", "SGC"):
        c = _centering_cap(comp, front_worst, back_worst)
        g = min(blended, min(c, 10.0))
        if g >= 10 and c >= 10.5 and worst >= 10:
            out[comp] = {"grade": "10", "label": "Pristine", "note": ""}
        else:
            out[comp] = {"grade": f"{g:g}", "label": HALF_LABELS[comp].get(g, ""), "note": f"centering allows up to {'10' if c >= 10 else f'{c:g}'}"}
    asub = {"centering": float(psa_centering_cap(front_worst, back_worst)), **{k: float(math.floor(v)) for k, v in cond.items()}}
    ag = ace_overall(asub)
    out["ACE"] = {"grade": f"{ag}", "label": ACE_LABELS.get(ag, ""), "sub": asub}
    score, tg, tl = tag_from_subs({"centering": centering_subgrade(front_worst, back_worst), **cond})
    out["TAG"] = {"grade": tg, "label": tl, "note": f"score {score} / 1000"}
    return out


def estimate(front_worst: int | None, back_worst: int | None, corners, edges, surface, tcg: bool = True) -> dict:
    """corners / edges / surface: a checklist answer ("Light wear") or a measured subgrade (8.0)."""
    val = lambda v: float(v) if isinstance(v, (int, float)) else CONDITION_OPTIONS.get(v, 9.0)
    subs = {
        "centering": centering_subgrade(front_worst, back_worst),
        "corners": val(corners),
        "edges": val(edges),
        "surface": val(surface),
    }
    cond = min(subs["corners"], subs["edges"], subs["surface"])
    cap = psa_centering_cap(front_worst, back_worst)
    # PSA: a card is graded by its weakest attribute; allow one tiny flaw at 9.
    psa = min(cap, 10 if cond >= 10 else int(max(1, cond)))
    low = max(1, psa - 1)
    high = min(10, psa + (1 if cond >= 9 and cap > psa else 0))
    score, tag_grade, tag_label = tag_from_subs(subs)
    return {
        "method": "checklist",
        "sub": subs,
        "psa": psa,
        "psa_label": PSA_LABELS.get(psa, ""),
        "psa_range": f"{low}-{high}" if low != high else str(psa),
        "tag_score": score,
        "tag_grade": tag_grade,
        "tag_label": tag_label,
        "centering_cap": cap,
        "graders": all_graders(subs, front_worst, back_worst, tcg),
    }


GUIDE = """
**How the graders judge a card**

- **Centering**: the border on opposite sides is compared, e.g. 55/45 means one side is 55% of the pair. Front and
  back have separate limits (the back is judged much more loosely). The best grade each company allows:

| Grade | PSA front / back | BGS | SGC | CGC | TAG front |
|---|---|---|---|---|---|
| 10 (Pristine) | — | 50/50 · back 55 | 50 | 50 | 51 |
| 10 Gem Mint | 55/45 · 75/25 | 9.5: 55 · back 60 | 55 | 55 · back 75 | 55 |
| 9 | 60/40 · 90/10 | 55 · back 70 | 60 | 60 · back 90 | 60 |
| 8 | 65/35 · 90/10 | 60 · back 80 | 65 | 65 | 65 |
| 7 | 70/30 · 90/10 | 65 · back 90 | 70 | 70 | 70 |

  TAG judges the back differently for TCG and sports cards (TCG 10: 65, sports 10: 70).
- **Corners**: PSA 10 = four perfectly sharp corners; 9 = one very minor flaw; 8 = slightest fraying at one or
  two corners; 7 = slight fraying on some; 5 = minor rounding.
- **Edges / surface**: 10 = no chipping, full original gloss, no staining; 9 allows one minor print imperfection
  or a very slight wax stain on the back.
- **Overall**: the weakest area decides (BGS: the overall tracks the lowest subgrade, a half grade above at most).
- **Full art / borderless**: graded like any card, but centering is judged on the thin frame / design, and
  graders are more forgiving because a shift is hard to see.
- **Die-cut**: no grader publishes a special rule; the shaped edges and points are held to the normal corner /
  edge standard, centering is judged on the printed design.
- **Vintage**: many old cards are cut square or to other sizes; that is not a flaw.
- **Autographs**: an authenticator (PSA/DNA, JSA, Beckett) compares the signature with known examples, checks
  the ink and flow. PSA auto grade 10 = bold, no skips; 9 = a very light skip; 8 = more noticeable skip or slight
  fading. Maker-certified autos (on-card or sticker) are guaranteed by the maker.

Sources: psacard.com grading standards · cgccards.com grading scale · taggrading.com rubric · Beckett / SGC
published scales (via collector guides) · psacard.com autograph grading standards.
"""


# ---------------- measured damage -> subgrade ----------------
# Thresholds set so the graded reference cards (data/tests/graded) land on their real grades; they follow the
# published wording: 10 = no visible flaw, 9 = one minor flaw, 8 = slight wear on one or two corners / a minor
# flaw, 6-7 = visible wear, 5 = minor rounding / chipping / several scratches, 4 and below = rounding, scuffing,
# creases, heavy scratching.

def surface_from_reference(sev: float) -> float:
    """Surface subgrade from the comparison with a clean picture of the same card (core/refdiff.py)."""
    for lim, g in ((0.15, 10.0), (0.25, 9.5), (0.4, 9.0), (0.55, 8.0), (0.7, 6.0), (0.85, 4.0)):
        if sev <= lim:
            return g
    return 2.5


def corners_from_wear(frac: float) -> float:
    """Corner subgrade from the share of the worst corner that lost the border colour (above the set's own)."""
    for lim, g in ((0.04, 10.0), (0.08, 9.0), (0.13, 8.0), (0.2, 7.0), (0.3, 6.0), (0.45, 5.0)):
        if frac <= lim:
            return g
    return 4.0


def edges_from_wear(frac: float) -> float:
    """Edge subgrade from the share of the worst edge's outer millimetre that lost the border colour."""
    for lim, g in ((0.03, 10.0), (0.06, 9.0), (0.1, 8.0), (0.15, 7.0), (0.22, 6.0), (0.3, 5.0)):
        if frac <= lim:
            return g
    return 4.0


# ---------------------------------------------------------------------------------------------------------------
# Defect rulebook: the highest grade a card can get with each defect, from the companies' published standards
# (TAG's per-grade rubric for corners / edges / surface, PSA's grade definitions and deduction guides, Beckett's
# subgrade descriptions). Whole numbers follow PSA; the halves are TAG / BGS / CGC / SGC steps. Back defects are
# held to a slightly looser standard by TAG (and in practice by the others), so `back` caps are half a grade higher
# where the rubric says so.
DEFECTS: dict[str, dict] = {
    # corners
    "corner_touch":      {"what": "light touch / fray on a corner (magnification)", "front": [(1, 10), (2, 9), (4, 8.5)], "back": [(2, 10), (4, 9)]},
    "corner_whitening":  {"what": "whitening on a corner", "levels": {"under 1 mm": 8.5, "over 1 mm": 7, "several corners, visible": 6}},
    "corner_soft":       {"what": "corner losing its point (soft / slightly rounded)", "levels": {"one corner": 6, "two corners": 5, "all four": 3.5}},
    "corner_rounded":    {"what": "clearly rounded corner", "levels": {"one corner": 4.5, "two or three": 4, "all four": 3.5, "extreme": 2.5}},
    "corner_ding":       {"what": "bent / dinged corner", "levels": {"slight": 6, "several": 4.5}},
    "corner_lifted":     {"what": "lifted / layered corner (surface separating from the core)", "levels": {"slight": 6, "clear": 5}},
    "corner_missing":    {"what": "missing stock at a corner", "levels": {"small, back": 8.5, "small, front": 7, "large": 4}},
    # edges
    "edge_wear":         {"what": "edge wear / whitening along an edge", "levels": {"one or two edges, minor": 9, "multiple edges, light": 8.5, "all four": 8}},
    "edge_chipping":     {"what": "chipping along an edge", "levels": {"under 1 mm": 8.5, "1-2 mm": 7, "over 2 mm or many": 5.5}},
    "edge_lifting":      {"what": "lifted / peeling edge (layer separating)", "levels": {"minor, one edge": 7.5, "all four": 7, "significant": 6}},
    "edge_notch":        {"what": "notch in an edge", "levels": {"minor, one": 7, "two edges": 6.5, "three or more / severe": 6, "severe on two": 5.5}},
    "edge_tear":         {"what": "tear in an edge", "levels": {"minor": 2, "larger / several": 1.5}},
    # surface
    "print_spot":        {"what": "print spot / speck / dot", "levels": {"one, under magnification": 10, "a few": 9, "several": 8, "many / obvious": 7}},
    "print_line":        {"what": "print / refractor line", "levels": {"one": 9, "several": 8.5, "roller line": 8}},
    "scratch":           {"what": "scratch", "levels": {"light, not through gloss": 10, "longer, not through gloss": 9, "through the gloss": 8.5, "several deep": 7}},
    "scuff":             {"what": "scuffing / loss of gloss", "levels": {"minor": 8.5, "significant in one area": 6, "multiple / gloss gone": 5}},
    "dent":              {"what": "dent / indentation (dimple)", "levels": {"very minor, front": 7.5, "minor": 7, "larger or several": 6}},
    "wrinkle":           {"what": "wrinkle (soft crease that hasn't broken the stock)", "levels": {"very short, back": 6.5, "longer, back": 6, "small, front": 5.5, "several": 5, "across half the card": 4, "3/4 across": 3.5}},
    "crease":            {"what": "crease (breaks the stock)", "levels": {"minor": 4.5, "on both sides": 4, "several": 3.5, "heavy": 3, "full length": 2.5, "multiple full length": 2}},
    "stain":             {"what": "stain / discoloration", "levels": {"light, back": 6, "light, front": 5.5, "larger": 5, "large area": 4, "tape / glue residue": 1.5}},
    "water_damage":      {"what": "water damage", "levels": {"small, back": 6.5, "small, front": 5.5, "larger area": 4}},
    "hole":              {"what": "pinhole / staple hole", "levels": {"pinhole": 2, "staple holes": 1.5}},
    "writing":           {"what": "writing / ink / pencil marks", "levels": {"any": 1}, "note": "PSA adds the MK qualifier; the others usually return it ungraded / Authentic"},
    "focus":             {"what": "out of focus / out of register print", "levels": {"subtle": 8.5, "noticeable": 6}},
    "foil_clouding":     {"what": "hazy / clouded foil (reverse holos, Enchanted, old foils)", "levels": {"slight": 9, "noticeable": 8, "widespread": 7}},
    "foil_peeling":      {"what": "foil / refractor lifting or peeling (chrome, Prizm, foil edges)", "levels": {"micro, at an edge": 8, "visible lifting / bubbling": 6}},
    "holo_bleed":        {"what": "holo bleed / foil misregistration (factory)", "levels": {"slight": 9, "obvious": 8}},
    "wax_stain":         {"what": "wax stain (pack wax, 1970s-early 1990s)", "levels": {"very slight, back": 9, "slight": 8, "heavy": 6, "into the stock": 5}},
    "pitting":           {"what": "surface pitting (coating breaking down)", "levels": {"light, small area": 8.5, "widespread": 7}},
    "fingerprint":       {"what": "fingerprint / oil residue (glossy chrome / Prizm)", "levels": {"light": 9.5, "heavy / etched": 8}},
    "yellowing":         {"what": "yellowed / faded borders or colour", "levels": {"slight": 8, "noticeable": 7, "severe": 5}},
    "curl":              {"what": "curled / warped card (humidity, foils)", "levels": {"slight": 9, "noticeable": 7, "warped": 5}},
}


def defect_cap(kind: str, level: str, side: str = "front") -> float:
    """Highest grade possible with this defect at this severity (10 = no limit)."""
    d = DEFECTS.get(kind) or {}
    cap = float((d.get("levels") or {}).get(level, 10))
    if side == "back" and kind not in ("crease", "hole", "writing", "edge_tear"):
        cap = min(10.0, cap + 0.5)  # TAG's rubric gives back corners / edges / surface more tolerance
    return cap


def apply_defect_caps(grade: float, defects: list[tuple[str, str, str]], whole: bool = False) -> tuple[float, list[str]]:
    """Lower a grade to the worst defect's limit. defects = [(kind, level, side)]. Returns (grade, reasons)."""
    reasons, out = [], grade
    for kind, level, side in defects:
        c = defect_cap(kind, level, side)
        if c < out:
            out = c
        if c < 10:
            reasons.append(f"{DEFECTS[kind]['what']} ({level}, {side}) limits the grade to {c:g}")
    if whole:
        out = float(math.floor(out))
    return out, reasons


# How each kind of card in the app is graded differently: what shows up most, what graders forgive, and what the
# inspection has to watch for. The per-set baselines (border colour / width, corner shape, normal wear on clean
# copies) come from set learning (core/learn.py); this is the game-level layer above them.
GAME_PROFILES: dict[str, dict] = {
    "pokemon_vintage": {"match": "Pokémon, 1999-2003 (WOTC)", "watch": ["back (blue) edge and corner whitening", "holo scratches", "yellow border wear", "print spots on thin stock", "wax / pack marks"],
                        "forgiven": ["Shadowless / 1st Edition print quality is often off-centre: graders hold the same standard but many copies only reach 7-8"],
                        "extra": ["holo_bleed", "wax_stain", "foil_clouding"], "back_whitening_visible": True},
    "pokemon_modern":  {"match": "Pokémon, 2003 on", "watch": ["centering (the most common reason a modern card misses a 10)", "back edge whitening", "full art / textured surface wear", "reverse holo clouding"],
                        "forgiven": ["intended texture on full arts / illustration rares is not damage"], "extra": ["foil_clouding", "holo_bleed"],
                        "note": "Japanese prints usually have tighter centering and better print quality than English"},
    "yugioh":          {"match": "Yu-Gi-Oh!", "watch": ["silver border / dark back edge whitening", "holo, secret and ultimate rare scratches", "foil chipping where the foil reaches the edge (Ultimate / Ghost rares)", "corner fuzzing from loose sleeves"],
                        "extra": ["foil_peeling", "foil_clouding"], "back_whitening_visible": True, "note": "OCG (Japanese) and TCG stock and foils differ: compare with the same print"},
    "mtg":             {"match": "Magic: The Gathering", "watch": ["black border corner / edge whitening (shows very easily)", "foil curl and clouding", "narrow borders make centering errors obvious", "edge wear on 1993-94 thin stock"],
                        "forgiven": ["Alpha corners are rounder by design", "some edge wear expected on 1993 stock (back judged a little more leniently)"],
                        "extra": ["curl", "foil_clouding"], "back_whitening_visible": True},
    "lorcana":         {"match": "Disney Lorcana", "watch": ["Enchanted foil micro-scratches and clouding", "narrow borders: centering", "thick stock shows corner dings / edge chips", "foil curl"],
                        "forgiven": ["full-bleed Enchanted art: centering judged by art alignment"], "extra": ["foil_clouding", "curl"]},
    "onepiece":        {"match": "One Piece Card Game", "watch": ["print lines (factory, still cap at 9)", "Manga / Alt Art foil scratches", "corner whitening / chipping", "edge nicks from sleeving"],
                        "extra": ["foil_clouding"]},
    "sports_chrome":   {"match": "Sports, chrome / refractor / Prizm / Select", "watch": ["surface scratches and fingerprints on gloss", "print and roller lines", "refractor / foil peeling at edges", "corner and edge chipping on dark parallels"],
                        "extra": ["foil_peeling", "fingerprint", "pitting"], "note": "TAG holds sports backs to a looser centering limit than TCG backs"},
    "sports_paper":    {"match": "Sports, paper stock (modern base, 1980s-90s)", "watch": ["corner wear / fuzzing", "wax stains (junk wax era)", "print spots and focus", "border yellowing"],
                        "extra": ["wax_stain", "yellowing", "focus"]},
    "sports_vintage":  {"match": "Sports, pre-1980 and tobacco", "watch": ["centering (often poor from the factory)", "rounded corners", "creases", "staining and yellowing", "writing on the back"],
                        "forgiven": ["some sets were cut square or to odd sizes: square corners are not a flaw there", "some age toning is tolerated"],
                        "extra": ["yellowing", "wax_stain", "writing"]},
    "nonsport":        {"match": "Non-sport and other trading cards", "watch": ["corner wear", "surface scratches", "print defects", "centering"], "extra": ["yellowing", "wax_stain"]},
}


def game_profile(game: str, year: str | int | None = None, variant: str = "", style: str = "") -> str:
    """Which GAME_PROFILES entry a card falls under (game name as the app stores it)."""
    g = (game or "").lower()
    try:
        y = int(str(year)[:4]) if year else None
    except ValueError:
        y = None
    v = (variant or "").lower()
    if "pok" in g:
        return "pokemon_vintage" if y and y <= 2003 else "pokemon_modern"
    if "yu-gi" in g or "yugioh" in g:
        return "yugioh"
    if "magic" in g or g == "mtg":
        return "mtg"
    if "lorcana" in g:
        return "lorcana"
    if "one piece" in g:
        return "onepiece"
    if "non-sport" in g or "nonsport" in g or "non sport" in g:
        return "nonsport"
    if any(k in g for k in ("baseball", "basketball", "football", "soccer", "hockey", "sport")):
        if y and y < 1980:
            return "sports_vintage"
        if any(k in v for k in ("chrome", "refractor", "prizm", "select", "optic", "finest", "mosaic")):
            return "sports_chrome"
        return "sports_paper"
    return "nonsport"


# Card formats: what changes in grading for each, and which companies grade it at all.
CARD_FORMATS: dict[str, dict] = {
    "standard":    {"what": "standard card (2.5 x 3.5 in / 63 x 88 mm), rounded corners", "notes": []},
    "square":      {"what": "square-cut corners (many vintage and tobacco sets, some modern inserts)",
                    "notes": ["square corners are how the set was cut, not wear; corners are judged on sharpness and fraying only"]},
    "die_cut":     {"what": "die-cut (shaped outline)", "not_graded_by": ["TAG"],
                    "notes": ["the points of the shape are judged as corners and the cut sides as edges", "die-cut points chip easily; any missing tip is a corner defect"]},
    "mini":        {"what": "mini (e.g. Allen & Ginter / T206 size)",
                    "notes": ["same grading scale; borders are thinner so centering shifts show more", "measured relative to the card's own size"]},
    "relic":       {"what": "patch / jersey / relic / memorabilia card (thick stock with a window)", "not_graded_by": ["TAG"],
                    "notes": ["card stock graded as usual; thick edges show chipping and dings easily", "a cloudy or scratched window lowers the surface grade",
                              "frayed, loose or damaged swatch counts against the card", "a tampered / replaced patch is returned ungraded (altered)"]},
    "thick":       {"what": "thick card (over 35pt, not a relic)", "notes": ["TAG grades up to 50pt only", "edges get extra attention: thick stock chips"]},
    "autograph":   {"what": "autographed card",
                    "notes": ["the card gets its normal grade; the signature gets its own 1-10 grade (PSA/DNA, BGS auto subgrade, CGC)",
                              "Beckett's autograph grade does not change the card's overall grade",
                              "on-card autographs are judged on the signature itself; sticker autos also on how the sticker sits"]},
    "plate":       {"what": "printing plate (metal 1 of 1)",
                    "notes": ["usually authenticated and encapsulated rather than given a numeric card grade",
                              "scratches, dents and bent corners on the metal are what reduce value; the estimate here is condition only"]},
    "metal":       {"what": "metal / steel card",
                    "notes": ["eligibility and holders vary by company; surface scratches and dented corners are the main defects"]},
    "acetate":     {"what": "acetate / clear / lenticular card", "not_graded_by": ["TAG"],
                    "notes": ["clear plastic shows every scratch; scratches count as surface defects", "lenticular cards are judged on the lens surface"]},
    "rounded":     {"what": "fully rounded corners (e.g. some oddball or kids' sets)", "not_graded_by": ["TAG"], "notes": []},
    "oversized":   {"what": "oversized / jumbo card", "notes": ["same scale; needs a larger holder (extra fee at most companies)"]},
    "sticker":     {"what": "sticker / collectible card", "notes": ["same scale; peeled or lifted backing counts like a lifted edge"]},
}


def card_format(variant: str = "", name: str = "", style: str = "", corner_radius_px: int | None = None, aspect: float | None = None) -> str:
    """Best guess at the card's format from what the catalog says about it and what the photo shows."""
    t = f"{variant} {name}".lower()
    if style == "die_cut" or "die-cut" in t or "die cut" in t or "diecut" in t:
        return "die_cut"
    if "printing plate" in t or re.search(r"\bplate\b.*\b(cyan|magenta|yellow|black)\b", t):
        return "plate"
    if re.search(r"\b(patch|jersey|relic|memorabilia|swatch|bat knob|game[- ]used|game[- ]worn|nameplate|laundry tag)\b", t):
        return "relic"
    if re.search(r"\b(acetate|clear|lenticular)\b", t):
        return "acetate"
    if re.search(r"\b(steel|metal card|metal\b(?! universe))", t):
        return "metal"
    if re.search(r"\bmini\b", t) or (aspect is not None and aspect < 0.62):
        return "mini"
    if re.search(r"\b(jumbo|oversized|box topper|5x7)\b", t):
        return "oversized"
    if re.search(r"\bsticker\b", t):
        return "sticker"
    if corner_radius_px is not None and corner_radius_px <= 2:
        return "square"
    return "standard"


# PSA/DNA autograph grades (the scale BGS and CGC follow closely)
AUTO_GRADES = {
    10: "bold, clear, complete; no skips, fading or retracing; ideal placement",
    9: "very bold; at most one minor flaw such as a very light skip",
    8: "slightly less bold; fully legible; very slight fading; a light skip, bleed or retrace",
    7: "fully visible; minor even fading; more skipping or bleeding that doesn't hurt the look",
    6: "fully legible; more fading; more skipping or bleeding",
    5: "has lost its boldness; advanced fading; small smudged area; up to ~25% retraced",
    4: "about 75% visible; noticeable fading in areas",
    3: "about 50% visible; faded throughout",
    2: "much of it lost; still identifiable",
    1: "barely readable",
}


def findings_to_defects(findings, side: str = "front") -> list[dict]:
    """Name what the inspection found in the graders' own terms (DEFECTS) with the level it reaches, so the grade
    can be capped the way the companies' rubrics cap it and the person sees why. Only 'likely' findings cap a
    subgrade; 'possible' ones are listed but don't lower the grade (the detectors over-call them on photos)."""
    out: list[dict] = []
    corners_white, edges = [], set()
    for f in findings or []:
        what = f.what.lower()
        if f.area == "corners" and "whitening" in what:
            m = re.search(r"([\d.]+)% of the corner", what)
            corners_white.append(float(m.group(1)) if m else 0.0)
        elif f.area == "corners" and ("rounded" in what or "dinged" in what):
            out.append({"kind": "corner_ding", "level": "slight", "side": side, "sure": f.sure, "area": "corners"})
        elif f.area == "edges" and ("chip" in what or "white spot" in what or "whitening" in what):
            edges.add(f.where)
        elif f.area == "surface" and "scratch" in what:
            n = int((re.match(r"(\d+)", what) or [0, "1"])[1])
            out.append({"kind": "scratch", "level": "several deep" if n >= 6 else "longer, not through gloss", "side": side, "sure": f.sure, "area": "surface"})
        elif f.area == "surface" and "crease" in what:
            out.append({"kind": "crease", "level": "minor", "side": side, "sure": f.sure, "area": "surface"})
        elif f.area == "surface" and ("stain" in what or "discoloured" in what):
            out.append({"kind": "stain", "level": f"light, {side}", "side": side, "sure": f.sure, "area": "surface"})
        elif f.area == "surface" and "speck" in what:
            n = int((re.match(r"(\d+)", what) or [0, "1"])[1])
            out.append({"kind": "print_spot", "level": "many / obvious" if n > 12 else "several" if n > 5 else "a few", "side": side, "sure": f.sure, "area": "surface"})
    if corners_white:
        lvl = "several corners, visible" if sum(w >= 5 for w in corners_white) >= 3 else "over 1 mm" if max(corners_white) >= 8 else "under 1 mm"
        out.append({"kind": "corner_whitening", "level": lvl, "side": side, "sure": "likely", "area": "corners"})
    if edges:
        lvl = "all four" if len(edges) >= 4 else "multiple edges, light" if len(edges) == 3 else "one or two edges, minor"
        out.append({"kind": "edge_wear", "level": lvl, "side": side, "sure": "likely", "area": "edges"})
    for d in out:
        d["cap"] = defect_cap(d["kind"], d["level"], side)
        d["what"] = DEFECTS[d["kind"]]["what"]
    return out
