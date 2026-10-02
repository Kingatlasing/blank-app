/** Grade estimate from measured centering + condition checklist. Same rules as the Streamlit app (see core/grading.py). */

const PSA_CENTER: [number, number, number][] = [[10, 55, 75], [9, 60, 90], [8, 65, 90], [7, 70, 90], [6, 80, 90], [5, 85, 90], [4, 85, 90], [3, 90, 90], [2, 95, 95], [1, 100, 100]];
export const PSA_LABELS: Record<number, string> = { 10: 'GEM MT', 9: 'MINT', 8: 'NM-MT', 7: 'NM', 6: 'EX-MT', 5: 'EX', 4: 'VG-EX', 3: 'VG', 2: 'GOOD', 1: 'POOR' };
export const CONDITION_OPTIONS: [string, number][] = [
  ['Flawless', 10], ['One tiny flaw', 9], ['Light wear', 8], ['Noticeable wear', 6.5], ['Heavy wear', 4], ['Crease / damage', 2],
];
export const CONDITION_HELP: Record<string, string> = {
  corners: 'White specks or rounding on any of the four corners, front and back.',
  edges: 'White chipping along the edges, especially on the back.',
  surface: 'Tilt under a light: scratches, print lines, dents, stains, holo scuffs.',
};
// TAG score bands (taggrading.com/pages/scale): 50-point bands per half grade
const TAG_BANDS: [number, string, string][] = [[990, '10', 'Pristine'], [950, '10', 'Gem Mint'], [900, '9', 'Mint'], [850, '8.5', 'NM-MT+'], [800, '8', 'NM-MT'], [750, '7.5', 'NM+'], [700, '7', 'NM'], [650, '6.5', 'EX-MT+'], [600, '6', 'EX-MT'], [550, '5.5', 'EX+'], [500, '5', 'EX'], [450, '4.5', 'VG-EX+'], [400, '4', 'VG-EX'], [350, '3.5', 'VG+'], [300, '3', 'VG'], [250, '2.5', 'Good+'], [200, '2', 'Good'], [150, '1.5', 'Fair'], [0, '1', 'Poor']];
// TAG front centering limit (larger side %) per grade; 10.5 stands for Pristine
const TAG_CENTER: [number, number][] = [[10.5, 51], [10, 55], [9, 60], [8.5, 62.5], [8, 65], [7.5, 67.5], [7, 70], [6.5, 72.5], [6, 75], [5.5, 77.5], [5, 80], [4.5, 82.5], [4, 85], [3.5, 87.5], [3, 90], [2, 95], [1.5, 98.33]];

/** Nearest checklist answer for an automatic subgrade. */
export function subgradeToOption(g: number) {
  return g >= 10 ? 'Flawless' : g >= 9 ? 'One tiny flaw' : g >= 7.5 ? 'Light wear' : g >= 5.5 ? 'Noticeable wear' : g >= 3.5 ? 'Heavy wear' : 'Crease / damage';
}

export function psaCenteringCap(front?: number | null, back?: number | null) {
  if (front == null) return 10;
  const b = back ?? 50;
  for (const [g, f, bk] of PSA_CENTER) if (front <= f && b <= bk) return g;
  return 1;
}

export interface GradeResult {
  method: 'checklist' | 'ai' | 'automatic inspection' | 'inspection + your checklist' | 'scan server';
  sub: { centering?: number; corners?: number; edges?: number; surface?: number };
  psa?: number;
  psa_label?: string;
  psa_range?: string;
  tag_score?: number;
  tag_grade?: string;
  tag_label?: string;
  centering_cap?: number;
  centering?: { front?: string; back?: string };
  notes?: string;
}

