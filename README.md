# ⛏️ Minecraft Scale Model Designer

Design accurate, scaled Minecraft block models of real-world landmarks — or literally anything else — with computed measurements, a hollow-or-filled interior, modeled interior chambers/floors, a layer-by-layer building blueprint, and ready-to-paste `/fill` build commands.

This is a self-contained HTML/CSS/JS app (`app/index.html`, rendered with [three.js](https://threejs.org/) for the 3D preview) shown full-screen through a thin Streamlit wrapper (`streamlit_app.py`). No backend, no build step — everything runs client-side in the browser.

## What it does

Ask it (by picking from the library, or describing a shape) for something like *"a 3/8 scale replica of Khufu's Pyramid, filled, with the interior chambers"* and it will:

- **Compute real measurements** — real-world height/footprint, your chosen scale ratio (e.g. `3/8`, or "target height in blocks"), and the resulting size in Minecraft blocks.
- **Generate the 3D shape** as a voxel model, textured with real Minecraft block art and previewed live in the browser.
- **Model the interior** — for the Great Pyramid (and the other Giza pyramids), it carves a proportionally-scaled entrance, descending/ascending passages, Grand Gallery, and King's & Queen's Chambers based on published Giza figures, lit with torches. For towers, houses, and other buildings, it hollows the shape and adds floor slabs, a ladder-equipped stairwell, a real door at the entrance, and windows — with textured doors, glass panes, ladders, and torches, not placeholder blocks.
- **Toggle hollow vs. filled** — a solid core with an exterior skin (realistic, more blocks) or a thin shell (lighter, faster to build).
- **Let you explore the inside** — orbit, a free-fly camera, a first-person walk mode, or third-person, all with real gravity/collision and Minecraft's own camera scale (1.62 block eye height, 0.6×1.8 hitbox, 70° FOV), plus a cutaway slider that clips away one side to see inside without switching modes.
- **Let you actually operate the mechanisms** — turn on Interact mode and click any door, trapdoor, lever, button, or pressure plate to see it open/close or flip, with a real hinge-pivoted swing animation, not a texture swap. Walking onto a pressure plate in Walk mode triggers it too.
- **Show a layer-by-layer blueprint** — a scrubbable top-down view of every Y-level, color-coded by block type, with door/window/torch/ladder/lever/plate markers, so you know exactly what to place where.
- **Export build commands** — optimized (rectangle-merged) `/fill` commands plus `/setblock` commands for doors, windows, torches, levers, buttons, and plates, as a downloadable `.mcfunction` file.
- **Report full stats** — block counts by material, total blocks, stack/shulker-box counts, and notes on every simplification made.

### Real Minecraft block textures, real Minecraft geometry

Every texture (blocks, doors, windows, torches, levers, buttons, tripwire, plants) is the actual in-game art, not a redrawn approximation, sourced from [PrismarineJS/minecraft-assets](https://github.com/PrismarineJS/minecraft-assets) — a community project that extracts textures from the Minecraft client for use by tools like mineflayer and prismarine-viewer — and embedded directly in `app/index.html` (along with a vendored copy of three.js) so the page needs no network access at all. These are Mojang's own copyrighted art assets, unofficially re-published; using them this way is a long-standing, widely-tolerated norm in the Minecraft tooling community, but it's worth knowing if this project is ever redistributed publicly rather than kept for personal use.

The block picker covers **321 real blocks** — every full-cube block in the game (all wood types, stone/deepslate/nether/end variants, ores, all 16 colors of wool/concrete/terracotta/glazed-terracotta/stained-glass, copper oxidation stages, coral, and more), extracted programmatically from Minecraft's own block-model data rather than hand-picked, grouped by category in the dropdown.

Non-cube elements are modeled as real 3D volumes with real measurements (in 16ths of a block, matching Minecraft's own modeling unit), not flat sprites or texture swaps:

- **Doors** — two full-height 16×16×3px panels, correctly flush against one edge of the block (not centered) and pivoting around the true hinge edge, so opening is a real 90° swing you can watch happen.
- **Trapdoors** — a 16×16×3px panel mounted flush at the floor or ceiling, swinging to vertical against the wall when opened.
- **Levers** — a genuine two-part object (6×3×5px stone base + 2×10×2px arm) that mounts on and orients to the floor, a wall, or the ceiling, with the arm's angle changing between on/off.
- **Buttons** and **pressure plates** — real proportions (6×2×4px; 14×14×1px inset from the block edges) that visibly depress when pressed.
- **Torches** (regular/soul/redstone) — a standing 3×3×10px rod, not a billboard cross; redstone torches swap between lit/unlit textures.
- **Tripwire + hooks**, a **chair** (the actual L-shaped stair-block silhouette), and cross-plane **flowers/grass/fire** and a simple **tree** (log trunk + leaf canopy) round out the non-cube set.

These are placed automatically by the generators — torches lighting the Great Pyramid's passages, a tripwire-and-lever trap flourish near its entrance, and a working door/windows/ladder/chair set in generic building interiors — and there's a dedicated **"Redstone Mechanism Demo Room"** preset that wires a lever to the entrance door and a pressure plate to a floor-trapdoor pit, specifically so you can see these mechanisms functioning together rather than just sitting there. (The wiring is a simple, deliberate 1:1 trigger link for demonstration — not a simulated redstone-dust signal; real Minecraft wiring follows more detailed rules this app doesn't model.)

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
