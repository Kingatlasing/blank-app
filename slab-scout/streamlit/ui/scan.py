"""Scan: snap -> instant match with price -> one-tap add. Bulk mode keeps the camera ready for the next card."""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime

import streamlit as st

from core import ai, catalog, databases, grading, ocr, pipeline, vision
from ui.common import (VERDICTS, add_to_collection, esc, get_store, grade_color, money, need_code, open_card, rarity_pill,
                       record_from_catalog)

GAMES = ["Auto", "Pokémon", "Yu-Gi-Oh!", "Magic: The Gathering", "Lorcana", "One Piece", "Sports", "Kakawow / Disney / Marvel",
         "Non-sport (history, music…)", "Other"]


def _analyze(front: bytes, back: bytes | None, game: str) -> dict:
    f = pipeline.analyze_photo(front)
    b = pipeline.analyze_photo(back) if back else None
    parsed = ocr.parse(f["lines"], "" if game in ("Auto", "Sports", "Kakawow / Disney / Marvel", "Non-sport (history, music…)", "Other") else game)
    store = get_store()
    comm = pipeline.community_matches(store, f["phash"])
    cands: list[dict] = []

    # 1. Exact code / name matches in the card database (Kakawow codes pin the exact parallel)
    for c in catalog.match_text(parsed["raw_text"], parsed.get("name", ""), parsed.get("number", ""))[:8]:
        cands.append({"kind": "catalog", "card": c, "score": 100 if catalog.CODE_RE.search(parsed["raw_text"].upper()) else 60})
    # 2. Community fingerprint matches (cards people confirmed before)
    for m in comm:
        if not m.get("is_fake"):
            cands.append({"kind": "community", "row": m, "score": 90 - m["distance"] * 3})
    # 3. Free TCG databases
    g = parsed.get("game") or ""
    if (game in ("Auto", "Pokémon", "Yu-Gi-Oh!", "Magic: The Gathering", "Lorcana")) and (parsed.get("name") or parsed.get("number")):
        dbc = databases.search_all({"name": parsed.get("name", ""), "number": parsed.get("number", ""), "set_code": parsed.get("set_code", "")},
                                   "" if game == "Auto" else game)[:6]
        pipeline.official_similarity(f["card"], dbc)
        for c in dbc:
            d = c.get("official_distance")
            cands.append({"kind": "tcgdb", "c": c, "score": 80 - (d or 20)})
    cands.sort(key=lambda x: -x["score"])
    return {"front": f, "back": b, "parsed": parsed, "cands": cands, "fakes": [c for c in comm if c.get("is_fake") and c["distance"] <= pipeline.MATCH_STRONG],
            "id": hashlib.sha1(front).hexdigest()[:12], "ai": None}


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
        return f"{r['name']} [{r.get('rarity') or ''}] #{r.get('number') or ''}"
    if x["kind"] == "tcgdb":
        return f"{x['c']['name']} [{x['c']['rarity']}] #{x['c']['number']}"
    return f"{x['c'].get('name','')} [{x['c'].get('rarity','')}]"


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
    left, right = st.columns([1, 1.4])
    left.image(f["card"], width="stretch")
    with right:
        if not cands:
            st.markdown("**No match yet.**")
            st.caption("Type the name below, turn on the free AI boost in the menu, or confirm it for the community so the next scan is recognised.")
            q = st.text_input("Search the database", key=f"q_{scan['id']}")
            if q:
                for c in catalog.search(q, limit=6):
                    cands.append({"kind": "catalog", "card": c, "score": 50})
                if cands:
                    st.rerun()
            return
        i = min(s.get("pick", 0), len(cands) - 1)
        x = cands[i]
        raw, p10 = _price(x)
        title = _title(x)
        pr = x["card"].print_run if x["kind"] == "catalog" else None
        src = {"catalog": "card database", "community": "community catalog", "tcgdb": "official database", "ai": "AI"}[x["kind"]]
        st.markdown(f"<div class='hero'><div class='lbl'>Best match · {src}</div><div style='font-size:20px;font-weight:800'>{esc(title)}</div>"
                    f"<div>{rarity_pill(pr)}</div><div class='big' style='color:#E6B94B'>{money(raw)}</div>"
                    f"<div class='muted'>raw{(' · PSA 10 ' + money(p10)) if p10 else ''}</div></div>", unsafe_allow_html=True)
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
            s.setdefault("tray", []).append({"title": title, "price": raw})
            st.toast(f"Added {title}")
            if s.get("bulk"):
                s.scan_n = s.get("scan_n", 0) + 1
                s.pop("scan", None)
                st.rerun()
        if b[1].button("♡ Wishlist", width="stretch", disabled=disabled):
            add_to_collection(_record(x, scan, grade, auth), wishlist=True)
            st.toast("Added to wishlist")
        if x["kind"] == "catalog" and st.button("Open card page", width="stretch"):
            open_card(x["card"].key)
        if len(cands) > 1:
            labels = [f"{_title(c)} · {money(_price(c)[0])}" for c in cands[:10]]
            pick = st.selectbox("Not right? Pick another match", range(len(labels)), index=i, format_func=lambda k: labels[k])
            if pick != i:
                s.pick = pick
                st.rerun()
    _details(scan, x, grade, auth)


