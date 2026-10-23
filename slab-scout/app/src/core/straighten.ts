/**
 * Angled / hand-held photo correction in plain JS (a lighter port of the web app's vision._persp_quads,
 * _best_quad, _snap_edges and _warp). Kept free of Expo imports so it can be tested on its own.
 *
 *  1. findCardQuad: edges (brightness + colour) in a small copy of the photo, straight lines through them
 *     (Hough), two side lines + two end lines intersected into four-sided shapes, kept when they look like
 *     a card seen at an angle (convex, near-square corners, card proportions, big enough, sides on edges).
 *  2. snapQuad: on a sharper copy, each side is moved onto the strongest colour step next to it.
 *  3. warpQuad: perspective (homography) warp with bilinear sampling to a flat card.
 */
export type Pt = [number, number];
/** top-left, top-right, bottom-right, bottom-left */
export type Quad = [Pt, Pt, Pt, Pt];
export interface RGBImage {
  w: number;
  h: number;
  rgb: Uint8Array;
}

const CARD_W = 630;
const CARD_H = 880;
const RATIO = CARD_W / CARD_H;
const DEG = Math.PI / 180;

/* ---------- edge map (a small Canny: blur, Sobel, thin, two thresholds) ---------- */
function blur3(src: Float32Array, w: number, h: number) {
  const tmp = new Float32Array(src.length);
  const out = new Float32Array(src.length);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      tmp[i] = (src[x > 0 ? i - 1 : i] + src[i] * 2 + src[x < w - 1 ? i + 1 : i]) / 4;
    }
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      out[i] = (tmp[y > 0 ? i - w : i] + tmp[i] * 2 + tmp[y < h - 1 ? i + w : i]) / 4;
    }
  return out;
}

/** 1 = edge pixel. Brightness and two colour channels, so a dark blue border on a black desk still shows. */
export function edgeMap(im: RGBImage, lo = 30, hi = 100): Uint8Array {
  const { w, h, rgb } = im;
  const n = w * h;
  let L = new Float32Array(n), A = new Float32Array(n), B = new Float32Array(n);
  for (let i = 0, j = 0; i < n; i++, j += 3) {
    const r = rgb[j], g = rgb[j + 1], b = rgb[j + 2];
    L[i] = 0.299 * r + 0.587 * g + 0.114 * b;
    A[i] = (r - g) * 0.8; // weighted so colour steps count about as much as in the web app's Lab edges
    B[i] = (r + g) / 2 - b;
  }
  L = blur3(blur3(L, w, h), w, h);
  A = blur3(blur3(A, w, h), w, h);
  B = blur3(blur3(B, w, h), w, h);
  const mag = new Float32Array(n);
  const dir = new Uint8Array(n); // 0 = left/right, 1 = diagonal \, 2 = up/down, 3 = diagonal /
  for (let y = 1; y < h - 1; y++)
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      let best = 0, bx = 0, by = 0;
      for (const c of [L, A, B]) {
        const gx = c[i - w + 1] + 2 * c[i + 1] + c[i + w + 1] - c[i - w - 1] - 2 * c[i - 1] - c[i + w - 1];
        const gy = c[i + w - 1] + 2 * c[i + w] + c[i + w + 1] - c[i - w - 1] - 2 * c[i - w] - c[i - w + 1];
        const m = Math.abs(gx) + Math.abs(gy);
        if (m > best) {
          best = m;
          bx = gx;
          by = gy;
        }
      }
      mag[i] = best;
      const a = ((Math.atan2(by, bx) / DEG) + 180) % 180;
      dir[i] = a < 22.5 || a >= 157.5 ? 0 : a < 67.5 ? 1 : a < 112.5 ? 2 : 3;
    }
  // thin to one pixel (keep local maxima across the edge), then keep weak edges only when joined to strong ones
  const offs = [1, w + 1, w, w - 1];
  const state = new Uint8Array(n); // 1 weak, 2 strong
  const stack: number[] = [];
  for (let y = 2; y < h - 2; y++)
    for (let x = 2; x < w - 2; x++) {
      const i = y * w + x;
      const m = mag[i];
      if (m < lo) continue;
      const o = offs[dir[i]];
      if (m < mag[i - o] || m <= mag[i + o]) continue;
      state[i] = m >= hi ? 2 : 1;
      if (state[i] === 2) stack.push(i);
    }
  const out = new Uint8Array(n);
  while (stack.length) {
    const i = stack.pop()!;
    if (out[i]) continue;
    out[i] = 1;
    for (const d of [-w - 1, -w, -w + 1, -1, 1, w - 1, w, w + 1]) if (state[i + d] && !out[i + d]) stack.push(i + d);
  }
  return out;
}

