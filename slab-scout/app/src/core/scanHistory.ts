/** Scan history: every card the live scanner identified, newest first, kept on the phone.
 * Cards can be added to the collection from here later (the + button), so nothing scanned is lost. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Candidate } from './databases';

const KEY = 'slabscout.scanHistory.v1';
const MAX = 200;

export interface ScanItem {
  id: string;
  at: string;
  uri: string; // the cropped photo (cache file: may be cleared by the phone later)
  thumb: string; // small base64 jpeg, always kept
  phash: string;
  game: string;
  name: string;
  set: string;
  number: string;
  rarity: string;
  price: number | null;
  currency: string;
  source: string; // 'card database' | a free database name | 'text' | ''
  catalog_key?: string;
  cand?: Candidate;
  note?: string; // e.g. "back of a Pokémon card"
  added?: boolean;
  wish?: boolean;
  /** the front alone wasn't enough: why the back is needed (shown with a "Scan the back" button) */
  needBack?: string;
  /** identified from front + back */
  withBack?: boolean;
  /** every line of text read on the card (front / back), kept with the scan */
  text?: string[];
  backText?: string[];
}

let cache: ScanItem[] | null = null;
const listeners = new Set<(l: ScanItem[]) => void>();

export async function loadHistory(): Promise<ScanItem[]> {
  if (cache) return cache;
  try {
    cache = JSON.parse((await AsyncStorage.getItem(KEY)) || '[]');
  } catch {
    cache = [];
  }
  return cache!;
}

async function save(list: ScanItem[]) {
  cache = list.slice(0, MAX);
  listeners.forEach((f) => f(cache!));
  await AsyncStorage.setItem(KEY, JSON.stringify(cache));
}

export async function addHistory(item: ScanItem) {
  await save([item, ...(await loadHistory()).filter((x) => x.id !== item.id)]);
}

export async function updateHistory(id: string, patch: Partial<ScanItem>) {
  await save((await loadHistory()).map((x) => (x.id === id ? { ...x, ...patch } : x)));
}

export async function removeHistory(id: string) {
  await save((await loadHistory()).filter((x) => x.id !== id));
}

export async function clearHistory(keepAdded = false) {
  await save(keepAdded ? (await loadHistory()).filter((x) => x.added) : []);
}

export function onHistory(f: (l: ScanItem[]) => void) {
  listeners.add(f);
  return () => listeners.delete(f);
}
