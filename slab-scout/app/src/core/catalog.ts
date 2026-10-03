/**
 * Built-in card database (same files as the Streamlit app: data/catalog → assets/catalog).
 * Every card we collected with its parallel, print run, sold prices and pull odds.
 * Loaded lazily on first use so the app opens fast.
 */

import { useEffect, useState } from 'react';
import { Directory, File, Paths } from 'expo-file-system';
import { ungzip } from 'pako';

export interface Tier {
  name: string;
  print_run: number | null;
  count: number;
  priced?: number;
  median_raw?: number | null;
  top_raw?: number | null;
  odds?: string;
  estimate?: string;
  ebay_median?: number;
  ebay_n?: number;
  ebay_query?: string;
}

export interface SetInfo {
  id: string;
  name: string;
  brand: string;
  category: string;
  year: string;
  cards: number;
  tiers: Tier[];
  box?: { packs_per_box?: number; cards_per_pack?: number; note?: string };
  notes?: string;
  source?: string;
  source_url: string;
  base_url?: string;
  prices_as_of?: string;
  estimate_source?: string;
  odds_list?: { type: string; odds: string }[];
  /** card list is not bundled; download with loadSet() */
  remote?: boolean;
  /** sample card photo for sets without per-card photos */
  image?: string;
  /** photo id of the set's most valuable card (series / set tiles) */
  cover?: string;
}

export interface Card {
  setId: string;
  name: string;
  number: string;
  variant: string;
  printRun: number | null;
  raw: number | null;
  psa9: number | null;
  psa10: number | null;
  path: string;
  key: string;
  /** price-guide photo id; '~id' = photo of another parallel of the same card */
  img: string;
}

export interface SoldListing {
  d: string;
  p: number;
  t: string;
  u: string;
}

let _sets: Record<string, SetInfo> | null = null;
let _cards: Card[] | null = null;
let _byKey: Map<string, Card> | null = null;
let _bySet: Map<string, Card[]> | null = null;
let _index: Map<string, number[]> | null = null;
let _sales: Record<string, { n: number; median: number; sales: SoldListing[] }> | null = null;

export const cardKeyOf = (setId: string, number: string, variant: string, name: string) => `${setId}|${number}|${variant}|${name}`;

/** Big brand pulls (every Upper Deck / Topps baseball set...) live on GitHub, one file per set plus
 * name-search shards, and are downloaded when a set is opened or a search needs them. */
// big catalog files live on the repo's catalog-data branch (replaced on each publish, keeps the code history small)
export const REMOTE = 'https://raw.githubusercontent.com/Kingatlasing/blank-app/catalog-data/remote';
const _loadedSets = new Set<string>();
const _loadedShards = new Set<string>();
const _pending = new Map<string, Promise<any>>();
let _version = 0;
const _listeners = new Set<() => void>();
/** Re-render hook: bumps whenever downloaded cards are added. */
export function onCatalogChange(fn: () => void) {
  _listeners.add(fn);
  return () => _listeners.delete(fn);
}
export const catalogVersion = () => _version;
/** Re-renders the component when downloaded cards arrive. */
export function useCatalogVersion() {
  const [v, setV] = useState(_version);
  useEffect(() => {
    const off = onCatalogChange(() => setV(_version));
    return () => {
      off();
    };
  }, []);
  return v;
}

const toCard = ([setId, name, number, variant, printRun, raw, psa9, psa10, path, img]: any[]): Card => ({
  setId, name, number: number || '', variant: variant || '', printRun, raw, psa9, psa10, path: path || '', img: img || '',
  key: cardKeyOf(setId, number || '', variant || '', name),
});

function addRows(rows: any[][]) {
  load();
  let added = 0;
  for (const r of rows) {
    const c = toCard(r);
    if (_byKey!.has(c.key)) continue;
    _byKey!.set(c.key, c);
    _cards!.push(c);
    const a = _bySet!.get(c.setId);
    if (a) a.push(c);
    else _bySet!.set(c.setId, [c]);
    added++;
  }
  if (added) {
    _index = null;
    _version++;
    _listeners.forEach((f) => f());
  }
}

