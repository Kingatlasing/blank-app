import React, { useMemo } from 'react';
import { Image, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { C, S, money, pctText } from '../theme';
import { Carousel, CardTile, SectionTitle } from '../components/cards';
import { AreaChart, Gradient, GradientBorder, Glow, Icon } from '../components/visual';
import { useApp } from '../appContext';
import { useLayout } from '../layout';
import { useCollection, useValueHistory } from '../portfolioHooks';
import { cards, imageUrl, priceIn, sets } from '../core/catalog';
import { changeOver, currentValue, priceMoves, recordImage } from '../core/portfolio';

/** Discover: profile header, collection value card, search, then carousels (price alerts, chase cards, recent). */
export default function HomeScreen() {
  const app = useApp();
  const L = useLayout();
  const { items, total } = useCollection();
  const hist = useValueHistory(total);

  const ch30 = changeOver(hist, total, 30);
  const prev = hist.length >= 2 ? hist[hist.length - 2] : null;
  const change = ch30 ? ch30.abs : prev ? total - prev.value : 0;
  const changeLabel = ch30 ? '30d' : prev ? `since ${prev.day}` : '';
  // Discover only shows cards with a picture: the card's own photo, or the photo taken when it was scanned
  const pictured = useMemo(() => items.filter((r) => !!(r.thumb || recordImage(r))), [items]);
  const top = useMemo(() => [...pictured].sort((a, b) => currentValue(b) - currentValue(a)).slice(0, 10), [pictured]);
  const recent = useMemo(() => [...pictured].sort((a, b) => (b.added_at || '').localeCompare(a.added_at || '')).slice(0, 10), [pictured]);
  const mode = app.settings.priceMode;
  const chase = useMemo(() => cards().filter((c) => !!c.img && !c.img.startsWith('~') && priceIn(c, mode).v).sort((a, b) => (priceIn(b, mode).v || 0) - (priceIn(a, mode).v || 0)).slice(0, 10), [mode]);
  const allSets = sets();
  const moves = useMemo(() => priceMoves(pictured).slice(0, 10), [pictured]);
  const cw = L.carouselW();
  const openRec = (r: (typeof items)[number]) => (r.match?.catalog_key ? app.openCard(r.match.catalog_key) : app.goTab('collection'));
  const av = L.sp(40);

  return (
    <ScrollView style={S.screen} contentContainerStyle={{ padding: L.gutter, paddingTop: L.sp(8), gap: L.sp(16), paddingBottom: L.sp(40) }}
      refreshControl={<RefreshControl refreshing={app.vaultLoading} onRefresh={app.refreshVault} tintColor={C.accent} />}>
      {/* header: avatar, name, gear */}
      <View style={[S.row, { gap: L.sp(12) }]}>
        <Pressable onPress={() => app.goTab('collection')} accessibilityLabel="Your profile" style={{ width: av, height: av, borderRadius: av / 2, backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
          {app.profile.avatar ? <Image source={{ uri: app.profile.avatar }} style={{ width: av, height: av }} /> : <Icon name="plus" size={L.fs(16)} color={C.ink} />}
        </Pressable>
        <Text style={{ flex: 1, color: C.ink, fontSize: L.fs(22), fontWeight: '800' }} numberOfLines={1}>{app.displayName}</Text>
        <Pressable onPress={app.openSettings} hitSlop={10} accessibilityLabel="Settings" style={{ padding: 4 }}>
          <Icon name="gear" size={L.fs(24)} color={C.ink} />
        </Pressable>
      </View>

      {app.needsCode ? (
        <View style={S.banner}>
          <Text style={S.body}>Set a private vault code in Settings to start your collection. Use the same code in the web app to see the same cards.</Text>
        </View>
      ) : (
        <Pressable onPress={() => app.goTab('collection')} style={{ borderRadius: L.sp(24), overflow: 'hidden', backgroundColor: C.hero, borderWidth: 1, borderColor: '#2B3070' }}>
          <Gradient colors={[C.heroTop, C.hero, '#12142A']} steps={20} vertical />
          <Glow color={C.blue} size={L.sp(220)} style={{ right: -L.sp(70), top: -L.sp(90) }} />
          <View style={{ padding: L.sp(20), gap: L.sp(4) }}>
            <View style={[S.row, { justifyContent: 'space-between' }]}>
              <Text style={{ color: '#C9CCF5', fontWeight: '700', fontSize: L.fs(14) }}>Collection value</Text>
              <View style={[S.row, { gap: 4 }]}>
                <Text style={{ color: C.ink, fontWeight: '800', fontSize: L.fs(14) }}>Collection</Text>
                <Icon name="forward" size={L.fs(13)} color={C.ink} />
              </View>
            </View>
            <View style={[S.row, { alignItems: 'flex-end', gap: L.sp(12) }]}>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={{ color: C.ink, fontSize: L.fs(44), fontWeight: '900', letterSpacing: -1, fontVariant: ['tabular-nums'] }} numberOfLines={1} adjustsFontSizeToFit>{money(total)}</Text>
                {changeLabel ? (
                  <Text style={{ color: change >= 0 ? C.good : C.crit, fontWeight: '800', fontSize: L.fs(14) }}>
                    {change >= 0 ? '▲' : '▼'} {money(Math.abs(change))} · {changeLabel}
                  </Text>
                ) : (
                  <Text style={{ color: C.ink2, fontSize: L.fs(13) }}>Tracking starts today</Text>
                )}
                <Text style={{ color: '#A9ADD6', fontSize: L.fs(12), marginTop: 2 }}>{items.length} card{items.length === 1 ? '' : 's'}</Text>
              </View>
              <View style={{ width: L.sp(118), paddingBottom: L.sp(6) }}>
                {hist.length >= 2 ? <AreaChart spark points={hist.slice(-60)} height={L.sp(54)} color={change >= 0 ? C.good : C.crit} lineColor={change >= 0 ? C.good : C.crit} fillTop={0.3} bg={C.hero} /> : null}
              </View>
            </View>
          </View>
        </Pressable>
      )}

      <Pressable onPress={app.openSearch} accessibilityLabel="Search cards">
        <GradientBorder radius={L.sp(16)} width={1.6} colors={[C.blue, C.purple, C.orange, C.goldBright]}>
          <View style={[S.row, { paddingHorizontal: L.sp(14), height: L.sp(50), gap: 10 }]}>
            <Icon name="search" size={L.fs(19)} color={C.ink2} />
            <Text style={{ color: C.ink2, fontSize: L.fs(15), flex: 1 }} numberOfLines={1}>Find PSA 10 Charizard</Text>
          </View>
        </GradientBorder>
      </Pressable>

      {moves.length ? (
        <View style={{ gap: L.sp(10) }}>
          <SectionTitle title="Price alerts" />
          <Text style={[S.muted, { fontSize: L.fs(13), marginTop: -L.sp(6) }]}>Moved 20%+ (and at least $5) since you added them.</Text>
          <Carousel>
            {moves.map((m) => (
              <CardTile key={m.rec.id} width={cw} title={m.rec.card?.name || 'Card'} number={m.rec.card?.number} rarity={m.rec.card?.rarity} price={money(m.now)} thumb={m.rec.thumb} uri={recordImage(m.rec) || undefined}
                badge={`${m.now >= m.was ? '▲' : '▼'} ${pctText(m.pct)}`} onPress={() => openRec(m.rec)} />
            ))}
          </Carousel>
        </View>
      ) : null}

      {items.length ? (
        <>
          <View style={{ gap: L.sp(10) }}>
            <SectionTitle title="Most valuable" action="See all" onAction={() => app.goTab('collection')} />
            <Carousel>
              {top.map((r) => (
                <CardTile key={r.id} width={cw} title={r.card?.name || 'Card'} number={r.card?.number} rarity={r.card?.rarity} price={money(currentValue(r) || undefined)} thumb={r.thumb} uri={recordImage(r) || undefined} onPress={() => openRec(r)} />
              ))}
            </Carousel>
          </View>
        </>
      ) : !app.needsCode ? (
        <View style={[S.card, { gap: 6 }]}>
          <Text style={[S.h3, { fontSize: L.fs(16) }]}>Your collection is empty</Text>
          <Text style={S.muted}>Scan a card, or add one from Explore, to start tracking its value.</Text>
          <Pressable onPress={() => app.goTab('scan')} style={[S.btn, S.primary, { marginTop: 6 }]}><Text style={S.primaryText}>Scan a card</Text></Pressable>
        </View>
      ) : null}

      <View style={{ gap: L.sp(10) }}>
        <SectionTitle title="Top chase cards" action="Explore" onAction={() => app.goTab('explore')} />
        <Carousel>
          {chase.map((c) => (
            <CardTile key={c.key} width={cw} title={c.name} number={c.number} rarity={c.variant || 'Base'} price={priceIn(c, app.settings.priceMode).text} uri={imageUrl(c)[0] || undefined} badge={c.printRun ? (c.printRun === 1 ? '1 of 1' : `/${c.printRun}`) : allSets[c.setId]?.brand} onPress={() => app.openCard(c.key)} />
          ))}
        </Carousel>
      </View>

      {recent.length ? (
        <View style={{ gap: L.sp(10) }}>
          <SectionTitle title="Recently added" />
          <Carousel>
            {recent.map((r) => (
              <CardTile key={r.id} width={cw} title={r.card?.name || 'Card'} number={r.card?.number} rarity={r.card?.rarity} price={money(currentValue(r) || undefined)} thumb={r.thumb} uri={recordImage(r) || undefined} onPress={() => openRec(r)} />
            ))}
          </Carousel>
        </View>
      ) : null}
    </ScrollView>
  );
}