def _grade_auth(scan: dict, x: dict):
    f = scan["front"]
    key = scan["id"]
    cen = f["centering"] or vision.Centering(40, 40, 40, 40)
    L = st.session_state.get(f"cl_{key}", cen.left)
    R = st.session_state.get(f"cr_{key}", cen.right)
    T = st.session_state.get(f"ct_{key}", cen.top)
    B = st.session_state.get(f"cb_{key}", cen.bottom)
    front_c = vision.Centering(L, R, T, B)
    back_c = scan["back"]["centering"] if scan["back"] else None
    corners = st.session_state.get(f"k_c_{key}", "One tiny flaw")
    edges = st.session_state.get(f"k_e_{key}", "One tiny flaw")
    surface = st.session_state.get(f"k_s_{key}", "One tiny flaw")
    grade = grading.estimate(front_c.worst(), back_c.worst() if back_c else None, corners, edges, surface)
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
        cc = st.columns([1, 1.3])
        cen = f["centering"] or vision.Centering(40, 40, 40, 40)
        with cc[1]:
            st.slider("Left border", 1, 200, cen.left, key=f"cl_{key}")
            st.slider("Right border", 1, 200, cen.right, key=f"cr_{key}")
            st.slider("Top border", 1, 250, cen.top, key=f"ct_{key}")
            st.slider("Bottom border", 1, 250, cen.bottom, key=f"cb_{key}")
        cc[0].image(vision.draw_centering(f["card"], vision.Centering(st.session_state[f"cl_{key}"], st.session_state[f"cr_{key}"], st.session_state[f"ct_{key}"], st.session_state[f"cb_{key}"])), width="stretch")
        opts = list(grading.CONDITION_OPTIONS)
        k = st.columns(3)
        k[0].selectbox("Corners", opts, index=1, key=f"k_c_{key}", help=grading.CONDITION_HELP["corners"])
        k[1].selectbox("Edges", opts, index=1, key=f"k_e_{key}", help=grading.CONDITION_HELP["edges"])
        k[2].selectbox("Surface", opts, index=1, key=f"k_s_{key}", help=grading.CONDITION_HELP["surface"])
        reasons = "".join(f"<li>{esc(r)}</li>" for r in auth["reasons"]) or "<li>Pick a database match or use the AI boost to compare against the real card.</li>"
        st.markdown(f"<div class='verdict' style='background:{bg};border:1px solid {fg}'><b style='color:{fg}'>{label}</b><ul style='margin:6px 0 0 0'>{reasons}</ul></div>", unsafe_allow_html=True)
        st.caption("Every card is scanned and graded, fakes and customs included. These are warning signs, not proof.")
        a, b = st.columns(2)
        if a.button("Confirm for community", help="Teaches the app this card so everyone's next scan is recognised", key=f"cf_{key}"):
            card = _record(x, scan, grade, auth)["card"]
            get_store().add_card(card, f["phash"], vision.thumbnail_b64(f["card"], 140), x["kind"])
            st.toast("Added to the community catalog")
        with b.popover("Report as fake"):
            why = st.text_area("What gives it away?", key=f"why_{key}")
            if st.button("Submit report", key=f"rf_{key}"):
                card = _record(x, scan, grade, auth)["card"]
                get_store().add_card(card, f["phash"], vision.thumbnail_b64(f["card"], 140), "report", is_fake=True, fake_reasons=why[:1000])
                st.toast("Reported. Look-alikes will be flagged.")
        if scan["parsed"]["raw_text"]:
            st.caption("Text read: " + scan["parsed"]["raw_text"].replace("\n", " · ")[:300])


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
