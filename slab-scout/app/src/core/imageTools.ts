/**
 * Image helpers that run on the phone with no network or AI:
 * crop the card from the photo, fingerprint it (same pHash as the Streamlit
 * app, so both share one community catalog), measure centering, make thumbnails.
 */
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { File, Paths } from 'expo-file-system';
import * as jpeg from 'jpeg-js';
import { findCardQuad, Quad, quadTilt, snapQuad, warpQuad } from './straighten';

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
export type CardStyle = 'standard' | 'full_art' | 'die_cut' | 'vintage';
/** Expected inner-border widths as a share of card width (l, r) / height (t, b). */
export type BorderExpect = { l: number; r: number; t: number; b: number };
/** Thin frame around full-art / illustration rares (same values as the web app). */
export const FULL_ART_BORDER: BorderExpect = { l: 0.035, r: 0.035, t: 0.028, b: 0.028 };

export async function findLines(
  cardUri: string,
  tight = true,
  style: CardStyle = 'standard',
  expect?: BorderExpect | null,
): Promise<{ lines: Lines; found: Record<'left' | 'right' | 'top' | 'bottom', boolean>; looksFullArt: boolean }> {
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
  const limX = Math.round(W * 0.2), limY = Math.round(H * 0.2);
  const nearX = Math.max(3, Math.round(W * 0.025)), nearY = Math.max(3, Math.round(H * 0.025));
  /** Inner edge of the border: where the colour stops matching the border colour just inside the card edge. */
  const byColour = (line: number[][], start: number, limit: number): number | null => {
    const seg = line.slice(start, start + limit);
    if (seg.length < 8) return null;
    const ref = [0, 1, 2].map((c) => [...seg.slice(1, 5).map((p) => p[c])].sort((a, b) => a - b)[2]);
    const d = seg.map((p) => Math.abs(p[0] - ref[0]) + Math.abs(p[1] - ref[1]) + Math.abs(p[2] - ref[2]));
    const sm = d.map((_, i) => ((d[i - 1] ?? d[i]) + d[i] + (d[i + 1] ?? d[i])) / 3);
    const noise = [...sm.slice(1, 5)].sort((a, b) => a - b)[2] + 1;
    const thr = Math.max(40, noise * 4);
    let run = 0;
    for (let i = 5; i < sm.length; i++) {
      run = sm[i] > thr ? run + 1 : 0;
      if (run >= 2) return start + i - 1;
    }
    return null;
  };
  /** Per scan line: table -> thin bands at the edge (slab rim, background) -> card edge -> border edge.
   * `exp` = where this card's frame should be (px from the card edge) for a known layout, e.g. full art. */
  const side = (lines: number[][][], limO: number, limI: number, near: number, exp: number | null = null): [number, number | null] => {
    const outs: number[] = [], ins: (number | null)[] = [];
    const skip = Math.max(3, Math.round(lines[0].length * 0.012));
    for (const l of lines) {
      const o = outer(l, limO);
      let start = o, out = o, inner: number | null = null;
      for (let k = 0; k < 4; k++) {
        const d = depth(l, start, limI);
        if (d == null) break;
        if (d - start <= near && d <= l.length * 0.035) { // background bands only right at the photo edge
          out = d;
          start = d + skip;
          continue;
        }
        inner = d;
        break;
      }
      const cb = byColour(l, out + 1, limI);
      if (cb != null && (inner == null || cb < inner)) inner = cb;
      if (exp != null) {
        // known layout: take the colour step closest to where its frame should be
        const seg = l.slice(out, out + Math.round(exp * 2.2) + 6);
        if (seg.length > 6) {
          const g: number[] = [];
          for (let i = 1; i < seg.length; i++) g.push(Math.abs(seg[i][0] - seg[i - 1][0]) + Math.abs(seg[i][1] - seg[i - 1][1]) + Math.abs(seg[i][2] - seg[i - 1][2]));
          const k3 = g.map((_, i) => ((g[i - 1] ?? g[i]) + g[i] + (g[i + 1] ?? g[i])) / 3);
          const lo = Math.max(2, Math.floor(exp * 0.45)), hi = Math.min(k3.length - 1, Math.floor(exp * 1.8) + 3);
          if (hi > lo) {
            let k = lo;
            for (let i = lo; i < hi; i++) if (k3[i] - 0.6 * Math.abs(i - exp) > k3[k] - 0.6 * Math.abs(k - exp)) k = i;
            inner = k3[k] >= 18 ? out + k + 1 : null;
          }
        }
      }
      outs.push(out);
      ins.push(inner);
    }
    return [med(outs) ?? 0, med(ins)];
  };
  // full art: look for the thin frame where it's printed. Die-cut and vintage cards use the normal search
  // (die-cut centering is judged on the printed design; vintage only changes the corner check).
  const ex = expect || (style === 'full_art' ? FULL_ART_BORDER : null);
  const [ol, il] = side(R, limOX, limX, nearX, ex ? ex.l * W : null);
  const [or, ir] = side(Rr, limOX, limX, nearX, ex ? ex.r * W : null);
  const [ot, it] = side(Cc, limOY, limY, nearY, ex ? ex.t * H : null);
  const [ob, ib] = side(Cr, limOY, limY, nearY, ex ? ex.b * H : null);
  const found = { left: il != null, right: ir != null, top: it != null, bottom: ib != null };
  // no border line found: the border of a perfectly centred card of this layout
  const L = (il ?? ol + W * (ex?.l ?? 0.055)) * sx, Rt = (ir ?? or + W * (ex?.r ?? 0.055)) * sx;
  const T = (it ?? ot + H * (ex?.t ?? 0.045)) * sy, B = (ib ?? ob + H * (ex?.b ?? 0.045)) * sy;
  const lines = { ol: ol * sx, ot: ot * sy, or: CARD_W - or * sx, ob: CARD_H - ob * sy, il: L, it: T, ir: CARD_W - Rt, ib: CARD_H - B };
  return { lines, found, looksFullArt: fullArtLook(data, W, H, lines) };
}

