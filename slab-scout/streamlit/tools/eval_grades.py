"""How close the grade estimate is to real grades: photos of graded cards (data/tests/graded, labels.json) are
graded from the card itself, ignoring the slab label, and compared with the grade on the label.

Run: python3 streamlit/tools/eval_grades.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

TESTS = os.path.join(HERE, "..", "..", "data", "tests", "graded")


def main():
    import service
    from ui import scan
    scan._read_slab = lambda f, game: None  # grade the card, not the label
    labels = json.load(open(os.path.join(TESTS, "labels.json")))["scans"]
    errs = []
    for s in labels:
        p = os.path.join(TESTS, "images", s["file"])
        if not os.path.exists(p):
            continue
        out = service.do_scan(open(p, "rb").read(), None, "Auto", True)
        g = out.get("grade") or {}
        comp = s["company"]
        est = (g.get("graders") or {}).get(comp, {})
        try:
            guess = float(est.get("grade"))
        except (TypeError, ValueError):
            guess = None
        subs = est.get("sub") or g.get("sub") or {}
        print(f"{s['file'][:32]:32s} real {comp} {s['grade']:<4}  estimate {guess}  subs {subs}  top: "
              f"{(out.get('matches') or [{}])[0].get('name')}")
        if isinstance(guess, (int, float)):
            errs.append(abs(float(guess) - float(s["grade"])))
    if errs:
        print(f"average miss: {sum(errs) / len(errs):.2f} grades, within 1 grade: {sum(e <= 1 for e in errs)}/{len(errs)}")


if __name__ == "__main__":
    main()
