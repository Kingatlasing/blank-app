/** Building blocks: card tiles, grids, carousels, pills, segmented / underline tabs, value chart, headers. */
import React from 'react';
import { Image, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleProp, StyleSheet, Text, TextInput, View, ViewStyle } from 'react-native';
import { C, R, S, money } from '../theme';
import { useLayout } from '../layout';
import { AreaChart, Icon, IconName } from './visual';

export function RarityChip({ printRun }: { printRun?: number | null }) {
  if (!printRun) return null;
  const hot = printRun <= 5;
  const warm = printRun <= 25;
  return (
    <View style={[S.chip, { alignSelf: 'flex-start', backgroundColor: hot ? C.critSoft : warm ? C.goldSoft : C.surface2 }]}>
      <Text style={[S.chipText, { color: hot ? C.crit : warm ? C.gold : C.ink }]}>{printRun === 1 ? '1 of 1' : `/${printRun}`}</Text>
    </View>
  );
}

export function Tile({ title, sub, price, thumb, uri, printRun, onPress, badge, change, width }: { title: string; sub?: string; price: string; thumb?: string; uri?: string; printRun?: number | null; onPress?: () => void; badge?: string; change?: { text: string; up: boolean }; width?: number }) {
  const L = useLayout();
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [st.tile, width ? { width } : { flex: 1 }, pressed && { opacity: 0.75 }]}>
      <View style={st.imgWrap}>
        {uri || thumb ? (
          <Image source={{ uri: uri || `data:image/jpeg;base64,${thumb}` }} style={[st.img, { resizeMode: 'contain' }]} />
        ) : (
          <View style={st.ph}>
            <Text style={st.phText} numberOfLines={3}>{title}</Text>
          </View>
        )}
        {change ? (
          <View style={[st.badge, { backgroundColor: change.up ? C.goodSoft : C.critSoft }]}>
            <Text style={{ color: change.up ? C.good : C.crit, fontWeight: '800', fontSize: L.fs(11) }}>{change.up ? '▲' : '▼'} {change.text}</Text>
          </View>
        ) : null}
      </View>
      <Text style={[st.nm, { fontSize: L.fs(13) }]} numberOfLines={2}>{title}</Text>
      {sub ? <Text style={[st.sub, { fontSize: L.fs(11) }]} numberOfLines={1}>{sub}</Text> : null}
      {printRun || badge ? (
        <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap' }}>
          <RarityChip printRun={printRun} />
          {badge ? <View style={S.chip}><Text style={S.chipText}>{badge}</Text></View> : null}
        </View>
      ) : null}
      <Text style={[st.px, { fontSize: L.fs(15) }]} numberOfLines={1}>{price}</Text>
    </Pressable>
  );
}

/** Lays children out in rows, like a binder page. Columns follow the screen width unless given. */
export function Grid({ children, cols }: { children: React.ReactNode; cols?: number }) {
  const L = useLayout();
  const n = cols || L.cols;
  const gap = L.sp(10);
  const items = React.Children.toArray(children);
  const rows: React.ReactNode[][] = [];
  for (let i = 0; i < items.length; i += n) rows.push(items.slice(i, i + n));
  return (
    <View style={{ gap }}>
      {rows.map((r, i) => (
        <View key={i} style={{ flexDirection: 'row', gap }}>
          {r.map((c, j) => (
            <View key={j} style={{ flex: 1 }}>{c}</View>
          ))}
          {Array.from({ length: n - r.length }).map((_, j) => (
            <View key={`e${j}`} style={{ flex: 1 }} />
          ))}
        </View>
      ))}
    </View>
  );
}

/** Horizontal carousel that bleeds to the screen edge. */
export function Carousel({ children }: { children: React.ReactNode }) {
  const L = useLayout();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -L.gutter }} contentContainerStyle={{ paddingHorizontal: L.gutter, gap: L.sp(12) }}>
      {children}
    </ScrollView>
  );
}

