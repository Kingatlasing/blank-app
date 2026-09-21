# 🧱 VoxelCraft

Turn any text prompt into a blocky, Minecraft-style 3D voxel model — or turn a reference image (from a URL or a file upload) into one instead. Everything runs locally with rule-based procedural generation and image color-quantization; no external AI service or API key is required.

- **Prompt → model** — type something like `a red house with a garden`, `a diamond sword`, or `a golden castle` and VoxelCraft recognizes the subject, colors, and builds a voxel structure for it. Anything it doesn't recognize still gets a unique abstract voxel sculpture, deterministically generated from your prompt text.
- **Image → model (optional)** — paste an image URL or upload a photo and VoxelCraft downsamples it, quantizes every pixel to the closest real Minecraft block color, and extrudes it into either a flat pixel-art plane or a 3D bas-relief sculpture.
- **Live 3D preview** — every model renders instantly in an orbitable, zoomable Three.js viewer right in the browser.
- **Real Minecraft export** — download a `.mcfunction` file (built from `/fill` commands using actual vanilla block IDs) that you can drop into a datapack and run in-game to build the model out of real blocks. JSON and OBJ+MTL mesh exports are also available for use in other 3D tools.
- **Chunkiness control** — scale how big each voxel/block is to make the model coarser or more detailed.

### How it works

- `app/voxelcraft/palette.py` — the shared Minecraft-block color palette (hex color ↔ real block id), plus color-word detection for prompts.
- `app/voxelcraft/shapes.py` — procedural builders (humanoid, tree, house, castle, sword, pickaxe, heart, star, pyramid, vehicles, animals, a deterministic fallback sculpture, ...).
- `app/voxelcraft/text_generator.py` — matches prompt keywords to a shape builder and recolors it from any color words found.
- `app/voxelcraft/image_generator.py` — fetches/loads an image and voxelizes it (flat pixel-art or 3D relief).
- `app/voxelcraft/exporters.py` — JSON, OBJ/MTL, and `.mcfunction` export.
- `app/voxelcraft/viewer.py` — builds the self-contained Three.js preview page.
- `streamlit_app.py` — the UI wiring it all together.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

### Using the `.mcfunction` export in real Minecraft (Java Edition)

1. Create a datapack: `<world>/datapacks/voxelcraft/data/voxelcraft/functions/build.mcfunction` and paste the downloaded file's contents into it, alongside a minimal `pack.mcmeta` (see the [data pack docs](https://minecraft.wiki/w/Data_pack)).
2. In-world, run `/reload`.
3. Stand where you want the model's corner to appear and run `/function voxelcraft:build`.