/** corners / edges / surface: a checklist answer ("Light wear") or a measured subgrade (8). */
export function estimate(front: number | null, back: number | null, corners: string | number, edges: string | number, surface: string | number): GradeResult {
  const val = (k: string | number) => (typeof k === 'number' ? k : CONDITION_OPTIONS.find((o) => o[0] === k)?.[1] ?? 9);
  const cap = psaCenteringCap(front, back);
  const centering = front == null ? 9 : Math.min(10, TAG_CENTER.find(([, lim]) => front <= lim)?.[0] ?? 1);
  const subs = { centering, corners: val(corners), edges: val(edges), surface: val(surface) };
  const cond = Math.min(subs.corners, subs.edges, subs.surface);
  const byCond = cond >= 10 ? 10 : Math.max(1, Math.floor(cond));
  const psa = Math.min(cap, byCond);
  const low = Math.max(1, psa - 1);
  const high = Math.min(10, psa + (cond >= 9 && cap > psa ? 1 : 0));
  const avg = subs.centering * 0.2 + subs.corners * 0.3 + subs.edges * 0.2 + subs.surface * 0.3;
  const score = Math.max(100, Math.min(1000, Math.round((0.7 * avg + 0.3 * Math.min(...Object.values(subs))) * 100)));
  const band = TAG_BANDS.find((b) => score >= b[0])!;
  return {
    method: 'checklist', sub: subs, psa, psa_label: PSA_LABELS[psa], psa_range: low !== high ? `${low}-${high}` : String(psa),
    tag_score: score, tag_grade: band[1], tag_label: band[2], centering_cap: cap,
  };
}

/** Centering limits per company: [grade, front max %, back max % | null]. PSA / CGC / TAG from their published
 * scales; BGS and SGC from published collector guides. Same table as the web app (core/grading.py). */
export const GRADERS: Record<string, [string, number, number | null][]> = {
  PSA: [['10', 55, 75], ['9', 60, 90], ['8', 65, 90], ['7', 70, 90], ['6', 80, 90], ['5', 85, 90], ['4', 85, 90], ['3', 90, 90], ['2', 95, 95]],
  BGS: [['10 Pristine', 50, 55], ['9.5', 55, 60], ['9', 55, 70], ['8', 60, 80], ['7', 65, 90], ['6', 70, 95]],
  SGC: [['10 Pristine', 50, null], ['10', 55, null], ['9', 60, null], ['8', 65, null], ['7', 70, null], ['6', 75, null]],
  CGC: [['10 Pristine', 50, null], ['10', 55, 75], ['9', 60, 90], ['8', 65, null], ['7.5', 65, null], ['7', 70, null], ['6', 75, null], ['4.5', 85, null]],
  TAG: [['10 Pristine', 51, null], ['10', 55, null], ['9', 60, null], ['8.5', 62.5, null], ['8', 65, null], ['7', 70, null], ['6', 75, null], ['5', 80, null]],
};
const TAG_BACK: Record<'tcg' | 'sports', Record<string, number>> = { tcg: { '10 Pristine': 52, '10': 65, '9': 75, '8.5': 85 }, sports: { '10 Pristine': 54.5, '10': 70, '9': 90, '8.5': 95 } };

/** Best grade each company allows for this centering alone (larger-side % front / back). */
export function graderCaps(front: number | null, back: number | null, tcg = true): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [comp, rows] of Object.entries(GRADERS)) {
    let best = 'below scale';
    for (const [label, f, b0] of rows) {
      const b = comp === 'TAG' ? TAG_BACK[tcg ? 'tcg' : 'sports'][label] ?? 100 : b0;
      if ((front == null || front <= f) && (back == null || b == null || back <= b)) { best = label; break; }
    }
    out[comp] = best;
  }
  return out;
}

export const CARD_STYLES: Record<string, string> = {
  standard: 'Standard (bordered): centering is the printed border on each side, card edge to the inner frame.',
  full_art: 'Full art / SIR / SAR: a thin frame with the art running to it; centering is judged on that frame, and graders are more forgiving since a shift is hard to see.',
  die_cut: 'Die-cut: shaped outline. Centering is judged on the printed design; the shaped edges and points are held to the normal corner / edge standard. No grader publishes a separate die-cut rule.',
  vintage: 'Vintage: many old cards are cut square or to other sizes; square corners are not a flaw.',
};

