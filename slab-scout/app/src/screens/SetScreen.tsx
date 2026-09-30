import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Image, Linking, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { C, S, money } from '../theme';
import { Btn } from '../components/ui';
import { ChipRow, Header, RarityChip, Segmented } from '../components/cards';
import { useApp } from '../appContext';
import { loadSet, priceIn, oddsText, printRunLabel, setCards, sets, useCatalogVersion, value } from '../core/catalog';

type Show = 'all' | 'owned' | 'missing' | 'value';

export default function SetScreen({ setId, onBack }: { setId: string; onBack: () => void }) {
  const app = useApp();
  const s = sets()[setId];
  const [q, setQ] = useState('');
  const [tierSel, setTierSel] = useState('All');
  const [show, setShow] = useState<Show>('all');
  const ver = useCatalogVersion();
  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState('');
  useEffect(() => {
    if (!s?.remote) return;
    setLoading(true);
    setLoadErr('');
    loadSet(s.id)
      .catch((e) => setLoadErr(String(e?.message || e)))
      .finally(() => setLoading(false));
  }, [s]);
  const all = useMemo(() => (s ? setCards(s.id) : []), [s, ver]);
  const owned = useMemo(() => new Set(app.vault.filter((r) => (r.list || 'collection') === 'collection').map((r) => r.match?.catalog_key || '')), [app.vault]);
  const have = all.filter((c) => owned.has(c.key)).length;

  const view = useMemo(() => {
    let v = all;
    const ql = q.trim().toLowerCase();
    if (ql) v = v.filter((c) => c.name.toLowerCase().includes(ql) || c.number.toLowerCase().includes(ql));
    if (tierSel !== 'All') v = v.filter((c) => (c.variant || 'Base') === tierSel);
    if (show === 'owned') v = v.filter((c) => owned.has(c.key));
    if (show === 'missing') v = v.filter((c) => !owned.has(c.key));
    if (show === 'value') v = [...v].sort((a, b) => (priceIn(b, app.settings.priceMode).v || 0) - (priceIn(a, app.settings.priceMode).v || 0));
    return v;
  }, [all, q, tierSel, show, owned, app.settings.priceMode]);

  if (!s) return <View style={[S.screen, S.pad]}><Header onBack={onBack} /><Text style={S.body}>Set not found.</Text></View>;

  const header = (
    <View style={{ gap: 12, marginBottom: 10 }}>
      <Header onBack={onBack} title="Set" />
      <Text style={S.h1}>{s.name}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
        {[s.brand, s.category, `${s.cards.toLocaleString()} cards`, s.prices_as_of ? `prices ${s.prices_as_of}` : ''].filter(Boolean).map((x) => (
          <View key={x} style={S.chip}><Text style={S.chipText}>{x}</Text></View>
        ))}
      </View>
      {s.box?.packs_per_box || s.box?.note ? (
        <Text style={S.muted}>{[s.box?.packs_per_box ? `${s.box.packs_per_box} packs × ${s.box.cards_per_pack} cards per box` : '', s.box?.note || ''].filter(Boolean).join(' · ')}</Text>
      ) : null}
      {s.notes ? <Text style={S.muted}>{s.notes}</Text> : null}
      {s.image ? <Image source={{ uri: s.image }} style={{ width: 150, height: 210, borderRadius: 8 }} resizeMode="contain" /> : null}
      {loading ? (
        <View style={[S.row, { gap: 8 }]}><ActivityIndicator color={C.accent} /><Text style={S.muted}>Downloading this set's {s.cards.toLocaleString()} cards…</Text></View>
      ) : null}
      {loadErr ? <Text style={[S.muted, { color: C.crit }]}>{loadErr}. Check your connection and reopen the set.</Text> : null}

      <View style={{ gap: 4 }}>
        <Text style={S.body}>You own {have} of {all.length.toLocaleString()} ({((have / Math.max(1, all.length)) * 100).toFixed(1)}%)</Text>
        <View style={st.bar}><View style={[st.fill, { width: `${(have / Math.max(1, all.length)) * 100}%` }]} /></View>
      </View>

      <Text style={S.h2}>Rarity ladder</Text>
      <View style={S.card}>
        {s.tiers.map((t) => {
          const val = t.ebay_median ? `${money(t.ebay_median)}` : t.median_raw ? money(t.median_raw) : t.estimate ? `${t.estimate} (est.)` : '—';
          const odds = oddsText(t, s);
          return (
            <Pressable key={t.name} onPress={() => setTierSel(tierSel === t.name ? 'All' : t.name)} style={[st.ladderRow, tierSel === t.name && { backgroundColor: C.surface2 }]}>
              <View style={{ flex: 1, gap: 2 }}>
                <View style={[S.row, { gap: 6 }]}>
                  <Text style={[S.body, { fontWeight: '700' }]}>{t.name}</Text>
                  <RarityChip printRun={t.print_run} />
                </View>
                <Text style={S.muted}>{t.count} cards{odds ? ` · ${odds}` : ''}{t.ebay_n ? ` · ${t.ebay_n} eBay sales` : ''}</Text>
              </View>
              <Text style={[S.body, S.mono, { color: C.gold, fontWeight: '800', maxWidth: 130, textAlign: 'right' }]} numberOfLines={2}>{val}</Text>
            </Pressable>
          );
        })}
        {s.estimate_source ? <Text style={S.muted}>(est.) = {s.estimate_source}</Text> : null}
        <Text style={S.muted}>Tap a parallel to filter the checklist.</Text>
      </View>

      <Text style={S.h2}>Checklist</Text>
      <TextInput style={S.input} value={q} onChangeText={setQ} placeholder="Filter by name or number" placeholderTextColor={C.ink2} />
      <Segmented options={[['all', 'All'], ['owned', 'Owned'], ['missing', 'Missing'], ['value', 'Top value']]} value={show} onChange={setShow} />
      {tierSel !== 'All' ? <ChipRow options={['All', tierSel]} value={tierSel} onChange={setTierSel} /> : null}
      <Text style={S.muted}>{view.length.toLocaleString()} cards</Text>
    </View>
  );

  return (
    <FlatList
      style={S.screen}
      contentContainerStyle={[S.pad, { gap: 6, paddingBottom: 40 }]}
      data={view}
      keyExtractor={(c) => c.key}
      ListHeaderComponent={header}
      initialNumToRender={25}
      keyboardShouldPersistTaps="handled"
      ListFooterComponent={<Btn label="Full price guide ↗" onPress={() => Linking.openURL(s.source_url).catch(() => {})} />}
      renderItem={({ item: c }) => {
        const p = priceIn(c, app.settings.priceMode);
        const mine = owned.has(c.key);
        return (
          <Pressable onPress={() => app.openCard(c.key)} style={({ pressed }) => [st.row, pressed && { opacity: 0.7 }]}>
            <Text style={{ width: 18, color: mine ? C.good : C.line, fontWeight: '800' }}>{mine ? '✓' : '○'}</Text>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={[S.body, { fontWeight: '700' }]} numberOfLines={1}>{c.name}</Text>
              <Text style={S.muted} numberOfLines={1}>#{c.number} · {c.variant || 'Base'} {printRunLabel(c.printRun)}</Text>
            </View>
            <Text style={[S.body, S.mono, { fontWeight: '700', color: p.graded ? C.gold : p.text.startsWith('~') ? C.ink2 : C.ink }]}>{p.text}</Text>
          </Pressable>
        );
      }}
    />
  );
}

const st = StyleSheet.create({
  bar: { height: 8, borderRadius: 4, backgroundColor: C.surface2, overflow: 'hidden' },
  fill: { height: 8, backgroundColor: C.accent },
  ladderRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 6, borderBottomWidth: 1, borderBottomColor: C.line, borderRadius: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, borderRadius: 10, padding: 10 },
});
