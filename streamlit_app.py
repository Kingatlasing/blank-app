"""Slab Scout, the trading card scanner (slab-scout/streamlit/app.py), as the repo's default Streamlit app.

Deploying this repo on share.streamlit.io with the default main file opens the scanner. The app itself lives in
slab-scout/streamlit; this file only puts that folder on the import path and runs it.
"""
import runpy
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent / "slab-scout" / "streamlit"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

runpy.run_path(str(APP_DIR / "app.py"), run_name="__main__")
