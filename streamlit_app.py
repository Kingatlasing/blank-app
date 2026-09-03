import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Sideline Rips", page_icon="🏆", layout="wide")

# Streamlit adds default padding/whitespace around the page; strip it so the
# embedded app fills the frame like a real full-screen web app.
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
DATA_PATH = ROOT / "data" / "cards.json"


@st.cache_data
def load_html() -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")

    cards = []
    if DATA_PATH.exists():
        try:
            cards = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cards = []

    data_js = json.dumps(cards)
    html = html.replace("/*__CARD_DATA__*/ [] /*__END_CARD_DATA__*/", data_js)
    return html


components.html(load_html(), height=860, scrolling=True)
