/** Details of one saved card (grade estimate, authenticity, value, sold links, remove). Opened from the Collection grid
 * and from the "In your collection" rows on a card page. */
import React, { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { C, S, money } from '../theme';
import { Btn, Chip, LinkRow, Slab, Thumb, Verdict } from './ui';
import { Icon } from './visual';
import type { VaultRecord } from '../core/community';
import { soldLinks } from '../core/databases';
import { currentValue, recordImage } from '../core/portfolio';
import { useApp } from '../appContext';
import { useLayout } from '../layout';
import { GRADERS, estimateMiss, exportResults, markReturned, markSent } from '../core/submissions';

export default function RecordSheet({ rec, onClose, onOpenCard }: { rec: VaultRecord | null; onClose: () => void; onOpenCard?: (key: string) => void }) {
  const app = useApp();
  const L = useLayout();
  const [confirmDel, setConfirmDel] = useState(false);
  const [pickCo, setPickCo] = useState(false);
  const [retGrade, setRetGrade] = useState('');
  const [retCert, setRetCert] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setConfirmDel(false);
    setPickCo(false);
    setRetGrade('');
    setRetCert('');
  }, [rec?.id]);
  const save = async (r: VaultRecord) => {
    setBusy(true);
    try {
      await app.updateRecord(r);
    } finally {
      setBusy(false);
    }
    onClose();
  };
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
            {!wish ? (
              <View style={[S.card, { gap: 8 }]}>
                <Text style={S.h3}>Grading submission</Text>
                {!open.submission ? (
                  pickCo ? (
                    <>
                      <Text style={S.muted}>Sent to which company?</Text>
                      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                        {GRADERS.map((co) => (
                          <Pressable key={co} disabled={busy} onPress={() => save(markSent(open, co))} style={[S.chip, { paddingVertical: 8 }]}>
                            <Text style={S.chipText}>{co}</Text>
                          </Pressable>
                        ))}
                      </View>
                    </>
                  ) : (
                    <>
                      <Text style={S.muted}>
                        Sending this card off? Mark it, then add the grade when it comes back. Your scan photos and our estimate are kept with it, so the app can learn how close it was.
                        {open.photos?.front ? '' : ' (No full photo was kept for this card: scan it again before sending for the best comparison.)'}
                      </Text>
                      <Btn label="Mark as sent for grading" onPress={() => setPickCo(true)} />
                    </>
                  )
                ) : !open.submission.returned ? (
                  <>
                    <Text style={S.body}>
                      Sent to {open.submission.company} on {open.submission.sent_on}
                      {open.submission.estimate?.psa != null ? ` · our estimate PSA ${open.submission.estimate.psa}` : ''}
                    </Text>
                    <Text style={S.muted}>Got it back? Enter the grade on the label.</Text>
                    <View style={[S.row, { gap: 8 }]}>
                      <TextInput value={retGrade} onChangeText={setRetGrade} placeholder="Grade (e.g. 9)" placeholderTextColor={C.ink2} keyboardType="decimal-pad" style={[S.input, { flex: 1 }]} />
                      <TextInput value={retCert} onChangeText={setRetCert} placeholder="Cert # (optional)" placeholderTextColor={C.ink2} keyboardType="number-pad" style={[S.input, { flex: 1.4 }]} />
                    </View>
                    <Btn label="Save grade" disabled={!retGrade.trim() || busy} onPress={() => save(markReturned(open, retGrade, retCert))} />
                  </>
                ) : (
                  <>
                    <Text style={S.body}>
                      {open.submission.company} {open.submission.returned.grade}
                      {open.submission.returned.cert ? ` · cert ${open.submission.returned.cert}` : ''}
                      {open.submission.estimate?.psa != null ? ` · we estimated ${open.submission.estimate.psa}` : ''}
                    </Text>
                    {(() => {
                      const m = estimateMiss(open.submission);
                      return m == null ? null : (
                        <Text style={[S.muted, { color: Math.abs(m) <= 1 ? C.lime : C.warn }]}>
                          {m === 0 ? 'Spot on.' : `${Math.abs(m)} grade${Math.abs(m) === 1 ? '' : 's'} ${m > 0 ? 'higher' : 'lower'} than our estimate.`}
                        </Text>
                      );
                    })()}
                    <Btn label="Share all grading results" onPress={() => exportResults(app.vault).catch(() => {})} />
                  </>
                )}
              </View>
            ) : null}
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
