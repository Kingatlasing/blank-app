"""Card page: price by grade, every parallel's price, print run, pull odds, recent sales, add to collection."""
from __future__ import annotations

from urllib.parse import quote_plus

import streamlit as st

from core import catalog, community
from ui.common import (add_to_collection, catalog_card, collection, esc, get_store, money, need_code, open_card, open_set,
                       rarity_pill, record_from_catalog)


def page():
    key = st.session_state.get("card_key")
    c = catalog_card(key) if key else None
    if not c:
        st.info("Pick a card from Explore, search, or your collection.")
        return
    s = catalog.sets().get(c.set_id, {})
    t = catalog.tier(c) or {}
    nav = st.columns([1, 1, 3])
    if nav[0].button("← Back"):
        st.switch_page(st.session_state.pages["explore"])
    if nav[1].button("Set"):
        open_set(c.set_id)

    img, other = catalog.image_url(c, 1600)
    if img:
        pic, info = st.columns([1, 1.6])
        pic.image(img, width="stretch", caption="Photo of another parallel of this card" if other else None)
        info_ctx = info
    else:
        info_ctx = st.container()
    info_ctx.markdown(f"### {esc(c.name)}")
    info_ctx.markdown(f"{esc(s.get('name',''))} · #{esc(c.number)}  \n<span class='pill gold'>{esc(c.variant or 'Base')}</span>{rarity_pill(c.print_run)}"
                f"<span class='pill'>{esc(s.get('brand',''))}</span>", unsafe_allow_html=True)

    m = st.columns(3)
    _v, _est = catalog.value(c)
    m[0].metric("Raw" + (" (typical)" if _est else ""), money(_v), help="No sale of this exact card yet, so this is the typical sold price for its parallel." if _est else None)
    m[1].metric("PSA 9", money(c.psa9))
    m[2].metric("PSA 10 (Gem Mint)", money(c.psa10))
    odds = catalog.odds_text(t, s)
    facts = []
    if c.print_run:
        facts.append("Only 1 exists" if c.print_run == 1 else f"Only {c.print_run} copies exist")
    if odds:
        facts.append(f"Pull odds: {odds}")
    if t.get("median_raw"):
        facts.append(f"Typical {c.variant or 'Base'} in this set sells for {money(t['median_raw'])}")
    if facts:
        st.markdown(" · ".join(esc(f) for f in facts))
    if s.get("prices_as_of"):
        st.caption(f"Prices from {s.get('source')} sold listings, updated {s['prices_as_of']}.")

    # ---------- add ----------
    owned = [r for r in collection() if (r.get("match") or {}).get("catalog_key") == c.key] if not need_code() else []
    with st.container(border=True):
        a, b, g = st.columns([1.2, 1, 1])
        grade = g.selectbox("Condition", ["Raw", "PSA 10", "PSA 9", "PSA 8", "TAG 10", "TAG 9", "BGS 9.5", "CGC 10", "Other graded"], label_visibility="collapsed")
        if a.button("Add to collection", type="primary", width="stretch", disabled=not st.session_state.get("vault_code") and get_store().shared):
            rec = record_from_catalog(c)
            if grade != "Raw":
                rec["grade"] = {"method": "owner", "label": grade}
                if grade == "PSA 10" and c.psa10:
                    rec["pricing"]["raw"]["mid"] = c.psa10
                elif grade == "PSA 9" and c.psa9:
                    rec["pricing"]["raw"]["mid"] = c.psa9
            add_to_collection(rec)
            st.toast(f"Added {c.name} to your collection")
        if b.button("♡ Wishlist", width="stretch", disabled=not st.session_state.get("vault_code") and get_store().shared):
            add_to_collection(record_from_catalog(c), wishlist=True)
            st.toast("Added to wishlist")
        if owned:
            st.caption(f"You own {len(owned)} of this card.")

    # ---------- parallel ladder ----------
    sib = sorted(catalog.siblings(c), key=lambda x: (x.print_run or 10**6), reverse=True)
    if len(sib) > 1:
        st.markdown("#### Every version of this card")
        rows = "".join(
            f"<tr class='{'me' if x.key == c.key else ''}'><td>{esc(x.variant or 'Base')}</td><td>{'1/1' if x.print_run == 1 else ('/' + str(x.print_run)) if x.print_run else '—'}</td>"
            f"<td>{money(x.raw)}</td><td>{money(x.psa10)}</td></tr>" for x in sib)
        st.markdown(f"<table class='ladder'><tr><th>Parallel</th><th>Print run</th><th>Raw</th><th>PSA 10</th></tr>{rows}</table>", unsafe_allow_html=True)
        names = [f"{x.variant or 'Base'} {('/' + str(x.print_run)) if x.print_run else ''}" for x in sib]
        pick = st.selectbox("Open another version", ["—"] + names, label_visibility="collapsed")
        if pick != "—":
            open_card(sib[names.index(pick)].key)

    # ---------- sales ----------
    st.markdown("#### Recent sales")
    comm = get_store().sales_for({"game": s.get("category", ""), "name": c.name, "set": s.get("name", ""), "number": c.number, "variant": c.variant})
    ebay = catalog.related_sales(c)
    if comm:
        st.caption("Added by the community")
        for x in comm[:8]:
            st.markdown(f"- **{money(x['price'])}** · {esc(x['grade'])} · {esc(x.get('sold_on') or '')}")
    if ebay:
        st.caption("eBay sold listings mentioning this card")
        for x in ebay:
            st.markdown(f"- **{money(x['p'])}** · {esc(x['d'])} · [{esc(x['t'][:80])}]({x['u']})")
    if not comm and not ebay:
        st.caption("No individual sales stored for this card yet. Check the live links below.")
    q = f"{s.get('year','')} {s.get('brand','')} {s.get('name','').split(' Checklist')[0]} {c.name} {c.variant} {c.number}".replace("  ", " ")
    l = st.columns(3)
    l[0].link_button("Price guide ↗", catalog.price_url(c), width="stretch")
    l[1].link_button("eBay sold ↗", f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(c.name + ' ' + (c.variant or '') + ' ' + c.number)}&LH_Sold=1&LH_Complete=1", width="stretch")
    l[2].link_button("Google ↗", f"https://www.google.com/search?q={quote_plus(q + ' sold price')}", width="stretch")

    with st.expander("Add a sale you saw"):
        with st.form(f"sale_{c.key}", clear_on_submit=True):
            x = st.columns(2)
            gsel = x[0].selectbox("Grade", ["Raw", "PSA 10", "PSA 9", "PSA 8", "TAG 10", "TAG 9", "BGS 9.5", "CGC 10", "Other"])
            price = x[1].number_input("Sold for ($)", min_value=0.0, step=1.0)
            url = st.text_input("Listing link (optional)")
            if st.form_submit_button("Add sale") and price > 0:
                get_store().add_sale({"game": s.get("category", ""), "name": c.name, "set": s.get("name", ""), "number": c.number, "variant": c.variant},
                                     gsel, float(price), "", url)
                st.success("Thanks! Added.")
