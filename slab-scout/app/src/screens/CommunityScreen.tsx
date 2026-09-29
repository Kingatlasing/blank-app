import React, { useEffect, useState } from 'react';
import { ScrollView, Text, TextInput, View } from 'react-native';
import { C, S } from '../theme';
import { Chip, Thumb } from '../components/ui';
import type { CatalogRow, Store } from '../core/community';

export default function CommunityScreen({ store }: { store: Store }) {
  const [stats, setStats] = useState<{ cards: number; fakes: number; sales: number } | null>(null);
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<CatalogRow[]>([]);
  const [err, setErr] = useState('');

  useEffect(() => {
    store.stats().then(setStats).catch((e) => setErr(String(e?.message || e)));
  }, [store]);
  useEffect(() => {
    const t = setTimeout(() => store.search(q).then(setRows).catch((e) => setErr(String(e?.message || e))), 350);
    return () => clearTimeout(t);
  }, [q, store]);

  return (
    <ScrollView style={S.screen} contentContainerStyle={[S.pad, { paddingBottom: 40 }]} keyboardShouldPersistTaps="handled">
      <Text style={S.h2}>Community catalog</Text>
      <Text style={S.muted}>
        {store.shared
          ? 'Shared with everyone using Slab Scout. Every confirmed scan teaches the app that card, and every reported fake gets flagged on future scans.'
          : 'Kept on this phone only. Connect a free Supabase project in Settings to share with everyone and sync with the Streamlit app.'}
      </Text>
      {stats ? (
        <View style={S.row}>
          {[['Cards known', stats.cards], ['Fakes reported', stats.fakes], ['Sales added', stats.sales]].map(([l, v]) => (
            <View key={String(l)} style={[S.card, { flex: 1, padding: 10, gap: 2 }]}>
              <Text style={S.eyebrow}>{l}</Text>
              <Text style={[S.h2, S.mono]}>{v}</Text>
            </View>
          ))}
        </View>
      ) : null}
      {err ? <Text style={[S.body, { color: C.crit }]}>{err}</Text> : null}
      <TextInput style={S.input} value={q} onChangeText={setQ} placeholder="Search player, card or set" placeholderTextColor={C.ink2} />
      {rows.map((r) => (
        <View key={r.id} style={[S.row, S.card, { padding: 8 }]}>
          <Thumb b64={r.thumb} />
          <View style={{ flex: 1, gap: 3 }}>
            <Text style={[S.body, { fontWeight: '700' }]}>{r.name}</Text>
            <Text style={S.muted}>{[r.set_name, r.number].filter(Boolean).join(' · ')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
              {r.is_fake ? <Chip label="reported fake" color={C.crit} /> : null}
              {r.rarity ? <Chip gold label={r.rarity} /> : null}
              {r.game ? <Chip label={r.game} /> : null}
              <Chip label={`seen ${r.confirmations}×`} />
            </View>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}
