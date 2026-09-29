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
const TAG_BANDS: [number, string, string][] = [[990, '10', 'Pristine'], [950, '10', 'Gem Mint'], [900, '9', 'Mint'], [850, '8.5', 'NM-MT+'], [800, '8', 'NM-MT'], [750, '7.5', 'NM+'], [700, '7', 'NM'], [600, '6', 'EX-MT'], [500, '5', 'EX'], [400, '4', 'VG-EX'], [300, '3', 'VG'], [200, '2', 'Good'], [0, '1', 'Poor']];

export function psaCenteringCap(front?: number | null, back?: number | null) {
  if (front == null) return 10;
  const b = back ?? 50;
  for (const [g, f, bk] of PSA_CENTER) if (front <= f && b <= bk) return g;
  return 1;
}

export interface GradeResult {
  method: 'checklist' | 'ai';
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

export function estimate(front: number | null, back: number | null, corners: string, edges: string, surface: string): GradeResult {
  const val = (k: string) => CONDITION_OPTIONS.find((o) => o[0] === k)?.[1] ?? 9;
  const cap = psaCenteringCap(front, back);
  const centering = front == null ? 9 : cap === 10 ? (front <= 52 ? 10 : 9.5) : cap;
  const subs = { centering, corners: val(corners), edges: val(edges), surface: val(surface) };
  const cond = Math.min(subs.corners, subs.edges, subs.surface);
  const byCond = cond >= 10 ? 10 : cond >= 9 ? 9 : cond >= 8 ? 8 : cond >= 6.5 ? 6 : cond >= 4 ? 4 : 2;
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
