/**
 * Built-in card database (same files as the Streamlit app: data/catalog → assets/catalog).
 * Every card we collected with its parallel, print run, sold prices and pull odds.
 * Loaded lazily on first use so the app opens fast.
 */

import { useEffect, useState } from 'react';

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
export const REMOTE = 'https://raw.githubusercontent.com/Kingatlasing/blank-app/slab-scout/slab-scout/data/catalog/remote';
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

export const isLoaded = (setId: string) => !sets()[setId]?.remote || _loadedSets.has(setId);

/** Make sure a set's cards are in memory (downloads remote sets once per app session). */
export async function loadSet(setId: string): Promise<Card[]> {
  load();
  const s = _sets![setId];
  if (s?.remote && !_loadedSets.has(setId)) {
    const rows = await fetchJson(`${REMOTE}/sets/${encodeURIComponent(setId.replace(/[^\w.-]/g, '_'))}.json`);
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
  const toks = tokens(query).filter((t) => t.length >= 2 && !/^\d+$/.test(t));
  const keys = [...new Set(toks.map((t) => t.slice(0, 2)))].filter((k) => !_loadedShards.has(k)).slice(0, 3);
  await Promise.all(
    keys.map(async (k) => {
      try {
        addRows(await fetchJson(`${REMOTE}/names/${k}.json`));
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

/** Best matches for text read off a card. Card codes like CDT-BBG-199 pin the exact parallel. */
export function matchText(text: string, nameHint = '', numberHint = ''): { cards: Card[]; byCode: boolean } {
  const out: Card[] = [];
  const up = (text || '').toUpperCase();
  for (const m of up.matchAll(CODE_RE)) {
    out.push(...byCode(`${m[1]}-${m[2]}-${m[3]}`), ...byCode(`${m[1]}-${m[2]}-${m[3].padStart(2, '0')}`));
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

/** [price, isEstimate]: the card's own sold price, else the typical sold price of its parallel. */
export function value(card: Card): [number | null, boolean] {
  if (card.raw) return [card.raw, false];
  const t = tier(card);
  const v = t?.ebay_median || t?.median_raw;
  return v ? [v, true] : [null, false];
}

/** [url, isAnotherParallel]. Sizes: 60, 240, 1600. */
export function imageUrl(card: Card | null | undefined, size = 240): [string, boolean] {
  if (!card?.img) return ['', false];
  return [`https://storage.googleapis.com/images.pricecharting.com/${card.img.replace(/^~/, '')}/${size}.jpg`, card.img.startsWith('~')];
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
