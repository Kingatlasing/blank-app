# Asset Library — Emberwild Trails

Internal reference for every asset available to this project, where it comes
from, and how it's addressed in code. Keep this updated when new assets are
pulled in. See `../ATTRIBUTIONS.md` for license details.

## 1. World tile atlas (`tiled.js` → `TILED.atlas`, `TILED.maps`)

Source: `aaron5670/PokeMMO-Online-Realtime-Multiplayer-Game`, tileset
`tuxmon-sample-32px-extruded.png` (816x1020, 32px tiles, margin 1 / spacing 2,
24 columns). Rebuilt into a packed 20-col atlas (`world_atlas.png`, 640x416,
254 unique tiles) with no margin/spacing, indexed 1..N (slot 0 = empty).

**Render contract:** each map in `TILED.maps[name]` has `w`, `h`, and flat
row-major arrays `below`/`world`/`above`/`grass` (atlas slot per cell, 0 =
none) plus `collide` (bool per cell, true = solid), `spawns` (name → {x,y}
tile coords), `warps` (rects → target map + spawn name), `indoor` (zone
rects, informational). Draw order: `below`, `world`, then player/NPCs
sorted by y, then `above` on top (so tree canopies overlap the player).
**Tile size:** atlas tiles are 32px native (`SRC_TILE`); on-screen they draw
at `TILE=64` (clean 2x, integer — never resize the canvas to a non-multiple
of this or tile-boundary seams reappear, e.g. the "trees cut in half" bug).

Maps available and what's in them (all five are one connected world,
in this order): `town` (40x40, start town: 2 houses, 3 "center-style"
buildings, fountain plaza) → `route1` (40x28, grass encounters) →
`ashveld` (40x36, has a `hall-8-23` zone = the Arena-style building) →
`route2` (40x30, grass encounters) → `crysthaven` (48x40, biggest city,
`hall-31-15` = its Arena building). `pokemon_center_*` map files exist in
the source repo but are **unfinished placeholders** (grass + tree-corner
tiles, not a real interior) — don't use them.

Loose tile crops from the same repo's tileset, kept from an earlier pass,
still used for two hand-built bonus maps (`enforcerhideout`, `summitplateau`)
that have no equivalent in the source world:
`grass`, `path`, `water`, `boulder`, `bush`, `berry`, `flower`, `fence`,
`stump`, plus building stamps `b_mart`, `b_center`, `b_tower`, `b_cabin`,
`b_small`, `b_arena`, `b_fountain` (all in `ASSET_B64.tiles` /
`ASSET_B64.buildings`, drawn via the legacy `TILE_DEF`/`drawTileImg` path —
see `enforcerhideout`/`summitplateau` in `engine.js`). `rocktexture` /
`cavefloor` come from Tuxemon's own tileset (`Tiles_packed.png`), used only
for the dungeon.

## 2. Creatures (`data.js` → `MONSTERS`, sprites in `ASSET_B64.monsters`)

Source: `Tuxemon/Tuxemon`, `mods/tuxemon/db/monster/*.yaml` +
`mods/tuxemon/gfx/sprites/battle/*-sheet.png` (top-left 64x44 frame cropped).
165 of the project's 411 creatures are included (full evolution families,
spread across all 13 types). To add more: re-run the extraction against
a fresh slug list — `MONSTERS[slug]` gives `types`, `shape`, `stats`
(shape attributes), `moveset` (level→technique), `evolutions`, `catch_rate`.

## 3. Moves / Items / Type chart (`data.js`)

`TECHNIQUES` (207 moves used by the 165 creatures' movesets),
`ITEMS_DB` (13 curated items: potion tiers, tuxeball tiers, antidote,
revive, cureall — plus one project-original entry, `bridge_pass`),
`ELEMENTS` (13x13 type effectiveness chart). All from Tuxemon's `db/`.

## 4. Character sprites (`ASSET_B64.chars`)

Source: `Tuxemon/Tuxemon`, `mods/tuxemon/sprites/*.png` — each a 48x128
sheet, 3 walk frames x 4 direction-rows (row order: down, left, right, up —
see `charFrame()` in `engine.js`). Currently mapped: `player_boy`
(adventurer), `player_girl` (heroine), `professor`, `rival` (postboy_red),
`nurse`, `shopkeeper`, 8x `leader_*` (monk/ceo/swimmer/catgirl/barmaid/
beachcomber variants), `enforcer_grunt`/`enforcer_boss` (boss variants),
`champion` (boss_orange), `townsfolk1`/`townsfolk2`. 209 total sprites
exist in that folder if more NPC variety is wanted later.

## 5. Element/type icons (`ASSET_B64.elements`)

Source: Tuxemon `mods/tuxemon/gfx/ui/icons/element/*_type_small.png`,
one per type slug. Not currently drawn anywhere in the UI (type badges use
flat color chips via `TYPE_COLORS` instead) — available if real icons are
wanted in the battle/party UI.

## What's NOT here (by design)

No real Pokémon assets, sprites, or species data anywhere — verified both
source repos contain none (the PokeMMO-clone repo's "Pokémon" integration
was an unshipped, PokeAPI-fetching feature this project never touches).
