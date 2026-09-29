import React, { useEffect, useMemo, useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { C, S, money } from '../theme';
import { Btn, LinkRow } from '../components/ui';
import { ChipRow, Header, RarityChip } from '../components/cards';
import { useApp } from '../appContext';
import { getCard, oddsText, priceUrl, printRunLabel, relatedSales, sets, siblings, tier, value } from '../core/catalog';
import { recordFromCatalog } from '../core/portfolio';
import type { Sale } from '../core/community';

const CONDITIONS = ['Raw', 'PSA 10', 'PSA 9', 'PSA 8', 'TAG 10', 'TAG 9', 'BGS 9.5', 'CGC 10'];

export default function CardScreen({ cardKey, onBack }: { cardKey: string; onBack: () => void }) {
  const app = useApp();
  const c = getCard(cardKey);
  const [cond, setCond] = useState('Raw');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [comm, setComm] = useState<Sale[]>([]);
  const [sale, setSale] = useState({ grade: 'Raw', price: '' });
  const s = c ? sets()[c.setId] : undefined;
  const fields = useMemo(() => (c && s ? { game: s.category, name: c.name, set: s.name, number: c.number, year: s.year, brand: s.brand, rarity: '', variant: c.variant, card_type: '' } : null), [c, s]);

  useEffect(() => {
    setMsg('');
    if (fields) app.store.salesFor(fields).then(setComm).catch(() => setComm([]));
  }, [fields, app.store]);

  if (!c || !s) return <View style={[S.screen, S.pad]}><Header onBack={onBack} /><Text style={S.body}>Card not found.</Text></View>;

  const t = tier(c);
  const [v, est] = value(c);
  const odds = oddsText(t, s);
  const sib = siblings(c).sort((a, b) => (b.printRun || 1e6) - (a.printRun || 1e6));
  const ebay = relatedSales(c);
  const mine = app.vault.filter((r) => r.match?.catalog_key === c.key && (r.list || 'collection') === 'collection').length;
  const q = [s.year, s.brand, s.name.split(' Checklist')[0], c.name, c.variant, c.number].filter(Boolean).join(' ');

  async function add(list: 'collection' | 'wishlist') {
    if (app.needsCode) return setMsg('Set a vault code in Settings first.');
    setBusy(true);
    try {
      const rec = recordFromCatalog(c!);
      if (list === 'collection' && cond !== 'Raw') {
        rec.grade = { method: 'owner', label: cond };
        if (cond === 'PSA 10' && c!.psa10) rec.pricing.raw.mid = c!.psa10;
        if (cond === 'PSA 9' && c!.psa9) rec.pricing.raw.mid = c!.psa9;
      }
      await app.addRecord(rec, list);
      setMsg(list === 'wishlist' ? 'Added to your wishlist ♡' : `Added ${c!.name} to your collection ✓`);
    } catch (e: any) {
      setMsg(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView style={S.screen} contentContainerStyle={[S.pad, { paddingBottom: 50 }]} keyboardShouldPersistTaps="handled">
      <Header onBack={onBack} right={<Pressable onPress={() => app.openSet(c.setId)}><Text style={{ color: C.accent, fontWeight: '700' }}>Set ›</Text></Pressable>} />
      <View style={{ gap: 6 }}>
        <Text style={S.h1}>{c.name}</Text>
        <Text style={S.muted}>{s.name} · #{c.number}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
          <View style={[S.chip, { backgroundColor: C.goldSoft }]}><Text style={[S.chipText, { color: C.gold }]}>{c.variant || 'Base'}</Text></View>
          <RarityChip printRun={c.printRun} />
          <View style={S.chip}><Text style={S.chipText}>{s.brand}</Text></View>
        </View>
      </View>

      <View style={S.row}>
        {([[est ? 'Raw (typical)' : 'Raw', v], ['PSA 9', c.psa9], ['PSA 10', c.psa10]] as [string, number | null][]).map(([l, x], i) => (
          <View key={l} style={[st.metric, i === 0 && { backgroundColor: C.goldSoft }]}>
            <Text style={S.eyebrow}>{l}</Text>
            <Text style={[st.big, i === 0 && { color: C.gold }]} numberOfLines={1} adjustsFontSizeToFit>{money(x ?? undefined)}</Text>
          </View>
        ))}
      </View>
      {est ? <Text style={S.muted}>No sale of this exact card yet, so Raw shows the typical sold price for its parallel.</Text> : null}
      {[c.printRun ? (c.printRun === 1 ? 'Only 1 exists' : `Only ${c.printRun} copies exist`) : '', odds ? `Pull odds: ${odds}` : ''].filter(Boolean).map((f) => (
        <Text key={f} style={S.body}>{f}</Text>
      ))}
      {s.prices_as_of ? <Text style={S.muted}>Prices from {s.source} sold listings, updated {s.prices_as_of}.</Text> : null}

      <View style={S.card}>
        <Text style={S.eyebrow}>Condition</Text>
        <ChipRow options={CONDITIONS} value={cond} onChange={setCond} />
        <View style={S.row}>
          <Btn primary label="Add to collection" style={{ flex: 1.4 }} disabled={busy} onPress={() => add('collection')} />
          <Btn label="♡ Wishlist" style={{ flex: 1 }} disabled={busy} onPress={() => add('wishlist')} />
        </View>
        {msg ? <Text style={[S.body, { color: C.good }]}>{msg}</Text> : null}
        {mine ? <Text style={S.muted}>You own {mine} of this card.</Text> : null}
      </View>

      {sib.length > 1 ? (
        <View style={{ gap: 6 }}>
          <Text style={S.h2}>Every version of this card</Text>
          <View style={S.card}>
            <View style={st.lrow}>
              {['Parallel', 'Run', 'Raw', 'PSA 10'].map((h, i) => <Text key={h} style={[S.eyebrow, i ? st.num : st.first]}>{h}</Text>)}
            </View>
            {sib.map((x) => {
              const me = x.key === c.key;
              return (
                <Pressable key={x.key} style={st.lrow} onPress={() => !me && app.openCard(x.key)}>
                  <Text style={[S.body, st.first, me && { color: C.accent, fontWeight: '800' }]} numberOfLines={1}>{x.variant || 'Base'}</Text>
                  <Text style={[S.body, S.mono, st.num, me && { color: C.accent }]}>{printRunLabel(x.printRun) || '—'}</Text>
                  <Text style={[S.body, S.mono, st.num, me && { color: C.accent }]}>{money(x.raw ?? undefined)}</Text>
                  <Text style={[S.body, S.mono, st.num, me && { color: C.accent }]}>{money(x.psa10 ?? undefined)}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ) : null}

      <Text style={S.h2}>Recent sales</Text>
      <View style={[S.card, { gap: 8 }]}>
        {comm.length ? <Text style={S.eyebrow}>Added by the community</Text> : null}
        {comm.slice(0, 8).map((x, i) => (
          <Text key={`c${i}`} style={[S.body, S.mono]}>{money(+x.price)} · {x.grade}{x.sold_on ? ` · ${x.sold_on}` : ''}</Text>
        ))}
        {ebay.length ? <Text style={S.eyebrow}>eBay sold listings mentioning this card</Text> : null}
        {ebay.map((x, i) => (
          <Pressable key={`e${i}`} onPress={() => Linking.openURL(x.u).catch(() => {})} style={{ gap: 1 }}>
            <Text style={[S.body, S.mono, { fontWeight: '700' }]}>{money(x.p)} <Text style={S.muted}>· {x.d}</Text></Text>
            <Text style={[S.muted, { color: C.ink2 }]} numberOfLines={1}>{x.t} ↗</Text>
          </Pressable>
        ))}
        {!comm.length && !ebay.length ? <Text style={S.muted}>No individual sales stored for this card yet. Check the live links below.</Text> : null}
      </View>
      <LinkRow links={[['Price guide', priceUrl(c)], ...soldLinksFor(q)]} />

      <View style={S.card}>
        <Text style={S.eyebrow}>Add a sale you saw (helps everyone)</Text>
        <ChipRow options={CONDITIONS} value={sale.grade} onChange={(g) => setSale((x) => ({ ...x, grade: g }))} />
        <View style={S.row}>
          <TextInput style={[S.input, { flex: 1 }]} placeholder="Sold for $" keyboardType="decimal-pad" value={sale.price} onChangeText={(p) => setSale((x) => ({ ...x, price: p }))} placeholderTextColor={C.ink2} />
          <Btn label="Add sale" disabled={!(+sale.price > 0) || !fields}
            onPress={async () => {
              await app.store.addSale(fields!, sale.grade, +sale.price, new Date().toISOString().slice(0, 10), '');
              setSale({ ...sale, price: '' });
              setComm(await app.store.salesFor(fields!));
            }} />
        </View>
      </View>
    </ScrollView>
  );
}

function soldLinksFor(q: string): [string, string][] {
  const e = encodeURIComponent;
  return [
    ['eBay sold', `https://www.ebay.com/sch/i.html?_nkw=${e(q)}&LH_Sold=1&LH_Complete=1`],
    ['Google', `https://www.google.com/search?q=${e(q + ' sold price')}`],
  ];
}

const st = StyleSheet.create({
  metric: { flex: 1, backgroundColor: C.surface2, borderRadius: 12, padding: 10, gap: 2 },
  big: { color: C.ink, fontSize: 20, fontWeight: '800', fontVariant: ['tabular-nums'] },
  lrow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.line, gap: 6 },
  first: { flex: 1.6 },
  num: { flex: 1, textAlign: 'right' },
});
