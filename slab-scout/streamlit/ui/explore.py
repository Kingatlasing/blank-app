"""Explore: search every card, browse brands and sets, set pages with checklist + completion."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import catalog
from ui.common import card_image, card_price, price_label, price_mode, collection, esc, money, need_code, open_card, open_set, rarity_pill, tile


def page():
    st.markdown("### Explore")
    sets = catalog.sets()
    if not sets:
        st.warning("The card database isn't installed. Copy data/catalog next to app.py (see README).")
        return
    q = st.text_input("Search cards and sets", placeholder="e.g. Stitch black gold, Demidov high gloss, CDT-G-171, Elvis relic", label_visibility="collapsed")
    if q.strip():
        hits = catalog.search(q, limit=45)
        st.caption(f"{len(hits)} match{'es' if len(hits) != 1 else ''}" + (" (showing top 45)" if len(hits) == 45 else ""))
        _card_grid(hits)
        return

    brands = sorted({s["brand"] for s in sets.values()})
    brand = st.pills("Brand", ["All"] + brands, default="All", label_visibility="collapsed") or "All"
    cats = sorted({s["category"] for s in sets.values() if brand in ("All", s["brand"])})
    cat = st.pills("Category", ["All"] + cats, default="All", label_visibility="collapsed") or "All"
    shown = [s for s in sets.values() if brand in ("All", s["brand"]) and cat in ("All", s["category"])]
    years = sorted({s.get("year") or "" for s in shown if s.get("year")}, reverse=True)
    f1, f2 = st.columns([1, 2])
    year = f1.selectbox("Year", ["All years"] + years, label_visibility="collapsed")
    sq = f2.text_input("Find a set", placeholder="Find a set, e.g. 1991 Upper Deck, SP Authentic", label_visibility="collapsed")
    if year != "All years":
        shown = [s for s in shown if s.get("year") == year]
    if sq.strip():
        words = sq.lower().split()
        shown = [s for s in shown if all(w in f"{s['name']} {s.get('year','')} {s['brand']}".lower() for w in words)]
    shown.sort(key=lambda s: (-(int(s.get("year") or 0)), -s["cards"]))
    per = 40
    n_pages = max(1, (len(shown) + per - 1) // per)
    st.caption(f"{len(shown):,} sets with card lists")
    pg = st.number_input("Page", 1, n_pages, 1, key="explore_pg") if n_pages > 1 else 1
    owned = _owned_keys()
    for s in shown[(pg - 1) * per: pg * per]:
        have = sum(1 for k in owned if k.startswith(s["id"] + "|"))
        chase = next((t for t in sorted(s["tiers"], key=lambda t: t["print_run"] or 10**6) if t.get("print_run")), None)
        with st.container(border=True):
            a, b = st.columns([4, 1])
            a.markdown(f"**{esc(s['name'])}**  \n<span class='pill'>{esc(s['brand'])}</span><span class='pill'>{esc(s['category'])}</span>"
                       f"<span class='pill'>{s['cards']:,} cards</span>"
                       + (f"<span class='pill gold'>rarest {('1 of 1' if chase['print_run']==1 else '/'+str(chase['print_run']))}</span>" if chase else "")
                       + (f"<span class='pill green'>you own {have}</span>" if have else ""), unsafe_allow_html=True)
            if b.button("Open", key=f"set_{s['id']}", width="stretch"):
                open_set(s["id"])
    _directory()


def _directory():
    """Every product the checklist sites list, with a cover photo and a link to its checklist."""
    idx = catalog.set_index()
    if not idx:
        return
    with st.expander(f"Set directory: {len(idx):,} more products from Topps, Upper Deck, Checklist Insider and BaseballCardPedia"):
        st.caption("These are listed by the checklist sites. Card-by-card prices are only in the sets above; open a link for the full checklist.")
        q = st.text_input("Search the directory", placeholder="e.g. 2026 Bowman Chrome, Allen & Ginter, 1989 Fleer", key="dir_q", label_visibility="collapsed")
        view = idx
        if q.strip():
            words = q.lower().split()
            view = [i for i in idx if all(w in f"{i['name']} {i.get('year','')} {i.get('sport','')} {i.get('brand','')}".lower() for w in words)]
        view = sorted(view, key=lambda i: (-(int(i["year"]) if str(i.get("year", "")).isdigit() else 0), i["name"]))[:300]
        df = pd.DataFrame([{"Photo": i.get("img") or None, "Product": i["name"], "Year": i.get("year", ""), "Sport": i.get("sport", ""),
                            "Source": i.get("source", ""), "Checklist": i.get("url", "")} for i in view])
        if len(df):
            st.dataframe(df, hide_index=True, width="stretch", column_config={
                "Photo": st.column_config.ImageColumn(width="small"),
                "Checklist": st.column_config.LinkColumn(display_text="Open ↗")})
            st.caption(f"Showing {len(df)} of {len(idx):,}" if len(df) == 300 else f"{len(df)} products")


def _owned_keys() -> set[str]:
    try:
        return {(r.get("match") or {}).get("catalog_key", "") for r in collection() if r.get("list", "collection") == "collection"}
    except Exception:
        return set()


def _card_grid(cards: list, cols_n: int = 3):
    sets = catalog.sets()
    cols = st.columns(cols_n)
    for i, c in enumerate(cards):
        with cols[i % cols_n]:
            st.markdown(tile(c.name, f"{sets.get(c.set_id, {}).get('name','')} · {c.variant or 'Base'} · #{c.number}", price_label(c), None, rarity_pill(c.print_run), card_image(c)), unsafe_allow_html=True)
            if st.button("View", key=f"g_{c.key}", width="stretch"):
                open_card(c.key)


def set_page():
    sid = st.session_state.get("set_id")
    s = catalog.sets().get(sid or "")
    if not s:
        st.info("Pick a set in Explore.")
        if st.button("Go to Explore"):
            st.switch_page(st.session_state.pages["explore"])
        return
    if st.button("← Explore"):
        st.switch_page(st.session_state.pages["explore"])
    st.markdown(f"### {esc(s['name'])}")
    st.markdown(f"<span class='pill'>{esc(s['brand'])}</span><span class='pill'>{esc(s['category'])}</span><span class='pill'>{s['cards']:,} cards</span>"
                + (f"<span class='pill'>prices {esc(s['prices_as_of'])}</span>" if s.get("prices_as_of") else ""), unsafe_allow_html=True)
    box = s.get("box") or {}
    if box.get("note") or box.get("packs_per_box"):
        st.caption(" · ".join(x for x in [f"{box['packs_per_box']} packs × {box['cards_per_pack']} cards per box" if box.get("packs_per_box") else "", box.get("note", "")] if x))
    if s.get("notes"):
        st.caption(s["notes"])
    if s.get("image"):
        st.image(s["image"], caption="Sample card from this set", width=220)

    cards = catalog.set_cards(s["id"])
    owned = _owned_keys()
    have = sum(1 for c in cards if c.key in owned)
    st.progress(have / max(1, len(cards)), text=f"You own {have} of {len(cards):,} ({have / max(1, len(cards)) * 100:.1f}%)")

    st.markdown("#### Rarity ladder")
    rows = []
    for t in s["tiers"]:
        odds = catalog.odds_text(t, s)
        if t.get("ebay_median"):
            val = f"{money(t['ebay_median'])} · eBay ({t['ebay_n']} sold)"
        elif t.get("median_raw"):
            val = money(t["median_raw"])
        elif t.get("estimate"):
            val = t["estimate"] + " (est.)"
        else:
            val = "—"
        rows.append({"Parallel": t["name"], "Print run": ("1 of 1" if t.get("print_run") == 1 else f"/{t['print_run']}" if t.get("print_run") else "—"),
                     "Typical value": val, "Pull odds": odds or "—", "Cards": t["count"],
                     "Top sale": money(t.get("top_raw")) if t.get("top_raw") else "—"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if s.get("estimate_source"):
        st.caption(f"(est.) = {s['estimate_source']}")

    st.markdown("#### Checklist")
    c1, c2, c3 = st.columns([2, 1, 1])
    q = c1.text_input("Filter", placeholder="Name or number", label_visibility="collapsed")
    tier_names = ["All parallels"] + [t["name"] for t in s["tiers"]]
    tsel = c2.selectbox("Parallel", tier_names, label_visibility="collapsed")
    show = c3.selectbox("Show", ["All", "Owned", "Missing", "Most valuable"], label_visibility="collapsed")
    view = cards
    if q:
        ql = q.lower()
        view = [c for c in view if ql in c.name.lower() or ql in c.number.lower()]
    if tsel != "All parallels":
        view = [c for c in view if (c.variant or "Base") == tsel]
    if show == "Owned":
        view = [c for c in view if c.key in owned]
    elif show == "Missing":
        view = [c for c in view if c.key not in owned]
    elif show == "Most valuable":
        view = sorted(view, key=lambda c: -(card_price(c)[0] or 0))
    st.caption(f"{len(view):,} cards")
    df = pd.DataFrame([{"✓": "✓" if c.key in owned else "", "Card": c.name, "Parallel": c.variant or "Base", "Raw": c.raw,
                        "#": c.number, "Print run": (f"/{c.print_run}" if c.print_run else ""), "PSA 9": c.psa9, "PSA 10": c.psa10} for c in view[:500]])
    if len(df) and price_mode() != "Raw":  # graded view: graded price first
        col = "PSA 10" if price_mode().startswith("PSA 10") else "PSA 9"
        df = df[["✓", "Card", "Parallel", col] + [k for k in df.columns if k not in ("✓", "Card", "Parallel", col)]]
    if len(df):
        ev = st.dataframe(df, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                          column_config={"Raw": st.column_config.NumberColumn(format="$%.2f"), "PSA 9": st.column_config.NumberColumn(format="$%.2f"),
                                         "PSA 10": st.column_config.NumberColumn("PSA 10 (Gem)", format="$%.2f")})
        sel = (ev.selection.rows if ev and ev.selection else [])
        if sel:
            open_card(view[sel[0]].key)
        if len(view) > 500:
            st.caption("Showing the first 500. Use the filter to narrow it down.")
    st.link_button("Full price guide ↗", s["source_url"])
