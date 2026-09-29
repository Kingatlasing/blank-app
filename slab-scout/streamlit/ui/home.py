"""Portfolio home: total value, value chart, top cards, recent adds, biggest sets."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import catalog
from ui.common import card_image, record_image, collection, current_value, esc, money, need_code, open_card, portfolio_history, rarity_pill, tile


def page():
    st.markdown("### Portfolio")
    if need_code():
        _discover()
        return
    items = [r for r in collection() if r.get("list", "collection") == "collection"]
    total = sum(current_value(r) for r in items)
    hist = portfolio_history(total)
    prev = hist[-2]["value"] if len(hist) >= 2 else None
    change = total - prev if prev is not None else 0.0
    pct = (change / prev * 100) if prev else 0.0
    cls = "up" if change >= 0 else "down"
    arrow = "▲" if change >= 0 else "▼"
    st.markdown(
        f'<div class="hero"><div class="lbl">Collection value</div><div class="big">{money(total)}</div>'
        + (f'<div class="{cls}">{arrow} {money(abs(change))} ({pct:+.1f}%) since {esc(hist[-2]["day"])}</div>' if prev is not None else '<div class="muted">Tracking starts today</div>')
        + f'<div class="muted">{len(items)} card{"" if len(items) == 1 else "s"}</div></div>',
        unsafe_allow_html=True,
    )
    if len(hist) >= 2:
        df = pd.DataFrame(hist).rename(columns={"day": "Day", "value": "Value"}).set_index("Day")
        st.area_chart(df, height=180, color="#FF6A33")
    else:
        st.caption("Your value chart fills in as prices update day to day.")

    c1, c2 = st.columns(2)
    if c1.button("Scan a card", type="primary", width="stretch"):
        st.switch_page(st.session_state.pages["scan"])
    if c2.button("Explore sets", width="stretch"):
        st.switch_page(st.session_state.pages["explore"])

    if items:
        st.markdown("#### Most valuable")
        top = sorted(items, key=current_value, reverse=True)[:6]
        _grid(top, "top")
        st.markdown("#### Recently added")
        recent = sorted(items, key=lambda r: r.get("added_at", ""), reverse=True)[:6]
        _grid(recent, "new")
    else:
        st.info("Your collection is empty. Scan a card or add one from Explore to start tracking its value.")
    _discover()


def _grid(recs: list[dict], tag: str):
    cols = st.columns(3)
    for i, r in enumerate(recs):
        k = r.get("card", {})
        with cols[i % 3]:
            st.markdown(tile(k.get("name", ""), f"{k.get('set','')} {('#' + k['number']) if k.get('number') else ''}",
                             money(current_value(r) or None), r.get("thumb"), rarity_pill(r.get("print_run")), record_image(r)), unsafe_allow_html=True)
            key = (r.get("match") or {}).get("catalog_key")
            if key and st.button("View", key=f"h_{tag}_{r['id']}", width="stretch"):
                open_card(key)


def _discover():
    cards = [c for c in catalog.cards() if c.raw]
    if not cards:
        return
    st.markdown("#### Top chase cards right now")
    top = sorted(cards, key=lambda c: c.raw, reverse=True)[:6]
    cols = st.columns(3)
    sets = catalog.sets()
    for i, c in enumerate(top):
        with cols[i % 3]:
            st.markdown(tile(c.name, f"{sets.get(c.set_id, {}).get('name','')} · {c.variant or 'Base'}", money(c.raw), None, rarity_pill(c.print_run), card_image(c)), unsafe_allow_html=True)
            if st.button("View", key=f"d_{i}", width="stretch"):
                open_card(c.key)