export function SectionTitle({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  const L = useLayout();
  return (
    <View style={[S.row, { justifyContent: 'space-between', marginTop: L.sp(6) }]}>
      <Text style={[S.h2, { fontSize: L.fs(20) }]}>{title}</Text>
      {action ? (
        <Pressable onPress={onAction} hitSlop={10} style={[S.row, { gap: 2 }]}>
          <Text style={{ color: C.ink2, fontWeight: '700', fontSize: L.fs(14) }}>{action}</Text>
          <Icon name="forward" size={L.fs(14)} color={C.ink2} />
        </Pressable>
      ) : null}
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

/** Text tabs with an underline under the selected one. */
export function UnderlineTabs<T extends string>({ options, value, onChange }: { options: [T, string][]; value: T; onChange: (v: T) => void }) {
  const L = useLayout();
  return (
    <View style={st.utabs}>
      {options.map(([id, label]) => {
        const on = value === id;
        return (
          <Pressable key={id} style={st.utab} onPress={() => onChange(id)}>
            <Text style={{ color: on ? C.ink : C.ink2, fontWeight: on ? '800' : '600', fontSize: L.fs(15) }} numberOfLines={1}>{label}</Text>
            <View style={[st.uline, on && { backgroundColor: C.ink }]} />
          </Pressable>
        );
      })}
    </View>
  );
}

/** Rounded filter pills; the selected one is bright indigo. Scrolls sideways when it overflows. */
export function Pills<T extends string>({ options, value, onChange, labels, wrap }: { options: T[]; value: T; onChange: (v: T) => void; labels?: Record<string, string>; wrap?: boolean }) {
  const L = useLayout();
  const body = options.map((o) => {
    const on = value === o;
    return (
      <Pressable key={o} onPress={() => onChange(o)} style={[S.pill, { paddingVertical: L.sp(8), paddingHorizontal: L.sp(15) }, on && S.pillOn]}>
        <Text style={[S.pillText, { fontSize: L.fs(14) }, on && { color: '#fff' }]}>{labels?.[o] || o}</Text>
      </Pressable>
    );
  });
  if (wrap) return <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{body}</View>;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -L.gutter, flexGrow: 0 }} contentContainerStyle={{ paddingHorizontal: L.gutter, gap: 8 }}>
      {body}
    </ScrollView>
  );
}

/** Small chips that wrap (used inside panels); selected = indigo. */
export function ChipRow<T extends string>({ options, value, onChange }: { options: T[]; value: T; onChange: (v: T) => void }) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
      {options.map((o) => (
        <Pressable key={o} onPress={() => onChange(o)} style={[S.chip, { paddingVertical: 7, paddingHorizontal: 13 }, value === o && { backgroundColor: C.blue }]}>
          <Text style={[S.chipText, value === o && { color: '#fff' }]}>{o}</Text>
        </Pressable>
      ))}
    </View>
  );
}

/** Daily collection value: smooth filled area chart with gridlines and dates. */
export function ValueChart({ points, height }: { points: { day: string; value: number }[]; height?: number }) {
  const L = useLayout();
  const pts = points.slice(-120);
  return <AreaChart points={pts} height={height || L.sp(200)} color={C.good} lineColor="#B9F5CF" fillTop={0.38} />;
}

export function IconBtn({ name, onPress, size, style, color, label }: { name: IconName; onPress?: () => void; size?: number; style?: StyleProp<ViewStyle>; color?: string; label?: string }) {
  const L = useLayout();
  const d = size || L.sp(40);
  return (
    <Pressable onPress={onPress} hitSlop={8} accessibilityLabel={label || name} style={({ pressed }) => [{ width: d, height: d, borderRadius: d / 2, backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, alignItems: 'center', justifyContent: 'center' }, pressed && { opacity: 0.7 }, style]}>
      <Icon name={name} size={d * 0.48} color={color || C.ink} />
    </Pressable>
  );
}

/** Page header: round back chevron, centred title, optional right content. */
export function Header({ title, onBack, right }: { title?: string; onBack?: () => void; right?: React.ReactNode }) {
  const L = useLayout();
  return (
    <View style={[S.row, { justifyContent: 'space-between', minHeight: L.sp(44) }]}>
      {onBack ? <IconBtn name="back" onPress={onBack} label="Back" /> : <View style={{ width: L.sp(40) }} />}
      {title ? <Text style={{ flex: 1, textAlign: 'center', color: C.ink, fontWeight: '800', fontSize: L.fs(16) }} numberOfLines={1}>{title}</Text> : <View style={{ flex: 1 }} />}
      {right || <View style={{ width: L.sp(40) }} />}
    </View>
  );
}

