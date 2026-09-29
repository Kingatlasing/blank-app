"""Grade estimates from measured centering + a condition checklist (no AI needed).

PSA centering limits (front / back), from PSA's published grading standards:
  10: 55/45 / 75/25   9: 60/40 / 90/10   8: 65/35 / 90/10   7: 70/30 / 90/10
   6: 80/20 / 90/10   5: 85/15 / 90/10   4: 85/15 / 90/10   3: 90/10 / 90/10
TAG publishes a 1000-point score; the bands below are an approximation used
for an estimate, not TAG's official conversion.
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
             (800, "8", "NM-MT"), (750, "7.5", "NM+"), (700, "7", "NM"), (600, "6", "EX-MT"),
             (500, "5", "EX"), (400, "4", "VG-EX"), (300, "3", "VG"), (200, "2", "Good"), (0, "1", "Poor")]


def psa_centering_cap(front_worst: int | None, back_worst: int | None) -> int:
    if front_worst is None:
        return 10
    back_worst = back_worst or 50
    for grade, f, b in PSA_CENTER:
        if front_worst <= f and back_worst <= b:
            return grade
    return 1


def centering_subgrade(front_worst: int | None, back_worst: int | None) -> float:
    if front_worst is None:
        return 9.0
    cap = psa_centering_cap(front_worst, back_worst)
    # Finer steps inside a band so 51/49 beats 55/45.
    if cap == 10:
        return 10.0 if front_worst <= 52 else 9.5
    return float(cap)


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


def estimate(front_worst: int | None, back_worst: int | None, corners: str, edges: str, surface: str) -> dict:
    subs = {
        "centering": centering_subgrade(front_worst, back_worst),
        "corners": CONDITION_OPTIONS.get(corners, 9.0),
        "edges": CONDITION_OPTIONS.get(edges, 9.0),
        "surface": CONDITION_OPTIONS.get(surface, 9.0),
    }
    cond = min(subs["corners"], subs["edges"], subs["surface"])
    cap = psa_centering_cap(front_worst, back_worst)
    # PSA: a card is graded by its weakest attribute; allow one tiny flaw at 9.
    psa = min(cap, 10 if cond >= 10 else 9 if cond >= 9 else 8 if cond >= 8 else 6 if cond >= 6.5 else 4 if cond >= 4 else 2)
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
