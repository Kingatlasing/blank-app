/**
 * Shared community catalog + vault (same Supabase tables as the Streamlit app).
 * Without Supabase settings, everything is kept on this phone only.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface CardFields {
  game: string;
  name: string;
  set: string;
  number: string;
  year: string;
  brand: string;
  rarity: string;
  variant: string;
  card_type: string;
}

export interface CatalogRow {
  id: string;
  card_key: string;
  game: string;
  name: string;
  set_name: string;
  number: string;
  year: string;
  brand: string;
  rarity: string;
  variant: string;
  card_type: string;
  phash: string;
  thumb?: string;
  confirmations: number;
  is_fake: boolean;
  fake_reasons?: string;
  distance?: number;
}

export interface Sale {
  grade: string;
  price: number;
  sold_on?: string;
  url?: string;
}

/** A vault record. Same JSON shape the Streamlit app saves, so one vault code works in both. */
export interface VaultRecord {
  id: string;
  v: 1;
  added_at: string;
  card: CardFields;
  grade: any;
  authenticity: { verdict: string; reasons: string[] };
  pricing: { raw: { low?: number; mid?: number; high?: number }; currency: string; note: string; graded_label: string; graded_mid?: number | null; priced_at: string };
  match: { source: string; ref_id?: string; image_url: string; url: string; catalog_key?: string };
  thumb: string;
  phash: string;
  /** 'collection' (default) or 'wishlist'. */
  list?: 'collection' | 'wishlist';
  print_run?: number | null;
  odds?: string;
}

export const cardKey = (c: Partial<CardFields>) =>
  [c.game, c.name, c.set, c.number, c.variant].map((p) => String(p || '').toLowerCase().split(/\s+/).filter(Boolean).join(' ')).join('|');

const L_CATALOG = 'slabscout.local.catalog';
const L_SALES = 'slabscout.local.sales';
const L_VAULT = 'slabscout.local.vault';
const L_HISTORY = 'slabscout.local.history';
const L_CORR = 'slabscout.local.corrections';
const uid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
const loadL = async <T,>(k: string): Promise<T[]> => {
  try {
    return JSON.parse((await AsyncStorage.getItem(k)) || '[]');
  } catch {
    return [];
  }
};
const saveL = (k: string, v: unknown) => AsyncStorage.setItem(k, JSON.stringify(v));

export class Store {
  shared: boolean;
  private fpCache: { at: number; rows: CatalogRow[] } | null = null;

  constructor(private url = '', private key = '') {
    this.url = url.replace(/\/+$/, '');
    this.shared = !!(this.url && this.key);
  }

