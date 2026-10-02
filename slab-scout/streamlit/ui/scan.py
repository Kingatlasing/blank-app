"""Scan: snap -> instant match with price -> one-tap add. Bulk mode keeps the camera ready for the next card."""
from __future__ import annotations

import base64
import copy
import hashlib
import re
from datetime import datetime

import streamlit as st

from core import ai, autograph, catalog, colour, condition, databases, grading, identify, ocr, pipeline, slab, verify, vision
from ui import centering
from ui.common import (card_image, VERDICTS, add_to_collection, esc, get_store, grade_color, money, need_code, open_card, rarity_pill,
                       record_from_catalog)

GAMES = ["Auto", "Graded slab", "Pokémon", "Pokémon Japanese / Korean", "Yu-Gi-Oh!", "Magic: The Gathering", "Lorcana", "One Piece",
         "Dragon Ball", "Digimon", "Star Wars", "Marvel", "Gundam", "Riftbound", "Harry Potter", "Garbage Pail Kids", "Sports", "Kakawow / Disney / Marvel",
         "Non-sport (history, music…)", "Other"]


def _analyze(front: bytes, back: bytes | None, game: str) -> dict:
    f = pipeline.analyze_photo(front)
    b = pipeline.analyze_photo(back) if back else None
    sl = _read_slab(f, game)
    if sl:
        return _analyze_slab(front, f, b, sl, game)
    back_of = identify.card_back(f["lines"], f["card"], f.get("phash", ""))
    if back_of:
        return {"front": f, "back": b, "parsed": ocr.parse(f["lines"], "Auto"), "cands": [], "fakes": [], "is_back": back_of,
                "id": hashlib.sha1(front).hexdigest()[:12], "ai": None, "game": back_of}
    f["inspect"] = condition.inspect_card(vision.tight_card(f["card"], f["edges"]))
    if b:
        b["inspect"] = condition.inspect_card(vision.tight_card(b["card"], b["edges"]), is_back=True)
    parsed = ocr.parse(f["lines"], "" if game in ("Auto", "Sports", "Kakawow / Disney / Marvel", "Non-sport (history, music…)", "Other", "Pokémon Japanese / Korean") else game)
    if (parsed.get("game") or g0(game)) not in identify.TCG_GAMES:
        pn = _player_name(f["lines"])
        if pn and not all(w.lower() in (parsed.get("name") or "").lower() for w in pn.split()):
            parsed = {**parsed, "name": pn}
    store = get_store()
    comm = pipeline.community_matches(store, f["phash"])
    cands: list[dict] = []

    g = "" if game == "Auto" else game
    # Japanese / Korean cards: read the Asian text with the multilingual reader, map the Pokémon name to English
    if g in ("", "Pokémon", "Pokémon Japanese / Korean") and (g == "Pokémon Japanese / Korean" or ocr.has_cjk(f["lines"])
                                                           or len(re.findall(r"[A-Za-z]{4,}", parsed["raw_text"])) < 5):
        jl = ocr.read_text_cjk(f["card"])
        jp = identify.cjk_pokemon(jl)
        lang = "Japanese"
        if not jp or not any(re.search(r"[\u3040-\u30ff]", t) for t, *_ in jl):  # no kana: try the Korean reader
            kl = ocr.read_text_ko(f["card"])
            jk = identify.cjk_pokemon(kl)
            if jk and any(re.search(r"[\uac00-\ud7a3]", t) for t, *_ in kl):
                jp, jl, lang = jk, kl, "Korean"
        if jp:
            g = "Pokémon Japanese / Korean"
            parsed = {**parsed, "name": jp["name"], "number": jp["number"], "game": g,
                      "raw_text": parsed["raw_text"] + "\n" + "\n".join(t for t, *_ in jl)}
            for c in catalog.search(f"{jp['species']} {jp['number']}".strip(), limit=40) or catalog.search(jp["species"], limit=40):
                if catalog.sets().get(c.set_id, {}).get("category") != "Pokémon":
                    continue
                num_ok = jp["number"] and re.sub(r"^0+", "", c.number) == jp["number"]
                sc = 58 + (18 if num_ok else 0) + (8 if jp["name"].lower() == c.name.lower() else 0) + \
                    (6 if lang in catalog.sets().get(c.set_id, {}).get("name", "") else 0)
                cands.append({"kind": "catalog", "card": c, "score": sc,
                              "why": [f"reads {jp['name']} ({lang} text)"] + ([f"number {jp['number']} ✓"] if num_ok else [])})
    # 1. Kakawow-style card codes pin the exact card + parallel in the built-in database
    code_hit = bool(catalog.CODE_RE.search(parsed["raw_text"].upper()))
    text_n = " " + identify.norm(parsed["raw_text"]) + " "
    for c in catalog.match_text(parsed["raw_text"], parsed.get("name", ""), parsed.get("number", ""))[:8]:
        if code_hit:
            cands.append({"kind": "catalog", "card": c, "score": 100, "why": [f"card code {c.number} ✓"]})
            continue
        # Without a code, only accept a database card whose full name is actually printed on the card
        words = [w for w in identify.norm(c.name).split() if len(w) >= 3]
        tcg = (parsed.get("game") or "") in identify.TCG_GAMES
        if words and all(f" {w} " in text_n for w in words):
            cands.append({"kind": "catalog", "card": c, "score": 55 if tcg else 62, "why": [f"name {c.name} ✓"]})
        elif parsed.get("name"):
            # misread letters ('Charizrd'): the closest card name to what was read still counts, a bit lower
            import difflib
            sim = difflib.SequenceMatcher(None, c.name.lower(), parsed["name"].lower()).ratio()
            if sim >= 0.8:
                num_ok = bool(parsed.get("number")) and c.number.lower().lstrip("0").endswith(parsed["number"].split("/")[0].lstrip("#0").lower())
                cands.append({"kind": "catalog", "card": c, "score": (52 if tcg else 58) + (10 if num_ok else 0),
                              "why": [f"closest name to the text read ({parsed['name']} → {c.name})"] + (["number ✓"] if num_ok else [])})
    # 1b. Photo match against the price-guide photos (sports / non-sport cards): picks the exact card and
    #     parallel among the name matches, or among the player's cards when only the name was read
    if not code_hit and (parsed.get("game") or "") not in identify.TCG_GAMES and g not in identify.TCG_GAMES:
        pool = []
        for x in cands:
            if x["kind"] == "catalog":
                pool += [x["card"]] + catalog.siblings(x["card"])
        if not pool and parsed.get("name"):
            pool = catalog.search(parsed["name"], limit=40)
        if pool:
            pm = pipeline.catalog_photo_match(vision.tight_card(f["card"], f["edges"]), pool)
            by_key = {x["card"].key: x for x in cands if x["kind"] == "catalog"}
            for r in pm[:6]:
                if r["distance"] > 24 and r["score"] < 55:
                    continue  # doesn't look like it
                bonus = 30 if r["distance"] <= 10 else 18 if r["distance"] <= 16 else 6
                why = f"photo matches the price-guide picture ({r['distance']}/64 artwork, {r['colour'] * 100:.0f}% colours)"
                if r["card"].key in by_key:
                    by_key[r["card"].key]["score"] += bonus
                    by_key[r["card"].key]["why"].append(why)
                else:
                    cands.append({"kind": "catalog", "card": r["card"], "score": 50 + bonus, "why": [why]})
    # 1c. Picture alone: the scan's fingerprint against every price-guide photo (works with no readable text)
    if not code_hit:
        have = {x["card"].key for x in cands if x["kind"] == "catalog"}
        # 64-bit fingerprints of unrelated cards often sit ~12 apart, so only close ones count: <= 6 on its own,
        # <= 10 only to back up a card the text already points to
        pics = catalog.photo_lookup(f["phash"], max_distance=10)
        if len(pics) > 1 and pics[1][1] - pics[0][1] <= 4:
            # same artwork, several parallels: let the colours decide (compares with the actual photos)
            try:
                col = {r["card"].key: r["colour"] for r in pipeline.catalog_photo_match(vision.tight_card(f["card"], f["edges"]), [c for c, _ in pics])}
                pics.sort(key=lambda t: (t[1] - col.get(t[0].key, 0) * 8))
            except Exception:
                pass
        for c, dist in pics:
            why = f"picture matches the price-guide photo ({dist}/64)"
            if c.key in have:
                for x in cands:
                    if x["kind"] == "catalog" and x["card"].key == c.key:
                        x["score"] += 20 if dist <= 8 else 10
                        x["why"].append(why)
            elif dist <= 6:
                cands.append({"kind": "catalog", "card": c, "score": 80 - dist * 3, "why": [why]})
                have.add(c.key)
    # 2. Community fingerprint matches (cards people confirmed before)
    for m in comm:
        if not m.get("is_fake"):
            cands.append({"kind": "community", "row": m, "score": 90 - m["distance"] * 3, "why": [f"photo matches a confirmed scan ({m['distance']}/64)"]})
    # 3. Official databases: name + number + set size + HP/ATK/DEF + attacks
    if not code_hit and g in ("", "Pokémon", "Yu-Gi-Oh!", "Magic: The Gathering", "Lorcana"):
        dbc = identify.identify(f["lines"], parsed, g)[:6]
        if not dbc or dbc[0].get("score", 0) < 60:
            # the crop may have missed text (busy photo, card in hand): read the whole photo too
            full = f["full"]
            if max(full.size) > 1600:
                k = 1600 / max(full.size)
                full = full.resize((int(full.width * k), int(full.height * k)))
            fl = ocr.read_text(full)
            fp = ocr.parse(fl, "" if game == "Auto" else game)
            fp["number"] = fp.get("number") or parsed.get("number", "")
            more = identify.identify(fl, fp, g or fp.get("game") or parsed.get("game") or "")[:6]
            if more and (not dbc or more[0].get("score", 0) > dbc[0].get("score", 0)):
                dbc = more
                parsed = {**parsed, **{k: v for k, v in fp.items() if v}}
        pipeline.official_similarity(f["card"], dbc[:4])
        for c in dbc:
            d = c.get("official_distance")
            sc = c.get("score", 40)
            why = list(c.get("why", []))
            if d is not None and d <= 12:
                sc += 8
                why.append("artwork matches ✓")
            elif d is not None and d > 26:
                sc -= 12
            cands.append({"kind": "tcgdb", "c": c, "score": sc, "why": why})
    cands.sort(key=lambda x: -x["score"])
    try:
        _verify(cands, f, b, parsed, store)
    except Exception:
        pass
    cands.sort(key=lambda x: -x["score"])
    try:
        _colour_check(cands, vision.tight_card(f["card"], f["edges"]))
    except Exception:
        pass
    return {"front": f, "back": b, "parsed": parsed, "cands": cands, "fakes": [c for c in comm if c.get("is_fake") and c["distance"] <= pipeline.MATCH_STRONG],
            "id": hashlib.sha1(front).hexdigest()[:12], "ai": None, "game": g}


