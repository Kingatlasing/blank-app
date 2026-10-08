/**
 * Slab Scout scan service (the web app's full engine, hosted free on Streamlit Community Cloud): text reading in English,
 * Japanese and Korean, fingerprint, colours, serial / back checks, slab labels and the grade estimate.
 * The phone uses it whenever a server address is set in Settings and there's signal; otherwise everything
 * runs on the phone as before. Code: streamlit/api_app.py (Streamlit) and
 * streamlit/service.py (Docker hosts), set-up steps: scan-service/README.md.
 */
import { Platform } from 'react-native';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';

export interface ServerMatch {
  kind: 'catalog' | 'tcgdb' | 'community' | 'ai';
  score: number;
  why: string[];
  key?: string;
  set_id?: string;
  name: string;
  number: string;
  variant?: string;
  rarity?: string;
  print_run?: number | null;
  set: string;
  year: string;
  game: string;
  price: number | null;
  psa9?: number | null;
  psa10?: number | null;
  image_url?: string;
  ref_id?: string;
  url?: string;
  official_distance?: number | null;
  label?: string;
}

export interface ServerSide {
  subgrades: { corners: number; edges: number; surface: number };
  findings: { area: string; where: string; what: string; severity: number; sure: string }[];
  photo_ok: boolean;
  photo_notes: string[];
}

export interface ServerCentering {
  left: number;
  right: number;
  top: number;
  bottom: number;
  text: string;
  worst: number;
}

export interface ServerGrade {
  error?: string;
  method: string;
  sub: { centering: number; corners: number; edges: number; surface: number };
  psa: number;
  psa_label: string;
  psa_range: string;
  tag_score: number;
  tag_grade: string;
  tag_label: string;
  style: string;
  centering: { front: ServerCentering | null; back: ServerCentering | null };
  caps: Record<string, string>;
  front: ServerSide | null;
  back: ServerSide | null;
  straightened: boolean;
  tips: string[];
  confidence: 'high' | 'medium' | 'low';
}

export interface ServerScan {
  is_back: string;
  game: string;
  parsed: { name?: string; number?: string; raw_text?: string; game?: string; set_code?: string; year?: string };
  lines: string[];
  back_lines: string[];
  phash: string;
  found: boolean;
  matches: ServerMatch[];
  fakes: { name: string; reasons: string; distance: number }[];
  colours: string;
  card_jpeg: string;
  slab?: { company: string; grade: number | string; label: string; cert: string; grade_text: string; price_at_grade?: number | null; lookup?: string };
  grade?: ServerGrade;
  autograph?: { found: boolean; kind: string; certified: boolean; auto_grade: string; notes: string[]; verify: string };
  authenticity?: { verdict: string; reasons: string[] };
  seconds: number;
}

