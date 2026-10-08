"""AGS 10 sold prices per card, from eBay sold listings collected in the browser (raw/slabscout-ags-sold-*.json.gz).

A sale counts toward a card only when its title has the card's number, every word of the card's name and at least
one distinctive word of the set name (and the right language for Japanese / Chinese sets). Sales that fit no card,
or fit more than one equally well, are left out. Nothing is estimated.

Output: catalog/remote/ags10.json.gz  {card path: {"v": median price, "sales": n, "last": "YYYY-MM-DD"}}
"""
import glob
import gzip
import json
import os
import re
import statistics
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
GENERIC = set("""pokemon pokémon card cards tcg the of and a to in checklist trading game japanese chinese korean english
set series edition holo foil rare promo base topps panini sports basketball baseball football soccer hockey""".split())


def words(s: str) -> set[str]:
    """Lower-case words, plurals folded ('refractors' -> 'refractor')."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
            for w in re.findall(r"[a-z0-9]+", s.lower().replace("é", "e"))}


def norm_num(n: str) -> str:
    n = (n or "").upper().split("/")[0].strip().lstrip("#")
    m = re.fullmatch(r"([A-Z]*)0*(\d+)([A-Z]*)", n)
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else n


def title_numbers(t: str) -> set[str]:
    out = set()
    for m in re.finditer(r"\b([A-Z]{0,4}\d{1,4}[A-Z]?)\s*/\s*[A-Z]{0,4}\d{1,4}\b", t, re.I):
        out.add(norm_num(m.group(1)))
    for m in re.finditer(r"#\s*([A-Z]{0,5}-?\d{1,4}[A-Z]?)\b", t, re.I):
        out.add(norm_num(m.group(1).replace("-", "")))
        out.add(norm_num(m.group(1)))
    for m in re.finditer(r"\b([A-Z]{1,5}\d{0,3}-[A-Z]{0,4}\d{0,3})\b", t):  # SD22-06, EVT1-SEC style codes
        out.add(m.group(1).upper())
    return {x for x in out if x}


def price(p: str) -> float | None:
    if " to " in p:
        return None
    m = re.search(r"\$([\d,]+\.?\d*)", p)
    return float(m.group(1).replace(",", "")) if m else None


def day(d: str) -> str:
    try:
        return datetime.strptime(d.strip(), "%b %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def main():
    sales = {}
    for f in sorted(glob.glob(os.path.join(HERE, "raw", "slabscout-ags-sold-*.json.gz"))):
        sales.update(json.load(gzip.open(f))["sales"])
    # AGS 10 only: drop titles that also name another grade or company slab
    keep = {}
    for k, v in sales.items():
        t = v["t"]
        if not re.search(r"\bAGS\b", t, re.I) or not re.search(r"\b10\b", t):
            continue
        if re.search(r"\b(PSA|BGS|CGC|SGC|TAG|Beckett)\b", t, re.I) and not re.search(r"\bAGS\s*(?:GEM|10)", t, re.I):
            continue
        if re.search(r"\blot\b|\bbundle\b|\bx\d+\b|\d+\s*cards?\b", t, re.I):
            continue
        keep[k] = v
    need = {n for v in keep.values() for n in title_numbers(v["t"])}
    sets = {s["id"]: s for s in json.load(open(os.path.join(HERE, "catalog", "sets.json")))}
    by_num: dict[str, list] = {}
    for f in glob.glob(os.path.join(HERE, "catalog", "remote", "sets", "*.json.gz")):
        for r in json.load(gzip.open(f)):
            set_id, name, number, variant, path = r[0], r[1], r[2] or "", r[3] or "", r[8] or ""
            if not path:
                continue
            for n in {norm_num(number), (number or "").upper()}:
                if n in need:
                    by_num.setdefault(n, []).append((set_id, name, variant, path))
    out: dict[str, list] = {}
    unmatched = ambiguous = 0
    for k, v in keep.items():
        t = v["t"]
        tw = words(t)
        jp = bool(re.search(r"japan|\bjp\b|\bjpn\b", t, re.I))
        cn = bool(re.search(r"chinese|\bcn\b|simplified", t, re.I))
        best, best_score, tie = None, -1, False
        for n in title_numbers(t):
            for set_id, name, variant, path in by_num.get(n, []):
                nw = {w for w in words(name) if len(w) > 1 or w.isdigit()}
                if not nw or not nw <= tw:
                    continue
                s = sets.get(set_id, {})
                sname = (s.get("name") or "").lower()
                if ("japanese" in sname) != jp or ("chinese" in sname) != cn:
                    continue
                sw = words(sname.split(" checklist")[0]) - GENERIC
                hit = len(sw & tw)
                if hit < 1:
                    continue
                vw = words(variant) - GENERIC
                if vw and not vw <= tw:
                    continue
                score = hit * 10 + len(vw) * 3 + (1 if not variant else 0) + (2 if s.get("year") and s["year"] in t else 0)
                if score > best_score:
                    best, best_score, tie = path, score, False
                elif score == best_score and path != best:
                    tie = True
        serial = bool(re.search(r"#?\s*/\s*\d{1,4}\b(?!\s*[A-Za-z]*\d)", t)) and not re.search(r"\b\d{1,4}\s*/\s*\d{1,4}\b", t)
        if best is not None and serial and best_score % 10 == 1:  # a numbered parallel ("#/199") but only the base card fit
            best = None
        if best is None:
            unmatched += 1
            continue
        if tie:
            ambiguous += 1
            continue
        p = price(v["p"])
        if p:
            out.setdefault(best, []).append((p, day(v["d"])))
    table = {}
    for path, xs in out.items():
        ps = [p for p, _ in xs]
        table[path] = {"v": round(statistics.median(ps), 2), "sales": len(ps), "last": max(d for _, d in xs)}
    dst = os.path.join(HERE, "catalog", "remote", "ags10.json.gz")
    with gzip.open(dst, "wt") as fh:
        json.dump(table, fh, separators=(",", ":"))
    print(f"AGS 10: {len(keep)} sales kept, {sum(len(x) for x in out.values())} matched to {len(table)} cards, "
          f"{unmatched} no card, {ambiguous} ambiguous")


if __name__ == "__main__":
    main()
