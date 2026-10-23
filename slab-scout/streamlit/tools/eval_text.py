"""How well the card text reader does on the real test photos (data/tests/real_scans): for every front photo with a
known name / number, read the card's text the way the scan server does (detect + crop the card, read every line,
switch to the Japanese / Korean reader when the card is in those languages) and report whether the name and the
number were read, plus what was read.

Run: python3 streamlit/tools/eval_text.py [--lines]
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from core import ocr, vision  # noqa: E402

TESTS = os.path.join(HERE, "..", "..", "data", "tests", "real_scans")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("é", "e"))


def read(img):
    card, found = vision.detect_and_crop(img)
    lines = ocr.read_card(card)
    if ocr.has_cjk(lines) or len(re.findall(r"[A-Za-z]{4,}", " ".join(t for t, *_ in lines))) < 5:
        jl = ocr.read_text_cjk(card)
        if any(re.search(r"[぀-ヿ一-鿿]", t) for t, *_ in jl):
            lines = jl
    return lines, found


def main():
    show = "--lines" in sys.argv
    labels = json.load(open(os.path.join(TESTS, "labels.json")))["scans"]
    rows, t0 = [], time.time()
    for s in labels:
        e = s["expect"]
        if e.get("kind") != "front":
            continue
        path = os.path.join(TESTS, "images", s["file"])
        if not os.path.exists(path):
            continue
        img = vision.load_image(open(path, "rb").read())
        lines, found = read(img)
        p = ocr.parse(lines, e.get("game", "Auto"))
        blob = norm(" ".join(t for t, *_ in lines))
        name_ok = bool(e.get("name")) and norm(e["name"]) in blob
        name_parsed = bool(e.get("name")) and norm(e["name"]) in norm(p.get("name", ""))
        num = e.get("number")
        num_ok = None if not num else (norm(num) in norm(p.get("number", "") + " " + p.get("set_code", "")) or bool(re.search(r"(?<![0-9a-z])" + re.escape(norm(num)) + r"(?![0-9])", " ".join(norm(t) for t, *_ in lines))))
        rows.append({"file": s["file"], "note": s.get("note", ""), "name_read": name_ok, "name_parsed": name_parsed,
                     "number_read": num_ok, "parsed": {k: p.get(k) for k in ("name", "number", "set_code", "year", "game")},
                     "lines": [t for t, *_ in lines], "found": found})
    n = len(rows)
    print(f"{n} front photos, {time.time() - t0:.0f}s")
    print(f"name somewhere in the text: {sum(r['name_read'] for r in rows)}/{n}")
    print(f"name picked as the card name: {sum(r['name_parsed'] for r in rows)}/{n}")
    nn = [r for r in rows if r["number_read"] is not None]
    print(f"number read: {sum(r['number_read'] for r in nn)}/{len(nn)}")
    for r in rows:
        flag = ("ok " if r["name_parsed"] else ("txt" if r["name_read"] else "MISS")) + (" #ok" if r["number_read"] else (" #-" if r["number_read"] is None else " #MISS"))
        print(f"  {flag:10s} {r['file'][:14]:14s} {r['note'][:34]:34s} -> {r['parsed']}")
        if show:
            print("      " + " | ".join(r["lines"])[:400])


if __name__ == "__main__":
    main()
