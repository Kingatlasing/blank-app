import React from 'react';
import { Image, Linking, Pressable, StyleSheet, Text, View, ViewStyle } from 'react-native';
import { C, S, gradeColor } from '../theme';

export function Chip({ label, gold, color }: { label: string; gold?: boolean; color?: string }) {
  return (
    <View style={[S.chip, gold && { backgroundColor: C.goldSoft }]}>
      <Text style={[S.chipText, gold && { color: C.gold }, color ? { color } : null]}>{label}</Text>
    </View>
  );
}

export function Btn({ label, onPress, primary, disabled, style, danger }: { label: string; onPress: () => void; primary?: boolean; disabled?: boolean; style?: ViewStyle; danger?: boolean }) {
  return (
    <Pressable style={[S.btn, primary && S.primary, disabled && { opacity: 0.45 }, style]} onPress={onPress} disabled={disabled}>
      <Text style={[primary ? S.primaryText : S.btnText, danger && { color: C.crit }]}>{label}</Text>
    </Pressable>
  );
}

export function Section({ n, title, children }: { n?: number; title: string; children: React.ReactNode }) {
  return (
    <View style={S.card}>
      <Text style={S.h3}>{n ? `${n} · ` : ''}{title}</Text>
      {children}
    </View>
  );
}

export function Slab({ who, grade, label, sub }: { who: string; grade?: number | string | null; label?: string; sub?: string }) {
  return (
    <View style={st.slab}>
      <View style={st.slabLabel}>
        <Text style={S.eyebrow}>{who}</Text>
        <Text style={[st.grade, { color: gradeColor(grade ?? undefined) }]}>{grade ?? '—'}</Text>
        <Text style={st.slabLbl}>{label || ' '}</Text>
        {sub ? <Text style={S.muted}>{sub}</Text> : null}
      </View>
      <View style={st.well} />
    </View>
  );
}

export const VERDICTS: Record<string, [string, string, string]> = {
  looks_genuine: ['#123524', '#43C47A', 'Looks genuine'],
  unsure: ['#2A2112', '#E3A83E', "Can't confirm, check closely"],
  likely_fake: ['#3A1616', '#F0625F', 'Likely fake'],
  custom_or_proxy: ['#2A1F33', '#C08BF0', 'Custom card or proxy'],
  not_checked: ['#20252E', '#9BA4B3', 'Not checked'],
};

export function Verdict({ verdict, reasons }: { verdict: string; reasons: string[] }) {
  const [bg, fg, label] = VERDICTS[verdict] || VERDICTS.not_checked;
  return (
    <View style={{ backgroundColor: bg, borderColor: fg, borderWidth: 1, borderRadius: 10, padding: 12, gap: 4 }}>
      <Text style={{ color: fg, fontWeight: '800' }}>{label}</Text>
      {reasons.length ? reasons.map((r, i) => <Text key={i} style={S.muted}>• {r}</Text>) : <Text style={S.muted}>Pick a database match or use the AI boost to compare against the real card.</Text>}
    </View>
  );
}

export function Thumb({ b64, uri, w = 46 }: { b64?: string; uri?: string; w?: number }) {
  const src = uri ? { uri } : b64 ? { uri: `data:image/jpeg;base64,${b64}` } : null;
  return src ? <Image source={src} style={{ width: w, height: (w * 88) / 63, borderRadius: 5 }} /> : <View style={{ width: w, height: (w * 88) / 63, borderRadius: 5, backgroundColor: C.surface2 }} />;
}

export function LinkRow({ links }: { links: [string, string][] }) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
      {links.map(([label, url]) => (
        <Pressable key={label} onPress={() => Linking.openURL(url).catch(() => {})} style={st.link}>
          <Text style={S.chipText}>{label} ↗</Text>
        </Pressable>
      ))}
    </View>
  );
}

const st = StyleSheet.create({
  slab: { flex: 1, backgroundColor: '#1B2029', borderWidth: 1, borderColor: '#343B48', borderRadius: 12, padding: 6 },
  slabLabel: { backgroundColor: C.surface, borderRadius: 7, borderWidth: 1, borderColor: '#343B48', padding: 10, minHeight: 112, gap: 2 },
  grade: { fontSize: 40, fontWeight: '800', lineHeight: 44 },
  slabLbl: { color: C.ink, fontWeight: '700', fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.5 },
  well: { height: 10, marginHorizontal: 8, marginTop: 6, borderWidth: 1, borderTopWidth: 0, borderColor: '#343B48', borderBottomLeftRadius: 6, borderBottomRightRadius: 6 },
  link: { borderWidth: 1, borderColor: C.line, borderRadius: 999, paddingHorizontal: 11, paddingVertical: 6 },
});