function dilate3(m: Uint8Array, w: number, h: number) {
  const out = new Uint8Array(m.length);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      if (!m[y * w + x]) continue;
      for (let dy = -1; dy <= 1; dy++)
        for (let dx = -1; dx <= 1; dx++) {
          const xx = x + dx, yy = y + dy;
          if (xx >= 0 && yy >= 0 && xx < w && yy < h) out[yy * w + xx] = 1;
        }
    }
  return out;
}

/* ---------- straight lines (Hough) ---------- */
type Line = [number, number]; // rho, theta: x cos t + y sin t = rho

function houghLines(e: Uint8Array, w: number, h: number, thr: number, maxLines = 300): Line[] {
  const nT = 180;
  const cs = Array.from({ length: nT }, (_, t) => Math.cos(t * DEG));
  const sn = Array.from({ length: nT }, (_, t) => Math.sin(t * DEG));
  const D = Math.ceil(Math.hypot(w, h));
  const nR = 2 * D + 1;
  const acc = new Int32Array(nR * nT);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      if (!e[y * w + x]) continue;
      for (let t = 0; t < nT; t++) acc[(Math.round(x * cs[t] + y * sn[t]) + D) * nT + t]++;
    }
  const peaks: [number, number, number][] = [];
  for (let r = 1; r < nR - 1; r++)
    for (let t = 0; t < nT; t++) {
      const v = acc[r * nT + t];
      if (v < thr) continue;
      const tl = (t + nT - 1) % nT, tr = (t + 1) % nT;
      if (v < acc[(r - 1) * nT + t] || v <= acc[(r + 1) * nT + t] || v < acc[r * nT + tl] || v <= acc[r * nT + tr]) continue;
      peaks.push([v, r - D, t * DEG]);
    }
  peaks.sort((a, b) => b[0] - a[0]);
  const picked: Line[] = [];
  const near = Math.max(4, Math.round(Math.max(w, h) * 0.01));
  for (const [, r0, t0] of peaks) {
    let rho = r0, th = t0;
    if (rho < 0) {
      rho = -rho;
      th -= Math.PI;
    }
    if (picked.some(([r, t]) => Math.abs(rho - r) < near && Math.abs(Math.sin(th - t)) < 0.06)) continue; // same line again
    picked.push([rho, th]);
    if (picked.length >= maxLines) break;
  }
  return picked;
}

function intersect(a: Line, b: Line): Pt | null {
  const [r1, t1] = a, [r2, t2] = b;
  const a11 = Math.cos(t1), a12 = Math.sin(t1), a21 = Math.cos(t2), a22 = Math.sin(t2);
  const det = a11 * a22 - a12 * a21;
  if (Math.abs(det) < 1e-6) return null;
  return [(r1 * a22 - a12 * r2) / det, (a11 * r2 - r1 * a21) / det];
}

/* ---------- geometry helpers ---------- */
const sub = (a: Pt, b: Pt): Pt => [a[0] - b[0], a[1] - b[1]];
const len = (a: Pt) => Math.hypot(a[0], a[1]);
const dist = (a: Pt, b: Pt) => Math.hypot(a[0] - b[0], a[1] - b[1]);

