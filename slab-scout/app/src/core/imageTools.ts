/**
 * Image helpers that run on the phone with no network or AI:
 * crop the card from the photo, fingerprint it (same pHash as the Streamlit
 * app, so both share one community catalog), measure centering, make thumbnails.
 */
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { File, Paths } from 'expo-file-system';
import * as jpeg from 'jpeg-js';

export const CARD_W = 630;
export const CARD_H = 880;

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
export function b64ToBytes(b64: string): Uint8Array {
  const clean = b64.replace(/[^A-Za-z0-9+/]/g, '');
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let o = 0;
  for (let i = 0; i < clean.length; i += 4) {
    const a = B64.indexOf(clean[i]);
    const b = B64.indexOf(clean[i + 1]);
    const c = B64.indexOf(clean[i + 2]);
    const d = B64.indexOf(clean[i + 3]);
    out[o++] = (a << 2) | (b >> 4);
    if (c >= 0 && i + 2 < clean.length) out[o++] = ((b & 15) << 4) | (c >> 2);
    if (d >= 0 && i + 3 < clean.length) out[o++] = ((c & 3) << 6) | d;
  }
  return out.subarray(0, o);
}

export async function pixels(uri: string, w: number, h: number): Promise<{ data: Uint8Array; width: number; height: number }> {
  const ctx = ImageManipulator.manipulate(uri).resize({ width: w, height: h });
  const ref = await ctx.renderAsync();
  const out = await ref.saveAsync({ base64: true, compress: 1, format: SaveFormat.JPEG });
  const img = jpeg.decode(b64ToBytes(out.base64 || ''), { useTArray: true, formatAsRGBA: false });
  return { data: img.data as Uint8Array, width: img.width, height: img.height };
}

/** Crop a photo to the card. `guide` is the card frame in photo pixels (from the camera overlay); otherwise center-crop. */
export async function cropCard(uri: string, photoW: number, photoH: number, guide?: Rect): Promise<{ uri: string; base64: string }> {
  let r: Rect;
  if (guide) {
    r = guide;
  } else {
    const target = CARD_W / CARD_H;
    if (photoW / photoH > target) {
      const w = photoH * target;
      r = { x: (photoW - w) / 2, y: 0, w, h: photoH };
    } else {
      const h = photoW / target;
      r = { x: 0, y: (photoH - h) / 2, w: photoW, h };
    }
  }
  const x = Math.max(0, Math.round(r.x));
  const y = Math.max(0, Math.round(r.y));
  const w = Math.min(photoW - x, Math.round(r.w));
  const h = Math.min(photoH - y, Math.round(r.h));
  const ctx = ImageManipulator.manipulate(uri).crop({ originX: x, originY: y, width: w, height: h }).resize({ width: CARD_W, height: CARD_H });
  const ref = await ctx.renderAsync();
  const out = await ref.saveAsync({ base64: true, compress: 0.9, format: SaveFormat.JPEG });
  return { uri: out.uri, base64: out.base64 || '' };
}

export async function thumbnail(uri: string, width = 180): Promise<string> {
  const ref = await ImageManipulator.manipulate(uri).resize({ width }).renderAsync();
  const out = await ref.saveAsync({ base64: true, compress: 0.7, format: SaveFormat.JPEG });
  return out.base64 || '';
}

/* ---------- perceptual hash (matches Python imagehash.phash, hash_size=8) ---------- */
function dct1d(v: number[]): number[] {
  const N = v.length;
  const out = new Array(N).fill(0);
  for (let k = 0; k < N; k++) {
    let s = 0;
    for (let n = 0; n < N; n++) s += v[n] * Math.cos((Math.PI * k * (2 * n + 1)) / (2 * N));
    out[k] = 2 * s;
  }
  return out;
}

