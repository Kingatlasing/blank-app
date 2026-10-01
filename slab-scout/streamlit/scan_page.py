"""Page shown at the scan service's address (the phone app talks to /api/scan and /api/ocr)."""
import streamlit as st

st.set_page_config(page_title="Slab Scout scan service", page_icon="🃏")
st.title("Slab Scout scan service")
st.success("Running. Paste this page's address into the Slab Scout app: Settings → Scan server.")
st.caption("The phone app sends card photos to /api/scan (identify + grade) and /api/ocr (read the text in English, "
           "Japanese and Korean). Photos are processed in memory and never stored.")