export function quadArea(q: Pt[]) {
  let s = 0;
  for (let i = 0; i < q.length; i++) {
    const [x1, y1] = q[i], [x2, y2] = q[(i + 1) % q.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2;
}
function convex(q: Pt[]) {
  let sign = 0;
  for (let i = 0; i < 4; i++) {
    const a = sub(q[(i + 1) % 4], q[i]), b = sub(q[(i + 2) % 4], q[(i + 1) % 4]);
    const c = a[0] * b[1] - a[1] * b[0];
    if (Math.abs(c) < 1e-9) return false;
    if (sign && Math.sign(c) !== sign) return false;
    sign = Math.sign(c);
  }
  return true;
}

/** Order four points as top-left, top-right, bottom-right, bottom-left (same rule as the web app's _order). */
export function order(pts: Pt[]): Quad {
  const s = pts.map((p) => p[0] + p[1]);
  const d = pts.map((p) => p[1] - p[0]);
  const at = (arr: number[], max: boolean) => pts[arr.indexOf(max ? Math.max(...arr) : Math.min(...arr))];
  return [at(s, false), at(d, false), at(s, true), at(d, true)];
}

/** How far the card is turned or skewed, in degrees (top side vs level, left side vs upright). */
export function quadTilt(q: Quad) {
  const [tl, tr, , bl] = q;
  return Math.max(Math.abs(Math.atan2(tr[1] - tl[1], tr[0] - tl[0]) / DEG), Math.abs(Math.atan2(bl[0] - tl[0], bl[1] - tl[1]) / DEG));
}

/* ---------- perspective warp ---------- */
/** 3x3 homography (9 numbers, last = 1) taking the four `from` points to the four `to` points. */
export function homography(from: Pt[], to: Pt[]): number[] {
  const M: number[][] = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = from[i], [u, v] = to[i];
    M.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
    M.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  }
  // Gaussian elimination with partial pivoting
  for (let c = 0; c < 8; c++) {
    let p = c;
    for (let r = c + 1; r < 8; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    const piv = M[c][c] || 1e-12;
    for (let r = 0; r < 8; r++) {
      if (r === c) continue;
      const f = M[r][c] / piv;
      if (f) for (let k = c; k < 9; k++) M[r][k] -= f * M[c][k];
    }
  }
  const h = M.map((row, i) => row[8] / (row[i] || 1e-12));
  return [...h, 1];
}

/** Flatten the quad to a W x H RGB image (bilinear sampling, edge pixels repeated outside the photo). */
export function warpQuad(im: RGBImage, q: Quad, W = CARD_W, H = CARD_H): Uint8Array {
  const Hm = homography([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], q);
  const out = new Uint8Array(W * H * 3);
  const { w, h, rgb } = im;
  for (let v = 0; v < H; v++)
    for (let u = 0; u < W; u++) {
      const z = Hm[6] * u + Hm[7] * v + 1;
      let x = (Hm[0] * u + Hm[1] * v + Hm[2]) / z;
      let y = (Hm[3] * u + Hm[4] * v + Hm[5]) / z;
      x = Math.min(w - 1, Math.max(0, x));
      y = Math.min(h - 1, Math.max(0, y));
      const x0 = Math.floor(x), y0 = Math.floor(y);
      const x1 = Math.min(w - 1, x0 + 1), y1 = Math.min(h - 1, y0 + 1);
      const fx = x - x0, fy = y - y0;
      const i00 = (y0 * w + x0) * 3, i10 = (y0 * w + x1) * 3, i01 = (y1 * w + x0) * 3, i11 = (y1 * w + x1) * 3;
      const o = (v * W + u) * 3;
      for (let c = 0; c < 3; c++) {
        const top = rgb[i00 + c] + (rgb[i10 + c] - rgb[i00 + c]) * fx;
        const bot = rgb[i01 + c] + (rgb[i11 + c] - rgb[i01 + c]) * fx;
        out[o + c] = Math.round(top + (bot - top) * fy);
      }
    }
  return out;
}

function sample(im: RGBImage, x: number, y: number, out: number[]) {
  const { w, h, rgb } = im;
  x = Math.min(w - 1, Math.max(0, x));
  y = Math.min(h - 1, Math.max(0, y));
  const x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(w - 1, x0 + 1), y1 = Math.min(h - 1, y0 + 1);
  const fx = x - x0, fy = y - y0;
  for (let c = 0; c < 3; c++) {
    const a = rgb[(y0 * w + x0) * 3 + c], b = rgb[(y0 * w + x1) * 3 + c], d = rgb[(y1 * w + x0) * 3 + c], e = rgb[(y1 * w + x1) * 3 + c];
    out[c] = (a + (b - a) * fx) * (1 - fy) + (d + (e - d) * fx) * fy;
  }
  return out;
}

const medianOf = (v: number[]) => {
  const s = [...v].sort((a, b) => a - b);
  return s.length ? s[s.length >> 1] : 0;
};

/** How strongly the corner tips differ from the border next to them (high = rounded card corners with
 * background showing; low = a square window, frame or the card's own inner panel). */
function roundedCornerScore(im: RGBImage, q: Quad) {
  const W = 126, H = 176; // as if the outline were flattened to 126 x 176 (only the few pixels needed are sampled)
  const Hm = homography([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], q);
  const px = [0, 0, 0];
  const at = (u: number, v: number) => {
    const z = Hm[6] * u + Hm[7] * v + 1;
    return sample(im, (Hm[0] * u + Hm[1] * v + Hm[2]) / z, (Hm[3] * u + Hm[4] * v + Hm[5]) / z, px);
  };
  const scores: number[] = [];
  for (const [cx, cy, sx, sy] of [[0, 0, 1, 1], [W - 1, 0, -1, 1], [0, H - 1, 1, -1], [W - 1, H - 1, -1, -1]]) {
    const tip: number[][] = [[], [], []], edge: number[][] = [[], [], []];
    for (let i = 0; i <= 2; i++)
      for (let j = 0; j <= 2; j++) {
        const p = at(cx + sx * j, cy + sy * i);
        for (let c = 0; c < 3; c++) tip[c].push(p[c]);
      }
    for (let i = 1; i <= 3; i++)
      for (let j = 14; j <= 22; j++) {
        let p = at(cx + sx * j, cy + sy * i);
        for (let c = 0; c < 3; c++) edge[c].push(p[c]);
        p = at(cx + sx * i, cy + sy * j);
        for (let c = 0; c < 3; c++) edge[c].push(p[c]);
      }
    scores.push([0, 1, 2].reduce((s, c) => s + Math.abs(medianOf(tip[c]) - medianOf(edge[c])), 0));
  }
  scores.sort((x, y) => x - y);
  return (scores[1] + scores[2] + scores[3]) / 3; // ignore the single worst corner (fingers, glare)
}

/** Second-weakest side's colour difference between just outside and just inside the outline (null when
 * every side runs along the photo's own edge). */
function sideContrast(im: RGBImage, q: Quad, off: number) {
  const c: Pt = [(q[0][0] + q[1][0] + q[2][0] + q[3][0]) / 4, (q[0][1] + q[1][1] + q[2][1] + q[3][1]) / 4];
  const sides: number[] = [];
  const A = [0, 0, 0], B = [0, 0, 0];
  for (let k = 0; k < 4; k++) {
    const p = q[k], r = q[(k + 1) % 4];
    const d = sub(r, p);
    const L = len(d) || 1;
    let nrm: Pt = [-d[1] / L, d[0] / L];
    const mid: Pt = [(p[0] + r[0]) / 2, (p[1] + r[1]) / 2];
    if ((mid[0] - c[0]) * nrm[0] + (mid[1] - c[1]) * nrm[1] < 0) nrm = [-nrm[0], -nrm[1]];
    const diffs: number[] = [];
    for (let i = 0; i < 30; i++) {
      const t = 0.15 + (0.7 * i) / 29;
      const m: Pt = [p[0] + d[0] * t, p[1] + d[1] * t];
      const xo = m[0] + nrm[0] * off, yo = m[1] + nrm[1] * off, xi = m[0] - nrm[0] * off, yi = m[1] - nrm[1] * off;
      if (xo < 0 || yo < 0 || xo > im.w - 1 || yo > im.h - 1 || xi < 0 || yi < 0 || xi > im.w - 1 || yi > im.h - 1) continue;
      sample(im, xo, yo, A);
      sample(im, xi, yi, B);
      diffs.push(Math.abs(A[0] - B[0]) + Math.abs(A[1] - B[1]) + Math.abs(A[2] - B[2]));
    }
    if (diffs.length >= 10) sides.push(medianOf(diffs));
  }
  if (!sides.length) return null;
  sides.sort((a, b) => a - b);
  return sides.length === 4 ? sides[1] : sides[0]; // one side may be partly covered by fingers
}

export interface QuadResult {
  quad: Quad;
  /** share of each side's length on an edge: top, right, bottom, left */
  support: number[];
  tilt: number;
  /** how clearly the corners are rounded (card) vs square (frame) */
  rounded: number;
}

/**
 * The card's outline in a small photo (long side ~400 px), or null. Same checks as the web app: convex,
 * corners within 10 degrees of square, sides foreshortened at most 30%, card proportions within 0.12,
 * at least 12% of the photo, every side mostly on an edge (one side may be half hidden by fingers).
 */
export function findCardQuad(im: RGBImage): QuadResult | null {
  const { w, h } = im;
  const edges = edgeMap(im);
  const lines = houghLines(edges, w, h, Math.round(Math.min(w, h) * 0.18));
  const emap = dilate3(edges, w, h);
  const N = 40;
  const support = (a: Pt, b: Pt) => {
    let hits = 0;
    for (let i = 0; i < N; i++) {
      const t = 0.1 + (0.8 * i) / (N - 1);
      const x = Math.trunc(a[0] + (b[0] - a[0]) * t), y = Math.trunc(a[1] + (b[1] - a[1]) * t);
      if (x >= 0 && y >= 0 && x < w && y < h && emap[y * w + x]) hits++;
    }
    return hits / N;
  };
  const cos35 = Math.cos(35 * DEG);
  const xmid = ([r, t]: Line) => (r - (h / 2) * Math.sin(t)) / (Math.cos(t) + 1e-9);
  const vert = lines.filter((l) => Math.abs(Math.cos(l[1])) > cos35).slice(0, 24).sort((a, b) => xmid(a) - xmid(b));
  const horiz = lines.filter((l) => Math.abs(Math.sin(l[1])) > cos35).slice(0, 60);
  const sin10 = Math.sin(10 * DEG);
  const cands: { sides: number[]; q: Quad }[] = [];
  for (let i = 0; i < vert.length; i++)
    for (let j = i + 1; j < vert.length; j++) {
      if (xmid(vert[j]) - xmid(vert[i]) < 0.2 * w) continue;
      // end lines ranked by how well they run along an edge BETWEEN these two side lines
      let ends: [number, number, Pt, Pt][] = [];
      for (const hl of horiz) {
        const a = intersect(vert[i], hl), b = intersect(vert[j], hl);
        if (!a || !b) continue;
        const sp = support(a, b);
        if (sp >= 0.35) ends.push([a[1] + b[1], sp, a, b]);
      }
      ends.sort((x, y) => y[1] - x[1]);
      ends = ends.slice(0, 10).sort((x, y) => x[0] - y[0]);
      for (let k = 0; k < ends.length; k++)
        for (let m = k + 1; m < ends.length; m++) {
          const [, sTop, p0, p1] = ends[k];
          const [, sBot, p3, p2] = ends[m];
          const q: Quad = [p0, p1, p2, p3];
          if (q.some(([x, y]) => x < -0.03 * w || x > 1.03 * w || y < -0.03 * h || y > 1.03 * h)) continue;
          if (!convex(q) || quadArea(q) < 0.12 * w * h) continue;
          const top = dist(q[0], q[1]), bot = dist(q[3], q[2]), lef = dist(q[0], q[3]), rig = dist(q[1], q[2]);
          if (Math.min(top, bot) / Math.max(top, bot) < 0.7 || Math.min(lef, rig) / Math.max(lef, rig) < 0.7) continue; // stronger foreshortening than a hand-held photo gives
          const ratio = (top + bot) / 2 / ((lef + rig) / 2);
          if (Math.abs(Math.min(ratio, 1 / ratio) - RATIO) > 0.12) continue;
          // a card seen at an angle still has near-square corners; a slanted background line joined to its sides does not
          let angOk = true;
          for (let c = 0; c < 4; c++) {
            const u = sub(q[(c + 3) % 4], q[c]), v = sub(q[(c + 1) % 4], q[c]);
            if (Math.abs(u[0] * v[0] + u[1] * v[1]) / (len(u) * len(v) + 1e-9) > sin10) {
              angOk = false;
              break;
            }
          }
          if (!angOk) continue;
          const sides = [sTop, support(q[1], q[2]), sBot, support(q[3], q[0])];
          const srt = [...sides].sort((a, b) => a - b);
          if (srt[0] < 0.25 || srt[1] < 0.5) continue; // at most one side may be mostly hidden (fingers)
          cands.push({ sides, q });
        }
    }
  if (!cands.length) return null;
  cands.sort((a, b) => b.sides.reduce((s, x) => s + x, 0) + Math.min(...b.sides) - (a.sides.reduce((s, x) => s + x, 0) + Math.min(...a.sides)));
  const off = Math.max(2, Math.round(Math.max(w, h) * 0.005));
  const scored = cands.slice(0, 200).flatMap(({ sides, q }) => {
    const top = dist(q[0], q[1]), lef = dist(q[0], q[3]);
    if (lef < top) return []; // sideways shapes are almost always background
    const err = Math.min(Math.abs(Math.min(top, lef) / Math.max(top, lef) - RATIO), 0.089);
    return [{ q, sides, area: quadArea(q), err, sup: [...sides].sort((a, b) => a - b)[1], round: roundedCornerScore(im, q), con: sideContrast(im, q, off) }];
  });
  if (!scored.length) return null;
  // a real card edge separates card from table on every side; outlines traced along artwork or table texture don't
  const known = scored.map((c) => c.con).filter((c): c is number => c != null);
  const bestC = known.length ? Math.max(...known) : 0;
  const kept = scored.filter((c) => c.con == null || c.con >= 0.25 * bestC);
  const rounded = kept.filter((c) => c.round >= 45);
  const pool = rounded.length ? rounded : kept;
  const topArea = Math.max(...pool.map((c) => c.area));
  // sides on real edges + size + rounded corners - off card proportions + card / background contrast
  const key = (c: (typeof pool)[number]) =>
    (c.area >= 0.8 * topArea ? 100 : 0) + c.sup + c.area / topArea + Math.min(c.round, 300) / 300 - 5 * c.err + 1.5 * (c.con == null || !bestC ? 1 : c.con / bestC);
  const win = pool.reduce((a, b) => (key(b) > key(a) ? b : a));
  const quad = order(win.q);
  return { quad, support: win.sides, tilt: quadTilt(quad), rounded: win.round };
}

/** Least-squares line depth = m * pos + c through edge points, dropping outliers once (web _fit_edge). */
function fitEdge(pts: Pt[]): [number, number, number] | null {
  if (pts.length < 8) return null;
  const fit = (p: Pt[]) => {
    const n = p.length;
    let sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (const [x, y] of p) {
      sx += x;
      sy += y;
      sxx += x * x;
      sxy += x * y;
    }
    const den = n * sxx - sx * sx || 1e-9;
    const m = (n * sxy - sx * sy) / den;
    return [m, (sy - m * sx) / n];
  };
  let [m, c] = fit(pts);
  const res = pts.map(([x, y]) => Math.abs(y - (m * x + c)));
  const lim = Math.max(2, 2.5 * medianOf(res));
  const keep = pts.filter((_, i) => res[i] <= lim);
  if (keep.length < 8) return null;
  [m, c] = fit(keep);
  const spread = keep.reduce((s, [x, y]) => s + Math.abs(y - (m * x + c)), 0) / keep.length;
  return [m, c, spread];
}

/**
 * Precise sides on a sharper copy (web _snap_edges). The first outline can sit a little off the real edge:
 * on the printed border's inner line, or cut by a finger. On every side, colour steps are looked for in a
 * band from a little inside to well outside the outline, along 31 cross-lines; steps at the same depth are
 * fitted with a straight line, and the OUTERMOST line that runs cleanly along most of the side and is a
 * strong change wins (the card edge, not a faint sleeve edge or table texture). The four lines are then
 * intersected. `snapped` = how many sides were found this way (the rest stay where they were); the first
 * outline comes back unchanged (snapped 0) when the lines found don't make a card shape.
 */
export function snapQuad(im: RGBImage, q: Quad): { quad: Quad; snapped: number } {
  const c: Pt = [(q[0][0] + q[1][0] + q[2][0] + q[3][0]) / 4, (q[0][1] + q[1][1] + q[2][1] + q[3][1]) / 4];
  const P = [0, 0, 0], Q = [0, 0, 0];
  const wd = (dist(q[0], q[1]) + dist(q[3], q[2])) / 2, ht = (dist(q[0], q[3]) + dist(q[1], q[2])) / 2;
  const sides: { a: Pt; d: Pt }[] = []; // a point and direction for each side's line
  let snapped = 0;
  for (let k = 0; k < 4; k++) {
    const p = q[k], r = q[(k + 1) % 4];
    const d = sub(r, p);
    const L = len(d) || 1;
    const u: Pt = [d[0] / L, d[1] / L];
    let nrm: Pt = [-u[1], u[0]];
    const mid: Pt = [(p[0] + r[0]) / 2, (p[1] + r[1]) / 2];
    if ((mid[0] - c[0]) * nrm[0] + (mid[1] - c[1]) * nrm[1] < 0) nrm = [-nrm[0], -nrm[1]];
    const across = k % 2 ? wd : ht; // top / bottom sides: steps across the card's height
    const rIn = Math.max(3, Math.round(across * 0.02)), rOut = Math.max(5, Math.round(across * 0.06));
    // per cross-line: every clear local peak of colour change (offset > 0 = outside the outline)
    const per: { pos: number; steps: [number, number][] }[] = [];
    for (let i = 0; i < 31; i++) {
      const t = 0.15 + (0.7 * i) / 30;
      const m: Pt = [p[0] + d[0] * t, p[1] + d[1] * t];
      const g: number[] = [];
      for (let s = -rIn; s <= rOut; s++) {
        sample(im, m[0] + nrm[0] * (s + 1), m[1] + nrm[1] * (s + 1), P);
        sample(im, m[0] + nrm[0] * (s - 1), m[1] + nrm[1] * (s - 1), Q);
        g.push(Math.abs(P[0] - Q[0]) + Math.abs(P[1] - Q[1]) + Math.abs(P[2] - Q[2]));
      }
      const steps: [number, number][] = [];
      for (let j = 1; j < g.length - 1; j++) if (g[j] >= 30 && g[j] >= g[j - 1] && g[j] > g[j + 1]) steps.push([j - rIn, g[j]]);
      per.push({ pos: t * L, steps });
    }
    // candidate depths: cluster step offsets, fit a line to each cluster
    const all = [...new Set(per.flatMap((x) => x.steps.map(([o]) => Math.floor((o + rIn) / 3))))].sort((a, b) => a - b);
    const cands: [number, number, [number, number, number]][] = []; // depth at the middle, strength, fit
    for (const bin of all) {
      const centre = bin * 3 - rIn + 1;
      const pts: Pt[] = [];
      const strg: number[] = [];
      for (const x of per) {
        const near = x.steps.filter(([o]) => Math.abs(o - centre) <= 4);
        if (!near.length) continue;
        const [o, gg] = near.reduce((a, b) => (b[1] > a[1] ? b : a));
        pts.push([x.pos, o]);
        strg.push(gg);
      }
      const f = pts.length >= 0.6 * per.length ? fitEdge(pts) : null;
      if (f && f[2] <= 2) cands.push([f[1] + (f[0] * L) / 2, medianOf(strg), f]);
    }
    if (!cands.length) {
      sides.push({ a: p, d: u });
      continue;
    }
    const top = Math.max(...cands.map((x) => x[1]));
    const [, , [m, cc]] = cands.filter((x) => x[1] >= 0.35 * top).reduce((a, b) => (b[0] > a[0] ? b : a));
    sides.push({ a: [p[0] + nrm[0] * cc, p[1] + nrm[1] * cc], d: [u[0] + nrm[0] * m, u[1] + nrm[1] * m] });
    snapped++;
  }
  const cross = (s1: { a: Pt; d: Pt }, s2: { a: Pt; d: Pt }): Pt | null => {
    const den = s1.d[0] * s2.d[1] - s1.d[1] * s2.d[0];
    if (Math.abs(den) < 1e-9) return null;
    const t = ((s2.a[0] - s1.a[0]) * s2.d[1] - (s2.a[1] - s1.a[1]) * s2.d[0]) / den;
    return [s1.a[0] + s1.d[0] * t, s1.a[1] + s1.d[1] * t];
  };
  // corner k sits where side k-1 (ending there) meets side k (starting there)
  const out: Pt[] = [];
  for (let k = 0; k < 4; k++) {
    const pt = cross(sides[(k + 3) % 4], sides[k]);
    if (!pt) return { quad: q, snapped: 0 };
    out.push(pt);
  }
  const o = out as Quad;
  const w2 = (dist(o[0], o[1]) + dist(o[3], o[2])) / 2, h2 = (dist(o[0], o[3]) + dist(o[1], o[2])) / 2;
  if (!convex(o) || Math.abs(w2 / h2 - wd / ht) > 0.05 || w2 < wd * 0.85 || h2 < ht * 0.85) return { quad: q, snapped: 0 }; // not a card outline: keep the first one
  return { quad: o, snapped };
}
