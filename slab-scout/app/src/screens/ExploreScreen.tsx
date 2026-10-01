/** Explore: every set and card in the price guide. Discover's search bar opens this with the search box focused. */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FlatList, Image, Pressable, Text, TextInput, View } from 'react-native';
import { C, S } from '../theme';
import { CardTile, Pills, RarityChip, ScreenTitle, TileGrid } from '../components/cards';
import { GradientBorder, Icon } from '../components/visual';
import { useApp } from '../appContext';
import { useLayout } from '../layout';
import { Card, imageUrl, priceIn, printRunLabel, search, searchRemote, sets } from '../core/catalog';

// the last search request from Discover already handled (Explore remounts on every tab switch)
let handledToken = 0;

export default function ExploreScreen({ searchToken = 0 }: { searchToken?: number }) {
  const app = useApp();
  const L = useLayout();
  const [q, setQ] = useState('');
  const [brand, setBrand] = useState('All');
  const [cat, setCat] = useState('All');
  const input = useRef<TextInput>(null);
  useEffect(() => {
    if (!searchToken || searchToken === handledToken) return;
    handledToken = searchToken;
    const t = setTimeout(() => input.current?.focus(), 250);
    return () => clearTimeout(t);
  }, [searchToken]);
  const all = sets();
  const owned = useMemo(() => new Set(app.vault.filter((r) => (r.list || 'collection') === 'collection').map((r) => r.match?.catalog_key || '')), [app.vault]);
  const brands = useMemo(() => ['All', ...[...new Set(Object.values(all).map((s) => s.brand))].sort()], [all]);
  const cats = useMemo(() => ['All', ...[...new Set(Object.values(all).filter((s) => brand === 'All' || s.brand === brand).map((s) => s.category))].sort()], [all, brand]);
  const shown = useMemo(
    () => Object.values(all).filter((s) => (brand === 'All' || s.brand === brand) && (cat === 'All' || s.category === cat)).sort((a, b) => (+b.year || 0) - (+a.year || 0) || b.cards - a.cards),
    [all, brand, cat],
  );
  const [hits, setHits] = useState<Card[]>([]);
  const [searching, setSearching] = useState(false);
  useEffect(() => {
    if (q.trim().length < 2) return setHits([]);
    setHits(search(q, 45)); // bundled cards: instant
    setSearching(true);
    const t = setTimeout(() => {
      searchRemote(q, 45)
        .then(setHits)
        .catch(() => {})
        .finally(() => setSearching(false));
    }, 400);
    return () => clearTimeout(t);
  }, [q]);
  const setHitsList = useMemo(() => {
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length || q.trim().length < 2) return [];
    return Object.values(all).filter((s) => words.every((w) => `${s.name} ${s.year} ${s.brand}`.toLowerCase().includes(w))).slice(0, 12);
  }, [q, all]);
  const searchingNow = q.trim().length >= 2;

  const header = (
    <View style={{ gap: L.sp(14), marginBottom: L.sp(12) }}>
      <ScreenTitle title="Explore" />
      <GradientBorder radius={L.sp(16)} width={1.6} colors={[C.blue, C.purple, C.orange, C.goldBright]}>
        <View style={[S.row, { paddingHorizontal: L.sp(14), height: L.sp(50), gap: 10 }]}>
          <Icon name="search" size={L.fs(19)} color={C.ink2} />
          <TextInput ref={input} style={{ flex: 1, color: C.ink, fontSize: L.fs(15), paddingVertical: 0 }} value={q} onChangeText={setQ} placeholder="Find PSA 10 Charizard, CDT-G-171, Elvis relic…"
            placeholderTextColor={C.ink2} autoCorrect={false} clearButtonMode="while-editing" returnKeyType="search" />
        </View>
      </GradientBorder>
      {searchingNow ? (
        <>
          {setHitsList.length ? (
            <View style={{ gap: 8 }}>
              <Text style={[S.h2, { fontSize: L.fs(19) }]}>Sets</Text>
              {setHitsList.map((s) => (
                <Pressable key={s.id} onPress={() => app.openSet(s.id)} style={({ pressed }) => [S.card, { paddingVertical: L.sp(12), borderRadius: L.sp(18), gap: 2 }, pressed && { opacity: 0.7 }]}>
                  <Text style={{ color: C.ink, fontWeight: '800', fontSize: L.fs(15) }}>{s.name}</Text>
                  <Text style={S.muted}>{s.brand} · {s.category} · {s.cards.toLocaleString()} cards</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
          <Text style={[S.h2, { fontSize: L.fs(19) }]}>Cards</Text>
          <Text style={[S.muted, { marginTop: -L.sp(8) }]}>{hits.length} match{hits.length === 1 ? '' : 'es'}{hits.length === 45 ? ' (top 45)' : ''}{searching ? ' · searching all sets…' : ''}</Text>
          <TileGrid items={hits} keyOf={(c) => c.key}
            render={(c, w) => (
              <CardTile width={w} title={c.name} number={c.number} rarity={c.variant || 'Base'} price={priceIn(c, app.settings.priceMode).text} uri={imageUrl(c)[0] || undefined}
                badge={owned.has(c.key) ? 'Owned' : c.printRun ? printRunLabel(c.printRun) : undefined} onPress={() => app.openCard(c.key)} />
            )} />
        </>
      ) : (
        <>
          <Pills options={brands} value={brand} onChange={(b) => { setBrand(b); setCat('All'); }} />
          {cats.length > 2 ? <Pills options={cats} value={cat} onChange={setCat} /> : null}
          <Text style={[S.muted, { fontSize: L.fs(12) }]}>{shown.length} set{shown.length === 1 ? '' : 's'}</Text>
        </>
      )}
    </View>
  );

  return (
    <FlatList
      style={S.screen}
      contentContainerStyle={{ padding: L.gutter, paddingTop: L.sp(8), gap: L.sp(10), paddingBottom: L.sp(40) }}
      data={searchingNow ? [] : shown}
      keyExtractor={(s) => s.id}
      ListHeaderComponent={header}
      keyboardShouldPersistTaps="handled"
      renderItem={({ item: s }) => {
        const have = [...owned].filter((k) => k.startsWith(s.id + '|')).length;
        const rarest = [...s.tiers].filter((t) => t.print_run).sort((a, b) => a.print_run! - b.print_run!)[0];
        return (
          <Pressable onPress={() => app.openSet(s.id)} style={({ pressed }) => [S.row, { backgroundColor: C.surface, borderRadius: L.sp(20), padding: L.sp(14), gap: L.sp(12), alignItems: 'flex-start' }, pressed && { opacity: 0.75 }]}>
            {s.image ? <Image source={{ uri: s.image }} style={{ width: L.sp(48), height: L.sp(67), borderRadius: 8, backgroundColor: C.surface3 }} resizeMode="cover" /> : null}
            <View style={{ flex: 1, gap: L.sp(6), minWidth: 0 }}>
              <Text style={{ color: C.ink, fontWeight: '800', fontSize: L.fs(16) }}>{s.name}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                <View style={[S.chip, { backgroundColor: C.surface2 }]}><Text style={S.chipText}>{s.brand}</Text></View>
                <View style={[S.chip, { backgroundColor: C.surface2 }]}><Text style={S.chipText}>{s.category}</Text></View>
                <View style={[S.chip, { backgroundColor: C.surface2 }]}><Text style={S.chipText}>{s.cards.toLocaleString()} cards</Text></View>
                {rarest ? <RarityChip printRun={rarest.print_run} /> : null}
                {have ? <View style={[S.chip, { backgroundColor: C.goodSoft }]}><Text style={[S.chipText, { color: C.good }]}>you own {have}</Text></View> : null}
              </View>
              {rarest ? <Text style={[S.muted, { fontSize: L.fs(12) }]}>Rarest: {rarest.name} {printRunLabel(rarest.print_run)}</Text> : null}
            </View>
            <Icon name="forward" size={L.fs(14)} color={C.ink2} />
          </Pressable>
        );
      }}
    />
  );
}
