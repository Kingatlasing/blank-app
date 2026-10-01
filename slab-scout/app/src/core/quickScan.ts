/** Live-scanner identification: one photo in, the best match with its price out, fast (no grading).
 * Order: card code on the card -> photo fingerprint against every price-guide photo -> card database text
 * match -> free TCG databases. The full grading flow runs only when the person taps Grade. */
import type { VaultRecord } from './community';
import { DB_GAMES, type Candidate } from './databases';
import { cardBack, identify } from './identify';
import { fingerprintCard, thumbnail } from './imageTools';
import { parseText, readText } from './ocr';
import { nameGuess, readLabel } from './slab';
import { Card, closestRemote, getCard, matchText, photoLookup, searchRemote, sets, value } from './catalog';
import { recordFromCatalog } from './portfolio';
import { colourSignature, describeColours, rankParallels } from './colour';
import { refineMatches } from './verify';
import type { Store } from './community';
import type { ScanItem } from './scanHistory';

const uid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;

export async function quickIdentify(uri: string, game: string, store?: Store | null): Promise<ScanItem> {
  const [phash, thumb, lines] = await Promise.all([fingerprintCard(uri), thumbnail(uri, 160), readText(uri).catch(() => [] as string[])]);
  const base: ScanItem = { id: uid(), at: new Date().toISOString(), uri, thumb, phash, game: '', name: '', set: '', number: '', rarity: '', price: null, currency: 'USD', source: '' };
  const back = cardBack(lines);
  if (back) return { ...base, game: back, note: `Back of a ${back} card: scan the front to identify it (the back is used when grading).` };
  const g = game === 'Auto' ? '' : game;
  const parsed = parseText(lines, g);
  const sl = readLabel(lines);
  if (sl) {
    parsed.name = nameGuess(sl) || parsed.name;
    parsed.number = sl.number || parsed.number;
  }
  const cm = matchText(parsed.rawText, parsed.name, parsed.number);
  let byPicture = false;
  if (!cm.byCode) {
    try {
      const pm = await photoLookup(phash);
      if (pm.length && pm[0].distance <= 6) {
        const pics = pm.map((m) => m.card);
        cm.cards = [...pics, ...cm.cards.filter((c) => !pics.some((p) => p.key === c.key))];
        byPicture = true;
      }
    } catch {
      /* fingerprints not downloaded and offline */
    }
  }
  const gg = g || parsed.game;
  if (!cm.byCode && !byPicture && parsed.name && !DB_GAMES.includes(gg)) {
    try {
      const more = await searchRemote(`${parsed.name} ${parsed.number ? parsed.number.split('/')[0] : ''}`, 20);
      cm.cards = [...cm.cards, ...more.filter((m) => !cm.cards.some((c) => c.key === m.key))];
    } catch {}
  }
  let byClosest = false;
  if (!cm.byCode && !cm.cards.length && (parsed.name || parsed.rawText)) {
    // nothing matched word for word: the closest names (misread letters, missing words)
    try {
      cm.cards = await closestRemote(parsed.rawText, parsed.name, parsed.number);
      byClosest = cm.cards.length > 0;
    } catch {}
  }
  let refineNote = '';
  let refined = false;
  if (!cm.byCode) {
    // corrections people made before + a serial number on the card (see verify.ts)
    try {
      const r = await refineMatches(cm.cards, { phash, text: parsed.rawText, tcg: DB_GAMES.includes(gg) || ['One Piece', 'Dragon Ball', 'Digimon'].includes(gg), store });
      refined = !!r.notes.length;
      cm.cards = r.cards;
      refineNote = r.notes[0] || '';
    } catch {}
  }
  let top = cm.cards[0];
  const nameOk = top && (!parsed.name || top.name.toLowerCase().split(/\s+/).some((w) => w.length > 2 && parsed.rawText.toLowerCase().includes(w)) || byClosest);
  if (top && (cm.byCode || byPicture || nameOk || refined)) {
    // same card, several parallels (Silver / Blue / Gold Prizm...): let the colours pick the parallel,
    // unless a printed card code already named the exact one
    let note: string | undefined = refineNote || undefined;
    if (!cm.byCode && !/serial/i.test(refineNote)) {
      try {
        const sig = await colourSignature(uri);
        const ranked = await rankParallels(top, sig);
        const cur = ranked.find((r) => r.card.key === top!.key);
        const best = ranked[0];
        const clear = best && (ranked.length === 1 || ranked[1].fit - best.fit >= 0.15); // gold vs bronze can tie
        if (best && clear && best.card.key !== top.key && best.fit <= 0.3 && (!cur || cur.fit - best.fit >= 0.25)) {
          note = `Parallel picked by colour: ${best.card.variant || 'Base'} (${describeColours(sig)}). Check the back or serial number.`;
          top = best.card;
        } else if (cur && cur.fit >= 0.65) {
          note = `Colours don't look like ${top.variant || 'Base'} (${describeColours(sig)}): check which parallel this is.`;
        }
      } catch {
        /* colour check is optional */
      }
    }
    return { ...fromCatalog(top), id: base.id, at: base.at, uri, thumb, phash, note, source: byPicture ? 'picture match' : byClosest ? 'closest match to the text read' : 'card database' };
  }
  if ((!gg || DB_GAMES.includes(gg)) && (parsed.name || parsed.number)) {
    const list = await identify(lines, parsed.rawText, parsed.name, parsed.number, parsed.setCode, gg).catch(() => []);
    const best = list[0];
    if (best && best.score >= 45) {
      return { ...base, game: best.game, name: best.name, set: best.set, number: best.number, rarity: best.rarity, price: best.raw.mid ?? null, currency: best.currency, source: best.source, cand: stripCand(best) };
    }
  }
  return { ...base, game: gg, name: parsed.name, number: parsed.number, source: parsed.name ? 'text read' : '', note: parsed.name ? 'Not sure about this one: tap Grade to check the details.' : 'Could not read this card. Move closer, fill the frame and tap again.' };
}

