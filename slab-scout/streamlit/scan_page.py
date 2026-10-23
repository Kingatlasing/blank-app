"""Page shown at the scan service's address: the Slab Scout phone app (browser build, /web) full screen.
The phone app's API calls go to /api/scan and /api/ocr on this same address."""
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Slab Scout", page_icon="🃏", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """<style>
    header, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {display: none !important;}
    .block-container {padding: 0 !important; max-width: 100% !important;}
    [data-testid="stAppViewContainer"], .stApp {background: #0b0d10;}
    iframe {display: block; border: 0; height: 100vh !important; height: 100dvh !important;}
    </style>""",
    unsafe_allow_html=True,
)
# relative address: resolves next to this page, wherever Streamlit Cloud serves it from
components.iframe("web/index.html", height=900, scrolling=False)
