"""How close the grade estimate is to real grades: photos of graded cards (data/tests/graded, labels.json) are
scanned the normal way; the card inside the slab is graded as a raw card would be and compared with the grade
on the label (and BGS subgrades when the label shows them).

Run: python3 streamlit/tools/eval_grades.py [--local-ref name=photo ...]
  --local-ref: offline only, use a local clean photo as the card's clean picture (the server fetches the real one)
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
    from core import vision
    refs = {}
    for a in sys.argv[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            refs[k.lower()] = v
    if refs:
        real = scan._ref_image

        def local_ref(x):
            name = (x["card"].name if x and x.get("kind") == "catalog" else (x or {}).get("c", {}).get("name", "")).lower()
            for k, v in refs.items():
                if k in name:
                    return vision.detect_and_crop(vision.load_image(open(v, "rb").read()))[0]
            return real(x)
        scan._ref_image = local_ref
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
            guess = float(str(est.get("grade")).split()[0])
        except (TypeError, ValueError):
            guess = None
        subs = est.get("sub") or g.get("sub") or {}
        lab = (out.get("slab") or {}).get("grade_text", "")
        print(f"{s['file'][:30]:30s} real {comp} {s['grade']:<4} (label read: {lab or '-'})  estimate {guess}  "
              f"subs {({k: v for k, v in subs.items()})}  {g.get('error', '')}")
        if s.get("sub"):
            print(f"{'':30s} real subgrades {s['sub']}")
        if isinstance(guess, (int, float)):
            errs.append(abs(guess - float(s["grade"])))
    if errs:
        print(f"average miss: {sum(errs) / len(errs):.2f} grades, exact: {sum(e == 0 for e in errs)}/{len(errs)}, "
              f"within 1 grade: {sum(e <= 1 for e in errs)}/{len(errs)}")


if __name__ == "__main__":
    main()
