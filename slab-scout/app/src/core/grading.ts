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
  method: 'checklist' | 'ai' | 'automatic inspection' | 'inspection + your checklist';
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
