/** Feed: the community catalog (cards people confirmed, fakes they reported) plus your own recent scans. */
import React, { useEffect, useMemo, useState } from 'react';
import { Image, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
import { C, S, money } from '../theme';
import { Pills, ScreenTitle, TileGrid } from '../components/cards';
import { Icon } from '../components/visual';
import type { CatalogRow, Store } from '../core/community';
import { loadHistory, onHistory, ScanItem } from '../core/scanHistory';
import { useApp } from '../appContext';
import { useLayout } from '../layout';

type Filter = 'new' | 'hot' | 'top' | 'fakes' | 'mine';
const FILTERS: Filter[] = ['new', 'hot', 'top', 'fakes', 'mine'];
const LABELS: Record<Filter, string> = { new: '✨ New', hot: '🔥 Hot', top: '🏆 Top', fakes: '🚩 Fakes reported', mine: '📸 Your scans' };
const HINTS: Record<Filter, string> = {
  new: 'Cards the community has confirmed only once so far.',
  hot: 'Cards confirmed by several people.',
  top: 'The most-confirmed cards in the catalog.',
  fakes: 'Cards people reported as fake. Future scans of these get flagged.',
  mine: 'Everything you scanned on this phone, newest first.',
};

export default function CommunityScreen({ store }: { store: Store }) {
  const app = useApp();
  const L = useLayout();
  const [stats, setStats] = useState<{ cards: number; fakes: number; sales: number } | null>(null);
  const [q, setQ] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [rows, setRows] = useState<CatalogRow[]>([]);
  const [err, setErr] = useState('');
  const [filter, setFilter] = useState<Filter>('top');
  const [scans, setScans] = useState<ScanItem[]>([]);
  const [tick, setTick] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    store.stats().then(setStats).catch((e) => setErr(String(e?.message || e)));
  }, [store, tick]);
  useEffect(() => {
    setLoading(true);
    const t = setTimeout(
      () =>
        store
          .search(q)
          .then((r) => { setRows(r); setErr(''); })
          .catch((e) => setErr(String(e?.message || e)))
          .finally(() => setLoading(false)),
      350,
    );
    return () => clearTimeout(t);
  }, [q, store, tick]);
  useEffect(() => {
    loadHistory().then(setScans);
    const off = onHistory(setScans);
    return () => { off(); };
  }, []);

  const list = useMemo(() => {
    const real = rows.filter((r) => !r.is_fake);
    if (filter === 'fakes') return rows.filter((r) => r.is_fake);
    if (filter === 'new') return real.filter((r) => r.confirmations <= 1);
    if (filter === 'hot') return real.filter((r) => r.confirmations >= 2).sort((a, b) => b.confirmations - a.confirmations);
    return [...real].sort((a, b) => b.confirmations - a.confirmations);
  }, [rows, filter]);
  const myScans = useMemo(() => {
    const s = q.trim().toLowerCase();
    return scans.filter((x) => x.name && (!s || `${x.name} ${x.set}`.toLowerCase().includes(s)));
  }, [scans, q]);
  const cols = L.tablet ? 3 : 2;

  return (
    <ScrollView style={S.screen} contentContainerStyle={{ padding: L.gutter, paddingTop: L.sp(8), gap: L.sp(14), paddingBottom: L.sp(40) }} keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={loading && !!rows.length} onRefresh={() => setTick((n) => n + 1)} tintColor={C.lime} />}>
      <ScreenTitle title="Community"
        right={
          <Pressable onPress={() => { setSearchOpen(!searchOpen); if (searchOpen) setQ(''); }} hitSlop={8} accessibilityLabel="Search the community catalog"
            style={{ width: L.sp(40), height: L.sp(40), borderRadius: L.sp(20), backgroundColor: searchOpen ? C.blue : C.surface, alignItems: 'center', justifyContent: 'center' }}>
            <Icon name={searchOpen ? 'close' : 'search'} size={L.fs(searchOpen ? 14 : 18)} color={C.ink} />
          </Pressable>
        } />
      {searchOpen ? (
        <View style={[S.row, { gap: 8, backgroundColor: C.surface, borderRadius: L.sp(14), borderWidth: 1, borderColor: C.line, paddingHorizontal: L.sp(12), height: L.sp(46) }]}>
          <Icon name="search" size={L.fs(17)} color={C.ink2} />
          <TextInput value={q} onChangeText={setQ} autoFocus placeholder="Search player, card or set" placeholderTextColor={C.ink2} autoCorrect={false} style={{ flex: 1, color: C.ink, fontSize: L.fs(15), paddingVertical: 0 }} />
        </View>
      ) : null}
      <Pills options={FILTERS} value={filter} onChange={setFilter} labels={LABELS} />

      {stats ? (
        <View style={[S.row, { gap: 8 }]}>
          {([['Cards known', stats.cards], ['Fakes reported', stats.fakes], ['Sales added', stats.sales]] as [string, number][]).map(([l, v]) => (
            <View key={l} style={{ flex: 1, backgroundColor: C.surface, borderRadius: L.sp(16), padding: L.sp(12), gap: 2 }}>
              <Text style={{ color: C.ink, fontWeight: '900', fontSize: L.fs(20), fontVariant: ['tabular-nums'] }} numberOfLines={1} adjustsFontSizeToFit>{v.toLocaleString()}</Text>
              <Text style={{ color: C.ink2, fontWeight: '600', fontSize: L.fs(11) }} numberOfLines={1}>{l}</Text>
            </View>
          ))}
        </View>
      ) : null}
      <Text style={[S.muted, { fontSize: L.fs(12) }]}>
        {HINTS[filter]}{' '}
        {filter !== 'mine' ? (store.shared ? 'Shared with everyone using Slab Scout.' : 'Kept on this phone only; connect a free Supabase project in Settings to share.') : ''}
      </Text>
      {err ? <Text style={[S.body, { color: C.crit }]}>{err}</Text> : null}

      {filter === 'mine' ? (
        <TileGrid items={myScans} cols={cols} keyOf={(x) => x.id}
          render={(x, w) => (
            <FeedCard w={w} b64={x.thumb} title={x.name} sub={[x.set, x.number && `#${x.number}`].filter(Boolean).join(' · ')}
              tags={[x.added ? 'In collection' : '', x.wish ? 'Wishlist' : '', new Date(x.at).toLocaleDateString()].filter(Boolean)}
              price={x.price != null ? (x.currency === 'EUR' ? `€${x.price.toFixed(2)}` : money(x.price)) : ''}
              onPress={x.catalog_key ? () => app.openCard(x.catalog_key!) : undefined} />
          )} />
      ) : (
        <TileGrid items={list} cols={cols} keyOf={(r) => r.id}
          render={(r, w) => (
            <FeedCard w={w} b64={r.thumb} title={r.name} sub={[r.set_name, r.number && `#${r.number}`].filter(Boolean).join(' · ')}
              tags={[r.game, r.rarity, `seen ${r.confirmations}×`].filter(Boolean)} fake={r.is_fake ? r.fake_reasons || 'Reported fake' : undefined} />
          )} />
      )}
      {(filter === 'mine' ? !myScans.length : !list.length) && !loading ? (
        <View style={[S.card, { alignItems: 'center', paddingVertical: L.sp(26), borderRadius: L.sp(20) }]}>
          <Text style={[S.h3, { fontSize: L.fs(16) }]}>Nothing here yet</Text>
          <Text style={[S.muted, { textAlign: 'center' }]}>{filter === 'mine' ? 'Cards you scan show up here.' : 'Confirm a scan for the community (from the grading screen) to add the first one.'}</Text>
        </View>
      ) : null}
    </ScrollView>
  );
}

