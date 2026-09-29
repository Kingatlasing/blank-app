/**
 * Automatic condition inspection on the phone (port of the web app's core/condition.py, no OpenCV).
 *
 * Checks the straightened 630x880 card photo the way graders do:
 *  - corners: zoomed crops + whitening / fraying and missing material (table showing through)
 *  - edges:   whitening and chips along all four edges
 *  - surface: scratches (thin bright lines, top-hat filter), specks / dents (small dark spots in flat
 *             areas), stains (patches off the border colour, surrounded by clean border)
 *  - fading + error / misprint check against the official image when there is one
 *  - photo quality (blur, glare)
 * and builds the inspection views: zoomed corners and edges, inverted colours, black & white scan,
 * contrast-boosted surface view and a defect map.
 * Crease detection (long straight lines) is only in the web app for now.
 */
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { File, Paths } from 'expo-file-system';
import { CARD_H, CARD_W, pixels } from './imageTools';

const CORNER = 70;
const EDGE = 14;
const MARGIN = 5;

export interface Finding {
  area: 'corners' | 'edges' | 'surface' | 'error';
  where: string;
  what: string;
  severity: number;
  sure: 'likely' | 'possible';
}

export interface Inspection {
  subgrades: { corners: number; edges: number; surface: number };
  findings: Finding[];
  photoNotes: string[];
  metrics: Record<string, number>;
  views: { name: string; uris: string[] }[];
}

export const LEGEND = 'Magenta = whitening / chipping · Yellow = scratches · Cyan = specks / dents · Green = stains · Orange box = differs from the official card';

const sevToGrade = (s: number) => {
  const t: [number, number][] = [[0.03, 10], [0.1, 9], [0.25, 8], [0.45, 7], [0.6, 6], [0.75, 5], [0.9, 4]];
  for (const [lim, g] of t) if (s <= lim) return g;
  return 3;
};

/* ---------- small image-processing helpers ---------- */
type Img = { w: number; h: number; rgb: Uint8Array };

