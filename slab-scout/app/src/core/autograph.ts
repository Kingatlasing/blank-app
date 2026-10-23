/**
 * Autograph check on the phone (port of the web app's core/autograph.py, plain JS, no OpenCV).
 *
 * Finds a signature on the card, tells on-card from sticker autos, reads the maker's certification
 * wording, and estimates the signature's own grade (boldness, skips) the way PSA/DNA and Beckett describe
 * it. It does NOT authenticate a signature: PSA/DNA, JSA and Beckett do that by comparing with known
 * examples of the person's signature, ink and flow under magnification. The app only reports what it sees.
 *
 * PSA autograph grades: 10 = bold, no skipping or retracing; 9 = a very light skip; 8 = more noticeable
 * skip or very slight fading; 7 = even fading or a minor blemish.
 *
 * Pixel sizes are the web app's, for a 630 px wide card (scaled for smaller copies, but thin ink then looks
 * fainter, so pass the full 630x880 card for the same results as the web app).
 */
export interface AutographResult {
  found: boolean;
  kind: '' | 'on-card' | 'sticker';
  /** the maker's certified-autograph wording was read on the card */
  certified: boolean;
  /** x, y, w, h in 630x880 card pixels */
  box: [number, number, number, number] | null;
  autoGrade: number | null;
  notes: string[];
  verify: string;
}

export const CERT =
  /certified\s+auto|authentic\s+(?:auto|signature)|autograph(?:ed)?\s+(?:card|issue)|signed\s+(?:by|in\s+person)|guaranteed\s+(?:by|authentic)|topps\s+certified|panini\s+authentic|upper\s+deck\s+(?:authenticated|certif)|leaf\s+(?:authentic|certif)|\bauto(?:graph)?\s*(?:#|serial)|on[- ]card\s+auto/i;

/** The card's type / variant / name says it's signed. */
export const SIGNED = /\bauto(graph)?s?\b|signature|signed/i;

/* ---------- small helpers ---------- */
/** Running min or max over a k x k square (rows then columns). */
function morph(src: Uint8Array, w: number, h: number, k: number, max: boolean) {
  const r = k >> 1;
  const tmp = new Uint8Array(src.length);
  const out = new Uint8Array(src.length);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      let m = src[y * w + x];
      for (let d = -r; d <= r; d++) {
        const xx = x + d;
        if (xx < 0 || xx >= w) continue;
        const v = src[y * w + xx];
        if (max ? v > m : v < m) m = v;
      }
      tmp[y * w + x] = m;
    }
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      let m = tmp[y * w + x];
      for (let d = -r; d <= r; d++) {
        const yy = y + d;
        if (yy < 0 || yy >= h) continue;
        const v = tmp[yy * w + x];
        if (max ? v > m : v < m) m = v;
      }
      out[y * w + x] = m;
    }
  return out;
}

/** 8-neighbour connected components of a 0/1 mask: label image (0 = none) + boxes and areas. */
function label(mask: Uint8Array, w: number, h: number) {
  const lab = new Int32Array(w * h);
  const stats: { x: number; y: number; bw: number; bh: number; area: number }[] = [{ x: 0, y: 0, bw: 0, bh: 0, area: 0 }];
  const stack: number[] = [];
  for (let s = 0; s < w * h; s++) {
    if (!mask[s] || lab[s]) continue;
    const id = stats.length;
    let minx = w, maxx = 0, miny = h, maxy = 0, area = 0;
    lab[s] = id;
    stack.push(s);
    while (stack.length) {
      const p = stack.pop()!;
      const py = (p / w) | 0, px = p - py * w;
      area++;
      if (px < minx) minx = px;
      if (px > maxx) maxx = px;
      if (py < miny) miny = py;
      if (py > maxy) maxy = py;
      for (let dy = -1; dy <= 1; dy++)
        for (let dx = -1; dx <= 1; dx++) {
          const nx = px + dx, ny = py + dy;
          if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
          const q = ny * w + nx;
          if (mask[q] && !lab[q]) {
            lab[q] = id;
            stack.push(q);
          }
        }
    }
    stats.push({ x: minx, y: miny, bw: maxx - minx + 1, bh: maxy - miny + 1, area });
  }
  return { lab, stats };
}

