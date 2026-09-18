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
evolutions), moves/techniques, items, and monster battle sprites.

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