async function fetchJson(url: string) {
  if (_pending.has(url)) return _pending.get(url);
  const p = fetch(url).then((r) => {
    if (!r.ok) throw new Error(`Couldn't download card list (${r.status})`);
    return r.json();
  });
  _pending.set(url, p);
  try {
    return await p;
  } finally {
    _pending.delete(url);
  }
}

/* ---------- offline copy on the phone ----------
 * Every downloaded set / name shard is saved under documents/catalog, so it keeps working without internet.
 * "Download everything" in Settings fetches all of them up front (see remote/index.json). */
let _dir: Directory | null = null;
function cacheDir(): Directory {
  if (!_dir) {
    _dir = new Directory(Paths.document, 'catalog');
    if (!_dir.exists) _dir.create({ intermediates: true, idempotent: true });
  }
  return _dir;
}
const cacheFile = (rel: string) => new File(cacheDir(), rel.replace(/\//g, '__'));

const parseGz = (buf: ArrayBuffer) => JSON.parse(ungzip(new Uint8Array(buf), { to: 'string' }));

/** Remote catalog files are gzip-compressed JSON: read the saved copy, else download (and save) it. */
async function cachedJson(rel: string) {
  try {
    const f = cacheFile(rel);
    if (f.exists) return parseGz(await f.arrayBuffer());
  } catch {
    /* corrupt / missing: download again */
  }
  const url = `${REMOTE}/${rel}`;
  if (_pending.has(url)) return _pending.get(url);
  const p = fetch(url).then(async (r) => {
    if (!r.ok) throw new Error(`Couldn't download card list (${r.status})`);
    const buf = await r.arrayBuffer();
    try {
      const f = cacheFile(rel);
      if (!f.exists) f.create();
      f.write(new Uint8Array(buf));
    } catch {
      /* no space: still usable this session */
    }
    return parseGz(buf);
  });
  _pending.set(url, p);
  try {
    return await p;
  } finally {
    _pending.delete(url);
  }
}

export interface OfflineStatus { files: number; total: number; bytes: number; totalBytes: number; version: string }

/** How much of the card database is saved on this phone. Pass the online index to compare. */
export async function offlineStatus(): Promise<OfflineStatus> {
  let idx: { version: string; files: [string, number][]; bytes: number } | null = null;
  try {
    idx = await fetchJson(`${REMOTE}/index.json`);
  } catch {
    try {
      const f = cacheFile('index.json');
      if (f.exists) idx = JSON.parse(await f.text());
    } catch {
      idx = null;
    }
  }
  let files = 0;
  let bytes = 0;
  for (const [rel, size] of idx?.files || []) {
    if (cacheFile(rel).exists) {
      files++;
      bytes += size;
    }
  }
  return { files, total: idx?.files.length || 0, bytes, totalBytes: idx?.bytes || 0, version: idx?.version || '' };
}

/** Save the whole card database on the phone (skips files already saved). */
export async function downloadAll(onProgress: (done: number, total: number) => void, signal?: { cancelled: boolean }) {
  const idx: { version: string; files: [string, number][] } = await fetchJson(`${REMOTE}/index.json`);
  // newer data online: drop saved files that changed so they download again
  try {
    const old = cacheFile('index.json');
    if (old.exists) {
      const prev: { version: string; files: [string, number][] } = JSON.parse(await old.text());
      if (prev.version !== idx.version) {
        const was = new Map(prev.files);
        for (const [rel, size] of idx.files) {
          const f = cacheFile(rel);
          if (f.exists && was.get(rel) !== size) f.delete();
        }
      }
    }
  } catch {
    /* no previous copy */
  }
  const todo = idx.files.filter(([rel]) => !cacheFile(rel).exists);
  let done = idx.files.length - todo.length;
  onProgress(done, idx.files.length);
  const q = [...todo];
  await Promise.all(
    [0, 1, 2, 3].map(async () => {
      while (q.length && !signal?.cancelled) {
        const [rel] = q.shift()!;
        try {
          await File.downloadFileAsync(`${REMOTE}/${rel}`, cacheFile(rel), { idempotent: true });
        } catch {
          /* retry next time */
        }
        done++;
        onProgress(done, idx.files.length);
      }
    }),
  );
  const f = cacheFile('index.json');
  if (!f.exists) f.create();
  f.write(JSON.stringify(idx));
}

/** Delete the saved copy (the bundled sets stay). */
export function clearOffline() {
  try {
    cacheDir().delete();
  } catch {
    /* already gone */
  }
  _dir = null;
}

/* ---------- picture matching ---------- */
type PhTable = { hi: Uint32Array; lo: Uint32Array; meta: [string, string][] };
const _ph = new Map<string, PhTable>(); // per fingerprint group (pokemon, football, ...)
const popcnt = (v: number) => {
  v = v - ((v >>> 1) & 0x55555555);
  v = (v & 0x33333333) + ((v >>> 2) & 0x33333333);
  return (((v + (v >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
};

// which fingerprint group(s) a game's cards are in (same groups as data/build_catalog.py phash_group)
const PH_GROUP: Record<string, string[]> = {
  'Pokémon': ['pokemon'], 'Pokémon Japanese / Korean': ['pokemon'], 'Yu-Gi-Oh!': ['yugioh'], 'Magic: The Gathering': ['magic'],
  Lorcana: ['tcg'], 'One Piece': ['tcg'], 'Dragon Ball': ['tcg'], Digimon: ['tcg'], Gundam: ['tcg'], Riftbound: ['tcg'], 'Other TCG': ['tcg'],
  Baseball: ['baseball'], Basketball: ['basketball'], Football: ['football'], Soccer: ['soccer'], Hockey: ['hockey'],
  Sports: ['baseball', 'basketball', 'football', 'soccer', 'hockey', 'othersports'],
  'Star Wars': ['nonsport'], Marvel: ['nonsport'], 'Harry Potter': ['nonsport'], 'Garbage Pail Kids': ['nonsport'], Kakawow: ['nonsport'], 'Non-sport': ['nonsport'],
};

let _idx: { version: string; files: [string, number][]; phash?: Record<string, string[]> } | null = null;
async function remoteIndex() {
  if (_idx) return _idx;
  try {
    _idx = await fetchJson(`${REMOTE}/index.json`);
  } catch {
    const f = cacheFile('index.json');
    _idx = f.exists ? JSON.parse(await f.text()) : { version: '', files: [] };
  }
  return _idx!;
}

async function phTable(group: string, files: string[]): Promise<PhTable> {
  const have = _ph.get(group);
  if (have) return have;
  let rows: [string, string, string][] = [];
  for (const f of files) {
    try {
      rows = rows.concat(await cachedJson(f));
    } catch {
      /* missing part: use the rest */
    }
  }
  const hi = new Uint32Array(rows.length);
  const lo = new Uint32Array(rows.length);
  rows.forEach(([h], i) => {
    hi[i] = parseInt(h.slice(0, 8), 16) >>> 0;
    lo[i] = parseInt(h.slice(8), 16) >>> 0;
  });
  const t: PhTable = { hi, lo, meta: rows.map(([, im, sid]) => [im, sid]) };
  _ph.set(group, t);
  return t;
}

/** Cards whose price-guide photo looks like this scan (perceptual hash), closest first. Works offline once
 * saved. With a game picked, only that game's fingerprints are loaded (much less memory than all of them). */
export async function photoLookup(hash: string, maxDistance = 12, limit = 8, game = ''): Promise<{ card: Card; distance: number }[]> {
  if (!hash || hash.length !== 16) return [];
  const idx = await remoteIndex();
  const tables: PhTable[] = [];
  if (idx.phash) {
    const want = PH_GROUP[game] || Object.keys(idx.phash);
    for (const g of want) if (idx.phash[g]) tables.push(await phTable(g, idx.phash[g]));
  } else {
    // older publish: phash-0..n holds every game
    const parts: string[] = [];
    for (let i = 0; i < 16; i++) parts.push(`phash-${i}.json.gz`);
    tables.push(await phTable('all', parts.filter((p) => idx.files.some(([f]) => f === p))));
  }
  const qh = parseInt(hash.slice(0, 8), 16) >>> 0;
  const ql = parseInt(hash.slice(8), 16) >>> 0;
  const best: [number, PhTable, number][] = [];
  for (const t of tables)
    for (let i = 0; i < t.hi.length; i++) {
      const d = popcnt((t.hi[i] ^ qh) >>> 0) + popcnt((t.lo[i] ^ ql) >>> 0);
      if (d <= maxDistance) best.push([d, t, i]);
    }
  best.sort((a, b) => a[0] - b[0]);
  const out: { card: Card; distance: number }[] = [];
  for (const [d, t, i] of best.slice(0, limit * 3)) {
    const [im, sid] = t.meta[i];
    const cs = await loadSet(sid).catch(() => setCards(sid));
    cs.filter((c) => c.img === im).forEach((card) => out.push({ card, distance: d }));
    if (out.length >= limit) break;
  }
  return out.slice(0, limit);
}

/* ---------- colours of each parallel (learned from price-guide photos, see core/colour.ts) ---------- */
let _colours: Record<string, Record<string, string>> | null = null;
export async function colourProfiles(): Promise<Record<string, Record<string, string>>> {
  if (_colours) return _colours;
  try {
    _colours = await cachedJson('colours.json.gz');
  } catch {
    return {}; // not published yet or offline without a saved copy: name colours still work
  }
  return _colours || {};
}

export const isLoaded = (setId: string) => !sets()[setId]?.remote || _loadedSets.has(setId);

/** Make sure a set's cards are in memory (downloads remote sets once per app session). */
export async function loadSet(setId: string): Promise<Card[]> {
  load();
  const s = _sets![setId];
  if (s?.remote && !_loadedSets.has(setId)) {
    const rows = await cachedJson(`sets/${setId.replace(/[^\w.-]/g, '_')}.json.gz`);
    addRows(rows);
    _loadedSets.add(setId);
  }
  return setCards(setId);
}

/** Loads the sets behind a list of card keys (e.g. everything in the vault). */
export async function loadKeys(keys: (string | null | undefined)[]) {
  const ids = new Set(keys.filter(Boolean).map((k) => String(k).split('|')[0]));
  await Promise.all([...ids].map((id) => loadSet(id).catch(() => [])));
}

/** Search the downloadable sets by card name: fetches the shards for the query's words. */
export async function searchRemote(query: string, limit = 60): Promise<Card[]> {
  const toks = (query.toLowerCase().match(/[a-z]+/g) || []).filter((t) => t.length >= 3);
  const keys = [...new Set(toks.map((t) => t.slice(0, 2)))].filter((k) => !_loadedShards.has(k)).slice(0, 3);
  await Promise.all(
    keys.map(async (k) => {
      try {
        addRows(await cachedJson(`names/${k}.json.gz`));
      } catch {
        /* no shard for these letters */
      }
      _loadedShards.add(k);
    }),
  );
  return search(query, limit);
}

function load() {
  if (_cards) return;
  const setsRaw: SetInfo[] = require('../../assets/catalog/sets.json');
  const cardsRaw: { fields: string[]; rows: any[][] } = require('../../assets/catalog/cards.json');
  _sets = Object.fromEntries(setsRaw.map((s) => [s.id, s]));
  _cards = cardsRaw.rows.map(toCard);
  _byKey = new Map(_cards.map((c) => [c.key, c]));
  _bySet = new Map();
  for (const c of _cards) {
    const a = _bySet.get(c.setId);
    if (a) a.push(c);
    else _bySet.set(c.setId, [c]);
  }
}

export function sets(): Record<string, SetInfo> {
  load();
  return _sets!;
}
export function cards(): Card[] {
  load();
  return _cards!;
}
export function getCard(key?: string | null): Card | null {
  load();
  return (key && _byKey!.get(key)) || null;
}
export function setCards(setId: string): Card[] {
  load();
  return _bySet!.get(setId) || [];
}
export function sales() {
  if (!_sales) {
    try {
      _sales = require('../../assets/catalog/sales.json');
    } catch {
      _sales = {};
    }
  }
  return _sales!;
}

const tokens = (s: string) => s.toLowerCase().match(/[a-z0-9]+/g) || [];

function index() {
  if (_index) return _index;
  load();
  _index = new Map();
  _cards!.forEach((c, i) => {
    const s = _sets![c.setId];
    const toks = new Set(tokens(`${c.name} ${c.variant} ${c.number} ${s?.name || ''} ${s?.brand || ''} ${s?.category || ''}`));
    toks.forEach((t) => {
      const a = _index!.get(t);
      if (a) a.push(i);
      else _index!.set(t, [i]);
    });
  });
  return _index;
}

export function search(query: string, limit = 60, setId = ''): Card[] {
  const toks = tokens(query);
  const all = cards();
  if (!toks.length) return (setId ? setCards(setId) : all).slice(0, limit);
  const idx = index();
  let hits: Set<number> = new Set();
  let first = true;
  for (const t of toks) {
    let ids = idx.get(t);
    let set: Set<number>;
    if (ids) set = new Set(ids);
    else {
      set = new Set();
      idx.forEach((v, k) => {
        if (k.startsWith(t)) v.forEach((i) => set.add(i));
      });
    }
    hits = first ? set : new Set([...hits].filter((i) => set.has(i)));
    first = false;
    if (!hits.size) return [];
  }
  let res = [...hits].map((i) => all[i]);
  if (setId) res = res.filter((c) => c.setId === setId);
  res.sort((a, b) => (b.raw || 0) - (a.raw || 0) || a.name.localeCompare(b.name));
  return res.slice(0, limit);
}

export function byCode(code: string): Card[] {
  const c = code.toUpperCase().trim().replace(/^#/, '');
  return cards().filter((x) => x.number.toUpperCase() === c);
}

const CODE_RE = /\b([A-Z]{2,5})-([A-Z]{1,5})-?(\d{1,3})\b/g;
const LONG_CODE_RE = /\b([A-Z]{2,6}\d{1,3}-[A-Z]{1,5}-\d{2,4}[A-Z0-9]{0,3}|[A-Z]{2,5}-[A-Z]{1,5}-\d{2,4}[A-Z][A-Z0-9]{0,2})\b/g;

/** Best matches for text read off a card. Card codes like CDT-BBG-199 pin the exact parallel. */
export function matchText(text: string, nameHint = '', numberHint = ''): { cards: Card[]; byCode: boolean } {
  const out: Card[] = [];
  const up = (text || '').toUpperCase();
  for (const m of up.matchAll(CODE_RE)) {
    out.push(...byCode(`${m[1]}-${m[2]}-${m[3]}`), ...byCode(`${m[1]}-${m[2]}-${m[3].padStart(2, '0')}`));
  }
  if (!out.length) {
    // codes with digits in the prefix or a suffix, read exactly as printed (Kayou 'NRSA01-SSR-020L3')
    for (const m of up.matchAll(LONG_CODE_RE)) out.push(...byCode(m[1]));
  }
  if (out.length) return { cards: dedupe(out), byCode: true };
  const q = [nameHint, numberHint ? numberHint.split('/')[0] : ''].filter(Boolean).join(' ');
  return { cards: q.trim() ? search(q, 20) : [], byCode: false };
}

function dedupe(cs: Card[]) {
  const seen = new Set<string>();
  return cs.filter((c) => (seen.has(c.key) ? false : (seen.add(c.key), true)));
}

/** Every parallel of the same card in the same set. */
export function siblings(card: Card): Card[] {
  const base = card.number ? card.number.replace(/^[A-Z]{2,5}-[A-Z]{1,5}-/, '') : '';
  return setCards(card.setId).filter((c) => c.name === card.name && (!base || c.number.endsWith(base)));
}

export function tier(card: Card): Tier | null {
  const s = sets()[card.setId];
  return s?.tiers.find((t) => t.name === (card.variant || 'Base')) || null;
}

export type PriceMode = 'raw' | 'psa9' | 'psa10';

/** Price label in the chosen view. Graded views fall back to the raw price (marked 'raw') when the card
 * has no graded sales; '~' = the parallel's typical raw price. */
export function priceIn(card: Card, mode: PriceMode = 'raw'): { v: number | null; text: string; graded: boolean } {
  if (mode === 'psa10' && card.psa10) return { v: card.psa10, text: `PSA 10 $${card.psa10.toFixed(2)}`, graded: true };
  if (mode === 'psa9' && card.psa9) return { v: card.psa9, text: `PSA 9 $${card.psa9.toFixed(2)}`, graded: true };
  const [v, est] = value(card);
  if (!v) return { v: null, text: '—', graded: false };
  return { v, text: `${est ? '~' : ''}$${v.toFixed(2)}${mode !== 'raw' ? ' raw' : ''}`, graded: false };
}

/** [price, isEstimate]: the card's own sold price, else the typical sold price of its parallel. */
export function value(card: Card): [number | null, boolean] {
  if (card.raw) return [card.raw, false];
  const t = tier(card);
  const v = t?.ebay_median || t?.median_raw;
  return v ? [v, true] : [null, false];
}

const photoFile = (id: string, size: number) => {
  const d = new Directory(cacheDir(), 'photos');
  if (!d.exists) d.create({ intermediates: true, idempotent: true });
  return new File(d, `${id}-${size}.jpg`);
};

/** A set's cover picture: its most valuable card's photo, else its sample photo. */
export function setCover(s: SetInfo | undefined, size = 240): string {
  if (!s) return '';
  if (s.cover) return imageUrl({ img: s.cover } as Card, size)[0];
  return s.image || '';
}

/** [url, isAnotherParallel]. Sizes: 60, 240, 1600. Uses the copy saved on the phone when there is one. */
export function imageUrl(card: Card | null | undefined, size = 240): [string, boolean] {
  if (!card?.img) return ['', false];
  if (card.img.startsWith('wc:')) return [`https://waifucards.app/img/cards/${card.img.slice(3)}.webp`, false]; // Naruto Kayou
  if (card.img.startsWith('ct:')) return [`https://ekptjfsrfdagbefgwvkx.supabase.co/storage/v1/object/public/${card.img.slice(3)}`, false]; // Naruto Kayou English (CardToad)
  if (card.img.startsWith('nc:')) return [`https://cdn.narutocards.ca/${card.img.slice(3)}`, false]; // Naruto (narutocards.ca)
  const id = card.img.replace(/^~/, '');
  try {
    const f = photoFile(id, size);
    if (f.exists) return [f.uri, card.img.startsWith('~')];
  } catch {
    /* no file system (web): use the online photo */
  }
  return [`https://storage.googleapis.com/images.pricecharting.com/${id}/${size}.jpg`, card.img.startsWith('~')];
}

/** Save these cards' photos on the phone (your collection) so they show offline. */
export async function savePhotos(cs: (Card | null | undefined)[], size = 240) {
  // only price-guide photos are saved (Naruto pictures from wc: / nc: sites stay online)
  const ids = [...new Set(cs.filter((c): c is Card => !!c?.img && !/^(wc|nc|ct):/.test(c.img)).map((c) => c.img.replace(/^~/, '')))];
  const q = ids.filter((id) => !photoFile(id, size).exists);
  await Promise.all(
    [0, 1, 2].map(async () => {
      while (q.length) {
        const id = q.shift()!;
        try {
          await File.downloadFileAsync(`https://storage.googleapis.com/images.pricecharting.com/${id}/${size}.jpg`, photoFile(id, size), { idempotent: true });
        } catch {
          /* offline: try again next time */
        }
      }
    }),
  );
}

export function priceUrl(card: Card): string {
  const s = sets()[card.setId];
  if (!s) return '';
  return card.path && s.base_url ? `${s.base_url}/game/${card.path}` : s.source_url;
}

export function relatedSales(card: Card, limit = 8): SoldListing[] {
  const name = card.name.toLowerCase().split(' / ')[0];
  const first = name.split(/\s+/)[0] || '';
  const variant = (card.variant || '').toLowerCase().split(/\s+/)[0] || '';
  const out: SoldListing[] = [];
  Object.values(sales()).forEach((v) =>
    (v.sales || []).forEach((s) => {
      const t = s.t.toLowerCase();
      if (first && t.includes(first) && (!variant || t.includes(variant))) out.push(s);
    }),
  );
  return out.sort((a, b) => Date.parse(b.d) - Date.parse(a.d)).slice(0, limit);
}

export function oddsText(t: Tier | null, s?: SetInfo): string {
  if (!t?.odds) return '';
  const m = t.odds.match(/1 in ([\d,]+) packs/);
  const box = s?.box?.packs_per_box;
  if (m && box) {
    const boxes = parseInt(m[1].replace(/,/g, ''), 10) / box;
    return `${t.odds} (about 1 per ${Math.round(boxes).toLocaleString()} box${boxes >= 1.5 ? 'es' : ''})`;
  }
  return t.odds;
}

export const printRunLabel = (n?: number | null) => (!n ? '' : n === 1 ? '1 of 1' : `/${n}`);

/* ---------- closest match for text read off a photo (misread letters, missing words) ---------- */
function editDistance(a: string, b: string): number {
  const m = a.length, n = b.length;
  if (!m || !n) return m + n;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    for (let j = 1; j <= n; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur;
  }
  return prev[n];
}
const similar = (a: string, b: string) => 1 - editDistance(a, b) / Math.max(a.length, b.length, 1);
const OCR_FIX: Record<string, string> = { '0': 'o', '1': 'l', '5': 's', '8': 'b', '7': 't', '4': 'a' };

/** Closest catalog cards to text read off a card, tolerating misread letters ('Charizrd', 'Tr0ut'): each word is
 * matched to the nearest known word, then cards are ranked by how alike their name is to the text, plus the
 * card number when it was read. Loads the name lists it needs (downloaded or cached). */
export async function closestRemote(text: string, nameHint = '', numberHint = '', limit = 20): Promise<Card[]> {
  const lines = [nameHint, ...(text || '').split('\n')].map((l) => l.trim()).filter(Boolean).slice(0, 8);
  const fix = (w: string) => (/[a-z]/.test(w) && /\d/.test(w) ? w.replace(/[015874]/g, (d) => OCR_FIX[d]) : w);
  const words = [...new Set(lines.flatMap((l) => (l.toLowerCase().match(/[a-z0-9]+/g) || []).map(fix)).filter((w) => w.length >= 4 && /^[a-z]+$/.test(w)))];
  if (!words.length) return [];
  await searchRemote(words.join(' '), 1).catch(() => []); // loads the name lists for these words
  const idx = index();
  const vocab = new Map<string, string[]>();
  idx.forEach((_, k) => {
    if (k.length >= 4 && /^[a-z]+$/.test(k)) {
      const a = vocab.get(k[0]);
      if (a) a.push(k);
      else vocab.set(k[0], [k]);
    }
  });
  const fixed: string[] = [];
  for (const w of words) {
    if (idx.has(w)) { fixed.push(w); continue; }
    let best = '', bs = 0.75;
    for (const k of vocab.get(w[0]) || []) {
      if (Math.abs(k.length - w.length) > 2) continue;
      const s = similar(w, k);
      if (s > bs) { bs = s; best = k; }
    }
    if (best) fixed.push(best);
  }
  const pool = new Map<number, number>();
  for (const w of fixed) for (const i of (idx.get(w) || []).slice(0, 4000)) pool.set(i, (pool.get(i) || 0) + 1);
  const all = cards();
  const num = (numberHint || '').split('/')[0].replace(/^#/, '').replace(/^0+/, '').toLowerCase();
  const target = fix((nameHint || lines[0] || '').toLowerCase());
  return [...pool.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3000)
    .map(([i, n]) => {
      const c = all[i];
      const bonus = num && c.number.toLowerCase().replace(/^0+/, '').endsWith(num) ? 0.35 : 0;
      return { c, s: similar(c.name.toLowerCase(), target) + 0.1 * n + bonus };
    })
    .sort((a, b) => b.s - a.s)
    .filter((x) => x.s >= 0.55)
    .slice(0, limit)
    .map((x) => x.c);
}