/** Number of 8-connected pieces in a 0/1 mask. */
const pieces = (mask: Uint8Array, w: number, h: number) => label(mask, w, h).stats.length - 1;

const median = (v: ArrayLike<number>) => {
  const s = Array.from(v).sort((a, b) => a - b);
  return s.length ? s[s.length >> 1] : 0;
};

/** sRGB -> CIE Lab a*, b* (same units as OpenCV's 8-bit Lab minus 128). */
const LIN = Array.from({ length: 256 }, (_, i) => {
  const c = i / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
});
function labAB(r: number, g: number, b: number): [number, number] {
  const R = LIN[r], G = LIN[g], B = LIN[b];
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const X = f((0.412453 * R + 0.35758 * G + 0.180423 * B) / 0.950456);
  const Y = f(0.212671 * R + 0.71516 * G + 0.072169 * B);
  const Z = f((0.019334 * R + 0.119193 * G + 0.950227 * B) / 1.088754);
  return [500 * (X - Y), 200 * (Y - Z)];
}

/** Two-pass chamfer distance to the nearest 0 pixel (1 / 1.4 steps, close to OpenCV's 3x3 L2). */
function distance(mask: Uint8Array, w: number, h: number) {
  const INF = 1e9;
  const d = new Float32Array(w * h);
  for (let i = 0; i < d.length; i++) d[i] = mask[i] ? INF : 0;
  const D = 1.4;
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (!d[i]) continue;
      let v = d[i];
      if (x > 0) v = Math.min(v, d[i - 1] + 1);
      if (y > 0) {
        v = Math.min(v, d[i - w] + 1);
        if (x > 0) v = Math.min(v, d[i - w - 1] + D);
        if (x < w - 1) v = Math.min(v, d[i - w + 1] + D);
      }
      d[i] = v;
    }
  for (let y = h - 1; y >= 0; y--)
    for (let x = w - 1; x >= 0; x--) {
      const i = y * w + x;
      if (!d[i]) continue;
      let v = d[i];
      if (x < w - 1) v = Math.min(v, d[i + 1] + 1);
      if (y < h - 1) {
        v = Math.min(v, d[i + w] + 1);
        if (x < w - 1) v = Math.min(v, d[i + w + 1] + D);
        if (x > 0) v = Math.min(v, d[i + w - 1] + D);
      }
      d[i] = v;
    }
  return d;
}

/* ---------- the check ---------- */
/**
 * `rgb` = a w x h RGB copy of the straightened card (630x880 or smaller). `text` / `backText` = words read
 * on the front / back. `cardType` = the card type the person picked ('Autograph' makes it look harder).
 */
