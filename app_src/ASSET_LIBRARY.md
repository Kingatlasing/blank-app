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

## 6. Building interiors (`interior_tiled.js` → `INTERIOR_TILED.atlas`, `.maps`)

Source: `Tuxemon/Tuxemon`, real Tiled interior maps from `mods/tuxemon/maps/`
(`healing_center.tmx`, `tuxe_mart_taba.tmx`, `professor_lab.tmx`,
`player_house_bedroom.tmx`, `player_house_downstairs.tmx`,
`classic_gym_astra.tmx`, `classic_gym_bravion.tmx`) and their `core_indoor_*`
tileset PNGs (16px tiles - a separate, more detailed art family from the 32px
outdoor `tuxmon-sample` set, so it gets its own atlas/image rather than
sharing the outdoor one). Packed the same way as the outdoor atlas: every
unique tile actually used across all 7 maps, deduped and slot-indexed into
one 384x112 PNG.

**Render contract:** same shape as `TILED` (`w`, `h`, `below`/`world`/`above`
flat slot arrays, `collide`) but no `grass`/`spawns` - interior warps always
carry explicit `tx`/`ty`. `map.tiledSrc: 'interior'` on a `MAPS.*` entry
switches the renderer/collision code (`tiledSourceFor()` in `engine.js`) from
`TILED`/`ATLAS_IMG` to `INTERIOR_TILED`/`INTERIOR_ATLAS_IMG`.

Seven interiors, wired to real building doors in the outdoor maps via
`extraWarps` (town/ashveld/crysthaven's own doors, plus 3 door tiles in
ashveld/crysthaven that had no walkable gap in the source collision data at
all - opened via `patchBuildingDoors()`, same pattern as the town gate fix):
`healing_center_town/_ashveld/_crysthaven` (nurse, heals party), `mart_town/
_ashveld/_crysthaven` (shopkeeper, opens the shop UI), `lab` (Professor
Larkspur, starter selection), `house_downstairs` + `house_bedroom` (player's
house, linked by their own stairs tile), `gym_ashveld` (Leader Sylva) /
`gym_crysthaven` (Leader Pyra) using the two different `classic_gym_*`
layouts. The Center/Mart layout is reused per-town (one real map, three
`MAPS.*` entries each with their own return-warp) since the source repo only
has one of each.

## 7. The wider Emberwild region (`classic_tiled.js` → `CLASSIC_TILED.atlas`, `.maps`)

Source: `Tuxemon/Tuxemon`, the real "classic continent" Tiled maps from
`mods/tuxemon/maps/classic_*.tmx` - 7 cities (`hearthrock`, `steamshore`,
`stormpeak`, `valorhold`, `aerolume`, `thornwood`, `umbrastar`) and 8
connecting routes (`classic_route1`..`classic_route8`), reachable from
Crysthaven's north edge. Yet another 16px tileset family
(`core_city_and_country`/`core_outdoor`/`core_buildings`/`core_outdoor_water`/
`core_outdoor_nature`/`core_set pieces`), distinct from both the outdoor
tuxmon-sample set and the `core_indoor_*` interior set, so it gets its own
atlas/image (`CLASSIC_ATLAS_IMG`) - `map.tiledSrc: 'classic'` on a `MAPS.*`
entry routes it there via the same `tiledSourceFor()` dispatch the interiors
use. Same render contract as `TILED`/`INTERIOR_TILED` (`w`/`h`/`below`/
`world`/`above`/`collide`, explicit `tx`/`ty` on every warp).

Every city-to-route and route-to-route connection (which tile warps to which
map, and exactly where you land) is copied directly from that map's own real
Tiled "Events" teleport objects - not invented. 6 of this region's real,
reachable Gym buildings are wired in as new Halls (`gym_hearthrock1/2`,
`gym_steamshore1/2`, `gym_stormpeak`, `gym_aerolume` - tiledSrc `'interior'`,
sharing `INTERIOR_TILED`'s atlas since gym interiors use the same
`core_indoor_*` family), each with a real Tuxemon leader sprite
(`leader_mila`, `leader_granite`, `leader_marin`, `leader_voltessa`,
`leader_zephra`, plus `leader_orion` standing in for the `classic_gym_pyra.tmx`
gym to avoid a same-name clash with Crysthaven's existing "Pyra"). Two of the
real gyms (`classic_gym_astra`/`classic_gym_bravion`) are deliberately not
reused here since Ashveld/Crysthaven already use them; `classic_gym_zephra`
is placed in Aerolume, which has no gym in the source data, rather than
inventing new art for a 6th Hall. Team rosters are original (Tuxemon's own
`db/npc/classic_gym_people.yaml` defines no teams for any of these leaders).
`healing_center`/`mart` (from section 6) are reused again for Hearthrock,
Steamshore, and Stormpeak, the 3 of these 7 cities whose real map data
includes an actual Center/Mart building (found by tile-ID matching against
Hearthrock's, then confirming each door via its own real collision gap - see
`patchBuildingDoors`-style comments in `engine.js`); the other 4 cities have
none in the source data, so none was added - Fast Travel covers healing
there instead. Valorhold/Thornwood/Umbrastar are real but sparse
(forest/open-field) connector cities with no gym.

## 7b. Battle HP bar and menu buttons (`ASSET_B64.battleui.hp_bar_frame` / `.menu_border`)

Source: `Tuxemon/Tuxemon`, `mods/tuxemon/gfx/ui/monster/hp_bar.png` (the real
HP-bar frame - a red "HP" tag plus a semi-transparent fill slot, 30x12 native)
and `mods/tuxemon/gfx/borders/borders-blue.png` (an 18x18 9-slice panel
border). Both replace flat CSS-drawn boxes that were there before. The HP
bar's colored fill (`.hpfill`, same green/yellow/red threshold logic as
before) is drawn under the frame image inside its real fill-slot bounds
(`.hpfilltrack`, offset 30%/16.7% from each edge - that PNG's own slot, not
guessed); the frame's semi-transparent interior shades it slightly, same
layering the source game uses. The border is applied via CSS
`border-image-slice`/`border-image-width` so its four corner/edge/center
tiles stretch to fit the prompt line, every battle-menu button, the move
grid, and the move-info panel, without needing a separate image per size.

## 8. Battle platform (`ASSET_B64.battleui.platform_oval`)

Source: `limbusdev/guardian_monsters_artwork` (CC BY-4.0), `backdrops/battle/
grass.png`. That file's own oval "arena glow" ground shape was cropped out
(chroma-keyed against its flat ground color) into a standalone transparent
PNG, since neither Tuxemon nor the PokeMMO-clone repo has an equivalent -
the classic games' battle screens always show each creature standing on an
oval platform, which the real Tuxemon battle backgrounds (section on battle
UI in `ATTRIBUTIONS.md`) don't include. Drawn by `renderBattleScene()` under
both combatants, sized/positioned separately for the (smaller, further-back)
opponent and the (larger, closer) player creature.

## What's NOT here (by design)

No real Pokémon assets, sprites, or species data anywhere — verified both
source repos contain none (the PokeMMO-clone repo's "Pokémon" integration
was an unshipped, PokeAPI-fetching feature this project never touches).
