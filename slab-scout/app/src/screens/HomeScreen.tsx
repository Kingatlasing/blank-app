import React, { useEffect, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';
import { C, S, money } from '../theme';
import { Btn } from '../components/ui';
import { Grid, Tile, ValueChart } from '../components/cards';
import { useApp } from '../appContext';
import { cards, imageUrl, priceIn, sets, value } from '../core/catalog';
import { currentValue, inCollection, priceMoves, recordImage, today } from '../core/portfolio';

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
  const mode = app.settings.priceMode;
  const chase = useMemo(() => cards().filter((c) => priceIn(c, mode).v).sort((a, b) => (priceIn(b, mode).v || 0) - (priceIn(a, mode).v || 0)).slice(0, 6), [mode]);
  const allSets = sets();
  const moves = useMemo(() => priceMoves(items).slice(0, 8), [items]);

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
          {moves.length ? (
            <View style={[S.card, { gap: 6 }]}>
              <Text style={S.h2}>Price alerts</Text>
              <Text style={S.muted}>Moved 20%+ (and at least $5) since you added them.</Text>
              {moves.map((m) => (
                <Text key={m.rec.id} style={S.body} onPress={m.rec.match?.catalog_key ? () => app.openCard(m.rec.match.catalog_key!) : undefined}>
                  <Text style={{ color: m.now >= m.was ? C.good : C.crit, fontWeight: '700' }}>{m.now >= m.was ? '▲' : '▼'} {m.pct >= 0 ? '+' : ''}{m.pct.toFixed(0)}%</Text>
                  {`  ${m.rec.card?.name || ''} · ${m.rec.card?.set || ''}  ${money(m.was)} → ${money(m.now)}`}
                </Text>
              ))}
            </View>
          ) : null}
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
          <Tile key={c.key} title={c.name} sub={`${allSets[c.setId]?.name || ''} · ${c.variant || 'Base'}`} price={priceIn(c, app.settings.priceMode).text} printRun={c.printRun} uri={imageUrl(c)[0]} onPress={() => app.openCard(c.key)} />
        ))}
      </Grid>
    </ScrollView>
  );
}