/** Big bold screen title with optional icons on the right. */
export function ScreenTitle({ title, right }: { title: string; right?: React.ReactNode }) {
  const L = useLayout();
  return (
    <View style={[S.row, { justifyContent: 'space-between', paddingTop: L.sp(6) }]}>
      <Text style={[S.h1, { fontSize: L.fs(30) }]} numberOfLines={1}>{title}</Text>
      {right ? <View style={[S.row, { gap: 8 }]}>{right}</View> : null}
    </View>
  );
}

export function Stat({ value, label, color }: { value: string; label: string; color?: string }) {
  const L = useLayout();
  return (
    <View style={{ flex: 1, alignItems: 'center', gap: 2 }}>
      <Text style={[{ color: color || C.ink, fontSize: L.fs(18), fontWeight: '800' }, S.mono]} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
      <Text style={{ color: C.ink2, fontSize: L.fs(12), fontWeight: '600' }} numberOfLines={1}>{label}</Text>
    </View>
  );
}

/** Collection-grid tile: the official card photo, then "name #num" + lime price, then "#num R" + quantity. */
export function CardTile({ title, number, rarity, price, uri, thumb, qty, width, onPress, onLongPress, badge, selected }: {
  title: string; number?: string; rarity?: string; price: string; uri?: string; thumb?: string; qty?: number; width?: number;
  onPress?: () => void; onLongPress?: () => void; badge?: string; selected?: boolean;
}) {
  const L = useLayout();
  const num = number ? `#${String(number).replace(/^#/, '')}` : '';
  const ri = (rarity || '').trim().charAt(0).toUpperCase();
  return (
    <Pressable onPress={onPress} onLongPress={onLongPress} delayLongPress={350} style={({ pressed }) => [width ? { width } : { flex: 1 }, pressed && { opacity: 0.75 }]}>
      <View style={[st.cimg, selected && { borderColor: C.blue, borderWidth: 2 }]}>
        {uri || thumb ? (
          <Image source={{ uri: uri || `data:image/jpeg;base64,${thumb}` }} style={[st.img, { resizeMode: 'cover' }]} />
        ) : (
          <View style={st.ph}><Text style={st.phText} numberOfLines={3}>{title}</Text></View>
        )}
        {badge ? (
          <View style={st.darkPill}><Text style={{ color: '#fff', fontSize: L.fs(10), fontWeight: '800' }} numberOfLines={1}>{badge}</Text></View>
        ) : null}
        {selected ? (
          <View style={st.check}><Icon name="check" size={L.fs(14)} color="#fff" /></View>
        ) : null}
      </View>
      <View style={[S.row, { gap: 4, marginTop: L.sp(6) }]}>
        <Text style={{ flex: 1, color: C.ink, fontWeight: '800', fontSize: L.fs(12.5) }} numberOfLines={1}>{title}{num ? ` ${num}` : ''}</Text>
        <Text style={{ color: C.lime, fontWeight: '800', fontSize: L.fs(12.5), fontVariant: ['tabular-nums'] }} numberOfLines={1}>{price}</Text>
      </View>
      <View style={[S.row, { gap: 4, marginTop: 2 }]}>
        <Text style={{ flex: 1, color: C.ink2, fontSize: L.fs(11), fontWeight: '600' }} numberOfLines={1}>{[num, ri].filter(Boolean).join(' ') || ' '}</Text>
        {qty ? (
          <View style={[S.row, { gap: 3 }]}>
            <Icon name="cards" size={L.fs(12)} color={C.ink2} stroke={1.3} />
            <Text style={{ color: C.ink2, fontSize: L.fs(11), fontWeight: '700' }}>{qty}</Text>
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

/** Lays out tiles of a fixed width in rows (no flex stretching), `cols` per row. */
export function TileGrid<T>({ items, cols, render, keyOf, innerW }: { items: T[]; cols?: number; render: (item: T, w: number) => React.ReactNode; keyOf: (item: T) => string; innerW?: number }) {
  const L = useLayout();
  const n = cols || L.cols;
  const gap = L.sp(10);
  // innerW: the width the grid gets when it isn't the full content column (e.g. inside a sheet on iPad)
  const w = innerW ? Math.floor((innerW - gap * (n - 1)) / n) : L.tileW(n, gap);
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', columnGap: gap, rowGap: L.sp(16) }}>
      {items.map((it) => <View key={keyOf(it)} style={{ width: w }}>{render(it, w)}</View>)}
    </View>
  );
}

/** Square icon button (search-row sort / filter buttons). */
export function SquareBtn({ name, onPress, on, label }: { name: IconName; onPress?: () => void; on?: boolean; label?: string }) {
  const L = useLayout();
  const d = L.sp(44);
  return (
    <Pressable onPress={onPress} accessibilityLabel={label || name} hitSlop={4} style={({ pressed }) => [{ width: d, height: d, borderRadius: L.sp(12), backgroundColor: on ? C.blue : C.surface, borderWidth: 1, borderColor: on ? C.blue : C.line, alignItems: 'center', justifyContent: 'center' }, pressed && { opacity: 0.7 }]}>
      <Icon name={name} size={L.fs(20)} color={C.ink} />
    </Pressable>
  );
}

/** Search field with a magnifier (dark slate, rounded). */
export function SearchField({ value, onChangeText, placeholder, autoFocus, style }: { value: string; onChangeText: (v: string) => void; placeholder: string; autoFocus?: boolean; style?: StyleProp<ViewStyle> }) {
  const L = useLayout();
  return (
    <View style={[S.row, { flex: 1, gap: 8, backgroundColor: C.surface, borderRadius: L.sp(12), borderWidth: 1, borderColor: C.line, paddingHorizontal: L.sp(12), height: L.sp(44) }, style]}>
      <Icon name="search" size={L.fs(18)} color={C.ink2} />
      <TextInput value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor={C.ink2} autoFocus={autoFocus} autoCorrect={false} clearButtonMode="while-editing"
        style={{ flex: 1, color: C.ink, fontSize: L.fs(15), paddingVertical: 0 }} />
    </View>
  );
}

/** Bottom sheet: dark, rounded top corners, close × top-right. Width follows the content column on tablets. */
export function Sheet({ visible, onClose, title, children, scroll = true }: { visible: boolean; onClose: () => void; title?: string; children: React.ReactNode; scroll?: boolean }) {
  const L = useLayout();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, justifyContent: 'flex-end' }}>
        <Pressable style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(0,0,0,0.55)' }]} onPress={onClose} />
        <View style={{ width: '100%', maxWidth: L.tablet ? Math.min(L.maxW, 640) : undefined, alignSelf: 'center', maxHeight: L.height * 0.88, backgroundColor: C.surface, borderTopLeftRadius: L.sp(24), borderTopRightRadius: L.sp(24), borderWidth: 1, borderBottomWidth: 0, borderColor: C.line, paddingBottom: Math.max(L.bottom, 12) }}>
          <View style={{ alignItems: 'center', paddingTop: 8 }}><View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: C.line }} /></View>
          <View style={[S.row, { paddingHorizontal: L.gutter, paddingTop: L.sp(8), paddingBottom: L.sp(4), minHeight: L.sp(40) }]}>
            <Text style={{ flex: 1, color: C.ink, fontWeight: '800', fontSize: L.fs(19) }} numberOfLines={1}>{title || ''}</Text>
            <Pressable onPress={onClose} hitSlop={10} accessibilityLabel="Close" style={{ width: L.sp(32), height: L.sp(32), borderRadius: L.sp(16), backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center' }}>
              <Icon name="close" size={L.fs(14)} color={C.ink} />
            </Pressable>
          </View>
          {scroll ? (
            <ScrollView contentContainerStyle={{ paddingHorizontal: L.gutter, paddingTop: L.sp(8), paddingBottom: L.sp(12), gap: L.sp(14) }} keyboardShouldPersistTaps="handled">{children}</ScrollView>
          ) : (
            <View style={{ paddingHorizontal: L.gutter, paddingTop: L.sp(8), paddingBottom: L.sp(12), gap: L.sp(14) }}>{children}</View>
          )}
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

/** Row of options inside a sheet; the selected one gets a check. */
export function SheetOption({ label, sub, on, onPress, right }: { label: string; sub?: string; on?: boolean; onPress: () => void; right?: React.ReactNode }) {
  const L = useLayout();
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [S.row, { paddingVertical: L.sp(12), paddingHorizontal: L.sp(14), borderRadius: L.sp(14), backgroundColor: on ? C.indigoDeep : C.surface2 }, pressed && { opacity: 0.75 }]}>
      <View style={{ flex: 1 }}>
        <Text style={{ color: C.ink, fontWeight: '700', fontSize: L.fs(15) }}>{label}</Text>
        {sub ? <Text style={{ color: C.ink2, fontSize: L.fs(12) }}>{sub}</Text> : null}
      </View>
      {right}
      {on ? <Icon name="check" size={L.fs(16)} color={C.ink} /> : null}
    </Pressable>
  );
}