const FULL_ART = /full art|illustration rare|special illustration|\balt(?:ernate)? art|secret|rainbow|gold(?:en)? rare|hyper rare|character (?:super )?rare|art rare|\b(?:sar|ar|sr|ur|hr|chr|csr|sir|ir|sfa|ssr|fa)\b|trainer gallery|galarian gallery|shiny vault|borderless|showcase|full[- ]bleed/i;

/** Printed layout from the rarity / parallel and number (same rules as the web app). */
export function cardStyle(variant = '', name = '', year = '', number = ''): 'standard' | 'full_art' | 'die_cut' | 'vintage' {
  const t = `${variant} ${name}`;
  if (/die[- ]?cut/i.test(t)) return 'die_cut';
  const m = /^\D*(\d+)\s*\/\s*\D*(\d+)$/.exec(number || '');
  const secret = !!m && +m[1] > +m[2] && +m[2] > 0;
  if (FULL_ART.test(t) || secret || /^(?:SV|TG|GG)\d/i.test(number || '')) return 'full_art';
  if (/^\d{4}$/.test(year) && +year < 1957) return 'vintage';
  return 'standard';
}

export const GUIDE: [string, string][] = [
  ['Centering', 'Opposite borders are compared (55/45 = one side is 55% of the pair); the back is judged much more loosely. PSA 10: 55/45 front, 75/25 back. BGS 9.5: 55 both ways (Pristine 10: 50/50). SGC 10: 55. CGC 10: 55 front, 75 back. TAG 10: 55 front; TAG backs differ for TCG (65) and sports (70).'],
  ['Corners', 'PSA 10: four perfectly sharp corners. 9: one very minor flaw. 8: slightest fraying at one or two corners. 7: slight fraying on some. 5: minor rounding.'],
  ['Edges & surface', '10: no chipping, full original gloss, no staining. 9 allows one minor print imperfection or a very slight wax stain on the back.'],
  ['Overall', 'The weakest area decides the grade (BGS: at most a half grade above the lowest subgrade).'],
  ['Full art / die-cut / vintage', 'Full art: judged on the thin frame, more forgiving. Die-cut: no special rule; shaped edges held to the normal standard. Vintage: square-cut corners are not a flaw.'],
  ['Autographs', 'Authenticators (PSA/DNA, JSA, Beckett) compare with known examples of the signature, ink and flow. PSA auto 10 = bold, no skips; 9 = a very light skip; 8 = more noticeable skip or slight fading. Maker-certified autos are guaranteed by the maker.'],
];

