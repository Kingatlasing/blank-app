"""Collection + Wishlist grids grouped by brand / type / category / value."""
from __future__ import annotations

import json

import streamlit as st

from ui.common import (VERDICTS, collection, current_value, esc, grade_color, money, need_code, open_card, rarity_pill,
                       remove_from_collection, tile)


def page():
    _grid_page("collection", "Collection")


def wishlist_page():
    _grid_page("wishlist", "Wishlist")


def _grid_page(which: str, title: str):
    st.markdown(f"### {title}")
    if need_code():
        return
    items = [r for r in collection() if r.get("list", "collection") == which]
    total = sum(current_value(r) for r in items)
    m = st.columns(3)
    m[0].metric("Cards", len(items))
    m[1].metric("Value" if which == "collection" else "Cost to complete", money(total))
    m[2].metric("Top card", money(max((current_value(r) for r in items), default=0) or None))
    if not items:
        st.info("Nothing here yet. " + ("Scan a card or add one from Explore." if which == "collection" else "Tap ♡ Wishlist on any card page."))
        return
    group = st.segmented_control("Group by", ["Brand", "Type", "Category", "Most valuable"], default="Most valuable", key=f"grp_{which}") or "Most valuable"
    q = st.text_input("Search", placeholder="Name, set, parallel…", key=f"q_{which}", label_visibility="collapsed").lower().strip()
    if q:
        items = [r for r in items if q in json.dumps(r.get("card", {})).lower()]
    if group == "Most valuable":
        _grid(sorted(items, key=current_value, reverse=True), which)
        return
    field = {"Brand": "brand", "Type": "card_type", "Category": "game"}[group]
    groups: dict[str, list] = {}
    for r in items:
        groups.setdefault((r.get("card", {}).get(field) or "Other").strip() or "Other", []).append(r)
    for name, rs in sorted(groups.items(), key=lambda kv: -sum(current_value(r) for r in kv[1])):
        st.markdown(f"#### {esc(name)} <span class='muted' style='font-size:14px'>{len(rs)} · {money(sum(current_value(r) for r in rs))}</span>", unsafe_allow_html=True)
        _grid(sorted(rs, key=current_value, reverse=True), which)


def _grid(recs: list[dict], which: str):
    cols = st.columns(3)
    for i, r in enumerate(recs):
        k = r.get("card", {})
        g = r.get("grade") or {}
        pills = rarity_pill(r.get("print_run"))
        if g.get("psa") is not None:
            pills += f"<span class='pill' style='color:{grade_color(g.get('psa'))}'>PSA {esc(g.get('psa'))} est.</span>"
        elif g.get("label"):
            pills += f"<span class='pill green'>{esc(g['label'])}</span>"
        with cols[i % 3]:
            st.markdown(tile(k.get("name", ""), f"{k.get('set','')} · {k.get('rarity') or k.get('variant') or ''}", money(current_value(r) or None), r.get("thumb"), pills), unsafe_allow_html=True)
            with st.popover("More", width="stretch"):
                key = (r.get("match") or {}).get("catalog_key")
                if key and st.button("Open card page", key=f"o_{r['id']}"):
                    open_card(key)
                au = r.get("authenticity") or {}
                if au.get("verdict") and au["verdict"] != "not_checked":
                    st.markdown(f"**Authenticity:** {VERDICTS.get(au['verdict'], VERDICTS['not_checked'])[2]}")
                if (g.get("centering") or {}).get("front"):
                    st.caption(f"Centering {g['centering']['front']}")
                if st.button("Remove", key=f"rm_{r['id']}"):
                    remove_from_collection(r["id"])
                    st.rerun()
