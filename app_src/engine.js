'use strict';
/* ============================================================================
   MONSTER TAMER: EMBERWILD TRAILS
   An original creature-collecting RPG. Creature/item/move data and pixel art
   are adapted from the open-source Tuxemon project (github.com/Tuxemon/Tuxemon,
   GPL-3.0 code / CC-BY-SA 4.0 art). See ATTRIBUTIONS.md for full credit.
   All game code, world design, story, and UI in this file are original.
============================================================================ */

/* ---------------------------- Image loading ---------------------------- */
const IMG = { monsters: {}, items: {}, tiles: {}, chars: {}, elements: {}, buildings: {}, battleui: {} };
let ATLAS_IMG = null;
const ATLAS_COLS = TILED.atlasCols;
// Building interiors (Pokemon Center, Mart, Lab, player's house, Gyms) use a second,
// separate atlas: real Tuxemon TMX interior maps, a different tileset (16px "core_indoor_*"
// furniture/walls/floors) from the 32px outdoor tuxmon-sample set. Kept as its own
// atlas/image rather than merged into the outdoor one since the source art is a distinct family.
let INTERIOR_ATLAS_IMG = null;
const INTERIOR_ATLAS_COLS = INTERIOR_TILED.atlasCols;
const INTERIOR_SRC_TILE = 16;
// A third atlas: the "classic continent" outdoor maps (7 cities + 8 routes, real
// Tuxemon TMX data) use yet another 16px tileset family (core_city_and_country/
// core_outdoor/core_buildings/etc.) distinct from both the tuxmon-sample outdoor
// set and the core_indoor_* interior set, so it gets its own atlas/image too.
let CLASSIC_ATLAS_IMG = null;
const CLASSIC_ATLAS_COLS = CLASSIC_TILED.atlasCols;
const CLASSIC_SRC_TILE = 16;
let imagesLoaded = 0, imagesTotal = 0;
function loadAllImages(cb) {
  const cats = ['monsters', 'items', 'tiles', 'chars', 'elements', 'buildings', 'battleui'];
  for (const cat of cats) {
    for (const key in ASSET_B64[cat]) imagesTotal++;
  }
  imagesTotal += 3; // world atlas + interior atlas + classic atlas
  ATLAS_IMG = new Image();
  ATLAS_IMG.onload = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
  ATLAS_IMG.onerror = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
  ATLAS_IMG.src = 'data:image/png;base64,' + TILED.atlas;
  INTERIOR_ATLAS_IMG = new Image();
  INTERIOR_ATLAS_IMG.onload = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
  INTERIOR_ATLAS_IMG.onerror = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
  INTERIOR_ATLAS_IMG.src = 'data:image/png;base64,' + INTERIOR_TILED.atlas;
  CLASSIC_ATLAS_IMG = new Image();
  CLASSIC_ATLAS_IMG.onload = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
  CLASSIC_ATLAS_IMG.onerror = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
  CLASSIC_ATLAS_IMG.src = 'data:image/png;base64,' + CLASSIC_TILED.atlas;
  for (const cat of cats) {
    for (const key in ASSET_B64[cat]) {
      const im = new Image();
      im.onload = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
      im.onerror = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
      im.src = 'data:image/png;base64,' + ASSET_B64[cat][key];
      IMG[cat][key] = im;
    }
  }
}

/* ---------------------------- Map data patch ---------------------------- */
// Some buildings in the source maps sit close enough together that a
// border/ornamental tree lands in the narrow gap between their roof-cap
// (Above Player layer) runs on the same row, with no roof covering it -
// so a tree pokes up right in the middle of what should read as one
// continuous roofline. Find every such gap, on every map, and clear the
// tree there (falls back to plain grass) so no roof ever looks broken.
(function patchMissingRoofs() {
  // Searched every row of every map for a building (a wide run of non-tree
  // "World" wall/window tiles) whose topmost row has no roof-cap in the
  // Above layer and isn't itself continuing an existing wall above it -
  // i.e. a building with no roof at all, bottom-to-top. Found exactly one:
  // this 9-wide tower in town whose roof-cap was simply never placed in
  // the source map. Rather than inventing new art, this overlay is a real
  // crop of the SAME building's own roof from elsewhere in the same source
  // tileset (identical width, identical style) - see roofcap_tower asset.
  TILED.maps.town.overlays = [
    { x: 18, y: 0, w: 9, h: 2, img: 'roofcap_tower' },
  ];
})();

(function patchTreesInRoofGaps() {
  const TREE_SLOTS = new Set([12, 13, 16, 17]);
  const MAX_GAP = 3;
  for (const name in TILED.maps) {
    const td = TILED.maps[name];
    const w = td.w, h = td.h;
    for (let y = 0; y < h; y++) {
      let runs = [], curStart = null;
      for (let x = 0; x <= w; x++) {
        const has = x < w && td.above[y * w + x] > 0;
        if (has && curStart === null) curStart = x;
        if (!has && curStart !== null) { runs.push([curStart, x - 1]); curStart = null; }
      }
      for (let i = 0; i < runs.length - 1; i++) {
        const gapStart = runs[i][1] + 1, gapEnd = runs[i + 1][0] - 1;
        if (gapEnd - gapStart + 1 > MAX_GAP) continue;
        for (let x = gapStart; x <= gapEnd; x++) {
          const i = y * w + x;
          if (TREE_SLOTS.has(td.world[i])) { td.world[i] = 0; td.collide[i] = false; }
        }
      }
    }
  }
})();

// The source maps leave a walkable gap directly at the base of some border
// trees (e.g. narrow alleys between buildings). Standing there is never
// actually broken - the player sprite still draws correctly in front of the
// tree - but it looks wrong at a glance (player squeezed right against/under
// the canopy), so we extend each such tree's collision by one tile downward
// at load time. This only touches collision, never the visuals/tile data.
(function patchUnreachableWarps() {
  // town's south wall (row 37, a solid fence/railing tile per the source
  // tileset's own "collides" property) has no gap aligned with the route1
  // exit corridor directly below it (row 38-39, x17-22) - a dead end in the
  // source map that leaves the plaza with no way to actually reach route1.
  // Verified with a full flood-fill from the spawn point: every other warp
  // in every map is reachable; this is the one exception. Open a matching
  // gate in that wall so the exit is actually usable.
  const t = TILED.maps.town;
  for (let x = 17; x <= 22; x++) t.collide[37 * t.w + x] = false;
})();

(function patchBuildingDoors() {
  // The Pokemon Center / Mart / Gym buildings in ashveld and crysthaven (unlike
  // their equivalents in town) have a fully solid bottom wall in the source map -
  // no door tile was ever cut into the collision data anywhere along their front,
  // confirmed by scanning every tile of each building's footprint. These are the
  // exact buildings these interiors are now wired to (see the new healing_center_*/
  // mart_*/gym_* MAPS entries and their matching extraWarps below), so each needs
  // one real, walkable doorway. Open a single tile at the spot the original NPCs
  // (nurse/shopkeeper/leader) already stood at, which lines up with the middle of
  // each building's front wall.
  const doors = [
    ['ashveld', 7, 7], ['ashveld', 32, 7], ['ashveld', 11, 26],
    ['crysthaven', 6, 7], ['crysthaven', 15, 7], ['crysthaven', 34, 18],
  ];
  for (const [mapKey, x, y] of doors) {
    const td = TILED.maps[mapKey];
    td.collide[y * td.w + x] = false;
  }
})();

(function patchCrysthavenNorthRoad() {
  // Crysthaven's entire north border is a solid tree line except the existing
  // 6-tile route2 gap (x21-26) - confirmed by scanning the whole row. The new
  // road north to Hearthrock (see crysthaven's extraWarps) needs its own gap,
  // clear of that one, rather than colliding with the real route2 exit.
  const t = TILED.maps.crysthaven;
  for (const y of [0, 1]) t.collide[y * t.w + 35] = false;
})();

(function patchBadSpawnPoints() {
  // crysthaven's own "Spawn Point"/"from-route2" marker sits on a solid tile
  // in the source map (inside a building's footprint) - a pre-existing
  // authoring issue in that map file, not something this project introduced.
  // Nudge it to the nearest open tile so arriving from route2 never drops
  // the player inside a wall.
  const c = TILED.maps.crysthaven;
  if (c && c.spawns['from-route2']) {
    c.spawns['from-route2'] = { x: 24, y: 4 };
    c.spawns['Spawn Point'] = { x: 24, y: 4 };
  }
})();

(function patchTreeCollision() {
  const TREE_SLOTS = new Set([12, 13, 16, 17]);
  for (const name in TILED.maps) {
    const td = TILED.maps[name];
    const w = td.w, h = td.h;
    for (let y = 0; y < h - 1; y++) {
      for (let x = 0; x < w; x++) {
        if (TREE_SLOTS.has(td.world[y * w + x])) td.collide[(y + 1) * w + x] = true;
      }
    }
  }
})();

/* ---------------------------- Constants ---------------------------- */
const SRC_TILE = 32; // native pixel size of the source tile/atlas art
const TILE = 64; // on-screen rendered tile size - a clean 2x integer upscale of SRC_TILE.
// IMPORTANT: canvas.width/height are set to exactly VIEW_COLS*TILE / VIEW_ROWS*TILE, and the
// canvas's CSS box is given those same pixel dimensions (see shell CSS) so the browser never
// stretches the canvas by a fractional amount. A non-integer CSS scale on a pixel-art canvas
// causes 1px seams right at tile boundaries (this is what made trees look "cut in half").
const VIEW_COLS = 15, VIEW_ROWS = 10;
const TYPE_COLORS = {
  fire:'#e0562b', water:'#2f8fd6', wood:'#4a9c3e', earth:'#a9752f', metal:'#8c95a3',
  lightning:'#e0c72b', frost:'#7fd6e0', sky:'#8fb8e6', shadow:'#5a4a7a', venom:'#8a4fae',
  cosmic:'#4a3a8a', normal:'#b7b2a3', heroic:'#e0b23c'
};

/* ---------------------------- Custom (non-Tuxemon) narrative items ---------------------------- */
ITEMS_DB.bridge_pass = { slug: 'bridge_pass', name: 'Bridge Pass', description: 'Proof you cleared the Enforcer Outpost. Lets you cross into the Summit.', category: 'key', cost: 0 };

/* ---------------------------- Starters & roster helpers ---------------------------- */
const STARTERS = ['agnite', 'axolightl', 'anoleaf'];

function speciesFamily(slug) {
  // walk down evolution chain slugs starting from a base to build ordered array (not required elsewhere)
  return slug;
}

function computeDerivedStats(monster, level) {
  const a = monster.stats;
  return {
    hp: Math.floor(a.hp * 3.2 + level * 2.4) + 10,
    atk: Math.floor(a.melee * 2.1 + level * 1.15) + 5,
    ranged: Math.floor(a.ranged * 2.1 + level * 1.15) + 5,
    def: Math.floor(a.armour * 1.9 + level * 0.95) + 5,
    spd: Math.floor(a.speed * 1.9 + level * 0.85) + 5,
    eva: a.dodge
  };
}

function expToNext(level) { return Math.floor(level * level * 6 + 24); }

function createMonsterInstance(slug, level, opts) {
  opts = opts || {};
  const def = MONSTERS[slug];
  const derived = computeDerivedStats(def, level);
  const inst = {
    slug, level, exp: 0,
    currentHP: derived.hp,
    derived,
    nickname: opts.nickname || null,
    status: null,
    id: 'm' + Math.random().toString(36).slice(2, 10)
  };
  return inst;
}

function monsterDisplayName(inst) {
  return inst.nickname || MONSTERS[inst.slug].name;
}

function getActiveMoves(inst) {
  const def = MONSTERS[inst.slug];
  const learned = def.moveset.filter(m => m.level <= inst.level).sort((a, b) => a.level - b.level);
  const uniq = [];
  const seen = new Set();
  for (let i = learned.length - 1; i >= 0 && uniq.length < 4; i--) {
    if (!seen.has(learned[i].technique)) { seen.add(learned[i].technique); uniq.unshift(learned[i].technique); }
  }
  if (uniq.length === 0) uniq.push('struggle');
  return uniq.map(t => TECHNIQUES[t]).filter(Boolean);
}

function typeEffectiveness(atkType, defTypes) {
  let mult = 1;
  const chart = ELEMENTS[atkType];
  if (!chart) return 1;
  for (const dt of defTypes) mult *= (chart[dt] != null ? chart[dt] : 1);
  return mult;
}

function maybeEvolve(inst, log) {
  const def = MONSTERS[inst.slug];
  for (const ev of def.evolutions) {
    if (inst.level >= ev.level && MONSTERS[ev.to]) {
      const oldName = monsterDisplayName(inst);
      inst.slug = ev.to;
      log.push(oldName + ' evolved into ' + MONSTERS[ev.to].name + '!');
      const nd = computeDerivedStats(MONSTERS[ev.to], inst.level);
      const hpFrac = inst.currentHP / inst.derived.hp;
      inst.derived = nd;
      inst.currentHP = Math.max(1, Math.floor(nd.hp * hpFrac));
      break;
    }
  }
}

