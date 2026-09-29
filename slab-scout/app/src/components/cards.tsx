/** Rare Candy-style building blocks: card tiles, grids, segmented control, rarity chip, value chart. */
import React from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { C, S, money } from '../theme';

export function RarityChip({ printRun }: { printRun?: number | null }) {
  if (!printRun) return null;
  const hot = printRun <= 5;
  const warm = printRun <= 25;
  return (
    <View style={[S.chip, { alignSelf: 'flex-start', backgroundColor: hot ? '#3A1616' : warm ? C.goldSoft : C.surface2 }]}>
      <Text style={[S.chipText, { color: hot ? C.crit : warm ? C.gold : C.ink }]}>{printRun === 1 ? '1 of 1' : `/${printRun}`}</Text>
    </View>
  );
}

export function Tile({ title, sub, price, thumb, printRun, onPress, badge }: { title: string; sub?: string; price: string; thumb?: string; printRun?: number | null; onPress?: () => void; badge?: string }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [st.tile, pressed && { opacity: 0.7 }]}>
      {thumb ? (
        <Image source={{ uri: `data:image/jpeg;base64,${thumb}` }} style={st.img} />
      ) : (
        <View style={st.ph}>
          <Text style={st.phText} numberOfLines={3}>{title}</Text>
        </View>
      )}
      <Text style={st.nm} numberOfLines={2}>{title}</Text>
      {sub ? <Text style={st.sub} numberOfLines={2}>{sub}</Text> : null}
      <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap' }}>
        <RarityChip printRun={printRun} />
        {badge ? <View style={S.chip}><Text style={S.chipText}>{badge}</Text></View> : null}
      </View>
      <Text style={st.px}>{price}</Text>
    </Pressable>
  );
}

/** Lays children out 3 per row, like a card binder page. */
export function Grid({ children, cols = 3 }: { children: React.ReactNode; cols?: number }) {
  const items = React.Children.toArray(children);
  const rows: React.ReactNode[][] = [];
  for (let i = 0; i < items.length; i += cols) rows.push(items.slice(i, i + cols));
  return (
    <View style={{ gap: 8 }}>
      {rows.map((r, i) => (
        <View key={i} style={{ flexDirection: 'row', gap: 8 }}>
          {r.map((c, j) => (
            <View key={j} style={{ flex: 1 }}>{c}</View>
          ))}
          {Array.from({ length: cols - r.length }).map((_, j) => (
            <View key={`e${j}`} style={{ flex: 1 }} />
          ))}
        </View>
      ))}
    </View>
  );
}

export function Segmented<T extends string>({ options, value, onChange }: { options: [T, string][]; value: T; onChange: (v: T) => void }) {
  return (
    <View style={st.seg}>
      {options.map(([id, label]) => (
        <Pressable key={id} style={[st.segBtn, value === id && st.segOn]} onPress={() => onChange(id)}>
          <Text style={[st.segText, value === id && { color: C.ink }]} numberOfLines={1}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function ChipRow<T extends string>({ options, value, onChange }: { options: T[]; value: T; onChange: (v: T) => void }) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
      {options.map((o) => (
        <Pressable key={o} onPress={() => onChange(o)} style={[S.chip, { paddingVertical: 7, paddingHorizontal: 12 }, value === o && { backgroundColor: C.accent }]}>
          <Text style={[S.chipText, value === o && { color: C.accentInk }]}>{o}</Text>
        </Pressable>
      ))}
    </View>
  );
}

/** Simple area-style bar chart of daily portfolio value (no chart library needed). */
export function ValueChart({ points }: { points: { day: string; value: number }[] }) {
  const pts = points.slice(-60);
  const max = Math.max(...pts.map((p) => p.value), 1);
  const min = Math.min(...pts.map((p) => p.value));
  const lo = min > 0 ? min * 0.9 : 0;
  return (
    <View style={{ gap: 4 }}>
      <View style={st.chart}>
        {pts.map((p, i) => (
          <View key={p.day} style={{ flex: 1, height: `${Math.max(4, ((p.value - lo) / (max - lo || 1)) * 100)}%`, backgroundColor: i === pts.length - 1 ? C.accent : '#7A3A22', borderTopLeftRadius: 2, borderTopRightRadius: 2 }} />
        ))}
      </View>
      <View style={[S.row, { justifyContent: 'space-between' }]}>
        <Text style={S.muted}>{pts[0]?.day}</Text>
        <Text style={S.muted}>{money(max)} high</Text>
        <Text style={S.muted}>{pts[pts.length - 1]?.day}</Text>
      </View>
    </View>
  );
}

export function Header({ title, onBack, right }: { title?: string; onBack?: () => void; right?: React.ReactNode }) {
  return (
    <View style={[S.row, { justifyContent: 'space-between' }]}>
      {onBack ? (
        <Pressable onPress={onBack} hitSlop={12} style={st.back}>
          <Text style={{ color: C.ink, fontWeight: '700', fontSize: 15 }}>‹ Back</Text>
        </Pressable>
      ) : <View />}
      {title ? <Text style={[S.muted, { flex: 1, textAlign: 'center' }]} numberOfLines={1}>{title}</Text> : null}
      {right || <View style={{ width: 60 }} />}
    </View>
  );
}

const st = StyleSheet.create({
  tile: { backgroundColor: C.surface, borderRadius: 12, borderWidth: 1, borderColor: C.line, padding: 6, gap: 3, flex: 1 },
  ph: { aspectRatio: 63 / 88, borderRadius: 7, backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center', padding: 6 },
  phText: { color: C.ink2, fontSize: 11, textAlign: 'center' },
  img: { width: '100%', aspectRatio: 63 / 88, borderRadius: 7 },
  nm: { color: C.ink, fontWeight: '700', fontSize: 12, marginTop: 3 },
  sub: { color: C.ink2, fontSize: 10 },
  px: { color: C.gold, fontWeight: '800', fontSize: 14, fontVariant: ['tabular-nums'] },
  seg: { flexDirection: 'row', backgroundColor: C.surface2, borderRadius: 12, padding: 4, gap: 4 },
  segBtn: { flex: 1, paddingVertical: 9, borderRadius: 9, alignItems: 'center' },
  segOn: { backgroundColor: C.surface },
  segText: { color: C.ink2, fontWeight: '700', fontSize: 13 },
  chart: { height: 110, flexDirection: 'row', alignItems: 'flex-end', gap: 2 },
  back: { paddingVertical: 6, paddingRight: 10 },
});
