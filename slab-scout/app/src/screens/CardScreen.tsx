/** Card page: big photo with a warm glow, chips, name, Add / Buying options, what you own (with a quantity stepper),
 * market value (finish + grade pickers, sold-price chart, price tiles), past sales, then every parallel, odds and
 * "add a sale". */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Animated, Image, Linking, Pressable, Share, StyleSheet, Text, TextInput, View } from 'react-native';
import { C, S, money } from '../theme';
import { Btn } from '../components/ui';
import { ChangeChip, ChipRow, Header, RarityChip, Sheet, SheetOption, ValueChart } from '../components/cards';
import { Glow, Icon, IconName } from '../components/visual';
import RecordSheet from '../components/RecordSheet';
import { useApp } from '../appContext';
import { useLayout } from '../layout';
import { cardGrades, type GradeTable } from '../core/grades';
import { GRADE_OPTIONS, GRADE_SUB, gradedPrice, getCard, loadSet, useCatalogVersion, imageUrl, oddsText, priceUrl, printRunLabel, relatedSales, sets, siblings, tier, value } from '../core/catalog';
import { changeOver, currentValue, duplicateRecord, recordFromCatalog, recordImage } from '../core/portfolio';
import { soldLinks } from '../core/databases';
import type { Sale, VaultRecord } from '../core/community';
import { TcdbCard, tcdbPage } from '../components/TcdbCard';

const CONDITIONS: string[] = ['Raw', ...GRADE_OPTIONS];
type SaleFilter = 'recent' | '6m' | 'market';

/** Grade written in a sold-listing title ('PSA 10', 'BGS 9.5'...), else 'Raw'. */
function gradeOfTitle(t: string): string {
  const m = /\b(PSA|BGS|CGC|SGC|TAG)\s*(10|9\.5|9|8\.5|8|7|6|5)\b/i.exec(t);
  return m ? `${m[1].toUpperCase()} ${m[2]}` : 'Raw';
}

interface SaleRow { price: number; grade: string; day: string; title?: string; url?: string; market: boolean }

