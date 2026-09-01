from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Lemonade Stand Tycoon", page_icon="🍋", layout="wide")

# Streamlit adds default padding/whitespace around the page; strip it so the
# embedded game fills the frame like a real full-screen web app.
st.markdown(
    """
    <style>
        .block-container {padding: 0 !important; max-width: 100% !important;}
        header[data-testid="stHeader"] {display:none;}
        iframe {border: none;}
    </style>
    """,
    unsafe_allow_html=True,
)

ROOT = Path(__file__).parent
TEMPLATE_PATH = ROOT / "app" / "index.html"


@st.cache_data
def load_html() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


components.html(load_html(), height=1300, scrolling=True)
