import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, LayoutRectangle, Linking, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import Slider from '@react-native-community/slider';
import { C, S, money } from '../theme';
import type { Settings } from '../types';
import { Btn, Chip, LinkRow, Section, Slab, Thumb, Verdict } from '../components/ui';
import { Candidate, DB_GAMES, soldLinks } from '../core/databases';
import { cardBack, identify, Scored } from '../core/identify';
import { gradeText, nameGuess, readLabel, SlabInfo } from '../core/slab';
import { CatalogRow, CardFields, Sale, Store } from '../core/community';
import { CARD_STYLES, CONDITION_HELP, CONDITION_OPTIONS, GUIDE, GradeResult, cardStyle, estimate, graderCaps, subgradeToOption } from '../core/grading';
import { CardStyle, Centering, centeringText, centeringWorst, cropAndTrim, findLines, fingerprintCard, fingerprintRemote, hashDistance, Lines, measureCentering, pixels, thumbnail } from '../core/imageTools';
import { ocrAvailable, parseText, readText } from '../core/ocr';
import { analyzeWithAI } from '../core/ai';
import { Inspection, inspectCard, LEGEND } from '../core/condition';
import { AutographResult, checkAutograph, SIGNED } from '../core/autograph';
import CenteringTool from '../components/CenteringTool';
import { Card as CatCard, closestRemote, imageUrl, matchText, photoLookup, printRunLabel, searchRemote, sets as catSets, siblings, value as catValue } from '../core/catalog';
import { recordFromCatalog } from '../core/portfolio';
import { RarityChip } from '../components/cards';
import { useApp } from '../appContext';
import { quickIdentify, recordFromScan } from '../core/quickScan';
import { playerName, refineMatches } from '../core/verify';
import { addHistory, clearHistory, loadHistory, onHistory, removeHistory, ScanItem, updateHistory } from '../core/scanHistory';

export const GAMES = ['Auto', 'Pokémon', 'Pokémon Japanese / Korean', 'Yu-Gi-Oh!', 'Magic: The Gathering', 'Lorcana', 'One Piece', 'Dragon Ball', 'Digimon', 'Star Wars', 'Marvel', 'Gundam', 'Riftbound', 'Harry Potter', 'Garbage Pail Kids', 'Kakawow', 'Baseball', 'Basketball', 'Football', 'Soccer', 'Hockey', 'Non-sport', 'Other TCG'];
const STYLE_LABELS: Record<CardStyle, string> = { standard: 'Standard (bordered)', full_art: 'Full art / borderless', die_cut: 'Die-cut', vintage: 'Vintage / square corners' };
const TYPES = ['Base', 'Holo', 'Reverse Holo', 'Full Art', 'Secret Rare', 'Rookie', 'Parallel', 'Insert', 'Autograph', 'Relic', 'Promo', 'Custom', 'Other'];
const MATCH_STRONG = 10;
const MATCH_WEAK = 16;
const OFFICIAL_OK = 16;
const OFFICIAL_BAD = 24;
const EMPTY: CardFields = { game: '', name: '', set: '', number: '', year: '', brand: '', rarity: '', variant: '', card_type: 'Base' };

interface Shot {
  uri: string;
  base64: string;
  /** trimmed to the card with the camera guide (vs. a loose photo from the library) */
  tight?: boolean;
}
type Phase = 'capture' | 'review' | 'working' | 'result';

