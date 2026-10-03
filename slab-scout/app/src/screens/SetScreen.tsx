import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Image, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { C, S, money } from '../theme';
import { Btn } from '../components/ui';
import { CardArt, ChipRow, Header, Pills, RarityChip, SearchField, Segmented, SquareBtn, rarityTint } from '../components/cards';
import { useLayout } from '../layout';
import { useApp } from '../appContext';
import { imageUrl, loadSet, priceIn, oddsText, printRunLabel, setCards, setCover, sets, useCatalogVersion, value } from '../core/catalog';

type Show = 'all' | 'owned' | 'missing' | 'value';

export default function SetScreen({ setId, onBack }: { setId: string; onBack: () => void }) {
  const app = useApp();
  const L = useLayout();
  const s = sets()[setId];
  const [q, setQ] = useState('');
  const [tierSel, setTierSel] = useState('All');
  const [show, setShow] = useState<Show>('all');
  const [tab, setTab] = useState<'cards' | 'about'>('cards');
  const [grid, setGrid] = useState(true);
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

  const pct = (have / Math.max(1, all.length)) * 100;
  const cover = setCover(s, 240);
  const cols = L.cols;
  const gap = L.sp(10);
  const tileW = L.tileW(cols, gap);

  const about = (
    <View style={{ gap: L.sp(12) }}>
      <View style={{ gap: 8, backgroundColor: C.hero, borderRadius: L.sp(20), padding: L.sp(16), borderWidth: 1, borderColor: '#2B3070' }}>
        <View style={[S.row, { justifyContent: 'space-between', alignItems: 'flex-end' }]}>
          <View>
            <Text style={{ color: '#C9CCF5', fontWeight: '700', fontSize: L.fs(13) }}>Your progress</Text>
            <Text style={{ color: C.ink, fontWeight: '900', fontSize: L.fs(26), fontVariant: ['tabular-nums'] }}>{have} <Text style={{ color: C.ink2, fontSize: L.fs(16) }}>/ {all.length.toLocaleString()}</Text></Text>
          </View>
          <Text style={{ color: C.lime, fontWeight: '900', fontSize: L.fs(20), fontVariant: ['tabular-nums'] }}>{pct.toFixed(1)}%</Text>
        </View>
        <View style={st.bar}><View style={[st.fill, { width: `${pct}%` }]} /></View>
      </View>
      {s.box?.packs_per_box || s.box?.note || s.notes ? (
        <View style={[S.card, { borderRadius: L.sp(18) }]}>
          {s.box?.packs_per_box || s.box?.note ? (
            <Text style={S.body}>{[s.box?.packs_per_box ? `${s.box.packs_per_box} packs × ${s.box.cards_per_pack} cards per box` : '', s.box?.note || ''].filter(Boolean).join(' · ')}</Text>
          ) : null}
          {s.notes ? <Text style={S.muted}>{s.notes}</Text> : null}
        </View>
      ) : null}
      <Text style={[S.h2, { fontSize: L.fs(20) }]}>Rarity ladder</Text>
      <View style={[S.card, { borderRadius: L.sp(20) }]}>
        {s.tiers.map((t) => {
          const val = t.ebay_median ? `${money(t.ebay_median)}` : t.median_raw ? money(t.median_raw) : t.estimate ? `${t.estimate} (est.)` : '—';
          const odds = oddsText(t, s);
          return (
            <Pressable key={t.name} onPress={() => { setTierSel(t.name); setTab('cards'); }} style={st.ladderRow}>
              <View style={{ width: 4, alignSelf: 'stretch', borderRadius: 2, backgroundColor: rarityTint(t.name, t.print_run) }} />
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
        <Text style={S.muted}>Tap a parallel to see its cards.</Text>
      </View>
      <Btn label="Full price guide ↗" onPress={() => Linking.openURL(s.source_url).catch(() => {})} />
    </View>
  );

  const header = (
    <View style={{ gap: L.sp(12), marginBottom: L.sp(10) }}>
      <Header onBack={onBack} title={s.category} />
      <View style={[st.panel, { borderRadius: L.sp(20), padding: L.sp(14), gap: L.sp(10) }]}>
        <View style={[S.row, { gap: L.sp(14), alignItems: 'flex-start' }]}>
          <View style={{ width: L.sp(84), height: L.sp(118), borderRadius: L.sp(12), backgroundColor: C.surface3, overflow: 'hidden', borderWidth: 1, borderColor: C.line }}>
            {cover ? <Image source={{ uri: cover }} style={{ width: '100%', height: '100%' }} resizeMode="cover" /> : null}
          </View>
          <View style={{ flex: 1, minWidth: 0, gap: 4 }}>
            <Text style={{ color: C.ink3, fontSize: L.fs(11.5), fontWeight: '700' }} numberOfLines={1}>All sets / {s.category}</Text>
            <Text style={{ color: C.ink, fontWeight: '900', fontSize: L.fs(22), letterSpacing: -0.3 }} numberOfLines={3}>{s.name}</Text>
            <Text style={{ color: C.ink2, fontSize: L.fs(12.5) }} numberOfLines={2}>{s.cards.toLocaleString()} cards · {s.tiers.length} {s.tiers.length === 1 ? 'parallel' : 'parallels / rarities'}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {[s.brand, s.year ? `Released ${s.year}` : 'Release date unknown', s.prices_as_of ? `Prices ${s.prices_as_of}` : '', have ? `You own ${have}` : ''].filter(Boolean).map((x) => (
            <View key={x} style={[S.chip, { borderRadius: 8, paddingVertical: 5 }]}><Text style={S.chipText}>{x}</Text></View>
          ))}
        </View>
        {have ? <View style={st.bar}><View style={[st.fill, { width: `${pct}%` }]} /></View> : null}
      </View>
      {loading ? (
        <View style={[S.row, { gap: 8 }]}><ActivityIndicator color={C.accent} /><Text style={S.muted}>Downloading this set's {s.cards.toLocaleString()} cards…</Text></View>
      ) : null}
      {loadErr ? <Text style={[S.muted, { color: C.crit }]}>{loadErr}. Check your connection and reopen the set.</Text> : null}

      <Segmented options={[['cards', 'Cardlist'], ['about', 'About the set']]} value={tab} onChange={setTab} />
      {tab === 'about' ? about : (
        <>
          <View style={[S.row, { gap: 8 }]}>
            <SearchField value={q} onChangeText={setQ} placeholder="Character, name or card number…" />
            <SquareBtn name={grid ? 'list' : 'grid'} onPress={() => setGrid(!grid)} label={grid ? 'List view' : 'Picture view'} />
          </View>
          <Pills options={['all', 'owned', 'missing', 'value'] as Show[]} labels={{ all: 'All', owned: 'Owned', missing: 'Missing', value: 'Top value' }} value={show} onChange={setShow} />
          {s.tiers.length > 1 ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -L.gutter, flexGrow: 0 }} contentContainerStyle={{ paddingHorizontal: L.gutter, gap: 6 }}>
              {['All', ...s.tiers.map((t) => t.name)].map((t) => {
                const on = tierSel === t;
                const tier = s.tiers.find((x) => x.name === t);
                const tint = t === 'All' ? C.blue : rarityTint(t, tier?.print_run);
                return (
                  <Pressable key={t} onPress={() => setTierSel(t)} style={{ borderRadius: 8, borderWidth: 1, borderColor: on ? tint : C.line, backgroundColor: on ? tint + '33' : C.surface, paddingHorizontal: 10, paddingVertical: 6 }}>
                    <Text style={{ color: on ? C.ink : C.ink2, fontWeight: '800', fontSize: L.fs(12) }}>{t}{tier?.print_run ? ` /${tier.print_run}` : ''}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
          ) : null}
          <Text style={S.muted}>{view.length.toLocaleString()} cards</Text>
        </>
      )}
    </View>
  );

  const showCards = tab === 'cards';
  if (grid && showCards) {
    return (
      <FlatList
        key={`g${cols}`}
        style={S.screen}
        contentContainerStyle={{ padding: L.gutter, paddingTop: L.sp(6), paddingBottom: L.sp(40), rowGap: L.sp(14) }}
        columnWrapperStyle={{ columnGap: gap }}
        numColumns={cols}
        data={view}
        keyExtractor={(c) => c.key}
        ListHeaderComponent={header}
        initialNumToRender={18}
        windowSize={7}
        keyboardShouldPersistTaps="handled"
        renderItem={({ item: c }) => (
          <CardArt width={tileW} title={c.name} number={c.number} rarity={c.variant || 'Base'} printRun={c.printRun} price={priceIn(c, app.settings.priceMode).text}
            uri={imageUrl(c)[0] || undefined} owned={owned.has(c.key)} onPress={() => app.openCard(c.key)} />
        )}
      />
    );
  }

  return (
    <FlatList
      key="list"
      style={S.screen}
      contentContainerStyle={{ padding: L.gutter, paddingTop: L.sp(6), gap: L.sp(6), paddingBottom: L.sp(40) }}
      data={showCards ? view : []}
      keyExtractor={(c) => c.key}
      ListHeaderComponent={header}
      initialNumToRender={25}
      keyboardShouldPersistTaps="handled"
      renderItem={({ item: c }) => {
        const p = priceIn(c, app.settings.priceMode);
        const mine = owned.has(c.key);
        return (
          <Pressable onPress={() => app.openCard(c.key)} style={({ pressed }) => [st.row, { borderLeftWidth: 3, borderLeftColor: rarityTint(c.variant, c.printRun) }, pressed && { opacity: 0.7 }]}>
            <View style={{ width: L.sp(22), height: L.sp(22), borderRadius: L.sp(11), borderWidth: 2, borderColor: mine ? C.good : C.line, backgroundColor: mine ? C.good : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
              {mine ? <Text style={{ color: C.bg, fontWeight: '900', fontSize: L.fs(12) }}>✓</Text> : null}
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={[S.body, { fontWeight: '700' }]} numberOfLines={1}>{c.name}</Text>
              <Text style={S.muted} numberOfLines={1}>#{c.number} · {c.variant || 'Base'} {printRunLabel(c.printRun)}</Text>
            </View>
            <Text style={[S.body, S.mono, { fontWeight: '800', color: p.text.startsWith('~') || p.text === '—' ? C.ink2 : C.lime }]}>{p.text}</Text>
          </Pressable>
        );
      }}
    />
  );
}

const st = StyleSheet.create({
  panel: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.lineSoft },
  bar: { height: 8, borderRadius: 4, backgroundColor: C.surface2, overflow: 'hidden' },
  fill: { height: 8, backgroundColor: C.lime },
  ladderRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 6, borderBottomWidth: 1, borderBottomColor: C.line, borderRadius: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.surface, borderRadius: 16, paddingVertical: 12, paddingHorizontal: 14 },
});
