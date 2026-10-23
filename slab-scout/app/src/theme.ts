import { StyleSheet } from 'react-native';

/** Dark navy + indigo panels, lime for value / scanning, indigo for selection. */
export const C = {
  /** near-black page background */
  bg: '#0A0B10',
  /** dark slate panels / cards */
  surface: '#1B1D2A',
  /** raised controls on a panel (chips, inputs on cards) */
  surface2: '#262938',
  /** image wells / placeholders */
  surface3: '#14161F',
  /** deeper indigo for hero cards */
  hero: '#171A33',
  heroTop: '#2A2F8A',
  line: '#2A2D3D',
  lineSoft: '#20222F',
  ink: '#FFFFFF',
  /** muted grey-lavender secondary text */
  ink2: '#8E93A8',
  ink3: '#5F6478',
  /** lime: scan button, scanner frame, prices */
  accent: '#D4F25A',
  accentInk: '#0A0B10',
  lime: '#D4F25A',
  /** bright indigo: selected pills, primary buttons */
  blue: '#4F5BF5',
  indigo: '#3A3FC9',
  indigoDeep: '#23267A',
  purple: '#8B5CF6',
  orange: '#FF8A3D',
  goldBright: '#FFC93C',
  /** prices (kept as `gold` so older code compiles) */
  gold: '#D4F25A',
  goldSoft: '#242A12',
  good: '#3DDC84',
  goodSoft: '#12301F',
  warn: '#F5B544',
  crit: '#FF5A4A',
  critSoft: '#3A1620',
  overlay: 'rgba(10,11,16,0.72)',
  tabBar: '#0E0F15',
};

/** Binder cover colours offered when creating a binder. */
export const BINDER_COLORS = ['#4F5BF5', '#A100FF', '#4FCFE8', '#077A8A', '#D4F25A', '#FFE27A', '#FF5A4A', '#FFA07A', '#F78FE3', '#3A3A44'];

export const R = { sm: 10, md: 14, lg: 20, xl: 24, pill: 999 };

export const gradeColor = (g?: number | string) => {
  const n = typeof g === 'string' ? parseFloat(g) : g;
  if (n == null || !isFinite(n)) return C.ink2;
  if (n >= 9) return C.good;
  if (n >= 7) return C.warn;
  return C.crit;
};

export function money(v?: number) {
  if (v == null || !isFinite(v)) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: v < 100 ? 2 : 0,
    minimumFractionDigits: v < 100 && v % 1 ? 2 : 0,
  }).format(v);
}

/** 2954.2 -> "2,954%" */
export const pctText = (p: number) => `${Math.abs(p) >= 100 ? Math.round(Math.abs(p)).toLocaleString('en-US') : Math.abs(p).toFixed(1)}%`;

export const S = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  pad: { padding: 16, gap: 14 },
  h1: { color: C.ink, fontSize: 28, fontWeight: '800', letterSpacing: -0.3 },
  h2: { color: C.ink, fontSize: 20, fontWeight: '800' },
  h3: { color: C.ink, fontSize: 16, fontWeight: '700' },
  body: { color: C.ink, fontSize: 15, lineHeight: 21 },
  muted: { color: C.ink2, fontSize: 13, lineHeight: 18 },
  eyebrow: { color: C.ink2, fontSize: 11, letterSpacing: 1.2, textTransform: 'uppercase', fontWeight: '700' },
  card: { backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.lineSoft, padding: 16, gap: 10 },
  input: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, borderRadius: R.md, paddingHorizontal: 14, paddingVertical: 12, color: C.ink, fontSize: 15 },
  btn: { borderRadius: R.md, paddingVertical: 13, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: C.surface2, borderWidth: 1, borderColor: C.line },
  btnText: { color: C.ink, fontWeight: '700', fontSize: 15 },
  primary: { backgroundColor: C.blue, borderColor: C.blue },
  primaryText: { color: '#fff', fontWeight: '800', fontSize: 16, letterSpacing: 0.2 },
  chip: { backgroundColor: C.surface2, borderRadius: R.pill, paddingHorizontal: 10, paddingVertical: 4 },
  chipText: { color: C.ink, fontSize: 12, fontWeight: '600' },
  pill: { backgroundColor: C.surface, borderRadius: R.pill, paddingHorizontal: 16, paddingVertical: 9, borderWidth: 1, borderColor: C.line },
  pillOn: { backgroundColor: C.blue, borderColor: C.blue },
  pillText: { color: C.ink2, fontSize: 14, fontWeight: '700' },
  row: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  banner: { backgroundColor: '#2A2412', borderColor: '#5A4A20', borderWidth: 1, borderRadius: R.md, padding: 12 },
  mono: { fontVariant: ['tabular-nums'] },
});
