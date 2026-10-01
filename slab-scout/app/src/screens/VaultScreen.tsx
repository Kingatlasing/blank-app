/** Collection: a profile page. Cover + avatar + stats + name collapse into a compact bar on scroll, and the tab row
 * (Insights | Collection | Sets | Binders | Wishlist) sticks under it. */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Animated, Image, Modal, Pressable, RefreshControl, ScrollView, Share, Text, TextInput, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { C, S, money, pctText } from '../theme';
import { Btn } from '../components/ui';
import { Carousel, CardTile, ChangeChip, SearchField, SectionTitle, Sheet, SheetOption, SquareBtn, TileGrid, ValueChart } from '../components/cards';
import { Gradient, GradientBorder, Icon, alpha } from '../components/visual';
import RecordSheet from '../components/RecordSheet';
import type { VaultRecord } from '../core/community';
import { sets as catSets } from '../core/catalog';
import { changeOver, currentValue, gradeWorthy, groupRecords, isGraded, recordImage, recordSetId, RecordGroup } from '../core/portfolio';
import { addToBinder, Binder, createBinder, deleteBinder, loadBinders, normalizeHex, saveBinders } from '../core/binders';
import { keepPhoto } from '../storage';
import { useApp } from '../appContext';
import { Layout, useLayout } from '../layout';
import { useCollection, useValueHistory } from '../portfolioHooks';
import { BINDER_COLORS } from '../theme';

type TabId = 'insights' | 'collection' | 'sets' | 'binders' | 'wishlist';
const TABS: [TabId, string][] = [['insights', 'Insights'], ['collection', 'Collection'], ['sets', 'Sets'], ['binders', 'Binders'], ['wishlist', 'Wishlist']];
type Sort = 'value_desc' | 'value_asc' | 'name' | 'newest' | 'set';
const SORTS: [Sort, string][] = [['value_desc', 'Value: high to low'], ['value_asc', 'Value: low to high'], ['name', 'Name (A–Z)'], ['newest', 'Newest added'], ['set', 'Set']];
type Graded = 'all' | 'graded' | 'raw';
interface Filters { category: string; set: string; graded: Graded }
const NO_FILTERS: Filters = { category: 'All', set: 'All', graded: 'all' };

const sortGroups = (gs: RecordGroup[], s: Sort) => {
  const out = [...gs];
  const newest = (g: RecordGroup) => g.recs.reduce((m, r) => (r.added_at > m ? r.added_at : m), '');
  if (s === 'value_desc') out.sort((a, b) => b.value - a.value);
  if (s === 'value_asc') out.sort((a, b) => a.value - b.value);
  if (s === 'name') out.sort((a, b) => (a.rec.card?.name || '').localeCompare(b.rec.card?.name || ''));
  if (s === 'newest') out.sort((a, b) => newest(b).localeCompare(newest(a)));
  if (s === 'set') out.sort((a, b) => (a.rec.card?.set || '').localeCompare(b.rec.card?.set || '') || (a.rec.card?.number || '').localeCompare(b.rec.card?.number || '', undefined, { numeric: true }));
  return out;
};