function toGray(im: Img) {
  const g = new Uint8Array(im.w * im.h);
  for (let i = 0, j = 0; i < g.length; i++, j += 3) g[i] = (im.rgb[j] * 299 + im.rgb[j + 1] * 587 + im.rgb[j + 2] * 114) / 1000;
  return g;
}
function satVal(im: Img) {
  const s = new Uint8Array(im.w * im.h);
  const v = new Uint8Array(im.w * im.h);
  for (let i = 0, j = 0; i < s.length; i++, j += 3) {
    const r = im.rgb[j], g = im.rgb[j + 1], b = im.rgb[j + 2];
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
    v[i] = mx;
    s[i] = mx ? Math.round(((mx - mn) * 255) / mx) : 0;
  }
  return { s, v };
}
/** 1-D running min/max along rows then columns (square window k). */
function morph(src: Uint8Array, w: number, h: number, k: number, max: boolean) {
  const r = Math.floor(k / 2);
  const tmp = new Uint8Array(src.length);
  const out = new Uint8Array(src.length);
  const pick = max ? Math.max : Math.min;
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      let m = src[y * w + x];
      for (let d = -r; d <= r; d++) {
        const xx = x + d;
        if (xx >= 0 && xx < w) m = pick(m, src[y * w + xx]);
      }
      tmp[y * w + x] = m;
    }
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      let m = tmp[y * w + x];
      for (let d = -r; d <= r; d++) {
        const yy = y + d;
        if (yy >= 0 && yy < h) m = pick(m, tmp[yy * w + x]);
      }
      out[y * w + x] = m;
    }
  return out;
}
/** Box mean with an integral image. */
function boxMean(src: ArrayLike<number>, w: number, h: number, r: number) {
  const I = new Float64Array((w + 1) * (h + 1));
  for (let y = 0; y < h; y++) {
    let row = 0;
    for (let x = 0; x < w; x++) {
      row += src[y * w + x];
      I[(y + 1) * (w + 1) + x + 1] = I[y * (w + 1) + x + 1] + row;
    }
  }
  const out = new Float32Array(w * h);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const x0 = Math.max(0, x - r), x1 = Math.min(w, x + r + 1), y0 = Math.max(0, y - r), y1 = Math.min(h, y + r + 1);
      const sum = I[y1 * (w + 1) + x1] - I[y0 * (w + 1) + x1] - I[y1 * (w + 1) + x0] + I[y0 * (w + 1) + x0];
      out[y * w + x] = sum / ((x1 - x0) * (y1 - y0));
    }
  return out;
}
/** Connected components of a 0/1 mask (8-neighbour). Returns boxes + areas. */
function components(mask: Uint8Array, w: number, h: number, x0 = 0, y0 = 0, x1 = w, y1 = h) {
  const seen = new Uint8Array(w * h);
  const out: { x: number; y: number; bw: number; bh: number; area: number; px: number[] }[] = [];
  const stack: number[] = [];
  for (let y = y0; y < y1; y++)
    for (let x = x0; x < x1; x++) {
      const i = y * w + x;
      if (!mask[i] || seen[i]) continue;
      let minx = x, maxx = x, miny = y, maxy = y;
      const px: number[] = [];
      stack.push(i);
      seen[i] = 1;
      while (stack.length) {
        const p = stack.pop()!;
        px.push(p);
        const py = (p / w) | 0, pxx = p % w;
        if (pxx < minx) minx = pxx;
        if (pxx > maxx) maxx = pxx;
        if (py < miny) miny = py;
        if (py > maxy) maxy = py;
        for (let dy = -1; dy <= 1; dy++)
          for (let dx = -1; dx <= 1; dx++) {
            const nx = pxx + dx, ny = py + dy;
            if (nx < x0 || ny < y0 || nx >= x1 || ny >= y1) continue;
            const q = ny * w + nx;
            if (mask[q] && !seen[q]) {
              seen[q] = 1;
              stack.push(q);
            }
          }
      }
      out.push({ x: minx, y: miny, bw: maxx - minx + 1, bh: maxy - miny + 1, area: px.length, px });
    }
  return out;
}
function median(vals: number[]) {
  const v = [...vals].sort((a, b) => a - b);
  return v.length ? v[v.length >> 1] : 0;
}

/* ---------- JPEG out (for the inspection views) ---------- */
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
function bytesToB64(b: Uint8Array) {
  let s = '';
  for (let i = 0; i < b.length; i += 3) {
    const n = (b[i] << 16) | ((b[i + 1] ?? 0) << 8) | (b[i + 2] ?? 0);
    s += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + (i + 1 < b.length ? B64[(n >> 6) & 63] : '=') + (i + 2 < b.length ? B64[n & 63] : '=');
  }
  return s;
}
/** Uncompressed 24-bit BMP as a data URI (works on iOS, Android and web; jpeg-js's encoder needs Node's Buffer). */
function encode(rgb: Uint8Array, w: number, h: number) {
  const rowSize = Math.ceil((w * 3) / 4) * 4;
  const size = 54 + rowSize * h;
  const b = new Uint8Array(size);
  const dv = new DataView(b.buffer);
  b[0] = 0x42;
  b[1] = 0x4d;
  dv.setUint32(2, size, true);
  dv.setUint32(10, 54, true);
  dv.setUint32(14, 40, true);
  dv.setInt32(18, w, true);
  dv.setInt32(22, -h, true); // top-down rows
  dv.setUint16(26, 1, true);
  dv.setUint16(28, 24, true);
  dv.setUint32(34, rowSize * h, true);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 3;
      const o = 54 + y * rowSize + x * 3;
      b[o] = rgb[i + 2];
      b[o + 1] = rgb[i + 1];
      b[o + 2] = rgb[i];
    }
  return `data:image/bmp;base64,${bytesToB64(b)}`;
}
const grayToRgb = (g: ArrayLike<number>) => {
  const o = new Uint8Array(g.length * 3);
  for (let i = 0; i < g.length; i++) o[i * 3] = o[i * 3 + 1] = o[i * 3 + 2] = g[i];
  return o;
};

