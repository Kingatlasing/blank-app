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

/** True when the record is a graded / slabbed card (a grade label or PSA number saved on it). */
export const isGraded = (r: VaultRecord) => !!(r.grade?.label || r.grade?.psa != null || r.grade?.tag_grade != null);

/** "Grade worthy": raw cards whose PSA 10 price is far above their raw price, biggest uplift first. */
export function gradeWorthy(recs: VaultRecord[], limit = 12): { rec: VaultRecord; raw: number; psa10: number; pct: number }[] {
  const out: { rec: VaultRecord; raw: number; psa10: number; pct: number }[] = [];
  const seen = new Set<string>();
  for (const r of recs) {
    if (isGraded(r)) continue;
    const c = getCard(r.match?.catalog_key);
    const raw = currentValue(r);
    const psa10 = Number(c?.psa10 || (r.pricing?.graded_label === 'PSA 10' ? r.pricing?.graded_mid : 0)) || 0;
    const k = r.match?.catalog_key || r.id;
    if (raw > 0 && psa10 > raw && !seen.has(k)) {
      seen.add(k);
      out.push({ rec: r, raw, psa10, pct: ((psa10 - raw) / raw) * 100 });
    }
  }
  return out.sort((a, b) => b.pct - a.pct).slice(0, limit);
}

/** Change in value over the last `days` days of the history (null when there is no older point). */
export function changeOver(hist: { day: string; value: number }[], now: number, days: number): { abs: number; pct: number } | null {
  if (!hist.length) return null;
  const since = new Date(Date.now() - days * 864e5).toISOString().slice(0, 10);
  const base = hist.find((h) => h.day >= since) || null;
  const older = [...hist].reverse().find((h) => h.day < since);
  const ref = older || base;
  if (!ref || ref.day === today()) return null;
  const abs = now - ref.value;
  return { abs, pct: ref.value ? (abs / ref.value) * 100 : 0 };
}
