import React, { useEffect, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';
import { C, S, money } from '../theme';
import { Btn } from '../components/ui';
import { Grid, Tile, ValueChart } from '../components/cards';
import { useApp } from '../appContext';
import { cards, imageUrl, sets, value } from '../core/catalog';
import { currentValue, inCollection, recordImage, today } from '../core/portfolio';

export default function HomeScreen() {
  const app = useApp();
  const items = useMemo(() => app.vault.filter(inCollection), [app.vault]);
  const total = useMemo(() => items.reduce((s, r) => s + currentValue(r), 0), [items]);
  const [hist, setHist] = useState<{ day: string; value: number }[]>([]);

  useEffect(() => {
    if (app.needsCode || app.vaultLoading) return;
    (async () => {
      try {
        let h = await app.store.historyList(app.settings.vaultCode);
        const last = h[h.length - 1];
        if (!last || last.day !== today() || Math.abs(last.value - total) > 0.005) {
          await app.store.historyAdd(app.settings.vaultCode, today(), total);
          h = await app.store.historyList(app.settings.vaultCode);
        }
        setHist(h);
      } catch {
        setHist([{ day: today(), value: total }]);
      }
    })();
  }, [total, app.needsCode, app.vaultLoading, app.store, app.settings.vaultCode]);

  const prev = hist.length >= 2 ? hist[hist.length - 2] : null;
  const change = prev ? total - prev.value : 0;
  const pct = prev && prev.value ? (change / prev.value) * 100 : 0;
  const top = [...items].sort((a, b) => currentValue(b) - currentValue(a)).slice(0, 6);
  const recent = [...items].sort((a, b) => (b.added_at || '').localeCompare(a.added_at || '')).slice(0, 6);
  const chase = useMemo(() => cards().filter((c) => c.raw).sort((a, b) => (b.raw || 0) - (a.raw || 0)).slice(0, 6), []);
  const allSets = sets();

  return (
    <ScrollView style={S.screen} contentContainerStyle={[S.pad, { paddingBottom: 40 }]} refreshControl={<RefreshControl refreshing={app.vaultLoading} onRefresh={app.refreshVault} tintColor={C.accent} />}>
      {app.needsCode ? (
        <View style={S.banner}>
          <Text style={S.body}>Set a private vault code in Settings to start your collection. Use the same code in the web app to see the same cards.</Text>
        </View>
      ) : (
        <>
          <View style={[S.card, { gap: 4, paddingVertical: 18 }]}>
            <Text style={S.eyebrow}>Collection value</Text>
            <Text style={{ color: C.ink, fontSize: 40, fontWeight: '800', fontVariant: ['tabular-nums'] }}>{money(total)}</Text>
            {prev ? (
              <Text style={{ color: change >= 0 ? C.good : C.crit, fontWeight: '700' }}>
                {change >= 0 ? '▲' : '▼'} {money(Math.abs(change))} ({pct >= 0 ? '+' : ''}{pct.toFixed(1)}%) since {prev.day}
              </Text>
            ) : (
              <Text style={S.muted}>Tracking starts today</Text>
            )}
            <Text style={S.muted}>{items.length} card{items.length === 1 ? '' : 's'}</Text>
            {hist.length >= 2 ? <ValueChart points={hist} /> : null}
          </View>
          <View style={S.row}>
            <Btn primary label="Scan a card" style={{ flex: 1 }} onPress={() => app.goTab('scan')} />
            <Btn label="Explore sets" style={{ flex: 1 }} onPress={() => app.goTab('explore')} />
          </View>
          {items.length ? (
            <>
              <Text style={S.h2}>Most valuable</Text>
              <Grid>
                {top.map((r) => (
                  <Tile key={r.id} title={r.card?.name} sub={[r.card?.set, r.card?.number && `#${r.card.number}`].filter(Boolean).join(' ')} price={money(currentValue(r) || undefined)} thumb={r.thumb} uri={recordImage(r)} printRun={r.print_run}
                    onPress={r.match?.catalog_key ? () => app.openCard(r.match.catalog_key!) : () => app.goTab('collection')} />
                ))}
              </Grid>
              <Text style={S.h2}>Recently added</Text>
              <Grid>
                {recent.map((r) => (
                  <Tile key={r.id} title={r.card?.name} sub={r.card?.set} price={money(currentValue(r) || undefined)} thumb={r.thumb} uri={recordImage(r)} printRun={r.print_run}
                    onPress={r.match?.catalog_key ? () => app.openCard(r.match.catalog_key!) : () => app.goTab('collection')} />
                ))}
              </Grid>
            </>
          ) : (
            <View style={S.card}>
              <Text style={S.h3}>Your collection is empty</Text>
              <Text style={S.muted}>Scan a card, or add one from Explore, to start tracking its value.</Text>
            </View>
          )}
        </>
      )}
      <Text style={S.h2}>Top chase cards right now</Text>
      <Grid>
        {chase.map((c) => (
          <Tile key={c.key} title={c.name} sub={`${allSets[c.setId]?.name || ''} · ${c.variant || 'Base'}`} price={money(value(c)[0] ?? undefined)} printRun={c.printRun} uri={imageUrl(c)[0]} onPress={() => app.openCard(c.key)} />
        ))}
      </Grid>
    </ScrollView>
  );
}
