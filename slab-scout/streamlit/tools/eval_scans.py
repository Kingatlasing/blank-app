"""Measure how well scanning works on real photos with known answers.

    python streamlit/tools/eval_scans.py [labels.json] [--images DIR]

Runs the same identification as the Scan page on every photo in data/tests/real_scans (labels.json says what each
photo is) and reports: right card first, right card in the top 3, backs recognised as backs, custom / fan-made
cards NOT confidently matched, and the time per photo. Add your own photos + labels to grow the test set; run it
after every change to see whether scanning got better or worse.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

DEFAULT = os.path.join(HERE, "..", "..", "data", "tests", "real_scans", "labels.json")
CONFIDENT = 70  # a match scored this high is shown as the answer, not "not sure"


def _title(x: dict) -> tuple[str, str, str]:
    """(name, number, set + variant) of a candidate from the Scan page."""
    if x["kind"] == "catalog":
        from core import catalog
        c = x["card"]
        return c.name, c.number, f"{catalog.sets().get(c.set_id, {}).get('name', '')} {c.variant}"
    if x["kind"] == "community":
        r = x["row"]
        return r.get("name", ""), r.get("number", ""), f"{r.get('set_name', '')} {r.get('variant', '')}"
    c = x.get("c") or {}
    return c.get("name", ""), c.get("number", ""), f"{c.get('set', '')} {c.get('rarity', '')} {c.get('variant', '')}"


def _hit(x: dict, exp: dict) -> bool:
    name, number, setv = (s.lower() for s in _title(x))
    if exp.get("name") and exp["name"].lower() not in name and name not in exp["name"].lower():
        return False
    if exp.get("number"):
        want = exp["number"].lower().lstrip("#0")
        got = number.lower().lstrip("#0")
        if not (got == want or got.startswith(want + "/") or got.split("/")[0] == want or want in got):
            return False
    if exp.get("set") and exp["set"].lower() not in setv:
        return False
    if exp.get("variant") and exp["variant"].lower() not in setv:
        return False
    return True


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    labels_path = args[0] if args else DEFAULT
    img_dir = sys.argv[sys.argv.index("--images") + 1] if "--images" in sys.argv else os.path.join(os.path.dirname(labels_path), "images")
    labels = json.load(open(labels_path))["scans"]

    import ui.common as common
    from core import community
    tmp = tempfile.mkdtemp()
    store = community.Store(local_path=os.path.join(tmp, "eval.db"))  # empty: no help from earlier corrections
    common.get_store = lambda: store
    import ui.scan as scan
    scan.get_store = lambda: store

    rows, stats = [], {"front": [0, 0, 0], "back": [0, 0], "unknown": [0, 0]}
    times = []
    for item in labels:
        p = os.path.join(img_dir, item["file"])
        if not os.path.exists(p):
            rows.append((item["file"], "missing photo", ""))
            continue
        exp = item["expect"]
        t = time.time()
        try:
            res = scan._analyze(open(p, "rb").read(), None, exp.get("game") or "Auto")
        except Exception as e:  # a crash counts as a miss
            res = {"cands": [], "is_back": None, "err": str(e)}
        times.append(time.time() - t)
        cands = res.get("cands", [])
        top = cands[0] if cands else None
        got = " · ".join(x for x in _title(top) if x) if top else ("back of a card" if res.get("is_back") else "no match")
        if exp["kind"] == "back":
            ok = bool(res.get("is_back"))
            stats["back"][0] += 1
            stats["back"][1] += ok
            rows.append((item["file"], "✓ back" if ok else "✗ not seen as a back", got))
        elif exp["kind"] == "unknown":
            ok = not top or top["score"] < CONFIDENT
            stats["unknown"][0] += 1
            stats["unknown"][1] += ok
            rows.append((item["file"], "✓ not confidently matched" if ok else f"✗ confident wrong match ({top['score']})", got))
        else:
            first = bool(top) and _hit(top, exp)
            top3 = any(_hit(x, exp) for x in cands[:3])
            stats["front"][0] += 1
            stats["front"][1] += first
            stats["front"][2] += top3
            rows.append((item["file"], "✓ first" if first else "~ top 3" if top3 else "✗ missed", got + (f"  [{res['err']}]" if res.get("err") else "")))

    w = max(len(r[0]) for r in rows) if rows else 10
    for f, verdict, got in rows:
        print(f"{f:<{w}}  {verdict:<28}  {got}")
    n, a, b = stats["front"]
    print()
    if n:
        print(f"Card fronts: {a}/{n} right first ({100 * a / n:.0f}%), {b}/{n} in the top 3 ({100 * b / n:.0f}%)")
    if stats["back"][0]:
        print(f"Backs recognised: {stats['back'][1]}/{stats['back'][0]}")
    if stats["unknown"][0]:
        print(f"Custom / fan-made cards not confidently matched: {stats['unknown'][1]}/{stats['unknown'][0]}")
    if times:
        print(f"Time per photo: {sum(times) / len(times):.1f}s average, {max(times):.1f}s slowest")


if __name__ == "__main__":
    main()
