import React, { useMemo, useState } from 'react';
import { FlatList, Pressable, Text, TextInput, View } from 'react-native';
import { C, S } from '../theme';
import { ChipRow, Grid, RarityChip, Tile } from '../components/cards';
import { useApp } from '../appContext';
import { printRunLabel, search, sets, value } from '../core/catalog';
import { money } from '../theme';

export default function ExploreScreen() {
  const app = useApp();
  const [q, setQ] = useState('');
  const [brand, setBrand] = useState('All');
  const [cat, setCat] = useState('All');
  const all = sets();
  const owned = useMemo(() => new Set(app.vault.filter((r) => (r.list || 'collection') === 'collection').map((r) => r.match?.catalog_key || '')), [app.vault]);
  const brands = useMemo(() => ['All', ...[...new Set(Object.values(all).map((s) => s.brand))].sort()], [all]);
  const cats = useMemo(() => ['All', ...[...new Set(Object.values(all).filter((s) => brand === 'All' || s.brand === brand).map((s) => s.category))].sort()], [all, brand]);
  const shown = useMemo(
    () => Object.values(all).filter((s) => (brand === 'All' || s.brand === brand) && (cat === 'All' || s.category === cat)).sort((a, b) => (+b.year || 0) - (+a.year || 0) || b.cards - a.cards),
    [all, brand, cat],
  );
  const hits = useMemo(() => (q.trim().length >= 2 ? search(q, 45) : []), [q]);

  const header = (
    <View style={{ gap: 12, marginBottom: 12 }}>
      <TextInput style={S.input} value={q} onChangeText={setQ} placeholder="Search: Stitch black gold, CDT-G-171, Elvis relic…" placeholderTextColor={C.ink2} autoCorrect={false} clearButtonMode="while-editing" />
      {q.trim().length >= 2 ? (
        <>
          <Text style={S.muted}>{hits.length} match{hits.length === 1 ? '' : 'es'}{hits.length === 45 ? ' (top 45)' : ''}</Text>
          <Grid>
            {hits.map((c) => {
              const [v, est] = value(c);
              return <Tile key={c.key} title={c.name} sub={`${all[c.setId]?.name || ''} · ${c.variant || 'Base'} · #${c.number}`} price={v ? `${est ? '~' : ''}${money(v)}` : '—'} printRun={c.printRun} onPress={() => app.openCard(c.key)} />;
            })}
          </Grid>
        </>
      ) : (
        <>
          <ChipRow options={brands} value={brand} onChange={(b) => { setBrand(b); setCat('All'); }} />
          {cats.length > 2 ? <ChipRow options={cats} value={cat} onChange={setCat} /> : null}
        </>
      )}
    </View>
  );

  return (
    <FlatList
      style={S.screen}
      contentContainerStyle={[S.pad, { gap: 8, paddingBottom: 40 }]}
      data={q.trim().length >= 2 ? [] : shown}
      keyExtractor={(s) => s.id}
      ListHeaderComponent={header}
      keyboardShouldPersistTaps="handled"
      renderItem={({ item: s }) => {
        const have = [...owned].filter((k) => k.startsWith(s.id + '|')).length;
        const rarest = [...s.tiers].filter((t) => t.print_run).sort((a, b) => a.print_run! - b.print_run!)[0];
        return (
          <Pressable onPress={() => app.openSet(s.id)} style={({ pressed }) => [S.card, { gap: 6 }, pressed && { opacity: 0.7 }]}>
            <Text style={S.h3}>{s.name}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
              <View style={S.chip}><Text style={S.chipText}>{s.brand}</Text></View>
              <View style={S.chip}><Text style={S.chipText}>{s.category}</Text></View>
              <View style={S.chip}><Text style={S.chipText}>{s.cards.toLocaleString()} cards</Text></View>
              {rarest ? <RarityChip printRun={rarest.print_run} /> : null}
              {have ? <View style={[S.chip, { backgroundColor: '#123524' }]}><Text style={[S.chipText, { color: C.good }]}>you own {have}</Text></View> : null}
            </View>
            {rarest ? <Text style={S.muted}>Rarest: {rarest.name} {printRunLabel(rarest.print_run)}</Text> : null}
          </Pressable>
        );
      }}
    />
  );
}