export async function fingerprintCard(cardUri: string): Promise<string> {
  // Same inner crop as the Streamlit app: 8% sides, 6% top/bottom of a 630x880 card.
  const ix = Math.round(CARD_W * 0.08);
  const iy = Math.round(CARD_H * 0.06);
  const ref = await ImageManipulator.manipulate(cardUri)
    .crop({ originX: ix, originY: iy, width: CARD_W - 2 * ix, height: CARD_H - 2 * iy })
    .renderAsync();
  const inner = await ref.saveAsync({ compress: 1, format: SaveFormat.JPEG });
  return phashOf(inner.uri);
}

export async function phashOf(uri: string): Promise<string> {
  const { data } = await pixels(uri, 32, 32);
  const gray: number[][] = [];
  for (let y = 0; y < 32; y++) {
    const row: number[] = [];
    for (let x = 0; x < 32; x++) {
      const i = (y * 32 + x) * 3;
      row.push((data[i] * 19595 + data[i + 1] * 38470 + data[i + 2] * 7471 + 0x8000) >> 16); // PIL "L"
    }
    gray.push(row);
  }
  // scipy dct(dct(pixels, axis=0), axis=1)
  const cols: number[][] = Array.from({ length: 32 }, (_, x) => dct1d(gray.map((r) => r[x])));
  const d0 = Array.from({ length: 32 }, (_, y) => cols.map((c) => c[y]));
  const d = d0.map((r) => dct1d(r));
  const low: number[] = [];
  for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) low.push(d[y][x]);
  const sorted = [...low].sort((a, b) => a - b);
  const med = (sorted[31] + sorted[32]) / 2;
  let hex = '';
  for (let i = 0; i < 64; i += 4) {
    let nib = 0;
    for (let j = 0; j < 4; j++) nib = (nib << 1) | (low[i + j] > med ? 1 : 0);
    hex += nib.toString(16);
  }
  return hex;
}

export function hashDistance(a: string, b: string): number {
  if (!a || !b || a.length !== b.length) return 64;
  let d = 0;
  for (let i = 0; i < a.length; i++) {
    let x = parseInt(a[i], 16) ^ parseInt(b[i], 16);
    while (x) {
      d += x & 1;
      x >>= 1;
    }
  }
  return d;
}

/** Download an image (e.g. the official card picture) and fingerprint it the same way. */
export async function fingerprintRemote(url: string): Promise<string | null> {
  try {
    const dest = new File(Paths.cache, `ref-${Math.abs(hashString(url))}.img`);
    if (!dest.exists) await File.downloadFileAsync(url, dest, { idempotent: true });
    const ref = await ImageManipulator.manipulate(dest.uri).resize({ width: CARD_W, height: CARD_H }).renderAsync();
    const out = await ref.saveAsync({ compress: 1, format: SaveFormat.JPEG });
    return fingerprintCard(out.uri);
  } catch {
    return null;
  }
}

