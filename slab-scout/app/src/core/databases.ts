/** Free card databases (no keys): TCGdex (Pokémon), YGOPRODeck (Yu-Gi-Oh!), Scryfall (Magic), Lorcast (Lorcana). */

export interface Candidate {
  game: string;
  name: string;
  set: string;
  number: string;
  year: string;
  brand: string;
  rarity: string;
  variant: string;
  card_type: string;
  image_url: string;
  url: string;
  source: string;
  ref_id: string;
  raw: { low?: number; mid?: number; high?: number };
  price_note: string;
  currency: 'USD' | 'EUR';
  official_distance?: number | null;
}

const H = { 'User-Agent': 'SlabScout/1.0', Accept: 'application/json' };
async function get(url: string): Promise<any> {
  try {
    const r = await fetch(url, { headers: H });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}
const qs = (o: Record<string, string | number>) => Object.entries(o).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&');
const num = (v: any) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return typeof n === 'number' && isFinite(n) && n > 0 ? n : undefined;
};
const cand = (c: Partial<Candidate>): Candidate => ({
  game: '', name: '', set: '', number: '', year: '', brand: '', rarity: '', variant: '', card_type: '', image_url: '', url: '',
  source: '', ref_id: '', raw: {}, price_note: '', currency: 'USD', ...c,
});

function pokemonType(r = '') {
  const x = r.toLowerCase();
  if (/special illustration|hyper|secret|gold|rainbow/.test(x)) return 'Secret Rare';
  if (/illustration|full art|ultra/.test(x)) return 'Full Art';
  if (/holo|double rare/.test(x)) return 'Holo';
  if (/promo/.test(x)) return 'Promo';
  return 'Base';
}

export async function searchPokemon(name: string, number: string, limit = 6): Promise<Candidate[]> {
  const base: Record<string, string | number> = { 'pagination:itemsPerPage': 40 };
  if (name) base.name = name;
  const local = number ? number.split('/')[0].trim() : '';
  let briefs: any[] = [];
  if (local) {
    for (const lid of [...new Set([local, local.replace(/^0+/, '') || '0', local.padStart(3, '0')])]) {
      briefs = briefs.concat((await get(`https://api.tcgdex.net/v2/en/cards?${qs({ ...base, localId: `eq:${lid}` })}`)) || []);
    }
  }
  if (!briefs.length && name) briefs = (await get(`https://api.tcgdex.net/v2/en/cards?${qs(base)}`)) || [];
  const total = number.includes('/') ? number.split('/')[1].trim().replace(/^0+/, '') : '';
  const seen = new Set<string>();
  const scored: [number, Candidate][] = [];
  for (const b of briefs.slice(0, limit * 2)) {
    if (seen.has(b.id)) continue;
    seen.add(b.id);
    const full = await get(`https://api.tcgdex.net/v2/en/cards/${b.id}`);
    if (!full) continue;
    const s = full.set || {};
    const count = s.cardCount?.official;
    let score = 0;
    if (total && count && String(count).replace(/^0+/, '') === total) score += 2;
    if (name && (full.name || '').toLowerCase().includes(name.toLowerCase())) score += 1;
    const tp = full.pricing?.tcgplayer || {};
    const rows = Object.values(tp).filter((v: any) => v && typeof v === 'object' && v.marketPrice) as any[];
    const pref = ['holofoil', 'holo', 'normal', 'reverse-holofoil', 'reverse'].map((k) => tp[k]).find((v) => v?.marketPrice) || rows[0];
    const cm = full.pricing?.cardmarket || {};
    const img = full.image || b.image || '';
    scored.push([
      score,
      cand({
        game: 'Pokémon', name: full.name, set: s.name || '', number: count ? `${full.localId}/${count}` : full.localId,
        brand: 'The Pokémon Company', rarity: full.rarity || '', card_type: pokemonType(full.rarity), image_url: img ? `${img}/high.jpg` : '',
        url: `https://tcgdex.dev/cards/${b.id}`, source: 'TCGdex', ref_id: b.id,
        ...(pref
          ? { raw: { low: num(pref.lowPrice), mid: num(pref.marketPrice), high: num(pref.highPrice) }, price_note: `TCGplayer market price (updated ${String(tp.updated || '').slice(0, 10)})` }
          : cm.trend || cm.avg
            ? { raw: { low: num(cm.low), mid: num(cm.trend || cm.avg) }, price_note: 'Cardmarket trend (EUR)', currency: 'EUR' as const }
            : {}),
      }),
    ]);
  }
  return scored.sort((a, b) => b[0] - a[0]).slice(0, limit).map((x) => x[1]);
}

