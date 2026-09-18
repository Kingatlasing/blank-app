'use strict';
/* ============================================================================
   MONSTER TAMER: EMBERWILD TRAILS
   An original creature-collecting RPG. Creature/item/move data and pixel art
   are adapted from the open-source Tuxemon project (github.com/Tuxemon/Tuxemon,
   GPL-3.0 code / CC-BY-SA 4.0 art). See ATTRIBUTIONS.md for full credit.
   All game code, world design, story, and UI in this file are original.
============================================================================ */

/* ---------------------------- Image loading ---------------------------- */
const IMG = { monsters: {}, items: {}, tiles: {}, chars: {}, elements: {}, buildings: {} };
let ATLAS_IMG = null;
const ATLAS_COLS = TILED.atlasCols;
let imagesLoaded = 0, imagesTotal = 0;
function loadAllImages(cb) {
  const cats = ['monsters', 'items', 'tiles', 'chars', 'elements', 'buildings'];
  for (const cat of cats) {
    for (const key in ASSET_B64[cat]) imagesTotal++;
  }
  imagesTotal++; // world atlas
  ATLAS_IMG = new Image();
  ATLAS_IMG.onload = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
  ATLAS_IMG.onerror = () => { imagesLoaded++; if (imagesLoaded >= imagesTotal) cb(); };
  ATLAS_IMG.src = 'data:image/png;base64,' + TILED.atlas;
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
  camera: { x: 0, y: 0 }
};

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
    { id: 'mom', x: 8, y: 35, sprite: 'townsfolk2', facing: 'down',
      dialogue: () => ["Off on an adventure already? Don't forget to visit Professor Larkspur first!"] },
    { id: 'rival', x: 18, y: 35, sprite: 'rival', facing: 'down', dialogue: rivalHometownDialogue },
    { id: 'nurse', x: 9, y: 17, sprite: 'nurse', facing: 'down', heal: true, fastTravel: true,
      dialogue: () => ["Welcome to the Monster Center!", "Your creatures are fighting fit. Take care out there!"] },
    { id: 'shopkeeper', x: 17, y: 17, sprite: 'shopkeeper', facing: 'down', shop: true,
      dialogue: () => ["Take a look at my wares!"] },
    { id: 'professor', x: 26, y: 17, sprite: 'professor', facing: 'down', dialogue: professorDialogue },
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
    { id: 'nurse', x: 7, y: 7, sprite: 'nurse', facing: 'down', heal: true, fastTravel: true,
      dialogue: () => ["Welcome to the Monster Center!", "Your creatures are fighting fit. Take care out there!"] },
    { id: 'shopkeeper', x: 32, y: 7, sprite: 'shopkeeper', facing: 'down', shop: true,
      dialogue: () => ["Take a look at my wares!"] },
    { id: 'leader_sylva', x: 11, y: 26, sprite: 'leader_sylva', facing: 'down', trainer: {
        name: 'Arena Leader Sylva', team: [
          { slug: 'anoleaf', level: 9 }, { slug: 'budaye', level: 9 }, { slug: 'chloragon', level: 10 },
        ], prizeMoney: 300, flag: 'sylva_defeated', badge: 'Bramble Badge',
        preBattle: ["I am Sylva, Leader of the Ashveld Hall.", "Let's see if your team has truly grown!"],
        postWin: ["Impressive. Take this Bramble Badge as proof of your victory."],
      } },
    { id: 'sidequest_giver', x: 8, y: 16, sprite: 'townsfolk1', facing: 'down', dialogue: lostPetDialogue },
    { id: 'minigame_host', x: 18, y: 16, sprite: 'townsfolk2', facing: 'down', minigame: true },
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
    { id: 'nurse', x: 6, y: 7, sprite: 'nurse', facing: 'down', heal: true, fastTravel: true,
      dialogue: () => ["Rest up before you challenge Pyra - she battles hot!"] },
    { id: 'shopkeeper', x: 15, y: 7, sprite: 'shopkeeper', facing: 'down', shop: true, dialogue: () => ["Welcome!"] },
    { id: 'leader_pyra', x: 34, y: 18, sprite: 'leader_pyra', facing: 'down', trainer: {
        name: 'Arena Leader Pyra', team: [
          { slug: 'embra', level: 16 }, { slug: 'agnidon', level: 17 }, { slug: 'cardiling', level: 16 },
        ], prizeMoney: 600, flag: 'pyra_defeated', badge: 'Cinder Badge',
        preBattle: ["I'm Pyra. My creatures burn brighter than any rival's.", "Show me your fire!"],
        postWin: ["You've got real heat. Take the Cinder Badge."],
      } },
    { id: 'guide', x: 25, y: 7, sprite: 'townsfolk2', facing: 'down', dialogue: bridgeGuideDialogue },
    { id: 'outpost_gate', x: 24, y: 35, sprite: 'townsfolk1', facing: 'down',
      dialogue: () => (state.flags.enforcerDefeated ? ["The Enforcer Outpost is cleared out for good."] :
        ["The Enforcers are holed up south of here.", "Someone should really do something about that..."]) },
    { id: 'summit_sign', x: 28, y: 35, sprite: 'townsfolk2', facing: 'down',
      dialogue: () => (state.flags.enforcerDefeated ? ["The path south leads to the Summit and the Champion.", "Good luck out there."] :
        ["This path is closed until the Enforcer trouble is dealt with."]) },
  ],
  extraWarps: [
    { x: 24, y: 36, w: 1, h: 1, to: 'enforcerhideout', tx: 6, ty: 10, requires: null },
    { x: 28, y: 36, w: 1, h: 1, to: 'summitplateau', tx: 7, ty: 12, requires: 'enforcerDefeated' },
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

/* ---------------------------- NPC dialogue functions ---------------------------- */
function professorDialogue() {
  if (!state.flags.starterChosen) {
    return { choice: true,
      lines: ["Ah, a new trainer! I'm Professor Larkspur.", "Every journey starts with a partner. Choose wisely:"],
      options: STARTERS.map(s => MONSTERS[s].name),
      onChoose: (i) => {
        const slug = STARTERS[i];
        state.party.push(createMonsterInstance(slug, 5));
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
    if (state.screen === 'dialogue' && !currentChoice) state.screen = 'overworld';
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
    startTrainerBattle(npc.trainer);
    return;
  }
  if (npc.wildFixed && !state.flags.lostPetDone) {
    startWildBattle(npc.wildFixed.slug, npc.wildFixed.level, true);
    return;
  }
  if (npc.heal) {
    for (const m of state.party) m.currentHP = m.derived.hp;
  }
  if (npc.shop) { openShop(); return; }
  if (npc.minigame) { openMinigame(); return; }
  let result = npc.dialogue ? npc.dialogue() : null;
  if (!result) return;
  if (result.trainerNow) { startTrainerBattle(result.trainerNow); return; }
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
    const td = TILED.maps[map.tiledKey];
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
    const td = TILED.maps[map.tiledKey];
    const allWarps = (td.warps || []).concat(map.extraWarps || []);
    const hit = allWarps.find(w => state.x >= w.x && state.x < w.x + w.w && state.y >= w.y && state.y < w.y + w.h);
    if (hit) {
      if (hit.requires && !state.flags[hit.requires]) {
        pushDialogue(["It's blocked for now."]);
        state.x = state.moveFrom.x; state.y = state.moveFrom.y;
        return;
      }
      const targetKey = hit.to;
      const targetMap = MAPS[targetKey];
      const targetTd = TILED.maps[targetKey];
      let tx = hit.tx, ty = hit.ty;
      if (tx === undefined && targetTd && targetTd.spawns[hit.spawn]) {
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

function drawAtlasTile(slot, dx, dy) {
  if (!slot || !ATLAS_IMG || !ATLAS_IMG.complete) return;
  const idx = slot - 1;
  const sx = (idx % ATLAS_COLS) * SRC_TILE, sy = Math.floor(idx / ATLAS_COLS) * SRC_TILE;
  ctx.drawImage(ATLAS_IMG, sx, sy, SRC_TILE, SRC_TILE, dx, dy, TILE, TILE);
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
  const td = TILED.maps[map.tiledKey];
  ctx.fillStyle = '#87ceeb';
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
      drawAtlasTile(td.below[i], dx, dy);
      drawAtlasTile(td.world[i], dx, dy);
      if (td.grass && td.grass[i]) { ctx.fillStyle = 'rgba(20,60,20,0.18)'; ctx.fillRect(dx, dy, TILE, TILE); }
    }
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
      drawAtlasTile(td.above[ty * td.w + tx], dx, dy);
    }
  }
}

/* ---------------------------- Game loop / movement animation ---------------------------- */
function updateMovementAnim() {
  if (state.moving) {
    state.moveProgress = (state.moveProgress || 0) + 0.22;
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
  if (state.screen === 'overworld' || state.screen === 'dialogue') renderOverworld();
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
  state.screen = 'battle';
  openBattleUI();
}
function startTrainerBattle(trainerDef) {
  battle = {
    kind: 'trainer', trainer: trainerDef,
    enemyTeam: trainerDef.team.map(t => createMonsterInstance(t.slug, t.level)),
    enemyIdx: 0,
    playerIdx: state.party.findIndex(m => m.currentHP > 0),
    log: [], turnLock: false,
  };
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

function renderBattleScene() {
  ctx.fillStyle = '#cfe8c9';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#8fbf7a';
  ctx.fillRect(0, canvas.height * 0.55, canvas.width, canvas.height * 0.45);
  const enemy = currentEnemy();
  const pm = currentPlayerMon();
  if (enemy) {
    const im = IMG.monsters[enemy.slug];
    if (im && im.complete) ctx.drawImage(im, canvas.width * 0.62, canvas.height * 0.14, 64 * 2.4, 44 * 2.4);
  }
  if (pm) {
    const im = IMG.monsters[pm.slug];
    if (im && im.complete) ctx.drawImage(im, canvas.width * 0.08, canvas.height * 0.42, 64 * 2.8, 44 * 2.8);
  }
}
(function hookBattleRender() {
  const origLoop = gameLoop;
})();

function battleHpBar(m) {
  const pct = Math.max(0, Math.floor(m.currentHP / m.derived.hp * 100));
  const typeBadges = MONSTERS[m.slug].types.map(t => `<span class="typebadge" style="background:${TYPE_COLORS[t]||'#888'}">${t}</span>`).join('');
  return `<div class="battlecard"><b>${monsterDisplayName(m)}</b> Lv${m.level} ${typeBadges}<div class="hpbar"><div class="hpfill" style="width:${pct}%;background:${pct>50?'#4caf50':pct>20?'#e0a52b':'#e04b2b'}"></div></div><div class="hptext">${m.currentHP}/${m.derived.hp} HP</div></div>`;
}

function renderBattleMain() {
  const enemy = currentEnemy(); const pm = currentPlayerMon();
  const top = document.getElementById('battleTop');
  top.innerHTML = (battle.trainer ? `<div class="trainername">${battle.trainer.name}</div>` : '') + battleHpBar(enemy) + battleHpBar(pm);
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
  });
});