/** Green ▲ / red ▼ change pill: "▲ $124.95 (3.2%) this week". */
export function ChangeChip({ abs, pct, label }: { abs: number; pct: number; label: string }) {
  const L = useLayout();
  const up = abs >= 0;
  const col = up ? C.good : C.crit;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 999, paddingHorizontal: L.sp(12), paddingVertical: L.sp(7), backgroundColor: up ? C.goodSoft : C.critSoft }}>
      <Text style={{ color: col, fontWeight: '800', fontSize: L.fs(13), fontVariant: ['tabular-nums'] }}>{up ? '▲' : '▼'} {money(Math.abs(abs))} ({Math.abs(pct) < 0.05 ? '0' : Math.abs(pct).toFixed(Math.abs(pct) >= 10 ? 0 : 2)}%)</Text>
      <Text style={{ color: C.ink2, fontWeight: '600', fontSize: L.fs(13) }}>{label}</Text>
    </View>
  );
}


export { money };

const st = StyleSheet.create({
  tile: { backgroundColor: C.surface, borderRadius: R.lg - 2, padding: 8, gap: 3 },
  imgWrap: { borderRadius: 10, overflow: 'hidden', backgroundColor: C.surface3 },
  ph: { aspectRatio: 63 / 88, alignItems: 'center', justifyContent: 'center', padding: 6 },
  phText: { color: C.ink2, fontSize: 11, textAlign: 'center' },
  img: { width: '100%', aspectRatio: 63 / 88 },
  cimg: { borderRadius: 10, overflow: 'hidden', backgroundColor: C.surface3, borderWidth: 1, borderColor: C.lineSoft },
  darkPill: { position: 'absolute', right: 6, top: 6, borderRadius: 999, paddingHorizontal: 7, paddingVertical: 3, backgroundColor: 'rgba(10,11,16,0.86)' },
  check: { position: 'absolute', right: 6, top: 6, width: 24, height: 24, borderRadius: 12, backgroundColor: C.blue, alignItems: 'center', justifyContent: 'center' },
  badge: { position: 'absolute', left: 6, top: 6, borderRadius: R.pill, paddingHorizontal: 7, paddingVertical: 3 },
  nm: { color: C.ink, fontWeight: '700', marginTop: 5 },
  sub: { color: C.ink2 },
  px: { color: C.gold, fontWeight: '800', fontVariant: ['tabular-nums'], marginTop: 2 },
  seg: { flexDirection: 'row', backgroundColor: C.surface, borderRadius: R.md, padding: 4, gap: 4, borderWidth: 1, borderColor: C.line },
  segBtn: { flex: 1, paddingVertical: 9, borderRadius: 10, alignItems: 'center' },
  segOn: { backgroundColor: C.blue },
  segText: { color: C.ink2, fontWeight: '700', fontSize: 13 },
  utabs: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.line },
  utab: { flex: 1, alignItems: 'center', paddingTop: 10, gap: 9 },
  uline: { height: 3, borderRadius: 2, alignSelf: 'stretch', marginHorizontal: 10, backgroundColor: 'transparent', marginBottom: -1 },
});
