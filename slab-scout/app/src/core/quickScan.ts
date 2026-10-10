/** Live-scanner identification: one photo in, the best match with its price out, fast (no grading).
 * Order: card code on the card -> photo fingerprint against every price-guide photo -> card database text
 * match -> free TCG databases. The full grading flow runs only when the person taps Grade. */
import type { VaultRecord } from './community';
import { DB_GAMES, type Candidate } from './databases';
import { cardBack, identify } from './identify';
import { fingerprintCard, thumbnail } from './imageTools';
import { parseText, readText } from './ocr';
import { nameGuess, readLabel } from './slab';
import { Card, closestRemote, getCard, loadSet, matchText, photoLookup, searchRemote, sets, value } from './catalog';
import { recordFromCatalog } from './portfolio';
import { colourSignature, describeColours, rankParallels } from './colour';
import { playerName, refineMatches } from './verify';
import type { Store } from './community';
import type { ScanItem } from './scanHistory';
import { serverOn, serverScan, type ServerMatch } from './server';

const uid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;

/** Sports cards (and other photo-heavy sets) reuse the same picture across many parallels and years, so the front
 * alone often can't settle which one it is. */
export const HARD_GAMES = ['Sports', 'Baseball', 'Basketball', 'Football', 'Soccer', 'Hockey', 'Racing', 'Wrestling', 'UFC', 'Golf', 'Tennis', 'Boxing'];
const isHard = (game: string) => HARD_GAMES.includes(game);

/** One photo of the front identifies most cards. Asks for the back (needBack) only when the match isn't certain
 * or it's a sports card whose parallels / years look alike and nothing printed (card code, serial) settled it. */
export async function quickIdentify(uri: string, game: string, store?: Store | null, orig?: string, backUri?: string | null): Promise<ScanItem> {
  const read: { text?: string[]; backText?: string[] } = {};
  const it = { ...(await identifyOnce(uri, game, store, orig, backUri, read)), ...clean(read) };
  if (backUri) return { ...it, withBack: true, needBack: undefined };
  return it;
}

/** the text kept with a scan: the lines actually read, trimmed (no empty lines, at most 80 lines of 200 characters) */
function clean(read: { text?: string[]; backText?: string[] }) {
  const tidy = (l?: string[]) => (l || []).map((t) => String(t).trim().slice(0, 200)).filter(Boolean).slice(0, 80);
  return { text: tidy(read.text), backText: tidy(read.backText) };
}

