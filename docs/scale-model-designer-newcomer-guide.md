# Minecraft Scale Model Designer: a newcomer's guide

> **Status note (2026-09-21).** The Scale Model Designer and VoxelCraft now run
> side by side as two pages of one Streamlit app. §1 below describes the older
> one-app-per-branch layout and is kept for history — it no longer describes this
> branch. Run both with `streamlit run streamlit_app.py` from the repo root and
> pick a tool from the sidebar; the designer is `pages/2_Scale_Model_Designer.py`.
> VoxelCraft's own guide is
> [`docs/voxelcraft-newcomer-guide.md`](./voxelcraft-newcomer-guide.md).


Written 2026-09-21, describing this branch as of commit `da675d8`. Everything below
was read from the source and, where it says "verified", actually run.

---

## 1. Where this lives

This app is on branch **`claude/minecraft-3d-model-designer-j1vrke`** of
`Kingatlasing/blank-app`. Two things to know before you go looking for it:

- **It is not on `main`.** `main` holds *Lemonade Stand Tycoon*, an unrelated game.
- **It has no pull request.** At 221 commits ahead of `main` it is by far the largest
  body of work in the repository, and it is invisible if you only read the PR list.

The repository started as Streamlit's blank-app template and is used as a
**one-app-at-a-time sandbox**: every branch replaces the app *entirely*, so branches
cannot be merged with each other and only one can ever sit on `main`. That is why six
unrelated apps live in one repo.

