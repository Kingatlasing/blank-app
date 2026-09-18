# Attributions

Emberwild Trails is an original creature-taming RPG. It contains no Nintendo/Game
Freak/The Pokémon Company assets, names, or characters. Its game code, story,
creature names/lore text, and UI are original, written for this project.

Creature stats/movesets/evolutions, item and technique data, and the world map
art are **adapted from two open-source projects**, used under their licenses:

## Tuxemon
https://github.com/Tuxemon/Tuxemon

- Code: GNU GPL-3.0
- Art assets (creature sprites, tilesets, character sprites): CC BY-SA 4.0
  (see that project's own `ATTRIBUTIONS.md` for the full per-asset artist credit
  list — contributors include Mike Bramson, William Edwards, Sanglorian,
  tamashihoshi, Leo, josepharaoh99, and others)

Used for: the 165-creature roster (names, types, base stats, movesets,
evolutions, species classification, height/weight, and Bestiary flavor text -
the last of these from that project's own `l18n/en_US/LC_MESSAGES/base.po`
locale file), moves/techniques, items, and monster battle sprites. Also used
for the thirteen interior maps buildings can be entered into (Monster Center,
Mart, Professor's Lab, player's house bedroom + downstairs, eight Arena Hall
layouts), taken directly from that project's own Tiled interior maps
(`mods/tuxemon/maps/healing_center.tmx`, `tuxe_mart_taba.tmx`,
`professor_lab.tmx`, `player_house_bedroom.tmx`, `player_house_downstairs.tmx`,
`classic_gym_astra.tmx`, `classic_gym_bravion.tmx`, `classic_gym_mila.tmx`,
`classic_gym_granite.tmx`, `classic_gym_marin.tmx`, `classic_gym_pyra.tmx`,
`classic_gym_voltessa.tmx`, `classic_gym_zephra.tmx`) and their matching
`core_indoor_floors`/`core_indoor_walls`/`core_set pieces` tileset art —
extracted tile-for-tile with their original furniture/collision layout,
nothing hand-built or invented.

Also used for a second connected region north of Crysthaven: seven more
cities and eight connecting routes from Tuxemon's own "classic continent" map
set (`mods/tuxemon/maps/classic_*.tmx` - `classic_hearthrock_city.tmx`,
`classic_steamshore_city.tmx`, `classic_stormpeak_city.tmx`,
`classic_valorhold_city.tmx`, `classic_aerolume_city.tmx`,
`classic_thornwood_city.tmx`, `classic_umbrastar_city.tmx`,
`classic_route_1.tmx` through `classic_route_8.tmx`) and their tileset art
(`core_city_and_country`/`core_outdoor`/`core_buildings`/`core_outdoor_water`/
`core_outdoor_nature`/`core_set pieces`), extracted the same tile-for-tile
way. Which map connects to which, and at what tile, is taken directly from
each map's own real Tiled warp/teleport data, not invented. The six new Arena
Leaders (Mila, Granite, Marin, Orion, Voltessa, Zephra) use Tuxemon's own
real NPC sprites for those exact gym slugs (`leader_mila`, `leader_granite`,
etc., from `mods/tuxemon/sprites/`); their team rosters and dialogue are
original, since Tuxemon's own NPC database
(`mods/tuxemon/db/npc/classic_gym_people.yaml`) defines no teams for any of
them.

The battle screen itself (background art and each combatant's name/level/HP
card frame) also uses Tuxemon's own real battle UI assets from
`mods/tuxemon/gfx/ui/combat/` (`grass_background.png`, `stadium_background.png`,
`hp_player_nohp.png`, `hp_opponent_nohp.png`) in place of the flat CSS
backgrounds/boxes used before - picked by context (a Hall battle gets the
real stadium art, everything else gets the real forest/grass art), not drawn
or invented for this project.

The actual HP fill bar (previously a flat CSS `<div>`) and every button/panel
in the bottom battle menu (previously flat `border-radius` CSS boxes) also
use real Tuxemon UI art: `mods/tuxemon/gfx/ui/monster/hp_bar.png` (the HP-bar
frame with its own "HP" tag and fill slot) and `mods/tuxemon/gfx/borders/
borders-blue.png` (a 9-slice panel border, applied via CSS `border-image`
so it can stretch to any button/panel size without being redrawn).

## Guardian Monsters Artwork
https://github.com/limbusdev/guardian_monsters_artwork

- License: CC BY-4.0 ("Includes Guardian Monsters Artwork by Georg Eckert /
  lucidtanooki")

Used for one element only: the oval ground platform each creature stands on
in battle (`backdrops/battle/grass.png`, cropped down to just its glowing
oval ring and made transparent around it). Neither Tuxemon nor the
PokeMMO-clone repo has an equivalent asset, and this platform shape isn't
drawn/invented for this project - it's a real, licensed graphic from
another open-source monster-battler, cropped (not redrawn) from its source
file.

## PokeMMO-Online-Realtime-Multiplayer-Game
https://github.com/aaron5670/PokeMMO-Online-Realtime-Multiplayer-Game

- Code: WTFPL
- Tileset: `tuxmon-sample-32px` (CC BY-SA, part of the Tuxemon project,
  distributed with this repo's Phaser/Tiled sample)
- Map data: `town.json`, `route1.json`, `ashveld.json`, `route2.json`,
  `crysthaven.json` (Tiled/JSON tilemaps built by that project against the
  tuxmon-sample tileset), plus the `misa`-style character sprite conventions

Used for: the overworld tile art (grass/path/water/trees/fences/fountains),
every building facade (Monster Center, Mart, Hall, houses), and the layout of
the game's five connected maps (Cottonwood Town, Route 1, Ashveld Town,
Route 2, Crysthaven City), rendered here through an original tile-atlas
renderer built for this project.

Both projects were verified before use to contain **no ripped or
API-fetched Pokémon character assets** — Tuxemon's creatures are wholly
original designs, and the PokeMMO-clone repo's own "Pokémon" integration was
an unfinished, never-shipped feature that this project does not use.

## This project's own code

Everything else — the game engine (movement, camera, battle system, dialogue,
quests, save/load, UI), the story and world-building script, the villain
faction reflavoring ("Enforcers"), and the specific NPC placements/quest
design — is original work written for this repository.

If you redistribute this project, keep this file and honor the CC BY-SA / GPL
terms above for the adapted assets and data.