function FeedCard({ w, b64, title, sub, tags, price, fake, onPress }: { w: number; b64?: string; title: string; sub: string; tags: string[]; price?: string; fake?: string; onPress?: () => void }) {
  const L = useLayout();
  return (
    <Pressable disabled={!onPress} onPress={onPress} style={({ pressed }) => [{ width: w, backgroundColor: C.surface, borderRadius: L.sp(20), overflow: 'hidden', borderWidth: 1, borderColor: fake ? C.crit : C.lineSoft }, pressed && { opacity: 0.8 }]}>
      <View style={{ width: '100%', aspectRatio: 4 / 4.2, backgroundColor: C.surface3, alignItems: 'center', justifyContent: 'center', padding: L.sp(10) }}>
        {b64 ? <Image source={{ uri: `data:image/jpeg;base64,${b64}` }} style={{ height: '100%', aspectRatio: 63 / 88, borderRadius: L.sp(8) }} resizeMode="cover" /> : <Icon name="cards" size={L.fs(34)} color={C.ink3} />}
        {fake ? (
          <View style={{ position: 'absolute', left: 8, top: 8, backgroundColor: C.critSoft, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
            <Text style={{ color: C.crit, fontWeight: '800', fontSize: L.fs(11) }}>🚩 Fake</Text>
          </View>
        ) : null}
      </View>
      <View style={{ padding: L.sp(10), gap: 3 }}>
        <View style={[S.row, { gap: 4 }]}>
          <Text style={{ flex: 1, color: C.ink, fontWeight: '800', fontSize: L.fs(14) }} numberOfLines={1}>{title}</Text>
          {price ? <Text style={{ color: C.lime, fontWeight: '800', fontSize: L.fs(13), fontVariant: ['tabular-nums'] }}>{price}</Text> : null}
        </View>
        {sub ? <Text style={{ color: C.ink2, fontSize: L.fs(12) }} numberOfLines={1}>{sub}</Text> : null}
        <Text style={{ color: C.ink3, fontSize: L.fs(11), fontWeight: '600' }} numberOfLines={1}>{tags.join(' · ')}</Text>
        {fake && fake !== 'Reported fake' ? <Text style={{ color: C.crit, fontSize: L.fs(11) }} numberOfLines={2}>{fake}</Text> : null}
      </View>
    </Pressable>
  );
}