function stripCand(c: Candidate): Candidate {
  const { official_distance, ...rest } = c as Candidate & { score?: number; why?: string[] };
  delete (rest as any).score;
  delete (rest as any).why;
  return rest as Candidate;
}

function fromCatalog(c: Card): ScanItem {
  const s = sets()[c.setId];
  const [v] = value(c);
  return {
    id: '', at: '', uri: '', thumb: '', phash: '', game: s?.category || '', name: c.name, set: s?.name || '', number: c.number,
    rarity: (c.variant || 'Base') + (c.printRun ? ` /${c.printRun}` : ''), price: v, currency: 'USD', source: 'card database', catalog_key: c.key,
  };
}

/** A collection record for a scanned card, or null when it wasn't identified well enough to save. */
export function recordFromScan(it: ScanItem, list: 'collection' | 'wishlist' = 'collection'): Omit<VaultRecord, 'id'> | null {
  const c = it.catalog_key ? getCard(it.catalog_key) : null;
  if (c) return recordFromCatalog(c, { thumb: it.thumb, phash: it.phash, list });
  if (!it.name) return null;
  const now = new Date().toISOString();
  const d = it.cand;
  return {
    v: 1, added_at: now, list,
    card: { game: it.game, name: it.name, set: it.set, number: it.number, year: d?.year || '', brand: d?.brand || '', rarity: it.rarity, variant: d?.variant || '', card_type: d?.card_type || 'Base' },
    grade: {}, authenticity: { verdict: 'not_checked', reasons: [] },
    pricing: { raw: d?.raw || { mid: it.price ?? undefined }, currency: it.currency, note: d?.price_note || '', graded_label: '', graded_mid: null, priced_at: now },
    match: { source: it.source, ref_id: d?.ref_id || '', image_url: d?.image_url || '', url: d?.url || '' },
    thumb: it.thumb, phash: it.phash, print_run: null, odds: '',
  };
}
