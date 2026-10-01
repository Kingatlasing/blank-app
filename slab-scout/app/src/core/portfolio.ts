/** Collection value helpers shared by the Portfolio, Collection, Card and Scan screens. */
import type { VaultRecord } from './community';
import { Card, getCard, imageUrl, oddsText, priceUrl, sets, tier, value } from './catalog';

/** Latest catalog price when the record is linked to the card database, else the price saved at scan time. */
export function currentValue(r: VaultRecord): number {
  const c = getCard(r.match?.catalog_key);
  if (c) {
    const [v] = value(c);
    if (v) return v;
  }
  return Number(r.pricing?.raw?.mid) || 0;
}

/** Official photo for a record: the card database photo, else the matched database image. */
export function recordImage(r: VaultRecord): string {
  return imageUrl(getCard(r.match?.catalog_key))[0] || r.match?.image_url || '';
}

export const inCollection = (r: VaultRecord) => (r.list || 'collection') === 'collection';

export function recordFromCatalog(c: Card, extra: Partial<VaultRecord> = {}): Omit<VaultRecord, 'id'> {
  const s = sets()[c.setId];
  const t = tier(c);
  const now = new Date().toISOString();
  const [v] = value(c);
  return {
    v: 1,
    added_at: now,
    card: {
      game: s?.category || '', name: c.name, set: s?.name || '', number: c.number, year: s?.year || '', brand: s?.brand || '',
      rarity: (c.variant || 'Base') + (c.printRun ? ` /${c.printRun}` : ''), variant: c.variant, card_type: c.variant ? 'Parallel' : 'Base',
    },
    grade: {},
    authenticity: { verdict: 'not_checked', reasons: [] },
    pricing: {
      raw: { mid: v ?? undefined }, currency: 'USD', note: `${s?.source || ''} sold-listing price${s?.prices_as_of ? ` (${s.prices_as_of})` : ''}`,
      graded_label: 'PSA 10', graded_mid: c.psa10, priced_at: now,
    },
    match: { source: 'catalog', catalog_key: c.key, url: priceUrl(c), image_url: '' },
    thumb: '', phash: '', print_run: c.printRun, odds: oddsText(t, s), list: 'collection',
    ...extra,
  };
}

export const today = () => new Date().toISOString().slice(0, 10);

/** Cards whose value moved a lot since they were added (20%+ and at least $5), biggest move first. */
export function priceMoves(recs: VaultRecord[], minPct = 20, minAbs = 5): { rec: VaultRecord; was: number; now: number; pct: number }[] {
  const out: { rec: VaultRecord; was: number; now: number; pct: number }[] = [];
  for (const r of recs) {
    const was = Number(r.pricing?.raw?.mid) || 0;
    const now = currentValue(r);
    if (was > 0 && now > 0 && Math.abs(now - was) >= minAbs && (Math.abs(now - was) / was) * 100 >= minPct) {
      out.push({ rec: r, was, now, pct: ((now - was) / was) * 100 });
    }
  }
  return out.sort((a, b) => Math.abs(b.now - b.was) - Math.abs(a.now - a.was));
}