let base = '';
/** Called when settings load or change. Accepts 'my-app.streamlit.app' or a full https:// address. */
export function setScanServer(url: string | undefined) {
  let u = (url || '').trim().replace(/\/+$/, '');
  if (u && !/^https?:\/\//i.test(u)) u = `https://${u}`;
  // the browser build served by the scan app itself (/web/index.html): use that same address, since a
  // browser won't let a page call another site's API
  if (Platform.OS === 'web' && typeof location !== 'undefined') {
    const i = location.pathname.indexOf('/web/');
    if (i >= 0) u = location.origin + location.pathname.slice(0, i);
  }
  if (u !== base) api = null;
  base = u;
}
// Where the API sits under that address: '/api' on a Streamlit app (Streamlit Cloud may add '/~/+'),
// nothing on a Docker host. Found once by asking each for /health.
let api: string | null = null;
let probing: Promise<string | null> | null = null;
async function apiRoot(timeoutMs = 90000): Promise<string | null> {
  if (!base) return null;
  if (api !== null) return api;
  if (!probing) {
    probing = (async () => {
      const deadline = Date.now() + timeoutMs;
      while (Date.now() < deadline) {
        for (const pre of ['/api', '/~/+/api', '']) {
          const ac = new AbortController();
          const t = setTimeout(() => ac.abort(), 20000);
          try {
            const r = await fetch(`${base}${pre}/health`, { signal: ac.signal });
            const j = r.ok ? await r.json().catch(() => null) : null;
            if (j?.ok) return (api = pre);
          } catch {
            /* try the next one */
          } finally {
            clearTimeout(t);
          }
        }
        await new Promise((r) => setTimeout(r, 5000)); // waking up
      }
      return null;
    })().finally(() => {
      probing = null;
    });
  }
  return probing;
}
export const scanServer = () => base;
/** The API path prefix on the scan server ('/api', '/~/+/api' or ''), or null when it can't be reached. */
export const serverApi = (timeoutMs = 30000) => apiRoot(timeoutMs);
export const serverOn = () => !!base;

/** A photo as an upload: big camera shots shrunk to 2000 px on the long side (plenty for grading, quick to send). */
async function upload(uri: string, field: string, form: FormData) {
  let u = uri;
  try {
    const ref = await ImageManipulator.manipulate(uri).renderAsync();
    const long = Math.max(ref.width, ref.height);
    const out = long > 2000 ? await ImageManipulator.manipulate(uri).resize(ref.width >= ref.height ? { width: 2000 } : { height: 2000 }).renderAsync() : ref;
    u = (await out.saveAsync({ compress: 0.9, format: SaveFormat.JPEG })).uri;
  } catch {
    /* send as is */
  }
  if (Platform.OS === 'web') {
    const blob = await (await fetch(u)).blob();
    form.append(field, blob, `${field}.jpg`);
  } else {
    form.append(field, { uri: u, name: `${field}.jpg`, type: 'image/jpeg' } as any);
  }
}

async function post<T>(path: string, form: FormData, timeoutMs: number): Promise<T> {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const pre = await apiRoot();
    if (pre === null) throw new Error('scan server unreachable');
    const r = await fetch(`${base}${pre}${path}`, { method: 'POST', body: form, signal: ac.signal });
    if (!r.ok) throw new Error(`scan server ${r.status}`);
    return (await r.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

/** Is the server awake? A free Space sleeps when unused and takes up to a minute or two to wake. */
export async function wakeServer(timeoutMs = 90000): Promise<boolean> {
  if (!base) return false;
  api = null;
  return (await apiRoot(timeoutMs)) !== null;
}

// One request per photo: the text reader (readText) and the scan screen share the same answer.
const cache = new Map<string, Promise<ServerScan | null>>();

/** Full scan on the server. `photo` is the best photo of the front (the original camera shot when there is one);
 * `key` is the card crop's address, so readText(crop) reuses this answer instead of sending the photo again. */
export function serverScan(photo: string, opts: { back?: string | null; game?: string; grade?: boolean; key?: string; timeoutMs?: number } = {}): Promise<ServerScan | null> {
  if (!base) return Promise.resolve(null);
  const k = `${opts.key || photo}|${opts.back || ''}|${opts.grade !== false}`;
  const hit = cache.get(k);
  if (hit) return hit;
  const p = (async () => {
    const form = new FormData();
    await upload(photo, 'front', form);
    if (opts.back) await upload(opts.back, 'back', form);
    form.append('game', opts.game || 'Auto');
    form.append('grade', opts.grade === false ? 'false' : 'true');
    return post<ServerScan>('/scan', form, opts.timeoutMs ?? 120000);
  })().catch(() => null);
  cache.set(k, p);
  if (cache.size > 12) cache.delete(cache.keys().next().value as string);
  return p;
}

/** Text lines on a card (English, plus Japanese / Korean when it sees them), from a scan already sent or a new request. */
export async function serverText(uri: string): Promise<string[] | null> {
  if (!base) return null;
  for (const [k, p] of cache) {
    if (k.startsWith(`${uri}|`)) {
      const r = await p;
      if (r) return r.lines;
    }
  }
  try {
    const form = new FormData();
    await upload(uri, 'photo', form);
    const r = await post<{ lines: string[] }>('/ocr', form, 90000);
    return r.lines;
  } catch {
    return null;
  }
}