export default function CardScreen({ cardKey, onBack }: { cardKey: string; onBack: () => void }) {
  const app = useApp();
  const L = useLayout();
  useCatalogVersion();
  const c = getCard(cardKey);
  const [loadingSet, setLoadingSet] = useState(false);
  useEffect(() => {
    if (getCard(cardKey)) return;
    const sid = cardKey.split('|')[0];
    if (!sets()[sid]?.remote) return;
    setLoadingSet(true);
    loadSet(sid).catch(() => {}).finally(() => setLoadingSet(false));
  }, [cardKey]);
  const [cond, setCond] = useState('Raw');
  const [gTable, setGTable] = useState<GradeTable | null>(null);
  const [gLoading, setGLoading] = useState(false);
  const cardForGrades = getCard(cardKey);
  useEffect(() => {
    if (!cardForGrades) return;
    let live = true;
    setGLoading(true);
    cardGrades(cardForGrades).then((t) => { if (live) { setGTable(t); setGLoading(false); } });
    return () => { live = false; };
  }, [cardKey, !!cardForGrades]);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [comm, setComm] = useState<Sale[]>([]);
  const [sale, setSale] = useState({ grade: 'Raw', price: '' });
  const [buySheet, setBuySheet] = useState(false);
  const [finishSheet, setFinishSheet] = useState(false);
  const [gradeSheet, setGradeSheet] = useState(false);
  const [ownedOpen, setOwnedOpen] = useState(true);
  const [saleFilter, setSaleFilter] = useState<SaleFilter>('recent');
  const [openRec, setOpenRec] = useState<VaultRecord | null>(null);
  const s = c ? sets()[c.setId] : undefined;
  const fields = useMemo(() => (c && s ? { game: s.category, name: c.name, set: s.name, number: c.number, year: s.year, brand: s.brand, rarity: '', variant: c.variant, card_type: '' } : null), [c, s]);

  useEffect(() => {
    setMsg('');
    if (fields) app.store.salesFor(fields).then(setComm).catch(() => setComm([]));
  }, [fields, app.store]);

  // sticky bar: set name fades into the top bar, the indigo "buying options" pill appears once the buttons scroll away
  const scrollY = useRef(new Animated.Value(0)).current;
  const [btnY, setBtnY] = useState(10000);
  const [pillOn, setPillOn] = useState(false);
  useEffect(() => {
    const id = scrollY.addListener(({ value: y }) => setPillOn((on) => (y > btnY ? true : y < btnY - 8 ? false : on)));
    return () => scrollY.removeListener(id);
  }, [btnY, scrollY]);
  const titleOpacity = scrollY.interpolate({ inputRange: [L.sp(140), L.sp(240)], outputRange: [0, 1], extrapolate: 'clamp' });

  if (!c || !s)
    return (
      <View style={[S.screen, { padding: L.gutter, gap: 12 }]}>
        <Header onBack={onBack} />
        <Text style={S.body}>{loadingSet ? 'Loading card…' : 'Card not found.'}</Text>
      </View>
    );

  const t = tier(c);
  const [v, est] = value(c);
  const odds = oddsText(t, s);
  const sib = siblings(c).sort((a, b) => (b.printRun || 1e6) - (a.printRun || 1e6));
  const ebay = relatedSales(c);
  const owned = app.vault.filter((r) => r.match?.catalog_key === c.key && (r.list || 'collection') === 'collection');
  const wishRec = app.vault.find((r) => r.match?.catalog_key === c.key && r.list === 'wishlist') || null;
  const q = [s.year, s.brand, s.name.split(' Checklist')[0], c.name, c.variant, c.number].filter(Boolean).join(' ');
  const img = imageUrl(c, 1600)[0];
  const rarity = `${c.variant || 'Base'}${c.printRun ? ` ${printRunLabel(c.printRun)}` : ''}`;
  const gradeP = (g: string) => (g === 'Raw' ? (v ? { v, sales: undefined as number | undefined } : null) : gradedPrice({ raw: v, psa9: c.psa9, psa10: c.psa10, table: gTable }, g));
  const priceFor = (g: string): number | null => gradeP(g)?.v ?? null;
  const shownPrice = priceFor(cond);
  const lang = /japan|korean|chinese/i.test(`${s.category} ${s.name}`) ? (/korean/i.test(`${s.category} ${s.name}`) ? 'KR' : /chinese/i.test(`${s.category} ${s.name}`) ? 'CN' : 'JP') : 'EN';

  // every dated sale we have: community sales + price-guide eBay sold listings
  const allSales: SaleRow[] = [
    ...comm.filter((x) => +x.price > 0).map((x) => ({ price: +x.price, grade: x.grade || 'Raw', day: x.sold_on || '', url: x.url || undefined, market: false })),
    ...ebay.map((x) => ({ price: x.p, grade: gradeOfTitle(x.t), day: (() => { const d = new Date(x.d); return isNaN(+d) ? '' : d.toISOString().slice(0, 10); })(), title: x.t, url: x.u, market: true })),
  ].sort((a, b) => b.day.localeCompare(a.day));
  const series = allSales.filter((x) => x.day && x.grade.toUpperCase() === cond.toUpperCase()).map((x) => ({ day: x.day, value: x.price })).sort((a, b) => a.day.localeCompare(b.day));
  const latest = series.length ? series[series.length - 1].value : 0;
  const chips = series.length >= 2
    ? ([['this week', 7], ['last 2 weeks', 14], ['this month', 30], ['last 3 months', 90]] as [string, number][]).map(([l, d]) => ({ l, ch: changeOver(series, latest, d) })).filter((x) => x.ch)
    : [];
  const since = Date.now() - 182 * 864e5;
  const salesShown = allSales.filter((x) => (saleFilter === 'market' ? x.market : saleFilter === '6m' ? x.day && Date.parse(x.day) >= since : true));
  const tiles = (['Raw', 'PSA 9', 'PSA 10', ...(['Raw', 'PSA 9', 'PSA 10'].includes(cond) ? [] : [cond])] as string[]).map((g) => [g, priceFor(g)] as const).filter(([, p]) => p);

  async function add(list: 'collection' | 'wishlist', grade = cond) {
    if (app.needsCode) return setMsg('Set a vault code in Settings first.');
    setBusy(true);
    try {
      const rec = recordFromCatalog(c!);
      if (list === 'collection' && grade !== 'Raw') {
        rec.grade = { method: 'owner', label: grade };
        const gp = gradeP(grade);
        if (gp) {
          rec.pricing.raw.mid = gp.v;
          rec.pricing.graded_label = grade;
          rec.pricing.graded_mid = gp.v;
          rec.pricing.note = `${grade} sold price${gp.sales ? ` (${gp.sales} sales)` : ''} from the price guide`;
        }
      }
      await app.addRecord(rec, list);
      setMsg(list === 'wishlist' ? 'Added to your wishlist' : `Added ${c!.name}${grade !== 'Raw' ? ` (${grade})` : ''} to your collection ✓`);
    } catch (e: any) {
      setMsg(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  }
  async function toggleWish() {
    if (wishRec) {
      setBusy(true);
      try {
        await app.removeRecord(wishRec.id);
        setMsg('Removed from your wishlist');
      } finally {
        setBusy(false);
      }
    } else add('wishlist');
  }
  function share() {
    Share.share({ message: `${c!.name} #${c!.number} · ${s!.name} (${rarity}) · ${v ? `${est ? '~' : ''}${money(v)} raw` : 'no price yet'}${c!.psa10 ? ` · PSA 10 ${money(c!.psa10)}` : ''}${priceUrl(c!) ? `\n${priceUrl(c!)}` : ''}` }).catch(() => {});
  }

  // owned copies, stacked by condition / grade + finish
  const ownedGroups = (() => {
    const m = new Map<string, VaultRecord[]>();
    owned.forEach((r) => {
      const k = `${r.grade?.label || r.grade?.condition || 'Raw'}|${r.card?.variant || 'Normal'}`;
      m.set(k, [...(m.get(k) || []), r]);
    });
    return [...m.entries()].map(([k, recs]) => ({ k, recs, label: k.replace('|', ' • ') }));
  })();
  async function step(recs: VaultRecord[], d: 1 | -1) {
    if (busy) return;
    if (d === -1 && recs.length === 1) {
      Alert.alert('Remove from collection?', `${c!.name} (${recs[0].grade?.label || recs[0].grade?.condition || 'Raw'})`, [
        { text: 'Keep', style: 'cancel' },
        { text: 'Remove', style: 'destructive', onPress: () => { setBusy(true); app.removeRecord(recs[0].id).finally(() => setBusy(false)); } },
      ]);
      return;
    }
    setBusy(true);
    try {
      if (d === 1) await app.addRecord(duplicateRecord(recs[0]), 'collection');
      else await app.removeRecord(recs[recs.length - 1].id);
    } catch (e: any) {
      setMsg(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  }

  const buyLinks: [string, string][] = [
    ...(priceUrl(c) ? [['Price guide', priceUrl(c)] as [string, string]] : []),
    ['eBay listings', `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(q + (cond !== 'Raw' ? ` ${cond}` : ''))}`],
    ...soldLinks(q, cond !== 'Raw' ? cond : '', img),
  ];
  const imgW = Math.min(L.contentW * 0.62, L.sp(300), 380);
  const barH = L.sp(52);

  return (
    <View style={S.screen}>
      {/* top bar */}
      <View style={[S.row, { height: barH, paddingHorizontal: L.gutter, gap: 8, backgroundColor: C.bg, zIndex: 2 }]}>
        <TopBtn name="back" onPress={onBack} label="Back" />
        <Animated.Text style={{ flex: 1, textAlign: 'center', color: C.ink, fontWeight: '700', fontSize: L.fs(14), opacity: titleOpacity }} numberOfLines={1}>{s.name}</Animated.Text>
        <TopBtn name="bookmark" onPress={toggleWish} label={wishRec ? 'Remove from wishlist' : 'Add to wishlist'} on={!!wishRec} />
        <TopBtn name="share" onPress={share} label="Share" />
      </View>

      <Animated.ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: L.gutter, paddingBottom: L.sp(60), gap: L.sp(14) }}
        keyboardShouldPersistTaps="handled"
        scrollEventThrottle={16}
        onScroll={Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], { useNativeDriver: true })}
      >
        {/* photo with a warm glow */}
        <View style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: L.sp(18) }}>
          <Glow color="#FF9F4A" size={imgW * 1.55} style={{ alignSelf: 'center' }} />
          <Glow color="#FFD27A" size={imgW * 1.05} style={{ alignSelf: 'center' }} />
          {img ? (
            <Image source={{ uri: img }} style={{ width: imgW, aspectRatio: 63 / 88, borderRadius: L.sp(12), resizeMode: 'contain' }} />
          ) : tcdbPage(c) ? (
            <TcdbCard card={c} width={imgW} radius={L.sp(12)} />
          ) : (
            <View style={{ width: imgW, aspectRatio: 63 / 88, borderRadius: L.sp(12), backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center', padding: 12 }}>
              <Text style={[S.muted, { textAlign: 'center' }]}>{c.name}</Text>
            </View>
          )}
          {imageUrl(c)[1] ? <Text style={[S.muted, { marginTop: 6, fontSize: L.fs(12) }]}>Photo of another parallel of this card</Text> : null}
          {/^~?eb:/.test(c.img) ? <Text style={[S.muted, { marginTop: 6, fontSize: L.fs(12) }]}>Photo from an eBay sale of this card</Text> : null}
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          <InfoChip icon="cards" label={s.category || 'Cards'} />
          <InfoChip label={s.name} onPress={() => app.openSet(c.setId)} />
          <InfoChip label={lang} />
        </View>
        <View style={{ gap: 4 }}>
          <Text style={{ color: C.ink, fontWeight: '900', fontSize: L.fs(28), letterSpacing: -0.4 }}>{c.name} <Text style={{ color: C.ink2 }}>#{c.number}</Text></Text>
          <View style={[S.row, { gap: 6, flexWrap: 'wrap' }]}>
            <Text style={{ color: C.lime, fontWeight: '800', fontSize: L.fs(13), letterSpacing: 1, textTransform: 'uppercase' }}>{c.variant || 'Base'}</Text>
            <RarityChip printRun={c.printRun} />
            <Text style={{ color: C.ink2, fontSize: L.fs(13) }}>{s.brand}{s.year ? ` · ${s.year}` : ''}</Text>
          </View>
        </View>

        <View style={{ gap: L.sp(10) }} onLayout={(e) => setBtnY(e.nativeEvent.layout.y + e.nativeEvent.layout.height - L.sp(10))}>
          <BigBtn icon="book" label={busy ? 'SAVING…' : `ADD TO COLLECTION${cond !== 'Raw' ? ` · ${cond}` : ''}`} onPress={() => add('collection')} disabled={busy} />
          <BigBtn primary label="SEE BUYING OPTIONS" onPress={() => setBuySheet(true)} />
          {msg ? <Text style={[S.body, { color: C.good, textAlign: 'center' }]}>{msg}</Text> : null}
        </View>

        {/* in your collection */}
        {owned.length ? (
          <View style={[S.card, { padding: L.sp(14), gap: L.sp(10), borderRadius: L.sp(20) }]}>
            <Pressable onPress={() => setOwnedOpen(!ownedOpen)} style={[S.row, { justifyContent: 'space-between' }]}>
              <Text style={[S.h3, { fontSize: L.fs(17) }]}>In your collection <Text style={{ color: C.ink2 }}>· {owned.length}</Text></Text>
              <Icon name={ownedOpen ? 'up' : 'down'} size={L.fs(16)} color={C.ink2} />
            </Pressable>
            {ownedOpen ? (
              <>
                <Text style={S.eyebrow}>Owned</Text>
                {ownedGroups.map((g) => (
                  <View key={g.k} style={[S.row, { gap: L.sp(10) }]}>
                    <Pressable onPress={() => setOpenRec(g.recs[0])} style={[S.row, { flex: 1, gap: L.sp(10), minWidth: 0 }]}>
                      {recordImage(g.recs[0]) || g.recs[0].thumb ? (
                        <Image source={{ uri: recordImage(g.recs[0]) || `data:image/jpeg;base64,${g.recs[0].thumb}` }} style={{ width: L.sp(36), height: L.sp(50), borderRadius: 5 }} />
                      ) : null}
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text style={{ color: C.ink, fontWeight: '700', fontSize: L.fs(14) }} numberOfLines={1}>{g.label}</Text>
                        <Text style={{ color: C.lime, fontWeight: '800', fontSize: L.fs(13), fontVariant: ['tabular-nums'] }}>{money(currentValue(g.recs[0]) || undefined)}</Text>
                      </View>
                    </Pressable>
                    <View style={[S.row, { gap: 0, backgroundColor: C.blue, borderRadius: 999, height: L.sp(36), paddingHorizontal: 4 }]}>
                      <Pressable onPress={() => step(g.recs, -1)} hitSlop={6} accessibilityLabel="Remove one" style={{ width: L.sp(34), alignItems: 'center' }}>
                        <Icon name={g.recs.length === 1 ? 'trash' : 'close'} size={L.fs(g.recs.length === 1 ? 16 : 12)} color="#fff" />
                      </Pressable>
                      <Text style={{ color: '#fff', fontWeight: '900', fontSize: L.fs(15), minWidth: L.sp(22), textAlign: 'center', fontVariant: ['tabular-nums'] }}>{g.recs.length}</Text>
                      <Pressable onPress={() => step(g.recs, 1)} hitSlop={6} accessibilityLabel="Add one more" style={{ width: L.sp(34), alignItems: 'center' }}>
                        <Icon name="plus" size={L.fs(15)} color="#fff" />
                      </Pressable>
                    </View>
                  </View>
                ))}
              </>
            ) : null}
          </View>
        ) : null}

        {/* market value */}
        <View style={{ gap: L.sp(12) }}>
          <Text style={[S.h2, { fontSize: L.fs(21) }]}>Market value</Text>
          <View style={[S.row, { gap: 8 }]}>
            <DropPill label={c.variant || 'Normal'} onPress={() => setFinishSheet(true)} disabled={sib.length < 2} />
            <DropPill label={cond} onPress={() => setGradeSheet(true)} />
          </View>
          <Text style={{ color: C.good, fontWeight: '900', fontSize: L.fs(36), fontVariant: ['tabular-nums'], letterSpacing: -0.5 }}>
            {shownPrice ? `${cond === 'Raw' && est ? '~' : ''}${money(shownPrice)}` : '—'}
          </Text>
          {!shownPrice ? <Text style={S.muted}>The price guide has no {cond} price for this card. Check the sold links in buying options.</Text> : null}
          {cond === 'Raw' && est ? <Text style={[S.muted, { marginTop: -L.sp(6) }]}>No sale of this exact card yet, so Raw shows the typical sold price for its parallel.</Text> : null}
          {chips.length ? (
            <Animated.ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -L.gutter, flexGrow: 0 }} contentContainerStyle={{ paddingHorizontal: L.gutter, gap: 8 }}>
              {chips.map(({ l, ch }) => <ChangeChip key={l} abs={ch!.abs} pct={ch!.pct} label={l} />)}
            </Animated.ScrollView>
          ) : null}
          {series.length >= 2 ? (
            <View style={{ gap: 4 }}>
              <ValueChart points={series} height={L.sp(180)} />
              <Text style={[S.muted, { fontSize: L.fs(11) }]}>{series.length} dated {cond} sales</Text>
            </View>
          ) : (
            <Text style={[S.muted, { fontSize: L.fs(12) }]}>Not enough dated {cond} sales of this card yet to draw a price trend.</Text>
          )}
          {tiles.length ? (
            <View style={[S.row, { gap: 8 }]}>
              {tiles.map(([g, p]) => {
                const on = g === cond;
                return (
                  <Pressable key={g} onPress={() => setCond(g)} style={{ flex: 1, borderRadius: L.sp(14), padding: L.sp(10), backgroundColor: C.surface, borderWidth: 1.5, borderColor: on ? C.blue : C.lineSoft, gap: 2 }}>
                    <Text style={{ color: C.ink2, fontWeight: '800', fontSize: L.fs(11), letterSpacing: 0.8 }}>{g === 'Raw' ? 'RAW' : g}</Text>
                    <Text style={{ color: C.ink, fontWeight: '900', fontSize: L.fs(16), fontVariant: ['tabular-nums'] }} numberOfLines={1} adjustsFontSizeToFit>{money(p ?? undefined)}</Text>
                  </Pressable>
                );
              })}
            </View>
          ) : null}
          <Text style={{ color: C.ink2, fontStyle: 'italic', fontSize: L.fs(12), lineHeight: L.fs(17) }}>
            Prices are estimates from price guides{s.prices_as_of ? ` (${s.source || 'sold listings'}, updated ${s.prices_as_of})` : ''} and recent sold listings. Actual sale prices may vary.
          </Text>
          <Pressable onPress={() => Linking.openURL(`mailto:?subject=${encodeURIComponent(`Slab Scout price error: ${c.name} #${c.number}`)}&body=${encodeURIComponent(`${s.name} · ${rarity}\nShown: ${money(shownPrice ?? undefined)} (${cond})\nCard key: ${c.key}\n\nWhat's wrong:\n`)}`).catch(() => {})}
            style={[S.pill, { alignSelf: 'flex-start', paddingVertical: L.sp(7) }]}>
            <Text style={{ color: C.ink, fontWeight: '700', fontSize: L.fs(13) }}>Report an error</Text>
          </Pressable>
        </View>

        {[c.printRun ? (c.printRun === 1 ? 'Only 1 exists' : `Only ${c.printRun} copies exist`) : '', odds ? `Pull odds: ${odds}` : ''].filter(Boolean).map((f) => (
          <Text key={f} style={S.body}>{f}</Text>
        ))}

        {/* past sales */}
        <View style={{ gap: L.sp(10) }}>
          <Text style={[S.h2, { fontSize: L.fs(21) }]}>Past sales</Text>
          <View style={[S.row, { gap: 8, flexWrap: 'wrap' }]}>
            {([['recent', 'Most recent'], ['6m', '6 months'], ['market', 'Marketplace']] as [SaleFilter, string][]).map(([id, l]) => {
              const on = saleFilter === id;
              return (
                <Pressable key={id} onPress={() => setSaleFilter(id)} style={[S.pill, { paddingVertical: L.sp(7), paddingHorizontal: L.sp(14) }, on && S.pillOn]}>
                  <Text style={{ color: on ? '#fff' : C.ink2, fontWeight: '700', fontSize: L.fs(13) }}>{l}</Text>
                </Pressable>
              );
            })}
          </View>
          <View style={[S.card, { gap: 0, paddingVertical: L.sp(4), borderRadius: L.sp(20) }]}>
            {salesShown.slice(0, 16).map((x, i) => (
              <Pressable key={i} disabled={!x.url} onPress={() => x.url && Linking.openURL(x.url).catch(() => {})} style={[S.row, { paddingVertical: L.sp(10), borderTopWidth: i ? StyleSheet.hairlineWidth : 0, borderTopColor: C.line, gap: 10 }]}>
                <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                  <Text style={{ color: C.ink, fontWeight: '700', fontSize: L.fs(13) }} numberOfLines={1}>{x.title || `${x.grade} · community sale`}</Text>
                  <Text style={{ color: C.ink2, fontSize: L.fs(12) }}>{[x.grade, x.day || 'date unknown', x.market ? 'eBay' : 'community'].join(' · ')}{x.url ? ' ↗' : ''}</Text>
                </View>
                <Text style={{ color: C.lime, fontWeight: '900', fontSize: L.fs(15), fontVariant: ['tabular-nums'] }}>{money(x.price)}</Text>
              </Pressable>
            ))}
            {!salesShown.length ? <Text style={[S.muted, { paddingVertical: L.sp(10) }]}>No individual sales stored for this filter yet. Check the live links in buying options.</Text> : null}
          </View>
        </View>

        {sib.length > 1 ? (
          <View style={{ gap: 8 }}>
            <Text style={[S.h2, { fontSize: L.fs(21) }]}>Every version of this card</Text>
            <View style={[S.card, { borderRadius: L.sp(20) }]}>
              <View style={st.lrow}>
                {['Parallel', 'Run', 'Raw', 'PSA 10'].map((h, i) => <Text key={h} style={[S.eyebrow, i ? st.num : st.first]}>{h}</Text>)}
              </View>
              {sib.map((x) => {
                const me = x.key === c.key;
                return (
                  <Pressable key={x.key} style={st.lrow} onPress={() => !me && app.openCard(x.key)}>
                    <Text style={[S.body, st.first, me && { color: C.lime, fontWeight: '800' }]} numberOfLines={1}>{x.variant || 'Base'}</Text>
                    <Text style={[S.body, S.mono, st.num, me && { color: C.lime }]}>{printRunLabel(x.printRun) || '—'}</Text>
                    <Text style={[S.body, S.mono, st.num, me && { color: C.lime }]}>{money(x.raw ?? undefined)}</Text>
                    <Text style={[S.body, S.mono, st.num, me && { color: C.lime }]}>{money(x.psa10 ?? undefined)}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        ) : null}

        <Pressable onPress={() => app.openSet(c.setId)} style={[S.row, S.card, { borderRadius: L.sp(20), justifyContent: 'space-between' }]}>
          <View style={{ flex: 1 }}>
            <Text style={S.eyebrow}>Set</Text>
            <Text style={[S.h3, { fontSize: L.fs(16) }]} numberOfLines={2}>{s.name}</Text>
          </View>
          <Icon name="forward" size={L.fs(16)} color={C.ink2} />
        </Pressable>

        <View style={[S.card, { borderRadius: L.sp(20) }]}>
          <Text style={S.eyebrow}>Add a sale you saw (helps everyone)</Text>
          <ChipRow options={CONDITIONS} value={sale.grade} onChange={(g) => setSale((x) => ({ ...x, grade: g }))} />
          <View style={S.row}>
            <TextInput style={[S.input, { flex: 1, backgroundColor: C.surface2 }]} placeholder="Sold for $" keyboardType="decimal-pad" value={sale.price} onChangeText={(p) => setSale((x) => ({ ...x, price: p }))} placeholderTextColor={C.ink2} />
            <Btn label="Add sale" disabled={!(+sale.price > 0) || !fields}
              onPress={async () => {
                await app.store.addSale(fields!, sale.grade, +sale.price, new Date().toISOString().slice(0, 10), '');
                setSale({ ...sale, price: '' });
                setComm(await app.store.salesFor(fields!));
              }} />
          </View>
        </View>
      </Animated.ScrollView>

      {/* compact sticky pill once the big buttons have scrolled away */}
      {pillOn ? (
        <View pointerEvents="box-none" style={{ position: 'absolute', top: barH + 4, left: L.gutter, right: L.gutter, zIndex: 3 }}>
          <Pressable onPress={() => setBuySheet(true)} style={[S.row, { backgroundColor: C.blue, borderRadius: 999, paddingVertical: L.sp(11), paddingHorizontal: L.sp(16), justifyContent: 'space-between', shadowColor: '#000', shadowOpacity: 0.4, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 6 }]}>
            <Text style={{ color: '#DADDFF', fontWeight: '800', fontSize: L.fs(11), letterSpacing: 1.2, textTransform: 'uppercase', flexShrink: 1 }} numberOfLines={1}>{rarity}</Text>
            <Text style={{ color: '#fff', fontWeight: '900', fontSize: L.fs(13), letterSpacing: 0.6 }}>SEE BUYING OPTIONS</Text>
          </Pressable>
        </View>
      ) : null}

      <Sheet visible={buySheet} onClose={() => setBuySheet(false)} title="Buying options">
        <Text style={S.muted}>Opens live listings and sold prices for {c.name} #{c.number}{cond !== 'Raw' ? ` (${cond})` : ''}.</Text>
        {buyLinks.map(([label, url]) => (
          <SheetOption key={label} label={label} sub={url.replace(/^https?:\/\/(www\.)?/, '').split('/')[0]} onPress={() => Linking.openURL(url).catch(() => {})} right={<Icon name="forward" size={L.fs(14)} color={C.ink2} />} />
        ))}
      </Sheet>
      <Sheet visible={finishSheet} onClose={() => setFinishSheet(false)} title="Finish / parallel">
        {sib.map((x) => (
          <SheetOption key={x.key} label={`${x.variant || 'Base'}${x.printRun ? ` ${printRunLabel(x.printRun)}` : ''}`} sub={x.raw ? `${money(x.raw)} raw` : undefined} on={x.key === c.key}
            onPress={() => { setFinishSheet(false); if (x.key !== c.key) app.openCard(x.key); }} />
        ))}
      </Sheet>
      <Sheet visible={gradeSheet} onClose={() => setGradeSheet(false)} title="Grade">
        {CONDITIONS.map((g) => (
          <SheetOption key={g} label={g} sub={[GRADE_SUB[g], gradeP(g) ? `${money(gradeP(g)!.v)}${gradeP(g)!.sales ? ` · ${gradeP(g)!.sales} sales` : ''}` : gLoading ? 'Looking up sold prices…' : 'No sold prices found'].filter(Boolean).join(' · ')} on={g === cond} onPress={() => { setCond(g); setGradeSheet(false); }} />
        ))}
      </Sheet>
      <RecordSheet rec={openRec} onClose={() => setOpenRec(null)} />
    </View>
  );
}

function TopBtn({ name, onPress, label, on }: { name: IconName; onPress: () => void; label: string; on?: boolean }) {
  const L = useLayout();
  const d = L.sp(40);
  return (
    <Pressable onPress={onPress} hitSlop={6} accessibilityLabel={label} style={({ pressed }) => [{ width: d, height: d, borderRadius: d / 2, backgroundColor: on ? C.blue : C.surface, alignItems: 'center', justifyContent: 'center' }, pressed && { opacity: 0.7 }]}>
      <Icon name={name} size={L.fs(18)} color={C.ink} />
    </Pressable>
  );
}

function InfoChip({ label, icon, onPress }: { label: string; icon?: IconName; onPress?: () => void }) {
  const L = useLayout();
  return (
    <Pressable disabled={!onPress} onPress={onPress} style={[S.row, { gap: 5, backgroundColor: C.surface, borderRadius: 999, paddingHorizontal: L.sp(11), paddingVertical: L.sp(6), borderWidth: 1, borderColor: C.line, maxWidth: '100%' }]}>
      {icon ? <Icon name={icon} size={L.fs(13)} color={C.ink2} stroke={1.3} /> : null}
      <Text style={{ color: C.ink, fontWeight: '700', fontSize: L.fs(12), flexShrink: 1 }} numberOfLines={1}>{label}</Text>
    </Pressable>
  );
}

function BigBtn({ label, onPress, primary, icon, disabled }: { label: string; onPress: () => void; primary?: boolean; icon?: IconName; disabled?: boolean }) {
  const L = useLayout();
  return (
    <Pressable onPress={onPress} disabled={disabled} style={({ pressed }) => [S.row, { justifyContent: 'center', gap: 8, borderRadius: 999, paddingVertical: L.sp(15), backgroundColor: primary ? C.blue : C.surface, borderWidth: primary ? 0 : 1, borderColor: C.line }, (pressed || disabled) && { opacity: 0.75 }]}>
      {icon ? <Icon name={icon} size={L.fs(17)} color={C.ink} /> : null}
      <Text style={{ color: '#fff', fontWeight: '900', fontSize: L.fs(14), letterSpacing: 0.8 }} numberOfLines={1}>{label}</Text>
    </Pressable>
  );
}

function DropPill({ label, onPress, disabled }: { label: string; onPress: () => void; disabled?: boolean }) {
  const L = useLayout();
  return (
    <Pressable onPress={onPress} disabled={disabled} style={[S.row, { gap: 6, backgroundColor: C.surface, borderRadius: 999, borderWidth: 1, borderColor: C.line, paddingHorizontal: L.sp(14), paddingVertical: L.sp(8), maxWidth: '60%' }]}>
      <Text style={{ color: C.ink, fontWeight: '700', fontSize: L.fs(13), flexShrink: 1 }} numberOfLines={1}>{label}</Text>
      {!disabled ? <Icon name="down" size={L.fs(12)} color={C.ink2} /> : null}
    </Pressable>
  );
}

const st = StyleSheet.create({
  lrow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.line, gap: 6 },
  first: { flex: 1.6 },
  num: { flex: 1, textAlign: 'right' },
});
