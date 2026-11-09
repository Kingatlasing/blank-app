/**
 * Cards sent off for grading: the photos taken before, our grade estimate, and the grade that came back.
 * These before/after pairs are the most trustworthy test of the grader (same phone, same app, real grades).
 */
import { Share } from 'react-native';
import { Directory, File, Paths } from 'expo-file-system';
import type { VaultRecord } from './community';

export const GRADERS = ['PSA', 'BGS', 'CGC', 'SGC', 'TAG', 'ACE', 'AGS', 'Other'] as const;

export interface Submission {
  company: string;
  sent_on: string;
  /** what we estimated when it was sent (copied from the record's grade at that moment) */
  estimate?: { psa?: number | string | null; tag?: number | string | null; label?: string; sub?: Record<string, number> | null; method?: string };
  /** subs: the label's subgrades as typed (BGS / TAG / CGC print them), e.g. "Ce 9.5 Co 9 E 9 S 10" */
  returned?: { grade: string; cert?: string; on: string; subs?: string };
}

const photoDir = () => {
  const d = new Directory(Paths.document, 'grading-photos');
  if (!d.exists) d.create({ intermediates: true, idempotent: true });
  return d;
};

/** Keep full-resolution copies of the scan photos with the record (this phone only). */
export async function keepPhotos(front?: string | null, back?: string | null): Promise<{ front?: string; back?: string } | undefined> {
  const out: { front?: string; back?: string } = {};
  const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  for (const [side, uri] of [['front', front], ['back', back]] as const) {
    if (!uri) continue;
    try {
      const dst = new File(photoDir(), `${stamp}-${side}.jpg`);
      await new File(uri).copy(dst);
      out[side] = dst.uri;
    } catch {
      /* the original is gone (e.g. a web blob): skip it */
    }
  }
  return out.front || out.back ? out : undefined;
}

export const markSent = (r: VaultRecord, company: string): VaultRecord => ({
  ...r,
  submission: {
    company,
    sent_on: new Date().toISOString().slice(0, 10),
    estimate: { psa: r.grade?.psa ?? null, tag: r.grade?.tag_grade ?? null, label: r.grade?.psa_label || r.grade?.label || '', sub: r.grade?.sub || null, method: r.grade?.method || '' },
  },
});

/** Undo "sent for grading" (marked by mistake, or the card never went). */
export const unmarkSent = (r: VaultRecord): VaultRecord => {
  const { submission, ...rest } = r;
  return rest as VaultRecord;
};

export const markReturned = (r: VaultRecord, grade: string, cert: string, subs = ''): VaultRecord => ({
  ...r,
  submission: {
    ...(r.submission as Submission),
    returned: { grade: grade.trim(), cert: cert.trim() || undefined, on: new Date().toISOString().slice(0, 10), subs: subs.trim() || undefined },
  },
  grade: { ...(r.grade || {}), label: `${r.submission?.company || ''} ${grade.trim()}`.trim() },
});

/** Our estimate in the company's own scale: the TAG-style estimate for TAG, the PSA estimate for everyone else. */
export const ourEstimate = (s?: Submission): number | null => {
  const v = parseFloat(String((s?.company === 'TAG' && s?.estimate?.tag != null ? s.estimate.tag : s?.estimate?.psa) ?? ''));
  return Number.isFinite(v) ? v : null;
};

/** How far off the estimate was (their grade minus ours), when both are numbers. */
export function estimateMiss(s?: Submission): number | null {
  const ours = ourEstimate(s) ?? NaN;
  const theirs = parseFloat(String(s?.returned?.grade ?? '').replace(/[^0-9.]/g, ''));
  return Number.isFinite(ours) && Number.isFinite(theirs) ? theirs - ours : null;
}

/** One file with every returned card: card, our estimate, their grade, and the photos (base64) so they can be used to test the grader. */
export async function exportResults(recs: VaultRecord[]): Promise<number> {
  const done = recs.filter((r) => r.submission?.returned);
  const rows = [];
  for (const r of done) {
    const photos: Record<string, string> = {};
    for (const side of ['front', 'back'] as const) {
      const u = r.photos?.[side];
      if (!u) continue;
      try {
        photos[side] = await new File(u).base64();
      } catch {
        /* photo missing on this phone */
      }
    }
    rows.push({ card: r.card, catalog_key: r.match?.catalog_key, submission: r.submission, grade_at_scan: r.grade, photos });
  }
  const f = new File(Paths.cache, `slabscout-grading-results-${new Date().toISOString().slice(0, 10)}.json`);
  if (f.exists) f.delete();
  f.create();
  f.write(JSON.stringify({ v: 1, exported_at: new Date().toISOString(), results: rows }));
  await Share.share({ url: f.uri, title: 'Slab Scout grading results', message: `${rows.length} graded cards with photos` });
  return rows.length;
}

const daysSince = (d: string) => Math.max(0, Math.floor((Date.now() - new Date(d + 'T12:00:00').getTime()) / 86400000));

/** Everything sent off: what is still out (and for how long), and how close our estimates were on what came back. */
export function submissionStats(recs: VaultRecord[]) {
  const sent = recs.filter((r) => r.submission && r.list !== 'wishlist');
  const out = sent.filter((r) => !r.submission!.returned).map((r) => ({ rec: r, days: daysSince(r.submission!.sent_on) })).sort((a, b) => b.days - a.days);
  const back = sent.filter((r) => r.submission!.returned);
  const misses = back.map((r) => estimateMiss(r.submission)).filter((m): m is number => m != null);
  return {
    out,
    back,
    compared: misses.length,
    exact: misses.filter((m) => m === 0).length,
    within1: misses.filter((m) => Math.abs(m) <= 1).length,
    avgMiss: misses.length ? misses.reduce((a, m) => a + Math.abs(m), 0) / misses.length : null,
    /** positive = the companies graded higher than we estimated, on average */
    lean: misses.length ? misses.reduce((a, m) => a + m, 0) / misses.length : null,
  };
}
