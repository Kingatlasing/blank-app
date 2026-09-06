# ⛏️ Minecraft Scale Model Designer

Design accurate, scaled Minecraft block models of real-world landmarks — or literally anything else — with computed measurements, a hollow-or-filled interior, modeled interior chambers/floors, a layer-by-layer building blueprint, and ready-to-paste `/fill` build commands.

This is a self-contained HTML/CSS/JS app (`app/index.html`, rendered with [three.js](https://threejs.org/) for the 3D preview) shown full-screen through a thin Streamlit wrapper (`streamlit_app.py`). No backend, no build step — everything runs client-side in the browser.

## What it does

Ask it (by picking from the library, or describing a shape) for something like *"a 3/8 scale replica of Khufu's Pyramid, filled, with the interior chambers"* and it will:

- **Compute real measurements** — real-world height/footprint, your chosen scale ratio (e.g. `3/8`, or "target height in blocks"), and the resulting size in Minecraft blocks.
- **Generate the 3D shape** as a voxel model, previewed live and orbit-able in the browser.
- **Model the interior** — for the Great Pyramid (and the other Giza pyramids), it carves a proportionally-scaled entrance, descending/ascending passages, Grand Gallery, and King's & Queen's Chambers based on published Giza figures. For towers, houses, and other buildings, it hollows the shape and adds floor slabs with a stairwell gap at a spacing you choose.
- **Toggle hollow vs. filled** — a solid core with an exterior skin (realistic, more blocks) or a thin shell (lighter, faster to build).
- **Show a layer-by-layer blueprint** — a scrubbable top-down view of every Y-level, color-coded by block type, so you know exactly what to place where.
- **Export build commands** — optimized (rectangle-merged) `/fill` commands as a downloadable `.mcfunction` file.
- **Report full stats** — block counts by material, total blocks, stack/shulker-box counts, and notes on every simplification made.

### Structure library

Great Pyramid of Khufu, Pyramid of Khafre, Pyramid of Menkaure, Great Ziggurat of Ur, Big Ben, Leaning Tower of Pisa, the Colosseum, the Statue of Liberty, the Taj Mahal, the Burj Khalifa, the Eiffel Tower, a windmill, a lighthouse, a medieval castle keep, and a village house — each with real published dimensions.

### Build anything else

Not in the library? Switch to **Custom Shape**, pick the closest primitive (box, pyramid, cylinder, cone, dome, ziggurat, tower, domed building, or a hollow ring/arena wall), type in the real height and footprint you looked up, and the same scaling/hollow/interior/blueprint/command pipeline applies. This is how you can approximate *any* structure, not just the ones in the preset list.

### Honest limitations

This app ships with a curated library of real dimensions and a handful of geometric primitives — it doesn't have live internet access or an AI model looking up arbitrary buildings on demand. Interior layouts (especially the pyramid passages) are proportional approximations based on published figures, not surveyed blueprints, and very thin real-world features (like a 1.2m-wide passage) get clamped to a minimum of 1 Minecraft block. Each generated model's *Measurements & Stats* tab lists the specific simplifications made for that structure.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