async function identifyOnce(uri: string, game: string, store?: Store | null, orig?: string, backUri?: string | null,
  read: { text?: string[]; backText?: string[] } = {}): Promise<ScanItem> {
  // scan server first (full engine: text in English / Japanese / Korean, fingerprint, colours, serials);
  // the text reader below reuses its answer, and the phone's own checks run if it's unreachable
  const srv = serverOn() ? serverScan(orig || uri, { game, grade: false, key: uri, back: backUri || null, timeoutMs: 60000 }) : null;
  const [phash, thumb, lines, backLines] = await Promise.all([
    fingerprintCard(uri), thumbnail(uri, 160), readText(uri).catch(() => [] as string[]),
    backUri ? readText(backUri).catch(() => [] as string[]) : Promise.resolve([] as string[]),
  ]);
  const base: ScanItem = { id: uid(), at: new Date().toISOString(), uri, thumb, phash, game: '', name: '', set: '', number: '', rarity: '', price: null, currency: 'USD', source: '' };
  const s = srv ? await srv : null;
  // keep what was read: the scan server's reading when it answered (sharper, repairs misread words), else the phone's
  read.text = s?.lines?.length ? s.lines : lines;
  read.backText = s?.back_lines?.length ? s.back_lines : backLines;
  if (s) {
    if (s.is_back) return { ...base, game: s.is_back, note: `Back of a ${s.is_back} card: scan the front to identify it (the back is used when grading).` };
    const top = s.matches[0];
    if (top && top.score >= 55) {
      const item = await fromServer(top, base);
      const note = s.slab ? `${s.slab.grade_text} slab${s.slab.cert ? ` · cert ${s.slab.cert}` : ''}` : top.why[0];
      const second = s.matches[1];
      const printed = top.why.some((w) => /code|serial|number on the card|slab|cert/i.test(w)) || !!s.slab;
      const close = !!second && second.score >= top.score - 8 && second.name === top.name;
      const needBack = printed ? undefined
        : top.score < 75 ? 'Not fully sure from the front alone.'
        : isHard(item.game || top.game) && close ? `${top.name} has look-alike parallels / years.`
        : undefined;
      return { ...item, uri, thumb, phash, note: note || item.note, source: 'scan server', needBack };
    }
  }
  const back = cardBack(lines, phash);
  if (back) return { ...base, game: back, note: `Back of a ${back} card: scan the front to identify it (the back is used when grading).` };
  const g = game === 'Auto' ? '' : game;
  const parsed = parseText(lines, g);
  const sl = readLabel(lines);
  if (sl) {
    parsed.name = nameGuess(sl) || parsed.name;
    parsed.number = sl.number || parsed.number;
  }
  const tcgGame = DB_GAMES.includes(g || parsed.game) || ['One Piece', 'Dragon Ball', 'Digimon'].includes(g || parsed.game);
  if (!tcgGame) {
    // 'MIKE' / 'TROUT' on separate lines -> 'Mike Trout' (not the team name)
    const pn = await playerName(lines).catch(() => '');
    if (pn && !pn.toLowerCase().split(' ').every((w) => (parsed.name || '').toLowerCase().includes(w))) parsed.name = pn;
  }
  const cm = matchText(parsed.rawText, parsed.name, parsed.number);
  let byPicture = false;
  if (!cm.byCode) {
    try {
      const pm = await photoLookup(phash, 12, 8, game === "Auto" ? "" : game);
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
      const r = await refineMatches(cm.cards, { phash, text: parsed.rawText, number: parsed.number, backLines, tcg: DB_GAMES.includes(gg) || ['One Piece', 'Dragon Ball', 'Digimon'].includes(gg), store });
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
    const item = fromCatalog(top);
    const siblings = cm.cards.filter((c) => c.key !== top!.key && c.name === top!.name).length;
    const settled = cm.byCode || /serial|back/i.test(refineNote);
    const needBack = settled ? undefined
      : byClosest || (!byPicture && !refined && !cm.byCode) ? 'Not fully sure from the front alone.'
      : isHard(item.game) && siblings > 0 ? `${top.name} has ${siblings + 1} look-alike versions.`
      : undefined;
    return { ...item, id: base.id, at: base.at, uri, thumb, phash, note, needBack, source: byPicture ? 'picture match' : byClosest ? 'closest match to the text read' : 'card database' };
  }
  if ((!gg || DB_GAMES.includes(gg)) && (parsed.name || parsed.number)) {
    const list = await identify(lines, parsed.rawText, parsed.name, parsed.number, parsed.setCode, gg).catch(() => []);
    const best = list[0];
    if (best && best.score >= 45) {
      return { ...base, game: best.game, name: best.name, set: best.set, number: best.number, rarity: best.rarity, price: best.raw.mid ?? null, currency: best.currency, source: best.source, cand: stripCand(best),
        needBack: best.score < 70 ? 'Not fully sure from the front alone.' : undefined };
    }
  }
  return { ...base, game: gg, name: parsed.name, number: parsed.number, source: parsed.name ? 'text read' : '', needBack: parsed.name ? 'Could not match this card from the front.' : undefined, note: parsed.name ? 'Not sure about this one: tap Grade to check the details.' : 'Could not read this card. Move closer, fill the frame and tap again.' };
}

/** A server match as a scan result: the phone's own catalog card when it has it (prices, parallels, add to collection). */
async function fromServer(m: ServerMatch, base: ScanItem): Promise<ScanItem> {
  if (m.kind === 'catalog' && m.key && m.set_id) {
    await loadSet(m.set_id).catch(() => null);
    const c = getCard(m.key);
    if (c) return { ...fromCatalog(c), id: base.id, at: base.at };
  }
  const rarity = [m.rarity, m.variant && m.variant !== 'Base' ? m.variant : ''].filter(Boolean).join(' ') + (m.print_run ? ` /${m.print_run}` : '');
  return { ...base, game: m.game, name: m.name, set: m.set, number: m.number, rarity, price: m.price ?? null, currency: 'USD', source: 'scan server' };
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
  const text = it.text?.length || it.backText?.length ? { text: { front: it.text || [], back: it.backText || [] } } : {};
  if (c) return { ...recordFromCatalog(c, { thumb: it.thumb, phash: it.phash, list }), ...text };
  if (!it.name) return null;
  const now = new Date().toISOString();
  const d = it.cand;
  return {
    v: 1, added_at: now, list,
    card: { game: it.game, name: it.name, set: it.set, number: it.number, year: d?.year || '', brand: d?.brand || '', rarity: it.rarity, variant: d?.variant || '', card_type: d?.card_type || 'Base' },
    grade: {}, authenticity: { verdict: 'not_checked', reasons: [] },
    pricing: { raw: d?.raw || { mid: it.price ?? undefined }, currency: it.currency, note: d?.price_note || '', graded_label: '', graded_mid: null, priced_at: now },
    match: { source: it.source, ref_id: d?.ref_id || '', image_url: d?.image_url || '', url: d?.url || '' },
    thumb: it.thumb, phash: it.phash, print_run: null, odds: '', ...text,
  };
}