/**
 * A thin, colourless (silver / grey / foil) frame with the artwork running to it: full art, illustration
 * rares, SAR / SIR. Standard cards have a wider, coloured border (yellow Pokémon, black Magic, white sports).
 * Port of the web app's vision.looks_full_art; `lines` in 630x880 units, `data` a W x H RGB copy of the card.
 */
function fullArtLook(data: Uint8Array, W: number, H: number, l: Lines) {
  const bx = ((l.il - l.ol) + (l.or - l.ir)) / 2 / CARD_W;
  const by = ((l.it - l.ot) + (l.ob - l.ib)) / 2 / CARD_H;
  const kx = W / CARD_W;
  const sats: number[] = [], vals: number[] = [];
  const take = (x0: number, x1: number) => {
    for (let y = Math.floor(H * 0.3); y < Math.floor(H * 0.7); y += 2)
      for (let x = Math.max(0, Math.floor(x0)); x < Math.min(W, Math.floor(x1)); x++) {
        const i = (y * W + x) * 3;
        const mx = Math.max(data[i], data[i + 1], data[i + 2]), mn = Math.min(data[i], data[i + 1], data[i + 2]);
        vals.push(mx);
        sats.push(mx ? ((mx - mn) * 255) / mx : 0);
      }
  };
  take((l.ol + 3) * kx, (l.il - 2) * kx);
  take((l.ir + 2) * kx, (l.or - 3) * kx);
  if (!vals.length) return false;
  const med = (v: number[]) => [...v].sort((a, b) => a - b)[v.length >> 1];
  const v = med(vals);
  return bx < 0.042 && by < 0.036 && med(sats) < 55 && v > 70 && v < 235;
}

export async function measureCentering(cardUri: string): Promise<Centering | null> {
  const e = await firstEdges(cardUri, 0.2);
  if (e.left == null || e.right == null || e.top == null || e.bottom == null) return null;
  return { left: e.left, right: e.right, top: e.top, bottom: e.bottom };
}

/**
 * Photo -> straight card image. A card held or photographed at an angle is flattened first
 * (straightenPhoto). Otherwise: crops the camera frame with a small margin, then trims
 * to the card's outer edge (first strong change from the background). If an edge
 * can't be found, that side keeps the frame position.
 */
const B64C = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
export function bytesToB64(b: Uint8Array) {
  const out: string[] = [];
  for (let i = 0; i < b.length; i += 3) {
    const n = (b[i] << 16) | ((b[i + 1] ?? 0) << 8) | (b[i + 2] ?? 0);
    out.push(B64C[(n >> 18) & 63] + B64C[(n >> 12) & 63] + (i + 1 < b.length ? B64C[(n >> 6) & 63] : '=') + (i + 2 < b.length ? B64C[n & 63] : '='));
  }
  return out.join('');
}

/** RGB pixels -> JPEG bytes with jpeg-js. Its encoder hands the bytes to Node's Buffer, which React Native
 * doesn't have, so a tiny stand-in is lent for the call. */
export function encodeJpeg(rgb: Uint8Array, w: number, h: number, quality = 92): Uint8Array {
  const g = globalThis as any;
  const lend = typeof g.Buffer === 'undefined';
  if (lend) g.Buffer = { from: (a: ArrayLike<number>) => Uint8Array.from(a) };
  try {
    const rgba = new Uint8Array(w * h * 4);
    for (let i = 0, j = 0; i < w * h; i++, j += 3) {
      rgba[i * 4] = rgb[j];
      rgba[i * 4 + 1] = rgb[j + 1];
      rgba[i * 4 + 2] = rgb[j + 2];
      rgba[i * 4 + 3] = 255;
    }
    return new Uint8Array(jpeg.encode({ data: rgba, width: w, height: h }, quality).data as unknown as ArrayLike<number>);
  } finally {
    if (lend) delete g.Buffer;
  }
}

