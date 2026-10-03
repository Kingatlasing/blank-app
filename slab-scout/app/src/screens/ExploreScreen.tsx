/** Explore: every set and card in the price guide. Discover's search bar opens this with the search box focused. */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FlatList, Image, Pressable, Text, TextInput, View } from 'react-native';
import { C, S } from '../theme';
import { CardArt, Pills, RarityChip, ScreenTitle, Segmented, SeriesTile, SetTile, TileGrid } from '../components/cards';
import { GradientBorder, Icon } from '../components/visual';
import { useApp } from '../appContext';
import { useLayout } from '../layout';
import { Card, SetInfo, imageUrl, priceIn, printRunLabel, search, searchRemote, setCover, sets } from '../core/catalog';

// the last search request from Discover already handled (Explore remounts on every tab switch)
let handledToken = 0;

export default function ExploreScreen({ searchToken = 0 }: { searchToken?: number }) {
  const app = useApp();
  const L = useLayout();
  const [q, setQ] = useState('');
  const [brand, setBrand] = useState('All');
  const [cat, setCat] = useState('All');
  // Grouped: one tile per series (Pokémon, Naruto, Basketball…); Expanded: every set
  const [mode, setMode] = useState<'grouped' | 'expanded'>('grouped');
  const input = useRef<TextInput>(null);
  useEffect(() => {
    if (!searchToken || searchToken === handledToken) return;
    handledToken = searchToken;
    const t = setTimeout(() => input.current?.focus(), 250);
    return () => clearTimeout(t);
  }, [searchToken]);
  const all0 = sets();
  // sets with no cards (only sealed boxes on the price guide) aren't worth browsing
  const all = useMemo(() => Object.fromEntries(Object.entries(all0).filter(([, x]) => x.cards > 0)), [all0]);
  const owned = useMemo(() => new Set(app.vault.filter((r) => (r.list || 'collection') === 'collection').map((r) => r.match?.catalog_key || '')), [app.vault]);
  const brands = useMemo(() => ['All', ...[...new Set(Object.values(all).map((s) => s.brand))].sort()], [all]);
  const cats = useMemo(() => ['All', ...[...new Set(Object.values(all).filter((s) => brand === 'All' || s.brand === brand).map((s) => s.category))].sort()], [all, brand]);
  const shown = useMemo(
    () => Object.values(all).filter((s) => (brand === 'All' || s.brand === brand) && (cat === 'All' || s.category === cat)).sort((a, b) => (+b.year || 0) - (+a.year || 0) || b.cards - a.cards),
    [all, brand, cat],
  );
  const groups = useMemo(() => {
    const g: Record<string, SetInfo[]> = {};
    for (const x of Object.values(all)) (g[x.category] ||= []).push(x);
    return Object.entries(g)
      .map(([name, list]) => {
        const brandsBy: Record<string, number> = {};
        for (const x of list) brandsBy[x.brand] = (brandsBy[x.brand] || 0) + 1;
        const topBrands = Object.entries(brandsBy).sort((a, b) => b[1] - a[1]).map(([b]) => b);
        const years = list.map((x) => +x.year).filter(Boolean);
        const coverSet = [...list].filter((x) => x.cover || x.image).sort((a, b) => b.cards - a.cards)[0];
        return {
          name, list, topBrands,
          cards: list.reduce((n, x) => n + x.cards, 0),
          years: years.length ? [Math.min(...years), Math.max(...years)] : null,
          cover: setCover(coverSet),
        };
      })
      .sort((a, b) => b.list.length - a.list.length);
  }, [all]);
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
      <ScreenTitle title={searchingNow ? 'Explore' : 'Card Series'} />
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
                <SetTile key={s.id} title={s.name} cover={setCover(s)} onPress={() => app.openSet(s.id)} meta={`${s.brand} · ${s.category} · ${s.cards.toLocaleString()} cards`} />
              ))}
            </View>
          ) : null}
          <Text style={[S.h2, { fontSize: L.fs(19) }]}>Cards</Text>
          <Text style={[S.muted, { marginTop: -L.sp(8) }]}>{hits.length} match{hits.length === 1 ? '' : 'es'}{hits.length === 45 ? ' (top 45)' : ''}{searching ? ' · searching all sets…' : ''}</Text>
          <TileGrid items={hits} keyOf={(c) => c.key}
            render={(c, w) => (
              <CardArt width={w} title={c.name} number={c.number} rarity={c.variant || 'Base'} printRun={c.printRun} price={priceIn(c, app.settings.priceMode).text} uri={imageUrl(c)[0] || undefined}
                owned={owned.has(c.key)} onPress={() => app.openCard(c.key)} />
            )} />
        </>
      ) : (
        <>
          <Segmented options={[['grouped', 'Grouped'], ['expanded', 'Expanded']]} value={mode} onChange={setMode} />
          {mode === 'expanded' ? (
            <>
              <Pills options={brands} value={brand} onChange={(b) => { setBrand(b); setCat('All'); }} />
              {cats.length > 2 ? <Pills options={cats} value={cat} onChange={setCat} /> : null}
            </>
          ) : null}
          <Text style={[S.muted, { fontSize: L.fs(12) }]}>
            {mode === 'grouped' ? `${groups.length} series · ${Object.keys(all).length.toLocaleString()} sets` : `${shown.length.toLocaleString()} set${shown.length === 1 ? '' : 's'}`}
          </Text>
        </>
      )}
    </View>
  );

  const openSeries = (name: string, b = 'All') => {
    setBrand(b);
    setCat(name);
    setMode('expanded');
  };
  type Row = { kind: 'series'; g: (typeof groups)[number] } | { kind: 'set'; s: SetInfo };
  const data: Row[] = searchingNow ? [] : mode === 'grouped' ? groups.map((g) => ({ kind: 'series', g })) : shown.map((x) => ({ kind: 'set', s: x }));

  return (
    <FlatList
      style={S.screen}
      contentContainerStyle={{ padding: L.gutter, paddingTop: L.sp(8), gap: L.sp(10), paddingBottom: L.sp(40) }}
      data={data}
      keyExtractor={(r) => (r.kind === 'series' ? `g:${r.g.name}` : r.s.id)}
      ListHeaderComponent={header}
      keyboardShouldPersistTaps="handled"
      initialNumToRender={12}
      renderItem={({ item: r }) => {
        if (r.kind === 'series') {
          const g = r.g;
          const yrs = g.years ? (g.years[0] === g.years[1] ? `${g.years[0]}` : `${g.years[0]}–${g.years[1]}`) : '';
          return (
            <SeriesTile title={g.name} cover={g.cover}
              meta={`${g.list.length.toLocaleString()} sets · ${g.topBrands.slice(0, 2).join(', ')}`}
              about={[`${g.cards.toLocaleString()} cards`, yrs].filter(Boolean).join(' · ')}
              chips={g.topBrands.length > 1 ? g.topBrands.slice(0, 6) : undefined}
              onPress={() => openSeries(g.name)} onChip={(b) => openSeries(g.name, b)} />
          );
        }
        const s = r.s;
        const have = [...owned].filter((k) => k.startsWith(s.id + '|')).length;
        const rarest = [...s.tiers].filter((t) => t.print_run).sort((a, b) => a.print_run! - b.print_run!)[0];
        return (
          <SetTile title={s.name} cover={setCover(s)} owned={have} onPress={() => app.openSet(s.id)}
            meta={[s.year, s.brand, `${s.cards.toLocaleString()} cards`].filter(Boolean).join(' · ')}
            chips={rarest ? <><RarityChip printRun={rarest.print_run} /><Text style={[S.muted, { fontSize: L.fs(11.5) }]} numberOfLines={1}>{rarest.name}</Text></> : null} />
        );
      }}
    />
  );
}
