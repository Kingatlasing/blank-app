# 🧱 Minecraft modeling tools

Two Minecraft modeling tools, running side by side as one Streamlit app. They share
no code — pick whichever fits what you're doing.

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Both tools appear in the sidebar.

## 🧱 VoxelCraft — prompt → voxel model

Type `a red house with a garden` or `a diamond sword` and get a blocky voxel model
back, built from procedural shapes with no API key or external service required.
Optionally research a real reference photo and real dimensions online, voxelize an
image you supply, or hand the design off to a local LLM. Exports `.mcfunction`,
JSON, and OBJ/MTL.

Full details: [`docs/voxelcraft.md`](docs/voxelcraft.md) ·
Guide: [`docs/voxelcraft-newcomer-guide.md`](docs/voxelcraft-newcomer-guide.md)

## ⛏️ Scale Model Designer — design to a real-world scale

Build accurate, scaled block models of real landmarks, or anything you design
yourself, in a three.js editor with ~320 real Minecraft blocks. Computes real
measurements for a chosen scale ratio (`3/8`, or a target height in blocks), models
interiors, renders a layer-by-layer blueprint, and exports optimized `/fill` commands.
Also imports `.glb` models and can call self-hosted mesh-generation backends.

Full details: [`docs/scale-model-designer.md`](docs/scale-model-designer.md) ·
Guide: [`docs/scale-model-designer-newcomer-guide.md`](docs/scale-model-designer-newcomer-guide.md)

## Layout

```
streamlit_app.py                 launcher; Streamlit builds the sidebar nav
pages/1_VoxelCraft.py            VoxelCraft's UI
pages/2_Scale_Model_Designer.py  thin wrapper that embeds app/index.html
app/voxelcraft/                  VoxelCraft's Python modules
app/index.html                   the Designer, entire (~2.9 MB, self-contained)
tools/ingest_library.py          builds VoxelCraft's bundled reference library
tests/accuracy_sweep.py          VoxelCraft's subject-matching accuracy sweep
```

New here? [`docs/newcomer-guide.md`](docs/newcomer-guide.md) is the starting point.

## Asset licensing

The Scale Model Designer embeds Minecraft block textures (Mojang's art, via
[PrismarineJS/minecraft-assets](https://github.com/PrismarineJS/minecraft-assets))
directly in `app/index.html`, and several presets are voxelized from CC-BY-4.0
Sketchfab models. The CC-BY attributions are recorded in
[`docs/scale-model-designer.md`](docs/scale-model-designer.md). The embedded Mojang
textures are not covered by this repository's Apache-2.0 license and are not the
maintainer's to relicense — see that document's own note before redistributing.