/** Part of a photo (photo pixels) as w x h RGB pixels. */
async function regionPixels(uri: string, r: Rect, w: number, h: number) {
  const ref = await ImageManipulator.manipulate(uri)
    .crop({ originX: Math.round(r.x), originY: Math.round(r.y), width: Math.round(r.w), height: Math.round(r.h) })
    .resize({ width: w, height: h })
    .renderAsync();
  const out = await ref.saveAsync({ base64: true, compress: 1, format: SaveFormat.JPEG });
  const img = jpeg.decode(b64ToBytes(out.base64 || ''), { useTArray: true, formatAsRGBA: false });
  return { w: img.width, h: img.height, rgb: img.data as Uint8Array };
}

function clampRect(r: Rect, W: number, H: number): Rect {
  const x = Math.max(0, Math.floor(r.x)), y = Math.max(0, Math.floor(r.y));
  return { x, y, w: Math.max(1, Math.min(W, Math.ceil(r.x + r.w)) - x), h: Math.max(1, Math.min(H, Math.ceil(r.y + r.h)) - y) };
}

/**
 * A card photographed at an angle or held in a hand, flattened to a straight 630x880 card (see
 * straighten.ts). Looks in the camera frame (plus room for a tilted card) or the whole photo, finds the
 * card's four sides in a ~400 px copy, snaps them to the exact edges in a sharper copy and warps.
 * Returns null when no clear card outline is found or the card is already square to the camera
 * (under 1 degree): the normal crop is used then.
 */
export async function straightenPhoto(uri: string, photoW: number, photoH: number, guide?: Rect): Promise<{ uri: string; base64: string; tilt: number } | null> {
  try {
    const area = guide
      ? clampRect({ x: guide.x - guide.w * 0.18, y: guide.y - guide.h * 0.12, w: guide.w * 1.36, h: guide.h * 1.24 }, photoW, photoH)
      : { x: 0, y: 0, w: photoW, h: photoH };
    const k = 400 / Math.max(area.w, area.h);
    const small = await regionPixels(uri, area, Math.max(16, Math.round(area.w * k)), Math.max(16, Math.round(area.h * k)));
    const hit = findCardQuad(small);
    if (!hit || hit.tilt < 0.5) return null;
    const q = hit.quad.map(([x, y]) => [area.x + (x * area.w) / small.w, area.y + (y * area.h) / small.h]) as Quad;
    const tall = (Math.hypot(q[3][0] - q[0][0], q[3][1] - q[0][1]) + Math.hypot(q[2][0] - q[1][0], q[2][1] - q[1][1])) / 2;
    if (guide) {
      // the card should be the thing in the camera frame, not something next to it
      const cx = (q[0][0] + q[1][0] + q[2][0] + q[3][0]) / 4, cy = (q[0][1] + q[1][1] + q[2][1] + q[3][1]) / 4;
      if (cx < guide.x || cx > guide.x + guide.w || cy < guide.y || cy > guide.y + guide.h || tall < guide.h * 0.6) return null;
    }
    // sharper copy around the card (about card size), with room for the edge snap to look outside
    const xs = q.map((p) => p[0]), ys = q.map((p) => p[1]);
    const pad = tall * 0.08;
    const box = clampRect({ x: Math.min(...xs) - pad, y: Math.min(...ys) - pad, w: Math.max(...xs) - Math.min(...xs) + 2 * pad, h: Math.max(...ys) - Math.min(...ys) + 2 * pad }, photoW, photoH);
    const s2 = Math.min(1, 1000 / tall);
    const big = await regionPixels(uri, box, Math.max(16, Math.round(box.w * s2)), Math.max(16, Math.round(box.h * s2)));
    const bq = q.map(([x, y]) => [((x - box.x) * big.w) / box.w, ((y - box.y) * big.h) / box.h]) as Quad;
    const { quad: sq, snapped } = snapQuad(big, bq);
    // a real card edge is found again on at least three sides (one may be under a finger)
    if (snapped < 3) return null;
    const tilt = quadTilt(sq);
    if (tilt < 1) return null; // square to the camera: the normal crop is as good
    const bytes = encodeJpeg(warpQuad(big, sq, CARD_W, CARD_H), CARD_W, CARD_H, 92);
    const f = new File(Paths.cache, `straight-${Date.now()}-${Math.round(Math.random() * 1e6)}.jpg`);
    if (!f.exists) f.create();
    f.write(bytes);
    return { uri: f.uri, base64: bytesToB64(bytes), tilt };
  } catch {
    return null;
  }
}

export async function cropAndTrim(uri: string, photoW: number, photoH: number, guide?: Rect, straighten = true) {
  if (straighten) {
    // held or tilted card: flatten it first (falls back to the plain crop below)
    const s = await straightenPhoto(uri, photoW, photoH, guide);
    if (s) return { uri: s.uri, base64: s.base64 };
  }
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
