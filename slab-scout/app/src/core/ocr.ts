/** On-device text reading (free, no network) + parsing. Needs the installed app build; in Expo Go it's unavailable and the user types details instead. */

let extractor: { isSupported: boolean; extractTextFromImage: (uri: string) => Promise<string[]> } | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  extractor = require('expo-text-extractor');
} catch {
  extractor = null;
}

export const ocrAvailable = () => !!extractor?.isSupported;

export async function readText(uri: string): Promise<string[]> {
  if (!extractor?.isSupported) return [];
  try {
    return (await extractor.extractTextFromImage(uri)).map((t) => t.trim()).filter(Boolean);
  } catch {
    return [];
  }
}

export const BRANDS = [
  'Topps', 'Bowman', 'Panini', 'Prizm', 'Donruss', 'Optic', 'Select', 'Mosaic', 'Upper Deck', 'Fleer', 'Score', 'Leaf', 'Skybox',
  'Pacific', 'Stadium Club', 'Chrome', 'Finest', 'Heritage', 'National Treasures', 'Contenders', 'Kakawow', 'Wild Card', 'Cardsmiths',
  'Card.Fun', 'Zenith', 'Hit Parade', 'Goodwin', 'Allen & Ginter', 'Futera', 'Sage', 'Onyx', 'Historic Autographs', 'Moments in History',
  'Michael Jackson',
];
const GAME_HINTS: Record<string, string[]> = {
  'Pokémon': ['pokémon', 'pokemon', 'weakness', 'resistance', 'retreat', 'illus.', 'hp', 'trainer', 'energy', 'basic'],
  'Yu-Gi-Oh!': ['atk/', 'def/', 'atk', 'effect]', 'spellcaster', 'konami', '[spell card]', '[trap card]', 'warrior', 'dragon/'],
  'Magic: The Gathering': ['creature —', 'creature -', 'instant', 'sorcery', 'enchantment', 'artifact', 'legendary', 'wizards of the coast'],
  Lorcana: ['lorcana', 'storyborn', 'dreamborn', 'floodborn', 'lore', 'willpower'],
  'One Piece': ['one piece', 'don!!', 'counter', 'leader', 'straw hat'],
  Baseball: ['mlb', 'baseball', 'pitcher', 'outfield', 'rbi', 'home runs'],
  Basketball: ['nba', 'basketball', 'rebounds', 'assists', 'guard', 'forward'],
  Football: ['nfl', 'football', 'quarterback', 'touchdowns', 'rushing', 'receiving'],
  Hockey: ['nhl', 'hockey', 'goals', 'defenseman', 'goaltender'],
  Soccer: ['fifa', 'premier league', 'uefa', 'mls', 'soccer'],
};

export interface Parsed {
  game: string;
  name: string;
  number: string;
  setCode: string;
  year: string;
  brand: string;
  serial: string;
  rawText: string;
}

const NUM_SLASH = /((?:TG|GG|SV|RC|SWSH|SM|XY|BW)?\d{1,3}[a-z]?)\s*\/\s*((?:TG|GG|SV|RC)?\d{2,3})/;
const YGO_CODE = /\b([A-Z0-9]{2,5}-[A-Z]{0,2}\d{2,3}[A-Z]?)\b/;
const YEAR = /(?:^|\D)(19[3-9]\d|20[0-3]\d)(?!\d)/g;
const SERIAL = /\b(\d{1,4})\s*\/\s*(\d{1,4})\b/g;
const SERIAL_RUNS = new Set([5, 10, 25, 49, 50, 75, 99, 100, 149, 150, 199, 249, 250, 299, 499]);

export function parseText(lines: string[], gameHint = ''): Parsed {
  const blob = lines.join('\n');
  const low = blob.toLowerCase();
  let game = gameHint;
  if (!game) {
    let best = ['', 0] as [string, number];
    for (const [g, keys] of Object.entries(GAME_HINTS)) {
      const sc = keys.filter((k) => low.includes(k)).length;
      if (sc > best[1]) best = [g, sc];
    }
    game = best[1] >= 2 ? best[0] : '';
  }
  let setCode = '';
  const y = blob.match(YGO_CODE);
  if (y && (!game || game === 'Yu-Gi-Oh!')) {
    setCode = y[1];
    game = game || 'Yu-Gi-Oh!';
  }
  const m = blob.match(NUM_SLASH);
  const number = m ? `${m[1]}/${m[2]}` : '';
  const years = [...blob.matchAll(YEAR)].map((x) => +x[1]);
  const brand = BRANDS.find((b) => low.includes(b.toLowerCase())) || '';
  let name = '';
  for (const t of lines.slice(0, Math.max(3, Math.ceil(lines.length / 3)))) {
    let c = t.trim();
    const lc = c.toLowerCase();
    if (BRANDS.some((b) => lc.includes(b.toLowerCase())) || /(19[3-9]\d|20[0-3]\d)/.test(c)) continue;
    if (c.length < 3 || /^[\d\s/\-HPhp:.]+$/.test(c) || ['basic', 'stage 1', 'stage 2', 'trainer', 'pokémon', 'pokemon'].includes(c.toLowerCase())) continue;
    const letters = (c.match(/[A-Za-zÀ-ÿ]/g) || []).length;
    if (letters < 3 || letters < 0.6 * c.replace(/\s/g, '').length || /^s?tage\s*\d/i.test(c)) continue; // '#70@', 'TAGE2'
    c = c.replace(/(HP|hp)\s*\d+/g, '').replace(/([a-z])(ex|EX|GX|VMAX|VSTAR|V)\b/g, '$1 $2').trim();
    if (c.length >= 3) {
      name = c;
      break;
    }
  }
  let serial = '';
  for (const s of blob.matchAll(SERIAL)) if (SERIAL_RUNS.has(+s[2]) && +s[1] <= +s[2]) serial = `${s[1]}/${s[2]}`;
  return { game, name, number, setCode, year: years.length ? String(Math.max(...years)) : '', brand, serial, rawText: blob };
}