export async function searchYugioh(name: string, setCode: string, limit = 6): Promise<Candidate[]> {
  if (!name) return [];
  const d = await get(`https://db.ygoprodeck.com/api/v7/cardinfo.php?${qs({ fname: name, num: 10, offset: 0 })}`);
  const out: Candidate[] = [];
  for (const c of d?.data || []) {
    const sets: any[] = c.card_sets || [];
    const chosen = setCode ? sets.find((s) => (s.set_code || '').toUpperCase() === setCode.toUpperCase()) : null;
    for (const s of chosen ? [chosen] : sets.slice(0, 3)) {
      out.push(cand({
        game: 'Yu-Gi-Oh!', name: c.name, set: s?.set_name || '', number: s?.set_code || '', brand: 'Konami', rarity: s?.set_rarity || '',
        card_type: c.humanReadableCardType || c.type || '', image_url: c.card_images?.[0]?.image_url || '', url: c.ygoprodeck_url || '',
        source: 'YGOPRODeck', ref_id: String(c.id), raw: { mid: num(s?.set_price) || num(c.card_prices?.[0]?.tcgplayer_price) }, price_note: 'YGOPRODeck set / TCGplayer price',
      }));
    }
    if (out.length >= limit) break;
  }
  return out.slice(0, limit);
}

export async function searchMtg(name: string, number: string, limit = 6): Promise<Candidate[]> {
  let q = name ? `"${name}"` : '';
  const cn = number ? number.split('/')[0].replace(/^0+/, '') : '';
  if (cn) q += ` cn:${cn}`;
  if (!q.trim()) return [];
  const d = await get(`https://api.scryfall.com/cards/search?${qs({ q: q.trim(), unique: 'prints', order: 'released' })}`);
  return (d?.data || []).slice(0, limit).map((c: any) =>
    cand({
      game: 'Magic: The Gathering', name: c.name, set: c.set_name, number: c.collector_number, year: (c.released_at || '').slice(0, 4),
      brand: 'Wizards of the Coast', rarity: (c.rarity || '').replace(/^./, (x: string) => x.toUpperCase()), card_type: c.type_line || '',
      image_url: c.image_uris?.normal || c.card_faces?.[0]?.image_uris?.normal || '', url: c.scryfall_uri || '', source: 'Scryfall', ref_id: c.id,
      raw: { mid: num(c.prices?.usd) || num(c.prices?.usd_foil) }, price_note: 'Scryfall USD price',
    }),
  );
}

export async function searchLorcana(name: string, limit = 6): Promise<Candidate[]> {
  if (!name) return [];
  const d = await get(`https://api.lorcast.com/v0/cards/search?${qs({ q: name })}`);
  return (d?.results || []).slice(0, limit).map((c: any) =>
    cand({
      game: 'Lorcana', name: [c.name, c.version].filter(Boolean).join(' - '), set: c.set?.name || '', number: String(c.collector_number || ''),
      year: (c.released_at || '').slice(0, 4), brand: 'Ravensburger', rarity: c.rarity || '', image_url: c.image_uris?.digital?.normal || '',
      source: 'Lorcast', ref_id: c.id, raw: { mid: num(c.prices?.usd) || num(c.prices?.usd_foil) }, price_note: 'Lorcast USD price',
    }),
  );
}

export const DB_GAMES = ['Pokémon', 'Yu-Gi-Oh!', 'Magic: The Gathering', 'Lorcana'];

export async function searchAll(name: string, number: string, setCode: string, game: string): Promise<Candidate[]> {
  const jobs: Promise<Candidate[]>[] = [];
  if (!game || game === 'Pokémon') jobs.push(searchPokemon(name, number));
  if (!game || game === 'Yu-Gi-Oh!') jobs.push(searchYugioh(name, setCode));
  if (!game || game === 'Magic: The Gathering') jobs.push(searchMtg(name, number));
  if (!game || game === 'Lorcana') jobs.push(searchLorcana(name));
  return (await Promise.all(jobs)).flat().slice(0, 8);
}

export function soldLinks(q: string, gradedLabel = '', imageUrl = ''): [string, string][] {
  const e = (s: string) => encodeURIComponent(s);
  const links: [string, string][] = [
    ['eBay sold', `https://www.ebay.com/sch/i.html?_nkw=${e(q)}&LH_Sold=1&LH_Complete=1`],
    ['eBay PSA 10 sold', `https://www.ebay.com/sch/i.html?_nkw=${e(q + ' PSA 10')}&LH_Sold=1&LH_Complete=1`],
    ['130point', 'https://130point.com/sales/'],
    ['PriceCharting', `https://www.pricecharting.com/search-products?q=${e(q)}&type=prices`],
    ['Google', `https://www.google.com/search?q=${e(q + ' sold price')}`],
  ];
  if (gradedLabel && gradedLabel !== 'PSA 10') links.splice(1, 0, [`eBay ${gradedLabel} sold`, `https://www.ebay.com/sch/i.html?_nkw=${e(q + ' ' + gradedLabel)}&LH_Sold=1&LH_Complete=1`]);
  if (imageUrl) links.push(['Google Lens', `https://lens.google.com/uploadbyurl?url=${e(imageUrl)}`]);
  return links;
}
