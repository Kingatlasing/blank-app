/**
 * Card colour signature: tells parallels / rarities apart by colour (Prizm Silver vs Blue vs Gold, a
 * Refractor's rainbow, a black 1/1). Same signature as the web app (streamlit/core/colour.py) and the one
 * computed for every price-guide photo, so a scan can be compared with what each parallel looks like.
 * Used only to rank a card's parallels against each other, never on its own to name a card.
 */
import { colourProfiles, siblings, loadSet, type Card } from './catalog';
import { pixels } from './imageTools';

const CW = 24;
const CH = 34;

/** 26 hex chars: ring L/A/B, inside L/A/B, 12-bin hue histogram, ring rainbow spread. */
export async function colourSignature(cardUri: string): Promise<string> {
  const { data } = await pixels(cardUri, CW, CH);
  const ring = [0, 0, 0];
  const cen = [0, 0, 0];
  let nr = 0;
  let nc = 0;
  const hist = new Array(12).fill(0);
  let vx = 0;
  let vy = 0;
  let vw = 0;
  for (let j = 0; j < CH; j++)
    for (let i = 0; i < CW; i++) {
      const k = (j * CW + i) * 3;
      const r = data[k];
      const g = data[k + 1];
      const b = data[k + 2];
      const L = (r + g + b) / 3;
      const A = r - g;
      const B = (r + g) / 2 - b;
      const ch = Math.hypot(A, B);
      const isR = i < 2 || i >= CW - 2 || j < 2 || j >= CH - 2;
      const m = isR ? ring : cen;
      m[0] += L;
      m[1] += A;
      m[2] += B;
      if (isR) nr++;
      else nc++;
      if (ch > 25) {
        const hu = Math.atan2(B, A);
        hist[Math.floor(((hu + Math.PI) / (2 * Math.PI)) * 12) % 12] += ch;
        if (isR) {
          vx += Math.cos(hu) * ch;
          vy += Math.sin(hu) * ch;
          vw += ch;
        }
      }
    }
  const q = (v: number) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0');
  const enc = (m: number[], n: number) => q(m[0] / n) + q(m[1] / n / 2 + 128) + q(m[2] / n / 2 + 128);
  const mx = Math.max(...hist);
  const hh = hist.map((v) => (mx > 0 ? Math.round((15 * v) / mx) : 0).toString(16)).join('');
  const spread = vw > 0 ? 1 - Math.hypot(vx, vy) / vw : 0;
  return enc(ring, nr) + enc(cen, nc) + hh + q(spread * 255);
}

type Dec = { ring: number[]; center: number[]; hist: number[]; rainbow: number };
function decode(sig: string): Dec | null {
  if (!sig || sig.length < 26) return null;
  const v = [0, 2, 4, 6, 8, 10].map((i) => parseInt(sig.slice(i, i + 2), 16));
  return {
    ring: [v[0], (v[1] - 128) * 2, (v[2] - 128) * 2],
    center: [v[3], (v[4] - 128) * 2, (v[5] - 128) * 2],
    hist: sig.slice(12, 24).split('').map((c) => parseInt(c, 16)),
    rainbow: parseInt(sig.slice(24, 26), 16) / 255,
  };
}
const dist3 = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

export function colourDistance(a: string, b: string): number {
  const x = decode(a);
  const y = decode(b);
  if (!x || !y) return 1;
  const sx = x.hist.reduce((s, v) => s + v, 0);
  const sy = y.hist.reduce((s, v) => s + v, 0);
  const hist = sx && sy ? x.hist.reduce((s, v, i) => s + Math.abs(v / sx - y.hist[i] / sy), 0) / 2 : sx === sy ? 0 : 0.5;
  return 0.5 * (dist3(x.ring, y.ring) / 90) + 0.2 * (dist3(x.center, y.center) / 120) + 0.2 * hist + 0.6 * Math.abs(x.rainbow - y.rainbow);
}

