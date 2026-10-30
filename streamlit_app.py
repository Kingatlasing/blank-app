"""Launcher for the two Minecraft modeling tools in this repo.

Each tool is a page under `pages/`; Streamlit builds the sidebar nav itself.
The tools share no code — see docs/newcomer-guide.md for the layout.
"""

import streamlit as st

st.set_page_config(
    page_title="Minecraft modeling tools", page_icon="🧱", layout="wide"
)

st.title("🧱 Minecraft modeling tools")

st.markdown(
    """
Two separate tools live here. Pick one from the sidebar.

### 🧱 VoxelCraft
Describe an object or a building in plain words and get a blocky, Minecraft-style
voxel model back, built from procedural shapes. It can optionally research a real
reference photo and real dimensions online, or hand the design off to a local LLM.
Exports `.mcfunction`, JSON, and OBJ/MTL.

### ⛏️ Scale Model Designer
Build accurate, scaled block models of real landmarks — or anything you design
yourself — in a three.js editor with ~320 real Minecraft blocks. Computes real
measurements for a chosen scale ratio, models interiors, shows a layer-by-layer
blueprint, and exports `/fill` commands.

---

VoxelCraft *generates* a model from a prompt; the Designer lets *you* build one to a
real-world scale.
"""
)
