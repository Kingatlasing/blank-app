/** Binders: named groups of collection cards, kept on this phone only (AsyncStorage). */
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface Binder {
  id: string;
  name: string;
  /** cover colour, '#RRGGBB' */
  color: string;
  private: boolean;
  /** vault record ids */
  cardIds: string[];
  created_at?: string;
}

const KEY = 'slabscout.binders.v1';
const uid = () => `b${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;

export async function loadBinders(): Promise<Binder[]> {
  try {
    const l = JSON.parse((await AsyncStorage.getItem(KEY)) || '[]');
    return Array.isArray(l) ? l : [];
  } catch {
    return [];
  }
}

export async function saveBinders(list: Binder[]) {
  await AsyncStorage.setItem(KEY, JSON.stringify(list));
}

export async function createBinder(b: Omit<Binder, 'id' | 'cardIds'> & { cardIds?: string[] }): Promise<Binder[]> {
  const list = await loadBinders();
  const nb: Binder = { id: uid(), cardIds: [], created_at: new Date().toISOString(), ...b };
  const out = [nb, ...list];
  await saveBinders(out);
  return out;
}

export async function updateBinder(id: string, patch: Partial<Binder>): Promise<Binder[]> {
  const out = (await loadBinders()).map((b) => (b.id === id ? { ...b, ...patch, id } : b));
  await saveBinders(out);
  return out;
}

export async function deleteBinder(id: string): Promise<Binder[]> {
  const out = (await loadBinders()).filter((b) => b.id !== id);
  await saveBinders(out);
  return out;
}

export async function addToBinder(id: string, cardIds: string[]): Promise<Binder[]> {
  const list = await loadBinders();
  const out = list.map((b) => (b.id === id ? { ...b, cardIds: [...new Set([...b.cardIds, ...cardIds])] } : b));
  await saveBinders(out);
  return out;
}

/** '#abc' / 'abc' / '#aabbcc' -> '#AABBCC', or '' when not a colour. */
export function normalizeHex(v: string): string {
  const h = v.trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(h)) return `#${h.split('').map((x) => x + x).join('').toUpperCase()}`;
  if (/^[0-9a-f]{6}$/i.test(h)) return `#${h.toUpperCase()}`;
  return '';
}