export default function VaultScreen() {
  const app = useApp();
  const L = useLayout();
  const { items, total } = useCollection();
  const hist = useValueHistory(total);
  const wish = useMemo(() => app.vault.filter((r) => r.list === 'wishlist'), [app.vault]);
  const [tab, setTab] = useState<TabId>('insights');
  const [binders, setBinders] = useState<Binder[]>([]);
  useEffect(() => {
    loadBinders().then(setBinders);
  }, []);

  // sheets / modals
  const [openRec, setOpenRec] = useState<VaultRecord | null>(null);
  const [nameSheet, setNameSheet] = useState(false);
  const [menu, setMenu] = useState(false);
  const [createFor, setCreateFor] = useState<string[] | null>(null); // record ids to put in the new binder
  const [binderPick, setBinderPick] = useState<string[] | null>(null); // "Add to binder" for these ids
  const [openBinder, setOpenBinder] = useState<string | null>(null);

  // collection tab
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<Sort>('value_desc');
  const [sortSheet, setSortSheet] = useState(false);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [filterSheet, setFilterSheet] = useState(false);

  const groups = useMemo(() => groupRecords(items), [items]);
  const shownGroups = useMemo(() => {
    const s = q.trim().toLowerCase();
    let g = groups;
    if (s) g = g.filter((x) => `${x.rec.card?.name} ${x.rec.card?.set} ${x.rec.card?.number} ${x.rec.card?.rarity} ${x.rec.card?.variant}`.toLowerCase().includes(s));
    if (filters.category !== 'All') g = g.filter((x) => (x.rec.card?.game || 'Other') === filters.category);
    if (filters.set !== 'All') g = g.filter((x) => (x.rec.card?.set || 'Other') === filters.set);
    if (filters.graded !== 'all') g = g.filter((x) => isGraded(x.rec) === (filters.graded === 'graded'));
    return sortGroups(g, sort);
  }, [groups, q, filters, sort]);
  const wishGroups = useMemo(() => sortGroups(groupRecords(wish), 'value_desc'), [wish]);
  const setCount = useMemo(() => new Set(items.map((r) => r.card?.set || '')).size, [items]);
  const gradedCount = useMemo(() => items.filter(isGraded).length, [items]);
  const filtersOn = filters.category !== 'All' || filters.set !== 'All' || filters.graded !== 'all';

  // collapsing header
  const scrollY = useRef(new Animated.Value(0)).current;
  const [headH, setHeadH] = useState(0);
  const [tabH, setTabH] = useState(L.sp(46));
  const barH = L.top + L.sp(48);
  const stickAt = Math.max(1, headH - barH);
  const barOpacity = scrollY.interpolate({ inputRange: [Math.max(0, stickAt - L.sp(70)), stickAt], outputRange: [0, 1], extrapolate: 'clamp' });

  async function pickPhoto(kind: 'avatar' | 'cover') {
    try {
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, aspect: kind === 'avatar' ? [1, 1] : [16, 9], quality: 0.85 });
      if (res.canceled || !res.assets?.[0]) return;
      const uri = await keepPhoto(res.assets[0].uri, kind, app.profile[kind]);
      app.setProfile({ ...app.profile, [kind]: uri });
    } catch (e: any) {
      Alert.alert("Couldn't open your photos", String(e?.message || e));
    }
  }
  function share() {
    const top = [...groups].sort((a, b) => b.value - a.value).slice(0, 3).map((g) => `${g.rec.card?.name}${g.rec.card?.number ? ` #${g.rec.card.number}` : ''} (${money(g.value || undefined)})`);
    Share.share({ message: `${app.displayName} on Slab Scout: ${items.length} card${items.length === 1 ? '' : 's'} worth ${money(total)}.${top.length ? `\nTop cards: ${top.join(', ')}` : ''}` }).catch(() => {});
  }
  const openGroup = (g: RecordGroup) => (g.rec.match?.catalog_key ? app.openCard(g.rec.match.catalog_key) : setOpenRec(g.rec));
  const binderOf = (id: string) => binders.find((b) => b.id === id) || null;

  /* ---------- header ---------- */
  const av = L.sp(84);
  const coverH = L.top + L.sp(128);
  const header = (
    <View onLayout={(e) => setHeadH(e.nativeEvent.layout.height)}>
      <Pressable onPress={() => pickPhoto('cover')} accessibilityLabel="Set your cover image" style={{ height: coverH, overflow: 'hidden', backgroundColor: C.hero }}>
        {app.profile.cover ? (
          <Image source={{ uri: app.profile.cover }} style={{ position: 'absolute', width: '100%', height: '100%' }} resizeMode="cover" />
        ) : (
          <Gradient colors={[C.heroTop, C.hero, C.bg]} vertical steps={18} />
        )}
        <View style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, backgroundColor: app.profile.cover ? 'rgba(10,11,16,0.35)' : 'transparent' }} />
        {!app.profile.cover ? (
          <View style={{ flex: 1, paddingTop: L.top, alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            <Icon name="photo" size={L.fs(22)} color={C.ink2} />
            <Text style={{ color: C.ink2, fontWeight: '700', fontSize: L.fs(14) }}>Set your cover image.</Text>
          </View>
        ) : null}
      </Pressable>
      <Pressable onPress={() => setMenu(true)} hitSlop={10} accessibilityLabel="More" style={{ position: 'absolute', right: L.gutter, top: L.top + L.sp(8), width: L.sp(36), height: L.sp(36), borderRadius: L.sp(18), backgroundColor: 'rgba(10,11,16,0.6)', alignItems: 'center', justifyContent: 'center' }}>
        <Icon name="more" size={L.fs(18)} color={C.ink} />
      </Pressable>
      <View style={{ paddingHorizontal: L.gutter, gap: L.sp(10), paddingBottom: L.sp(12) }}>
        <View style={[S.row, { alignItems: 'flex-end', gap: L.sp(12), marginTop: -av / 2 }]}>
          <Pressable onPress={() => pickPhoto('avatar')} accessibilityLabel="Set your profile photo" style={{ width: av, height: av, borderRadius: av / 2, borderWidth: 3, borderColor: C.bg, backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
            {app.profile.avatar ? <Image source={{ uri: app.profile.avatar }} style={{ width: av, height: av }} /> : <Icon name="plus" size={L.fs(26)} color={C.ink} />}
          </Pressable>
          <View style={[S.row, { flex: 1, gap: 2, paddingBottom: L.sp(4) }]}>
            <HeadStat L={L} v={items.length.toLocaleString()} l="Cards" />
            <HeadStat L={L} v={money(total)} l="Value" />
            <HeadStat L={L} v={String(setCount)} l="Sets" />
            <HeadStat L={L} v={String(gradedCount)} l="Graded" />
          </View>
        </View>
        <View style={[S.row, { gap: L.sp(8) }]}>
          <Text style={{ color: C.ink, fontSize: L.fs(24), fontWeight: '900', flexShrink: 1 }} numberOfLines={1}>{app.displayName}</Text>
          <Pressable onPress={() => setNameSheet(true)} hitSlop={8} accessibilityLabel="Edit name" style={{ padding: 4 }}>
            <Icon name="edit" size={L.fs(18)} color={C.ink2} />
          </Pressable>
          <View style={{ flex: 1 }} />
          <Pressable onPress={share} hitSlop={8} accessibilityLabel="Share your collection" style={{ width: L.sp(38), height: L.sp(38), borderRadius: L.sp(19), backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="share" size={L.fs(17)} color={C.ink} />
          </Pressable>
        </View>
      </View>
    </View>
  );

  /* ---------- tab content ---------- */
  const tile = (g: RecordGroup, w: number, onPress: () => void, onLongPress?: () => void, extra: { badge?: string; selected?: boolean } = {}) => (
    <CardTile width={w} title={g.rec.card?.name || 'Card'} number={g.rec.card?.number} rarity={g.rec.card?.rarity} price={money(g.value || undefined)} uri={recordImage(g.rec) || undefined} thumb={g.rec.thumb}
      qty={g.qty} onPress={onPress} onLongPress={onLongPress} {...extra} />
  );
  const empty = (title: string, sub: string, action?: [string, () => void]) => (
    <View style={[S.card, { alignItems: 'center', paddingVertical: L.sp(28), gap: 8 }]}>
      <Text style={[S.h3, { fontSize: L.fs(16) }]}>{title}</Text>
      <Text style={[S.muted, { textAlign: 'center' }]}>{sub}</Text>
      {action ? <Btn primary label={action[0]} onPress={action[1]} style={{ marginTop: 6, alignSelf: 'stretch' }} /> : null}
    </View>
  );

  let body: React.ReactNode = null;
  if (app.needsCode) {
    body = empty('Set a vault code', 'Your vault syncs through the community database. Pick a private vault code (6+ characters) in Settings. Use the same code in the web app to see the same cards.', ['Open Settings', app.openSettings]);
  } else if (tab === 'insights') {
    const doy = Math.max(1, Math.ceil((Date.now() - new Date(new Date().getFullYear(), 0, 1).getTime()) / 864e5));
    const chips = ([['this year', doy], ['this month', 30], ['this week', 7]] as [string, number][])
      .map(([l, d]) => ({ l, c: changeOver(hist, total, d) }))
      .filter((x) => x.c);
    const worthy = gradeWorthy(items);
    body = (
      <View style={{ gap: L.sp(14) }}>
        <View style={{ gap: 2 }}>
          <Text style={{ color: C.ink2, fontWeight: '700', fontSize: L.fs(15) }}>Your Collection</Text>
          <Text style={{ color: C.ink, fontSize: L.fs(40), fontWeight: '900', letterSpacing: -1, fontVariant: ['tabular-nums'] }} numberOfLines={1} adjustsFontSizeToFit>
            {money(total)}
          </Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -L.gutter, flexGrow: 0 }} contentContainerStyle={{ paddingHorizontal: L.gutter, gap: 8 }}>
          {chips.length ? (
            chips.map(({ l, c }) => <ChangeChip key={l} abs={c!.abs} pct={c!.pct} label={l} />)
          ) : (
            <View style={[S.pill, { paddingVertical: L.sp(7) }]}><Text style={{ color: C.ink2, fontWeight: '700', fontSize: L.fs(13) }}>Tracking since {hist[0]?.day || 'today'}</Text></View>
          )}
        </ScrollView>
        {hist.length ? <ValueChart points={hist} /> : null}
        {hist.length < 2 ? <Text style={[S.muted, { fontSize: L.fs(12) }]}>The chart fills in day by day as Slab Scout records your collection's value.</Text> : null}
        {worthy.length ? (
          <View style={{ gap: L.sp(10) }}>
            <SectionTitle title="Grade Worthy" />
            <Text style={[S.muted, { marginTop: -L.sp(6), fontSize: L.fs(13) }]}>Raw cards with the biggest jump from raw to a PSA 10 price.</Text>
            <Carousel>
              {worthy.map((w) => (
                <CardTile key={w.rec.id} width={L.carouselW()} title={w.rec.card?.name || 'Card'} number={w.rec.card?.number} rarity={w.rec.card?.rarity} price={money(w.raw)} uri={recordImage(w.rec) || undefined} thumb={w.rec.thumb}
                  badge={`▲ ${pctText(w.pct)}`} onPress={() => (w.rec.match?.catalog_key ? app.openCard(w.rec.match.catalog_key) : setOpenRec(w.rec))} />
              ))}
            </Carousel>
          </View>
        ) : null}
        {!items.length ? empty('Your collection is empty', 'Scan a card, or add one from Explore, to start tracking its value.', ['Scan a card', () => app.goTab('scan')]) : null}
      </View>
    );
  } else if (tab === 'collection') {
    body = (
      <View style={{ gap: L.sp(12) }}>
        <Text style={[S.h2, { fontSize: L.fs(20) }]}>All cards</Text>
        <View style={[S.row, { gap: 8 }]}>
          <SearchField value={q} onChangeText={setQ} placeholder="Search cards" />
          <SquareBtn name="sort" label="Sort" onPress={() => setSortSheet(true)} on={sort !== 'value_desc'} />
          <SquareBtn name="filter" label="Filter" onPress={() => setFilterSheet(true)} on={filtersOn} />
        </View>
        {app.vaultErr ? <Text style={[S.body, { color: C.crit }]}>{app.vaultErr}</Text> : null}
        {app.vaultLoading && !items.length ? <Text style={S.muted}>Loading…</Text> : null}
        {shownGroups.length ? (
          <Text style={[S.muted, { fontSize: L.fs(12) }]}>{shownGroups.reduce((s, g) => s + g.qty, 0)} cards · {money(shownGroups.reduce((s, g) => s + g.value * g.qty, 0))} · hold a card to add it to a binder</Text>
        ) : null}
        <TileGrid items={shownGroups} keyOf={(g) => g.key} render={(g, w) => tile(g, w, () => openGroup(g), () => setBinderPick(g.recs.map((r) => r.id)))} />
        {!shownGroups.length && !app.vaultLoading
          ? items.length
            ? empty('No cards match', 'Try another search or clear the filters.', ['Clear filters', () => { setQ(''); setFilters(NO_FILTERS); }])
            : empty('Your collection is empty', 'Scan a card, or add one from Explore.', ['Scan a card', () => app.goTab('scan')])
          : null}
      </View>
    );
  } else if (tab === 'sets') {
    const bySet = new Map<string, VaultRecord[]>();
    items.forEach((r) => {
      const k = r.card?.set || 'Other';
      bySet.set(k, [...(bySet.get(k) || []), r]);
    });
    const rows = [...bySet.entries()]
      .map(([name, recs]) => {
        const sid = recs.map(recordSetId).find(Boolean) || '';
        const info = sid ? catSets()[sid] : undefined;
        const uniq = new Set(recs.map((r) => r.match?.catalog_key).filter(Boolean)).size;
        return { name, recs, sid, info, value: recs.reduce((s, r) => s + currentValue(r), 0), pct: info?.cards ? Math.min(100, (uniq / info.cards) * 100) : null };
      })
      .sort((a, b) => b.value - a.value);
    body = (
      <View style={{ gap: L.sp(10) }}>
        <Text style={[S.h2, { fontSize: L.fs(20) }]}>Sets</Text>
        {rows.map((s) => {
          const img = recordImage(s.recs[0]);
          return (
            <Pressable key={s.name} onPress={() => (s.sid && s.info ? app.openSet(s.sid) : (setFilters({ ...NO_FILTERS, set: s.name }), setTab('collection')))}
              style={({ pressed }) => [S.row, { backgroundColor: C.surface, borderRadius: L.sp(18), padding: L.sp(12), gap: L.sp(12) }, pressed && { opacity: 0.75 }]}>
              <View style={{ width: L.sp(44), height: L.sp(61), borderRadius: 8, overflow: 'hidden', backgroundColor: C.surface3 }}>
                {img || s.recs[0].thumb ? <Image source={{ uri: img || `data:image/jpeg;base64,${s.recs[0].thumb}` }} style={{ width: '100%', height: '100%' }} /> : null}
              </View>
              <View style={{ flex: 1, gap: 4, minWidth: 0 }}>
                <Text style={{ color: C.ink, fontWeight: '800', fontSize: L.fs(15) }} numberOfLines={1}>{s.name}</Text>
                <Text style={{ color: C.ink2, fontSize: L.fs(12) }} numberOfLines={1}>
                  {s.recs.length} card{s.recs.length === 1 ? '' : 's'}{s.pct != null ? ` · ${s.pct < 10 ? s.pct.toFixed(1) : Math.round(s.pct)}% of ${s.info!.cards.toLocaleString()}` : ''}
                </Text>
                {s.pct != null ? (
                  <View style={{ height: 5, borderRadius: 3, backgroundColor: C.surface2, overflow: 'hidden' }}>
                    <View style={{ height: 5, width: `${Math.max(2, s.pct)}%`, backgroundColor: C.blue }} />
                  </View>
                ) : null}
              </View>
              <Text style={{ color: C.lime, fontWeight: '800', fontSize: L.fs(14), fontVariant: ['tabular-nums'] }}>{money(s.value)}</Text>
              <Icon name="forward" size={L.fs(14)} color={C.ink2} />
            </Pressable>
          );
        })}
        {!rows.length ? empty('No sets yet', 'Cards you add are grouped by their set here.') : null}
      </View>
    );
  } else if (tab === 'binders') {
    const cols = L.tablet ? 4 : 2;
    type Cell = { id: string; b?: Binder };
    const cells: Cell[] = [{ id: '__new' }, ...binders.map((b) => ({ id: b.id, b }))];
    body = (
      <View style={{ gap: L.sp(12) }}>
        <Text style={[S.h2, { fontSize: L.fs(20) }]}>Binders</Text>
        <TileGrid items={cells} cols={cols} keyOf={(c) => c.id}
          render={(c, w) => {
            const h = Math.round(w * 1.3);
            if (!c.b)
              return (
                <Pressable onPress={() => setCreateFor([])} accessibilityLabel="Create a new binder" style={({ pressed }) => [{ width: w, height: h, borderRadius: L.sp(20), borderWidth: 1.5, borderStyle: 'dashed', borderColor: C.line, backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center', gap: 8 }, pressed && { opacity: 0.75 }]}>
                  <View style={{ width: L.sp(46), height: L.sp(46), borderRadius: L.sp(23), backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center' }}>
                    <Icon name="plus" size={L.fs(20)} color={C.ink} />
                  </View>
                  <Text style={{ color: C.ink, fontWeight: '800', fontSize: L.fs(15) }}>Create New</Text>
                </Pressable>
              );
            const b = c.b;
            const recs = items.filter((r) => b.cardIds.includes(r.id));
            return (
              <Pressable onPress={() => setOpenBinder(b.id)} style={({ pressed }) => [{ width: w, gap: 6 }, pressed && { opacity: 0.8 }]}>
                <BinderCover L={L} color={b.color} w={w} h={h - L.sp(44)} name={b.name} locked={b.private} />
                <View style={[S.row, { justifyContent: 'space-between', gap: 4 }]}>
                  <Text style={{ color: C.ink2, fontSize: L.fs(12), fontWeight: '700' }}>{recs.length} card{recs.length === 1 ? '' : 's'}</Text>
                  <Text style={{ color: C.lime, fontSize: L.fs(13), fontWeight: '800', fontVariant: ['tabular-nums'] }}>{money(recs.reduce((s, r) => s + currentValue(r), 0))}</Text>
                </View>
              </Pressable>
            );
          }}
        />
        <Text style={[S.muted, { fontSize: L.fs(12) }]}>Binders are kept on this phone. Hold any card in the Collection tab to add it to a binder.</Text>
      </View>
    );
  } else if (tab === 'wishlist') {
    body = (
      <View style={{ gap: L.sp(12) }}>
        <Text style={[S.h2, { fontSize: L.fs(20) }]}>Wishlist</Text>
        <TileGrid items={wishGroups} keyOf={(g) => g.key} render={(g, w) => tile(g, w, () => openGroup(g), () => setOpenRec(g.rec))} />
        {!wishGroups.length ? empty('Your wishlist is empty', 'Tap the bookmark on any card page, or ♡ after a scan, to save cards you want.', ['Explore cards', () => app.goTab('explore')]) : null}
      </View>
    );
  }

  /* ---------- filter options ---------- */
  const categories = ['All', ...new Set(items.map((r) => r.card?.game || 'Other'))];
  const setNames = ['All', ...[...new Set(items.filter((r) => filters.category === 'All' || (r.card?.game || 'Other') === filters.category).map((r) => r.card?.set || 'Other'))].sort()];
  const ob = openBinder ? binderOf(openBinder) : null;

  return (
    <View style={S.screen}>
      <Animated.ScrollView
        scrollEventThrottle={16}
        onScroll={Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], { useNativeDriver: true })}
        contentContainerStyle={{ paddingBottom: L.sp(40) }}
        keyboardShouldPersistTaps="handled"
        refreshControl={<RefreshControl refreshing={app.vaultLoading} onRefresh={app.refreshVault} tintColor={C.lime} progressViewOffset={L.top} />}
      >
        {header}
        {/* room for the tab row, which floats above the list (below) so it can stick under the compact bar */}
        <View style={{ height: tabH }} />
        <View style={{ paddingHorizontal: L.gutter, paddingTop: L.sp(16) }}>{body}</View>
      </Animated.ScrollView>

      {/* tab row: follows the content, then sticks under the compact bar */}
      <Animated.View onLayout={(e) => setTabH(e.nativeEvent.layout.height)}
        style={{ position: 'absolute', left: 0, right: 0, top: 0, opacity: headH ? 1 : 0, transform: [{ translateY: scrollY.interpolate({ inputRange: [0, stickAt], outputRange: [headH, headH - stickAt], extrapolateRight: 'clamp' }) }] }}>
        <TabRow L={L} value={tab} onChange={setTab} />
      </Animated.View>

      {/* compact bar shown once the header has scrolled away */}
      <Animated.View pointerEvents="box-none" style={{ position: 'absolute', left: 0, right: 0, top: 0, height: barH, paddingTop: L.top, backgroundColor: C.bg, opacity: barOpacity, flexDirection: 'row', alignItems: 'center', paddingHorizontal: L.gutter }}>
        <View pointerEvents="none" style={{ flex: 1, paddingLeft: L.sp(36) }}>
          <Text style={{ textAlign: 'center', color: C.ink, fontWeight: '800', fontSize: L.fs(17) }} numberOfLines={1}>{app.displayName}</Text>
        </View>
        <Pressable onPress={() => setMenu(true)} hitSlop={10} accessibilityLabel="More" style={{ width: L.sp(36), alignItems: 'flex-end' }}>
          <Icon name="more" size={L.fs(18)} color={C.ink} />
        </Pressable>
      </Animated.View>

      <RecordSheet rec={openRec} onClose={() => setOpenRec(null)} onOpenCard={app.openCard} />

      <Sheet visible={menu} onClose={() => setMenu(false)} title="Profile">
        <SheetOption label="Change profile photo" onPress={() => { setMenu(false); pickPhoto('avatar'); }} />
        <SheetOption label="Change cover image" onPress={() => { setMenu(false); pickPhoto('cover'); }} />
        {app.profile.cover ? <SheetOption label="Remove cover image" onPress={() => { setMenu(false); app.setProfile({ ...app.profile, cover: '' }); }} /> : null}
        <SheetOption label="Edit name" onPress={() => { setMenu(false); setNameSheet(true); }} />
        <SheetOption label="Share collection" onPress={() => { setMenu(false); share(); }} />
        <SheetOption label="Settings" onPress={() => { setMenu(false); app.openSettings(); }} />
      </Sheet>

      <NameSheet visible={nameSheet} initial={app.profile.name} onClose={() => setNameSheet(false)} onSave={(name) => { app.setProfile({ ...app.profile, name }); setNameSheet(false); }} />

      <Sheet visible={sortSheet} onClose={() => setSortSheet(false)} title="Sort by">
        {SORTS.map(([id, label]) => <SheetOption key={id} label={label} on={sort === id} onPress={() => { setSort(id); setSortSheet(false); }} />)}
      </Sheet>

      <Sheet visible={filterSheet} onClose={() => setFilterSheet(false)} title="Filter">
        <Text style={S.eyebrow}>Category</Text>
        <PillWrap options={categories} value={filters.category} onChange={(v) => setFilters({ ...filters, category: v, set: 'All' })} />
        <Text style={S.eyebrow}>Set</Text>
        <PillWrap options={setNames} value={filters.set} onChange={(v) => setFilters({ ...filters, set: v })} />
        <Text style={S.eyebrow}>Graded / raw</Text>
        <PillWrap options={['all', 'graded', 'raw']} labels={{ all: 'All', graded: 'Graded', raw: 'Raw' }} value={filters.graded} onChange={(v) => setFilters({ ...filters, graded: v as Graded })} />
        <View style={[S.row, { marginTop: 4 }]}>
          <Btn label="Clear" style={{ flex: 1 }} onPress={() => setFilters(NO_FILTERS)} />
          <Btn primary label="Show cards" style={{ flex: 1.4 }} onPress={() => setFilterSheet(false)} />
        </View>
      </Sheet>

      <Sheet visible={!!binderPick} onClose={() => setBinderPick(null)} title="Add to binder">
        {binders.map((b) => (
          <SheetOption key={b.id} label={b.name} sub={`${b.cardIds.length} card${b.cardIds.length === 1 ? '' : 's'}`} on={!!binderPick && binderPick.every((id) => b.cardIds.includes(id))}
            right={<View style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: b.color, marginRight: 8 }} />}
            onPress={async () => { setBinders(await addToBinder(b.id, binderPick || [])); setBinderPick(null); }} />
        ))}
        <SheetOption label="Create new binder" sub="And put this card in it" right={<Icon name="plus" size={L.fs(16)} color={C.ink} />} onPress={() => { const ids = binderPick || []; setBinderPick(null); setTimeout(() => setCreateFor(ids), 350); }} />
      </Sheet>

      <CreateBinderSheet visible={!!createFor} onClose={() => setCreateFor(null)}
        onCreate={async (b) => {
          const list = await createBinder({ ...b, cardIds: createFor || [] });
          setBinders(list);
          setCreateFor(null);
          setTab('binders');
        }} />

      <BinderPage binder={ob} groupsAll={groups} items={items} onClose={() => setOpenBinder(null)}
        onChange={async (b) => { const list = binders.map((x) => (x.id === b.id ? b : x)); await saveBinders(list); setBinders(list); }}
        onDelete={async (id) => { setBinders(await deleteBinder(id)); setOpenBinder(null); }}
        onOpen={(g) => { setOpenBinder(null); openGroup(g); }} />
    </View>
  );
}

/* ---------- pieces ---------- */
function HeadStat({ L, v, l }: { L: Layout; v: string; l: string }) {
  return (
    <View style={{ flex: 1, alignItems: 'center', gap: 1, minWidth: 0 }}>
      <Text style={{ color: C.ink, fontSize: L.fs(17), fontWeight: '900', fontVariant: ['tabular-nums'] }} numberOfLines={1} adjustsFontSizeToFit>{v}</Text>
      <Text style={{ color: C.ink2, fontSize: L.fs(12), fontWeight: '600' }} numberOfLines={1}>{l}</Text>
    </View>
  );
}

function TabRow({ L, value, onChange }: { L: Layout; value: TabId; onChange: (t: TabId) => void }) {
  return (
    <View style={{ backgroundColor: C.bg, borderBottomWidth: 1, borderBottomColor: C.line }}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ flexGrow: 1, paddingHorizontal: L.gutter - L.sp(8) }}>
        {TABS.map(([id, label]) => {
          const on = value === id;
          return (
            <Pressable key={id} onPress={() => onChange(id)} style={{ flexGrow: 1, alignItems: 'center', paddingHorizontal: L.sp(8), paddingTop: L.sp(12) }}>
              <Text style={{ color: on ? C.ink : C.ink2, fontWeight: on ? '800' : '600', fontSize: L.fs(15) }} numberOfLines={1}>{label}</Text>
              <View style={{ height: 3, borderRadius: 2, alignSelf: 'stretch', marginTop: L.sp(10), marginBottom: -1, backgroundColor: on ? C.ink : 'transparent' }} />
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

function PillWrap({ options, value, onChange, labels }: { options: string[]; value: string; onChange: (v: string) => void; labels?: Record<string, string> }) {
  const L = useLayout();
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
      {options.map((o) => {
        const on = o === value;
        return (
          <Pressable key={o} onPress={() => onChange(o)} style={[S.pill, { paddingVertical: L.sp(7), paddingHorizontal: L.sp(13), backgroundColor: on ? C.blue : C.surface2, borderColor: on ? C.blue : C.line }]}>
            <Text style={{ color: on ? '#fff' : C.ink2, fontWeight: '700', fontSize: L.fs(13) }} numberOfLines={1}>{labels?.[o] || o}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

/** Binder cover: tinted rounded rect, darker spine, soft gradient and a dashed "stitched" inner border. */
export function BinderCover({ L, color, w, h, name, locked }: { L: Layout; color: string; w: number; h: number; name?: string; locked?: boolean }) {
  const r = L.sp(18);
  return (
    <View style={{ width: w, height: h, borderRadius: r, backgroundColor: color, overflow: 'hidden' }}>
      <Gradient vertical steps={14} colors={[alpha('#FFFFFF', 0.22), alpha('#FFFFFF', 0.04), alpha('#000000', 0.28)]} />
      <View style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: Math.max(8, w * 0.08), backgroundColor: alpha('#000000', 0.22) }} />
      <View style={{ position: 'absolute', left: Math.max(8, w * 0.08) + L.sp(7), right: L.sp(8), top: L.sp(8), bottom: L.sp(8), borderRadius: r - 6, borderWidth: 1.5, borderStyle: 'dashed', borderColor: alpha('#FFFFFF', 0.55) }} />
      {locked ? (
        <View style={{ position: 'absolute', right: L.sp(14), top: L.sp(14) }}>
          <Icon name="lock" size={L.fs(14)} color={alpha('#FFFFFF', 0.85)} />
        </View>
      ) : null}
      {name ? (
        <View style={{ position: 'absolute', left: Math.max(8, w * 0.08) + L.sp(14), right: L.sp(14), bottom: L.sp(16) }}>
          <Text style={{ color: '#fff', fontWeight: '900', fontSize: L.fs(16), textShadowColor: 'rgba(0,0,0,0.45)', textShadowRadius: 4 }} numberOfLines={2}>{name}</Text>
        </View>
      ) : null}
    </View>
  );
}

function NameSheet({ visible, initial, onClose, onSave }: { visible: boolean; initial: string; onClose: () => void; onSave: (n: string) => void }) {
  const L = useLayout();
  const [v, setV] = useState(initial);
  useEffect(() => {
    if (visible) setV(initial);
  }, [visible, initial]);
  return (
    <Sheet visible={visible} onClose={onClose} title="Your name">
      <TextInput value={v} onChangeText={setV} placeholder="My Collection" placeholderTextColor={C.ink2} autoFocus maxLength={40} style={[S.input, { backgroundColor: C.surface2, fontSize: L.fs(16) }]} onSubmitEditing={() => onSave(v.trim())} returnKeyType="done" />
      <Text style={S.muted}>Shown on Discover and your Collection. Kept on this phone.</Text>
      <Btn primary label="Save" onPress={() => onSave(v.trim())} />
    </Sheet>
  );
}

const RAINBOW = ['#FF5A4A', '#FFC93C', '#3DDC84', '#4FCFE8', '#4F5BF5', '#A100FF', '#F78FE3'];

function CreateBinderSheet({ visible, onClose, onCreate }: { visible: boolean; onClose: () => void; onCreate: (b: { name: string; color: string; private: boolean }) => void }) {
  const L = useLayout();
  const [name, setName] = useState('');
  const [color, setColor] = useState(BINDER_COLORS[0]);
  const [custom, setCustom] = useState(false);
  const [hex, setHex] = useState('');
  const [priv, setPriv] = useState(false);
  useEffect(() => {
    if (visible) {
      setName('');
      setColor(BINDER_COLORS[0]);
      setCustom(false);
      setHex('');
      setPriv(false);
    }
  }, [visible]);
  const shown = custom ? normalizeHex(hex) || '#3A3A44' : color;
  const ok = name.trim().length > 0;
  const sw = L.sp(34);
  const pw = Math.min(L.sp(150), L.width * 0.4);
  return (
    <Sheet visible={visible} onClose={onClose} title="New binder">
      <View style={{ alignItems: 'center', paddingVertical: L.sp(4) }}>
        <BinderCover L={L} color={shown} w={pw} h={Math.round(pw * 1.3)} name={name.trim() || 'Binder name'} locked={priv} />
      </View>
      <Text style={S.eyebrow}>Name</Text>
      <TextInput value={name} onChangeText={setName} placeholder="Binder name" placeholderTextColor={C.ink2} maxLength={40} style={[S.input, { backgroundColor: C.surface2, fontSize: L.fs(16) }]} />
      <Text style={S.eyebrow}>Color</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: L.sp(10) }}>
        {BINDER_COLORS.map((c) => {
          const on = !custom && color === c;
          return (
            <Pressable key={c} onPress={() => { setCustom(false); setColor(c); }} accessibilityLabel={`Colour ${c}`} style={{ width: sw + 6, height: sw + 6, borderRadius: sw, borderWidth: 2, borderColor: on ? C.ink : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
              <View style={{ width: sw, height: sw, borderRadius: sw / 2, backgroundColor: c }} />
            </Pressable>
          );
        })}
        <Pressable onPress={() => setCustom(true)} accessibilityLabel="Custom colour" style={{ width: sw + 6, height: sw + 6, borderRadius: sw, borderWidth: 2, borderColor: custom ? C.ink : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
          <GradientBorder radius={sw / 2} width={4} colors={RAINBOW} style={{ width: sw, height: sw }} innerStyle={{ flex: 1, backgroundColor: custom ? shown : C.surface, alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="plus" size={L.fs(11)} color={C.ink} />
          </GradientBorder>
        </Pressable>
      </View>
      {custom ? (
        <View style={[S.row, { gap: 8 }]}>
          <View style={[S.row, { flex: 1, gap: 6, backgroundColor: C.surface2, borderRadius: L.sp(12), paddingHorizontal: L.sp(12), height: L.sp(44), borderWidth: 1, borderColor: hex && !normalizeHex(hex) ? C.crit : C.line }]}>
            <Text style={{ color: C.ink2, fontWeight: '800', fontSize: L.fs(16) }}>#</Text>
            <TextInput value={hex.replace(/^#/, '')} onChangeText={(t) => setHex(t.replace(/[^0-9a-fA-F]/g, '').slice(0, 6))} placeholder="4F5BF5" placeholderTextColor={C.ink3} autoCapitalize="characters" autoCorrect={false} maxLength={6}
              style={{ flex: 1, color: C.ink, fontSize: L.fs(16), paddingVertical: 0, fontVariant: ['tabular-nums'] }} />
          </View>
          <Btn label="Clear" onPress={() => setHex('')} style={{ paddingVertical: L.sp(10) }} />
        </View>
      ) : null}
      <Pressable onPress={() => setPriv(!priv)} style={[S.row, { gap: L.sp(12), paddingVertical: 4 }]} accessibilityRole="checkbox" accessibilityState={{ checked: priv }}>
        <View style={{ width: L.sp(24), height: L.sp(24), borderRadius: 7, borderWidth: 2, borderColor: priv ? C.blue : C.ink3, backgroundColor: priv ? C.blue : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
          {priv ? <Icon name="check" size={L.fs(14)} color="#fff" /> : null}
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: C.ink, fontWeight: '800', fontSize: L.fs(15) }}>Private</Text>
          <Text style={{ color: C.ink2, fontSize: L.fs(12) }}>Only you can see this binder</Text>
        </View>
      </Pressable>
      <Pressable disabled={!ok} onPress={() => onCreate({ name: name.trim(), color: shown, private: priv })}
        style={({ pressed }) => [{ backgroundColor: C.blue, borderRadius: 999, paddingVertical: L.sp(15), alignItems: 'center', opacity: ok ? 1 : 0.4 }, pressed && ok && { opacity: 0.8 }]}>
        <Text style={{ color: '#fff', fontWeight: '900', fontSize: L.fs(16) }}>Create Binder</Text>
      </Pressable>
    </Sheet>
  );
}

/** One binder: its cards in the grid, "Add cards" from the collection (checkboxes), long-press to take a card out. */
function BinderPage({ binder, groupsAll, items, onClose, onChange, onDelete, onOpen }: {
  binder: Binder | null; groupsAll: RecordGroup[]; items: VaultRecord[]; onClose: () => void; onChange: (b: Binder) => void; onDelete: (id: string) => void; onOpen: (g: RecordGroup) => void;
}) {
  const L = useLayout();
  const [adding, setAdding] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [menu, setMenu] = useState(false);
  useEffect(() => {
    setAdding(false);
    setSel(new Set());
  }, [binder?.id]);
  if (!binder) return <Modal visible={false} />;
  const recs = items.filter((r) => binder.cardIds.includes(r.id));
  const groups = groupRecords(recs);
  const value = recs.reduce((s, r) => s + currentValue(r), 0);
  const candidates = groupsAll.filter((g) => !g.recs.every((r) => binder.cardIds.includes(r.id)));
  return (
    <Modal visible animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <View style={[S.screen, { paddingTop: L.top }]}>
        <View style={{ flex: 1, width: '100%', maxWidth: L.tablet ? L.maxW : undefined, alignSelf: 'center' }}>
          <View style={[S.row, { paddingHorizontal: L.gutter, paddingVertical: L.sp(8), gap: 8 }]}>
            <Pressable onPress={onClose} hitSlop={10} accessibilityLabel="Back" style={{ width: L.sp(40), height: L.sp(40), borderRadius: L.sp(20), backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center' }}>
              <Icon name="back" size={L.fs(18)} color={C.ink} />
            </Pressable>
            <Text style={{ flex: 1, textAlign: 'center', color: C.ink, fontWeight: '800', fontSize: L.fs(17) }} numberOfLines={1}>{binder.name}</Text>
            <Pressable onPress={() => setMenu(true)} hitSlop={10} accessibilityLabel="Binder options" style={{ width: L.sp(40), height: L.sp(40), borderRadius: L.sp(20), backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center' }}>
              <Icon name="more" size={L.fs(16)} color={C.ink} />
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: L.gutter, gap: L.sp(16), paddingBottom: L.sp(40) + L.bottom }}>
            <View style={[S.row, { gap: L.sp(16) }]}>
              <BinderCover L={L} color={binder.color} w={L.sp(96)} h={L.sp(124)} locked={binder.private} />
              <View style={{ flex: 1, gap: 4 }}>
                <Text style={{ color: C.ink, fontWeight: '900', fontSize: L.fs(22) }} numberOfLines={2}>{binder.name}</Text>
                <Text style={{ color: C.ink2, fontSize: L.fs(13) }}>{recs.length} card{recs.length === 1 ? '' : 's'}{binder.private ? ' · Private' : ''}</Text>
                <Text style={{ color: C.lime, fontWeight: '900', fontSize: L.fs(20), fontVariant: ['tabular-nums'] }}>{money(value)}</Text>
              </View>
            </View>
            <Pressable onPress={() => { setSel(new Set()); setAdding(true); }} style={({ pressed }) => [S.row, { justifyContent: 'center', gap: 8, backgroundColor: C.blue, borderRadius: 999, paddingVertical: L.sp(13) }, pressed && { opacity: 0.8 }]}>
              <Icon name="plus" size={L.fs(15)} color="#fff" />
              <Text style={{ color: '#fff', fontWeight: '900', fontSize: L.fs(15) }}>Add cards</Text>
            </Pressable>
            <TileGrid items={groups} keyOf={(g) => g.key}
              render={(g, w) => (
                <CardTile width={w} title={g.rec.card?.name || 'Card'} number={g.rec.card?.number} rarity={g.rec.card?.rarity} price={money(g.value || undefined)} uri={recordImage(g.rec) || undefined} thumb={g.rec.thumb} qty={g.qty}
                  onPress={() => onOpen(g)}
                  onLongPress={() => Alert.alert('Remove from binder?', g.rec.card?.name || '', [{ text: 'Keep', style: 'cancel' }, { text: 'Remove', style: 'destructive', onPress: () => onChange({ ...binder, cardIds: binder.cardIds.filter((id) => !g.recs.some((r) => r.id === id)) }) }])} />
              )} />
            {!groups.length ? <Text style={[S.muted, { textAlign: 'center' }]}>This binder is empty. Tap Add cards to fill it from your collection.</Text> : <Text style={[S.muted, { fontSize: L.fs(12) }]}>Hold a card to take it out of the binder.</Text>}
          </ScrollView>
        </View>
      </View>

      <Sheet visible={adding} onClose={() => setAdding(false)} title={`Add to ${binder.name}`}>
        {candidates.length ? (
          <TileGrid items={candidates} keyOf={(g) => g.key} cols={L.tablet ? 4 : L.cols} innerW={(L.tablet ? Math.min(L.maxW, 640) : L.width) - L.gutter * 2}
            render={(g, w) => (
              <CardTile width={w} title={g.rec.card?.name || 'Card'} number={g.rec.card?.number} rarity={g.rec.card?.rarity} price={money(g.value || undefined)} uri={recordImage(g.rec) || undefined} thumb={g.rec.thumb} qty={g.qty}
                selected={sel.has(g.key)} onPress={() => setSel((s) => { const n = new Set(s); n.has(g.key) ? n.delete(g.key) : n.add(g.key); return n; })} />
            )} />
        ) : (
          <Text style={S.muted}>Every card in your collection is already in this binder.</Text>
        )}
        <Pressable disabled={!sel.size}
          onPress={() => { const ids = candidates.filter((g) => sel.has(g.key)).flatMap((g) => g.recs.map((r) => r.id)); onChange({ ...binder, cardIds: [...new Set([...binder.cardIds, ...ids])] }); setAdding(false); }}
          style={{ backgroundColor: C.blue, borderRadius: 999, paddingVertical: L.sp(14), alignItems: 'center', opacity: sel.size ? 1 : 0.4 }}>
          <Text style={{ color: '#fff', fontWeight: '900', fontSize: L.fs(15) }}>{sel.size ? `Add ${sel.size} card${sel.size === 1 ? '' : 's'}` : 'Select cards'}</Text>
        </Pressable>
      </Sheet>

      <Sheet visible={menu} onClose={() => setMenu(false)} title={binder.name}>
        <SheetOption label={binder.private ? 'Make visible' : 'Make private'} sub={binder.private ? 'Currently only you can see it' : 'Only you will see it'} onPress={() => { onChange({ ...binder, private: !binder.private }); setMenu(false); }} />
        <SheetOption label="Delete binder" sub="Your cards stay in your collection"
          onPress={() => { setMenu(false); Alert.alert('Delete this binder?', 'The cards stay in your collection.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: () => onDelete(binder.id) }]); }} />
      </Sheet>
    </Modal>
  );
}
