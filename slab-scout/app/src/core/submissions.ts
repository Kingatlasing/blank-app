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
  estimate?: { psa?: number | string | null; label?: string; sub?: Record<string, number> | null; method?: string };
  returned?: { grade: string; cert?: string; on: string };
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
    estimate: { psa: r.grade?.psa ?? null, label: r.grade?.psa_label || r.grade?.label || '', sub: r.grade?.sub || null, method: r.grade?.method || '' },
  },
});

export const markReturned = (r: VaultRecord, grade: string, cert: string): VaultRecord => ({
  ...r,
  submission: { ...(r.submission as Submission), returned: { grade: grade.trim(), cert: cert.trim() || undefined, on: new Date().toISOString().slice(0, 10) } },
  grade: { ...(r.grade || {}), label: `${r.submission?.company || ''} ${grade.trim()}`.trim() },
});

/** How far off the estimate was (their grade minus ours), when both are numbers. */
export function estimateMiss(s?: Submission): number | null {
  const ours = parseFloat(String(s?.estimate?.psa ?? ''));
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
