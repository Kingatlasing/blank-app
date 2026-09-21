# blank-app: a newcomer's guide

This repository holds two Minecraft modeling tools that run together as one
Streamlit app, plus several unrelated apps on their own branches.

## Start here

```bash
git clone https://github.com/Kingatlasing/blank-app.git
cd blank-app
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The launcher opens with both tools in the sidebar.

## The two tools

| Tool | Page | What it does | Guide |
|---|---|---|---|
| **VoxelCraft** | `pages/1_VoxelCraft.py` | Describe an object in words, get a voxel model. Python, procedural, with an optional research/reference-photo path. | [voxelcraft-newcomer-guide.md](./voxelcraft-newcomer-guide.md) |
| **Scale Model Designer** | `pages/2_Scale_Model_Designer.py` | Design block models of real landmarks to a chosen scale, in a three.js editor. One self-contained `app/index.html`. | [scale-model-designer-newcomer-guide.md](./scale-model-designer-newcomer-guide.md) |

They share no code. The rough division: VoxelCraft *generates* from a prompt; the
Designer lets *you* build to a real-world scale. Each guide is written to be read on
its own, so they overlap on repository background.

## Layout

```
streamlit_app.py                 launcher; Streamlit builds the sidebar nav
pages/1_VoxelCraft.py            VoxelCraft's UI
pages/2_Scale_Model_Designer.py  thin wrapper that embeds app/index.html
app/voxelcraft/                  VoxelCraft's Python modules
app/index.html                   the Designer, entire (~2.9 MB)
tools/ingest_library.py          builds VoxelCraft's bundled reference library
tests/accuracy_sweep.py          VoxelCraft's 177-case subject-matching sweep
CLAUDE.md                        the Designer's working notes
```

## A note on history

Until 2026-09-21 this repo was a one-app-at-a-time sandbox: every branch replaced the
app wholesale, so branches could not be merged and only one could sit on `main`. Both
tool guides still describe that layout in their §1, kept for history. This branch is
where that stopped being true — the two apps turned out to collide on only four files,
none of them app code.

There is no CI — `.github/` holds only a `CODEOWNERS` file.

Other branches still carry unrelated apps: a Pokémon-style clone, Oregon Trail
minigames, and Lemonade Tycoon sprite work ([PR #3](https://github.com/Kingatlasing/blank-app/pull/3)).