  private async rest(method: string, path: string, body?: unknown, extra: Record<string, string> = {}) {
    const r = await fetch(`${this.url}/rest/v1/${path}`, {
      method,
      headers: { apikey: this.key, Authorization: `Bearer ${this.key}`, 'Content-Type': 'application/json', ...extra },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await r.text();
    if (!r.ok) throw new Error(`Community database error ${r.status}: ${text.slice(0, 160)}`);
    return text ? JSON.parse(text) : null;
  }
  private rpc = (fn: string, args: unknown) => this.rest('POST', `rpc/${fn}`, args);

  /* ---------- catalog ---------- */
  async fingerprints(): Promise<CatalogRow[]> {
    if (this.fpCache && Date.now() - this.fpCache.at < 5 * 60_000) return this.fpCache.rows;
    const rows: CatalogRow[] = this.shared
      ? (await this.rest('GET', 'catalog_cards?select=id,card_key,game,name,set_name,number,year,brand,rarity,variant,card_type,phash,thumb,confirmations,is_fake,fake_reasons&phash=not.is.null&limit=5000')) || []
      : await loadL<CatalogRow>(L_CATALOG);
    this.fpCache = { at: Date.now(), rows };
    return rows;
  }

  async addCard(card: CardFields, phash: string, thumb: string, source: string, isFake = false, fakeReasons = '') {
    this.fpCache = null;
    const row = {
      card_key: cardKey(card) + (isFake ? '|fake' : ''), game: card.game, name: card.name, set_name: card.set, number: card.number,
      year: card.year, brand: card.brand, rarity: card.rarity, variant: card.variant, card_type: card.card_type, phash, thumb, source,
      is_fake: isFake, fake_reasons: fakeReasons,
    };
    if (this.shared) return this.rpc('add_catalog_card', { p: row });
    const all = await loadL<CatalogRow>(L_CATALOG);
    const hit = all.find((r) => r.card_key === row.card_key);
    if (hit) hit.confirmations += 1;
    else all.push({ ...row, id: uid(), confirmations: 1 } as CatalogRow);
    await saveL(L_CATALOG, all);
  }

  async search(text: string): Promise<CatalogRow[]> {
    const t = text.trim();
    if (this.shared) {
      let q = 'catalog_cards?select=id,game,name,set_name,number,rarity,variant,brand,card_type,thumb,confirmations,is_fake,fake_reasons&order=confirmations.desc&limit=30';
      if (t) q += `&or=(name.ilike.*${encodeURIComponent(t)}*,set_name.ilike.*${encodeURIComponent(t)}*)`;
      return (await this.rest('GET', q)) || [];
    }
    const all = await loadL<CatalogRow>(L_CATALOG);
    return all.filter((r) => !t || `${r.name} ${r.set_name}`.toLowerCase().includes(t.toLowerCase())).slice(0, 30);
  }

  async stats() {
    if (this.shared) {
      const count = async (q: string) => {
        const r = await fetch(`${this.url}/rest/v1/${q}`, { headers: { apikey: this.key, Authorization: `Bearer ${this.key}`, Prefer: 'count=exact', Range: '0-0' } });
        return parseInt((r.headers.get('content-range') || '*/0').split('/').pop() || '0', 10) || 0;
      };
      return { cards: await count('catalog_cards?select=id&is_fake=eq.false'), fakes: await count('catalog_cards?select=id&is_fake=eq.true'), sales: await count('catalog_sales?select=id') };
    }
    const cat = await loadL<CatalogRow>(L_CATALOG);
    return { cards: cat.filter((c) => !c.is_fake).length, fakes: cat.filter((c) => c.is_fake).length, sales: (await loadL(L_SALES)).length };
  }

  /* ---------- corrections: the card a person settled on for a scan (fingerprint -> catalog card) ---------- */
  private corrCache: { at: number; rows: { phash: string; catalog_key: string }[] } | null = null;
  async addCorrection(phash: string, catalogKey: string) {
    if (!phash || !catalogKey) return;
    const row = { phash: phash.slice(0, 64), catalog_key: catalogKey.slice(0, 500) };
    // always kept on the phone too, so it works offline and with an older shared database
    const all = await loadL<typeof row>(L_CORR);
    if (!all.some((r) => r.phash === row.phash && r.catalog_key === row.catalog_key)) {
      all.unshift(row);
      await saveL(L_CORR, all.slice(0, 5000));
    }
    if (this.shared) await this.rest('POST', 'scan_corrections', row, { Prefer: 'return=minimal' }).catch(() => null);
    this.corrCache = null;
  }
  async corrections(): Promise<{ phash: string; catalog_key: string }[]> {
    if (this.corrCache && Date.now() - this.corrCache.at < 5 * 60e3) return this.corrCache.rows;
    let rows = await loadL<{ phash: string; catalog_key: string }>(L_CORR);
    if (this.shared) {
      try {
        rows = rows.concat((await this.rest('GET', 'scan_corrections?select=phash,catalog_key&order=created_at.desc&limit=20000')) || []);
      } catch {
        /* table not set up: phone-only corrections */
      }
    }
    this.corrCache = { at: Date.now(), rows };
    return rows;
  }

  /* ---------- sales ---------- */
  async addSale(card: CardFields, grade: string, price: number, soldOn: string, url: string) {
    const row = { card_key: cardKey(card), grade, price, sold_on: soldOn || null, url };
    if (this.shared) return this.rest('POST', 'catalog_sales', row);
    const all = await loadL<any>(L_SALES);
    all.push(row);
    await saveL(L_SALES, all);
  }

  async salesFor(card: CardFields): Promise<Sale[]> {
    const k = cardKey(card);
    if (this.shared) return (await this.rest('GET', `catalog_sales?select=grade,price,sold_on,url&card_key=eq.${encodeURIComponent(k)}&order=sold_on.desc.nullslast&limit=30`)) || [];
    return (await loadL<any>(L_SALES)).filter((s) => s.card_key === k);
  }

  /* ---------- vault ---------- */
  async vaultList(code: string): Promise<VaultRecord[]> {
    if (this.shared) {
      if (code.length < 6) return [];
      const rows = (await this.rpc('vault_list', { p_code: code })) || [];
      return rows.map((r: any) => ({ ...r.data, id: r.id }));
    }
    return loadL<VaultRecord>(L_VAULT);
  }
  async vaultAdd(code: string, rec: Omit<VaultRecord, 'id'>) {
    if (this.shared) return this.rpc('vault_add', { p_code: code, p_data: rec });
    const all = await loadL<VaultRecord>(L_VAULT);
    all.unshift({ ...rec, id: uid() } as VaultRecord);
    await saveL(L_VAULT, all);
  }
  async vaultUpdate(code: string, rec: VaultRecord) {
    const { id, ...data } = rec;
    if (this.shared) return this.rpc('vault_update', { p_code: code, p_id: id, p_data: data });
    const all = await loadL<VaultRecord>(L_VAULT);
    await saveL(L_VAULT, all.map((r) => (r.id === id ? rec : r)));
  }
  /* ---------- portfolio value history (one point per day) ---------- */
  async historyList(code: string): Promise<{ day: string; value: number }[]> {
    if (this.shared) return ((await this.rpc('vault_history_list', { p_code: code })) || []).map((r: any) => ({ day: String(r.day), value: Number(r.value) }));
    return (await loadL<{ day: string; value: number }>(L_HISTORY)).sort((a, b) => a.day.localeCompare(b.day));
  }
  async historyAdd(code: string, day: string, value: number) {
    if (this.shared) return this.rpc('vault_history_add', { p_code: code, p_day: day, p_value: value });
    const all = (await loadL<{ day: string; value: number }>(L_HISTORY)).filter((r) => r.day !== day);
    all.push({ day, value });
    await saveL(L_HISTORY, all);
  }

  async vaultDelete(code: string, id: string) {
    if (this.shared) return this.rpc('vault_delete', { p_code: code, p_id: id });
    await saveL(L_VAULT, (await loadL<VaultRecord>(L_VAULT)).filter((r) => r.id !== id));
  }
}
