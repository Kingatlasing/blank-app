/**
 * Real sold prices for every grade of one card, read from its PriceCharting / SportsCardsPro page
 * ("Full Price Guide" table + the sold-listing counts). Only grades with at least one sold listing are kept,
 * so nothing here is guessed. AGS is not covered by those sites, so it has no price unless one is found.
 * Phone: the page is read directly. Browser build: through the scan server (a browser can't read another site).
 */
import { Platform } from 'react-native';
import { Card, priceUrl } from './catalog';
import { scanServer, serverApi } from './server';

export interface GradePrice { v: number; sales: number }
export type GradeTable = Record<string, GradePrice>;

/** The site's labels -> the app's grade names. */
const LABELS: Record<string, string> = {
  'PSA 10': 'PSA 10', 'BGS 10': 'BGS 10 Pristine', 'BGS 10 Black': 'BGS 10 Black Label',
  'CGC 10': 'CGC 10', 'CGC 10 Pristine': 'CGC 10 Pristine', 'CGC 10 Prist.': 'CGC 10 Pristine',
  'SGC 10': 'SGC 10', 'TAG 10': 'TAG 10', 'ACE 10': 'ACE 10',
  'Grade 9.5': 'Grade 9.5', 'Grade 9': 'Grade 9', 'Grade 8': 'Grade 8', 'Grade 7': 'Grade 7', 'Grade 6': 'Grade 6',
  'Grade 5': 'Grade 5', 'Grade 4': 'Grade 4', 'Grade 3': 'Grade 3', 'Grade 2': 'Grade 2', 'Grade 1': 'Grade 1',
  Ungraded: 'RAW',
};

/** Parse a card page: prices from the full price guide, kept only where the sold-listing count is above 0. */
export function parseGradePage(html: string): GradeTable {
  const counts: Record<string, number> = {};
  for (const m of html.matchAll(/<option value="completed-auctions[^"]*">\s*([^<(]+?)\s*\((\d+)\)\s*<\/option>/g)) {
    const k = LABELS[m[1].trim()];
    if (k) counts[k] = Math.max(counts[k] || 0, +m[2]);
  }
  const out: GradeTable = {};
  for (const m of html.matchAll(/<td>\s*([^<]{2,30}?)\s*<\/td>\s*<td class="price js-price">\s*([^<]*?)\s*<\/td>/g)) {
    const k = LABELS[m[1].trim()];
    const v = parseFloat(m[2].replace(/[$,]/g, ''));
    if (!k || !(v > 0)) continue;
    const n = counts[k];
    if (n === 0 || n === undefined) continue; // no sold listings behind it: the site's own estimate, skipped
    out[k] = { v, sales: n };
  }
  return out;
}

const cache = new Map<string, Promise<GradeTable | null>>();

/** All real graded prices for a catalog card (null when its page can't be reached). Cached per session. */
export function cardGrades(card: Card): Promise<GradeTable | null> {
  const url = priceUrl(card);
  if (!/^https:\/\/www\.(pricecharting|sportscardspro)\.com\/game\//.test(url)) return Promise.resolve(null);
  const hit = cache.get(url);
  if (hit) return hit;
  const p = (async () => {
    if (Platform.OS !== 'web') {
      try {
        const r = await fetch(url, { headers: { Accept: 'text/html' } });
        if (r.ok) return parseGradePage(await r.text());
      } catch {
        /* fall back to the server */
      }
    }
    if (!scanServer()) return null;
    const pre = await serverApi();
    if (pre === null) return null;
    const r = await fetch(`${scanServer()}${pre}/grades?url=${encodeURIComponent(url)}`);
    if (!r.ok) return null;
    const j = await r.json();
    return (j?.grades as GradeTable) || null;
  })().catch(() => null);
  cache.set(url, p);
  p.then((v) => { if (!v) cache.delete(url); });
  return p;
}