function grantExp(inst, amount, log) {
  inst.exp += amount;
  let leveled = false;
  while (inst.exp >= expToNext(inst.level) && inst.level < 60) {
    inst.exp -= expToNext(inst.level);
    inst.level++;
    const hpFrac = inst.currentHP / inst.derived.hp;
    inst.derived = computeDerivedStats(MONSTERS[inst.slug], inst.level);
    inst.currentHP = Math.min(inst.derived.hp, Math.floor(inst.derived.hp * hpFrac) + Math.floor(inst.derived.hp * 0.15));
    leveled = true;
    log.push(monsterDisplayName(inst) + ' grew to level ' + inst.level + '!');
    maybeEvolve(inst, log);
  }
  return leveled;
}

/* ---------------------------- Game State ---------------------------- */
const state = {
  screen: 'boot', // boot, title, overworld, battle, menu, dialogue, minigame
  map: 'town',
  x: 20, y: 36, px: 0, py: 0, facing: 'up', moving: false, animFrame: 0, animTimer: 0,
  party: [],
  boxParty: [],
  inventory: { potion: 3, tuxeball: 5 },
  money: 500,
  flags: {},
  badges: [],
  stepCounter: 0,
  encounterCooldown: 0,
  camera: { x: 0, y: 0 },
  dex: {}, // slug -> 'seen' | 'caught', for the Bestiary screen
  visitedCenters: {}, // MAPS key of every healing_center_* interior visited, for Fast Travel
  biking: false
};

function markDexSeen(slug) { if (!state.dex[slug]) state.dex[slug] = 'seen'; }
function markDexCaught(slug) { state.dex[slug] = 'caught'; }

function addItem(slug, n) { state.inventory[slug] = (state.inventory[slug] || 0) + n; }
function removeItem(slug, n) {
  state.inventory[slug] = (state.inventory[slug] || 0) - n;
  if (state.inventory[slug] <= 0) delete state.inventory[slug];
}

/* ---------------------------- Tile legend ---------------------------- */
const TILE_DEF = {
  '.': { img: 'grass' },
  '#': { img: 'path' },
  '~': { img: 'water', solid: true },
  'R': { img: 'grass', solid: true }, // outdoor border (tree-lined, see objects)
  'X': { img: 'rocktexture', solid: true }, // dungeon wall
  'F': { img: 'cavefloor' },
  'g': { img: 'grass', encounter: true },
};
const BUILDING_DIMS = {
  b_mart: { w: 5, h: 4 }, b_center: { w: 5, h: 4 }, b_tower: { w: 9, h: 10 },
  b_cabin: { w: 6, h: 4 }, b_small: { w: 5, h: 4 }, b_fountain: { w: 3, h: 3 },
  b_bigtree: { w: 2, h: 2 }, b_arena: { w: 5, h: 4 },
};

/* ---------------------------- Map authoring helpers ---------------------------- */
function mkRows(strs) { return strs.map(s => s.split('')); }

/* ================================ MAPS ================================ */
const MAPS = {};

// Real, professionally-built world maps (town/route1/ashveld/route2/crysthaven) sourced
// from the Tiled map files in aaron5670/PokeMMO-Online-Realtime-Multiplayer-Game
// (WTFPL code; tuxmon-sample tileset CC-BY-SA - see ATTRIBUTIONS.md). We render their
// real tile layers + collision data via TILED, and place our own NPCs/trainers/quests on top.

MAPS.town = {
  tiledKey: 'town', name: 'Cottonwood Town',
  npcs: [
    { id: 'rival', x: 18, y: 35, sprite: 'rival', facing: 'down', dialogue: rivalHometownDialogue },
  ],
  // Nurse, shopkeeper, professor and mom used to stand outside on these exact
  // tiles; they've moved inside their buildings (see the new interior MAPS
  // entries below) and these are now the buildings' front doors instead.
  extraWarps: [
    { x: 9, y: 17, w: 1, h: 1, to: 'healing_center_town', tx: 6, ty: 10 },
    { x: 17, y: 17, w: 1, h: 1, to: 'mart_town', tx: 6, ty: 10 },
    { x: 26, y: 17, w: 1, h: 1, to: 'lab', tx: 6, ty: 17 },
    { x: 8, y: 35, w: 1, h: 1, to: 'house_downstairs', tx: 4, ty: 6 },
  ],
  encounterTable: [],
};

MAPS.route1 = {
  tiledKey: 'route1', name: 'Route 1',
  npcs: [
    { id: 'grunt1', x: 20, y: 14, sprite: 'enforcer_grunt', facing: 'down', trainer: {
        name: 'Enforcer Grunt', team: [{ slug: 'poinchin', level: 4 }, { slug: 'grimachin', level: 5 }],
        prizeMoney: 80, flag: 'grunt1_defeated',
        preBattle: ["The Enforcers claim this route now.", "Hand over your creatures... or battle!"],
        postWin: ["Ugh! I'll report this to the Commander..."],
      } },
  ],
  encounterTable: [
    { slug: 'aardorn', min: 2, max: 4, w: 5 }, { slug: 'chickadee', min: 2, max: 4, w: 5 },
    { slug: 'elofly', min: 2, max: 4, w: 4 }, { slug: 'poinchin', min: 2, max: 4, w: 3 },
    { slug: 'capiti', min: 2, max: 4, w: 3 },
  ],
};

MAPS.ashveld = {
  tiledKey: 'ashveld', name: 'Ashveld Town',
  npcs: [
    { id: 'sidequest_giver', x: 8, y: 16, sprite: 'townsfolk1', facing: 'down', dialogue: lostPetDialogue },
    { id: 'minigame_host', x: 18, y: 16, sprite: 'townsfolk2', facing: 'down', minigame: true },
  ],
  extraWarps: [
    { x: 7, y: 7, w: 1, h: 1, to: 'healing_center_ashveld', tx: 6, ty: 10 },
    { x: 32, y: 7, w: 1, h: 1, to: 'mart_ashveld', tx: 6, ty: 10 },
    { x: 11, y: 26, w: 1, h: 1, to: 'gym_ashveld', tx: 10, ty: 19 },
  ],
  encounterTable: [],
};

MAPS.route2 = {
  tiledKey: 'route2', name: 'Route 2',
  objects: [
    { x: 8, y: 8, key: 'berry', w: 1, h: 1, solid: false, pickup: { item: 'super_potion', flag: 'ww_berry1' } },
    { x: 30, y: 9, key: 'berry', w: 1, h: 1, solid: false, pickup: { item: 'tuxeball_refined', flag: 'ww_berry2' } },
    { x: 15, y: 22, key: 'berry', w: 1, h: 1, solid: false, pickup: { item: 'antidote_grapes', flag: 'ww_berry3' } },
  ],
  npcs: [
    { id: 'lostpet', x: 20, y: 15, sprite: 'townsfolk1', facing: 'down', wildFixed: { slug: 'chillimp', level: 8 },
      dialogue: null },
  ],
  encounterTable: [
    { slug: 'chillimp', min: 6, max: 9, w: 4 }, { slug: 'caper', min: 6, max: 9, w: 4 },
    { slug: 'uneye', min: 6, max: 9, w: 3 }, { slug: 'noctula', min: 6, max: 9, w: 3 },
    { slug: 'tumbleworm', min: 6, max: 9, w: 3 },
  ],
};

MAPS.crysthaven = {
  tiledKey: 'crysthaven', name: 'Crysthaven City',
  npcs: [
    { id: 'guide', x: 25, y: 7, sprite: 'townsfolk2', facing: 'down', dialogue: bridgeGuideDialogue },
    { id: 'outpost_gate', x: 24, y: 35, sprite: 'townsfolk1', facing: 'down',
      dialogue: () => (state.flags.enforcerDefeated ? ["The Enforcer Outpost is cleared out for good."] :
        ["The Enforcers are holed up south of here.", "Someone should really do something about that..."]) },
    { id: 'summit_sign', x: 28, y: 35, sprite: 'townsfolk2', facing: 'down',
      dialogue: () => (!state.flags.enforcerDefeated ? ["This path is closed until the Enforcer trouble is dealt with."] :
        state.badges.length < 8 ? ["The Summit only opens to a trainer holding all eight badges.", "You have " + state.badges.length + " so far."] :
        ["The path south leads to the Summit and the Champion.", "Good luck out there."]) },
    { id: 'north_road_sign', x: 35, y: 1, sprite: 'townsfolk1', facing: 'down',
      dialogue: () => ["The road north leads out of Crysthaven into the wider Emberwild region.", "Hearthrock, Steamshore, and five more Halls lie that way - plenty more badges to earn."] },
  ],
  extraWarps: [
    { x: 24, y: 36, w: 1, h: 1, to: 'enforcerhideout', tx: 6, ty: 10, requires: null },
    { x: 28, y: 36, w: 1, h: 1, to: 'summitplateau', tx: 7, ty: 12, requires: 'enforcerDefeated', requiresBadges: 8 },
    { x: 6, y: 7, w: 1, h: 1, to: 'healing_center_crysthaven', tx: 6, ty: 10 },
    { x: 15, y: 7, w: 1, h: 1, to: 'mart_crysthaven', tx: 6, ty: 10 },
    { x: 34, y: 18, w: 1, h: 1, to: 'gym_crysthaven', tx: 10, ty: 19 },
    { x: 35, y: 0, w: 1, h: 1, to: 'hearthrock', tx: 20, ty: 19 },
  ],
  encounterTable: [],
};

MAPS.enforcerhideout = {
  name: 'Enforcer Outpost',
  w: 14, h: 12,
  indoor: true,
  tiles: mkRows([
    'XXXXXXXXXXXXXX',
    'XFFFFFFFFFFFFX',
    'XFFFFFFFFFFFFX',
    'XFFXXXXXXXFFFX',
    'XFFFFFFFFFFFFX',
    'XFFFFFFFFFFFFX',
    'XFFXXXXXXXFFFX',
    'XFFFFFFFFFFFFX',
    'XFFFFFFFFFFFFX',
    'XFFFFFFFFFFFFX',
    'XFFFFFFFFFFFFX',
    'XXXXXXXXXXXXXX',
  ]),
  objects: [],
  npcs: [
    { id: 'grunt2', x: 4, y: 4, sprite: 'enforcer_grunt', facing: 'down', trainer: {
        name: 'Enforcer Grunt', team: [{ slug: 'grimachin', level: 13 }, { slug: 'cataspike', level: 14 }],
        prizeMoney: 150, flag: 'grunt2_defeated',
        preBattle: ["No unauthorized visitors!"], postWin: ["Impossible..."],
      } },
    { id: 'grunt3', x: 9, y: 7, sprite: 'enforcer_grunt', facing: 'down', trainer: {
        name: 'Enforcer Grunt', team: [{ slug: 'uneye', level: 14 }, { slug: 'tumbleworm', level: 14 }],
        prizeMoney: 150, flag: 'grunt3_defeated',
        preBattle: ["You'll never reach the Commander!"], postWin: ["This isn't over!"],
      } },
    { id: 'commander', x: 6, y: 9, sprite: 'enforcer_boss', facing: 'up', trainer: {
        name: 'Enforcer Commander', team: [
          { slug: 'cackleen', level: 19 }, { slug: 'katacoon', level: 19 }, { slug: 'vamporm', level: 20 },
        ], prizeMoney: 1000, flag: 'commanderDefeated', keyItem: 'Bridge Pass', story: 'enforcerDefeated',
        preBattle: ["So, a would-be hero comes to stop the Enforcers.", "I've built an empire on stolen creatures. Try and take it from me!"],
        postWin: ["Impossible! ...Fine. We're finished here. FOR NOW."],
      } },
  ],
  warps: [{ x: 0, y: 10 }, { x: 0, y: 9 }].map(p => ({ ...p, to: 'crysthaven', tx: 24, ty: 34 })),
  encounterTable: [],
};

MAPS.summitplateau = {
  name: 'Summit Plateau',
  w: 14, h: 14,
  tiles: mkRows([
    'RRRRRRRRRRRRRR',
    'R............R',
    'R............R',
    'R............R',
    'R............R',
    'R............R',
    'R............R',
    'R............R',
    'R............R',
    'R............R',
    'R............R',
    'R............R',
    'R............R',
    'RRRRRRR..RRRRR',
  ]),
  objects: [
    { x: 2, y: 1, w: 9, h: 10, solid: true, building: 'b_tower', label: "Champion's Hall" },
  ],
  npcs: [
    { id: 'champion', x: 6, y: 11, sprite: 'champion', facing: 'up', trainer: {
        name: 'Champion Reyes', team: [
          { slug: 'agnidon', level: 25 }, { slug: 'ampystoma', level: 25 }, { slug: 'gectile', level: 25 },
          { slug: 'aardart', level: 26 },
        ], prizeMoney: 3000, flag: 'championDefeated', story: 'gameWon',
        preBattle: ["Few make it this far.", "I am Reyes, Champion of the Arena Circuit.", "Let's see if you deserve the title!"],
        postWin: ["...I don't believe it. You've done it.", "You are the new Champion. Congratulations, trainer."],
      } },
  ],
  warps: [{ x: 7, y: 13 }, { x: 8, y: 13 }].map(p => ({ ...p, to: 'crysthaven', tx: 24, ty: 1 })),
  encounterTable: [],
};

