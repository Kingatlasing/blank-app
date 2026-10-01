/**
 * Extra checks after the first match (same rules as the web app, streamlit/core/verify.py):
 * - corrections: a scan that looked like this one was settled on a card before -> that card first
 * - serial numbers: "023/099", "1/1" name the parallel (only parallels with that print run fit)
 * - card back (sports): card number and © year printed on the back
 * They only reorder the matches (and add the right parallel of the top card), never name a card on their own.
 */
import { getCard, loadSet, sets, siblings, type Card } from './catalog';
import { hashDistance } from './imageTools';
import type { Store } from './community';

const SERIAL = /(?<![\d/])(\d{1,4})\s*(?:\/|of)\s*(\d{1,4})(?![\d/])/gi;
const ONE_OF_ONE = /\b(?:1\s*(?:\/|of)\s*1|one\s+of\s+one|1-of-1)\b/i;

export function serials(text: string): [number, number][] {
  const out: [number, number][] = [];
  if (ONE_OF_ONE.test(text || '')) out.push([1, 1]);
  for (const m of (text || '').matchAll(SERIAL)) {
    const n = parseInt(m[1], 10);
    const of = parseInt(m[2], 10);
    if (n > 0 && n <= of && of <= 9999 && !out.some(([a, b]) => a === n && b === of)) out.push([n, of]);
  }
  return out;
}

export function serialFit(text: string, runs: Set<number>): number | null {
  for (const [, of] of serials(text)) if (runs.has(of)) return of;
  return null;
}

const COPYRIGHT = /(?:©|\(c\)|copyright)\s*((?:19|20)\d\d)/gi;
const BACK_NUMBER = /(?:^|\s)(?:no\.?|#|card\s*(?:no\.?|#))\s*([A-Z]{0,4}-?\d{1,4}[A-Z]?)\b/i;

/** Card number and © year read from the back of a sports card (OCR lines, top to bottom). */
export function backFacts(lines: string[]): { number: string; year: number | null; text: string } {
  const text = lines.join('\n');
  const years = [...text.matchAll(COPYRIGHT)].map((m) => parseInt(m[1], 10));
  let number = text.match(BACK_NUMBER)?.[1] || '';
  if (!number) {
    const top = lines.slice(0, Math.max(2, Math.ceil(lines.length / 5)));
    number = top.map((t) => t.trim()).find((t) => /^[A-Z]{0,4}-?\d{1,4}[A-Z]?$/.test(t)) || '';
  }
  return { number, year: years.length ? Math.max(...years) : null, text };
}

const norm = (s: string) => (s || '').toLowerCase().replace(/[^0-9a-z]/g, '').replace(/^0+/, '');
export function numberMatches(cardNo: string, backNo: string) {
  const a = norm(cardNo);
  const b = norm(backNo);
  return !!a && !!b && (a === b || a.endsWith(b) || b.endsWith(a));
}
export function yearMatches(setYear: string | number | undefined, printed: number | null): boolean | null {
  const sy = parseInt(String(setYear || '').slice(0, 4), 10);
  if (!sy || !printed) return null;
  return printed === sy || printed === sy + 1;
}

export interface Refined {
  cards: Card[];
  notes: string[];
}

/** Reorder the catalog matches using corrections, the card back and a serial number. */
export async function refineMatches(
  cards: Card[],
  opts: { phash?: string; text: string; backLines?: string[]; tcg?: boolean; store?: Store | null },
): Promise<Refined> {
  const score = new Map<string, number>();
  const why = new Map<string, string>();
  const byKey = new Map<string, Card>();
  cards.forEach((c, i) => {
    score.set(c.key, 100 - i * 3);
    byKey.set(c.key, c);
  });
  const bump = (c: Card, pts: number, w: string, base = 70) => {
    if (!byKey.has(c.key)) {
      byKey.set(c.key, c);
      score.set(c.key, base);
    }
    score.set(c.key, (score.get(c.key) || 0) + pts);
    if (w) why.set(c.key, w);
  };
  const notes: string[] = [];

  // 1. corrections people made for scans that looked like this one
  if (opts.phash && opts.store) {
    try {
      const best = new Map<string, number>();
      for (const r of await opts.store.corrections()) {
        const d = hashDistance(opts.phash, r.phash);
        if (d <= 8 && (!best.has(r.catalog_key) || d < best.get(r.catalog_key)!)) best.set(r.catalog_key, d);
      }
      for (const [key, d] of [...best.entries()].sort((a, b) => a[1] - b[1]).slice(0, 3)) {
        const setId = key.split('|')[0];
        await loadSet(setId).catch(() => null);
        const c = getCard(key);
        if (c) bump(c, 40 - d * 2, 'picked before for a scan that looked like this', 60);
      }
    } catch {
      /* no corrections yet */
    }
  }
  const order = () => [...byKey.values()].sort((a, b) => (score.get(b.key) || 0) - (score.get(a.key) || 0));

  // 2. the card back: number + © year (sports)
  const back = opts.backLines?.length ? backFacts(opts.backLines) : null;
  if (back && !opts.tcg) {
    for (const c of [...byKey.values()]) {
      if (back.number && numberMatches(c.number, back.number)) bump(c, 12, `number ${back.number} on the back ✓`);
      else if (back.number && c.number) bump(c, -8, '');
      const ym = yearMatches(sets()[c.setId]?.year, back.year);
      if (ym) bump(c, 6, `© ${back.year} on the back ✓`);
      else if (ym === false) bump(c, -10, '');
    }
  }

  // 3. a serial number names the parallel
  const text = `${opts.text}\n${back?.text || ''}`;
  if (!opts.tcg && serials(text).length) {
    const top = order()[0];
    if (top) {
      await loadSet(top.setId).catch(() => null);
      const sib = siblings(top);
      const run = serialFit(text, new Set(sib.map((c) => c.printRun || 0).filter(Boolean)));
      if (run) {
        const topScore = score.get(top.key) || 70;
        for (const c of sib) {
          if (c.printRun === run) bump(c, 30, `serial numbered /${run} ✓`, topScore - 22);
          else if (byKey.has(c.key)) bump(c, -15, '');
        }
        notes.push(`Serial /${run} read on the card: matched to the /${run} parallel.`);
      }
    }
  }
  const out = order();
  const w = out[0] && why.get(out[0].key);
  if (w && !notes.length) notes.push(w);
  return { cards: out, notes };
}