@st.cache_data(ttl=300, show_spinner=False)
def _corrections() -> list[tuple[int, str]]:
    out = []
    for r in get_store().corrections():
        try:
            out.append((int(r["phash"], 16), r["catalog_key"]))
        except (TypeError, ValueError):
            pass
    return out


def g0(game: str) -> str:
    return "" if game in ("Auto", "Sports") else game


def _player_name(lines) -> str:
    """Sports cards often print the first and last name on separate lines ('MIKE' / 'TROUT') with the team
    name nearby ('ANGELS'). Try neighbouring one-word lines as a full name and keep the pair the card database
    knows as a card name."""
    words = [(t.strip(), y) for t, c, y in lines if c > 0.5 and re.fullmatch(r"[A-Za-z.'\-]{2,}", t.strip())]
    best, best_n = "", 0
    for (a, ya), (b, yb) in zip(words, words[1:]):
        if abs(ya - yb) > 0.12 or a.lower() == b.lower():
            continue
        name = f"{a} {b}".title()
        hits = [c for c in catalog.search(name, limit=30) if a.lower() in c.name.lower() and b.lower() in c.name.lower()]
        if len(hits) > best_n:
            best, best_n = name, len(hits)
    return best


def _verify(cands: list[dict], f: dict, b: dict | None, parsed: dict, store) -> None:
    """Corrections people made before, the serial number, and the card back (see core/verify.py)."""
    by_key = {x["card"].key: x for x in cands if x["kind"] == "catalog"}

    def bump(card, pts: int, why: str, base: int = 50):
        x = by_key.get(card.key)
        if x:
            x["score"] += pts
            x["why"].append(why)
        else:
            x = {"kind": "catalog", "card": card, "score": base + pts, "why": [why]}
            cands.append(x)
            by_key[card.key] = x

    # 1. a scan that looks like this one was corrected to a card before: trust that choice
    try:
        q = int(f["phash"], 16)
        seen = {}
        for h, key in _corrections():
            d = bin(q ^ h).count("1")
            if d <= 8 and (key not in seen or d < seen[key]):
                seen[key] = d
        for key, d in sorted(seen.items(), key=lambda kv: kv[1])[:3]:
            c = catalog.get(key)
            if c:
                bump(c, 40 - d * 2, f"picked by a person for a scan that looked like this ({d}/64)", base=45)
    except (TypeError, ValueError, KeyError):
        pass

    # the card number printed on the front ('4/102', '#325'): breaks ties between look-alike cards
    front_no = (parsed.get("number") or "").split("/")[0].lstrip("#").lstrip("0").lower()
    if front_no:
        for x in [x for x in cands if x["kind"] == "catalog"]:
            cn = (x["card"].number or "").split("/")[0].lstrip("#").lstrip("0").lower()
            if cn and cn == front_no:
                x["score"] += 8
                x["why"].append(f"number {parsed['number']} ✓")
            elif cn and not cn.endswith(front_no):
                x["score"] -= 6

    back_lines = (b or {}).get("lines", []) if b else []
    back = verify.back_facts(back_lines) if back_lines else None
    text = parsed.get("raw_text", "") + "\n" + (back["text"] if back else "")
    tcg = (parsed.get("game") or "") in identify.TCG_GAMES

    # 2. card back: number, © year (sports cards; TCG backs are all the same)
    if back and not tcg:
        top = next((x for x in sorted(cands, key=lambda z: -z["score"]) if x["kind"] == "catalog"), None)
        if not top or top["score"] < 70:
            # front gave little: the back usually has the player's name and the card number too
            bp = ocr.parse(back_lines, "")
            for c in catalog.match_text(back["text"], bp.get("name", ""), back["number"] or bp.get("number", ""))[:6]:
                if c.key not in by_key:
                    bump(c, 0, f"name on the back ({c.name})", base=50)
        for x in [x for x in cands if x["kind"] == "catalog"]:
            c = x["card"]
            if back["number"] and verify.number_matches(c.number, back["number"]):
                x["score"] += 12
                x["why"].append(f"number {back['number']} on the back ✓")
            elif back["number"] and c.number:
                x["score"] -= 8
            ym = verify.year_matches(catalog.sets().get(c.set_id, {}).get("year"), back["year"])
            if ym:
                x["score"] += 6
                x["why"].append(f"© {back['year']} on the back ✓")
            elif ym is False:
                x["score"] -= 10
                x["why"].append(f"© {back['year']} on the back doesn't fit this set's year")

    # 3. serial number: names the parallel exactly (sports / non-sport numbered parallels)
    if not tcg and verify.serials(text):
        top = next((x for x in sorted(cands, key=lambda z: -z["score"]) if x["kind"] == "catalog"), None)
        if top:
            sib = catalog.siblings(top["card"])
            run = verify.serial_fit(text, {c.print_run for c in sib if c.print_run})
            if run:
                top_score = top["score"]
                for c in sib:
                    if c.print_run == run:
                        bump(c, 30, f"serial numbered /{run} on the card ✓ ({c.variant or 'Base'} is /{run})", base=top_score - 22)
                    elif c.key in by_key:
                        # unnumbered base, or a parallel numbered to a different run
                        by_key[c.key]["score"] -= 15
                        by_key[c.key]["why"].append(f"the card is numbered /{run}, this one isn't" if not c.print_run else f"this one is /{c.print_run}, the card says /{run}")


