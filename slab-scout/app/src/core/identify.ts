import { hashDistance } from './imageTools';
/**
 * Identify the exact card from what's printed on it (same logic as the web app's core/identify.py):
 * real card names found in the text, card number, printed set size, HP, attacks, illustrator.
 * Each candidate gets a score and the facts that matched ("name ✓ · number 006 ✓ · HP 330 ✓").
 */
import { Candidate, searchLorcana, searchMtg, searchYugioh } from './databases';

export type Scored = Candidate & { score: number; why: string[] };

const H = { 'User-Agent': 'SlabScout/1.0', Accept: 'application/json' };
async function get(url: string): Promise<any> {
  try {
    const r = await fetch(url, { headers: H });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

export const norm = (s: string) =>
  (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9' ]+/g, ' ').replace(/\s+/g, ' ').trim();
export const numKey = (s: string) => {
  const m = (s || '').trim().toLowerCase().match(/^([a-z]*)0*(\d+)([a-z]*)$/);
  return m ? `${m[1]}${m[2]}${m[3]}` : (s || '').toLowerCase();
};

let pokeIdx: { at: number; byName: Map<string, any[]>; names: string[]; setCount: Map<string, number>; briefs: any[] } | null = null;
async function pokemonIndex() {
  if (pokeIdx && Date.now() - pokeIdx.at < 24 * 3600e3) return pokeIdx;
  const [briefs, sets] = await Promise.all([get('https://api.tcgdex.net/v2/en/cards'), get('https://api.tcgdex.net/v2/en/sets')]);
  if (!briefs?.length) return null;
  const byName = new Map<string, any[]>();
  for (const b of briefs) {
    const k = norm(b.name || '');
    const a = byName.get(k);
    if (a) a.push(b);
    else byName.set(k, [b]);
  }
  const setCount = new Map<string, number>();
  for (const s of sets || []) if (s?.id) setCount.set(s.id, s.cardCount?.official);
  pokeIdx = { at: Date.now(), byName, names: [...byName.keys()], setCount, briefs };
  return pokeIdx;
}

/** Real card names found in the top lines of text (longest exact phrase wins; close spelling as fallback). */
function matchNames(lines: string[], names: Set<string>, nameList: string[]): { name: string; score: number; exact: boolean }[] {
  const unglue = (t: string) => t.replace(/([a-z])(ex|EX|GX|VMAX|VSTAR)\b/g, '$1 $2').replace(/\b([A-Z][a-z]{2,})[C@©€eE]\b/g, '$1 ex');
  const top = lines.slice(0, Math.max(3, Math.ceil(lines.length * 0.45))).map(unglue);
  const found = new Map<string, { score: number; exact: boolean }>();
  top.forEach((line, li) => {
    const words = norm(line.replace(/\bHP\s*\d+|\d+\s*HP\b/gi, ' ')).split(' ').filter(Boolean);
    for (let i = 0; i < words.length; i++)
      for (let j = i + 1; j <= Math.min(words.length, i + 5); j++) {
        const p = words.slice(i, j).join(' ');
        if (p.length >= 3 && names.has(p)) {
          const sc = p.length * (1.4 - li / Math.max(1, top.length)) + 20;
          if (sc > (found.get(p)?.score || 0)) found.set(p, { score: sc, exact: true });
        }
      }
  });
  if (!found.size) {
    top.forEach((line) => {
      const t = norm(line.replace(/\bHP\s*\d+/gi, ' '));
      if (t.length < 4) return;
      for (const n of nameList) {
        if (Math.abs(n.length - t.length) > 3) continue;
        const r = similarity(t, n);
        if (r >= 0.8 && n.length * r > (found.get(n)?.score || 0)) found.set(n, { score: n.length * r, exact: false });
      }
    });
  }
  const keys = [...found.keys()];
  for (const k of keys) if (keys.some((o) => o !== k && ` ${o} `.includes(` ${k} `))) found.delete(k);
  return [...found.entries()].map(([name, v]) => ({ name, ...v })).sort((a, b) => b.score - a.score);
}

function similarity(a: string, b: string) {
  // normalised Levenshtein similarity
  const m = a.length, n = b.length;
  if (!m || !n) return 0;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    for (let j = 1; j <= n; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur;
  }
  return 1 - prev[n] / Math.max(m, n);
}

function pokemonPrice(full: any) {
  const tp = full.pricing?.tcgplayer || {};
  const rows = Object.values(tp).filter((v: any) => v && typeof v === 'object' && v.marketPrice) as any[];
  const pref = ['holofoil', 'holo', 'normal', 'reverse-holofoil', 'reverse'].map((k) => tp[k]).find((v) => v?.marketPrice) || rows[0];
  if (pref) return { raw: { low: pref.lowPrice, mid: pref.marketPrice, high: pref.highPrice }, price_note: 'TCGplayer market price', currency: 'USD' as const };
  const cm = full.pricing?.cardmarket || {};
  if (cm.trend || cm.avg) return { raw: { low: cm.low, mid: cm.trend || cm.avg }, price_note: 'Cardmarket trend (EUR)', currency: 'EUR' as const };
  return {};
}

export async function identifyPokemon(lines: string[], rawText: string, number: string, limit = 6): Promise<Scored[]> {
  const idx = await pokemonIndex();
  if (!idx) return [];
  const text = ` ${norm(rawText)} `;
  const names = matchNames(lines, new Set(idx.names), idx.names);
  const local = number ? numKey(number.split('/')[0]) : '';
  const total = number.includes('/') ? numKey(number.split('/')[1]) : '';
  const setOf = (id: string) => (id.includes('-') ? id.slice(0, id.lastIndexOf('-')) : '');
  let pool = new Map<string, { b: any; hit: boolean; exact: boolean }>();
  const SUFFIXES = ['ex', 'gx', 'v', 'vmax', 'vstar'];
  for (const n of names.slice(0, 3)) {
    for (const b of idx.byName.get(n.name) || []) pool.set(b.id, { b, hit: true, exact: n.exact });
    // the suffix logo (ex, V, VMAX...) is often unreadable: consider those versions too
    if (!SUFFIXES.some((x) => n.name.endsWith(' ' + x)))
      for (const x of SUFFIXES) for (const b of idx.byName.get(`${n.name} ${x}`) || []) if (!pool.has(b.id)) pool.set(b.id, { b, hit: true, exact: false });
  }
  if (local) {
    const same = new Map([...pool].filter(([, v]) => numKey(v.b.localId || '') === local));
    if (same.size) pool = same;
  }
  if (!pool.size && local) {
    for (const b of idx.briefs) {
      if (numKey(b.localId || '') !== local) continue;
      const cnt = idx.setCount.get(setOf(b.id));
      if (!total || (cnt && numKey(String(cnt)) === total)) pool.set(b.id, { b, hit: false, exact: false });
    }
  }
  const pre = (v: { b: any; hit: boolean }) => {
    const cnt = idx.setCount.get(setOf(v.b.id));
    return (v.hit ? 2 : 0) + (local && numKey(v.b.localId || '') === local ? 2 : 0) + (total && cnt && numKey(String(cnt)) === total ? 2 : 0);
  };
  const ranked = [...pool.values()].sort((a, b) => pre(b) - pre(a)).slice(0, 10);
  const hpM = rawText.match(/\bHP\s*(\d{2,3})\b|\b(\d{2,3})\s*HP\b/i);
  // 'HP' and the number are often read as separate pieces near the name at the top
  const hpLine = lines.slice(0, 6).map((l) => l.trim()).find((l) => /^\d{2,3}$/.test(l) && +l >= 30 && +l <= 400 && +l % 10 === 0);
  const hp = hpM ? hpM[1] || hpM[2] : hpLine || '';
  const fulls = await Promise.all(ranked.map((v) => get(`https://api.tcgdex.net/v2/en/cards/${v.b.id}`)));
  const out: Scored[] = [];
  ranked.forEach((v, i) => {
    const full = fulls[i];
    if (!full) return;
    const s = full.set || {};
    const count = s.cardCount?.official;
    const why: string[] = [];
    let score = 0;
    if (v.hit) {
      score += v.exact ? 40 : 28;
      why.push(`name ${full.name} ✓`);
    } else if (text.includes(` ${norm(full.name || '')} `)) {
      score += 30;
      why.push(`name ${full.name} ✓`);
    }
    if (local && numKey(full.localId || '') === local) {
      score += 20;
      why.push(`number ${full.localId} ✓`);
    }
    if (total && count && numKey(String(count)) === total) {
      score += 15;
      why.push(`set size ${count} ✓`);
    }
    if (hp && String(full.hp || '') === hp) {
      score += 10;
      why.push(`HP ${hp} ✓`);
    }
    const moves = [...(full.attacks || []), ...(full.abilities || [])].map((a: any) => a?.name || '').filter(Boolean);
    const squashed = text.replace(/ /g, ''); // OCR often drops spaces: 'ChaoticPain'
    const hits = moves.filter((m: string) => text.includes(` ${norm(m)} `) || (norm(m).length >= 8 && squashed.includes(norm(m).replace(/ /g, ''))));
    if (hits.length) {
      score += Math.min(15, 6 * hits.length);
      why.push(`attack ${hits.slice(0, 2).join(', ')} ✓`);
    }
    const sn = norm(s.name || '');
    if (sn.length >= 3 && text.includes(` ${sn} `)) {
      score += 8;
      why.push(`set ${s.name} ✓`);
    }
    const img = full.image || v.b.image || '';
    out.push({
      game: 'Pokémon', name: full.name || '', set: s.name || '', number: count ? `${full.localId}/${count}` : full.localId || '', year: '',
      brand: 'The Pokémon Company', rarity: full.rarity || '', variant: '', card_type: '', image_url: img ? `${img}/high.jpg` : '',
      url: `https://tcgdex.dev/cards/${v.b.id}`, source: 'TCGdex', ref_id: v.b.id, raw: {}, price_note: '', currency: 'USD',
      ...pokemonPrice(full), score: Math.min(100, score), why,
    } as Scored);
  });
  return out.sort((a, b) => b.score - a.score).slice(0, limit);
}

/** Best official-database candidates for the text on a card, highest score first. */
export async function identify(lines: string[], rawText: string, name: string, number: string, setCode: string, game: string): Promise<Scored[]> {
  const out: Scored[] = [];
  try {
    if (!game || game === 'Pokémon') out.push(...(await identifyPokemon(lines, rawText, number)));
    if (game === 'Yu-Gi-Oh!' || (!game && setCode)) out.push(...(await searchYugioh(name || lines[0] || '', setCode)).map((c) => ({ ...c, score: setCode && c.number.toUpperCase() === setCode.toUpperCase() ? 80 : 50, why: [`name ${c.name} ✓`, ...(setCode && c.number.toUpperCase() === setCode.toUpperCase() ? [`set code ${setCode} ✓`] : [])] })));
    if (game === 'Magic: The Gathering' || (!game && !out.length && name)) out.push(...(await searchMtg(name, number)).map((c) => ({ ...c, score: 50, why: [`name ${c.name} ✓`] })));
    if (game === 'Lorcana') out.push(...(await searchLorcana(name)).map((c) => ({ ...c, score: 50, why: [`name ${c.name} ✓`] })));
  } catch {}
  return out.sort((a, b) => b.score - a.score);
}

/** The game's name if this photo is the BACK of a card (just the logo, no card name), else ''. */
// fingerprint of the standard Pokémon back (swirl + Poké Ball): spots backs the text reader can't read
// (angled, sleeved, 'PeKOMoN'). Clean backs come out ~4 away, card fronts 28+. Same as the web app.
const BACK_PHASH: Record<string, string[]> = { 'Pokémon': ['d1226e9ef171468b'] };

export function cardBack(lines: string[], phash = ''): string {
  const dist: Record<string, number> = {};
  if (phash) for (const [g, hs] of Object.entries(BACK_PHASH)) dist[g] = Math.min(...hs.map((h) => hashDistance(phash, h)));
  for (const [g, d] of Object.entries(dist)) if (d <= 12) return g;
  const words = lines.map((t) => norm(t)).filter((t) => t.length >= 4);
  if (words.length > 8) return '';
  const toks = words.flatMap((w) => w.split(' '));
  const poke = toks.filter((t) => similarity(t, 'pokemon') >= 0.55).length;
  const texty = lines.some((t) => t.trim().split(/\s+/).length >= 3 || /\d{2,}/.test(t)); // rules text, HP, numbers = a front
  const other = toks.filter((t) => t.length >= 4 && similarity(t, 'pokemon') < 0.55).length; // e.g. a card name
  if ((poke >= 2 || (poke >= 1 && (dist['Pokémon'] ?? 64) <= 26)) && !texty && other <= 1) return 'Pokémon';
  const blob = words.join(' ');
  if (blob.includes('deckmaster') || (blob.includes('magic') && blob.includes('gathering'))) return 'Magic: The Gathering';
  if (blob.includes('konami') && words.length <= 3) return 'Yu-Gi-Oh!';
  return '';
}
