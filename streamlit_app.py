"""Slab Scout phone app, running in the browser for testing.

static/ holds the Expo phone app (slab-scout branch, slab-scout/app) exported for the web. Streamlit serves it
at /app/static/index.html. It uses the same card database (the repo's catalog-data branch) and, when the same
Supabase settings are entered in its Settings, the same shared community catalog and vault as the other apps.
"""
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Slab Scout · phone app preview", page_icon="🃏", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """<style>
    header, footer, #MainMenu {visibility: hidden;}
    .block-container {padding: 0.6rem 0.6rem 0 0.6rem; max-width: 100%;}
    a.open {display:block;text-align:center;background:#D4F25A;color:#0A0B10 !important;font-weight:800;
            padding:12px;border-radius:14px;text-decoration:none;margin-bottom:10px}
    </style>""",
    unsafe_allow_html=True,
)
st.markdown('<a class="open" href="./app/static/index.html" target="_blank">Open the app full screen ↗</a>', unsafe_allow_html=True)
st.caption("Phone app preview. Works best full screen on a phone. The camera scanner needs the browser's camera "
           "permission; reading card text and some phone-only features need Expo Go or the installed app.")
components.iframe("./app/static/index.html", height=860, scrolling=False)