def _colour_check(cands: list[dict], card) -> None:
    """Parallels / rarities of the top card compared by colour: each parallel's learned colours (from its
    price-guide photos) and the colour its name says (Gold, Blue Prizm, Black 1/1). Moves the parallel whose
    colours fit best up, and says so; it only reorders parallels of the same card, never picks the card."""
    top = next((x for x in cands if x["kind"] == "catalog"), None)
    if not top:
        return
    sib = catalog.siblings(top["card"])
    if len(sib) < 2:
        return
    sig = colour.signature(card)
    ranked = colour.rank_parallels(sig, [{"set": c.set_id, "variant": c.variant or "Base", "card": c} for c in sib],
                                   catalog.colour_profiles())
    known = [r for r in ranked if r["colour_fit"] is not None]
    if not known:
        return
    by_key = {x["card"].key: x for x in cands if x["kind"] == "catalog"}
    looks = colour.describe(sig)
    # only a clear winner counts (gold vs bronze vs orange can tie on colour alone)
    best = known[0] if len(known) == 1 or known[1]["colour_fit"] - known[0]["colour_fit"] >= 0.15 else None
    for r in known:
        fit, c = r["colour_fit"], r["card"]
        clear = best is not None and r is best
        adj = round((0.45 - fit) * 20) if (clear or fit >= 0.65) else 0  # +9 clear fit .. -11 clearly the wrong colour
        label = c.variant or "Base"
        why = f"colours fit {label} ✓ ({r['colour_why']})" if clear and fit <= 0.3 else \
              f"colours don't look like {label} (card looks: {looks})" if fit >= 0.65 else ""
        x = by_key.get(c.key)
        if x:
            x["score"] += adj
            if why:
                x["why"].append(why)
        elif r is best and fit <= 0.25 and x is None:
            # the best-fitting parallel wasn't among the matches yet: offer it next to the top card
            cands.append({"kind": "catalog", "card": c, "score": top["score"] - 4 + adj, "why": [f"same card as {top['card'].name}, {why}"]})
    cands.sort(key=lambda x: -x["score"])


def _read_slab(f: dict, game: str) -> dict | None:
    """Graded slab? Read the label from the card crop, else from the top of the full photo (where the label sits)."""
    sl = slab.read_label(f["lines"])
    lines = f["lines"]
    if not (sl and sl["company"] != "Unknown") and game in ("Auto", "Graded slab"):
        full = f["full"]
        top = full.crop((0, 0, full.width, int(full.height * 0.45)))
        if top.width > 1100:
            top = top.resize((1100, int(top.height * 1100 / top.width)))
        tl = ocr.read_text(top)
        s2 = slab.read_label(tl)
        if s2 and (s2["company"] != "Unknown" or game == "Graded slab"):
            sl, lines = s2, tl
    if sl and (sl["company"] != "Unknown" or game == "Graded slab"):
        sl["lines"] = lines
        return sl
    return None