There is a second, much smaller Minecraft project here that people confuse with this
one: **VoxelCraft** on `claude/prompt-minecraft-3d-generator-chl31j` (PR #4), a Python
app that turns a text prompt into a voxel model for you. It shares no code with this
one. Rough division: VoxelCraft *generates* from a prompt; this app lets *you* design
to a real-world scale. See that branch's own `docs/newcomer-guide.md`.

There is no CI — `.github/` holds only a `CODEOWNERS` file — so nothing checks a branch
automatically.

---

## 2. Running it locally

Verified on Python 3.11, 2026-09-21.

```bash
git clone https://github.com/Kingatlasing/blank-app.git
cd blank-app
git checkout claude/minecraft-3d-model-designer-j1vrke

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # one line: streamlit

streamlit run streamlit_app.py      # opens on http://localhost:8501
```

`requirements.txt` is literally just `streamlit`, because **Python does nothing here**.
`streamlit_app.py` is 30 lines that read `app/index.html` and hand it to
`components.html()` full-screen. All the work is client-side.

That means **you can skip Streamlit entirely** — opening `app/index.html` in a browser
directly works just as well, and is the faster loop when you're editing. No build step,
no bundler, no network access required at runtime.

Verified end to end in headless Chromium, loading the file directly: the page boots
with **0 console errors**, the picker fills with 118 structures, and clicking
**Generate model** on the default preset produces:

```
Great Pyramid of Khufu (Giza), scale 1/2
  → 115 x 73 x 115 blocks, 328,185 blocks total
  → 357 /fill commands
  → first command: fill ~0 ~0 ~0 ~114 ~0 ~114 minecraft:quartz_block
```

The optional AI and mesh-generation backends (§6) are the only things that need
network, and none of them is required to use the app.

---

## 3. The shape of the codebase

```
streamlit_app.py     30 lines   reads the HTML, renders it full-screen. That's all.
app/index.html    25,111 lines  the entire application (~3.0 MB)
CLAUDE.md          1,695 lines  chronological session notes
```

One file. This is unusual enough to be worth saying plainly: there is no module system,
no imports, no tests. Everything — markup, styles, vendored three.js, textures, block
tables, 118 structure definitions, the voxelizer, the redstone simulator, the exporter
— is in `app/index.html`.

Rough map by line number (they shift as the file is edited; grep for the `const` name):

| Lines | What |
|---|---|
| 6–156 | styles |
| 157–630 | the whole UI: sidebar controls, four build modes, camera toolbar, tab panes |
| 636 | **vendored three.js r128**, minified, ~603 KB on one line |
| 1703–1710 | `ATLAS_B64` (~205 KB base64 PNG) + `ATLAS_UV` tile coordinates |
| 1711–2050 | `MATERIALS` — the 321-block table |
| 2058+ | `DECOR_TYPES` — 130 non-cube objects |
| 3290–4080 | per-preset real-world constants and the RLE voxel scans |
| 4082–4720 | the glTF/`.glb` parser and the voxelizing Web Worker |
| 4725–5800 | the AI Generate integration |
| 6312+ | the interior builders (`buildPyramidInterior`, `buildFloorsInterior`, …) |
| 8267–9700 | `PRESETS` — the 118 structure definitions |
| 10083 | `generateModel()` — the pipeline entry point |
| 24832 | `renderCommands()` — the `/fill` exporter |

### `CLAUDE.md` is a log, not documentation

It is 27 dated session entries in chronological order ("Strafe direction was backwards
in Walk/third-person mode", "Truncated JSON responses, and a sparse-shape
false-rejection bug"). It records *why* decisions were made and is genuinely valuable
for that, but it is not a reference — it is append-only history, and later entries
sometimes supersede earlier ones. Read it when you want the reasoning behind something
specific; don't read it top-to-bottom to learn the app.

---

## 4. How a model gets built

`generateModel()` at line 10083 is the whole pipeline, and it is short and readable.

```
  pick real-world dimensions        preset's own `real: {height, baseX, baseZ}`,
                                    or your typed numbers, or a .glb's own units
            │
  apply scale ratio                 scaledDims(real, scale) → dims in blocks
            │                       (refuses above MAX_VOXEL_VOLUME)
            │
  buildSilhouette(shapeType, …)     the solid outer form, as a flag per cell
            │
  hollowCarve(…)                    filled → solid core + 1-block skin
            │                       hollow → shell of wallThickness
            │
  interior builder (optional)       one per interiorMode; writes into the grid
            │                       and pushes entries into `decor`
            ▼
  Uint16Array grid + decor[]        ← the model
            │
            ├─ three.js preview     orbit / fly / walk / third-person
            ├─ layer blueprint      scrubbable top-down view, per Y level
            └─ renderCommands()     greedy-rectangle /fill + /setblock for decor
```

Two implementation details in there are load-bearing and commented as such in the
source, because both were real bugs:

- **The grid is a `Uint16Array`, not `Uint8Array`.** It stores material *indices*
  (1..321), and the palette grew past 255. A `Uint8Array` silently wraps values above
  255 onto the wrong block. The same applies to the per-layer `mask` in
  `renderCommands()`.
- **`fillMode`** distinguishes `filled` (solid interior core plus a 1-block exterior
  skin — realistic, far more blocks) from `hollow` (a thin shell). This is not cosmetic:
  it changes the block count by an order of magnitude and decides whether an interior
  is meaningful.

### `shape` and `interiorMode`

Each preset names a `shape` (how the outer silhouette is built) and optionally an
`interiorMode` (what gets carved inside). Their distributions tell you a lot about the
app's real structure:

- **`shape`** is overwhelmingly `box` (99 of 118). The parametric ones are `pyramid`,
  `tower`, `ziggurat`, `cone`, `bridge`, plus one-offs hand-tuned per landmark
  (`eiffelTower`, `burjKhalifa`, `tajMahal`, `pisa`, `baldEagle`) and five `*Scan`
  shapes backed by real voxel data (§5c).
- **`interiorMode`** is the opposite — almost every value is unique. There are exactly
  91 distinct modes and 91 matching `build<Name>Interior` functions. Only three are
  shared by more than one preset: `logicGate` (10), `floors` (5) and `pyramidChambers`
  (3). The other 88 appear once each.

That asymmetry is the thing to understand before adding anything: **a new preset is
usually a `box` plus a bespoke interior builder**, not a new shape. Most of the 118
entries are scene/diorama presets (`panda-grove`, `deep-dark-den`, `wither-summoning-altar`)
that are a plain box with a hand-authored interior.

---

## 5. How the reference data is organized

Five separate data sets, each with a different job and a different origin. This is the
part worth understanding before changing anything.

### a. The block table — `MATERIALS` (321 entries)

```js
{ id: 'blue_concrete', name: 'Blue Concrete', color: '#2c2e8f',
  category: 'Concrete', faces: { all: 'blue_concrete' } }
```

Every full-cube block in the game, extracted programmatically from Minecraft's own
block-model data rather than hand-picked — all wood types, stone/deepslate/nether/end
variants, ores, all 16 colours of wool/concrete/terracotta/glazed-terracotta/stained
glass, copper oxidation stages, coral. `category` drives the dropdown grouping; `color`
is the flat fallback; `faces` maps to atlas tiles and can differ per face
(`{ top, side, bottom }` for logs and grass).

`MATERIAL_INDEX` maps `id → array index`. The grid stores **index + 1**, so 0 means
empty.

### b. The texture atlas — `ATLAS_B64` + `ATLAS_UV`

A single 512×256 base64 PNG of 16×16 tiles, embedded directly in the file, with
`ATLAS_UV` giving each tile's pixel offset. This is why the page needs no network: the
textures, the geometry, and three.js are all inline.

The art is real in-game texture data sourced from
[PrismarineJS/minecraft-assets](https://github.com/PrismarineJS/minecraft-assets).
**Worth a deliberate decision before this repo is ever made public**: these are Mojang's
copyrighted assets, unofficially republished. Long-standing and widely tolerated in the
Minecraft tooling community, fine for personal use, but it is a real consideration for
redistribution — and it is the kind of thing that is much easier to decide now than
after the fact.

### c. Voxel scans of real 3D models — the `*_SCAN_RUNS_STR` constants

Five presets are not generated from code. They are real 3D meshes, voxelized **offline**
from CC-BY `.glb` files and embedded as run-length-encoded strings:

| Constant | Preset | Grid | Encoded size |
|---|---|---|---|
| `COLOSSEUM_SCAN_RUNS_STR` | Colosseum | 207×78×247 | ~274 KB |
| `VADER_SCAN_RUNS_STR` | Darth Vader Helmet | — | ~125 KB |
| `KIP_SCAN_RUNS_STR` | Kip (original character) | 165×224×107 | ~113 KB |
| `GGB_SCAN_RUNS_STR` | Golden Gate Bridge | 564×56×109 | ~33 KB |
| `LIBERTY_SCAN_RUNS_STR` | Statue of Liberty | 87×108×92 | ~23 KB |

**The encoding is simple once you see it:** a comma-separated list of *run lengths*
only — no values. You start at `<NAME>_SCAN_FIRST` (0 or 1) and alternate every run:

```js
let pos = 0, val = GGB_SCAN_FIRST;
for (const len of runs) { if (val) grid.fill(1, pos, pos + len); pos += len; val = 1 - val; }
```

The matching `*ScanSolid(x, y, z, dims)` function then nearest-neighbour samples that
fixed grid at whatever scale you asked for, which is why these presets stay sharp at
any scale but can never gain detail beyond their scan resolution.

The Statue of Liberty additionally carries `LIBERTY_MATERIAL_RUNS_STR` with a
`LIBERTY_MATERIAL_PALETTE`, so it reproduces real per-block materials (white wool statue,
stone pedestal, glowstone walkway, grass plaza) rather than one flat colour — its source
model turned out to be a Mineways export from a real Minecraft world.

These exist because hand-tuned geometry could not get a convincing likeness. Every other
preset is generated from code.

### d. Structure presets — `PRESETS` (118 entries)

```js
{ id: 'great-pyramid', name: "Great Pyramid of Khufu (Giza)", shape: 'pyramid',
  real: { height: 146.6, baseX: 230.4, baseZ: 230.4 },
  interiorMode: 'pyramidChambers', defaultScaleNum: 1, defaultScaleDen: 2,
  blocks: { exterior: 'quartz_block', interior: 'stone', accent: 'gold_block' },
  desc: '…', notes: ['…'] }
```

`real` is the actual published real-world size in metres and is what makes the whole
scale system work. `notes` is an honesty channel, surfaced in the UI — the Great Pyramid
entry records that its passages are proportional approximations rather than surveyed
coordinates, that the Subterranean Chamber is omitted, and that narrow passages clamp to
one block at small scales. **Keep writing those.** They are the difference between a
model you can trust and one you can't.

The 118 break down as roughly 20 real-world landmarks and buildings, 15 redstone gates
and contraptions, and 83 scene/diorama presets.

### e. Decor — `DECOR_TYPES` (130 entries)

Everything that is not a full cube: doors, trapdoors, windows, ladders, bars, levers,
buttons, pressure plates, torches, redstone wire and torches, rails, chairs, chests,
plants, mobs. Each entry names its atlas tile, its geometry `kind`, and whether it is
`interactive` (`'open'` or `'power'`).

Interior builders push entries into a `decor` array alongside the grid, and
`renderCommands()` exports them as `/setblock` after the `/fill` commands. The
`interactive` flag is what lets Interact mode and the redstone simulation work on real
placed objects rather than a scripted animation.

---

## 6. The optional backends

Four build modes sit behind the "What to build" radio: **Famous structure**, **Custom
shape**, **Import 3D model (.glb)**, and **AI Generate**. The first two need nothing.
The other two reach outside:

- **Import `.glb`** parses the glTF binary container with a hand-rolled parser (no
  library), composes each mesh node's world transform, and voxelizes with
  rasterize-then-flood-fill in a Web Worker. Same technique used offline for the §5c
  presets. USDZ is deliberately unsupported — it would need a large WASM build of Pixar's
  USD library.
- **AI Generate** asks a model to write geometry code, run through the same pipeline as
  every other shape. Either Anthropic with your own key (stored in browser local storage,
  sent straight from the browser, since there is no backend) or any OpenAI-compatible
  local server (Ollama, LM Studio, llama.cpp, vLLM).
- **Two real mesh-generation backends** you self-host: LocalAI's `/3d/generations`
  (image-to-3D only) and Tencent's Hunyuan3D-2 (image *and* text to 3D).

**Before debugging Hunyuan3D-2 text-to-3D, read this:** it cannot work against a stock
upstream server. `api_server.py` ships with `pipeline_t2i` **commented out** while the
text branch calls it, so text requests raise `AttributeError`, get swallowed by a generic
handler, and surface as a canned "NETWORK ERROR DUE TO HIGH TRAFFIC" message. You have to
uncomment those lines and download the HunyuanDiT weights yourself. Same failure shape for
the "generate texture too" checkbox, which needs the server started with `--enable_tex` —
and the voxelizer discards texture data anyway, so leave it unchecked. Also: this app
defaults to port 8080, `api_server.py` defaults to 8081.

A generated mesh's colour never survives voxelization — nothing in the `.glb` pipeline
reads UV or material data, from any source.

---

## 7. Gotchas, collected

- **`main` is not this app**, and this branch has **no PR**. Check out the branch.
- **Branches cannot be merged together.** Each replaces the whole app.
- **Python is not involved.** Open `app/index.html` directly while developing; Streamlit
  is only a delivery wrapper.
- **No CI, no tests.** `CLAUDE.md:1674` cites a `hunyuan3d-test.js` suite, but it was
  never committed — the branch tracks 9 files and no test file exists in any branch's
  history. Verify in the browser.
- **`CLAUDE.md` is chronological history**, not a reference. Later entries can supersede
  earlier ones.
- **Never use `Uint8Array` for anything holding a material index.** The palette is 321
  entries; values above 255 wrap silently onto the wrong block.
- **A new preset is usually a `box` with a bespoke interior builder**, not a new shape.
- **The embedded textures are Mojang's copyrighted art.** Fine for personal use; decide
  deliberately before publishing.
- **The `notes` field on a preset is load-bearing.** Record every approximation you make.