/* ---------------------------- Building interiors ---------------------------- */
// Real, complete Tuxemon interior maps (mods/tuxemon/maps/*.tmx - healing_center.tmx,
// tuxe_mart_taba.tmx, professor_lab.tmx, player_house_bedroom/downstairs.tmx,
// classic_gym_astra/bravion.tmx), extracted tile-for-tile with their own furniture and
// counter/collision layout (see INTERIOR_TILED in interior_tiled.js) - not hand-built.
// The Pokemon Center and Mart layout is reused per-town (three separate MAPS entries
// sharing one tiledKey) since only one of each exists in the source repo; each still
// has its own door/return-warp back to its own town.
MAPS.healing_center_town = {
  tiledKey: 'healing_center', tiledSrc: 'interior', name: 'Cottonwood Monster Center',
  npcs: [{ id: 'nurse', x: 5, y: 4, sprite: 'nurse', facing: 'down', heal: true, fastTravel: true,
    dialogue: () => ["Welcome to the Monster Center!", "Your creatures are fighting fit. Take care out there!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'town', tx: 9, ty: 17 }],
};
MAPS.healing_center_ashveld = {
  tiledKey: 'healing_center', tiledSrc: 'interior', name: 'Ashveld Monster Center',
  npcs: [{ id: 'nurse', x: 5, y: 4, sprite: 'nurse', facing: 'down', heal: true, fastTravel: true,
    dialogue: () => ["Welcome to the Monster Center!", "Your creatures are fighting fit. Take care out there!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'ashveld', tx: 7, ty: 7 }],
};
MAPS.healing_center_crysthaven = {
  tiledKey: 'healing_center', tiledSrc: 'interior', name: 'Crysthaven Monster Center',
  npcs: [{ id: 'nurse', x: 5, y: 4, sprite: 'nurse', facing: 'down', heal: true, fastTravel: true,
    dialogue: () => ["Rest up before you challenge Pyra - she battles hot!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'crysthaven', tx: 6, ty: 7 }],
};
MAPS.mart_town = {
  tiledKey: 'mart', tiledSrc: 'interior', name: 'Cottonwood Mart',
  npcs: [{ id: 'shopkeeper', x: 1, y: 5, sprite: 'shopkeeper', facing: 'down', shop: true,
    dialogue: () => ["Take a look at my wares!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'town', tx: 17, ty: 17 }],
};
MAPS.mart_ashveld = {
  tiledKey: 'mart', tiledSrc: 'interior', name: 'Ashveld Mart',
  npcs: [{ id: 'shopkeeper', x: 1, y: 5, sprite: 'shopkeeper', facing: 'down', shop: true,
    dialogue: () => ["Take a look at my wares!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'ashveld', tx: 32, ty: 7 }],
};
MAPS.mart_crysthaven = {
  tiledKey: 'mart', tiledSrc: 'interior', name: 'Crysthaven Mart',
  npcs: [{ id: 'shopkeeper', x: 1, y: 5, sprite: 'shopkeeper', facing: 'down', shop: true,
    dialogue: () => ["Welcome!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'crysthaven', tx: 15, ty: 7 }],
};
MAPS.lab = {
  tiledKey: 'lab', tiledSrc: 'interior', name: "Professor Larkspur's Lab",
  npcs: [{ id: 'professor', x: 4, y: 6, sprite: 'professor', facing: 'down', dialogue: professorDialogue }],
  extraWarps: [{ x: 6, y: 17, w: 1, h: 1, to: 'town', tx: 26, ty: 17 }],
};
MAPS.house_downstairs = {
  tiledKey: 'house_downstairs', tiledSrc: 'interior', name: "Player's House",
  npcs: [{ id: 'mom', x: 8, y: 3, sprite: 'townsfolk2', facing: 'down',
    dialogue: () => ["Off on an adventure already? Don't forget to visit Professor Larkspur first!"] }],
  extraWarps: [
    { x: 4, y: 6, w: 1, h: 1, to: 'town', tx: 8, ty: 35 },
    { x: 0, y: 1, w: 1, h: 1, to: 'house_bedroom', tx: 8, ty: 2 },
  ],
};
MAPS.house_bedroom = {
  tiledKey: 'house_bedroom', tiledSrc: 'interior', name: "Player's Bedroom",
  npcs: [],
  extraWarps: [{ x: 8, y: 2, w: 1, h: 1, to: 'house_downstairs', tx: 0, ty: 1 }],
};
MAPS.gym_ashveld = {
  tiledKey: 'gym_astra', tiledSrc: 'interior', name: 'Ashveld Hall',
  npcs: [{ id: 'leader_sylva', x: 10, y: 5, sprite: 'leader_sylva', facing: 'down', trainer: {
      name: 'Arena Leader Sylva', team: [
        { slug: 'anoleaf', level: 9 }, { slug: 'budaye', level: 9 }, { slug: 'chloragon', level: 10 },
      ], prizeMoney: 300, flag: 'sylva_defeated', badge: 'Bramble Badge', givesBike: true,
      preBattle: ["I am Sylva, Leader of the Ashveld Hall.", "Let's see if your team has truly grown!"],
      postWin: ["Impressive. Take this Bramble Badge as proof of your victory.", "Here, take my old bike too - you'll cover ground a lot faster with it. Press B to ride!"],
    } }],
  extraWarps: [{ x: 10, y: 19, w: 1, h: 1, to: 'ashveld', tx: 11, ty: 26 }],
};
MAPS.gym_crysthaven = {
  tiledKey: 'gym_bravion', tiledSrc: 'interior', name: 'Crysthaven Hall',
  npcs: [{ id: 'leader_pyra', x: 10, y: 5, sprite: 'leader_pyra', facing: 'down', trainer: {
      name: 'Arena Leader Pyra', team: [
        { slug: 'embra', level: 16 }, { slug: 'agnidon', level: 17 }, { slug: 'cardiling', level: 16 },
      ], prizeMoney: 600, flag: 'pyra_defeated', badge: 'Cinder Badge',
      preBattle: ["I'm Pyra. My creatures burn brighter than any rival's.", "Show me your fire!"],
      postWin: ["You've got real heat. Take the Cinder Badge."],
    } }],
  extraWarps: [{ x: 10, y: 19, w: 1, h: 1, to: 'crysthaven', tx: 34, ty: 18 }],
};

/* ------------------- The wider Emberwild region (6 more Halls) -------------------
   Real Tuxemon "classic continent" data: 7 cities + 8 connecting routes
   (mods/tuxemon/maps/classic_*.tmx) plus 6 of its Gym buildings - reachable north of
   Crysthaven. Connections below (which tile warps to which map, at which arrival
   tile) are taken directly from each map's own real Tiled "Events" teleport objects,
   not invented - the only design choices made here are: which 6 of that data's real,
   reachable gyms to use (skipping classic_gym_astra/bravion, already used by
   Ashveld/Crysthaven, to avoid two towns sharing an identical-looking gym), and where
   to put a 6th gym (aerolume) since that city's real data has none - a real, unused
   gym map (classic_gym_zephra.tmx) placed there rather than inventing new art.
   Leader names/sprites (leader_mila, leader_granite, leader_marin, leader_voltessa,
   leader_zephra) are Tuxemon's own real NPC sprites for these exact gyms - only team
   rosters and dialogue are original, since Tuxemon's own db leaves those blank
   (mods/tuxemon/db/npc/classic_gym_people.yaml has no team data for any of them).
   The steamshore gym on the real classic_gym_pyra.tmx map is named "Orion" (using the
   unused leader_orion sprite) rather than "Pyra" to avoid clashing with the existing
   Crysthaven leader of that name, who uses a different real map (gym_bravion). */
MAPS.gym_hearthrock1 = {
  tiledKey: 'gym_mila', tiledSrc: 'interior', name: 'Hearthrock Hall (Mila)',
  npcs: [{ id: 'leader_mila', x: 10, y: 5, sprite: 'leader_mila', facing: 'down', trainer: {
      name: 'Arena Leader Mila', team: [
        { slug: 'krokivip', level: 19 }, { slug: 'bigfin', level: 19 }, { slug: 'galasces', level: 20 },
      ], prizeMoney: 800, flag: 'mila_defeated', badge: 'Torrent Badge',
      preBattle: ["Welcome to Hearthrock. I'm Mila.", "Let's see how you handle the current!"],
      postWin: ["Well fought. Take the Torrent Badge."],
    } }],
  extraWarps: [{ x: 10, y: 19, w: 1, h: 1, to: 'hearthrock', tx: 18, ty: 12 }],
};
MAPS.gym_hearthrock2 = {
  tiledKey: 'gym_granite', tiledSrc: 'interior', name: 'Hearthrock Hall (Granite)',
  npcs: [{ id: 'leader_granite', x: 10, y: 5, sprite: 'leader_granite', facing: 'down', trainer: {
      name: 'Arena Leader Granite', team: [
        { slug: 'grintrock', level: 22 }, { slug: 'bricgard', level: 22 }, { slug: 'deviraptor', level: 23 },
      ], prizeMoney: 900, flag: 'granite_defeated', badge: 'Boulder Badge',
      preBattle: ["Hearthrock's second Hall. I'm Granite.", "My team won't budge easily."],
      postWin: ["Solid effort. Take the Boulder Badge."],
    } }],
  extraWarps: [{ x: 10, y: 19, w: 1, h: 1, to: 'hearthrock', tx: 23, ty: 12 }],
};
MAPS.gym_steamshore1 = {
  tiledKey: 'gym_marin', tiledSrc: 'interior', name: 'Steamshore Hall (Marin)',
  npcs: [{ id: 'leader_marin', x: 10, y: 5, sprite: 'leader_marin', facing: 'down', trainer: {
      name: 'Arena Leader Marin', team: [
        { slug: 'katacoon', level: 25 }, { slug: 'tigrock', level: 25 }, { slug: 'dynastor', level: 26 },
      ], prizeMoney: 1000, flag: 'marin_defeated', badge: 'Anchor Badge',
      preBattle: ["Steamshore's harbor Hall. I'm Marin.", "My team is built like the docks - unshakable."],
      postWin: ["Good match. Take the Anchor Badge."],
    } }],
  extraWarps: [{ x: 10, y: 19, w: 1, h: 1, to: 'steamshore', tx: 31, ty: 5 }],
};
MAPS.gym_steamshore2 = {
  tiledKey: 'gym_pyra', tiledSrc: 'interior', name: 'Steamshore Hall (Orion)',
  npcs: [{ id: 'leader_orion', x: 10, y: 5, sprite: 'leader_orion', facing: 'down', trainer: {
      name: 'Arena Leader Orion', team: [
        { slug: 'eyesore', level: 28 }, { slug: 'dragarbor', level: 28 }, { slug: 'seraphice', level: 29 },
      ], prizeMoney: 1100, flag: 'orion_defeated', badge: 'Starfall Badge',
      preBattle: ["I'm Orion. My team answers to the stars.", "Let's see if your journey has aligned you well."],
      postWin: ["A battle well written in the stars. Take the Starfall Badge."],
    } }],
  extraWarps: [{ x: 10, y: 19, w: 1, h: 1, to: 'steamshore', tx: 23, ty: 15 }],
};
MAPS.gym_stormpeak = {
  tiledKey: 'gym_voltessa', tiledSrc: 'interior', name: 'Stormpeak Hall',
  npcs: [{ id: 'leader_voltessa', x: 10, y: 5, sprite: 'leader_voltessa', facing: 'down', trainer: {
      name: 'Arena Leader Voltessa', team: [
        { slug: 'apeoro', level: 31 }, { slug: 'ouroboutlet', level: 31 }, { slug: 'lightmare', level: 32 },
      ], prizeMoney: 1300, flag: 'voltessa_defeated', badge: 'Storm Badge',
      preBattle: ["Stormpeak's Hall, up where the lightning lives.", "I'm Voltessa. Try to keep up."],
      postWin: ["You held your ground up here. Take the Storm Badge."],
    } }],
  extraWarps: [{ x: 10, y: 19, w: 1, h: 1, to: 'stormpeak', tx: 5, ty: 4 }],
};
MAPS.gym_aerolume = {
  tiledKey: 'gym_zephra', tiledSrc: 'interior', name: 'Aerolume Hall',
  npcs: [{ id: 'leader_zephra', x: 10, y: 5, sprite: 'leader_zephra', facing: 'down', trainer: {
      name: 'Arena Leader Zephra', team: [
        { slug: 'eaglace', level: 34 }, { slug: 'elostorm', level: 34 }, { slug: 'gryfix', level: 35 },
      ], prizeMoney: 1500, flag: 'zephra_defeated', badge: 'Gale Badge',
      preBattle: ["Aerolume's Hall - just a gym in an open field, but don't underestimate it.", "I'm Zephra. Let's fly."],
      postWin: ["You matched my pace. Take the Gale Badge."],
    } }],
  extraWarps: [{ x: 10, y: 19, w: 1, h: 1, to: 'aerolume', tx: 20, ty: 11 }],
};

MAPS.healing_center_hearthrock = {
  tiledKey: 'healing_center', tiledSrc: 'interior', name: 'Hearthrock Monster Center',
  npcs: [{ id: 'nurse', x: 5, y: 4, sprite: 'nurse', facing: 'down', heal: true, fastTravel: true,
    dialogue: () => ["Welcome to the Monster Center!", "Hearthrock's Halls are tough - rest up before you challenge them."] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'hearthrock', tx: 8, ty: 12 }],
};
MAPS.mart_hearthrock = {
  tiledKey: 'mart', tiledSrc: 'interior', name: 'Hearthrock Mart',
  npcs: [{ id: 'shopkeeper', x: 1, y: 5, sprite: 'shopkeeper', facing: 'down', shop: true,
    dialogue: () => ["Take a look at my wares!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'hearthrock', tx: 13, ty: 12 }],
};
MAPS.healing_center_steamshore = {
  tiledKey: 'healing_center', tiledSrc: 'interior', name: 'Steamshore Monster Center',
  npcs: [{ id: 'nurse', x: 5, y: 4, sprite: 'nurse', facing: 'down', heal: true, fastTravel: true,
    dialogue: () => ["Welcome to the Monster Center!", "Your creatures are fighting fit. Take care out there!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'steamshore', tx: 33, ty: 15 }],
};
MAPS.mart_steamshore = {
  tiledKey: 'mart', tiledSrc: 'interior', name: 'Steamshore Mart',
  npcs: [{ id: 'shopkeeper', x: 1, y: 5, sprite: 'shopkeeper', facing: 'down', shop: true,
    dialogue: () => ["Take a look at my wares!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'steamshore', tx: 28, ty: 15 }],
};
MAPS.healing_center_stormpeak = {
  tiledKey: 'healing_center', tiledSrc: 'interior', name: 'Stormpeak Monster Center',
  npcs: [{ id: 'nurse', x: 5, y: 4, sprite: 'nurse', facing: 'down', heal: true, fastTravel: true,
    dialogue: () => ["Welcome to the Monster Center!", "It's cold up here - rest up before heading back out."] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'stormpeak', tx: 16, ty: 8 }],
};
MAPS.mart_stormpeak = {
  tiledKey: 'mart', tiledSrc: 'interior', name: 'Stormpeak Mart',
  npcs: [{ id: 'shopkeeper', x: 1, y: 5, sprite: 'shopkeeper', facing: 'down', shop: true,
    dialogue: () => ["Take a look at my wares!"] }],
  extraWarps: [{ x: 6, y: 10, w: 1, h: 1, to: 'stormpeak', tx: 21, ty: 8 }],
};

MAPS.hearthrock = {
  tiledKey: 'hearthrock', tiledSrc: 'classic', name: 'Hearthrock City',
  npcs: [],
  extraWarps: [
    { x: 32, y: 0, w: 1, h: 1, to: 'classic_route1', tx: 33, ty: 19 },
    { x: 39, y: 15, w: 1, h: 1, to: 'classic_route8', tx: 0, ty: 16 },
    { x: 18, y: 13, w: 1, h: 1, to: 'gym_hearthrock1', tx: 10, ty: 19 },
    { x: 23, y: 13, w: 1, h: 1, to: 'gym_hearthrock2', tx: 10, ty: 19 },
    { x: 8, y: 13, w: 1, h: 1, to: 'healing_center_hearthrock', tx: 6, ty: 10 },
    { x: 13, y: 13, w: 1, h: 1, to: 'mart_hearthrock', tx: 6, ty: 10 },
    { x: 20, y: 19, w: 1, h: 1, to: 'crysthaven', tx: 23, ty: 1 },
  ],
  encounterTable: [],
};
MAPS.steamshore = {
  tiledKey: 'steamshore', tiledSrc: 'classic', name: 'Steamshore City',
  npcs: [],
  extraWarps: [
    { x: 5, y: 19, w: 1, h: 1, to: 'classic_route1', tx: 6, ty: 0 },
    { x: 39, y: 2, w: 1, h: 1, to: 'classic_route2', tx: 0, ty: 3 },
    { x: 23, y: 14, w: 1, h: 1, to: 'gym_steamshore2', tx: 10, ty: 19 },
    { x: 31, y: 4, w: 1, h: 1, to: 'gym_steamshore1', tx: 10, ty: 19 },
    { x: 28, y: 14, w: 1, h: 1, to: 'mart_steamshore', tx: 6, ty: 10 },
    { x: 33, y: 14, w: 1, h: 1, to: 'healing_center_steamshore', tx: 6, ty: 10 },
  ],
  encounterTable: [],
};
MAPS.stormpeak = {
  tiledKey: 'stormpeak', tiledSrc: 'classic', name: 'Stormpeak City',
  npcs: [],
  extraWarps: [
    { x: 5, y: 3, w: 1, h: 1, to: 'gym_stormpeak', tx: 10, ty: 19 },
    { x: 15, y: 19, w: 1, h: 1, to: 'classic_route4', tx: 18, ty: 0 },
    { x: 16, y: 7, w: 1, h: 1, to: 'healing_center_stormpeak', tx: 6, ty: 10 },
    { x: 21, y: 7, w: 1, h: 1, to: 'mart_stormpeak', tx: 6, ty: 10 },
  ],
  encounterTable: [],
};
MAPS.valorhold = {
  tiledKey: 'valorhold', tiledSrc: 'classic', name: 'Valorhold',
  npcs: [{ id: 'valorhold_sign', x: 12, y: 10, sprite: 'townsfolk1', facing: 'down',
    dialogue: () => ["The old lighthouse tower here is said to hold a fierce trainer.", "No one's beaten them yet - but there's no badge in it, just bragging rights."] }],
  extraWarps: [
    { x: 0, y: 16, w: 1, h: 1, to: 'classic_route8', tx: 39, ty: 17 },
    { x: 2, y: 0, w: 1, h: 1, to: 'classic_route7', tx: 3, ty: 19 },
  ],
  encounterTable: [],
};
MAPS.aerolume = {
  tiledKey: 'aerolume', tiledSrc: 'classic', name: 'Aerolume',
  npcs: [],
  extraWarps: [
    { x: 39, y: 1, w: 1, h: 1, to: 'classic_route6', tx: 0, ty: 2 },
    { x: 0, y: 16, w: 1, h: 1, to: 'classic_route5', tx: 39, ty: 17 },
    { x: 20, y: 10, w: 1, h: 1, to: 'gym_aerolume', tx: 10, ty: 19 },
  ],
  encounterTable: [],
};
MAPS.thornwood = {
  tiledKey: 'thornwood', tiledSrc: 'classic', name: 'Thornwood',
  npcs: [{ id: 'thornwood_sign', x: 20, y: 10, sprite: 'townsfolk2', facing: 'down',
    dialogue: () => ["Thornwood sits at the crossroads of the whole region.", "Steamshore's east, Stormpeak and Valorhold are south, Aerolume's west."] }],
  extraWarps: [
    { x: 0, y: 16, w: 1, h: 1, to: 'classic_route2', tx: 39, ty: 17 },
    { x: 39, y: 1, w: 1, h: 1, to: 'classic_route5', tx: 0, ty: 2 },
    { x: 35, y: 19, w: 1, h: 1, to: 'classic_route7', tx: 36, ty: 0 },
    { x: 16, y: 0, w: 1, h: 1, to: 'classic_route3', tx: 17, ty: 19 },
  ],
  encounterTable: [],
};
MAPS.umbrastar = {
  tiledKey: 'umbrastar', tiledSrc: 'classic', name: 'Umbrastar',
  npcs: [{ id: 'umbrastar_sign', x: 20, y: 10, sprite: 'townsfolk1', facing: 'down',
    dialogue: () => ["Umbrastar's the end of the road out here.", "Quiet place. Good for training away from the crowds."] }],
  extraWarps: [{ x: 0, y: 16, w: 1, h: 1, to: 'classic_route6', tx: 39, ty: 17 }],
  encounterTable: [],
};

MAPS.classic_route1 = {
  tiledKey: 'classic_route1', tiledSrc: 'classic', name: 'Route 1 (Hearthrock-Steamshore)',
  npcs: [],
  extraWarps: [
    { x: 32, y: 19, w: 1, h: 1, to: 'hearthrock', tx: 33, ty: 0 },
    { x: 5, y: 0, w: 1, h: 1, to: 'steamshore', tx: 6, ty: 19 },
  ],
  encounterTable: [
    { slug: 'grintot', min: 18, max: 21, w: 4 }, { slug: 'boltnu', min: 18, max: 21, w: 4 },
    { slug: 'gupphish', min: 18, max: 21, w: 4 }, { slug: 'chickadee', min: 18, max: 21, w: 3 },
  ],
};
MAPS.classic_route2 = {
  tiledKey: 'classic_route2', tiledSrc: 'classic', name: 'Route 2 (Steamshore-Thornwood)',
  npcs: [],
  extraWarps: [
    { x: 0, y: 2, w: 1, h: 1, to: 'steamshore', tx: 39, ty: 3 },
    { x: 39, y: 16, w: 1, h: 1, to: 'thornwood', tx: 0, ty: 17 },
  ],
  encounterTable: [
    { slug: 'kroki', min: 20, max: 23, w: 4 }, { slug: 'katapill', min: 20, max: 23, w: 4 },
    { slug: 'fancair', min: 20, max: 23, w: 3 }, { slug: 'lesmagu', min: 20, max: 23, w: 3 },
  ],
};
MAPS.classic_route3 = {
  tiledKey: 'classic_route3', tiledSrc: 'classic', name: 'Route 3',
  npcs: [],
  extraWarps: [
    { x: 16, y: 0, w: 1, h: 1, to: 'classic_route4', tx: 20, ty: 0 },
    { x: 16, y: 19, w: 1, h: 1, to: 'thornwood', tx: 17, ty: 0 },
  ],
  encounterTable: [
    { slug: 'metesaur', min: 22, max: 25, w: 4 }, { slug: 'cataspike', min: 22, max: 25, w: 4 },
    { slug: 'dollfin', min: 22, max: 25, w: 3 }, { slug: 'pipis', min: 22, max: 25, w: 3 },
  ],
};
MAPS.classic_route4 = {
  tiledKey: 'classic_route4', tiledSrc: 'classic', name: 'Route 4',
  npcs: [],
  extraWarps: [
    { x: 15, y: 0, w: 1, h: 1, to: 'stormpeak', tx: 18, ty: 19 },
    { x: 16, y: 19, w: 1, h: 1, to: 'classic_route3', tx: 20, ty: 19 },
  ],
  encounterTable: [
    { slug: 'claymorior', min: 24, max: 27, w: 4 }, { slug: 'angrito', min: 24, max: 27, w: 4 },
    { slug: 'nebufin', min: 24, max: 27, w: 3 }, { slug: 'hatchling', min: 24, max: 27, w: 3 },
  ],
};
MAPS.classic_route5 = {
  tiledKey: 'classic_route5', tiledSrc: 'classic', name: 'Route 5 (Thornwood-Aerolume)',
  npcs: [],
  extraWarps: [
    { x: 0, y: 1, w: 1, h: 1, to: 'thornwood', tx: 39, ty: 2 },
    { x: 39, y: 16, w: 1, h: 1, to: 'aerolume', tx: 0, ty: 17 },
  ],
  encounterTable: [
    { slug: 'devidin', min: 26, max: 29, w: 4 }, { slug: 'botbot', min: 26, max: 29, w: 4 },
    { slug: 'jelillow', min: 26, max: 29, w: 3 }, { slug: 'noctula', min: 26, max: 29, w: 3 },
  ],
};
MAPS.classic_route6 = {
  tiledKey: 'classic_route6', tiledSrc: 'classic', name: 'Route 6 (Aerolume-Umbrastar)',
  npcs: [],
  extraWarps: [
    { x: 39, y: 16, w: 1, h: 1, to: 'umbrastar', tx: 0, ty: 17 },
    { x: 0, y: 1, w: 1, h: 1, to: 'aerolume', tx: 39, ty: 2 },
  ],
  encounterTable: [
    { slug: 'imbrickcile', min: 28, max: 31, w: 4 }, { slug: 'sadito', min: 28, max: 31, w: 4 },
    { slug: 'bedoo', min: 28, max: 31, w: 3 }, { slug: 'birdling', min: 28, max: 31, w: 3 },
  ],
};
MAPS.classic_route7 = {
  tiledKey: 'classic_route7', tiledSrc: 'classic', name: 'Route 7 (Thornwood-Valorhold)',
  npcs: [],
  extraWarps: [
    { x: 2, y: 19, w: 1, h: 1, to: 'valorhold', tx: 3, ty: 0 },
    { x: 35, y: 0, w: 1, h: 1, to: 'thornwood', tx: 36, ty: 19 },
  ],
  encounterTable: [
    { slug: 'grintot', min: 24, max: 27, w: 4 }, { slug: 'happito', min: 24, max: 27, w: 4 },
    { slug: 'galasces', min: 24, max: 27, w: 3 }, { slug: 'elofly', min: 24, max: 27, w: 3 },
  ],
};
MAPS.classic_route8 = {
  tiledKey: 'classic_route8', tiledSrc: 'classic', name: 'Route 8 (Hearthrock-Valorhold)',
  npcs: [],
  extraWarps: [
    { x: 0, y: 15, w: 1, h: 1, to: 'hearthrock', tx: 39, ty: 16 },
    { x: 39, y: 16, w: 1, h: 1, to: 'valorhold', tx: 0, ty: 17 },
  ],
  encounterTable: [
    { slug: 'baddrscratch', min: 18, max: 21, w: 4 }, { slug: 'picc', min: 18, max: 21, w: 4 },
    { slug: 'dollfin', min: 18, max: 21, w: 3 }, { slug: 'cardiling', min: 18, max: 21, w: 3 },
  ],
};

(function patchBrokenWarps() {
  // Each town has one warp into a "pokemon_center_*" building interior, but
  // those interior maps were never included in this build (ASSET_LIBRARY.md:
  // they're unfinished placeholders in the source repo - grass + tree-corner
  // tiles, not a real room). Walking onto that doorway tile therefore sent
  // the player to a map that doesn't exist in MAPS/TILED at all, which threw
  // (`Cannot read properties of undefined (reading 'tiledKey')`) and froze
  // the game on whatever frame was last drawn - looking exactly like the
  // player had walked straight into/through the building, since nothing
  // ever rendered again to show otherwise. Found by walking a real keyboard
  // path onto each of the three affected doors (town, ashveld, crysthaven)
  // and watching it crash the same way every time.
  // Fix: drop any warp whose destination map isn't actually part of this
  // build, everywhere, rather than special-casing the three known ones -
  // the door tile is left walkable (same as this project's other purely
  // decorative doors) but no longer tries to warp anywhere.
  const tiledSourceByName = { interior: INTERIOR_TILED, classic: CLASSIC_TILED };
  const targetExists = (key) => {
    const m = MAPS[key];
    if (!m) return false;
    if (!m.tiledKey) return true;
    return !!(tiledSourceByName[m.tiledSrc] || TILED).maps[m.tiledKey];
  };
  for (const name in TILED.maps) {
    const td = TILED.maps[name];
    if (td.warps) td.warps = td.warps.filter(w => targetExists(w.to));
    const map = MAPS[name];
    if (map && map.extraWarps) map.extraWarps = map.extraWarps.filter(w => targetExists(w.to));
  }
})();

/* ---------------------------- NPC dialogue functions ---------------------------- */
function professorDialogue() {
  if (!state.flags.starterChosen) {
    return { choice: true,
      lines: ["Ah, a new trainer! I'm Professor Larkspur.", "Every journey starts with a partner. Choose wisely:"],
      options: STARTERS.map(s => MONSTERS[s].name),
      onChoose: (i) => {
        const slug = STARTERS[i];
        state.party.push(createMonsterInstance(slug, 5));
        markDexCaught(slug);
        state.flags.starterChosen = true;
        pushDialogue([MONSTERS[slug].name + ' joined your team!', "Go show the world what you two can do!"]);
      }
    };
  }
  return ["Your " + monsterDisplayName(state.party[0]) + " looks strong. Good luck out there!"];
}
function rivalHometownDialogue() {
  if (!state.flags.starterChosen) return ["Hurry up and get your starter from the Professor!"];
  if (!state.flags.rivalBattled) {
    return { trainerNow: {
      name: 'Rival May', team: [{ slug: pickRivalStarter(), level: 5 }],
      prizeMoney: 50, flag: 'rivalBattled',
      preBattle: ["So you picked yours too. Let's see who's really got what it takes!"],
      postWin: ["Ha! Not bad. See you on the road, rival."],
      postLose: ["Wow, you're strong! I'll train harder and catch up."],
    }};
  }
  return ["Beat every Arena Leader before I do, alright?"];
}
function pickRivalStarter() {
  const my = state.party[0] ? state.party[0].slug : STARTERS[0];
  const idx = STARTERS.indexOf(my);
  return STARTERS[(idx + 1) % STARTERS.length];
}
function lostPetDialogue() {
  if (state.flags.lostPetDone) {
    if (!state.flags.lostPetRewarded) {
      state.flags.lostPetRewarded = true;
      addItem('super_potion', 2);
      state.money += 200;
      return ["You found my Chillimp! Thank you so much!", "Here, take this reward!", "(Received 2 Super Potions and ₡200!)"];
    }
    return ["Thank you again for finding my Chillimp!"];
  }
  return ["My pet Chillimp ran off into Whisper Woods!", "Could you find it and bring it back? I bet it's hiding in the tall grass."];
}
function bridgeGuideDialogue() {
  if (state.flags.enforcerDefeated) return ["The bridge is safe now, thanks to you!"];
  return ["The Enforcers have locked down the outpost to the west.", "Clear them out and I'll let you through to the Summit."];
}

/* ---------------------------- Dialogue box ---------------------------- */
let dialogueQueue = [];
let currentChoice = null;
function pushDialogue(lines) {
  dialogueQueue = dialogueQueue.concat(lines);
  state.screen = 'dialogue';
  showNextDialogueLine();
}
function showNextDialogueLine() {
  const box = document.getElementById('dialogueBox');
  const txt = document.getElementById('dialogueText');
  if (dialogueQueue.length === 0) {
    box.style.display = 'none';
    // A trainer's preBattle text runs through this same dialogue queue while
    // battle is already set up underneath (see startTrainerBattle) - once
    // dismissed, go back to the battle screen instead of the overworld, or
    // every state.screen==='battle' check elsewhere (HUD, movement input,
    // NPC interact, the render loop) would think the fight had ended.
    if (state.screen === 'dialogue' && !currentChoice) state.screen = battle ? 'battle' : 'overworld';
    return;
  }
  box.style.display = 'block';
  txt.textContent = dialogueQueue.shift();
}
function advanceDialogue() {
  showNextDialogueLine();
}

function handleNpcInteract(npc) {
  if (npc.trainer && !state.flags[npc.trainer.flag]) {
    startTrainerBattle(npc.trainer, npc.sprite);
    return;
  }
  if (npc.wildFixed && !state.flags.lostPetDone) {
    startWildBattle(npc.wildFixed.slug, npc.wildFixed.level, true);
    return;
  }
  if (npc.heal) {
    for (const m of state.party) m.currentHP = m.derived.hp;
    if (npc.fastTravel) state.visitedCenters[state.map] = true;
  }
  if (npc.shop) { openShop(); return; }
  if (npc.minigame) { openMinigame(); return; }
  let result = npc.dialogue ? npc.dialogue() : null;
  if (!result) return;
  if (result.trainerNow) { startTrainerBattle(result.trainerNow, npc.sprite); return; }
  if (result.choice) {
    pushDialogue(result.lines);
    currentChoice = result;
  } else {
    pushDialogue(result);
  }
}

/* ---------------------------- Movement & camera ---------------------------- */
const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
function currentMap() { return MAPS[state.map]; }

function tileSolidAt(map, x, y) {
  if (map.tiledKey) {
    const td = tiledSourceFor(map).data;
    if (x < 0 || y < 0 || x >= td.w || y >= td.h) return true;
    if (td.collide[y * td.w + x]) return true;
    for (const n of (map.npcs || [])) { if (n.x === x && n.y === y) return true; }
    return false;
  }
  if (x < 0 || y < 0 || x >= map.w || y >= map.h) return true;
  const row = map.tiles[y]; if (!row) return true;
  const ch = row[x];
  const def = TILE_DEF[ch] || TILE_DEF['.'];
  if (def.solid) return true;
  for (const o of (map.objects || [])) {
    if (o.solid && x >= o.x && x < o.x + o.w && y >= o.y && y < o.y + o.h) return true;
  }
  for (const n of (map.npcs || [])) { if (n.x === x && n.y === y) return true; }
  return false;
}

function tryMove(dx, dy, dir) {
  if (state.moving) return;
  state.facing = dir;
  const map = currentMap();
  const nx = state.x + dx, ny = state.y + dy;
  // check warp before solidity of border
  const warp = (map.warps || []).find(w => w.x === state.x && w.y === state.y && false);
  if (!tileSolidAt(map, nx, ny)) {
    state.moving = true;
    state.moveFrom = { x: state.x, y: state.y };
    state.x = nx; state.y = ny;
    state.moveProgress = 0;
  }
}

function onArrive() {
  const map = currentMap();
  if (map.tiledKey) {
    const td = tiledSourceFor(map).data;
    const allWarps = (td.warps || []).concat(map.extraWarps || []);
    const hit = allWarps.find(w => state.x >= w.x && state.x < w.x + w.w && state.y >= w.y && state.y < w.y + w.h);
    if (hit) {
      if (hit.requires && !state.flags[hit.requires]) {
        pushDialogue(["It's blocked for now."]);
        state.x = state.moveFrom.x; state.y = state.moveFrom.y;
        return;
      }
      if (hit.requiresBadges && state.badges.length < hit.requiresBadges) {
        pushDialogue(["The Summit only opens to a trainer holding all " + hit.requiresBadges + " badges.", "You have " + state.badges.length + " so far."]);
        state.x = state.moveFrom.x; state.y = state.moveFrom.y;
        return;
      }
      const targetKey = hit.to;
      const targetMap = MAPS[targetKey];
      const targetTd = targetMap.tiledKey ? tiledSourceFor(targetMap).data : null;
      let tx = hit.tx, ty = hit.ty;
      if (tx === undefined && targetTd && targetTd.spawns && targetTd.spawns[hit.spawn]) {
        tx = targetTd.spawns[hit.spawn].x; ty = targetTd.spawns[hit.spawn].y;
      }
      state.map = targetKey; state.x = tx; state.y = ty;
      return;
    }
    for (const o of (map.objects || [])) {
      if (o.pickup && state.x >= o.x && state.x < o.x + o.w && state.y >= o.y && state.y < o.y + o.h) {
        if (!state.flags[o.pickup.flag]) {
          state.flags[o.pickup.flag] = true;
          addItem(o.pickup.item, 1);
          pushDialogue(['You found ' + (ITEMS_DB[o.pickup.item] ? ITEMS_DB[o.pickup.item].name : o.pickup.item) + '!']);
        }
      }
    }
    if (td.grass && td.grass[state.y * td.w + state.x] && map.encounterTable && map.encounterTable.length) {
      state.stepCounter++;
      if (state.encounterCooldown > 0) { state.encounterCooldown--; }
      else if (Math.random() < 0.12) {
        state.encounterCooldown = 2;
        const enc = weightedPick(map.encounterTable);
        const lvl = enc.min + Math.floor(Math.random() * (enc.max - enc.min + 1));
        startWildBattle(enc.slug, lvl, false);
      }
    }
    return;
  }
  // warp check
  const warp = (map.warps || []).find(w => w.x === state.x && w.y === state.y);
  if (warp) {
    if (warp.requires && !state.flags[warp.requires]) {
      pushDialogue(["It's blocked for now."]);
      state.x = state.moveFrom.x; state.y = state.moveFrom.y;
      return;
    }
    state.map = warp.to; state.x = warp.tx; state.y = warp.ty;
    return;
  }
  // pickup object
  for (const o of (map.objects || [])) {
    if (o.pickup && state.x >= o.x && state.x < o.x + o.w && state.y >= o.y && state.y < o.y + o.h) {
      if (!state.flags[o.pickup.flag]) {
        state.flags[o.pickup.flag] = true;
        addItem(o.pickup.item, 1);
        pushDialogue(['You found ' + (ITEMS_DB[o.pickup.item] ? ITEMS_DB[o.pickup.item].name : o.pickup.item) + '!']);
      }
    }
  }
  // encounter
  const row = map.tiles[state.y];
  const ch = row ? row[state.x] : '.';
  const def = TILE_DEF[ch];
  if (def && def.encounter && map.encounterTable && map.encounterTable.length) {
    state.stepCounter++;
    if (Math.random() < 0.13) {
      const enc = weightedPick(map.encounterTable);
      const lvl = enc.min + Math.floor(Math.random() * (enc.max - enc.min + 1));
      startWildBattle(enc.slug, lvl, false);
    }
  }
}
function weightedPick(table) {
  const total = table.reduce((s, e) => s + e.w, 0);
  let r = Math.random() * total;
  for (const e of table) { if (r < e.w) return e; r -= e.w; }
  return table[0];
}

/* ---------------------------- Input ---------------------------- */
const keys = {};
window.addEventListener('keydown', e => {
  keys[e.key] = true;
  if (state.screen === 'dialogue' && ['Enter', ' '].includes(e.key)) { e.preventDefault(); advanceDialogue(); }
  if (state.screen === 'battle') handleBattleKey(e.key);
  if (e.key === 'Escape') toggleMenu();
  if ((e.key === 'b' || e.key === 'B') && state.screen === 'overworld' && state.flags.hasBike) {
    state.biking = !state.biking;
    pushDialogue([state.biking ? "Hopped on the bike!" : "Hopped off the bike."]);
  }
});
window.addEventListener('keyup', e => { keys[e.key] = false; });

function pollMovementInput() {
  if (state.screen !== 'overworld' || state.moving) return;
  if (keys['ArrowUp'] || keys['w']) tryMove(0, -1, 'up');
  else if (keys['ArrowDown'] || keys['s']) tryMove(0, 1, 'down');
  else if (keys['ArrowLeft'] || keys['a']) tryMove(-1, 0, 'left');
  else if (keys['ArrowRight'] || keys['d']) tryMove(1, 0, 'right');
}
document.addEventListener('keydown', e => {
  if (state.screen === 'overworld' && (e.key === 'Enter' || e.key === ' ')) {
    e.preventDefault();
    const map = currentMap();
    const [dx, dy] = DIRS[state.facing];
    const fx = state.x + dx, fy = state.y + dy;
    const npc = (map.npcs || []).find(n => n.x === fx && n.y === fy);
    if (npc) handleNpcInteract(npc);
  }
});

/* ---------------------------- Rendering ---------------------------- */
const canvas = document.getElementById('game');
canvas.width = VIEW_COLS * TILE;
canvas.height = VIEW_ROWS * TILE;
const ctx = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;

function drawTileImg(key, dx, dy, dw, dh) {
  const im = IMG.tiles[key];
  if (im && im.complete) ctx.drawImage(im, dx, dy, dw || TILE, dh || TILE);
}

function drawBuildingImg(key, dx, dy, w, h, label) {
  const im = IMG.buildings[key];
  if (im && im.complete) ctx.drawImage(im, dx, dy, w, h);
  if (label) {
    ctx.font = 'bold 11px monospace';
    ctx.textAlign = 'center';
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'rgba(0,0,0,0.7)';
    ctx.strokeText(label, dx + w / 2, dy - 4);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, dx + w / 2, dy - 4);
  }
}

function charFrame(spriteKey, facing, frame) {
  const rowMap = { down: 0, left: 1, right: 2, up: 3 };
  const r = rowMap[facing] || 0;
  const c = frame % 3;
  return { sx: c * 16, sy: r * 32, sw: 16, sh: 32 };
}
function drawChar(spriteKey, facing, frame, dx, dy, scale) {
  const im = IMG.chars[spriteKey];
  if (!im || !im.complete) return;
  const f = charFrame(spriteKey, facing, frame);
  const w = 16 * scale, h = 32 * scale;
  ctx.drawImage(im, f.sx, f.sy, f.sw, f.sh, dx, dy - (h - TILE), w, h);
}

function drawAtlasTileFrom(img, cols, srcTile, slot, dx, dy) {
  if (!slot || !img || !img.complete) return;
  const idx = slot - 1;
  const sx = (idx % cols) * srcTile, sy = Math.floor(idx / cols) * srcTile;
  ctx.drawImage(img, sx, sy, srcTile, srcTile, dx, dy, TILE, TILE);
}
function drawAtlasTile(slot, dx, dy) {
  drawAtlasTileFrom(ATLAS_IMG, ATLAS_COLS, SRC_TILE, slot, dx, dy);
}
// Resolves a map's raw tile-grid data plus which atlas/columns/native-tile-size to draw
// it with - outdoor maps use TILED (32px tuxmon-sample atlas), building interiors use
// INTERIOR_TILED (16px core_indoor_* atlas, a separate source-art family).
function tiledSourceFor(map) {
  if (map.tiledSrc === 'interior') return { data: INTERIOR_TILED.maps[map.tiledKey], img: INTERIOR_ATLAS_IMG, cols: INTERIOR_ATLAS_COLS, srcTile: INTERIOR_SRC_TILE };
  if (map.tiledSrc === 'classic') return { data: CLASSIC_TILED.maps[map.tiledKey], img: CLASSIC_ATLAS_IMG, cols: CLASSIC_ATLAS_COLS, srcTile: CLASSIC_SRC_TILE };
  return { data: TILED.maps[map.tiledKey], img: ATLAS_IMG, cols: ATLAS_COLS, srcTile: SRC_TILE };
}

function renderOverworld() {
  const map = currentMap();
  if (map.tiledKey) { renderTiledOverworld(map); return; }
  ctx.fillStyle = map.indoor ? '#111' : '#87ceeb';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const camX = state.px !== undefined ? state.px : state.x;
  const camY = state.py !== undefined ? state.py : state.y;
  const cam = cameraPixelPos(camX, camY, map.w, map.h);
  const originCol = Math.floor(cam.x / TILE) - 1;
  const originRow = Math.floor(cam.y / TILE) - 1;

  for (let ry = -1; ry <= VIEW_ROWS + 1; ry++) {
    for (let rx = -1; rx <= VIEW_COLS + 1; rx++) {
      const tx = originCol + rx, ty = originRow + ry;
      const dx = tx * TILE - cam.x, dy = ty * TILE - cam.y;
      let ch = '.';
      if (tx >= 0 && ty >= 0 && ty < map.h && tx < map.w) ch = map.tiles[ty][tx];
      const def = TILE_DEF[ch] || TILE_DEF['.'];
      drawTileImg(def.img, dx, dy);
      if (def.encounter) { ctx.fillStyle = 'rgba(20,60,20,0.25)'; ctx.fillRect(dx, dy, TILE, TILE); }
    }
  }

  const drawables = [];
  for (const o of (map.objects || [])) {
    const dx = o.x * TILE - cam.x, dy = o.y * TILE - cam.y;
    drawables.push({ y: o.y + o.h, draw: () => {
      if (o.building) drawBuildingImg(o.building, dx, dy, o.w * TILE, o.h * TILE, o.label);
      else drawTileImg(o.key, dx, dy, o.w * TILE, o.h * TILE);
    }});
  }
  for (const n of (map.npcs || [])) {
    const dx = n.x * TILE - cam.x, dy = n.y * TILE - cam.y;
    drawables.push({ y: n.y, draw: () => drawChar(n.sprite, n.facing, 0, dx, dy, 4) });
  }
  const pdx = camX * TILE - cam.x, pdy = camY * TILE - cam.y;
  const playerSprite = state.playerSprite || 'player_boy';
  drawables.push({ y: camY + 0.5, draw: () => drawChar(playerSprite, state.facing, state.moving ? (Math.floor(state.animTimer / 6) % 2 + 1) : 0, pdx, pdy, 4) });
  drawables.sort((a, b) => a.y - b.y);
  for (const d of drawables) d.draw();
}

// Converts a camera "look-at" position (in tile units) into a clamped top-left
// pixel offset for the viewport, so tiles/sprites draw at worldPos*TILE - cam.
// Clamping keeps the viewport inside the map (matching the source game's own
// camera.setBounds()) instead of always force-centering the player, which is
// what was producing empty space / misaligned tiles near map edges.
function cameraPixelPos(camX, camY, mapW, mapH) {
  let px = Math.floor(camX * TILE) - canvas.width / 2 + TILE / 2;
  let py = Math.floor(camY * TILE) - canvas.height / 2 + TILE / 2;
  const maxX = mapW * TILE - canvas.width, maxY = mapH * TILE - canvas.height;
  px = maxX > 0 ? Math.max(0, Math.min(px, maxX)) : Math.floor(maxX / 2);
  py = maxY > 0 ? Math.max(0, Math.min(py, maxY)) : Math.floor(maxY / 2);
  return { x: px, y: py };
}

function renderTiledOverworld(map) {
  const src = tiledSourceFor(map);
  const td = src.data;
  const draw = (slot, dx, dy) => drawAtlasTileFrom(src.img, src.cols, src.srcTile, slot, dx, dy);
  ctx.fillStyle = map.tiledSrc === 'interior' ? '#1c1c22' : '#87ceeb';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const camX = state.px !== undefined ? state.px : state.x;
  const camY = state.py !== undefined ? state.py : state.y;
  // Camera is clamped to the map's own bounds (matching the source game's
  // camera.setBounds() convention) so the viewport never shows empty space
  // past an edge, and the player naturally moves off-center near borders
  // instead of the whole tile grid ending up misaligned.
  const cam = cameraPixelPos(camX, camY, td.w, td.h);
  const originCol = Math.floor(cam.x / TILE) - 1;
  const originRow = Math.floor(cam.y / TILE) - 1;

  for (let ry = -1; ry <= VIEW_ROWS + 1; ry++) {
    for (let rx = -1; rx <= VIEW_COLS + 1; rx++) {
      const tx = originCol + rx, ty = originRow + ry;
      if (tx < 0 || ty < 0 || tx >= td.w || ty >= td.h) continue;
      const dx = tx * TILE - cam.x, dy = ty * TILE - cam.y;
      const i = ty * td.w + tx;
      draw(td.below[i], dx, dy);
      draw(td.world[i], dx, dy);
      if (td.grass && td.grass[i]) { ctx.fillStyle = 'rgba(20,60,20,0.18)'; ctx.fillRect(dx, dy, TILE, TILE); }
    }
  }
  for (const o of (td.overlays || [])) {
    const dx = o.x * TILE - cam.x, dy = o.y * TILE - cam.y;
    drawBuildingImg(o.img, dx, dy, o.w * TILE, o.h * TILE);
  }

  const drawables = [];
  for (const n of (map.npcs || [])) {
    const dx = n.x * TILE - cam.x, dy = n.y * TILE - cam.y;
    drawables.push({ y: n.y, draw: () => drawChar(n.sprite, n.facing, 0, dx, dy, 4) });
  }
  const pdx = camX * TILE - cam.x, pdy = camY * TILE - cam.y;
  const playerSprite = state.playerSprite || 'player_boy';
  drawables.push({ y: camY + 0.5, draw: () => drawChar(playerSprite, state.facing, state.moving ? (Math.floor(state.animTimer / 6) % 2 + 1) : 0, pdx, pdy, 4) });
  drawables.sort((a, b) => a.y - b.y);
  for (const d of drawables) d.draw();

  for (let ry = -1; ry <= VIEW_ROWS + 1; ry++) {
    for (let rx = -1; rx <= VIEW_COLS + 1; rx++) {
      const tx = originCol + rx, ty = originRow + ry;
      if (tx < 0 || ty < 0 || tx >= td.w || ty >= td.h) continue;
      const dx = tx * TILE - cam.x, dy = ty * TILE - cam.y;
      draw(td.above[ty * td.w + tx], dx, dy);
    }
  }
}

/* ---------------------------- Game loop / movement animation ---------------------------- */
function updateMovementAnim() {
  if (state.moving) {
    state.moveProgress = (state.moveProgress || 0) + (state.biking ? 0.44 : 0.22);
    state.animTimer++;
    state.px = state.moveFrom.x + (state.x - state.moveFrom.x) * Math.min(1, state.moveProgress);
    state.py = state.moveFrom.y + (state.y - state.moveFrom.y) * Math.min(1, state.moveProgress);
    if (state.moveProgress >= 1) {
      state.px = state.x; state.py = state.y;
      state.moving = false;
      onArrive();
    }
  } else {
    state.px = state.x; state.py = state.y;
  }
}

function gameLoop() {
  pollMovementInput();
  updateMovementAnim();
  // A trainer's preBattle dialogue runs through the same pushDialogue() as
  // ordinary overworld dialogue, which sets state.screen to 'dialogue' - so
  // checking state.screen alone here would redraw the overworld map (and,
  // once dismissed, state.screen goes to 'overworld' too) right over the
  // already-drawn battle scene/sprites while the battle is still up. `battle`
  // is the authoritative "a fight is in progress" flag regardless of which
  // screen value dialogue plumbing leaves behind, so gate on it too.
  if (!battle && (state.screen === 'overworld' || state.screen === 'dialogue')) renderOverworld();
  updateHud();
  requestAnimationFrame(gameLoop);
}

/* ---------------------------- HUD ---------------------------- */
function updateHud() {
  const bar = document.getElementById('partyBar');
  if (state.screen === 'battle' || state.screen === 'boot' || state.screen === 'title') { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  bar.innerHTML = state.party.map(m => {
    const pct = Math.max(0, Math.floor(m.currentHP / m.derived.hp * 100));
    return `<div class="hudmon"><img src="data:image/png;base64,${ASSET_B64.monsters[m.slug]}"/><div class="hudname">${monsterDisplayName(m)} Lv${m.level}</div><div class="hpbar"><div class="hpfill" style="width:${pct}%;background:${pct>50?'#4caf50':pct>20?'#e0a52b':'#e04b2b'}"></div></div></div>`;
  }).join('') + `<div class="moneybox">₡ ${state.money}</div>`;
}

/* ============================ BATTLE SYSTEM ============================ */
let battle = null;
function startWildBattle(slug, level, isFixed) {
  battle = {
    kind: 'wild', isFixed,
    enemyTeam: [createMonsterInstance(slug, level)],
    enemyIdx: 0,
    playerIdx: state.party.findIndex(m => m.currentHP > 0),
    log: [], turnLock: false,
  };
  markDexSeen(slug);
  state.screen = 'battle';
  openBattleUI();
}
function startTrainerBattle(trainerDef, trainerSprite) {
  battle = {
    kind: 'trainer', trainer: trainerDef, trainerSprite: trainerSprite || null,
    enemyTeam: trainerDef.team.map(t => createMonsterInstance(t.slug, t.level)),
    enemyIdx: 0,
    playerIdx: state.party.findIndex(m => m.currentHP > 0),
    log: [], turnLock: false,
  };
  for (const m of battle.enemyTeam) markDexSeen(m.slug);
  state.screen = 'battle';
  if (trainerDef.preBattle) pushDialogue(trainerDef.preBattle);
  openBattleUI();
}
function currentEnemy() { return battle.enemyTeam[battle.enemyIdx]; }
function currentPlayerMon() { return state.party[battle.playerIdx]; }

function openBattleUI() {
  document.getElementById('dialogueBox').style.display = 'none';
  const ui = document.getElementById('battleUI');
  ui.style.display = 'block';
  renderBattleMain();
}
function closeBattleUI() {
  document.getElementById('battleUI').style.display = 'none';
  state.screen = 'overworld';
  battle = null;
}

// Real Tuxemon battle background art (mods/tuxemon/gfx/ui/combat/*_background.png) -
// picks a scene that matches where the fight is actually happening instead of a
// flat CSS gradient. Gym battles (any map whose tiledKey starts with "gym_") get
// the stadium art; everything else (wild encounters, route trainers) gets grass.
function battleBackgroundKey() {
  const map = MAPS[state.map];
  if (map && map.tiledKey && map.tiledKey.indexOf('gym_') === 0) return 'bg_stadium';
  return 'bg_grass';
}
function renderBattleScene() {
  const bg = IMG.battleui[battleBackgroundKey()];
  if (bg && bg.complete) {
    const dw = canvas.width, dh = bg.naturalHeight * (canvas.width / bg.naturalWidth);
    ctx.drawImage(bg, 0, 0, bg.naturalWidth, bg.naturalHeight, 0, 0, dw, dh);
    if (dh < canvas.height) { ctx.fillStyle = '#8fbf7a'; ctx.fillRect(0, dh, canvas.width, canvas.height - dh); }
  } else {
    ctx.fillStyle = '#cfe8c9';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#8fbf7a';
    ctx.fillRect(0, canvas.height * 0.55, canvas.width, canvas.height * 0.45);
  }
  const enemy = currentEnemy();
  const pm = currentPlayerMon();
  // Opponent trainer (trainer battles only) - stands behind/above their own
  // monster, same convention as their name banner already shown up top.
  if (battle.trainerSprite) {
    drawChar(battle.trainerSprite, 'down', 0, canvas.width * 0.78, canvas.height * 0.14, 4);
  }
  if (enemy) {
    const im = IMG.monsters[enemy.slug];
    if (im && im.complete) ctx.drawImage(im, canvas.width * 0.58, canvas.height * 0.16, 64 * 3.3, 44 * 3.3);
  }
  // Player's own trainer, back view ('up' facing = back row in the sprite sheet).
  const playerSprite = state.playerSprite || 'player_boy';
  drawChar(playerSprite, 'up', 0, canvas.width * 0.02, canvas.height * 0.55, 4.3);
  if (pm) {
    const im = IMG.monsters[pm.slug];
    if (im && im.complete) ctx.drawImage(im, canvas.width * 0.05, canvas.height * 0.38, 64 * 3.8, 44 * 3.8);
  }
}
(function hookBattleRender() {
  const origLoop = gameLoop;
})();

function battleHpBar(m, side) {
  const pct = Math.max(0, Math.floor(m.currentHP / m.derived.hp * 100));
  const typeBadges = MONSTERS[m.slug].types.map(t => `<span class="typebadge" style="background:${TYPE_COLORS[t]||'#888'}">${t}</span>`).join('');
  return `<div class="battlecard ${side}"><b>${monsterDisplayName(m)}</b> Lv${m.level} ${typeBadges}<div class="hpbar"><div class="hpfill" style="width:${pct}%;background:${pct>50?'#4caf50':pct>20?'#e0a52b':'#e04b2b'}"></div></div><div class="hptext">${m.currentHP}/${m.derived.hp} HP</div></div>`;
}

function renderBattleMain() {
  const enemy = currentEnemy(); const pm = currentPlayerMon();
  // Opponent's card top-left, player's own lower-right beside their own sprite -
  // the classic layout, not both crammed together at the very top.
  document.getElementById('battleTrainerName').innerHTML = battle.trainer ? `<div class="trainername">${battle.trainer.name}</div>` : '';
  document.getElementById('battleTop').innerHTML = battleHpBar(enemy, 'opponent');
  document.getElementById('battlePlayerHp').innerHTML = battleHpBar(pm, 'player');
  const menu = document.getElementById('battleMenu');
  menu.innerHTML = `
    <button onclick="battleShowMoves()">Fight</button>
    <button onclick="openBagInBattle()">Bag</button>
    <button onclick="openPartyInBattle()">Creatures</button>
    <button onclick="battleRun()" ${battle.kind==='trainer'?'disabled':''}>${battle.kind==='trainer'?'Run':'Run'}</button>
    ${battle.kind==='wild' && !battle.isFixed ? '<button onclick="battleThrowBall()">Throw Ball</button>' : ''}
  `;
  renderBattleScene();
}

function battleShowMoves() {
  const pm = currentPlayerMon();
  const moves = getActiveMoves(pm);
  const menu = document.getElementById('battleMenu');
  menu.innerHTML = moves.map((mv, i) => `<button onclick="playerUseMove(${i})">${mv.name} <span class="movetype" style="background:${TYPE_COLORS[mv.type]||'#888'}">${mv.type}</span></button>`).join('') +
    `<button onclick="renderBattleMain()">Back</button>`;
}

function appendBattleLog(lines) {
  const log = document.getElementById('battleLog');
  log.innerHTML = lines.map(l => `<div>${l}</div>`).join('') + log.innerHTML;
}

function playerUseMove(i) {
  if (battle.turnLock) return;
  battle.turnLock = true;
  const pm = currentPlayerMon();
  const moves = getActiveMoves(pm);
  const mv = moves[i];
  const enemy = currentEnemy();
  const order = pm.derived.spd >= enemy.derived.spd ? ['player', 'enemy'] : ['enemy', 'player'];
  let msgs = [];
  function doAttack(attacker, defender, atkMon, defMon, isPlayer) {
    if (atkMon.currentHP <= 0) return;
    const move = isPlayer ? mv : pickEnemyMove(defender);
    const hit = Math.random() <= move.accuracy;
    if (!hit) { msgs.push(monsterDisplayName(atkMon) + "'s " + move.name + ' missed!'); return; }
    const atkStat = move.range === 'ranged' ? atkMon.derived.ranged : atkMon.derived.atk;
    const base = Math.max(1, atkStat * move.power - defMon.derived.def * 0.5);
    const mult = typeEffectiveness(move.type, MONSTERS[defMon.slug].types);
    const dmg = Math.max(1, Math.floor(base * mult * (0.85 + Math.random() * 0.3)));
    defMon.currentHP = Math.max(0, defMon.currentHP - dmg);
    msgs.push(monsterDisplayName(atkMon) + ' used ' + move.name + '!' + (mult > 1 ? ' It\'s super effective!' : mult < 1 && mult > 0 ? ' It\'s not very effective...' : ''));
  }
  for (const who of order) {
    if (who === 'player') doAttack(pm, enemy, pm, enemy, true);
    else doAttack(enemy, pm, enemy, pm, false);
    if (currentEnemy().currentHP <= 0 || currentPlayerMon().currentHP <= 0) break;
  }
  appendBattleLog(msgs);
  setTimeout(() => resolveBattleTurn(), 700);
}
function pickEnemyMove(enemyMon) {
  const moves = getActiveMoves(enemyMon);
  return moves[Math.floor(Math.random() * moves.length)];
}

function resolveBattleTurn() {
  const enemy = currentEnemy(); const pm = currentPlayerMon();
  if (enemy.currentHP <= 0) {
    const expLog = [];
    const gained = 12 + enemy.level * 4;
    grantExp(pm, gained, expLog);
    appendBattleLog([monsterDisplayName(enemy) + ' fainted!', pm && monsterDisplayName(pm) + ' gained ' + gained + ' EXP.'].concat(expLog));
    battle.enemyIdx++;
    if (battle.enemyIdx >= battle.enemyTeam.length) {
      finishBattle(true); return;
    } else {
      battle.turnLock = false; renderBattleMain(); return;
    }
  }
  if (pm.currentHP <= 0) {
    appendBattleLog([monsterDisplayName(pm) + ' fainted!']);
    const nextIdx = state.party.findIndex(m => m.currentHP > 0);
    if (nextIdx === -1) { finishBattle(false); return; }
    battle.playerIdx = nextIdx;
    appendBattleLog(['Go, ' + monsterDisplayName(state.party[nextIdx]) + '!']);
  }
  battle.turnLock = false;
  renderBattleMain();
}

function finishBattle(playerWon) {
  const t = battle.trainer;
  if (playerWon) {
    if (t) {
      state.money += t.prizeMoney || 0;
      state.flags[t.flag] = true;
      if (t.badge) state.badges.push(t.badge);
      if (t.givesBike) state.flags.hasBike = true;
      if (t.keyItem) addItem('bridge_pass', 1);
      if (t.story) state.flags[t.story] = true;
      const lines = (t.postWin || []).slice();
      if (t.prizeMoney) lines.push('You received ₡' + t.prizeMoney + '!');
      closeBattleUI();
      pushDialogue(lines);
      if (t.story === 'gameWon') showVictory();
    } else if (battle.isFixed) {
      const caught = currentEnemy();
      state.flags.lostPetDone = true;
      markDexCaught(caught.slug);
      if (state.party.length < 6) state.party.push(caught); else state.boxParty.push(caught);
      closeBattleUI();
      pushDialogue(['You gently coaxed ' + monsterDisplayName(caught) + ' to safety!', 'It joined your team!']);
    } else {
      closeBattleUI();
    }
  } else {
    for (const m of state.party) m.currentHP = m.derived.hp;
    closeBattleUI();
    pushDialogue(['You blacked out! Your team was healed at the Monster Center.']);
    state.map = 'town'; state.x = 20; state.y = 36;
  }
}
function battleRun() {
  if (battle.kind === 'trainer') { appendBattleLog(["You can't run from a trainer battle!"]); return; }
  closeBattleUI();
}
function battleThrowBall() {
  if (battle.turnLock) return;
  const ballSlug = ['tuxeball_majestic','tuxeball_ancient','tuxeball_refined','tuxeball_earth','tuxeball_nocturnal','tuxeball'].find(b => (state.inventory[b]||0) > 0);
  if (!ballSlug) { appendBattleLog(['You have no capture balls left!']); return; }
  removeItem(ballSlug, 1);
  const enemy = currentEnemy();
  const hpFrac = enemy.currentHP / enemy.derived.hp;
  const ballBonus = ballSlug === 'tuxeball' ? 1 : 1.5;
  const chance = Math.min(0.95, ((1 - hpFrac) * 0.75 + 0.12) * (enemy.catch_rate ? MONSTERS[enemy.slug].catch_rate/100 : 1) * ballBonus);
  appendBattleLog(['You threw a ' + ITEMS_DB[ballSlug].name + '!']);
  if (Math.random() < chance) {
    appendBattleLog(['Gotcha! ' + monsterDisplayName(enemy) + ' was caught!']);
    markDexCaught(enemy.slug);
    if (state.party.length < 6) state.party.push(enemy); else state.boxParty.push(enemy);
    setTimeout(() => { closeBattleUI(); }, 900);
  } else {
    appendBattleLog(['Argh! It broke free!']);
    setTimeout(() => resolveEnemyOnlyTurn(), 700);
  }
}
function resolveEnemyOnlyTurn() {
  const enemy = currentEnemy(); const pm = currentPlayerMon();
  const move = pickEnemyMove(enemy);
  const hit = Math.random() <= move.accuracy;
  if (hit) {
    const atkStat = move.range === 'ranged' ? enemy.derived.ranged : enemy.derived.atk;
    const base = Math.max(1, atkStat * move.power - pm.derived.def * 0.5);
    const mult = typeEffectiveness(move.type, MONSTERS[pm.slug].types);
    const dmg = Math.max(1, Math.floor(base * mult * (0.85 + Math.random() * 0.3)));
    pm.currentHP = Math.max(0, pm.currentHP - dmg);
    appendBattleLog([monsterDisplayName(enemy) + ' used ' + move.name + '!']);
  }
  resolveBattleTurn();
}

function openBagInBattle() {
  const menu = document.getElementById('battleMenu');
  const usable = Object.keys(state.inventory).filter(s => ITEMS_DB[s] && ITEMS_DB[s].category === 'potion');
  menu.innerHTML = usable.map(s => `<button onclick="useItemInBattle('${s}')">${ITEMS_DB[s].name} x${state.inventory[s]}</button>`).join('') + `<button onclick="renderBattleMain()">Back</button>`;
}
function useItemInBattle(slug) {
  const pm = currentPlayerMon();
  const heal = slug.includes('super') ? 100 : slug.includes('mega') ? 200 : slug.includes('imperial') ? 9999 : 50;
  pm.currentHP = Math.min(pm.derived.hp, pm.currentHP + heal);
  removeItem(slug, 1);
  appendBattleLog(['Used ' + ITEMS_DB[slug].name + ' on ' + monsterDisplayName(pm) + '.']);
  setTimeout(() => resolveEnemyOnlyTurn(), 500);
}
function openPartyInBattle() {
  const menu = document.getElementById('battleMenu');
  menu.innerHTML = state.party.map((m, i) => `<button ${m.currentHP<=0?'disabled':''} onclick="switchPlayerMon(${i})">${monsterDisplayName(m)} (${m.currentHP}/${m.derived.hp})</button>`).join('') + `<button onclick="renderBattleMain()">Back</button>`;
}
function switchPlayerMon(i) {
  battle.playerIdx = i;
  appendBattleLog(['Go, ' + monsterDisplayName(state.party[i]) + '!']);
  setTimeout(() => resolveEnemyOnlyTurn(), 500);
}
function handleBattleKey() {}

function showVictory() {
  const el = document.getElementById('victoryOverlay');
  el.style.display = 'flex';
}

/* ============================ SHOP ============================ */
const SHOP_STOCK = ['potion', 'super_potion', 'tuxeball', 'tuxeball_refined', 'antidote_grapes', 'revive'];
function openShop() {
  state.screen = 'menu';
  const el = document.getElementById('shopOverlay');
  el.style.display = 'flex';
  renderShop();
}
function renderShop() {
  const el = document.getElementById('shopOverlay');
  el.innerHTML = `<div class="panel"><h2>Item Shop</h2><div class="shoplist">` +
    SHOP_STOCK.map(s => `<div class="shoprow"><span>${ITEMS_DB[s].name} - ₡${ITEMS_DB[s].cost}</span><button onclick="buyItem('${s}')">Buy</button></div>`).join('') +
    `</div><div>Your money: ₡${state.money}</div><button onclick="closeShop()">Leave Shop</button></div>`;
}
function buyItem(slug) {
  const cost = ITEMS_DB[slug].cost;
  if (state.money >= cost) { state.money -= cost; addItem(slug, 1); renderShop(); }
}
function closeShop() { document.getElementById('shopOverlay').style.display = 'none'; state.screen = 'overworld'; }

/* ============================ MENU (pause) ============================ */
function toggleMenu() {
  if (state.screen === 'overworld') { openMenu(); }
  else if (state.screen === 'menu') { closeMenu(); }
}
function openMenu() {
  state.screen = 'menu';
  const el = document.getElementById('menuOverlay');
  el.style.display = 'flex';
  renderMenu();
}
function closeMenu() { document.getElementById('menuOverlay').style.display = 'none'; state.screen = 'overworld'; }
function renderMenu() {
  const el = document.getElementById('menuOverlay');
  el.innerHTML = `<div class="panel">
    <h2>Menu</h2>
    <button onclick="renderPartyMenu()">Creatures</button>
    <button onclick="renderBagMenu()">Bag</button>
    <button onclick="renderBadgesMenu()">Badges</button>
    <button onclick="renderBestiaryMenu()">Bestiary</button>
    <button onclick="renderFastTravelMenu()">Fast Travel</button>
    <button onclick="saveGame()">Save Game</button>
    <button onclick="closeMenu()">Close</button>
  </div>`;
}
function renderPartyMenu() {
  const el = document.getElementById('menuOverlay');
  el.innerHTML = `<div class="panel"><h2>Your Creatures</h2>` + state.party.map(m => {
    const moves = getActiveMoves(m).map(mv => mv.name).join(', ');
    return `<div class="battlecard"><img src="data:image/png;base64,${ASSET_B64.monsters[m.slug]}" style="image-rendering:pixelated;width:64px"><br><b>${monsterDisplayName(m)}</b> Lv${m.level} (${MONSTERS[m.slug].types.join('/')})<br>HP ${m.currentHP}/${m.derived.hp} | EXP ${m.exp}/${expToNext(m.level)}<br>Moves: ${moves}</div>`;
  }).join('') + `<button onclick="renderMenu()">Back</button></div>`;
}
function renderBagMenu() {
  const el = document.getElementById('menuOverlay');
  el.innerHTML = `<div class="panel"><h2>Bag</h2>` + Object.keys(state.inventory).map(s =>
    `<div class="shoprow"><span>${ITEMS_DB[s] ? ITEMS_DB[s].name : s} x${state.inventory[s]}</span></div>`).join('') +
    `<button onclick="renderMenu()">Back</button></div>`;
}
function renderBadgesMenu() {
  const el = document.getElementById('menuOverlay');
  el.innerHTML = `<div class="panel"><h2>Badges (${state.badges.length})</h2>` + state.badges.map(b => `<div>${b}</div>`).join('') + `<button onclick="renderMenu()">Back</button></div>`;
}
function dexStatus(slug) {
  if (state.dex[slug] === 'caught') return 'caught';
  if (state.party.some(m => m.slug === slug) || state.boxParty.some(m => m.slug === slug)) return 'caught';
  if (state.dex[slug] === 'seen') return 'seen';
  return 'unseen';
}
function renderBestiaryMenu() {
  const el = document.getElementById('menuOverlay');
  const slugs = Object.keys(MONSTERS);
  const caughtCount = slugs.filter(s => dexStatus(s) === 'caught').length;
  const cards = slugs.map(slug => {
    const status = dexStatus(slug);
    const mon = MONSTERS[slug];
    if (status === 'unseen') {
      return `<div class="battlecard" style="text-align:center;opacity:0.5"><div style="width:64px;height:44px;margin:0 auto;background:#333;border-radius:4px"></div><b>???</b></div>`;
    }
    const types = mon.types.map(t => `<span class="typebadge" style="background:${TYPE_COLORS[t]||'#888'}">${t}</span>`).join('');
    const img = `<img src="data:image/png;base64,${ASSET_B64.monsters[slug]}" style="image-rendering:pixelated;width:64px;${status==='seen'?'filter:grayscale(1) brightness(0.6)':''}">`;
    return `<div class="battlecard" style="text-align:center">${img}<br><b>${mon.name}</b><br>${types}${status==='caught' ? '<div style="color:#7fd87f;font-size:11px;margin-top:2px">&#10003; Caught</div>' : '<div style="color:#9fb4d8;font-size:11px;margin-top:2px">Seen</div>'}</div>`;
  }).join('');
  el.innerHTML = `<div class="panel" style="max-width:640px">
    <h2>Bestiary (${caughtCount}/${slugs.length} caught)</h2>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:6px;max-height:420px;overflow-y:auto">${cards}</div>
    <button onclick="renderMenu()">Back</button>
  </div>`;
}

function renderFastTravelMenu() {
  const el = document.getElementById('menuOverlay');
  const centers = Object.keys(state.visitedCenters).filter(k => state.visitedCenters[k]);
  const rows = centers.length
    ? centers.map(k => `<div class="shoprow"><span>${MAPS[k].name}</span><button onclick="fastTravelTo('${k}')">Go</button></div>`).join('')
    : `<p>You haven't healed at a Monster Center yet - visit one first to add it here.</p>`;
  el.innerHTML = `<div class="panel"><h2>Fast Travel</h2>${rows}<button onclick="renderMenu()">Back</button></div>`;
}
function fastTravelTo(centerKey) {
  const warp = MAPS[centerKey].extraWarps.find(w => MAPS[w.to] && MAPS[w.to].tiledSrc !== 'interior');
  if (!warp) return;
  state.map = warp.to; state.x = warp.tx; state.y = warp.ty; state.px = warp.tx; state.py = warp.ty;
  closeMenu();
}

/* ============================ SAVE / LOAD ============================ */
function saveGame() {
  localStorage.setItem('emberwild_save', JSON.stringify(state));
  alert('Game saved!');
}
function loadGame() {
  const raw = localStorage.getItem('emberwild_save');
  if (!raw) return false;
  Object.assign(state, JSON.parse(raw));
  return true;
}

/* ============================ Choice dialogue UI hookup ============================ */
function renderChoiceIfNeeded() {
  const box = document.getElementById('choiceBox');
  if (currentChoice && dialogueQueue.length === 0 && box.style.display !== 'block') {
    box.style.display = 'block';
    box.innerHTML = currentChoice.options.map((o, i) => `<button onclick="chooseOption(${i})">${o}</button>`).join('');
  } else if (!currentChoice) {
    box.style.display = 'none';
  }
}
function chooseOption(i) {
  document.getElementById('choiceBox').style.display = 'none';
  const cb = currentChoice.onChoose;
  currentChoice = null;
  cb(i);
}
setInterval(renderChoiceIfNeeded, 100);

/* ============================ MINI-GAME: Berry Toss ============================ */
let minigame = null;
function openMinigame() {
  state.screen = 'minigame';
  minigame = { pos: 0, dir: 1, round: 0, hits: 0 };
  document.getElementById('minigameOverlay').style.display = 'flex';
  requestAnimationFrame(minigameLoop);
}
function minigameLoop() {
  if (state.screen !== 'minigame') return;
  minigame.pos += minigame.dir * 2.2;
  if (minigame.pos > 100 || minigame.pos < 0) minigame.dir *= -1;
  const bar = document.getElementById('minigameBar');
  const marker = document.getElementById('minigameMarker');
  if (marker) marker.style.left = minigame.pos + '%';
  requestAnimationFrame(minigameLoop);
}
window.addEventListener('keydown', e => {
  if (state.screen === 'minigame' && e.key === ' ') {
    e.preventDefault();
    minigame.round++;
    const hit = minigame.pos > 40 && minigame.pos < 60;
    if (hit) minigame.hits++;
    document.getElementById('minigameResult').textContent = hit ? 'Nice throw!' : 'Missed!';
    if (minigame.round >= 5) {
      const reward = minigame.hits >= 4 ? 'imperial_potion' : minigame.hits >= 2 ? 'super_potion' : 'potion';
      addItem(reward, 1);
      document.getElementById('minigameResult').textContent = 'You scored ' + minigame.hits + '/5 and won a ' + ITEMS_DB[reward].name + '!';
      setTimeout(closeMinigame, 1800);
    }
  }
});
function closeMinigame() { document.getElementById('minigameOverlay').style.display = 'none'; state.screen = 'overworld'; }

/* ============================ BOOT ============================ */
function chooseCharacter(sprite) {
  state.playerSprite = sprite;
  document.getElementById('titleScreen').style.display = 'none';
  document.getElementById('charSelectScreen').style.display = 'none';
  state.screen = 'overworld';
  gameLoop();
}
function startNewGame() {
  document.getElementById('charSelectScreen').style.display = 'flex';
  document.getElementById('titleScreen').style.display = 'none';
}
function continueGame() {
  if (loadGame()) {
    document.getElementById('titleScreen').style.display = 'none';
    state.screen = 'overworld';
    gameLoop();
  } else {
    alert('No saved game found.');
  }
}
window.addEventListener('load', () => {
  loadAllImages(() => {
    document.getElementById('loadingScreen').style.display = 'none';
    document.getElementById('titleScreen').style.display = 'flex';
    // Real Tuxemon HP-card frame art (mods/tuxemon/gfx/ui/combat/hp_*_nohp.png) -
    // set as CSS vars here since the base64 data isn't known until ASSET_B64 loads.
    document.documentElement.style.setProperty('--hp-frame-player', "url(data:image/png;base64," + ASSET_B64.battleui.hp_player_frame + ")");
    document.documentElement.style.setProperty('--hp-frame-opponent', "url(data:image/png;base64," + ASSET_B64.battleui.hp_opponent_frame + ")");
  });
});