def _analyze_slab(front: bytes, f: dict, b, sl: dict, game: str) -> dict:
    """Identify the card from the slab label (name, number, set, year)."""
    desc = sl["desc"]
    up = desc.upper()
    g = "Pokémon" if re.search(r"POK[EÉ]MON|\bP\.?M\.?\b", up) else "Yu-Gi-Oh!" if "YU-GI-OH" in up else \
        "Magic: The Gathering" if "MAGIC" in up else "" if game in ("Auto", "Graded slab") else game
    lines = [(t, 0.99, 0.05 + i * 0.05) for i, t in enumerate(sl["desc_lines"])]
    parsed = {"raw_text": desc, "name": slab.name_guess(sl), "number": sl["number"], "set_code": "", "game": g, "year": sl["year"]}
    ym = re.search(r"[A-Z]{2,5}-[A-Z]{0,2}\d{2,3}", up)
    if ym:
        parsed["set_code"] = ym.group(0)
    cands: list[dict] = []
    text_n = " " + identify.norm(desc) + " "
    # card codes on labels often run into the next word ("#CDT-B-19922"): take up to 3 digits
    for m in re.finditer(r"([A-Z]{2,5})-([A-Z]{1,5})-?(\d{1,3})", up):
        for c in catalog.by_code(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")[:1]:
            cands.append({"kind": "catalog", "card": c, "score": 100, "why": [f"card code {c.number} on the label ✓"]})
    for c in ([] if cands else catalog.match_text(desc, parsed["name"], parsed["number"])[:8]):
        words = [w for w in identify.norm(c.name).split() if len(w) >= 3]
        if words and all(f" {w} " in text_n for w in words):
            sc = 70 + (10 if c.number and identify._num(c.number.split("-")[-1]) == identify._num(parsed["number"].split("/")[0]) else 0)
            if c.variant and all(w in text_n for w in identify.norm(c.variant).split()):
                sc += 10
            cands.append({"kind": "catalog", "card": c, "score": sc, "why": [f"label names {c.name} ✓"] + ([f"parallel {c.variant} ✓"] if c.variant and sc >= 80 else [])})
    if g in ("", "Pokémon", "Yu-Gi-Oh!", "Magic: The Gathering"):
        for c in identify.identify(lines, parsed, g)[:5]:
            cands.append({"kind": "tcgdb", "c": c, "score": c.get("score", 40), "why": ["read from the slab label"] + c.get("why", [])})
    if not cands and parsed["name"]:
        cands.append({"kind": "ai", "c": {"name": parsed["name"].title(), "number": parsed["number"], "set": "", "rarity": "", "year": sl["year"]},
                      "score": 30, "why": ["read from the slab label"]})
    cands.sort(key=lambda x: -x["score"])
    return {"front": f, "back": b, "parsed": parsed, "cands": cands, "fakes": [], "slab": sl,
            "id": hashlib.sha1(front).hexdigest()[:12], "ai": None, "game": g}


def _slab_price(x: dict, sl: dict):
    """Price at the slab's grade when the database has it (PSA 9 / PSA 10), else None."""
    if x["kind"] == "catalog" and sl["company"] == "PSA":
        if sl.get("grade") == 10 and x["card"].psa10:
            return x["card"].psa10
        if sl.get("grade") == 9 and x["card"].psa9:
            return x["card"].psa9
    return None


def _run_ai(scan: dict):
    a = st.session_state.get("ai")
    if not a:
        return
    imgs = [vision.to_jpeg_b64(scan["front"]["card"])]
    if scan["back"]:
        imgs.append(vision.to_jpeg_b64(scan["back"]["card"]))
    hint = "; ".join(_title(c) for c in scan["cands"][:5])
    text = ai.call(a["prov"], a["key"], a["model"], ai.grade_prompt("", bool(scan["back"]), scan["parsed"]["raw_text"], hint), imgs, a["base"])
    scan["ai"] = ai.extract_json(text)
    c = scan["ai"].get("card") or {}
    if c.get("name"):
        # Try to pin the AI's answer to an exact database card
        q = " ".join(x for x in [c.get("name", ""), c.get("variant", ""), (c.get("number") or "").split("/")[0]] if x)
        hits = catalog.search(q, limit=3)
        for h in hits:
            scan["cands"].insert(0, {"kind": "catalog", "card": h, "score": 95})
        scan["cands"].insert(len(hits), {"kind": "ai", "c": c, "score": 85})


def _title(x: dict) -> str:
    if x["kind"] == "catalog":
        return x["card"].label
    if x["kind"] == "community":
        r = x["row"]
        return _join(r["name"], r.get("rarity"), f"#{r['number']}" if r.get("number") else "", r.get("set_name"))
    if x["kind"] == "tcgdb":
        c = x["c"]
        return _join(c["name"], c.get("rarity"), f"#{c['number']}" if c.get("number") else "", c.get("set"))
    c = x["c"]
    return _join(c.get("name", ""), c.get("rarity"), f"#{c['number']}" if c.get("number") else "", c.get("set"))


def _join(*parts) -> str:
    """'Charizard ex · Special Illustration Rare · #199/165 · 151' (skips empty / 'None' parts)."""
    return " · ".join(str(p) for p in parts if p and str(p).strip().lower() not in ("none", "null"))


def _price(x: dict):
    if x["kind"] == "catalog":
        c = x["card"]
        return catalog.value(c)[0], c.psa10
    if x["kind"] == "tcgdb":
        return x["c"]["raw"].get("mid"), None
    return None, None


def _record(x: dict, scan: dict, grade: dict, auth: dict) -> dict:
    f = scan["front"]
    thumb = vision.thumbnail_b64(f["card"])
    if x["kind"] == "catalog":
        rec = record_from_catalog(x["card"], thumb)
    else:
        if x["kind"] == "community":
            r = x["row"]
            card = {"game": r["game"], "name": r["name"], "set": r["set_name"], "number": r["number"], "year": r["year"], "brand": r["brand"],
                    "rarity": r["rarity"], "variant": r["variant"], "card_type": r["card_type"]}
            raw = {"mid": None}
        elif x["kind"] == "tcgdb":
            c = x["c"]
            card = {k: c.get(k, "") for k in ("game", "name", "set", "number", "year", "brand", "rarity", "variant", "card_type")}
            raw = c["raw"]
        else:
            c = x["c"]
            card = {"game": c.get("game", ""), "name": c.get("name", ""), "set": c.get("set", ""), "number": c.get("number", ""), "year": c.get("year", ""),
                    "brand": c.get("brand", ""), "rarity": c.get("rarity", ""), "variant": c.get("variant", ""), "card_type": c.get("card_type", "")}
            raw = {"mid": None}
        rec = {"v": 1, "card": card, "pricing": {"raw": raw, "currency": "USD", "note": "", "graded_label": "", "graded_mid": None,
                                                 "priced_at": datetime.utcnow().isoformat() + "Z"},
               "match": {"source": x["kind"], "catalog_key": "", "url": "", "image_url": (x.get("c") or {}).get("image_url", "")},
               "thumb": thumb}
    rec["grade"] = grade
    sl = scan.get("slab")
    if sl:
        rec["pricing"]["graded_label"] = slab.grade_text(sl)
        rec["pricing"]["graded_mid"] = _slab_price(x, sl)
        rec["slab"] = {k: sl.get(k) for k in ("company", "grade", "label", "cert", "qualifiers", "subgrades", "tag_score", "lookup")}
    rec["authenticity"] = auth
    rec["phash"] = f["phash"]
    return rec


def page():
    st.markdown("### Scan")
    s = st.session_state
    top = st.columns([2, 1])
    bulk = top[1].toggle("Bulk mode", value=s.get("bulk", False), help="Keep scanning card after card; each one is added with one tap.")
    s.bulk = bulk
    game = top[0].selectbox("Card type", GAMES, index=0, label_visibility="collapsed")
    n = s.get("scan_n", 0)
    up = st.file_uploader("Take a photo of the card (front)", type=["jpg", "jpeg", "png", "webp"], key=f"up_{n}")
    with st.expander("Add the back (improves grading)"):
        up_b = st.file_uploader("Back", type=["jpg", "jpeg", "png", "webp"], key=f"upb_{n}", label_visibility="collapsed")
    st.caption("Card out of the sleeve, flat on a dark surface, all four corners in the shot.")

    if up:
        data = up.getvalue()
        sid = hashlib.sha1(data).hexdigest()[:12]
        if s.get("scan", {}).get("id") != sid:
            with st.spinner("Identifying…"):
                try:
                    s.scan = _analyze(data, up_b.getvalue() if up_b else None, game)
                    if s.get("ai") and (not s.scan["cands"] or s.scan["cands"][0]["score"] < 90):
                        _run_ai(s.scan)
                except Exception as e:
                    st.error(f"Couldn't read that photo ({e}). Try a closer, sharper shot.")
                    return
            s.pick = 0
    scan = s.get("scan")
    if scan and up:
        _result(scan)
    _tray()


def _result(scan: dict):
    s = st.session_state
    f = scan["front"]
    cands = scan["cands"]
    sl = scan.get("slab")
    if scan.get("is_back"):
        a, b2 = st.columns([1, 1.4])
        a.image(f["card"], width="stretch")
        b2.info(f"This is the **back** of a {scan['is_back']} card. Scan the front to identify and price it, then add this photo "
                "under **Add the back** to include it in grading (back centering counts for PSA and TAG).")
        return
    left, right = st.columns([1, 1.4])
    left.image(f["full"] if sl else f["card"], width="stretch")
    with right:
        if sl:
            _slab_header(sl)
        if not cands:
            st.markdown("**No match yet.**")
            st.caption("Type the name below, turn on the free AI boost in the menu, or confirm it for the community so the next scan is recognised. "
                       "The grade estimate below works either way.")
            _manual_search(scan, game_of(scan), expanded=True)
            x = {"kind": "ai", "c": {"name": scan["parsed"].get("name", ""), "number": scan["parsed"].get("number", ""), "set": "", "rarity": ""},
                 "score": 0, "why": []}
            grade, auth = _grade_auth(scan, x)
    if not cands:
        _details(scan, x, grade, auth)
        return
    with right:
        i = min(s.get("pick", 0), len(cands) - 1)
        x = cands[i]
        off_url = (x.get("c") or {}).get("image_url", "") if x["kind"] in ("tcgdb", "ai") else card_image(x["card"]) if x["kind"] == "catalog" else ""
        if off_url:
            left.image(off_url, width="stretch", caption="Official card image, to compare")
        raw, p10 = _price(x)
        title = _title(x)
        graded = _slab_price(x, sl) if sl else None
        pr = x["card"].print_run if x["kind"] == "catalog" else None
        src = {"catalog": "card database", "community": "community catalog", "tcgdb": "official database", "ai": "AI"}[x["kind"]]
        why = " · ".join(x.get("why", []))
        st.markdown(f"<div class='hero'><div class='lbl'>Best match · {src}</div><div style='font-size:20px;font-weight:800'>{esc(title)}</div>"
                    + (f"<div class='muted' style='font-size:13px'>Matched on: {esc(why)}</div>" if why else "")
                    + f"<div>{rarity_pill(pr)}</div><div class='big' style='color:#E6B94B'>{money(graded or raw)}</div>"
                    + (f"<div class='muted'>{esc(slab.grade_text(sl))} sold-listing price · raw {money(raw)}</div>" if graded else
                       f"<div class='muted'>raw{(' · PSA 10 ' + money(p10)) if p10 else ''}"
                       + (f" · price at {esc(slab.grade_text(sl))}: see sold links below" if sl else "") + "</div>")
                    + "</div>", unsafe_allow_html=True)
        if x["kind"] == "catalog":
            sset = catalog.sets().get(x["card"].set_id, {})
            st.caption(sset.get("name", ""))
            odds = catalog.odds_text(catalog.tier(x["card"]), sset)
            if odds:
                st.caption(f"Pull odds: {odds}")
        grade, auth = _grade_auth(scan, x)
        b = st.columns(2)
        disabled = bool(need_code()) if get_store().shared else False
        if b[0].button("Add to collection", type="primary", width="stretch", disabled=disabled):
            add_to_collection(_record(x, scan, grade, auth))
            _remember(scan, x)
            s.setdefault("tray", []).append({"title": title, "price": raw})
            st.toast(f"Added {title}")
            if s.get("bulk"):
                s.scan_n = s.get("scan_n", 0) + 1
                s.pop("scan", None)
                st.rerun()
        if b[1].button("♡ Wishlist", width="stretch", disabled=disabled):
            add_to_collection(_record(x, scan, grade, auth), wishlist=True)
            _remember(scan, x)
            st.toast("Added to wishlist")
        if x["kind"] == "catalog" and st.button("Open card page", width="stretch"):
            open_card(x["card"].key)
        if x.get("score", 0) < 50:
            st.warning("Not sure about this one. Check the name and number, pick another match, or search below.")
        if len(cands) > 1:
            labels = [f"{_title(c)} · {money(_price(c)[0])}" for c in cands[:10]]
            pick = st.selectbox("Not right? Pick another match", range(len(labels)), index=i, format_func=lambda k: labels[k])
            if pick != i:
                s.pick = pick
                st.rerun()
        _manual_search(scan, game_of(scan))
    _details(scan, x, grade, auth)


def _remember(scan: dict, x: dict) -> None:
    """The person settled on this card: save it against the scan's fingerprint, so the next scan that looks
    the same (same card, same parallel) gets it straight away."""
    if x["kind"] != "catalog" or scan.get("_remembered") == x["card"].key:
        return
    try:
        get_store().add_correction(scan["front"]["phash"], x["card"].key)
        scan["_remembered"] = x["card"].key
        _corrections.clear()
    except Exception:
        pass


def _slab_header(sl: dict):
    g = sl.get("grade")
    col = grade_color(g if isinstance(g, (int, float)) else None)
    subs = " · ".join(f"{k} {v:g}" for k, v in sl.get("subgrades", {}).items())
    st.markdown(
        f"<div class='slab'><div class='slab-in'><div class='slab-who'>Graded slab · {esc(sl['company'])}</div>"
        f"<div class='slab-grade' style='color:{col}'>{esc(f'{g:g}' if isinstance(g, (int, float)) else (sl.get('label') or '?'))}</div>"
        f"<div class='slab-lbl'>{esc(sl.get('label',''))} {esc(' '.join(sl.get('qualifiers', [])))}</div>"
        + (f"<div class='slab-sub'>TAG score {sl['tag_score']} / 1000</div>" if sl.get("tag_score") else "")
        + (f"<div class='slab-sub'>{esc(subs)}</div>" if subs else "")
        + f"<div class='slab-sub'>Cert #{esc(sl.get('cert') or 'not read')}</div></div></div>", unsafe_allow_html=True)
    if sl.get("qualifiers"):
        st.caption("Qualifier: " + ", ".join({"OC": "off-center", "ST": "staining", "PD": "print defect", "OF": "out of focus", "MK": "marks", "MC": "miscut"}[q] for q in sl["qualifiers"]))
    if sl.get("lookup"):
        st.link_button(f"Verify cert on {sl['company']} ↗", sl["lookup"], width="stretch")
    if sl.get("desc"):
        st.caption("Label: " + sl["desc"][:160])


def _user_lines(scan: dict) -> dict:
    """The card edges: the person's adjusted blue lines from the centering tool, else the automatic ones."""
    f = scan["front"]
    return st.session_state.get(f"_cenlines_cen_{scan['id']}") or f["edges"]


def _inspection(scan: dict, x: dict):
    """Front inspection on the card cut to its edges (re-run when the person moves the blue lines), and
    against the official image of the chosen match (error / fading check)."""
    f = scan["front"]
    L = _user_lines(scan)
    off = (x.get("c") or {}).get("_official") if x["kind"] == "tcgdb" else None
    rad = condition.corner_radius_px(game_of(scan), scan.get("_style", ""))
    sid = x["card"].set_id if x["kind"] == "catalog" else ""
    if sid and scan.get("_style") != "vintage":
        rad = catalog.corner_radius_px(sid) or rad  # this set's own corner shape, measured on its photos
    foil = scan.get("_style") == "full_art"
    ck = "_insp_" + str((x.get("c") or {}).get("ref_id") if off is not None else "") + f"_{rad}_{foil}_" + "_".join(str(round(L[k])) for k in ("ol", "ot", "or", "ob"))
    if ck not in scan:
        if off is None and L is f.get("_edges0", f["edges"]) and rad == 30 and not foil:
            scan[ck] = copy.deepcopy(f["inspect"])  # the set's baseline is applied to this copy below
        else:
            scan[ck] = condition.inspect_card(vision.tight_card(f["card"], L), official=off, corner_radius=rad, foil_border=foil)
        if sid and not scan[ck].metrics.get("baseline"):
            condition.apply_baseline(scan[ck], (catalog.set_profile(sid) or {}).get("sub"))  # the set's own design
        dco = catalog.die_cut_outline(x["card"]) if x["kind"] == "catalog" else None
        if dco and "die_cut" not in scan[ck].metrics:  # die-cut: compare the outline with the set's cut
            dcr = condition.die_cut_check(vision.tight_card(f["card"], L), dco["mask"], dco.get("agree", 1.0))
            g_dc = condition._sev_to_grade(dcr["sev"])
            scan[ck].subgrades["corners"] = g_dc
            scan[ck].subgrades["edges"] = min(scan[ck].subgrades["edges"], g_dc)
            scan[ck].findings += [condition.Finding("edges", "die-cut outline", n, dcr["sev"], "possible") for n in dcr["notes"]]
            scan[ck].metrics["die_cut"] = dcr
    return scan[ck]


def _auto_subs(scan: dict, x: dict) -> dict:
    fi = _inspection(scan, x)
    bi = (scan.get("back") or {}).get("inspect")
    return {k: min(fi.subgrades[k], bi.subgrades[k]) if bi else fi.subgrades[k] for k in ("corners", "edges", "surface")}


def game_of(scan: dict) -> str:
    return scan.get("game") or scan["parsed"].get("game") or ""


def _manual_search(scan: dict, game: str, expanded: bool = False):
    """Type the name (and number) printed on the card; searches the official databases and the built-in one."""
    with st.expander("Search by name and number", expanded=expanded):
        a, b, c = st.columns([2, 1, 1])
        name = a.text_input("Card name", key=f"mn_{scan['id']}", placeholder="e.g. Charizard ex")
        num = b.text_input("Number", key=f"mm_{scan['id']}", placeholder="006/165")
        g = c.selectbox("Game", ["Auto", "Pokémon", "Yu-Gi-Oh!", "Magic: The Gathering", "Lorcana", "Other"], key=f"mg_{scan['id']}")
        if st.button("Search", key=f"ms_{scan['id']}", disabled=not name.strip()):
            lines = [(name, 1.0, 0.05)] + ([(num, 1.0, 0.95)] if num else []) + list(scan["front"]["lines"])
            parsed = dict(scan["parsed"], name=name, number=num or scan["parsed"].get("number", ""),
                          raw_text=name + "\n" + num + "\n" + scan["parsed"]["raw_text"])
            gg = "" if g in ("Auto", "Other") else g
            new = []
            if g != "Other":
                for c2 in identify.identify(lines, parsed, gg)[:6]:
                    new.append({"kind": "tcgdb", "c": c2, "score": c2.get("score", 40) + 10, "why": c2.get("why", [])})
            for c2 in catalog.search(" ".join(x for x in [name, num.split("/")[0]] if x), limit=6):
                new.append({"kind": "catalog", "card": c2, "score": 55, "why": [f"name {c2.name} ✓"]})
            if new:
                new.sort(key=lambda z: -z["score"])
                scan["cands"] = new + [z for z in scan["cands"] if z not in new]
                st.session_state.pick = 0
                st.rerun()
            else:
                st.info("No card found with that name. Check the spelling, or pick the game.")


STYLE_LABELS = {"standard": "Standard (bordered)", "full_art": "Full art / borderless", "die_cut": "Die-cut", "vintage": "Vintage / square corners"}


def _card_facts(x: dict) -> tuple[str, str, str, str, str]:
    """(set id, variant / rarity, name, year, number) of the picked match."""
    if x["kind"] == "catalog":
        c = x["card"]
        return c.set_id, c.variant or "Base", c.name, str(catalog.sets().get(c.set_id, {}).get("year", "")), c.number
    c = x.get("c") or {}
    return "", f"{c.get('rarity', '')} {c.get('variant', '')}".strip(), c.get("name", ""), str(c.get("year", "")), c.get("number", "")


def _apply_style(scan: dict, x: dict) -> str:
    """Card layout (full art, die-cut...) and this set's measured border widths steer where the inner
    centering lines are looked for. Re-places the lines when the picked card or the chosen style changes."""
    f = scan["front"]
    sid, variant, name, year, number = _card_facts(x)
    printed = scan["parsed"].get("number", "") or ""
    pno, prar = vision.printed_rarity(scan["parsed"].get("raw_text", ""))
    printed = printed if "/" in printed else pno
    auto = vision.card_style(f"{variant} {prar}".strip(), name, year, printed or number)
    if auto == "standard" and vision.looks_full_art(f["card"], f.get("_edges0", f["edges"])):
        auto = "full_art"
    pick = st.session_state.get(f"style_{scan['id']}")
    style = next((k for k, v in STYLE_LABELS.items() if v == pick), auto) if pick and pick != "Auto" else auto
    prof = catalog.border_profile(sid, variant) if sid else None
    if not prof and sid and (catalog.set_profile(sid) or {}).get("border"):
        sb = catalog.set_profile(sid)
        prof = {"l": sb["border"][0], "r": sb["border"][1], "t": sb["border"][2], "b": sb["border"][3], "n": sb.get("n", 1), "borderless": sb.get("borderless", 0)}
    expect = {k: prof[k] for k in ("l", "r", "t", "b")} if prof and prof.get("n", 0) >= 2 and (prof.get("borderless") or 0) < 0.5 else None
    sig = (style, tuple(expect.values()) if expect else None)
    if scan.get("_style_sig") != sig:
        if "_edges0" not in f:
            f["_edges0"] = f["edges"]
        f["edges"] = f["_edges0"] if style == "standard" and not expect else vision.find_lines(f["card"], f["found"], expect=expect, style=style)
        L = f["edges"]
        f["centering"] = vision.Centering(L["il"] - L["ol"], L["or"] - L["ir"], L["it"] - L["ot"], L["ob"] - L["ib"])
        for k in (f"_cenlines_cen_{scan['id']}", f"_cenimg_cen_{scan['id']}"):
            st.session_state.pop(k, None)
        scan["_style_sig"] = sig
    scan["_style"], scan["_profile"] = style, prof
    return style


def _grade_auth(scan: dict, x: dict):
    sl = scan.get("slab")
    if sl:
        g = sl.get("grade")
        grade = {"method": "slab", "company": sl["company"], "grade": g, "label": sl.get("label", ""), "cert": sl.get("cert", ""),
                 "qualifiers": sl.get("qualifiers", []), "sub": sl.get("subgrades", {}), "centering": {"front": "", "back": ""},
                 "psa": g if sl["company"] == "PSA" else None, "psa_label": sl.get("label", "") if sl["company"] == "PSA" else "",
                 "tag_grade": f"{g:g}" if sl["company"] == "TAG" and isinstance(g, (int, float)) else "", "tag_score": sl.get("tag_score")}
        chosen = x.get("c") if x["kind"] == "tcgdb" else None
        auth = pipeline.authenticity_signals(chosen, [], None)
        auth["reasons"].insert(0, f"Graded and encapsulated by {sl['company']}. Check the cert number online to confirm the slab is real.")
        if auth["verdict"] == "not_checked":
            auth["verdict"] = "unsure" if not sl.get("cert") else "not_checked"
        return grade, auth
    _apply_style(scan, x)
    f = scan["front"]
    key = scan["id"]
    front_c = centering.current(f["card"], f["centering"], f"cen_{key}", f.get("edges"))
    back_c = scan["back"]["centering"] if scan["back"] else None
    auto = _auto_subs(scan, x)
    # the person's own checklist answers override the automatic ones
    picked, overridden = {}, False
    for k, lab in (("c", "corners"), ("e", "edges"), ("s", "surface")):
        sel = st.session_state.get(f"k_{k}_{key}")
        if sel and sel != condition.subgrade_to_option(auto[lab]):
            picked[lab], overridden = sel, True
        else:
            picked[lab] = auto[lab]
    grade = grading.estimate(front_c.worst(), back_c.worst() if back_c else None, picked["corners"], picked["edges"], picked["surface"],
                             tcg=game_of(scan) not in ("Sports", "Baseball", "Basketball", "Football", "Soccer", "Hockey"))
    grade["method"] = "inspection + your checklist" if overridden else "automatic inspection"
    grade["centering"] = {"front": front_c.text(), "back": back_c.text() if back_c else ""}
    aires = scan.get("ai") or {}
    if aires.get("psa") and st.session_state.get(f"useai_{key}", True):
        p, t, cnd = aires.get("psa") or {}, aires.get("tag") or {}, aires.get("condition") or {}
        grade.update({"method": "ai", "psa": p.get("grade"), "psa_label": p.get("label", ""), "psa_range": p.get("range", ""),
                      "tag_score": t.get("score"), "tag_grade": t.get("grade", ""), "tag_label": t.get("label", ""),
                      "notes": "; ".join((cnd.get("defects") or [])[:6])})
    chosen = x.get("c") if x["kind"] == "tcgdb" else None
    auth = pipeline.authenticity_signals(chosen, scan["fakes"], aires.get("authenticity"))
    return grade, auth


def _details(scan: dict, x: dict, grade: dict, auth: dict):
    if scan.get("slab"):
        sl = scan["slab"]
        with st.expander("Slab details and sold prices at this grade"):
            q = " ".join(z for z in [_title(x).split(" · ")[0], (x.get("c") or {}).get("set", "") if x["kind"] != "catalog" else catalog.sets().get(x["card"].set_id, {}).get("name", ""),
                                     f"{sl['company']} {sl['grade']:g}" if isinstance(sl.get("grade"), (int, float)) else sl["company"]] if z)
            st.markdown(f"[eBay sold: {esc(q)} ↗](https://www.ebay.com/sch/i.html?_nkw={q.replace(' ', '+')}&LH_Sold=1&LH_Complete=1) · "
                        f"[130point ↗](https://130point.com/sales/) · [Google ↗](https://www.google.com/search?q={q.replace(' ', '+')}+sold+price)")
            if sl.get("lookup"):
                st.markdown(f"Population report and cert details: [{sl['company']} cert {sl['cert']} ↗]({sl['lookup']})")
            st.caption("The card is sealed in the slab, so the app doesn't re-grade it. Text read from the label: " + " · ".join(sl.get("desc_lines", [])))
        return
    f = scan["front"]
    key = scan["id"]
    bg, fg, label = VERDICTS.get(auth["verdict"], VERDICTS["not_checked"])
    with st.expander(f"Grade estimate: PSA {grade.get('psa','—')} · TAG-style {grade.get('tag_grade','—')}   |   Authenticity: {label}"):
        c = st.columns(2)
        c[0].markdown(f"<div class='slab'><div class='slab-in'><div class='slab-who'>PSA · estimate</div><div class='slab-grade' style='color:{grade_color(grade.get('psa'))}'>{esc(grade.get('psa','—'))}</div>"
                      f"<div class='slab-lbl'>{esc(grade.get('psa_label',''))}</div><div class='slab-sub'>Likely {esc(grade.get('psa_range',''))}</div></div></div>", unsafe_allow_html=True)
        c[1].markdown(f"<div class='slab'><div class='slab-in'><div class='slab-who'>TAG-style · estimate</div><div class='slab-grade' style='color:{grade_color(grade.get('tag_grade'))}'>{esc(grade.get('tag_grade','—'))}</div>"
                      f"<div class='slab-lbl'>{esc(grade.get('tag_label',''))}</div><div class='slab-sub'>Score {esc(grade.get('tag_score','—'))} / 1000</div></div></div>", unsafe_allow_html=True)
        if (scan.get("ai") or {}).get("psa"):
            st.toggle("Use the AI's grade", value=True, key=f"useai_{key}")
        st.markdown(f"**Centering** {esc(grade['centering']['front'])}" + (f" · back {esc(grade['centering']['back'])}" if grade['centering'].get('back') else ""))
        style = scan.get("_style", "standard")
        sc = st.columns([1, 2])
        sc[0].selectbox("Card style", ["Auto"] + list(STYLE_LABELS.values()), key=f"style_{key}",
                        help="Auto reads it from the card's rarity / parallel. Full art: thin frame, art runs to it. Die-cut: shaped outline.")
        note = grading.CARD_STYLES.get(STYLE_LABELS.get(style, ""), "")
        prof = scan.get("_profile")
        sc[1].caption(f"**{STYLE_LABELS.get(style)}** · {note}" + (
            f"  \nThis set's printed border (from {prof['n']} photos): left+right ≈ {100 * (prof['l'] + prof['r']):.1f}% of the width, "
            f"top+bottom ≈ {100 * (prof['t'] + prof['b']):.1f}% of the height; the inner lines are looked for there." if prof and prof.get("l") is not None else
            f"  \nThis set / rarity is printed without a border line (measured on {prof['n']} photos)." if prof else ""))
        caps = grading.grader_caps(_worst_of(grade["centering"]["front"]), _worst_of(grade["centering"].get("back", "")),
                                   tcg=game_of(scan) not in ("Sports", "Baseball", "Basketball", "Football", "Soccer", "Hockey"))
        st.caption("Best grade the centering allows · " + " · ".join(f"**{k}** {v}" for k, v in caps.items()))
        if grade.get("graders") and grade.get("method") != "ai":
            st.markdown("**Estimated grade at each company** · " + " · ".join(
                f"{k} **{v['grade']}**" + (f" {v['label']}" if v.get("label") else "") for k, v in grade["graders"].items()))
            bs = grade["graders"].get("BGS", {}).get("sub")
            if bs:
                st.caption("BGS subgrades · " + " · ".join(f"{k} {v:g}" for k, v in bs.items()))
        with st.popover("How grading works"):
            st.markdown(grading.GUIDE)
        if (f.get("skew") or {}).get("applied"):
            st.caption("📐 The photo was taken at a slight angle, so the card was straightened (all four edges made square) before measuring centering and checking corners and edges.")
        centering.centering_tool(f["card"], f["centering"], f"cen_{key}", f.get("edges"))
        _inspection_panel(scan, x, key)
        _autograph_panel(scan, x)
        reasons = "".join(f"<li>{esc(r)}</li>" for r in auth["reasons"]) or "<li>Pick a database match or use the AI boost to compare against the real card.</li>"
        st.markdown(f"<div class='verdict' style='background:{bg};border:1px solid {fg}'><b style='color:{fg}'>{label}</b><ul style='margin:6px 0 0 0'>{reasons}</ul></div>", unsafe_allow_html=True)
        st.caption("Every card is scanned and graded, fakes and customs included. These are warning signs, not proof.")
        a, b = st.columns(2)
        if a.button("Confirm for community", help="Teaches the app this card so everyone's next scan is recognised", key=f"cf_{key}"):
            card = _record(x, scan, grade, auth)["card"]
            get_store().add_card(card, f["phash"], vision.thumbnail_b64(f["card"], 140), x["kind"])
            _remember(scan, x)
            st.toast("Added to the community catalog")
        with b.popover("Report as fake"):
            why = st.text_area("What gives it away?", key=f"why_{key}")
            if st.button("Submit report", key=f"rf_{key}"):
                card = _record(x, scan, grade, auth)["card"]
                get_store().add_card(card, f["phash"], vision.thumbnail_b64(f["card"], 140), "report", is_fake=True, fake_reasons=why[:1000])
                st.toast("Reported. Look-alikes will be flagged.")
        if scan["parsed"]["raw_text"]:
            st.caption("Text read: " + scan["parsed"]["raw_text"].replace("\n", " · ")[:300])


def _autograph_panel(scan: dict, x: dict):
    _, variant, name, _, _ = _card_facts(x)
    signed = bool(re.search(r"\bauto(graph)?s?\b|signature|signed", f"{variant} {name}", re.I))
    ck = f"_auto_{signed}"
    if ck not in scan:
        back = scan.get("back") or {}
        back_text = " ".join(t for t, *_ in back.get("lines", [])) if back else ""
        scan[ck] = autograph.check(scan["front"]["card"], scan["parsed"].get("raw_text", ""), back_text, "Autograph" if signed else "")
    a = scan[ck]
    if not (a["found"] or a["certified"] or signed):
        return
    st.markdown("**Autograph**" + (f" · {a['kind']}" if a["kind"] else "") + (f" · signature grade estimate **{a['auto_grade']}**" if a["auto_grade"] else ""))
    if a["box"]:
        from PIL import ImageDraw
        im = scan["front"]["card"].copy()
        bx, by, bw, bh = a["box"]
        ImageDraw.Draw(im).rectangle([bx - 6, by - 6, bx + bw + 6, by + bh + 6], outline=(255, 106, 51), width=4)
        st.image(im.crop((0, max(0, by - 80), im.width, min(im.height, by + bh + 80))), width="stretch")
    for n in a["notes"]:
        st.caption(n)
    st.info(a["verify"])


def _worst_of(text: str) -> float | None:
    """'52/48 · 55/45' -> 55 (the larger side of the worse split)."""
    nums = [int(n) for n in re.findall(r"(\d+)\s*/\s*\d+", text or "")]
    return float(max(nums)) if nums else None


def _inspection_panel(scan: dict, x: dict, key: str):
    fi = _inspection(scan, x)
    bi = (scan.get("back") or {}).get("inspect")
    auto = _auto_subs(scan, x)
    st.markdown("**Condition inspection** (automatic)")
    if not scan["front"].get("found") and not st.session_state.get(f"_cenlines_cen_{scan['id']}"):
        st.warning("Couldn't find the card's edges clearly (busy background, hands, or a case). Drag the blue lines onto "
                   "the card's edges in the centering tool above and the inspection will re-check the card.")
    for note in fi.photo_notes + (bi.photo_notes if bi else []):
        st.warning(note)
    m = st.columns(3)
    for i, k in enumerate(("corners", "edges", "surface")):
        m[i].metric(k.title(), f"{auto[k]:g}", help="Automatic subgrade from the photo (10 = no defects found)")
    finds = fi.findings + (bi.findings if bi else [])
    if finds:
        for fd in sorted(finds, key=lambda z: -z.severity)[:10]:
            icon = "🔴" if fd.severity >= 0.6 else "🟠" if fd.severity >= 0.25 else "🟡"
            st.markdown(f"{icon} **{esc(fd.where)}**: {esc(fd.what)}" + (" *(possible)*" if fd.sure == "possible" else ""))
    else:
        st.caption("No corner whitening, edge chips, scratches, stains or creases found in this photo.")
    views = dict(fi.views)
    if bi:
        views.update({f"Back · {k}": v for k, v in bi.views.items()})
    vk = st.segmented_control("Inspection view", list(views), default="Defect map", key=f"view_{key}", label_visibility="collapsed")
    if vk:
        st.image(views[vk], width="stretch")
        if vk.endswith("Defect map"):
            st.caption(condition.LEGEND)
    with st.popover("Adjust the condition yourself"):
        st.caption("The automatic answers are pre-selected. Change any that look wrong after checking the zoomed views.")
        opts = list(grading.CONDITION_OPTIONS)
        for k, lab in (("c", "corners"), ("e", "edges"), ("s", "surface")):
            default = condition.subgrade_to_option(auto[lab])
            st.selectbox(lab.title(), opts, index=opts.index(default), key=f"k_{k}_{key}", help=grading.CONDITION_HELP[lab])


def _tray():
    tray = st.session_state.get("tray", [])
    if not tray:
        return
    total = sum((t["price"] or 0) for t in tray)
    with st.container(border=True):
        a, b = st.columns([3, 1])
        a.markdown(f"**This session:** {len(tray)} card{'s' if len(tray) != 1 else ''} added · {money(total)}")
        if b.button("Clear", key="tray_clear"):
            st.session_state.tray = []
            st.rerun()
        for t in tray[-5:][::-1]:
            st.caption(f"{t['title']} · {money(t['price'])}")