async function crop(uri: string, x: number, y: number, w: number, h: number, scale: number) {
  const ref = await ImageManipulator.manipulate(uri).crop({ originX: x, originY: y, width: w, height: h }).resize({ width: Math.round(w * scale) }).renderAsync();
  const out = await ref.saveAsync({ compress: 0.9, format: SaveFormat.JPEG });
  return out.uri;
}

async function officialPixels(url: string, w: number, h: number): Promise<Img | null> {
  try {
    let hsh = 0;
    for (let i = 0; i < url.length; i++) hsh = (hsh * 31 + url.charCodeAt(i)) | 0;
    const dest = new File(Paths.cache, `ref-${Math.abs(hsh)}.img`);
    if (!dest.exists) await File.downloadFileAsync(url, dest, { idempotent: true });
    const p = await pixels(dest.uri, w, h);
    return { w: p.width, h: p.height, rgb: p.data };
  } catch {
    return null;
  }
}

/* ---------- the inspection ---------- */
export async function inspectCard(uri: string, officialUrl?: string | null, isBack = false): Promise<Inspection> {
  const side = isBack ? 'back' : 'front';
  const full = await pixels(uri, CARD_W, CARD_H);
  const im: Img = { w: full.width, h: full.height, rgb: full.data };
  const { w, h } = im;
  const gray = toGray(im);
  const { s: sat, v: val } = satVal(im);
  const findings: Finding[] = [];
  const photoNotes: string[] = [];
  const metrics: Record<string, number> = {};

  // photo quality: Laplacian variance (sharpness) and glare
  let lapSum = 0, lapSq = 0, n = 0, glare = 0;
  for (let y = 1; y < h - 1; y += 2)
    for (let x = 1; x < w - 1; x += 2) {
      const i = y * w + x;
      const l = gray[i - 1] + gray[i + 1] + gray[i - w] + gray[i + w] - 4 * gray[i];
      lapSum += l;
      lapSq += l * l;
      n++;
      if (gray[i] > 250) glare++;
    }
  const sharp = lapSq / n - (lapSum / n) ** 2;
  metrics.sharpness = Math.round(sharp);
  if (sharp < 60) photoNotes.push('Photo looks soft or blurry, so small scratches and whitening may be missed. Hold steady, add light, no zoom.');
  if (glare / n > 0.03) photoNotes.push("Glare on the card. Tilt it slightly away from the light so reflections don't hide the surface.");

  // border colour
  const bandIdx: number[] = [];
  for (let x = CORNER; x < w - CORNER; x += 3)
    for (let y = MARGIN + 4; y < MARGIN + 14; y += 3) bandIdx.push(y * w + x, (h - 1 - y) * w + x);
  for (let y = CORNER; y < h - CORNER; y += 3)
    for (let x = MARGIN + 4; x < MARGIN + 14; x += 3) bandIdx.push(y * w + x, y * w + (w - 1 - x));
  const br = median(bandIdx.map((i) => im.rgb[i * 3])), bg = median(bandIdx.map((i) => im.rgb[i * 3 + 1])), bb = median(bandIdx.map((i) => im.rgb[i * 3 + 2]));
  const bLum = (br * 299 + bg * 587 + bb * 114) / 1000;
  const bMax = Math.max(br, bg, bb), bSat = bMax ? ((bMax - Math.min(br, bg, bb)) * 255) / bMax : 0;
  const whiteBorder = bSat < 50 && bMax > 190;

  const white = new Uint8Array(w * h);
  const dark = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) {
    if (!whiteBorder && gray[i] - bLum > 22 && sat[i] < Math.max(55, bSat - 70) && val[i] > 185) white[i] = 1;
    if (val[i] < 45) dark[i] = 1;
  }

  // ----- corners -----
  const R = 32;
  const cornerSev: Record<string, number> = {};
  const corners: [string, number, number, boolean, boolean][] = [
    ['top-left', 0, 0, false, false], ['top-right', w - CORNER, 0, true, false], ['bottom-left', 0, h - CORNER, false, true], ['bottom-right', w - CORNER, h - CORNER, true, true],
  ];
  for (const [name, ox, oy, fx, fy] of corners) {
    let band = 0, wh = 0, miss = 0;
    for (let yy = 0; yy < CORNER; yy++)
      for (let xx = 0; xx < CORNER; xx++) {
        const lx = fx ? CORNER - 1 - xx : xx, ly = fy ? CORNER - 1 - yy : yy; // local coords as if top-left
        const inBand = (ly >= MARGIN && ly < MARGIN + 14 && lx >= MARGIN) || (lx >= MARGIN && lx < MARGIN + 14 && ly >= MARGIN);
        const outsideRound = lx < R && ly < R && (lx - R) ** 2 + (ly - R) ** 2 > R * R;
        if (!inBand || outsideRound) continue;
        band++;
        const i = (oy + yy) * w + ox + xx;
        if (white[i]) wh++;
        if (dark[i]) miss++;
      }
    const wf = wh / Math.max(1, band), mf = miss / Math.max(1, band);
    cornerSev[name] = Math.min(1, wf * 6 + mf * 4);
    if (wf > 0.01) findings.push({ area: 'corners', where: `${name} corner (${side})`, what: `Whitening / fraying (${(wf * 100).toFixed(1)}% of the corner edge)`, severity: Math.min(1, wf * 6), sure: 'likely' });
    if (mf > 0.04) findings.push({ area: 'corners', where: `${name} corner (${side})`, what: 'Corner looks rounded, bent or dinged (background showing)', severity: Math.min(1, mf * 4), sure: 'possible' });
  }
  const cs = Object.values(cornerSev).sort((a, b) => b - a);
  const cornersG = sevToGrade(cs[0] * 0.75 + cs[1] * 0.25);

  // ----- edges -----
  const edgeBoxes: [string, number, number, number, number][] = [
    ['top', CORNER, MARGIN, w - CORNER, MARGIN + EDGE], ['bottom', CORNER, h - MARGIN - EDGE, w - CORNER, h - MARGIN],
    ['left', MARGIN, CORNER, MARGIN + EDGE, h - CORNER], ['right', w - MARGIN - EDGE, CORNER, w - MARGIN, h - CORNER],
  ];
  const edgeMask = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) edgeMask[i] = white[i] | dark[i];
  const edgeSev: number[] = [];
  let chipsTotal = 0;
  for (const [name, x0, y0, x1, y1] of edgeBoxes) {
    const comps = components(edgeMask, w, h, x0, y0, x1, y1).filter((c) => c.area >= 4);
    let on = 0;
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) on += edgeMask[y * w + x];
    const frac = on / ((x1 - x0) * (y1 - y0));
    edgeSev.push(Math.min(1, frac * 8 + comps.length * 0.04));
    chipsTotal += comps.length;
    if (comps.length) findings.push({ area: 'edges', where: `${name} edge (${side})`, what: `${comps.length} chip${comps.length === 1 ? '' : 's'} / white spot${comps.length === 1 ? '' : 's'} along the edge`, severity: edgeSev[edgeSev.length - 1], sure: 'likely' });
  }
  edgeSev.sort((a, b) => b - a);
  const edgesG = sevToGrade(edgeSev[0] * 0.6 + edgeSev[1] * 0.25 + edgeSev[2] * 0.15);
  metrics.edgeChips = chipsTotal;

  // ----- surface (half resolution for speed) -----
  const hw = w >> 1, hh = h >> 1;
  // 2x2 pooling: brightest pixel keeps thin bright scratches, darkest keeps tiny dark specks
  const g2 = new Uint8Array(hw * hh);
  const gMax = new Uint8Array(hw * hh);
  const gMin = new Uint8Array(hw * hh);
  for (let y = 0; y < hh; y++)
    for (let x = 0; x < hw; x++) {
      const i = y * 2 * w + x * 2;
      const a = gray[i], b = gray[i + 1], c = gray[i + w], d = gray[i + w + 1];
      g2[y * hw + x] = (a + b + c + d) >> 2;
      gMax[y * hw + x] = Math.max(a, b, c, d);
      gMin[y * hw + x] = Math.min(a, b, c, d);
    }
  const inner = (x: number, y: number) => x >= (MARGIN + EDGE) / 2 && y >= (MARGIN + EDGE) / 2 && x < hw - (MARGIN + EDGE) / 2 && y < hh - (MARGIN + EDGE) / 2;
  const opened = morph(morph(gMax, hw, hh, 5, false), hw, hh, 5, true);
  const closed = morph(morph(gMin, hw, hh, 3, true), hw, hh, 3, false);
  const lap = new Float32Array(hw * hh);
  for (let y = 1; y < hh - 1; y++) for (let x = 1; x < hw - 1; x++) { const i = y * hw + x; lap[i] = Math.abs(g2[i - 1] + g2[i + 1] + g2[i - hw] + g2[i + hw] - 4 * g2[i]); }
  const busy = boxMean(lap, hw, hh, 6);
  const scratchM = new Uint8Array(hw * hh);
  const speckM = new Uint8Array(hw * hh);
  for (let y = 0; y < hh; y++)
    for (let x = 0; x < hw; x++) {
      if (!inner(x, y)) continue;
      const i = y * hw + x;
      if (gMax[i] - opened[i] > 40) scratchM[i] = 1;
      if (closed[i] - gMin[i] > 45 && gMin[i] > 120 && busy[i] < 6) speckM[i] = 1;
    }
  const scratches = components(scratchM, hw, hh).filter((c) => {
    const len = Math.hypot(c.bw, c.bh);
    return len >= 15 && c.area / len < 3 && c.bw * c.bh > c.area * 3;
  });
  const specks = components(speckM, hw, hh).filter((c) => c.area >= 1 && c.area <= 15);
  // stains in the border ring: off-colour patches surrounded by clean border
  const ring = (x: number, y: number) => {
    const X = x * 2, Y = y * 2;
    const inRing = (Y >= MARGIN + 4 && Y < MARGIN + 30) || (Y >= h - MARGIN - 30 && Y < h - MARGIN - 4) || (X >= MARGIN + 4 && X < MARGIN + 30) || (X >= w - MARGIN - 30 && X < w - MARGIN - 4);
    const inCorner = (X < CORNER || X >= w - CORNER) && (Y < CORNER || Y >= h - CORNER);
    return inRing && !inCorner;
  };
  const dist = (x: number, y: number) => {
    const j = (y * 2 * w + x * 2) * 3;
    return Math.abs(im.rgb[j] - br) + Math.abs(im.rgb[j + 1] - bg) + Math.abs(im.rgb[j + 2] - bb);
  };
  const stainM = new Uint8Array(hw * hh);
  for (let y = 0; y < hh; y++) for (let x = 0; x < hw; x++) if (ring(x, y) && dist(x, y) > 60 && !white[y * 2 * w + x * 2]) stainM[y * hw + x] = 1;
  const cleanAt = (x: number, y: number) => dist(x, y) < 45 || val[y * 2 * w + x * 2] < 45;
  const stains = components(stainM, hw, hh).filter((c) => {
    if (c.area < 10 || c.area > 750) return false;
    let clean = 0, tot = 0;
    for (let x = c.x - 2; x <= c.x + c.bw + 1; x++)
      for (const y of [c.y - 2, c.y + c.bh + 1]) if (x >= 0 && y >= 0 && x < hw && y < hh) { tot++; if (cleanAt(x, y)) clean++; }
    for (let y = c.y - 2; y <= c.y + c.bh + 1; y++)
      for (const x of [c.x - 2, c.x + c.bw + 1]) if (x >= 0 && y >= 0 && x < hw && y < hh) { tot++; if (cleanAt(x, y)) clean++; }
    return tot > 0 && clean / tot > 0.6;
  });

  let sev = 0;
  if (scratches.length) {
    const total = scratches.reduce((s, c) => s + Math.hypot(c.bw, c.bh) * 2, 0);
    const ss = Math.min(1, total / 900);
    sev = Math.max(sev, ss);
    findings.push({ area: 'surface', where: side, what: `${scratches.length} possible scratch${scratches.length === 1 ? '' : 'es'} (total ~${Math.round(total / 10)} mm)`, severity: ss, sure: scratches.length < 3 ? 'possible' : 'likely' });
  }
  if (specks.length > 6) {
    const ps = Math.min(0.5, specks.length / 60);
    sev = Math.max(sev, ps);
    findings.push({ area: 'surface', where: side, what: `${specks.length} small specks / dimples (print dots, debris or dents)`, severity: ps, sure: 'possible' });
  }
  if (stains.length) {
    const st = Math.min(0.7, stains.reduce((s, c) => s + c.area * 4, 0) / 2500);
    sev = Math.max(sev, st);
    findings.push({ area: 'surface', where: side, what: `${stains.length} discoloured patch${stains.length === 1 ? '' : 'es'} in the border (stain, wax or ink)`, severity: st, sure: 'possible' });
  }
  metrics.scratches = scratches.length;
  metrics.specks = specks.length;
  metrics.stains = stains.length;

  // ----- fading + error check vs the official image -----
  const errBoxes: [number, number, number, number][] = [];
  if (officialUrl) {
    const off = await officialPixels(officialUrl, hw, hh);
    if (off && off.w === hw && off.h === hh) {
      const small: Img = { w: hw, h: hh, rgb: new Uint8Array(hw * hh * 3) };
      for (let y = 0; y < hh; y++) for (let x = 0; x < hw; x++) for (let c = 0; c < 3; c++) small.rgb[(y * hw + x) * 3 + c] = im.rgb[(y * 2 * w + x * 2) * 3 + c];
      const sa = satVal(small).s, so = satVal(off).s;
      const mean = (a: ArrayLike<number>) => { let t = 0; for (let i = 0; i < a.length; i++) t += a[i]; return t / a.length; };
      const std = (a: ArrayLike<number>) => { const m = mean(a); let t = 0; for (let i = 0; i < a.length; i++) t += (a[i] - m) ** 2; return Math.sqrt(t / a.length); };
      const satRatio = mean(sa) / Math.max(1, mean(so));
      const conRatio = std(toGray(small)) / Math.max(1, std(toGray(off)));
      if (satRatio < 0.7 && conRatio < 0.8) findings.push({ area: 'surface', where: side, what: `Colours look faded vs the official card (${Math.round(satRatio * 100)}% saturation). Could be sun fading or dim lighting.`, severity: 0.5, sure: 'possible' });
      // normalise each image, compare cell by cell
      const norm = (m: Img) => {
        const out = new Float32Array(m.w * m.h * 3);
        for (let c = 0; c < 3; c++) {
          const ch = Array.from({ length: m.w * m.h }, (_, i) => m.rgb[i * 3 + c]);
          const mu = mean(ch), sd = std(ch) + 1e-3;
          for (let i = 0; i < ch.length; i++) out[i * 3 + c] = (ch[i] - mu) / sd;
        }
        return out;
      };
      const A = norm(small), O = norm(off);
      const gx = 7, gy = 10, cw = Math.floor(hw / gx), ch = Math.floor(hh / gy);
      const cells: [number, number, number][] = [];
      for (let i = 0; i < gx; i++)
        for (let j = 0; j < gy; j++) {
          let t = 0;
          for (let y = j * ch; y < (j + 1) * ch; y += 2) for (let x = i * cw; x < (i + 1) * cw; x += 2) { const k = (y * hw + x) * 3; t += (Math.abs(A[k] - O[k]) + Math.abs(A[k + 1] - O[k + 1]) + Math.abs(A[k + 2] - O[k + 2])) / 3; }
          cells.push([t / ((cw / 2) * (ch / 2)), i, j]);
        }
      const med = median(cells.map((c) => c[0]));
      const bad = cells.filter((c) => c[0] > Math.max(1.1, med * 2.2));
      if (bad.length && bad.length <= cells.length * 0.35) {
        bad.forEach(([, i, j]) => errBoxes.push([i * cw * 2, j * ch * 2, cw * 2, ch * 2]));
        findings.push({ area: 'error', where: side, what: `${bad.length} area${bad.length === 1 ? '' : 's'} look different from the official card: possible misprint / error card, alteration, or a different version`, severity: 0.4, sure: 'possible' });
      }
    }
  }

  // ----- views -----
  const views: Inspection['views'] = [];
  views.push({ name: 'Corners', uris: await Promise.all([[0, 0], [w - CORNER, 0], [0, h - CORNER], [w - CORNER, h - CORNER]].map(([x, y]) => crop(uri, x, y, CORNER, CORNER, 3))) });
  views.push({ name: 'Edges', uris: await Promise.all([crop(uri, 0, 0, w, 40, 1), crop(uri, 0, h - 40, w, 40, 1), crop(uri, 0, 0, 40, h, 1), crop(uri, w - 40, 0, 40, h, 1)]) });
  const small = new Uint8Array(hw * hh * 3);
  for (let y = 0; y < hh; y++) for (let x = 0; x < hw; x++) for (let c = 0; c < 3; c++) small[(y * hw + x) * 3 + c] = im.rgb[(y * 2 * w + x * 2) * 3 + c];
  views.push({ name: 'Inverted', uris: [encode(small.map((v) => 255 - v), hw, hh)] });
  const mean15 = boxMean(g2, hw, hh, 6);
  views.push({ name: 'Black & white', uris: [encode(grayToRgb(Array.from(g2, (v, i) => (v > mean15[i] - 9 ? 255 : 0))), hw, hh)] });
  views.push({ name: 'Surface detail', uris: [encode(grayToRgb(Array.from(g2, (v, i) => Math.max(0, Math.min(255, (v - mean15[i]) * 2.4 + 128)))), hw, hh)] });
  const map = small.map((v) => v * 0.45);
  const paint = (idx: number, c: [number, number, number]) => { map[idx * 3] = c[0]; map[idx * 3 + 1] = c[1]; map[idx * 3 + 2] = c[2]; };
  for (let y = 0; y < hh; y++)
    for (let x = 0; x < hw; x++) {
      const fi = y * 2 * w + x * 2;
      // whitening only matters in the edge band (the inside of a card can be white on purpose)
      const X = x * 2, Y = y * 2;
      const inCard = X >= MARGIN && Y >= MARGIN && X < w - MARGIN && Y < h - MARGIN;
      const nearEdge = inCard && (X < MARGIN + EDGE || Y < MARGIN + EDGE || X >= w - MARGIN - EDGE || Y >= h - MARGIN - EDGE);
      if (nearEdge && (white[fi] || white[fi + 1] || white[fi + w] || dark[fi])) paint(y * hw + x, [255, 0, 255]);
    }
  scratches.forEach((c) => c.px.forEach((p) => paint(p, [255, 230, 0])));
  specks.forEach((c) => c.px.forEach((p) => paint(p, [0, 220, 255])));
  stains.forEach((c) => c.px.forEach((p) => paint(p, [120, 255, 0])));
  errBoxes.forEach(([x, y, bw, bh]) => {
    const X = x >> 1, Y = y >> 1, W2 = bw >> 1, H2 = bh >> 1;
    for (let k = 0; k < W2; k++) for (const yy of [Y, Y + 1, Y + H2 - 2, Y + H2 - 1]) if (yy < hh) paint(yy * hw + X + k, [255, 140, 0]);
    for (let k = 0; k < H2; k++) for (const xx of [X, X + 1, X + W2 - 2, X + W2 - 1]) if (xx < hw) paint((Y + k) * hw + xx, [255, 140, 0]);
  });
  views.push({ name: 'Defect map', uris: [encode(map, hw, hh)] });

  return { subgrades: { corners: cornersG, edges: edgesG, surface: sevToGrade(sev) }, findings, photoNotes, metrics, views };
}
