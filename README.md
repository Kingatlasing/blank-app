# ⛏️ Minecraft Scale Model Designer

Design accurate, scaled Minecraft block models of real-world landmarks — or literally anything else — with computed measurements, a hollow-or-filled interior, modeled interior chambers/floors, a layer-by-layer building blueprint, and ready-to-paste `/fill` build commands.

This is a self-contained HTML/CSS/JS app (`app/index.html`, rendered with [three.js](https://threejs.org/) for the 3D preview) shown full-screen through a thin Streamlit wrapper (`streamlit_app.py`). No backend, no build step — everything runs client-side in the browser.

## What it does

Ask it (by picking from the library, or describing a shape) for something like *"a 3/8 scale replica of Khufu's Pyramid, filled, with the interior chambers"* and it will:

- **Compute real measurements** — real-world height/footprint, your chosen scale ratio (e.g. `3/8`, or "target height in blocks"), and the resulting size in Minecraft blocks.
- **Generate the 3D shape** as a voxel model, textured with real Minecraft block art and previewed live in the browser.
- **Model the interior** — for the Great Pyramid (and the other Giza pyramids), it carves a proportionally-scaled entrance, descending/ascending passages, Grand Gallery, and King's & Queen's Chambers based on published Giza figures, lit with torches. For towers, houses, and other buildings, it hollows the shape and adds floor slabs, a ladder-equipped stairwell, a real door at the entrance, and windows — with textured doors, glass panes, ladders, and torches, not placeholder blocks.
- **Toggle hollow vs. filled** — a solid core with an exterior skin (realistic, more blocks) or a thin shell (lighter, faster to build).
- **Let you explore the inside** — orbit, a free-fly camera (drag to look, WASD to move), or a first-person walk mode with real gravity and collision against the model, plus a cutaway slider that clips away one side to see inside without switching modes.
- **Show a layer-by-layer blueprint** — a scrubbable top-down view of every Y-level, color-coded by block type, with door/window/torch/ladder markers, so you know exactly what to place where.
- **Export build commands** — optimized (rectangle-merged) `/fill` commands plus `/setblock` commands for doors, windows, torches, and ladders, as a downloadable `.mcfunction` file.
- **Report full stats** — block counts by material, total blocks, stack/shulker-box counts, and notes on every simplification made.

### Real Minecraft block textures

Block, door, window, torch, lever, and tripwire textures are the actual in-game art (not redrawn approximations), sourced from [PrismarineJS/minecraft-assets](https://github.com/PrismarineJS/minecraft-assets) — a community project that extracts textures from the Minecraft client for use by tools like mineflayer and prismarine-viewer — and embedded directly in `app/index.html` (along with a vendored copy of three.js) so the page needs no network access at all. These are Mojang's own copyrighted art assets, unofficially re-published; using them this way is a long-standing, widely-tolerated norm in the Minecraft tooling community, but it's worth knowing if this project is ever redistributed publicly rather than kept for personal use.

The block picker covers **321 real blocks** — every full-cube block in the game (all wood types, stone/deepslate/nether/end variants, ores, all 16 colors of wool/concrete/terracotta/glazed-terracotta/stained-glass, copper oxidation stages, coral, and more), extracted programmatically from Minecraft's own block-model data rather than hand-picked, grouped by category in the dropdown.

Non-cube elements are modeled as real 3D shapes, not flat sprites: torches are a standing 3D rod (not a billboard cross), levers are a two-part stone base + angled arm, doors and trapdoors are true door/trapdoor-thickness panels, tripwire runs low across the floor between hooked posts, and a "chair" uses the actual L-shaped stair-block silhouette. Doors, windows, torches, ladders, levers, tripwire, and chairs are placed automatically: torches and a tripwire-and-lever trap flourish in the Great Pyramid's passages, and a door/windows/ladder/chair set in generic building interiors.

### Structure library

Great Pyramid of Khufu, Pyramid of Khafre, Pyramid of Menkaure, Great Ziggurat of Ur, Big Ben, Leaning Tower of Pisa, the Colosseum, the Statue of Liberty, the Taj Mahal, the Burj Khalifa, the Eiffel Tower, a windmill, a lighthouse, a medieval castle keep, and a village house — each with real published dimensions.

### Build anything else

Not in the library? Switch to **Custom Shape**, pick the closest primitive (box, pyramid, cylinder, cone, dome, ziggurat, tower, domed building, or a hollow ring/arena wall), type in the real height and footprint you looked up, and the same scaling/hollow/interior/blueprint/command pipeline applies. This is how you can approximate *any* structure, not just the ones in the preset list.

### Honest limitations

This app ships with a curated library of real dimensions and a handful of geometric primitives — it doesn't have live internet access or an AI model looking up arbitrary buildings on demand. Interior layouts (especially the pyramid passages) are proportional approximations based on published figures, not surveyed blueprints, and very thin real-world features (like a 1.2m-wide passage) get clamped to a minimum of 1 Minecraft block. Each generated model's *Measurements & Stats* tab lists the specific simplifications made for that structure.

### Not in this pass yet

Freeform generators for whole categories (a decorated house, a fortress with traps, a maze, an escape room, a town with quests) and a redstone reference/circuit tab are natural next additions but are big enough to deserve their own pass rather than being bolted on here — see the assistant's summary for the proposed plan.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
