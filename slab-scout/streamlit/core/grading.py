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

PSA_CENTER = [(10, 55, 75), (9, 60, 90), (8, 65, 90), (7, 70, 90), (6, 80, 90), (5, 85, 90), (4, 85, 90), (3, 90, 90), (2, 95, 95), (1, 100, 100)]
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
    # Weighted: surface and corners matter most, the weakest area pulls the score down.
    w = {"centering": 0.2, "corners": 0.3, "edges": 0.2, "surface": 0.3}
    avg = sum(subs[k] * w[k] for k in w)
    low = min(subs.values())
    score = int(round((0.7 * avg + 0.3 * low) * 100))
    score = max(100, min(1000, score))
    for floor, grade, label in TAG_BANDS:
        if score >= floor:
            return score, grade, label
    return score, "1", "Poor"


def estimate(front_worst: int | None, back_worst: int | None, corners, edges, surface) -> dict:
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
    }