// hue bins measured on pure colours: teal 0, light blue 1, blue 2-3, purple 4-5, pink 5-6, red 6, orange 7-8,
// gold 8, yellow 9, green 10-11
const NAME_COLOURS: [RegExp, { bins?: number[]; L?: 'dark' | 'light' | 'neutral' }][] = [
  [/\bpink\b|magenta|fuchsia|\brose\b/, { bins: [5, 6] }],
  [/\bred\b|ruby|crimson|scarlet/, { bins: [6] }],
  [/\borange\b|copper|bronze/, { bins: [7, 8] }],
  [/\bgold\b|golden|yellow|canary|lemon/, { bins: [8, 9] }],
  [/\bgreen\b|emerald|lime|jade/, { bins: [10, 11] }],
  [/\bteal\b|aqua|turquoise|cyan/, { bins: [0, 1] }],
  [/\bblue\b|sapphire|navy|\bice\b/, { bins: [1, 2, 3] }],
  [/\bpurple\b|violet|amethyst|lavender/, { bins: [4, 5] }],
  [/\bblack\b|onyx|noir/, { L: 'dark' }],
  [/\bwhite\b|snow|pearl/, { L: 'light' }],
  [/\bsilver\b|platinum/, { L: 'neutral' }],
];
const BIN_NAMES = ['teal', 'light blue', 'blue', 'blue', 'purple', 'purple/pink', 'red/pink', 'orange', 'gold', 'yellow', 'green', 'green'];

/** How well the scan fits the colour in the parallel's name (0 good .. 1 bad); null when the name has none. */
export function nameColourScore(variant: string, sig: string): number | null {
  const x = decode(sig);
  if (!x || !variant) return null;
  const v = variant.toLowerCase();
  for (const [re, spec] of NAME_COLOURS) {
    if (!re.test(v)) continue;
    const tot = x.hist.reduce((s, n) => s + n, 0);
    if (spec.bins) {
      if (!tot) return 0.8;
      const share = spec.bins.reduce((s, i) => s + x.hist[i], 0) / tot;
      let near = 0;
      for (const i of spec.bins)
        for (const d of [-1, 1]) {
          const k = (i + d + 12) % 12;
          if (!spec.bins.includes(k)) near += x.hist[k];
        }
      return Math.max(0, 1 - 1.2 * (share + (0.4 * near) / tot));
    }
    const L = (x.ring[0] + x.center[0]) / 2;
    const chroma = Math.hypot(x.ring[1], x.ring[2]);
    if (spec.L === 'dark') return Math.min(1, Math.max(0, (L - 70) / 90));
    if (spec.L === 'light') return Math.min(1, Math.max(0, (200 - x.ring[0]) / 80));
    return Math.min(1, chroma / 60);
  }
  return null;
}

export function describeColours(sig: string): string {
  const x = decode(sig);
  if (!x) return '';
  const [L, A, B] = x.ring;
  const c = Math.hypot(A, B);
  const top = x.hist.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]);
  const border = L < 60 ? 'black' : L > 215 && c < 25 ? 'white' : c < 25 ? 'silver/grey' : x.hist.some((v) => v) ? BIN_NAMES[top[0][1]] : 'grey';
  const main = [...new Set(top.filter(([v]) => v >= 6).slice(0, 2).map(([, i]) => BIN_NAMES[i]))];
  return `border ${border}${main.length ? ', mostly ' + main.join(' and ') : ''}${x.rainbow > 0.55 ? ', rainbow/refractor shine' : ''}`;
}

export interface ParallelFit { card: Card; fit: number; why: string }

/** The card's parallels ranked by how well the scan's colours fit each (best first); [] when colour can't tell. */
export async function rankParallels(top: Card, sig: string): Promise<ParallelFit[]> {
  await loadSet(top.setId).catch(() => null);
  const sib = siblings(top);
  if (sib.length < 2) return [];
  const prof = (await colourProfiles())[top.setId] || {};
  const out: ParallelFit[] = [];
  for (const c of sib) {
    const p = prof[c.variant || 'Base'];
    let fit: number | null = null;
    let why = '';
    if (p) {
      fit = Math.min(1, colourDistance(sig, p) / 1.5);
      why = "colours of this parallel's photos";
    }
    const n = nameColourScore(c.variant || '', sig);
    if (n !== null) {
      fit = fit === null ? n : (fit * 2 + n) / 3;
      why = why ? `${why} + colour in the name` : 'colour in the name';
    }
    if (fit !== null) out.push({ card: c, fit, why });
  }
  return out.sort((a, b) => a.fit - b.fit);
}