function hashString(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

/* ---------- centering ---------- */
export interface Centering {
  left: number;
  right: number;
  top: number;
  bottom: number;
}
export const ratio = (a: number, b: number): [number, number] => {
  const t = Math.max(a + b, 1);
  const big = Math.round((Math.max(a, b) * 100) / t);
  return [big, 100 - big];
};
export const centeringText = (c: Centering) => {
  const [a, b] = ratio(c.left, c.right);
  const [x, y] = ratio(c.top, c.bottom);
  return `${a}/${b} L/R, ${x}/${y} T/B`;
};
export const centeringWorst = (c: Centering) => Math.max(ratio(c.left, c.right)[0], ratio(c.top, c.bottom)[0]);

type Edges = { left: number | null; right: number | null; top: number | null; bottom: number | null };

/** First strong colour change in from each edge (values in 630x880 units). Port of the Streamlit border finder. */
async function firstEdges(cardUri: string, frac: number): Promise<Edges> {
  const W = 315;
  const H = 440;
  const { data } = await pixels(cardUri, W, H);
  const px = (x: number, y: number) => {
    const i = (y * W + x) * 3;
    return [data[i], data[i + 1], data[i + 2]];
  };
  const depth = (line: number[][], limit: number): number | null => {
    const seg = line.slice(2, limit);
    if (seg.length < 5) return null;
    const grad: number[] = [];
    for (let i = 1; i < seg.length; i++) grad.push(Math.abs(seg[i][0] - seg[i - 1][0]) + Math.abs(seg[i][1] - seg[i - 1][1]) + Math.abs(seg[i][2] - seg[i - 1][2]));
    const k = grad.map((_, i) => ((grad[i - 1] ?? grad[i]) + grad[i] + (grad[i + 1] ?? grad[i])) / 3);
    const peak = Math.max(...k);
    if (peak < 18) return null;
    const thresh = Math.max(18, Math.min(0.4 * peak, 60)); // capped: strong text/art edges further in can't hide the border
    let idx = k.findIndex((v) => v >= thresh);
    while (idx + 1 < k.length && k[idx + 1] >= k[idx]) idx++;
    return (idx + 3) * 2;
  };
  const med = (vals: (number | null)[]) => {
    const v = vals.filter((x): x is number => x != null).sort((a, b) => a - b);
    return v.length >= 5 ? v[Math.floor(v.length / 2)] : null;
  };
  const rows = Array.from({ length: 15 }, (_, i) => Math.round(H * 0.25 + (i * H * 0.5) / 14));
  const cols = Array.from({ length: 15 }, (_, i) => Math.round(W * 0.25 + (i * W * 0.5) / 14));
  const limX = Math.round(W * frac);
  const limY = Math.round(H * frac);
  const rowLine = (y: number) => Array.from({ length: W }, (_, x) => px(x, y));
  const colLine = (x: number) => Array.from({ length: H }, (_, y) => px(x, y));
  return {
    left: med(rows.map((y) => depth(rowLine(y), limX))),
    right: med(rows.map((y) => depth(rowLine(y).reverse(), limX))),
    top: med(cols.map((x) => depth(colLine(x), limY))),
    bottom: med(cols.map((x) => depth(colLine(x).reverse(), limY))),
  };
}

export type Lines = { ol: number; ot: number; or: number; ob: number; il: number; it: number; ir: number; ib: number };

/**
 * All eight centering lines in 630x880 card units: outer card edge (ol/ot/or/ob, where the dark table
 * stops) and inner border (il/it/ir/ib). Same rules as the web app's vision.find_lines.
 * `tight` = the photo was trimmed to the card (camera guide), so only a thin sliver of table can show.
 */
export async function findLines(cardUri: string, tight = true): Promise<{ lines: Lines; found: Record<'left' | 'right' | 'top' | 'bottom', boolean> }> {
  const img = await pixels(cardUri, 315, 440);
  const { data } = img;
  const W = img.width, H = img.height, sx = CARD_W / W, sy = CARD_H / H;
  const px = (x: number, y: number) => {
    const i = (y * W + x) * 3;
    return [data[i], data[i + 1], data[i + 2]];
  };
  const frac = tight ? 0.02 : 0.1;
  const outer = (line: number[][], limit: number) => {
    let run = 0;
    for (let i = 0; i < limit && i < line.length; i++) {
      if (Math.max(...line[i]) >= 60) break;
      run++;
    }
    return run < limit ? run : 0; // endless dark = a dark-bordered card, not table
  };
  const depth = (line: number[][], start: number, limit: number): number | null => {
    const seg = line.slice(start + 2, start + limit);
    if (seg.length < 5) return null;
    const grad: number[] = [];
    for (let i = 1; i < seg.length; i++) grad.push(Math.abs(seg[i][0] - seg[i - 1][0]) + Math.abs(seg[i][1] - seg[i - 1][1]) + Math.abs(seg[i][2] - seg[i - 1][2]));
    const k = grad.map((_, i) => ((grad[i - 1] ?? grad[i]) + grad[i] + (grad[i + 1] ?? grad[i])) / 3);
    const peak = Math.max(...k);
    if (peak < 18) return null;
    const thresh = Math.max(18, Math.min(0.4 * peak, 60)); // capped: strong text/art edges further in can't hide the border
    let idx = k.findIndex((v) => v >= thresh);
    while (idx + 1 < k.length && k[idx + 1] >= k[idx]) idx++;
    return start + idx + 3;
  };
  const med = (vals: (number | null)[], need = 5) => {
    const v = vals.filter((x): x is number => x != null).sort((a, b) => a - b);
    return v.length >= need ? v[Math.floor(v.length / 2)] : null;
  };
  const rows = Array.from({ length: 21 }, (_, i) => Math.round(H * 0.25 + (i * H * 0.5) / 20));
  const cols = Array.from({ length: 21 }, (_, i) => Math.round(W * 0.25 + (i * W * 0.5) / 20));
  const rowLine = (y: number) => Array.from({ length: W }, (_, x) => px(x, y));
  const colLine = (x: number) => Array.from({ length: H }, (_, y) => px(x, y));
  const R = rows.map(rowLine), Rr = R.map((l) => [...l].reverse()), Cc = cols.map(colLine), Cr = Cc.map((l) => [...l].reverse());
  const limOX = Math.max(2, Math.round(W * frac)), limOY = Math.max(2, Math.round(H * frac));
  const ol = med(R.map((l) => outer(l, limOX))) ?? 0, or = med(Rr.map((l) => outer(l, limOX))) ?? 0;
  const ot = med(Cc.map((l) => outer(l, limOY))) ?? 0, ob = med(Cr.map((l) => outer(l, limOY))) ?? 0;
  const limX = Math.round(W * 0.2), limY = Math.round(H * 0.2);
  const il = med(R.map((l) => depth(l, ol, limX))), ir = med(Rr.map((l) => depth(l, or, limX)));
  const it = med(Cc.map((l) => depth(l, ot, limY))), ib = med(Cr.map((l) => depth(l, ob, limY)));
  const found = { left: il != null, right: ir != null, top: it != null, bottom: ib != null };
  const L = (il ?? ol + W * 0.055) * sx, Rt = (ir ?? or + W * 0.055) * sx, T = (it ?? ot + H * 0.045) * sy, B = (ib ?? ob + H * 0.045) * sy;
  return {
    lines: { ol: ol * sx, ot: ot * sy, or: CARD_W - or * sx, ob: CARD_H - ob * sy, il: L, it: T, ir: CARD_W - Rt, ib: CARD_H - B },
    found,
  };
}

export async function measureCentering(cardUri: string): Promise<Centering | null> {
  const e = await firstEdges(cardUri, 0.2);
  if (e.left == null || e.right == null || e.top == null || e.bottom == null) return null;
  return { left: e.left, right: e.right, top: e.top, bottom: e.bottom };
}

/**
 * Photo -> straight card image. Crops the camera frame with a small margin, then trims
 * to the card's outer edge (first strong change from the background). If an edge
 * can't be found, that side keeps the frame position.
 */
export async function cropAndTrim(uri: string, photoW: number, photoH: number, guide?: Rect) {
  let r = guide;
  if (r) {
    const mx = r.w * 0.06;
    const my = r.h * 0.06;
    r = { x: r.x - mx, y: r.y - my, w: r.w + 2 * mx, h: r.h + 2 * my };
  }
  const first = await cropCard(uri, photoW, photoH, r);
  if (!guide) return first;
  const e = await firstEdges(first.uri, 0.14);
  const sx = CARD_W / 630;
  const cut = (v: number | null, fallback: number) => (v != null ? v : fallback);
  const l = cut(e.left, 630 * 0.053) * sx;
  const rr = cut(e.right, 630 * 0.053) * sx;
  const t = cut(e.top, 880 * 0.053);
  const b = cut(e.bottom, 880 * 0.053);
  const ref = await ImageManipulator.manipulate(first.uri)
    .crop({ originX: Math.round(l), originY: Math.round(t), width: Math.round(CARD_W - l - rr), height: Math.round(CARD_H - t - b) })
    .resize({ width: CARD_W, height: CARD_H })
    .renderAsync();
  const out = await ref.saveAsync({ base64: true, compress: 0.9, format: SaveFormat.JPEG });
  return { uri: out.uri, base64: out.base64 || '' };
}