/* ---------- every company's grade from the same measurements (same rules as core/grading.py all_graders) ---------- */
export interface CompanyGrade {
  grade: string;
  label: string;
  note?: string;
  sub?: Record<string, number>;
}
const HALF: Record<'BGS' | 'CGC' | 'SGC', Record<string, string>> = {
  BGS: { '10': 'Pristine', '9.5': 'Gem Mint', '9': 'Mint', '8.5': 'NM-MT+', '8': 'NM-MT', '7.5': 'NM+', '7': 'NM', '6.5': 'EX-MT+', '6': 'EX-MT', '5.5': 'EX+', '5': 'EX', '4.5': 'VG-EX+', '4': 'VG-EX', '3.5': 'VG+', '3': 'VG', '2.5': 'G+', '2': 'Good', '1.5': 'Fair', '1': 'Poor' },
  CGC: { '10': 'Gem Mint', '9.5': 'Mint+', '9': 'Mint', '8.5': 'NM/Mint+', '8': 'NM/Mint', '7.5': 'Near Mint+', '7': 'Near Mint', '6.5': 'Ex/NM+', '6': 'Ex/NM', '5.5': 'Excellent+', '5': 'Excellent', '4.5': 'VG/Ex+', '4': 'VG/Ex', '3.5': 'Very Good+', '3': 'Very Good', '2.5': 'Good+', '2': 'Good', '1.5': 'Fair', '1': 'Poor' },
  SGC: { '10': 'Gem Mint', '9.5': 'Mint+', '9': 'Mint', '8.5': 'NM-MT+', '8': 'NM-MT', '7.5': 'NM+', '7': 'NM', '6.5': 'EX-NM+', '6': 'EX-NM', '5.5': 'EX+', '5': 'EX', '4.5': 'VG-EX+', '4': 'VG-EX', '3.5': 'VG+', '3': 'VG', '2.5': 'G+', '2': 'Good', '1.5': 'Fair', '1': 'Poor' },
};
const half = (x: number) => Math.max(1, Math.min(10, Math.round(x * 2) / 2));
function companyCap(comp: string, front: number | null, back: number | null, tcg = true): number {
  if (front == null) return 10;
  for (const [label, f, b0] of GRADERS[comp]) {
    const b = comp === 'TAG' ? TAG_BACK[tcg ? 'tcg' : 'sports'][label] ?? 100 : b0;
    if (front <= f && (back == null || b == null || back <= b)) return label.includes('Pristine') ? 10.5 : parseFloat(label);
  }
  return 4;
}
function bgsCentering(front: number | null, back: number | null): number {
  const rows: [number, number, number][] = [[10, 50, 55], [9.5, 55, 60], [9, 55, 70], [8.5, 60, 80], [8, 60, 80], [7, 65, 90], [6, 70, 95], [5, 75, 95], [4, 80, 100]];
  if (front == null) return 9.5;
  for (const [g, f, b] of rows) if (front <= f && (back == null || back <= b)) return g;
  return 3;
}
/** Beckett: Black Label = four 10s; Pristine = all 9.5+ with three 10s; Gem Mint 9.5 = all 9+ with three 9.5+;
 * otherwise the lowest subgrade sets the floor and the second-lowest caps it (at most half a grade above the lowest). */
export function bgsOverall(sub: Record<string, number>): [number, string] {
  const v = Object.values(sub).sort((a, b) => a - b);
  if (v.every((x) => x >= 10)) return [10, 'Pristine (Black Label)'];
  if (v[0] >= 9.5 && v.filter((x) => x >= 10).length >= 3) return [10, 'Pristine'];
  if (v[0] >= 9 && v.filter((x) => x >= 9.5).length >= 3) return [9.5, 'Gem Mint'];
  const g = half(Math.min(v[1], v[0] + 0.5));
  return [g, HALF.BGS[String(g)] || ''];
}
export function allGraders(sub: { corners: number; edges: number; surface: number }, front: number | null, back: number | null, tcg = true): Record<string, CompanyGrade> {
  const cond = [sub.corners, sub.edges, sub.surface];
  const worst = Math.min(...cond);
  const blended = half(0.75 * worst + 0.25 * (cond.reduce((a, b) => a + b, 0) / 3));
  const out: Record<string, CompanyGrade> = {};
  const cap = psaCenteringCap(front, back);
  const psa = Math.min(cap, worst >= 10 ? 10 : Math.max(1, Math.floor(worst)));
  out.PSA = { grade: String(psa), label: PSA_LABELS[psa] || '', note: `centering allows up to ${cap}` };
  const bs = { centering: bgsCentering(front, back), corners: half(sub.corners), edges: half(sub.edges), surface: half(sub.surface) };
  const [bg, bl] = bgsOverall(bs);
  out.BGS = { grade: String(bg), label: bl, sub: bs };
  for (const comp of ['CGC', 'SGC'] as const) {
    const c = companyCap(comp, front, back, tcg);
    const g = Math.min(blended, Math.min(c, 10));
    out[comp] = g >= 10 && c >= 10.5 && worst >= 10 ? { grade: '10', label: 'Pristine' } : { grade: String(g), label: HALF[comp][String(g)] || '', note: `centering allows up to ${c >= 10 ? 10 : c}` };
  }
  const t = estimate(front, back, sub.corners, sub.edges, sub.surface);
  out.TAG = { grade: t.tag_grade || '', label: t.tag_label || '', note: `score ${t.tag_score} / 1000` };
  return out;
}
