"""Slab Scout: scan, grade and value trading cards; track your collection like a portfolio.

Run locally:  streamlit run app.py
Deploy free:  share.streamlit.io (see README)
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Slab Scout", page_icon="🃏", layout="centered")

from ui import card, collection, common, explore, home, scan  # noqa: E402

st.markdown(common.CSS, unsafe_allow_html=True)
common.settings_sidebar()

pages = {
    "home": st.Page(home.page, title="Portfolio", icon=":material/show_chart:", default=True),
    "scan": st.Page(scan.page, title="Scan", icon=":material/photo_camera:", url_path="scan"),
    "explore": st.Page(explore.page, title="Explore", icon=":material/search:", url_path="explore"),
    "collection": st.Page(collection.page, title="Collection", icon=":material/style:", url_path="collection"),
    "wishlist": st.Page(collection.wishlist_page, title="Wishlist", icon=":material/favorite:", url_path="wishlist"),
    "set": st.Page(explore.set_page, title="Set", icon=":material/grid_view:", url_path="set"),
    "card": st.Page(card.page, title="Card", icon=":material/badge:", url_path="card"),
}
st.session_state.pages = pages
nav = st.navigation(
    {"": [pages["home"], pages["scan"], pages["explore"], pages["collection"], pages["wishlist"]], "Browse": [pages["set"], pages["card"]]},
    position="top",
)
nav.run()