export function checkAutograph(rgb: Uint8Array, w: number, h: number, text = '', backText = '', cardType = ''): AutographResult {
  const sc = w / 630; // pixel sizes below are for a 630 px wide card
  const odd = (v: number) => Math.max(3, Math.round(v * sc) | 1);
  const n = w * h;
  const g = new Uint8Array(n);
  for (let i = 0, j = 0; i < n; i++, j += 3) g[i] = Math.round(0.299 * rgb[j] + 0.587 * rgb[j + 1] + 0.114 * rgb[j + 2]);
  // thin dark marks on a lighter background (ink), whatever the overall brightness: black-hat (closing - image)
  const k = odd(11);
  const closed = morph(morph(g, w, h, k, true), w, h, k, false);
  const m = new Uint8Array(n);
  for (let i = 0; i < n; i++) if (closed[i] - g[i] > 38) m[i] = 1;
  // strokes of one signature joined up
  const joined = morph(m, w, h, 3, true);
  const { lab, stats } = label(joined, w, h);

  type Hit = { score: number; box: [number, number, number, number]; id: number };
  const search = (fillMax: number, curlMin: number, sameMin: number, widthMax: number): Hit | null => {
    let best: Hit | null = null;
    for (let id = 1; id < stats.length; id++) {
      const { x, y, bw, bh, area } = stats[id];
      if (bw < 0.18 * w || bh < 0.035 * h || bh > 0.3 * h || bw < 2 * bh) continue; // signatures are long and low
      if (area / (bw * bh) > fillMax) continue; // solid shapes / printed blocks, not pen strokes
      // cursive: one long connected stroke that curls; printed text breaks into letters, frame lines stay straight.
      // Outline length ~ pixels on the outer boundary (outside reached from the box edge, holes in loops don't count)
      const W2 = bw + 2, H2 = bh + 2;
      const inC = (xx: number, yy: number) => xx >= 1 && yy >= 1 && xx <= bw && yy <= bh && lab[(y + yy - 1) * w + x + xx - 1] === id;
      const outside = new Uint8Array(W2 * H2);
      const st: number[] = [0];
      outside[0] = 1;
      while (st.length) {
        const p = st.pop()!;
        const py = (p / W2) | 0, px = p - py * W2;
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          const nx = px + dx, ny = py + dy;
          if (nx < 0 || ny < 0 || nx >= W2 || ny >= H2) continue;
          const q = ny * W2 + nx;
          if (!outside[q] && !inC(nx, ny)) {
            outside[q] = 1;
            st.push(q);
          }
        }
      }
      let per = 0;
      for (let yy = 1; yy <= bh; yy++)
        for (let xx = 1; xx <= bw; xx++)
          if (inC(xx, yy) && (outside[yy * W2 + xx - 1] || outside[yy * W2 + xx + 1] || outside[(yy - 1) * W2 + xx] || outside[(yy + 1) * W2 + xx])) per++;
      const curl = (per * 1.13) / (2 * (bw + bh)); // 1.13: boundary pixels -> outline length (diagonal steps)
      if (curl < curlMin) continue;
      // one pen: the ink is a single colour and the stroke keeps an even, thin width (artwork outlines vary)
      const as: number[] = [], bs: number[] = [];
      const raw = new Uint8Array(bw * bh);
      for (let yy = 0; yy < bh; yy++)
        for (let xx = 0; xx < bw; xx++) {
          const i = (y + yy) * w + x + xx;
          if (lab[i] !== id || !m[i]) continue;
          raw[yy * bw + xx] = 1;
          const [a, b] = labAB(rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]);
          as.push(a);
          bs.push(b);
        }
      if (as.length < 40 * sc * sc) continue;
      const ma = median(as), mb = median(bs);
      let same = 0;
      for (let i = 0; i < as.length; i++) if (Math.max(Math.abs(as[i] - ma), Math.abs(bs[i] - mb)) <= 10) same++;
      if (same / as.length < sameMin) continue; // most of the stroke must be one ink colour
      const dist = distance(raw, bw, bh);
      const widths = Array.from(dist).filter((v) => v > 0).sort((p, q) => p - q);
      if (!widths.length || widths[Math.min(widths.length - 1, Math.floor(widths.length * 0.9))] > widthMax * sc) continue;
      const score = curl * Math.min(bw / w, 0.6);
      if (!best || score > best.score) best = { score, box: [x, y, bw, bh], id };
    }
    return best;
  };

  const wants = /^auto/i.test(cardType);
  let best = search(0.45, 2.2, 0.6, 4.0);
  if (!best && wants) best = search(0.65, 1.7, 0.4, 6.0); // the person says it's signed: look harder (ink over busy artwork)
  const certified = CERT.test(`${text}\n${backText}`);
  const out: AutographResult = { found: false, kind: '', certified, box: null, autoGrade: null, notes: [], verify: '' };
  if (!best && !certified && !wants) return out;
  if (best) {
    const [x, y, bw, bh] = best.box;
    const toCard = 630 / w;
    out.found = true;
    out.box = [Math.round(x * toCard), Math.round(y * toCard), Math.round(bw * toCard), Math.round(bh * toCard)];
    if (!(certified || wants)) out.notes.push('Possible autograph spotted (mark the card type as Autograph if it is signed).');
    // sticker: the signature sits on a light, even patch with its own straight outline
    const pad = Math.round(0.04 * w);
    const x0 = Math.max(0, x - pad), y0 = Math.max(0, y - pad), x1 = Math.min(w, x + bw + pad), y1 = Math.min(h, y + bh + pad);
    const pw = x1 - x0, ph = y1 - y0;
    const comp = new Uint8Array(pw * ph); // the signature's pixels in the padded box
    for (let yy = y0; yy < y1; yy++) for (let xx = x0; xx < x1; xx++) if (lab[yy * w + xx] === best.id) comp[(yy - y0) * pw + xx - x0] = 1;
    const near = morph(comp, pw, ph, odd(9), true); // stroke plus a few px around it
    let s1 = 0, s2 = 0, cnt = 0;
    for (let yy = y0; yy < y1; yy++)
      for (let xx = x0; xx < x1; xx++) {
        const i = yy * w + xx;
        if (near[(yy - y0) * pw + xx - x0]) continue;
        s1 += g[i];
        s2 += g[i] * g[i];
        cnt++;
      }
    const mean = cnt ? s1 / cnt : 0;
    const sd = cnt ? Math.sqrt(Math.max(0, s2 / cnt - mean * mean)) : 99;
    const even = sd < 22 && mean > 170;
    // straight outline: at least two long level edges (the label's top and bottom) around the signature
    const ex0 = Math.max(0, x0 - pad), ey0 = Math.max(1, y0 - pad), ex1 = Math.min(w, x1 + pad), ey1 = Math.min(h - 1, y1 + pad);
    const minRun = bw * 0.8;
    const longRows: number[] = [];
    for (let yy = ey0; yy < ey1; yy++) {
      let run = 0, gap = 0, bestRun = 0;
      for (let xx = ex0; xx < ex1; xx++) {
        let edge = false;
        for (const dy of [-1, 0, 1]) {
          const yv = yy + dy;
          if (yv < 1 || yv >= h - 1) continue;
          if (Math.abs(g[(yv + 1) * w + xx] - g[(yv - 1) * w + xx]) >= 40) edge = true;
        }
        if (edge) {
          run += gap + 1;
          gap = 0;
        } else if (run && gap < 6 * sc) gap++;
        else {
          run = 0;
          gap = 0;
        }
        if (run > bestRun) bestRun = run;
      }
      if (bestRun >= minRun) longRows.push(yy);
    }
    let lines = 0;
    for (let i = 0; i < longRows.length; i++) if (i === 0 || longRows[i] - longRows[i - 1] > 3) lines++;
    out.kind = even && lines >= 2 ? 'sticker' : 'on-card';
    // signature grade: ink strength and breaks (skips) along the stroke
    const ink: number[] = [], paper: number[] = [];
    const rawBox = new Uint8Array(bw * bh);
    for (let yy = 0; yy < bh; yy++)
      for (let xx = 0; xx < bw; xx++) {
        const i = (y + yy) * w + x + xx;
        (comp[(y + yy - y0) * pw + x + xx - x0] ? ink : paper).push(g[i]);
        rawBox[yy * bw + xx] = m[i];
      }
    const contrast = ink.length && paper.length ? median(paper) - median(ink) : 0;
    const parts = pieces(rawBox, bw, bh);
    let ag: number, why: string;
    if (contrast >= 70 && parts <= 4) [ag, why] = [10, 'bold and unbroken'];
    else if (contrast >= 55 && parts <= 8) [ag, why] = [9, 'strong, with a very light skip at most'];
    else if (contrast >= 40) [ag, why] = [8, 'slight fading or a noticeable skip'];
    else [ag, why] = [7, 'faded or broken in places'];
    out.autoGrade = ag;
    out.notes.push(`Signature looks ${why} in this photo (autograph grade estimate ${ag}).`);
    out.notes.push(out.kind === 'sticker' ? 'Sticker auto: signed on a label that was applied at the factory.' : 'On-card auto: signed directly on the card.');
  } else if (wants) {
    out.notes.push('No signature found in this photo. Hold the light at an angle so the ink shows, or retake closer.');
  }
  if (certified)
    out.notes.push("The card carries the maker's certified-autograph wording: the manufacturer guarantees the signature (e.g. Topps replaces or credits a certified auto a grader rejects).");
  out.verify = certified
    ? 'Manufacturer-certified autos are guaranteed by the maker; check the serial / back wording matches the set.'
    : "Not a certified card: only an authenticator (PSA/DNA, JSA or Beckett) can verify the signature, by comparing it with known examples of the person's signature, ink and flow. The app can't confirm it's real.";
  return out;
}