export default function ScanScreen({ settings, apiKey, store, goSettings, onSaved }: { settings: Settings; apiKey: string; store: Store; goSettings: () => void; onSaved: () => void }) {
  const [perm, requestPerm] = useCameraPermissions();
  const cam = useRef<CameraView>(null);
  const [camBox, setCamBox] = useState<LayoutRectangle | null>(null);
  const [guideBox, setGuideBox] = useState<LayoutRectangle | null>(null);
  const [phase, setPhase] = useState<Phase>('capture');
  const [side, setSide] = useState<'front' | 'back'>('front');
  const [front, setFront] = useState<Shot | null>(null);
  const [back, setBack] = useState<Shot | null>(null);
  const frontState = front;
  const backState = back;
  const [game, setGame] = useState('Auto');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');

  const [phash, setPhash] = useState('');
  const [thumb, setThumb] = useState('');
  const [rawText, setRawText] = useState('');
  const [setCode, setSetCode] = useState('');
  const [community, setCommunity] = useState<CatalogRow[]>([]);
  const [candidates, setCandidates] = useState<Scored[]>([]);
  const [slab, setSlab] = useState<SlabInfo | null>(null);
  const [fields, setFields] = useState<CardFields>(EMPTY);
  const [source, setSource] = useState('');
  const [chosen, setChosen] = useState<Candidate | null>(null);
  const [aiRes, setAiRes] = useState<any>(null);
  const [useAiGrade, setUseAiGrade] = useState(true);
  const [autoCen, setAutoCen] = useState<Centering | null>(null);
  const [cen, setCen] = useState<Centering>({ left: 40, right: 40, top: 40, bottom: 40 });
  const [backCen, setBackCen] = useState<Centering | null>(null);
  const [autoLines, setAutoLines] = useState<Lines | null>(null);
  const [lineStatus, setLineStatus] = useState('');
  const [refineNote, setRefineNote] = useState(''); // serial / back / correction that picked the match
  const [corners, setCorners] = useState('');
  const [edges, setEdges] = useState('');
  const [surface, setSurface] = useState('');
  const [insp, setInsp] = useState<Inspection | null>(null);
  const [inspBack, setInspBack] = useState<Inspection | null>(null);
  const [view, setView] = useState('Defect map');
  // card layout (full art, die-cut, vintage) steers the centering lines and the condition check
  const [stylePick, setStylePick] = useState<'auto' | CardStyle>('auto');
  const [lookFull, setLookFull] = useState(false);
  const [offUrl, setOffUrl] = useState('');
  const first = useRef<{ lines: Lines | null; status: string; cen: Centering; insp: Inspection | null } | null>(null);
  const styleSig = useRef('');
  const styleReq = useRef(0); // only the latest re-check may update the screen
  const [autoRes, setAutoRes] = useState<AutographResult | null>(null);
  const backText = useRef<{ uri: string; text: string } | null>(null);
  const [sales, setSales] = useState<Sale[]>([]);
  const [saved, setSaved] = useState<{ vault?: boolean; wish?: boolean; comm?: boolean; fake?: boolean }>({});
  const [fakeWhy, setFakeWhy] = useState('');
  const [showFake, setShowFake] = useState(false);
  const [sale, setSale] = useState({ grade: 'PSA 10', price: '', url: '' });
  const abort = useRef<AbortController | null>(null);
  const app = useApp();
  const [bulk, setBulk] = useState(false);
  const [tally, setTally] = useState<{ n: number; value: number }>({ n: 0, value: 0 });
  const [catHits, setCatHits] = useState<CatCard[]>([]);
  const [catPick, setCatPick] = useState<CatCard | null>(null);
  const aiOn = settings.provider !== 'off' && !!apiKey;
  // live scanner (tap anywhere to scan) vs. the step-by-step front + back grading capture
  const [mode, setMode] = useState<'live' | 'grade'>('live');
  const [scanning, setScanning] = useState(false);
  const [last, setLast] = useState<ScanItem | null>(null);
  const [history, setHistory] = useState<ScanItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const shots = useRef(new Map<string, Shot>());
  const curItem = useRef<string | null>(null); // history entry being graded
  useEffect(() => {
    loadHistory().then(setHistory);
    const off = onHistory(setHistory);
    return () => { off(); };
  }, []);

  /* ---------- capture ---------- */
  function guideRect(w: number, h: number) {
    if (!camBox || !guideBox) return undefined;
    const s = Math.max(camBox.width / w, camBox.height / h); // preview is "cover"
    const offX = (camBox.width - w * s) / 2;
    const offY = (camBox.height - h * s) / 2;
    return { x: (guideBox.x - offX) / s, y: (guideBox.y - offY) / s, w: guideBox.width / s, h: guideBox.height / s };
  }
  const store2 = (s: Shot) => {
    if (side === 'front' && bulk) {
      setFront(s);
      setBack(null);
      analyze(s);
      return;
    }
    if (side === 'front') {
      setFront(s);
      if (back) setPhase('review');
      else setSide('back');
    } else {
      setBack(s);
      setPhase('review');
    }
  };
  async function snap() {
    if (!cam.current || busy) return;
    setBusy(true);
    try {
      const pic = await cam.current.takePictureAsync({ quality: 0.95, shutterSound: false });
      store2({ ...(await cropAndTrim(pic.uri, pic.width, pic.height, guideRect(pic.width, pic.height))), tight: true });
    } catch {
      setError("Couldn't take the photo. Try again.");
    } finally {
      setBusy(false);
    }
  }
  async function pick() {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 1, allowsEditing: true, aspect: [63, 88] });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    setBusy(true);
    try {
      store2({ ...(await cropAndTrim(a.uri, a.width, a.height)), tight: false });
    } finally {
      setBusy(false);
    }
  }

  /* ---------- live scanner ---------- */
  async function liveIdentify(shot: Shot) {
    const it = await quickIdentify(shot.uri, game, store);
    shots.current.set(it.id, shot);
    await addHistory(it);
    setLast(it);
  }
  async function tapScan() {
    if (!cam.current || scanning) return;
    setScanning(true);
    setError('');
    try {
      const pic = await cam.current.takePictureAsync({ quality: 0.92, shutterSound: false });
      await liveIdentify({ ...(await cropAndTrim(pic.uri, pic.width, pic.height, guideRect(pic.width, pic.height))), tight: true });
    } catch (e: any) {
      setError(`Couldn't scan that: ${e?.message || e}. Try again.`);
    } finally {
      setScanning(false);
    }
  }
  async function pickLive() {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 1 });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    setScanning(true);
    try {
      await liveIdentify({ ...(await cropAndTrim(a.uri, a.width, a.height)), tight: false });
    } catch (e: any) {
      setError(`Couldn't scan that photo: ${e?.message || e}`);
    } finally {
      setScanning(false);
    }
  }
  async function addItem(it: ScanItem, list: 'collection' | 'wishlist' = 'collection') {
    if (app.needsCode) return setError('Set a vault code (6+ characters) in Settings first.');
    const rec = recordFromScan(it, list);
    if (!rec) return setError('This card wasn’t identified yet. Tap Grade to fill in its details, then add it.');
    try {
      await app.addRecord(rec, list);
      if (it.catalog_key && it.phash) store.addCorrection(it.phash, it.catalog_key).catch(() => {});
      const patch = list === 'wishlist' ? { wish: true } : { added: true };
      await updateHistory(it.id, patch);
      if (last?.id === it.id) setLast({ ...it, ...patch });
      onSaved();
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  }
  function gradeItem(it: ScanItem) {
    const shot = shots.current.get(it.id) || { uri: it.uri, base64: '', tight: true };
    curItem.current = it.id;
    setShowHistory(false);
    setFront(shot);
    setBack(null);
    setSide('front');
    analyze(shot);
  }

  /* ---------- analysis ---------- */
  async function findCandidates(name: string, number: string, code: string, g: string, cardUri: string, lines: string[] = [], rawText = '') {
    const list: Scored[] = await identify(lines.length ? lines : [name, number].filter(Boolean), rawText || `${name}\n${number}`, name, number, code, g);
    const mine = await fingerprintCard(cardUri);
    await Promise.all(
      list.slice(0, 6).map(async (c) => {
        const off = c.image_url ? await fingerprintRemote(c.image_url) : null;
        c.official_distance = off ? hashDistance(mine, off) : null;
      }),
    );
    // text evidence first; a matching artwork adds a little, a clearly different one takes a little away
    const adj = (c: Scored) => c.score + (c.official_distance != null ? (c.official_distance <= 12 ? 8 : c.official_distance > 26 ? -12 : 0) : 0);
    list.sort((a, b) => adj(b) - adj(a));
    return list;
  }

  function pickCatalog(c: CatCard) {
    setFields(recordFromCatalog(c).card);
    setCatPick(c);
    setChosen(null);
    setSource('card database');
  }
  function pickCandidate(c: Scored) {
    setCatPick(null);
    setFields({ game: c.game, name: c.name, set: c.set, number: c.number, year: c.year, brand: c.brand, rarity: c.rarity, variant: c.variant, card_type: TYPES.includes(c.card_type) ? c.card_type : 'Other' });
    setChosen(c);
    setSource(c.source);
  }
  function pickCommunity(m: CatalogRow) {
    setCatPick(null);
    setFields({ game: m.game, name: m.name, set: m.set_name, number: m.number, year: m.year, brand: m.brand, rarity: m.rarity, variant: m.variant, card_type: m.card_type || 'Base' });
    setSource('community');
    setChosen(null);
  }

  async function analyze(shot?: Shot) {
    const front = shot || frontState;
    if (!front) return;
    const back = shot ? null : backState;
    setError('');
    setPhase('working');
    styleReq.current++; // drop any re-check still running for the previous card
    setStylePick('auto');
    setOffUrl('');
    setAutoRes(null);
    setRefineNote('');
    abort.current = new AbortController();
    try {
      setProgress('Fingerprinting and measuring centering…');
      const [ph, th, ac, bc] = await Promise.all([fingerprintCard(front.uri), thumbnail(front.uri, 180), measureCentering(front.uri), back ? measureCentering(back.uri) : Promise.resolve(null)]);
      setPhash(ph);
      setThumb(th);
      setAutoCen(ac);
      let fl0: Awaited<ReturnType<typeof findLines>> | null = null;
      try {
        const fl = await findLines(front.uri, front.tight !== false);
        fl0 = fl;
        setLookFull(fl.looksFullArt);
        setAutoLines(fl.lines);
        const miss = Object.entries(fl.found).filter(([, ok]) => !ok).map(([k]) => k);
        setLineStatus(miss.length ? `Auto-placed, but no clear border on the ${miss.join(', ')} (full-art card?). Set those lines yourself.` : 'Auto-placed: card edges and inner border found on all four sides.');
        const L = fl.lines;
        if (!miss.length) setCen({ left: Math.round(L.il - L.ol), right: Math.round(L.or - L.ir), top: Math.round(L.it - L.ot), bottom: Math.round(L.ob - L.ib) });
      } catch {
        setLookFull(false);
        setAutoLines(null);
        setLineStatus('');
      }
      setProgress('Inspecting corners, edges and surface…');
      const [fi, bi] = await Promise.all([inspectCard(front.uri).catch(() => null), back ? inspectCard(back.uri, null, true).catch(() => null) : Promise.resolve(null)]);
      setInsp(fi);
      setInspBack(bi);
      setCorners('');
      setEdges('');
      setSurface('');
      setCen(ac || { left: 40, right: 40, top: 40, bottom: 40 });
      setBackCen(bc);
      // what the standard layout gave, to go back to if the card style is switched back
      const miss0 = fl0 ? Object.values(fl0.found).filter((ok) => !ok).length : 0;
      first.current = { lines: fl0?.lines ?? null, status: fl0 ? (miss0 ? 'Auto-placed, but no clear border on some sides (full-art card?). Set those lines yourself.' : 'Auto-placed: card edges and inner border found on all four sides.') : '', cen: ac || { left: 40, right: 40, top: 40, bottom: 40 }, insp: fi };
      styleSig.current = `${front.uri}|standard|`;

      setProgress('Reading the text on the card…');
      const lines = await readText(front.uri);
      const backOf = cardBack(lines, ph);
      if (backOf) {
        setPhase('review');
        setError(`That's the back of a ${backOf} card. Take the front photo first (step 1), then the back (step 2); the back is used for grading.`);
        return;
      }
      const parsed = parseText(lines, game === 'Auto' ? '' : game);
      const sl = readLabel(lines);
      setSlab(sl);
      if (sl) {
        parsed.name = nameGuess(sl) || parsed.name;
        parsed.number = sl.number || parsed.number;
        parsed.year = sl.year || parsed.year;
        if (/POK[EÉ]MON/.test(sl.desc.toUpperCase())) parsed.game = 'Pokémon';
      }
      setRawText(parsed.rawText);
      setSetCode(parsed.setCode);
      const g = game === 'Auto' ? parsed.game : game;

      setProgress('Checking the community catalog…');
      let comm: CatalogRow[] = [];
      try {
        comm = (await store.fingerprints())
          .map((r) => ({ ...r, distance: hashDistance(ph, r.phash) }))
          .filter((r) => r.distance! <= MATCH_WEAK)
          .sort((a, b) => a.distance! - b.distance! || b.confirmations - a.confirmations)
          .slice(0, 5);
      } catch {}
      setCommunity(comm);

      let f: CardFields = { ...EMPTY, game: g, name: parsed.name, number: parsed.number || parsed.setCode, year: parsed.year, brand: parsed.brand, variant: parsed.serial ? `Serial ${parsed.serial}` : '' };
      let src = parsed.name ? 'text' : '';
      let pick: Scored | null = null;
      const strong = comm.find((c) => !c.is_fake && c.distance! <= MATCH_STRONG);
      if (strong) {
        f = { game: strong.game, name: strong.name, set: strong.set_name, number: strong.number, year: strong.year, brand: strong.brand, rarity: strong.rarity, variant: strong.variant, card_type: strong.card_type || 'Base' };
        src = 'community';
      }

      // Built-in card database first: a card code like CDT-BBG-199 pins the exact parallel.
      if (!(DB_GAMES.includes(g) || ['One Piece', 'Dragon Ball', 'Digimon'].includes(g))) {
        // 'MIKE' / 'TROUT' on separate lines -> 'Mike Trout' (not the team name)
        const pn = await playerName(lines).catch(() => '');
        if (pn && !pn.toLowerCase().split(' ').every((w) => (parsed.name || '').toLowerCase().includes(w))) {
          parsed.name = pn;
          f = { ...f, name: f.name && src === 'community' ? f.name : pn };
        }
      }
      const cm = matchText(parsed.rawText, parsed.name, parsed.number);
      let byPicture = false;
      let closestHit = false;
      // picture alone: this scan's fingerprint against every price-guide photo (no readable text needed)
      if (!cm.byCode) {
        try {
          setProgress('Matching the picture…');
          const pm = await photoLookup(await fingerprintCard(front.uri), 12, 8, game === "Auto" ? "" : game);
          // unrelated cards often sit ~12 apart: only a close picture match counts on its own
          if (pm.length && pm[0].distance <= 6) {
            const byPic = pm.map((m) => m.card);
            cm.cards = [...byPic, ...cm.cards.filter((c) => !byPic.some((b) => b.key === c.key))];
            byPicture = true;
          }
        } catch {
          /* fingerprints not downloaded yet and offline */
        }
      }
      if (!cm.byCode && parsed.name && !DB_GAMES.includes(g)) {
        // also look in the downloadable sets (every Upper Deck / Topps baseball card...)
        try {
          setProgress('Searching the card database…');
          const more = await searchRemote(`${parsed.name} ${parsed.number ? parsed.number.split('/')[0] : ''}`, 20);
          cm.cards = [...cm.cards, ...more.filter((m) => !cm.cards.some((c) => c.key === m.key))];
        } catch {
          /* offline: bundled cards only */
        }
      }
      if (!cm.byCode && !cm.cards.length && (parsed.name || parsed.rawText)) {
        // no word-for-word match: the closest card names (misread letters, missing words)
        try {
          setProgress('Finding the closest match…');
          cm.cards = await closestRemote(parsed.rawText, parsed.name, parsed.number);
          closestHit = cm.cards.length > 0;
        } catch {}
      }
      // photo match against the price-guide pictures picks the exact card and parallel
      if (!cm.byCode && cm.cards.length) {
        setProgress('Comparing with card photos…');
        const pool: CatCard[] = [];
        const seenImg = new Set<string>();
        for (const c of cm.cards.slice(0, 6).flatMap((c) => [c, ...siblings(c)])) {
          if (!c.img || c.img.startsWith('~') || seenImg.has(c.img)) continue;
          seenImg.add(c.img);
          pool.push(c);
          if (pool.length >= 16) break;
        }
        if (pool.length) {
          const mine = await fingerprintCard(front.uri);
          const dists = await Promise.all(pool.map(async (c) => {
            const fp = await fingerprintRemote(imageUrl(c)[0]);
            return { c, d: fp ? hashDistance(mine, fp) : 64 };
          }));
          dists.sort((x, y) => x.d - y.d);
          if (dists[0] && dists[0].d <= 14) {
            cm.cards = [dists[0].c, ...cm.cards.filter((c) => c.key !== dists[0].c.key)];
          }
        }
      }
      // corrections people made before, the card back (number, © year) and a serial number on the card
      if (!cm.byCode) {
        try {
          setProgress('Checking serial number and back…');
          const backLines = back ? await readText(back.uri).catch(() => [] as string[]) : [];
          const r = await refineMatches(cm.cards, { phash: ph, text: parsed.rawText, number: parsed.number, backLines, tcg: !!g && DB_GAMES.includes(g), store });
          cm.cards = r.cards;
          if (r.notes.length) closestHit = true; // a correction or serial is enough to take the top card
          setRefineNote(r.notes[0] || '');
        } catch {}
      }
      setCatHits(cm.cards.slice(0, 6));
      let cat: CatCard | null = null;
      if (cm.cards.length && (cm.byCode || !strong)) {
        const top = cm.cards[0];
        const nameOk = !parsed.name || top.name.toLowerCase().split(/\s+/).some((w) => w.length > 2 && parsed.rawText.toLowerCase().includes(w));
        if (cm.byCode || byPicture || nameOk || closestHit) {
          cat = top;
          f = recordFromCatalog(top).card;
          src = 'card database';
        }
      }

      let cands: Scored[] = [];
      if (!cat && (!g || DB_GAMES.includes(g)) && (f.name || f.number)) {
        setProgress('Searching free card databases…');
        cands = await findCandidates(f.name, f.number, parsed.setCode, g, front.uri, sl ? sl.descLines : lines, sl ? sl.desc : parsed.rawText);
        const best = cands[0];
        if (best && (best.score >= 45 || (best.official_distance != null && best.official_distance <= OFFICIAL_OK)) && src !== 'community') {
          pick = best;
        }
      }
      setCandidates(cands);

      let ai: any = null;
      if (aiOn) {
        setProgress('AI boost: identifying, checking authenticity and grading…');
        try {
          const hint = cands.slice(0, 5).map((c) => `${c.name} | ${c.set} | ${c.number} | ${c.rarity}`).join('; ');
          ai = await analyzeWithAI(settings, apiKey, front.base64, back?.base64 || null, parsed.rawText, hint, abort.current.signal);
          const c = ai.card || {};
          if (!pick && !cat && src !== 'community') {
            f = { game: GAMES.includes(c.game) ? c.game : c.game ? 'Other TCG' : f.game, name: c.name || f.name, set: c.set || '', number: c.number || f.number, year: c.year || f.year, brand: c.brand || f.brand, rarity: c.rarity || '', variant: c.variant || f.variant, card_type: TYPES.includes(c.card_type) ? c.card_type : 'Other' };
            src = 'AI';
            if (!cands.length && (!f.game || DB_GAMES.includes(f.game)) && f.name) {
              cands = await findCandidates(f.name, f.number, parsed.setCode, f.game, front.uri);
              setCandidates(cands);
              const best = cands[0];
              if (best?.official_distance != null && best.official_distance <= OFFICIAL_OK) pick = best;
            }
          }
        } catch (e: any) {
          if (e?.name !== 'AbortError') setError(`AI boost failed: ${e?.message || e}. Free results are shown below.`);
        }
      }
      setAiRes(ai);
      setUseAiGrade(!!ai?.psa);
      setOffUrl(pick?.image_url || ''); // fading / error check against it runs with the card style (below)
      if (cat) pickCatalog(cat);
      else if (pick) pickCandidate(pick);
      else {
        setCatPick(null);
        setFields(f);
        setSource(src);
        setChosen(null);
      }
      setSaved({});
      setPhase('result');
    } catch (e: any) {
      setPhase('review');
      if (e?.name !== 'AbortError') setError(e?.message || 'Scan failed.');
    }
  }

  // Community sales for whatever card is currently confirmed.
  useEffect(() => {
    if (phase !== 'result' || !fields.name) return;
    const t = setTimeout(() => store.salesFor(fields).then(setSales).catch(() => setSales([])), 600);
    return () => clearTimeout(t);
  }, [phase, fields.game, fields.name, fields.set, fields.number, fields.variant, store]);

  function reset() {
    abort.current?.abort();
    curItem.current = null;
    setFront(null);
    setBack(null);
    setSide('front');
    setCandidates([]);
    setSlab(null);
    setInsp(null);
    setInspBack(null);
    setStylePick('auto');
    setOffUrl('');
    setAutoRes(null);
    setCommunity([]);
    setCatHits([]);
    setCatPick(null);
    setAiRes(null);
    setFields(EMPTY);
    setChosen(null);
    setError('');
    setPhase('capture');
    setLast(null);
  }

  /* ---------- derived ---------- */
  const fakeHits = community.filter((c) => c.is_fake && c.distance! <= MATCH_STRONG);
  const auth = (() => {
    const reasons: string[] = [];
    let v = 'not_checked';
    if (fakeHits.length) {
      v = 'likely_fake';
      reasons.push(`Looks like a card the community reported as fake (${fakeHits[0].name}): ${fakeHits[0].fake_reasons || 'no notes'}`);
    }
    const d = chosen?.official_distance;
    if (d != null) {
      if (d <= OFFICIAL_OK) {
        if (v !== 'likely_fake') v = 'looks_genuine';
        reasons.push(`Artwork matches the official ${chosen!.source} image (difference ${d}/64).`);
      } else if (d > OFFICIAL_BAD) {
        if (v !== 'likely_fake') v = 'unsure';
        reasons.push(`Artwork differs from the official image (difference ${d}/64): a different printing, a poor photo, or a fake.`);
      } else {
        if (v === 'not_checked') v = 'unsure';
        reasons.push(`Artwork is close to the official image but not exact (difference ${d}/64).`);
      }
    }
    const a = aiRes?.authenticity;
    const order = ['looks_genuine', 'not_checked', 'unsure', 'custom_or_proxy', 'likely_fake'];
    if (a?.verdict && order.includes(a.verdict) && order.indexOf(a.verdict) > order.indexOf(v)) v = a.verdict;
    else if (a?.verdict && v === 'not_checked') v = a.verdict;
    (a?.reasons || []).forEach((r: string) => reasons.push(`AI: ${r}`));
    return { verdict: v, reasons };
  })();

  // card layout: picked by the person, else from the rarity / parallel, else a thin grey frame seen in the photo
  const printedNo = /\d+\s*\/\s*\d+/.exec(rawText)?.[0] || fields.number;
  const autoStyle0: CardStyle = cardStyle(`${fields.rarity} ${fields.variant}`, fields.name, fields.year, printedNo);
  const autoStyle: CardStyle = autoStyle0 === 'standard' && lookFull ? 'full_art' : autoStyle0;
  const style: CardStyle = stylePick !== 'auto' ? stylePick : autoStyle;
  const frontUri = front?.uri;
  const frontTight = front?.tight !== false;
  // Re-place the centering lines for the layout and re-run the condition check (strict whitening on a silver /
  // foil full-art frame, square corners on vintage, fading / error check against the official image).
  useEffect(() => {
    if (phase !== 'result' || !frontUri || !first.current) return;
    const sig = `${frontUri}|${style}|${offUrl}`;
    if (styleSig.current === sig) return;
    const [pu, ps] = styleSig.current.split('|');
    styleSig.current = sig;
    const req = ++styleReq.current;
    const live = () => styleReq.current === req;
    const f0 = first.current;
    if (pu !== frontUri || ps !== style) {
      if (style === 'standard') {
        setAutoLines(f0.lines);
        setLineStatus(f0.status);
        setCen(f0.cen);
      } else {
        findLines(frontUri, frontTight, style)
          .then((fl) => {
            if (!live()) return;
            setAutoLines(fl.lines);
            const miss = Object.entries(fl.found).filter(([, ok]) => !ok).map(([k]) => k);
            const L = fl.lines;
            setLineStatus(`${STYLE_LABELS[style]}: ${style === 'full_art' ? 'inner lines looked for on the thin printed frame' : 'card edges and printed border'}${miss.length ? `; no clear line on the ${miss.join(', ')}. Set those yourself.` : '.'}`);
            if (!miss.length) setCen({ left: Math.round(L.il - L.ol), right: Math.round(L.or - L.ir), top: Math.round(L.it - L.ot), bottom: Math.round(L.ob - L.ib) });
          })
          .catch(() => {});
      }
    }
    if (style === 'standard' && !offUrl) setInsp(f0.insp);
    else
      inspectCard(frontUri, offUrl || null, false, { foilBorder: style === 'full_art', cornerRadius: style === 'vintage' ? 0 : undefined })
        .then((r) => live() && setInsp(r))
        .catch(() => {});
  }, [phase, frontUri, frontTight, style, offUrl]);

  // Autograph check: only shown when the card is marked signed or a likely signature is found
  const signedByType = fields.card_type === 'Autograph' || SIGNED.test(`${fields.rarity} ${fields.variant} ${fields.name}`);
  const backUri = back?.uri;
  useEffect(() => {
    if (phase !== 'result' || !frontUri) return;
    let live = true;
    (async () => {
      let bt = '';
      if (backUri) {
        if (backText.current?.uri !== backUri) backText.current = { uri: backUri, text: (await readText(backUri)).join('\n') };
        bt = backText.current.text;
      }
      const p = await pixels(frontUri, 630, 880);
      const r = checkAutograph(p.data, p.width, p.height, rawText, bt, signedByType ? 'Autograph' : '');
      if (live) setAutoRes(r);
    })().catch(() => live && setAutoRes(null));
    return () => {
      live = false;
    };
  }, [phase, frontUri, backUri, rawText, signedByType]);

  const autoSub = {
    corners: Math.min(insp?.subgrades.corners ?? 9, inspBack?.subgrades.corners ?? 10),
    edges: Math.min(insp?.subgrades.edges ?? 9, inspBack?.subgrades.edges ?? 10),
    surface: Math.min(insp?.subgrades.surface ?? 9, inspBack?.subgrades.surface ?? 10),
  };
  const pickedSub = (user: string, auto: number) => (user && user !== subgradeToOption(auto) ? user : auto);
  const overridden = [[corners, autoSub.corners], [edges, autoSub.edges], [surface, autoSub.surface]].some(([u, a]) => u && u !== subgradeToOption(a as number));
  const est = estimate(centeringWorst(cen), backCen ? centeringWorst(backCen) : null, pickedSub(corners, autoSub.corners), pickedSub(edges, autoSub.edges), pickedSub(surface, autoSub.surface));
  est.method = insp ? (overridden ? 'inspection + your checklist' : 'automatic inspection') : 'checklist';
  let grade: GradeResult = { ...est, centering: { front: centeringText(cen), back: backCen ? centeringText(backCen) : '' } };
  if (useAiGrade && aiRes?.psa) {
    const cnd = aiRes.condition || {};
    grade = {
      ...grade, method: 'ai', psa: aiRes.psa.grade, psa_label: aiRes.psa.label, psa_range: aiRes.psa.range,
      tag_score: aiRes.tag?.score, tag_grade: aiRes.tag?.grade, tag_label: aiRes.tag?.label,
      sub: { centering: cnd.centering?.score, corners: cnd.corners?.score, edges: cnd.edges?.score, surface: cnd.surface?.score },
      notes: (cnd.defects || []).slice(0, 6).join('; '),
    };
  }
  const gradedLabel = typeof grade.psa === 'number' ? `PSA ${Math.round(grade.psa)}` : '';
  const gradedSales = sales.filter((s) => gradedLabel && (s.grade || '').toUpperCase() === gradedLabel);
  const gradedMid = gradedSales.length ? [...gradedSales].map((s) => +s.price).sort((a, b) => a - b)[Math.floor(gradedSales.length / 2)] : null;
  const query = [fields.year, fields.brand, fields.set, fields.name, fields.number].filter(Boolean).join(' ');
  const catVal = catPick ? catValue(catPick) : null;
  const raw = catPick ? { mid: catVal?.[0] ?? undefined } : chosen?.raw || {};
  const cur = catPick ? 'USD' : chosen?.currency || 'USD';
  const catGraded = catPick ? (gradedLabel === 'PSA 10' ? catPick.psa10 : gradedLabel === 'PSA 9' ? catPick.psa9 : null) : null;
  const priceNote = catPick ? (catVal?.[1] ? `Typical sold price for ${catPick.variant || 'Base'} in this set` : `${catSets()[catPick.setId]?.source || ''} sold-listing price`) : chosen?.price_note || '';

  async function saveVault(list: 'collection' | 'wishlist' = 'collection') {
    if (app.needsCode) {
      setError('Set a vault code (6+ characters) in Settings first.');
      return;
    }
    const now = new Date().toISOString();
    const base = catPick ? recordFromCatalog(catPick) : null;
    await app.addRecord({
      v: 1, added_at: now, card: fields, grade, authenticity: auth,
      pricing: { raw, currency: cur, note: priceNote, graded_label: gradedLabel, graded_mid: gradedMid ?? catGraded, priced_at: now },
      match: { source, ref_id: chosen?.ref_id || '', image_url: chosen?.image_url || '', url: base?.match.url || chosen?.url || '', catalog_key: catPick?.key },
      thumb, phash, print_run: catPick?.printRun ?? null, odds: base?.odds || '',
    }, list);
    if (catPick && phash) store.addCorrection(phash, catPick.key).catch(() => {});
    if (list === 'wishlist') {
      setSaved((s) => ({ ...s, wish: true }));
      return;
    }
    setSaved((s) => ({ ...s, vault: true }));
    if (curItem.current) updateHistory(curItem.current, { added: true }).catch(() => {});
    setTally((t) => ({ n: t.n + 1, value: t.value + (Number(raw.mid) || 0) }));
    onSaved();
    if (bulk) reset();
  }

  /* ---------- render: capture ---------- */
  if (phase === 'capture') {
    if (!perm) return <View style={S.screen} />;
    if (!perm.granted)
      return (
        <View style={[S.screen, S.pad, { justifyContent: 'center' }]}>
          <Text style={S.h2}>Camera access</Text>
          <Text style={S.body}>Slab Scout needs the camera to photograph your cards.</Text>
          <Btn primary label="Allow camera" onPress={requestPerm} />
          <Btn label="Choose from photos instead" onPress={pick} />
        </View>
      );
    if (showHistory) return <HistoryView items={history} onClose={() => setShowHistory(false)} onAdd={addItem} onGrade={gradeItem} error={error} />;
    if (mode === 'live')
      return (
        <View style={S.screen} onLayout={(e) => setCamBox(e.nativeEvent.layout)}>
          <CameraView ref={cam} style={StyleSheet.absoluteFill} facing="back" />
          <Pressable style={StyleSheet.absoluteFill} onPress={tapScan} accessibilityLabel="Tap to scan the card" />
          <View style={st.overlay} pointerEvents="box-none">
            <View style={st.topBar}>
              <View style={[S.row, { justifyContent: 'space-between' }]}>
                <Text style={st.stepText}>{scanning ? 'SCANNING…' : 'TAP ANYWHERE TO SCAN'}</Text>
                <Pressable onPress={() => setShowHistory(true)} style={st.histBtn}>
                  <Text style={st.histText}>History{history.length ? ` · ${history.length}` : ''}</Text>
                </Pressable>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                {GAMES.map((g) => (
                  <Pressable key={g} onPress={() => setGame(g)} style={[st.gchip, game === g && { backgroundColor: C.accent }]}>
                    <Text style={[st.gchipText, game === g && { color: C.accentInk }]}>{g}</Text>
                  </Pressable>
                ))}
              </ScrollView>
              <Text style={st.tip}>Best: card laid flat on a plain, dark surface, filling the frame. Holding it or tilting it works too; it gets straightened.</Text>
            </View>
            <View style={st.guide} pointerEvents="none" onLayout={(e) => setGuideBox(e.nativeEvent.layout)}>
              {[st.tl, st.tr, st.bl, st.br].map((p, i) => (
                <View key={i} style={[st.corner, p]} />
              ))}
            </View>
            <View pointerEvents="box-none">
              {error ? <View style={[st.sheet, { paddingVertical: 10 }]}><Text style={{ color: C.warn }}>{error}</Text></View> : null}
              {scanning ? (
                <View style={[st.sheet, S.row]}>
                  <ActivityIndicator color={C.accent} />
                  <Text style={S.body}>Identifying…</Text>
                </View>
              ) : last ? (
                <ResultSheet it={last} onAdd={() => addItem(last)} onWish={() => addItem(last, 'wishlist')} onGrade={() => gradeItem(last)} onClose={() => setLast(null)} />
              ) : (
                <View style={st.bottomBar}>
                  <Pressable style={st.side} onPress={pickLive}>
                    <Text style={st.sideText}>Photos</Text>
                  </Pressable>
                  <Pressable style={[st.side, { width: 170 }]} onPress={() => { setMode('grade'); setSide('front'); }}>
                    <Text style={st.sideText}>Front + back grading ›</Text>
                  </Pressable>
                </View>
              )}
            </View>
          </View>
        </View>
      );
    return (
      <View style={S.screen} onLayout={(e) => setCamBox(e.nativeEvent.layout)}>
        <CameraView ref={cam} style={StyleSheet.absoluteFill} facing="back" />
        <View style={st.overlay} pointerEvents="box-none">
          <View style={st.topBar}>
            <View style={[S.row, { justifyContent: 'space-between' }]}>
              <Text style={st.stepText}>{bulk ? `BULK SCAN${tally.n ? ` · ${tally.n} added · ${money(tally.value)}` : ''}` : side === 'front' ? 'FRONT · step 1 of 2' : 'BACK · step 2 of 2'}</Text>
              <Pressable onPress={() => setMode('live')} style={st.histBtn}>
                <Text style={st.histText}>‹ Live scanner</Text>
              </Pressable>
            </View>
            <Text style={st.tip}>{'For grading: card out of its sleeve, laid flat on a plain dark surface, edges lined up with the corners. A held or tilted card still works; it gets straightened.'}</Text>
          </View>
          <View style={st.guide} pointerEvents="none" onLayout={(e) => setGuideBox(e.nativeEvent.layout)}>
            {[st.tl, st.tr, st.bl, st.br].map((p, i) => (
              <View key={i} style={[st.corner, p]} />
            ))}
          </View>
          <View style={st.bottomBar}>
            <Pressable style={st.side} onPress={pick}>
              <Text style={st.sideText}>Photos</Text>
            </Pressable>
            <Pressable style={st.shutter} onPress={snap} disabled={busy}>
              {busy ? <ActivityIndicator color={C.accentInk} /> : <View style={st.shutterIn} />}
            </Pressable>
            {side === 'back' ? (
              <Pressable style={st.side} onPress={() => setPhase('review')}>
                <Text style={st.sideText}>Skip back</Text>
              </Pressable>
            ) : (
              <View style={st.side} />
            )}
          </View>
        </View>
      </View>
    );
  }

  /* ---------- render: review / working / result ---------- */
  const setF = (k: keyof CardFields) => (v: string) => setFields((f) => ({ ...f, [k]: v }));
  return (
    <ScrollView style={S.screen} contentContainerStyle={[S.pad, { paddingBottom: 50 }]} keyboardShouldPersistTaps="handled">
      <View style={S.row}>
        {[front, back].map((s, i) => (
          <Pressable key={i} style={st.thumbBox} disabled={phase !== 'review'} onPress={() => { setSide(i === 0 ? 'front' : 'back'); setPhase('capture'); }}>
            {s ? <Image source={{ uri: s.uri }} style={{ width: '100%', height: '100%' }} /> : <Text style={S.muted}>{i === 0 ? 'Front' : 'No back photo'}</Text>}
            {phase === 'review' ? <Text style={st.retake}>Retake</Text> : null}
          </Pressable>
        ))}
      </View>

      {phase === 'review' && (
        <>
          <Text style={S.eyebrow}>What kind of card?</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {GAMES.map((g) => (
              <Pressable key={g} onPress={() => setGame(g)} style={[S.chip, { paddingVertical: 7, paddingHorizontal: 12 }, game === g && { backgroundColor: C.accent }]}>
                <Text style={[S.chipText, game === g && { color: C.accentInk }]}>{g}</Text>
              </Pressable>
            ))}
          </ScrollView>
          {!ocrAvailable() ? <Text style={S.muted}>Text reading needs the installed app (not Expo Go). You can still type the card details after scanning.</Text> : null}
          {error ? <View style={S.banner}><Text style={[S.body, { color: C.warn }]}>{error}</Text></View> : null}
          <Btn primary label="Scan card" onPress={() => analyze()} />
          <Btn label="Start over" onPress={reset} />
          {!aiOn ? (
            <Text style={[S.muted, { textAlign: 'center' }]} onPress={goSettings}>
              Free mode. Add a free Gemini key in Settings for AI identification and grading →
            </Text>
          ) : null}
        </>
      )}

      {phase === 'working' && (
        <View style={[S.card, { alignItems: 'center', paddingVertical: 28 }]}>
          <ActivityIndicator size="large" color={C.accent} />
          <Text style={[S.body, { textAlign: 'center' }]}>{progress}</Text>
          <Btn label="Cancel" onPress={() => { abort.current?.abort(); setPhase('review'); }} />
        </View>
      )}

      {phase === 'result' && (
        <>
          {error ? <View style={S.banner}><Text style={[S.body, { color: C.warn }]}>{error}</Text></View> : null}

          <View style={[S.card, { gap: 8 }]}>
            {slab ? (
              <View style={{ backgroundColor: C.surface2, borderRadius: 10, padding: 10, gap: 4 }}>
                <Text style={S.eyebrow}>Graded slab · {slab.company}</Text>
                <Text style={{ color: C.good, fontSize: 30, fontWeight: '800' }}>{gradeText(slab)}</Text>
                <Text style={S.muted}>Cert #{slab.cert || 'not read'}{slab.desc ? ` · ${slab.desc.slice(0, 80)}` : ''}</Text>
                {slab.lookup ? <Btn label={`Verify cert on ${slab.company} ↗`} onPress={() => Linking.openURL(slab.lookup).catch(() => {})} /> : null}
              </View>
            ) : null}
            <Text style={S.eyebrow}>{fields.name ? `Best match · ${source || 'your details'}` : 'No match yet'}</Text>
            <Text style={S.h2}>{fields.name || 'Type the name below, or turn on the AI boost'}</Text>
            <Text style={S.muted}>{[fields.rarity, fields.set, fields.number && `#${fields.number}`, fields.year].filter(Boolean).join(' · ')}</Text>
            {chosen && (chosen as Scored).why?.length ? <Text style={[S.muted, { fontSize: 12 }]}>Matched on: {(chosen as Scored).why.join(' · ')}</Text> : null}
            {chosen && (chosen as Scored).score < 50 ? <Text style={[S.body, { color: C.warn }]}>Not sure about this one. Check the name and number, or pick another match below.</Text> : null}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
              {fields.rarity ? <Chip gold label={fields.rarity} /> : null}
              <RarityChip printRun={catPick?.printRun} />
              {auth.verdict !== 'not_checked' ? <Chip label={auth.verdict === 'looks_genuine' ? 'looks genuine' : auth.verdict.replace(/_/g, ' ')} color={auth.verdict === 'looks_genuine' ? C.good : C.warn} /> : null}
            </View>
            <Text style={{ color: C.gold, fontSize: 34, fontWeight: '800', fontVariant: ['tabular-nums'] }}>{cur === 'EUR' && raw.mid ? `€${raw.mid.toFixed(2)}` : money(raw.mid)}</Text>
            <Text style={S.muted}>{raw.mid ? `raw · ${priceNote}` : 'No price yet: pick a match below or check the sold links'}{gradedLabel ? ` · est. ${gradedLabel}` : ''}</Text>
            <View style={S.row}>
              <Btn primary label={saved.vault ? 'Added ✓' : bulk ? 'Add & scan next' : 'Add to collection'} style={{ flex: 1.4 }} disabled={!fields.name || saved.vault} onPress={() => saveVault().catch((e) => setError(String(e?.message || e)))} />
              <Btn label={saved.wish ? '♡ Added' : '♡ Wishlist'} style={{ flex: 1 }} disabled={!fields.name || saved.wish} onPress={() => saveVault('wishlist').catch((e) => setError(String(e?.message || e)))} />
            </View>
            {catPick ? <Btn label="Open card page (all parallels, sales, odds)" onPress={() => app.openCard(catPick.key)} /> : null}
            {bulk ? <Btn label="Skip this card" onPress={reset} /> : null}
          </View>

          <Section n={1} title="Identify">
            {refineNote ? <Text style={[S.muted, { color: C.accent }]}>{refineNote}</Text> : null}
            {catHits.map((c) => {
              const [v, est] = catValue(c);
              const on = catPick?.key === c.key;
              return (
                <Pressable key={c.key} style={[st.candRow, on && { borderColor: C.accent }]} onPress={() => pickCatalog(c)}>
                  <View style={{ flex: 1, gap: 3 }}>
                    <Text style={[S.body, { fontWeight: '700' }]}>{c.name}</Text>
                    <Text style={S.muted}>{catSets()[c.setId]?.name} · #{c.number}</Text>
                    <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap' }}>
                      <Chip gold label={`${c.variant || 'Base'} ${printRunLabel(c.printRun)}`} />
                      <Chip label="card database" />
                      <Chip label={`${v ? (est ? '~' : '') + money(v) : '—'} raw`} />
                    </View>
                  </View>
                  <Text style={{ color: on ? C.accent : C.ink2, fontWeight: '800' }}>{on ? '✓' : 'Use'}</Text>
                </Pressable>
              );
            })}
            {community.filter((c) => !c.is_fake).slice(0, 3).map((m) => (
              <Pressable key={m.id} style={st.candRow} onPress={() => pickCommunity(m)}>
                <Thumb b64={m.thumb} />
                <View style={{ flex: 1, gap: 3 }}>
                  <Text style={[S.body, { fontWeight: '700' }]}>{m.name}</Text>
                  <Text style={S.muted}>{[m.set_name, m.number].filter(Boolean).join(' · ')}</Text>
                  <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap' }}>
                    <Chip gold label={m.rarity || 'rarity ?'} />
                    <Chip label={`community · seen ${m.confirmations}×`} />
                  </View>
                </View>
              </Pressable>
            ))}
            {candidates.map((c, i) => {
              const d = c.official_distance;
              return (
                <Pressable key={`${c.ref_id}-${i}`} style={[st.candRow, chosen === c && { borderColor: C.accent }]} onPress={() => pickCandidate(c)}>
                  {c.image_url ? <Image source={{ uri: c.image_url }} style={{ width: 46, height: 64, borderRadius: 4 }} /> : <Thumb />}
                  <View style={{ flex: 1, gap: 3 }}>
                    <Text style={[S.body, { fontWeight: '700' }]}>{c.name}</Text>
                    <Text style={S.muted}>{[c.set, c.number].filter(Boolean).join(' · ')}</Text>
                    <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap' }}>
                      <Chip gold label={c.rarity || '—'} />
                      <Chip label={c.source} />
                      {d != null ? <Chip label={d <= OFFICIAL_OK ? 'art matches' : d > OFFICIAL_BAD ? 'art differs' : 'art close'} /> : null}
                      <Chip label={`${money(c.raw.mid)} raw`} />
                    </View>
                  </View>
                  <Text style={{ color: chosen === c ? C.accent : C.ink2, fontWeight: '800' }}>{chosen === c ? '✓' : 'Use'}</Text>
                </Pressable>
              );
            })}
            {!candidates.length && !community.length && !catHits.length ? (
              <Text style={S.muted}>
                {fields.game && !DB_GAMES.includes(fields.game)
                  ? 'Sports and non-sport cards have no free master list. Fill in the details and tap Confirm for community, and the next scan of this card will be recognised.'
                  : 'No database match yet. Check the name and number, then search again.'}
              </Text>
            ) : null}
            <View style={{ gap: 6 }}>
              {([['name', 'Card name / player'], ['number', 'Card number'], ['set', 'Set'], ['year', 'Year'], ['brand', 'Brand / maker'], ['rarity', 'Rarity / parallel'], ['variant', 'Variant (1st Ed, serial #, auto…)']] as [keyof CardFields, string][]).map(([k, label]) => (
                <View key={k} style={{ gap: 2 }}>
                  <Text style={S.eyebrow}>{label}</Text>
                  <TextInput style={S.input} value={fields[k]} onChangeText={setF(k)} placeholderTextColor={C.ink2} />
                </View>
              ))}
              <Text style={S.eyebrow}>Type</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                {TYPES.map((t) => (
                  <Pressable key={t} onPress={() => setF('card_type')(t)} style={[S.chip, { paddingVertical: 6 }, fields.card_type === t && { backgroundColor: C.accent }]}>
                    <Text style={[S.chipText, fields.card_type === t && { color: C.accentInk }]}>{t}</Text>
                  </Pressable>
                ))}
              </ScrollView>
              <Btn label="Search databases again" onPress={async () => { setBusy(true); try { setCandidates(await findCandidates(fields.name, fields.number, setCode, fields.game, front!.uri)); } finally { setBusy(false); } }} disabled={busy || !front} />
              {source ? <Text style={S.muted}>Details from: {source}</Text> : null}
              {aiRes?.card?.rarity_evidence ? <Text style={S.muted}>AI rarity evidence: {aiRes.card.rarity_evidence}</Text> : null}
              {rawText ? <Text style={S.muted} numberOfLines={3}>Text read: {rawText.replace(/\n/g, ' · ')}</Text> : null}
            </View>
          </Section>

          <Section n={2} title="Authenticity">
            <Verdict verdict={auth.verdict} reasons={auth.reasons} />
            <Text style={S.muted}>Every card gets scanned and graded, fakes and customs included. These are warning signs, not proof.</Text>
          </Section>

          <Section n={3} title="Centering">
            <Text style={[S.h3, S.mono]}>Front {centeringText(cen)}{backCen ? `  ·  Back ${centeringText(backCen)}` : ''}</Text>
            {!autoCen ? <Text style={S.muted}>No clear border found (full-art card?). Set the lines yourself.</Text> : null}
            <CenteringTool key={front!.uri + (autoLines ? `L${autoLines.il.toFixed(1)},${autoLines.it.toFixed(1)},${autoLines.ir.toFixed(1)},${autoLines.ib.toFixed(1)}` : '')} uri={front!.uri} auto={autoCen || cen} lines={autoLines} status={lineStatus} onChange={setCen} />
            {(() => {
              const caps = graderCaps(centeringWorst(cen), backCen ? centeringWorst(backCen) : null, !['Baseball', 'Basketball', 'Football', 'Soccer', 'Hockey'].includes(fields.game));
              return (
                <View style={{ gap: 6 }}>
                  <Text style={S.eyebrow}>Card style</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                    {(['auto', 'standard', 'full_art', 'die_cut', 'vintage'] as const).map((k) => (
                      <Pressable key={k} onPress={() => setStylePick(k)} style={[S.chip, { paddingVertical: 6 }, stylePick === k && { backgroundColor: C.accent }]}>
                        <Text style={[S.chipText, stylePick === k && { color: C.accentInk }]}>{k === 'auto' ? `Auto · ${STYLE_LABELS[autoStyle]}` : STYLE_LABELS[k]}</Text>
                      </Pressable>
                    ))}
                  </ScrollView>
                  <Text style={S.muted}>{CARD_STYLES[style]}</Text>
                  <Text style={S.eyebrow}>Best grade the centering allows</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    {Object.entries(caps).map(([k, v]) => <Chip key={k} label={`${k} ${v}`} />)}
                  </View>
                  <Pressable onPress={() => setShowGuide((g) => !g)}><Text style={{ color: C.accent, fontWeight: '700' }}>{showGuide ? 'Hide' : 'How grading works ›'}</Text></Pressable>
                  {showGuide ? GUIDE.map(([t, b]) => (
                    <View key={t} style={{ gap: 2 }}>
                      <Text style={[S.body, { fontWeight: '700' }]}>{t}</Text>
                      <Text style={S.muted}>{b}</Text>
                    </View>
                  )) : null}
                </View>
              );
            })()}
          </Section>

          <Section n={4} title="Condition & grade">
            {aiRes?.psa ? (
              <View style={[S.row, { justifyContent: 'space-between' }]}>
                <Text style={S.body}>Use the AI's grade</Text>
                <Switch value={useAiGrade} onValueChange={setUseAiGrade} trackColor={{ true: C.accent, false: C.surface2 }} />
              </View>
            ) : null}
            {insp ? (
              <View style={{ gap: 8 }}>
                <Text style={S.eyebrow}>Automatic inspection</Text>
                {[...insp.photoNotes, ...(inspBack?.photoNotes || [])].map((n) => (
                  <View key={n} style={S.banner}><Text style={[S.muted, { color: C.warn }]}>{n}</Text></View>
                ))}
                <View style={S.row}>
                  {(['corners', 'edges', 'surface'] as const).map((k) => (
                    <View key={k} style={{ flex: 1, backgroundColor: C.surface2, borderRadius: 10, padding: 8 }}>
                      <Text style={S.eyebrow}>{k}</Text>
                      <Text style={{ color: autoSub[k] >= 9 ? C.good : autoSub[k] >= 7 ? C.warn : C.crit, fontSize: 22, fontWeight: '800' }}>{autoSub[k]}</Text>
                    </View>
                  ))}
                </View>
                {[...insp.findings, ...(inspBack?.findings || [])].sort((a, b) => b.severity - a.severity).slice(0, 10).map((f, i) => (
                  <Text key={i} style={S.body}>
                    {f.severity >= 0.6 ? '🔴' : f.severity >= 0.25 ? '🟠' : '🟡'} <Text style={{ fontWeight: '700' }}>{f.where}</Text>: {f.what}{f.sure === 'possible' ? ' (possible)' : ''}
                  </Text>
                ))}
                {!insp.findings.length && !inspBack?.findings.length ? <Text style={S.muted}>No corner whitening, edge chips, scratches or stains found in this photo.</Text> : null}
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                  {[...insp.views.map((v) => v.name), ...(inspBack ? inspBack.views.map((v) => `Back · ${v.name}`) : [])].map((n) => (
                    <Pressable key={n} onPress={() => setView(n)} style={[S.chip, { paddingVertical: 7, paddingHorizontal: 12 }, view === n && { backgroundColor: C.accent }]}>
                      <Text style={[S.chipText, view === n && { color: C.accentInk }]}>{n}</Text>
                    </Pressable>
                  ))}
                </ScrollView>
                {(() => {
                  const isBack = view.startsWith('Back · ');
                  const v = (isBack ? inspBack : insp)?.views.find((x) => x.name === view.replace('Back · ', ''));
                  if (!v) return null;
                  if (v.name === 'Corners')
                    return (
                      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                        {v.uris.map((u, i) => <Image key={i} source={{ uri: u }} style={{ width: '48%', aspectRatio: 1, borderRadius: 6 }} />)}
                      </View>
                    );
                  if (v.name === 'Edges')
                    return (
                      <View style={{ gap: 6 }}>
                        {v.uris.slice(0, 2).map((u, i) => <Image key={i} source={{ uri: u }} style={{ width: '100%', aspectRatio: 630 / 40, borderRadius: 4 }} />)}
                        <View style={{ flexDirection: 'row', gap: 6, justifyContent: 'center' }}>
                          {v.uris.slice(2).map((u, i) => <Image key={i} source={{ uri: u }} style={{ width: 40, height: 880 * (40 / 40) * 0.4, borderRadius: 4, resizeMode: 'stretch' }} />)}
                        </View>
                      </View>
                    );
                  return <Image source={{ uri: v.uris[0] }} style={{ width: '100%', aspectRatio: 63 / 88, borderRadius: 8 }} />;
                })()}
                {view.endsWith('Defect map') ? <Text style={S.muted}>{LEGEND}</Text> : null}
              </View>
            ) : null}
            {!(useAiGrade && aiRes?.psa) &&
              ([['corners', corners, setCorners], ['edges', edges, setEdges], ['surface', surface, setSurface]] as [string, string, (v: string) => void][]).map(([k, v, set]) => {
                const shown = v || subgradeToOption(autoSub[k as 'corners' | 'edges' | 'surface']);
                return (
                  <View key={k} style={{ gap: 4 }}>
                    <Text style={S.eyebrow}>{k}{insp ? ' (pre-set from the inspection; change it if it looks wrong)' : ''}</Text>
                    <Text style={S.muted}>{CONDITION_HELP[k]}</Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                      {CONDITION_OPTIONS.map(([o]) => (
                        <Pressable key={o} onPress={() => set(o)} style={[S.chip, { paddingVertical: 6 }, shown === o && { backgroundColor: C.accent }]}>
                          <Text style={[S.chipText, shown === o && { color: C.accentInk }]}>{o}</Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                );
              })}
            <View style={S.row}>
              <Slab who="PSA · estimate" grade={grade.psa} label={grade.psa_label} sub={grade.psa_range ? `Likely ${grade.psa_range}` : undefined} />
              <Slab who="TAG-style · est." grade={grade.tag_grade} label={grade.tag_label} sub={grade.tag_score ? `Score ${grade.tag_score} / 1000` : undefined} />
            </View>
            <Text style={S.muted}>
              {Object.entries(grade.sub || {}).filter(([, v]) => v != null).map(([k, v]) => `${k} ${v}`).join(' · ')}
              {est.centering_cap && est.centering_cap < 10 ? ` · centering alone caps PSA at ${est.centering_cap}` : ''}
            </Text>
            {grade.notes ? <Text style={S.muted}>AI noted: {grade.notes}</Text> : null}
            {autoRes && (autoRes.found || autoRes.certified || signedByType) ? (
              <View style={{ gap: 6, backgroundColor: C.surface2, borderRadius: 10, padding: 10 }}>
                <Text style={S.eyebrow}>Autograph{autoRes.kind ? ` · ${autoRes.kind}` : ''}</Text>
                {autoRes.autoGrade ? (
                  <Text style={S.body}>
                    Signature grade estimate <Text style={{ fontWeight: '800', color: autoRes.autoGrade >= 9 ? C.good : C.warn }}>{autoRes.autoGrade}</Text>
                  </Text>
                ) : null}
                {autoRes.box ? <SignatureCrop uri={front!.uri} box={autoRes.box} /> : null}
                {autoRes.notes.map((n) => <Text key={n} style={S.muted}>{n}</Text>)}
                <View style={S.banner}><Text style={S.muted}>{autoRes.verify}</Text></View>
              </View>
            ) : null}
          </Section>

          <Section n={5} title="Value">
            <View style={S.row}>
              <View style={[st.vbox, { backgroundColor: C.goldSoft }]}>
                <Text style={S.eyebrow}>Raw</Text>
                <Text style={[st.big, { color: C.gold }]}>{cur === 'EUR' && raw.mid ? `€${raw.mid.toFixed(2)}` : money(raw.mid)}</Text>
                <Text style={S.muted} numberOfLines={2}>{priceNote || 'Pick a database match for a market price'}</Text>
              </View>
              <View style={st.vbox}>
                <Text style={S.eyebrow}>{gradedLabel || 'Graded'}</Text>
                <Text style={st.big}>{gradedMid ? money(gradedMid) : catGraded ? money(catGraded) : '—'}</Text>
                <Text style={S.muted}>{gradedSales.length ? `median of ${gradedSales.length} community sale(s)` : catGraded ? 'price guide sold listings' : 'Check sold links below'}</Text>
              </View>
            </View>
            {sales.length ? (
              <View style={{ gap: 4 }}>
                <Text style={S.eyebrow}>Sales added by the community</Text>
                {sales.slice(0, 8).map((s, i) => (
                  <Text key={i} style={[S.body, S.mono]}>{s.grade} · {money(+s.price)} {s.sold_on ? `· ${s.sold_on}` : ''}</Text>
                ))}
              </View>
            ) : null}
            <LinkRow links={soldLinks(query || fields.name, gradedLabel, chosen?.image_url || '')} />
            <Text style={S.eyebrow}>Add a sale you saw (helps everyone)</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
              {['Raw', 'PSA 10', 'PSA 9', 'PSA 8', 'TAG 10', 'TAG 9', 'BGS 9.5', 'CGC 10', 'SGC 10'].map((g) => (
                <Pressable key={g} onPress={() => setSale((s) => ({ ...s, grade: g }))} style={[S.chip, sale.grade === g && { backgroundColor: C.accent }]}>
                  <Text style={[S.chipText, sale.grade === g && { color: C.accentInk }]}>{g}</Text>
                </Pressable>
              ))}
            </ScrollView>
            <View style={S.row}>
              <TextInput style={[S.input, { flex: 1 }]} placeholder="Sold for $" keyboardType="decimal-pad" value={sale.price} onChangeText={(v) => setSale((s) => ({ ...s, price: v }))} placeholderTextColor={C.ink2} />
              <Btn
                label="Add sale"
                disabled={!(+sale.price > 0) || !fields.name}
                onPress={async () => {
                  await store.addSale(fields, sale.grade, +sale.price, new Date().toISOString().slice(0, 10), sale.url);
                  setSale({ ...sale, price: '' });
                  setSales(await store.salesFor(fields));
                }}
              />
            </View>
          </Section>

          <Section n={6} title="Save">
            <Btn primary label={saved.vault ? 'In your collection ✓' : 'Add to collection'} disabled={!fields.name || saved.vault} onPress={() => saveVault().catch((e) => setError(String(e?.message || e)))} />
            <Btn
              label={saved.comm ? 'Added to community ✓' : 'Confirm for community'}
              disabled={!fields.name || saved.comm}
              onPress={async () => {
                try {
                  await store.addCard(fields, phash, await thumbnail(front!.uri, 140), source || 'manual');
                  setSaved((s) => ({ ...s, comm: true }));
                } catch (e: any) {
                  setError(String(e?.message || e));
                }
              }}
            />
            {showFake ? (
              <View style={{ gap: 6 }}>
                <TextInput style={S.input} placeholder="What gives it away? (font, no texture, glossy stock…)" value={fakeWhy} onChangeText={setFakeWhy} placeholderTextColor={C.ink2} multiline />
                <Btn
                  danger
                  label={saved.fake ? 'Reported ✓' : 'Submit fake report'}
                  disabled={saved.fake}
                  onPress={async () => {
                    await store.addCard(fields, phash, await thumbnail(front!.uri, 140), 'report', true, fakeWhy.slice(0, 1000));
                    setSaved((s) => ({ ...s, fake: true }));
                  }}
                />
              </View>
            ) : (
              <Btn danger label="Report as fake" onPress={() => setShowFake(true)} />
            )}
            <Btn label="Scan another card" onPress={reset} />
          </Section>
        </>
      )}
    </ScrollView>
  );
}

/** The strip of the card around the signature, with the signature boxed (box in 630x880 card px). */
function SignatureCrop({ uri, box }: { uri: string; box: [number, number, number, number] }) {
  const [bx, by, bw, bh] = box;
  const y0 = Math.max(0, by - 80);
  const sh = Math.min(880, by + bh + 80) - y0;
  return (
    <View style={{ width: '100%', aspectRatio: 630 / sh, overflow: 'hidden', borderRadius: 6 }}>
      <Image source={{ uri }} style={{ position: 'absolute', left: 0, width: '100%', top: `${(-y0 / sh) * 100}%`, height: `${(880 / sh) * 100}%` }} />
      <View
        style={{
          position: 'absolute', borderWidth: 3, borderColor: C.accent, borderRadius: 4,
          left: `${((bx - 6) / 630) * 100}%`, top: `${((by - 6 - y0) / sh) * 100}%`, width: `${((bw + 12) / 630) * 100}%`, height: `${((bh + 12) / sh) * 100}%`,
        }}
      />
    </View>
  );
}

function priceText(it: ScanItem) {
  if (it.price == null) return '—';
  return it.currency === 'EUR' ? `€${it.price.toFixed(2)}` : money(it.price);
}

function ResultSheet({ it, onAdd, onWish, onGrade, onClose }: { it: ScanItem; onAdd: () => void; onWish: () => void; onGrade: () => void; onClose: () => void }) {
  return (
    <View style={st.sheet}>
      <View style={[S.row, { alignItems: 'flex-start' }]}>
        {it.thumb ? <Image source={{ uri: `data:image/jpeg;base64,${it.thumb}` }} style={st.sheetImg} /> : null}
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={S.h3} numberOfLines={2}>{it.name || (it.note ? 'Not identified' : 'Unknown card')}</Text>
          <Text style={S.muted} numberOfLines={2}>{[it.set, it.number && `#${it.number}`, it.rarity].filter(Boolean).join(' · ') || it.note || ''}</Text>
          {it.name ? <Text style={{ color: C.gold, fontSize: 24, fontWeight: '800', fontVariant: ['tabular-nums'] }}>{priceText(it)}</Text> : null}
          {it.name && it.note ? <Text style={[S.muted, { color: C.warn }]}>{it.note}</Text> : null}
          {it.source ? <Text style={[S.muted, { fontSize: 11 }]}>{it.source}</Text> : null}
        </View>
        <Pressable onPress={onClose} hitSlop={12}><Text style={{ color: C.ink2, fontSize: 20 }}>✕</Text></Pressable>
      </View>
      <View style={S.row}>
        <Pressable style={[st.plus, it.added && { backgroundColor: C.good }]} disabled={it.added || !it.name} onPress={onAdd}>
          <Text style={st.plusText}>{it.added ? '✓' : '+'}</Text>
        </Pressable>
        <Btn label={it.wish ? '♡ Saved' : '♡'} style={{ flex: 0.6 }} disabled={it.wish || !it.name} onPress={onWish} />
        <Btn primary label="Grade ›" style={{ flex: 1 }} onPress={onGrade} />
      </View>
      <Text style={[S.muted, { fontSize: 11, textAlign: 'center' }]}>Tap the camera again for the next card · every scan is kept in History</Text>
    </View>
  );
}

function HistoryView({ items, onClose, onAdd, onGrade, error }: { items: ScanItem[]; onClose: () => void; onAdd: (it: ScanItem) => void; onGrade: (it: ScanItem) => void; error: string }) {
  const [filter, setFilter] = useState<'all' | 'not added'>('not added');
  const list = filter === 'all' ? items : items.filter((x) => !x.added);
  const total = list.reduce((a, x) => a + (x.price || 0), 0);
  return (
    <ScrollView style={S.screen} contentContainerStyle={[S.pad, { paddingBottom: 60, gap: 10 }]}>
      <View style={[S.row, { justifyContent: 'space-between' }]}>
        <Text style={S.h2}>Scan history</Text>
        <Btn label="Back to camera" onPress={onClose} />
      </View>
      <View style={S.row}>
        {(['not added', 'all'] as const).map((f) => (
          <Pressable key={f} onPress={() => setFilter(f)} style={[S.chip, filter === f && { backgroundColor: C.accent }]}>
            <Text style={[S.chipText, filter === f && { color: C.accentInk }]}>{f === 'all' ? `All (${items.length})` : `Not in collection (${items.filter((x) => !x.added).length})`}</Text>
          </Pressable>
        ))}
      </View>
      <Text style={S.muted}>{list.length} card{list.length === 1 ? '' : 's'} · {money(total)} raw</Text>
      {error ? <View style={S.banner}><Text style={[S.body, { color: C.warn }]}>{error}</Text></View> : null}
      {list.map((it) => (
        <View key={it.id} style={st.histRow}>
          {it.thumb ? <Image source={{ uri: `data:image/jpeg;base64,${it.thumb}` }} style={{ width: 44, height: 62, borderRadius: 4 }} /> : null}
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[S.body, { fontWeight: '700' }]} numberOfLines={1}>{it.name || 'Not identified'}</Text>
            <Text style={S.muted} numberOfLines={1}>{[it.set, it.number && `#${it.number}`].filter(Boolean).join(' · ') || it.note || ''}</Text>
            <Text style={[S.muted, { fontSize: 11 }]}>{new Date(it.at).toLocaleString()} · {priceText(it)}</Text>
          </View>
          <Pressable onPress={() => onGrade(it)} hitSlop={6}><Text style={{ color: C.accent, fontWeight: '800' }}>Grade</Text></Pressable>
          <Pressable style={[st.plusSm, it.added && { backgroundColor: C.good }]} disabled={it.added || !it.name} onPress={() => onAdd(it)}>
            <Text style={st.plusText}>{it.added ? '✓' : '+'}</Text>
          </Pressable>
          <Pressable onPress={() => removeHistory(it.id)} hitSlop={8}><Text style={{ color: C.ink2 }}>✕</Text></Pressable>
        </View>
      ))}
      {!list.length ? <Text style={S.muted}>Nothing here yet. Cards you scan show up here, so you can add them to your collection later.</Text> : null}
      {items.length ? <Btn label="Clear history (keeps nothing in your collection affected)" onPress={() => clearHistory()} /> : null}
    </ScrollView>
  );
}

const CARD_W = 250;
const st = StyleSheet.create({
  sheet: { backgroundColor: C.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: 14, gap: 10 },
  sheetImg: { width: 64, height: 89, borderRadius: 6 },
  plus: { width: 54, height: 46, borderRadius: 12, backgroundColor: C.accent, alignItems: 'center', justifyContent: 'center' },
  plusSm: { width: 36, height: 36, borderRadius: 18, backgroundColor: C.accent, alignItems: 'center', justifyContent: 'center' },
  plusText: { color: C.accentInk, fontSize: 26, fontWeight: '900', marginTop: -2 },
  histBtn: { backgroundColor: 'rgba(255,255,255,.14)', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
  histText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  histRow: { flexDirection: 'row', gap: 10, alignItems: 'center', backgroundColor: C.surface, borderRadius: 12, padding: 8 },
  gchip: { backgroundColor: 'rgba(255,255,255,.14)', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  gchipText: { color: '#fff', fontWeight: '700', fontSize: 12 },
  overlay: { flex: 1, justifyContent: 'space-between' },
  topBar: { backgroundColor: 'rgba(8,10,14,.65)', padding: 16, paddingTop: 12, gap: 4 },
  stepText: { color: C.accent, fontWeight: '800', letterSpacing: 1.2, fontSize: 13 },
  tip: { color: '#fff', fontSize: 14 },
  guide: { alignSelf: 'center', width: CARD_W, height: (CARD_W * 88) / 63 },
  corner: { position: 'absolute', width: 34, height: 34, borderColor: '#fff' },
  tl: { top: 0, left: 0, borderTopWidth: 4, borderLeftWidth: 4, borderTopLeftRadius: 10 },
  tr: { top: 0, right: 0, borderTopWidth: 4, borderRightWidth: 4, borderTopRightRadius: 10 },
  bl: { bottom: 0, left: 0, borderBottomWidth: 4, borderLeftWidth: 4, borderBottomLeftRadius: 10 },
  br: { bottom: 0, right: 0, borderBottomWidth: 4, borderRightWidth: 4, borderBottomRightRadius: 10 },
  bottomBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', backgroundColor: 'rgba(8,10,14,.65)', paddingVertical: 18 },
  shutter: { width: 76, height: 76, borderRadius: 38, backgroundColor: C.accent, alignItems: 'center', justifyContent: 'center' },
  shutterIn: { width: 60, height: 60, borderRadius: 30, borderWidth: 3, borderColor: C.accentInk },
  side: { width: 84, alignItems: 'center' },
  sideText: { color: '#fff', fontWeight: '700' },
  thumbBox: { flex: 1, aspectRatio: 63 / 88, backgroundColor: C.surface, borderRadius: 12, borderWidth: 1, borderColor: C.line, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  retake: { position: 'absolute', bottom: 8, backgroundColor: 'rgba(0,0,0,.7)', color: '#fff', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999, fontSize: 12, overflow: 'hidden' },
  candRow: { flexDirection: 'row', gap: 10, alignItems: 'center', backgroundColor: C.surface2, borderRadius: 10, padding: 8, borderWidth: 1, borderColor: 'transparent' },
  cl: { position: 'absolute', top: 0, bottom: 0, width: 2, backgroundColor: C.accent },
  ch: { position: 'absolute', left: 0, right: 0, height: 2, backgroundColor: C.accent },
  vbox: { flex: 1, backgroundColor: C.surface2, borderRadius: 12, padding: 12, gap: 2 },
  big: { color: C.ink, fontSize: 24, fontWeight: '800', fontVariant: ['tabular-nums'] },
});
