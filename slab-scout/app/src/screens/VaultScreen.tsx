import React, { useMemo, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { C, S, gradeColor, money } from '../theme';
import { Btn, Chip, LinkRow, Slab, Thumb, Verdict } from '../components/ui';
import type { VaultRecord } from '../core/community';
import { soldLinks } from '../core/databases';
import { Grid, Segmented, Tile } from '../components/cards';
import { useApp } from '../appContext';
import { currentValue, recordImage } from '../core/portfolio';

type Group = 'brand' | 'type' | 'category' | 'value';
const GROUPS: [Group, string][] = [['brand', 'Brand'], ['type', 'Type'], ['category', 'Category'], ['value', 'Value']];
const rawOf = (c: VaultRecord) => currentValue(c);
const gradedOf = (c: VaultRecord) => Number(c.pricing?.graded_mid) || 0;
const keyOf = (c: VaultRecord, g: Group) => ((g === 'brand' ? c.card?.brand : g === 'type' ? c.card?.card_type : c.card?.game) || 'Other').trim() || 'Other';

export default function VaultScreen() {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const [which, setWhich] = useState<'collection' | 'wishlist'>('collection');
  const cards = useMemo(() => app.vault.filter((r) => (r.list || 'collection') === which), [app.vault, which]);
  const { vaultLoading: loading, vaultErr: error, needsCode, removeRecord: onDelete, refreshVault: onRefresh } = app;
  const [group, setGroup] = useState<Group>('brand');
  const [q, setQ] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [confirmDel, setConfirmDel] = useState(false);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? cards.filter((c) => JSON.stringify(c.card || {}).toLowerCase().includes(s)) : cards;
  }, [cards, q]);
  const sections = useMemo(() => {
    if (group === 'value') return [{ title: '', items: [...filtered].sort((a, b) => rawOf(b) - rawOf(a)), total: 0 }];
    const m = new Map<string, VaultRecord[]>();
    for (const c of filtered) m.set(keyOf(c, group), [...(m.get(keyOf(c, group)) || []), c]);
    return [...m.entries()].map(([title, items]) => ({ title, items: items.sort((a, b) => rawOf(b) - rawOf(a)), total: items.reduce((s, c) => s + rawOf(c), 0) })).sort((a, b) => b.total - a.total);
  }, [filtered, group]);
  const open = cards.find((c) => c.id === openId) || null;

  if (needsCode)
    return (
      <View style={[S.screen, S.pad]}>
        <Text style={S.h2}>Set a vault code</Text>
        <Text style={S.body}>Your vault syncs through the community database. Pick a private vault code (6+ characters) in Settings. Use the same code in the Streamlit app to see the same cards.</Text>
      </View>
    );

  return (
    <View style={S.screen}>
      <ScrollView contentContainerStyle={[S.pad, { paddingBottom: 40 }]}>
        <Segmented options={[['collection', `Collection ${app.vault.filter((r) => (r.list || 'collection') === 'collection').length}`], ['wishlist', `Wishlist ${app.vault.filter((r) => r.list === 'wishlist').length}`]]} value={which} onChange={setWhich} />
        <View style={S.row}>
          {[['Cards', String(cards.length), false], ['Raw value', money(cards.reduce((s, c) => s + rawOf(c), 0)), true], ['Graded (known)', money(cards.reduce((s, c) => s + gradedOf(c), 0)), false]].map(([l, v, g]) => (
            <View key={String(l)} style={[S.card, { flex: 1, padding: 10, gap: 2 }]}>
              <Text style={S.eyebrow}>{l}</Text>
              <Text style={[{ color: g ? C.gold : C.ink, fontSize: 17, fontWeight: '800' }, S.mono]} numberOfLines={1} adjustsFontSizeToFit>{v}</Text>
            </View>
          ))}
        </View>
        <View style={st.seg}>
          {GROUPS.map(([id, label]) => (
            <Pressable key={id} style={[st.segBtn, group === id && st.segOn]} onPress={() => setGroup(id)}>
              <Text style={[st.segText, group === id && { color: C.ink }]}>{label}</Text>
            </Pressable>
          ))}
        </View>
        <TextInput style={S.input} value={q} onChangeText={setQ} placeholder="Search name, set, rarity…" placeholderTextColor={C.ink2} />
        {error ? <Text style={[S.body, { color: C.crit }]}>{error}</Text> : null}
        {loading ? <Text style={S.muted}>Loading…</Text> : null}
        {!cards.length && !loading ? (
          <View style={[S.card, { alignItems: 'center', paddingVertical: 30 }]}>
            <Text style={S.h3}>{which === 'wishlist' ? 'Your wishlist is empty' : 'Your collection is empty'}</Text>
            <Text style={[S.muted, { textAlign: 'center' }]}>{which === 'wishlist' ? 'Tap ♡ Wishlist on any card in Explore.' : 'Scan a card, or add one from Explore.'}</Text>
            <Btn label="Refresh" onPress={onRefresh} />
          </View>
        ) : null}
        {sections.map((sec) => (
          <View key={sec.title || 'all'} style={{ gap: 8 }}>
            {sec.title ? (
              <View style={st.secHead}>
                <Text style={S.h3}>{sec.title}</Text>
                <Text style={[S.muted, S.mono]}>{sec.items.length} · {money(sec.total)}</Text>
              </View>
            ) : null}
            <Grid>
              {sec.items.map((c) => (
                <Tile key={c.id} title={c.card?.name} sub={[c.card?.set, c.card?.rarity].filter(Boolean).join(' · ')} price={money(rawOf(c) || undefined)} thumb={c.thumb} uri={recordImage(c)} printRun={c.print_run}
                  badge={c.grade?.label || (c.grade?.psa != null ? `PSA ${c.grade.psa}` : undefined)} onPress={() => { setOpenId(c.id); setConfirmDel(false); }} />
              ))}
            </Grid>
          </View>
        ))}
      </ScrollView>

      <Modal visible={!!open} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setOpenId(null)}>
        {open && (
          <View style={S.screen}>
            <View style={[S.row, { justifyContent: 'space-between', padding: 16, paddingBottom: 4 }]}>
              <Text style={S.eyebrow}>Card details</Text>
              <Btn label="Close" onPress={() => setOpenId(null)} style={{ paddingVertical: 7 }} />
            </View>
            <ScrollView contentContainerStyle={[S.pad, { paddingBottom: 40 + insets.bottom }]}>
              <View style={S.row}>
                <Thumb b64={open.thumb} w={110} />
                <View style={{ flex: 1, gap: 4 }}>
                  <Text style={S.h2}>{open.card?.name}</Text>
                  <Text style={S.muted}>{[open.card?.year, open.card?.brand, open.card?.set, open.card?.number].filter(Boolean).join(' · ')}</Text>
                  <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap' }}>
                    {open.card?.rarity ? <Chip gold label={open.card.rarity} /> : null}
                    {open.card?.variant ? <Chip label={open.card.variant} /> : null}
                    {open.card?.card_type ? <Chip label={open.card.card_type} /> : null}
                  </View>
                </View>
              </View>
              <View style={S.row}>
                <Slab who="PSA · estimate" grade={open.grade?.psa} label={open.grade?.psa_label} sub={open.grade?.psa_range ? `Likely ${open.grade.psa_range}` : ''} />
                <Slab who="TAG-style · est." grade={open.grade?.tag_grade} label={open.grade?.tag_label} sub={open.grade?.tag_score ? `Score ${open.grade.tag_score} / 1000` : ''} />
              </View>
              <Text style={S.muted}>Centering {open.grade?.centering?.front || '—'}{open.grade?.method === 'ai' ? ' · graded by AI' : ' · graded by checklist'}</Text>
              <Verdict verdict={open.authenticity?.verdict || 'not_checked'} reasons={open.authenticity?.reasons || []} />
              <View style={S.card}>
                <Text style={S.h3}>Value</Text>
                <Text style={[S.body, S.mono]}>Raw {money(rawOf(open) || undefined)}{open.pricing?.graded_mid ? ` · ${open.pricing.graded_label} ${money(open.pricing.graded_mid)}` : ''}</Text>
                {open.pricing?.note ? <Text style={S.muted}>{open.pricing.note}</Text> : null}
                <LinkRow links={soldLinks([open.card?.year, open.card?.set, open.card?.name, open.card?.number].filter(Boolean).join(' '), open.pricing?.graded_label, open.match?.image_url)} />
              </View>
              <Text style={S.muted}>Added {new Date(open.added_at).toLocaleDateString()}</Text>
              {open.match?.catalog_key ? <Btn label="Open card page" onPress={() => { const k = open.match.catalog_key!; setOpenId(null); app.openCard(k); }} /> : null}
              {confirmDel ? (
                <View style={S.row}>
                  <Btn danger label="Yes, remove it" style={{ flex: 1 }} onPress={async () => { await onDelete(open.id); setOpenId(null); }} />
                  <Btn label="Keep" style={{ flex: 1 }} onPress={() => setConfirmDel(false)} />
                </View>
              ) : (
                <Btn danger label={which === 'wishlist' ? 'Remove from wishlist' : 'Remove from collection'} onPress={() => setConfirmDel(true)} />
              )}
            </ScrollView>
          </View>
        )}
      </Modal>
    </View>
  );
}

const st = StyleSheet.create({
  seg: { flexDirection: 'row', backgroundColor: C.surface2, borderRadius: 12, padding: 4, gap: 4 },
  segBtn: { flex: 1, paddingVertical: 9, borderRadius: 9, alignItems: 'center' },
  segOn: { backgroundColor: C.surface },
  segText: { color: C.ink2, fontWeight: '700', fontSize: 13 },
  secHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', borderBottomWidth: 1, borderBottomColor: C.line, paddingBottom: 6, paddingTop: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, borderRadius: 12, padding: 8, paddingRight: 12 },
  rank: { color: C.ink2, fontWeight: '800', width: 22, textAlign: 'center' },
  pill: { fontSize: 11, fontWeight: '700', borderWidth: 1, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 1 },
});
