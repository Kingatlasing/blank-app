/** Details of one saved card (grade estimate, authenticity, value, sold links, remove). Opened from the Collection grid
 * and from the "In your collection" rows on a card page. */
import React, { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { C, S, money } from '../theme';
import { Btn, Chip, LinkRow, Slab, Thumb, Verdict } from './ui';
import { Icon } from './visual';
import type { VaultRecord } from '../core/community';
import { soldLinks } from '../core/databases';
import { currentValue, recordImage } from '../core/portfolio';
import { useApp } from '../appContext';
import { useLayout } from '../layout';

export default function RecordSheet({ rec, onClose, onOpenCard }: { rec: VaultRecord | null; onClose: () => void; onOpenCard?: (key: string) => void }) {
  const app = useApp();
  const L = useLayout();
  const [confirmDel, setConfirmDel] = useState(false);
  useEffect(() => setConfirmDel(false), [rec?.id]);
  const open = rec;
  const wish = open?.list === 'wishlist';
  return (
    <Modal visible={!!open} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      {open ? (
        <View style={[S.screen, { width: '100%', maxWidth: L.tablet ? 720 : undefined, alignSelf: 'center' }]}>
          <View style={[S.row, { justifyContent: 'space-between', paddingHorizontal: L.gutter, paddingTop: L.sp(14), paddingBottom: 4 }]}>
            <Text style={[S.h3, { fontSize: L.fs(17) }]}>Card details</Text>
            <Pressable onPress={onClose} hitSlop={10} accessibilityLabel="Close" style={{ width: L.sp(34), height: L.sp(34), borderRadius: L.sp(17), backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center' }}>
              <Icon name="close" size={L.fs(14)} color={C.ink} />
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: L.gutter, gap: L.sp(14), paddingBottom: L.sp(40) + L.bottom }}>
            <View style={[S.row, { alignItems: 'flex-start', gap: L.sp(14) }]}>
              <Thumb b64={open.thumb} uri={recordImage(open) || undefined} w={L.sp(110)} />
              <View style={{ flex: 1, gap: 4 }}>
                <Text style={[S.h2, { fontSize: L.fs(20) }]}>{open.card?.name}</Text>
                <Text style={S.muted}>{[open.card?.year, open.card?.brand, open.card?.set, open.card?.number].filter(Boolean).join(' · ')}</Text>
                <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap' }}>
                  {open.card?.rarity ? <Chip gold label={open.card.rarity} /> : null}
                  {open.card?.variant ? <Chip label={open.card.variant} /> : null}
                  {open.card?.card_type ? <Chip label={open.card.card_type} /> : null}
                  {open.grade?.condition ? <Chip label={open.grade.condition} /> : null}
                  {open.grade?.label ? <Chip label={open.grade.label} /> : null}
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
              <Text style={[S.body, S.mono]}>
                Raw <Text style={{ color: C.lime, fontWeight: '800' }}>{money(currentValue(open) || undefined)}</Text>
                {open.pricing?.graded_mid ? ` · ${open.pricing.graded_label} ${money(open.pricing.graded_mid)}` : ''}
              </Text>
              {open.pricing?.note ? <Text style={S.muted}>{open.pricing.note}</Text> : null}
              <LinkRow links={soldLinks([open.card?.year, open.card?.set, open.card?.name, open.card?.number].filter(Boolean).join(' '), open.pricing?.graded_label, open.match?.image_url)} />
            </View>
            <Text style={S.muted}>Added {new Date(open.added_at).toLocaleDateString()}</Text>
            {open.match?.catalog_key && onOpenCard ? <Btn label="Open card page" onPress={() => { const k = open.match.catalog_key!; onClose(); onOpenCard(k); }} /> : null}
            {confirmDel ? (
              <View style={S.row}>
                <Btn danger label="Yes, remove it" style={{ flex: 1 }} onPress={async () => { await app.removeRecord(open.id); onClose(); }} />
                <Btn label="Keep" style={{ flex: 1 }} onPress={() => setConfirmDel(false)} />
              </View>
            ) : (
              <Btn danger label={wish ? 'Remove from wishlist' : 'Remove from collection'} onPress={() => setConfirmDel(true)} />
            )}
          </ScrollView>
        </View>
      ) : null}
    </Modal>
  );
}
