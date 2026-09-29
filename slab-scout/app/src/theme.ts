import { StyleSheet } from 'react-native';

export const C = {
  bg: '#0D1015',
  surface: '#161A21',
  surface2: '#20252E',
  line: '#2A303B',
  ink: '#ECEFF4',
  ink2: '#9BA4B3',
  accent: '#FF6A33',
  accentInk: '#140A05',
  gold: '#E6B94B',
  goldSoft: '#2B2413',
  good: '#43C47A',
  warn: '#E3A83E',
  crit: '#F0625F',
};

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

export const S = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  pad: { padding: 16, gap: 14 },
  h1: { color: C.ink, fontSize: 26, fontWeight: '800', letterSpacing: 0.3 },
  h2: { color: C.ink, fontSize: 20, fontWeight: '700' },
  h3: { color: C.ink, fontSize: 16, fontWeight: '700' },
  body: { color: C.ink, fontSize: 15, lineHeight: 21 },
  muted: { color: C.ink2, fontSize: 13, lineHeight: 18 },
  eyebrow: { color: C.ink2, fontSize: 11, letterSpacing: 1.4, textTransform: 'uppercase', fontWeight: '600' },
  card: { backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: C.line, padding: 14, gap: 10 },
  input: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, color: C.ink, fontSize: 15 },
  btn: { borderRadius: 12, paddingVertical: 13, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: C.surface2, borderWidth: 1, borderColor: C.line },
  btnText: { color: C.ink, fontWeight: '700', fontSize: 15 },
  primary: { backgroundColor: C.accent, borderColor: C.accent },
  primaryText: { color: C.accentInk, fontWeight: '800', fontSize: 16, letterSpacing: 0.3 },
  chip: { backgroundColor: C.surface2, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4 },
  chipText: { color: C.ink, fontSize: 12, fontWeight: '600' },
  row: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  banner: { backgroundColor: '#2A2112', borderColor: '#5A4520', borderWidth: 1, borderRadius: 10, padding: 12 },
  mono: { fontVariant: ['tabular-nums'] },
});
