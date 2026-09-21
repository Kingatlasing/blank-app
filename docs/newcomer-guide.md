# blank-app: a newcomer's guide to the voxel model generator

Written 2026-09-21, describing this branch as of commit `e8a8b61`. Everything below
was read from the repository and, where it says "verified", actually run.

Two areas were being actively worked on as this was written and are the first places
to check for drift: the keyword/substring matching described in §3 and §4b, and the
bundled reference library in §4d.

---

## 1. What lives where

One correction up front, because it will save you an hour: **the model generator is
not on `main`.** `main` currently holds *Lemonade Stand Tycoon*, an unrelated game.

This repository started as Streamlit's blank-app template and is used as a
**one-app-at-a-time sandbox**. Every branch replaces the app *entirely* with a
different project, so the branches cannot be merged with each other — only one can
ever sit on `main`. That is why there are six unrelated apps in one repo.

| Branch | What it is | State |
|---|---|---|
| `main` | Lemonade Stand Tycoon | 2 merged PRs |
| `claude/prompt-minecraft-3d-generator-chl31j` | **VoxelCraft** — the Python voxel model *generator*. This guide is about this one. | open [PR #4](https://github.com/Kingatlasing/blank-app/pull/4), 18 commits ahead of main |
| `claude/minecraft-3d-model-designer-j1vrke` | **Minecraft Scale Model Designer** — a separate, much larger browser-side designer (see §5) | 221 commits ahead of main, **no PR** |
| `claude/pokemon-game-clone-4k-j4h2s8` | Pokémon-style game clone | 28 commits, no PR |
| `claude/oregon-trail-minigames-zombie-ijysnk` | Oregon Trail minigames | 8 commits, no PR |
| `claude/lemonade-tycoon-remake-qbsgy4` | Lemonade Tycoon sprite work | open [PR #3](https://github.com/Kingatlasing/blank-app/pull/3) |
| `claude/courtside-card-pack-mock-app-99fqki` | Card-pack mock app | merged as PR #1 |

There is no CI — `.github/` holds only a `CODEOWNERS` file — so nothing checks a
branch automatically. No issues have ever been opened.

**Two different Minecraft projects exist**, and people mix them up. VoxelCraft
(§2–§4) is Python, prompt-driven, and generates a model for you. The Scale Model
Designer (§5) is one enormous self-contained HTML file where *you* design to a
chosen scale. They share no code.

---

## 2. Running VoxelCraft locally

Verified on Python 3.11, 2026-09-21: the dependencies install and the app serves.

```bash
git clone https://github.com/Kingatlasing/blank-app.git
cd blank-app
git checkout claude/prompt-minecraft-3d-generator-chl31j

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # streamlit, pillow, requests — that's all

streamlit run streamlit_app.py       # opens on http://localhost:8501
```

There is no build step, no API key, and no database. `requirements.txt` is three
lines; the resolved versions in a clean venv were streamlit 1.64.0, pillow 12.3.0,
requests 2.34.2.

**The default path is fully offline.** Type a prompt, leave the build strategy on
"Built-in procedural shapes", and you get a model with no network access at all.
Verified directly:

```
'a red house with a garden' → 3000 voxels, 516 fill commands
'the Eiffel Tower'          → 2624 voxels, 792 fill commands
'a fluffy cloud'            → 2200 voxels, 704 fill commands  (no match → abstract sculpture)
```

Two optional paths need something extra, and both **fall back to procedural shapes
rather than failing** if that something is missing:

- **🔎 Research online** needs outbound HTTPS to Wikipedia, Wikidata, and Openverse.
  All three are free and keyless. In a sandbox without egress, the Wikipedia lookup
  returns `None` and you silently get the procedural model instead — verified.
- **🧠 Design with a local LLM** needs your own [Ollama](https://ollama.com) server
  at `http://localhost:11434` with a code model pulled (`qwen2.5-coder` is the
  default and the right kind of model for this). Nothing is sent off your machine.

### Headless / scripted check

Handy when you just want to confirm the pipeline works without a browser:

```bash
python -c "
from app.voxelcraft import text_generator, exporters
from app.voxelcraft.transform import normalize, scale_voxels
v, note = text_generator.generate_from_text('a red house with a garden')
v = normalize(scale_voxels(v, 2))
print(len(v), 'voxels —', note)
print(exporters.to_mcfunction(v)[:200])
"
```

---

## 3. How a prompt becomes a model

`streamlit_app.py` is the only wiring; every module below lives in `app/voxelcraft/`.

```
prompt
  │
  ├─ 🧠 llm_builder      (opt-in)  Ollama writes Python against a small geometry API,
  │                                run in a restricted sandbox
  ├─ 🔎 research         (opt-in)  find a reference photo + real dimensions,
  │                                then image_generator sculpts it
  └─ text_generator      (default) keyword → shapes.py builder
         │
         ▼
   list[(x, y, z, "#hex")]                  ← the one data structure everything speaks
         │
    transform.scale_voxels → normalize → voxel_count_limit (80,000 cap)
         │
         ├─ viewer.build_viewer_html   → three.js preview in an iframe
         └─ exporters                  → .json / .obj+.mtl / .mcfunction
```

A voxel is just a 4-tuple: `(x, y, z, hex_color)`, `y` is up. Every module either
produces or consumes a `list[Voxel]`, which is why the three generation strategies
are interchangeable.

Module by module:

| File | Lines | Job |
|---|---|---|
| `shapes.py` | 588 | 21 procedural builders — humanoid, tree, house, temple, tower, castle, sword, pickaxe, heart (flat and true 3D), star, dog, cat, dragon, car, boat, pyramid, plus `procedural_blob` |
| `research.py` | 403 | Wikipedia → Openverse photo lookup, Wikidata dimensions, and picking a 3D reconstruction strategy |
| `llm_builder.py` | 320 | Ollama prompt, AST pre-check, sandboxed execution of generated code |
| `image_generator.py` | 266 | photo → voxels: background removal, palette quantization, relief/revolve/flat |
| `text_generator.py` | 142 | 19-entry keyword table mapping prompt → builder; composes multiple subjects into one scene |
| `palette.py` | 134 | the 37-swatch block palette (see §4) |
| `viewer.py` | 121 | builds the self-contained three.js preview page |
| `exporters.py` | 92 | `to_json`, `to_obj`, `to_mcfunction` |
| `local_library.py` | 162 | bundled reference photos and cached dimensions (see §4) |
| `known_facts.py` | 77 | curated landmark dimensions (see §4) |
| `transform.py` | 36 | `scale_voxels`, `normalize`, `voxel_count_limit` |

Outside the package, `tools/ingest_library.py` (453 lines) generates the bundled
reference library described in §4d.

### The one genuinely clever bit

A photo shows one side of a thing, so stacking its pixels on a slab gives you a
cardboard cutout, not a model. `research.py` therefore picks a **reconstruction
strategy** from the Wikipedia article's own text:

- **`revolve`** — spin the silhouette around its vertical axis like a lathe. Right
  for towers, statues, bottles, domes.
- **`relief`** — extrude the silhouette into a bas-relief. Right for everything else.

Buildings are checked *first* and always win, because a temple described as having
"columns" is still a rectangular building, not one round object.

Two details in there are worth knowing before you touch the matcher. Keywords match
whole words with an optional trailing `s` and deliberately **not** as a prefix — the
comment in `_word_matches` records that `\b{keyword}\w*\b` made "dome" match
"domesticated" and "cup" match "cupboard" in testing. And `streamlit_app.py` runs
`image_generator.is_degenerate` on the result: a relief that comes out ~one solid
color means the reconstruction went wrong upstream, so the app throws it away and
falls back to a procedural shape rather than shipping a colored blob as the answer.

---

## 4. How the model reference data is organized

There are **four** separate data sets, each with a different job and a different
reason for existing. This is the part most worth understanding before changing
anything.

### a. The block palette — `palette.py`

37 `Swatch(name, hex, block)` entries, each pinning a color to a **real Minecraft
Java Edition block id** (`minecraft:red_wool`, `minecraft:oak_planks`, …).

This is the constraint the whole app is built around: every color VoxelCraft ever
places comes from this list, so any finished model can always be re-expressed as
real blocks by `exporters.to_mcfunction`. `nearest_swatch()` quantizes arbitrary RGB
from a photo to the closest swatch; `COLOR_WORDS` maps 79 prompt words and synonyms
("crimson", "azure", "molten", "glacier") onto swatch names so prompts can steer
color.

**Adding a swatch means adding a real block id** — don't add a color without one, or
the mcfunction export breaks its own promise.

### b. The procedural shape library — `shapes.py` + `text_generator.py`

The offline default. `_RULES` in `text_generator.py` is an **ordered, specific-first**
list of 19 `(keywords, builder)` pairs — order matters, since "pickaxe" must be
tested before generic matches. A prompt naming several subjects gets each one built
and composed side by side into a single scene. Anything unmatched falls through to
`procedural_blob`, which is seeded from the prompt text, so every prompt produces
*something*, and the same prompt always produces the same thing.

### c. Curated landmark dimensions — `known_facts.py`

28 hand-checked landmarks (Eiffel Tower, Burj Khalifa, Stonehenge, …) as
`(aliases, BlueprintFacts(height_m, width_m, diameter_m, floors))`.

Its role is precise, and the precedence is the thing to remember:

> `fetch_blueprint_facts()` asks **Wikidata first**, then the ingested cache in
> `library/facts.json`, then this table — each one filling in only the fields the
> ones above it left empty. A value a higher source *did* return is **never**
> overridden, because it is the more current source when you can reach it.

Verified offline: `get_known_facts('the eiffel tower in paris')` → height 330 m,
width 125 m, while the live Wikipedia lookup returned nothing.

Aliases are always **full phrases**, never a bare generic word like "tower" or
"bridge", so an unrelated prompt containing that word can't accidentally match.
Matching runs in both directions, so "the eiffel tower in paris" and "eiffel tower"
both hit. Keep that rule if you add entries.

These facts do real work: `BlueprintFacts.ratio` (height ÷ diameter-or-width) is
passed to `image_to_voxels` as `target_ratio` to correct the model's proportions to
the real object, instead of inheriting whatever foreshortening the photo had.

### d. The bundled reference library — `app/voxelcraft/library/`

`manifest.json`, `facts.json` and an `images/` directory, checked **before** any live
lookup. **It still ships empty** (`manifest.json` is `{}`), so this is a no-op and
every request falls through to live research — check the manifest before assuming it
is still empty.

It is no longer filled in by hand: `tools/ingest_library.py` generates all three from
Wikipedia, Wikidata, Commons and Openverse. The schema, per `library/README.md`:

```json
{
  "park bench": {
    "aliases": ["bench (furniture)", "park bench"],
    "wikipedia_title": "Bench (furniture)",
    "image": "images/park-bench.png",
    "source_label": "Openverse photo by <creator> (CC0)",
    "source_url": "https://openverse.org/image/...",
    "license": "cc0",
    "attribution": "<creator>",
    "extract": "A bench is a long seat ...",
    "build_method_override": null,
    "height_m": null, "width_m": null, "diameter_m": null, "floors": null
  }
}
```

Two things there are easy to misread. `extract` is stored because the `relief`
vs `revolve` decision is **re-derived from it on every request** rather than frozen
at ingest time, so a fix to `_classify_build_method` reaches bundled entries
immediately; `build_method_override` is the escape hatch for correcting one by hand.

The point is reliability: a bundled image never needs network, never rate-limits, and
its licence was verified at ingest time rather than trusted blind at generation time.
`get_local_reference()` never raises — a missing or malformed entry is treated exactly
like "not found", so a bad local file cannot break generation.

Two constraints the README is emphatic about, and they are the reason the directory
is empty rather than full:

1. **Every entry must be individually confirmed openly licensed** (CC0, or CC-BY with
   the attribution recorded in `source_label`/`source_url`). This is deliberately not
   an attempt to mirror Wikipedia — that is neither storable nor legal to bulk-copy.
   The ingest enforces it in `_licence_ok`: share-alike, non-commercial,
   no-derivatives and non-free files are rejected before download, and a subject whose
   only photo is rejected is left out rather than bundled anyway.
2. **The dev sandbox has no outbound network.** Its egress policy returns 403 for
   `en.wikipedia.org`, `www.wikidata.org`, `commons.wikimedia.org` and
   `api.openverse.org`, so the ingest has to run somewhere with real network access.
   That is why the library is still empty despite the tooling existing.

To fill it: `python tools/ingest_library.py` (add `--dry-run` to see what it would
fetch first). Accepted images land in `images/`, attribution is regenerated into
`ATTRIBUTION.md`, and `get_local_reference(subject)` picks them up with no code
changes.

### Lookup order, end to end

```
local_library (bundled, empty today)  →  Wikipedia  →  Openverse          [photo]
Wikidata (live)  →  facts.json (ingested)  →  known_facts (curated)  [dimensions]
```

---

## 5. The other project: Minecraft Scale Model Designer

On `claude/minecraft-3d-model-designer-j1vrke`. Worth knowing about because it is by
far the largest body of work in the repo — 221 commits — and it has **no pull
request**, so it is invisible if you only look at the PR list.

Architecturally it is the opposite of VoxelCraft: **one self-contained 25,111-line
`app/index.html`** (three.js vendored, Minecraft textures embedded, no network
needed) behind a thin Streamlit wrapper that just renders it full-screen. No backend,
no build step, all client-side.

```bash
git checkout claude/minecraft-3d-model-designer-j1vrke
pip install -r requirements.txt && streamlit run streamlit_app.py
```

What it does differently: you pick a real landmark or describe a shape, give it a
**scale ratio** (`3/8`, or a target height in blocks), and it computes real
measurements, models interiors (floors, stairwells, doors, windows — and for the
Great Pyramid, the actual passages and chambers from published Giza figures),
simulates redstone for real, lets you walk around inside with Minecraft's own camera
geometry, and exports `/fill` + `/setblock` commands.

It also carries its own, much larger reference data: ~320 real blocks extracted from
Minecraft's own block-model data, real textures from
[PrismarineJS/minecraft-assets](https://github.com/PrismarineJS/minecraft-assets),
and several presets voxelized offline from real CC-BY `.glb` meshes (Statue of
Liberty, Darth Vader helmet, Golden Gate Bridge, Colosseum). Its `CLAUDE.md` is
1,695 lines of accumulated session notes and is the real documentation for it.

One thing to be aware of if this repo is ever made public: those embedded textures
are Mojang's own copyrighted art, unofficially republished. Widely tolerated in the
Minecraft tooling community, fine for personal use, but worth a deliberate decision
before redistribution.

---

## 6. Gotchas, collected

- **`main` is not the generator.** Check out the branch.
- **Branches cannot be merged together.** Each replaces the whole app. Picking one
  for `main` means dropping the others from it.
- **`README.md` on the generator branch is out of date.** It documents `palette`,
  `shapes`, `text_generator`, `image_generator`, `exporters`, and `viewer`, but not
  `research.py`, `llm_builder.py`, `known_facts.py`, `local_library.py`, or
  `transform.py` — roughly half the modules, including both optional pipelines.
- **The bundled reference library was empty at `e8a8b61`**, making that code path
  dead scaffolding rather than a bug. Check `library/manifest.json` before relying on
  that still being true.
- **No CI.** Nothing runs on push; verify locally.
- **Two sliders are deliberately disabled.** `img_resolution` and `scale_factor` are
  hardcoded to 28 and 2 in `streamlit_app.py`, with a comment saying they were removed
  "while stabilizing generation quality" and are to come back once research mode is
  reliable.
- **The LLM sandbox is defense-in-depth, not a security boundary.** Its own docstring
  says so: builtins allowlist, AST check, 5-second wall clock. It assumes what it is —
  your own local model, on your own machine, that you chose to run.
