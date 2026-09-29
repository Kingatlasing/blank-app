/** Read a graded slab's label (same rules as the web app's core/slab.py): company, grade, cert, card description. */

const COMPANIES: [string, RegExp[]][] = [
  ['PSA', [/\bPSA\b/, /PSACARD/, /PSA\/DNA/]],
  ['CGC', [/\bCGC\b/, /CGCCARDS/, /CERTIFIED GUARANTY/]],
  ['BGS', [/\bBGS\b/, /BECKETT/, /\bBVG\b/]],
  ['TAG', [/\bTAG\b(?!\s*TEAM)/, /TAGGRADING/, /TAG GRADING/]],
  ['SGC', [/\bSGC\b/, /SPORTSCARD GUARANTY/]],
];
const GRADE_WORDS: [RegExp, number | null, string][] = [
  [/BLACK\s*LABEL|PRISTINE\s*10/, 10, 'PRISTINE'],
  [/GEM\s*-?\s*M(IN)?T\.?\s*10|10\s*GEM\s*M(IN)?T/, 10, 'GEM MINT'],
  [/MINT\s*\+\s*9\.5|GEM\s*MINT\s*9\.5|9\.5\s*(GEM\s*)?MINT\+?/, 9.5, 'MINT+'],
  [/MINT\s*9(?!\.)|9\s*MINT/, 9, 'MINT'],
  [/NM\s*-?\s*MT\s*\+?\s*8\.5|8\.5\s*NM/, 8.5, 'NM-MT+'],
  [/NM\s*-?\s*MT\s*8(?!\.)|8\s*NM\s*-?\s*MT/, 8, 'NM-MT'],
  [/\bNM\s*7|7\s*NM\b/, 7, 'NM'],
  [/EX\s*-?\s*MT\s*6|6\s*EX\s*-?\s*MT/, 6, 'EX-MT'],
  [/\bEX\s*5\b|\b5\s*EX\b/, 5, 'EX'],
  [/VG\s*-?\s*EX\s*4|4\s*VG\s*-?\s*EX/, 4, 'VG-EX'],
  [/\bVG\s*3|3\s*VG\b/, 3, 'VG'],
  [/GOOD\s*2|2\s*GOOD/, 2, 'GOOD'],
  [/\bAUTHENTIC\b/, null, 'AUTHENTIC'],
];
const LOOKUP: Record<string, string> = {
  PSA: 'https://www.psacard.com/cert/{c}',
  CGC: 'https://www.cgccards.com/certlookup/{c}/',
  BGS: 'https://www.beckett.com/grading/card-lookup?item_type=BGS&item_id={c}',
  TAG: 'https://my.taggrading.com/card/{c}',
  SGC: 'https://gosgc.com/cert-code-lookup?certCode={c}',
};

export interface SlabInfo {
  company: string;
  grade: number | null;
  label: string;
  cert: string;
  qualifiers: string[];
  desc: string;
  descLines: string[];
  number: string;
  year: string;
  lookup: string;
}

export function readLabel(lines: string[]): SlabInfo | null {
  const up = lines.join('\n').toUpperCase();
  const company = COMPANIES.find(([, pats]) => pats.some((p) => p.test(up)))?.[0] || '';
  if (!company) return null;
  const upn = up.replace(/6EM(?=\s*M)/g, 'GEM').replace(/NM\s*-?\s*MT/g, 'NM-MT');
  let grade: number | null = null;
  let label = '';
  for (const [re, g, lab] of GRADE_WORDS) {
    const m = upn.match(re);
    if (m) {
      grade = g;
      label = m[0].replace(/(^|\s)[\d.]+(?=\s|$)|\d+(\.\d)?$|^\d+(\.\d)?/g, ' ').replace(/\s+/g, ' ').trim() || lab;
      break;
    }
  }
  if (grade == null) {
    const n = lines.map((l) => l.trim()).find((l) => /^(10|9\.5|[1-9](\.5)?)$/.test(l));
    if (n) grade = parseFloat(n);
    if (/GEM\s*M(INT|T)/.test(upn)) label = 'GEM MINT';
  }
  const certs = [...up.replace(/ /g, '').matchAll(/(^|\D)(\d{7,10})(?!\d)/g)].map((m) => m[2]).filter((c) => !/^(19|20)\d{2}$/.test(c));
  const cert = certs.sort((a, b) => b.length - a.length)[0] || '';
  const qualifiers = company === 'PSA' ? ['OC', 'ST', 'PD', 'OF', 'MK', 'MC'].filter((q) => new RegExp(`\\b${q}\\b`).test(up)) : [];
  const skip = /PSA|CGC|BGS|BECKETT|SGC|\bTAG\b|CERT|GRADING|GUARANT|AUTHENTIC|PRISTINE|GEM|MINT|NM-MT|EX-MT|CENTERING|CORNERS|EDGES|SURFACE|^\d{7,10}$|^\s*(10|9\.5|[1-9](\.5)?)\s*$/i;
  const descLines = lines.map((t) => t.replace(/6EM\s*M(IN)?T|GEM\s*M(IN)?T|NM\s*-?\s*MT/gi, ' ').trim()).filter((t) => t.length > 1 && !skip.test(t)).slice(0, 4);
  const desc = descLines.join(' ');
  const num = desc.match(/#\s*([A-Z]{0,4}-?\d{1,4}[A-Z]?)/i) || desc.match(/\b(\d{1,3}\/\d{2,3})\b/);
  const year = desc.match(/\b(19[4-9]\d|20[0-3]\d)\b/)?.[1] || '';
  return {
    company, grade, label, cert, qualifiers, desc, descLines, number: num ? num[1] : '', year,
    lookup: cert && LOOKUP[company] ? LOOKUP[company].replace('{c}', cert) : '',
  };
}

export const gradeText = (s: SlabInfo) => `${s.company}${s.label && s.label !== 'AUTHENTIC' ? ` ${s.label}` : ''} ${s.grade ?? s.label ?? '?'}${s.qualifiers.length ? ` ${s.qualifiers.join(' ')}` : ''}`.replace(/\s+/g, ' ').trim();

export function nameGuess(s: SlabInfo) {
  return s.desc
    .replace(/\b(19[4-9]\d|20[0-3]\d)\b/g, ' ')
    .replace(/#\s*\S+/g, ' ')
    .replace(/\b\d{1,3}\/\d{2,3}\b/g, ' ')
    .replace(/\b(POKEMON|POKÉMON|JAPANESE|ENGLISH|TOPPS|PANINI|PRIZM|BOWMAN|UPPER DECK|DONRUSS|KAKAWOW|HOLO|1ST EDITION|SPECIAL ILLUSTRATION RARE|ILLUSTRATION RARE|FULL ART|PROMO)\b/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
