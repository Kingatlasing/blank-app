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
import { Card as CatCard, closestRemote, getCard, imageUrl, matchText, photoLookup, printRunLabel, searchRemote, sets as catSets, siblings, value as catValue } from '../core/catalog';
import { recordFromCatalog } from '../core/portfolio';
import { RarityChip, Sheet, SheetOption } from '../components/cards';
import { Icon } from '../components/visual';
import { useLayout } from '../layout';
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

/** Live-scanner zoom steps. expo-camera's zoom is 0..1 of the lens's range, so these are close to 1x / 1.5x / 2x, not exact on every phone. */
const ZOOMS: [string, number][] = [['1×', 0], ['1.5×', 0.07], ['2×', 0.14]];
const SCAN_GRADES = ['RAW', 'PSA 10', 'PSA 9', 'PSA 8', 'BGS 9.5', 'BGS 9', 'CGC 10', 'CGC 9.5', 'SGC 10', 'TAG 10'];
const SCAN_CONDS = ['NM', 'LP', 'MP', 'HP', 'DMG'];
const sameCard = (a: ScanItem | null, b: ScanItem | null) => !!a && !!b && (a.catalog_key && b.catalog_key ? a.catalog_key === b.catalog_key : !!a.name && a.name === b.name && a.number === b.number);

export default function ScanScreen({ settings, apiKey, store, goSettings, onSaved, onBack, onImmersive, paused }: {
  settings: Settings; apiKey: string; store: Store; goSettings: () => void; onSaved: () => void;
  /** leave the scanner (back to the previous tab) */
  onBack?: () => void;
  /** true while the full-screen camera is showing (the app hides the tab bar) */
  onImmersive?: (on: boolean) => void;
  /** another page (card, set, settings) is open on top: no auto-scanning */
  paused?: boolean;
}) {
  const L = useLayout();
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
  // live scanner controls
  const [zoomIdx, setZoomIdx] = useState(0);
  const [slabMode, setSlabMode] = useState(false); // Raw / Graded toggle: graded asks for the grade on each result
  const [auto, setAuto] = useState(false);
  const [gameSheet, setGameSheet] = useState(false);
  const [chipSheet, setChipSheet] = useState<'finish' | 'grade' | 'cond' | null>(null);
  const [choice, setChoice] = useState<{ grade: string; cond: string }>({ grade: 'RAW', cond: 'NM' });
  const [session, setSession] = useState<{ id: string; price: number }[]>([]);
  const [addedN, setAddedN] = useState<Record<string, number>>({});
  const lastRef = useRef<ScanItem | null>(null);
  lastRef.current = last;
  const camOn = phase === 'capture' && !!perm?.granted && !showHistory;
  useEffect(() => {
    onImmersive?.(camOn);
  }, [camOn]);
  useEffect(() => () => onImmersive?.(false), []);
  // new result: start from Raw / NM (or ask for the grade in Graded mode)
  useEffect(() => {
    setChoice({ grade: slabMode ? '' : 'RAW', cond: 'NM' });
  }, [last?.id]);
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
  async function liveIdentify(shot: Shot, quiet = false) {
    const it = await quickIdentify(shot.uri, game, store);
    // auto-scan: ignore frames with no card and the card that is already showing
    if (quiet && (!it.name || sameCard(it, lastRef.current))) return;
    shots.current.set(it.id, shot);
    await addHistory(it);
    setLast(it);
    setSession((s) => [...s, { id: it.id, price: it.price || 0 }]);
  }
  async function tapScan(quiet = false) {
    if (!cam.current || scanning) return;
    setScanning(true);
    if (!quiet) setError('');
    try {
      const pic = await cam.current.takePictureAsync({ quality: 0.92, shutterSound: false });
      await liveIdentify({ ...(await cropAndTrim(pic.uri, pic.width, pic.height, guideRect(pic.width, pic.height))), tight: true }, quiet);
    } catch (e: any) {
      if (!quiet) setError(`Couldn't scan that: ${e?.message || e}. Try again.`);
    } finally {
      setScanning(false);
    }
  }
  // Auto: scan again ~2.5 s after the scanner goes idle
  useEffect(() => {
    if (!auto || paused || mode !== 'live' || !camOn || scanning || gameSheet || chipSheet) return;
    const t = setTimeout(() => tapScan(true), 2500);
    return () => clearTimeout(t);
  }, [auto, paused, mode, camOn, scanning, gameSheet, chipSheet, last?.id]);
  /** Another parallel picked for the scanned card (finish chip). */
  async function pickFinish(it: ScanItem, c: CatCard) {
    const [v] = catValue(c);
    const patch: Partial<ScanItem> = { catalog_key: c.key, name: c.name, number: c.number, rarity: (c.variant || 'Base') + (c.printRun ? ` /${c.printRun}` : ''), price: v, currency: 'USD', source: 'card database' };
    await updateHistory(it.id, patch);
    setLast({ ...it, ...patch });
    setSession((s) => s.map((x) => (x.id === it.id ? { ...x, price: v || 0 } : x)));
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
  async function addItem(it: ScanItem, list: 'collection' | 'wishlist' = 'collection', pick?: { grade: string; cond: string }) {
    if (app.needsCode) return setError('Set a vault code (6+ characters) in Settings first.');
    const rec = recordFromScan(it, list);
    if (!rec) return setError('This card wasn’t identified yet. Tap Grade to fill in its details, then add it.');
    if (pick && list === 'collection') {
      // grade and condition picked under the result are saved on the record
      const graded = pick.grade && pick.grade !== 'RAW' ? pick.grade : '';
      rec.grade = { ...(rec.grade || {}), method: rec.grade?.method || 'owner', ...(graded ? { label: graded } : {}), condition: pick.cond };
      const c = it.catalog_key ? getCard(it.catalog_key) : null;
      if (c && graded === 'PSA 10' && c.psa10) rec.pricing.raw.mid = c.psa10;
      if (c && graded === 'PSA 9' && c.psa9) rec.pricing.raw.mid = c.psa9;
    }
    try {
      await app.addRecord(rec, list);
      if (it.catalog_key && it.phash) store.addCorrection(it.phash, it.catalog_key).catch(() => {});
      const patch = list === 'wishlist' ? { wish: true } : { added: true };
      await updateHistory(it.id, patch);
      if (last?.id === it.id) setLast({ ...it, ...patch });
      if (list === 'collection') setAddedN((m) => ({ ...m, [it.id]: (m[it.id] || 0) + 1 }));
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
        <View style={[S.screen, { padding: L.gutter, paddingTop: L.top + L.sp(8), gap: L.sp(14) }]}>
          {onBack ? <RoundBtn icon="back" onPress={onBack} label="Back" /> : null}
          <View style={{ flex: 1, justifyContent: 'center', gap: L.sp(14) }}>
            <View style={{ alignSelf: 'center', width: L.sp(84), height: L.sp(84), borderRadius: L.sp(24), borderWidth: 2, borderColor: C.lime, alignItems: 'center', justifyContent: 'center' }}>
              <Icon name="camera" size={L.fs(38)} color={C.lime} />
            </View>
            <Text style={[S.h2, { textAlign: 'center', fontSize: L.fs(22) }]}>Camera access</Text>
            <Text style={[S.body, { textAlign: 'center' }]}>Slab Scout needs the camera to photograph your cards.</Text>
            <Btn primary label="Allow camera" onPress={requestPerm} />
            <Btn label="Choose from photos instead" onPress={pick} />
          </View>
        </View>
      );
    if (showHistory) return <HistoryView items={history} onClose={() => setShowHistory(false)} onAdd={addItem} onGrade={gradeItem} error={error} />;
    const fr = L.scan.frame;
    const dim = 'rgba(5,6,10,0.45)';
    const shade = (
      <>
        <View pointerEvents="none" style={{ position: 'absolute', left: 0, right: 0, top: 0, height: fr.y, backgroundColor: dim }} />
        <View pointerEvents="none" style={{ position: 'absolute', left: 0, right: 0, top: fr.y + fr.h, bottom: 0, backgroundColor: dim }} />
        <View pointerEvents="none" style={{ position: 'absolute', left: 0, width: fr.x, top: fr.y, height: fr.h, backgroundColor: dim }} />
        <View pointerEvents="none" style={{ position: 'absolute', left: fr.x + fr.w, right: 0, top: fr.y, height: fr.h, backgroundColor: dim }} />
      </>
    );
    const frame = (label: string) => (
      <View pointerEvents="none" onLayout={(e) => setGuideBox(e.nativeEvent.layout)}
        style={{ position: 'absolute', left: fr.x, top: fr.y, width: fr.w, height: fr.h, borderRadius: L.sp(18), borderWidth: 3, borderColor: C.lime, alignItems: 'center', justifyContent: 'flex-end', paddingBottom: L.sp(14) }}>
        {label ? (
          <View style={[S.row, { gap: 6, backgroundColor: 'rgba(10,11,16,0.72)', borderRadius: 999, paddingHorizontal: L.sp(12), paddingVertical: L.sp(6) }]}>
            {scanning || busy ? <ActivityIndicator size="small" color={C.lime} /> : null}
            <Text style={{ color: '#fff', fontWeight: '700', fontSize: L.fs(13) }}>{label}</Text>
          </View>
        ) : null}
      </View>
    );
    if (mode === 'live') {
      const total = session.reduce((a, x) => a + x.price, 0);
      const cat = last?.catalog_key ? getCard(last.catalog_key) : null;
      const finishes = cat ? [cat, ...siblings(cat).filter((x) => x.key !== cat.key)] : [];
      const setName = (last?.set || last?.game || '').toUpperCase();
      return (
        <View style={S.screen} onLayout={(e) => setCamBox(e.nativeEvent.layout)}>
          <CameraView ref={cam} style={StyleSheet.absoluteFill} facing="back" zoom={ZOOMS[zoomIdx][1]} />
          {shade}
          <Pressable style={StyleSheet.absoluteFill} onPress={() => tapScan()} accessibilityLabel="Tap to scan the card" />
          {frame(scanning ? 'Scanning…' : auto ? 'Looking for card…' : 'Tap to scan')}

          {/* top: back + control pill */}
          <View pointerEvents="box-none" style={{ position: 'absolute', left: Math.max(L.gutter, (L.width - 640) / 2), right: Math.max(L.gutter, (L.width - 640) / 2), top: L.top + L.sp(6), gap: L.sp(8) }}>
            <View style={[S.row, { gap: L.sp(8) }]}>
              {onBack ? <RoundBtn icon="back" onPress={onBack} label="Back" /> : null}
              <View style={[S.row, { flex: 1, height: L.sp(40), borderRadius: 999, backgroundColor: 'rgba(16,18,28,0.78)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)', paddingHorizontal: 4, gap: 0 }]}>
                <BarSeg flex={1.5} onPress={() => setGameSheet(true)} label={`${game === 'Auto' ? 'Any Card' : game} ▾`} />
                <BarDiv />
                <BarSeg onPress={() => setZoomIdx((z) => (z + 1) % ZOOMS.length)} label={ZOOMS[zoomIdx][0]} on={zoomIdx > 0} />
                <BarDiv />
                <BarSeg flex={1.2} onPress={() => setSlabMode((g) => !g)} label={slabMode ? 'Graded' : 'Raw'} on={slabMode} />
                <BarDiv />
                <BarSeg flex={1.2} onPress={() => setAuto((a) => !a)} label="↻ Auto" on={auto} />
              </View>
            </View>
            <View pointerEvents="box-none" style={[S.row, { justifyContent: 'flex-end', gap: 8 }]}>
              <SmallPill label="Photos" icon="photo" onPress={pickLive} />
              <SmallPill label="Grade front + back" onPress={() => { setMode('grade'); setSide('front'); }} />
            </View>
            {slabMode ? <Text style={{ color: '#fff', fontSize: L.fs(12), textAlign: 'center', textShadowColor: '#000', textShadowRadius: 4 }}>Graded: fit the whole slab, label at the top, then pick the grade on the result.</Text> : null}
          </View>

          {/* bottom: last result + session footer */}
          <View pointerEvents="box-none" style={{ position: 'absolute', left: Math.max(0, (L.width - 640) / 2), right: Math.max(0, (L.width - 640) / 2), bottom: 0, paddingHorizontal: L.gutter, paddingBottom: L.bottom + L.sp(10), gap: L.sp(8) }}>
            {error ? (
              <Pressable onPress={() => setError('')} style={{ backgroundColor: 'rgba(42,36,18,0.95)', borderRadius: L.sp(14), padding: L.sp(10) }}>
                <Text style={{ color: C.warn, fontSize: L.fs(13) }}>{error}</Text>
              </Pressable>
            ) : null}
            <View style={{ backgroundColor: 'rgba(17,19,28,0.96)', borderRadius: L.sp(20), borderWidth: 1.5, borderColor: C.lime, padding: L.sp(12), gap: L.sp(10) }}>
              {last ? (
                <>
                  <View style={[S.row, { gap: L.sp(12) }]}>
                    {last.thumb ? <Image source={{ uri: `data:image/jpeg;base64,${last.thumb}` }} style={{ width: L.sp(48), height: L.sp(67), borderRadius: 6 }} /> : <View style={{ width: L.sp(48), height: L.sp(67), borderRadius: 6, backgroundColor: C.surface2 }} />}
                    <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                      <Text style={{ color: C.ink2, fontSize: L.fs(10.5), fontWeight: '800', letterSpacing: 1 }} numberOfLines={1}>{setName ? `${setName} • EN` : last.note ? 'NOT IDENTIFIED' : 'UNKNOWN CARD'}</Text>
                      <Text style={{ color: C.ink, fontWeight: '900', fontSize: L.fs(16) }} numberOfLines={1}>{last.name || 'No match'}{last.number ? <Text style={{ color: C.ink2 }}> #{last.number}</Text> : null}</Text>
                      {last.name ? (
                        <Text style={{ color: C.ink2, fontSize: L.fs(12) }} numberOfLines={1}>
                          <Text style={{ color: C.lime, fontWeight: '900', fontSize: L.fs(16), fontVariant: ['tabular-nums'] }}>{priceText(last)}</Text>  Est. Value
                        </Text>
                      ) : (
                        <Text style={{ color: C.warn, fontSize: L.fs(12) }} numberOfLines={2}>{last.note || 'Try again, closer and flatter, or tap Grade to type it in.'}</Text>
                      )}
                    </View>
                    <Pressable disabled={!last.name} onPress={() => addItem(last, 'collection', choice)} accessibilityLabel="Add to collection"
                      style={({ pressed }) => [{ width: L.sp(58), height: L.sp(58), borderRadius: L.sp(16), alignItems: 'center', justifyContent: 'center', gap: 1, backgroundColor: addedN[last.id] ? C.good : C.lime, opacity: last.name ? 1 : 0.4 }, pressed && { opacity: 0.75 }]}>
                      <Icon name={addedN[last.id] ? 'check' : 'cards'} size={L.fs(22)} color={C.accentInk} stroke={2.2} />
                      <Text style={{ color: C.accentInk, fontWeight: '900', fontSize: L.fs(9.5) }}>{addedN[last.id] ? `ADDED ${addedN[last.id]}` : 'ADD'}</Text>
                    </Pressable>
                  </View>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }} keyboardShouldPersistTaps="handled">
                    <DropChip label={cat ? cat.variant || 'Normal' : 'Normal'} onPress={() => setChipSheet('finish')} disabled={finishes.length < 2} />
                    <DropChip label={choice.grade || 'Pick grade'} onPress={() => setChipSheet('grade')} hot={!choice.grade} />
                    <DropChip label={choice.cond} onPress={() => setChipSheet('cond')} />
                    <DropChip label={last.wish ? '♡ Saved' : '♡ Wishlist'} onPress={() => addItem(last, 'wishlist')} disabled={last.wish || !last.name} arrow={false} />
                    <DropChip label="Grade ›" onPress={() => gradeItem(last)} arrow={false} />
                    {cat ? <DropChip label="Card page ›" onPress={() => app.openCard(cat.key)} arrow={false} /> : null}
                  </ScrollView>
                </>
              ) : (
                <View style={[S.row, { gap: L.sp(12), minHeight: L.sp(67) }]}>
                  {scanning ? <ActivityIndicator color={C.lime} /> : <Icon name="cards" size={L.fs(26)} color={C.lime} />}
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={{ color: C.ink, fontWeight: '800', fontSize: L.fs(15) }}>{scanning ? 'Identifying…' : auto ? 'Hold a card in the frame' : 'Tap the frame to scan'}</Text>
                    <Text style={{ color: C.ink2, fontSize: L.fs(12) }}>Best: card flat on a plain dark surface, filling the frame. Tilted cards get straightened.</Text>
                  </View>
                </View>
              )}
            </View>
            <Pressable onPress={() => setShowHistory(true)} style={({ pressed }) => [S.row, { backgroundColor: C.blue, borderRadius: 999, paddingVertical: L.sp(11), paddingHorizontal: L.sp(16), gap: L.sp(10) }, pressed && { opacity: 0.85 }]}>
              <Text style={{ color: '#fff', fontWeight: '800', fontSize: L.fs(14) }}>{session.length} scan{session.length === 1 ? '' : 's'}</Text>
              <Text style={{ color: C.lime, fontWeight: '900', fontSize: L.fs(14), fontVariant: ['tabular-nums'] }}>{money(total)}</Text>
              <View style={{ flex: 1 }} />
              <Text style={{ color: '#fff', fontWeight: '800', fontSize: L.fs(13) }}>See all scans</Text>
              <Icon name="up" size={L.fs(12)} color="#fff" />
            </Pressable>
          </View>

          <Sheet visible={gameSheet} onClose={() => setGameSheet(false)} title="What are you scanning?">
            {GAMES.map((g) => <SheetOption key={g} label={g === 'Auto' ? 'Any Card' : g} sub={g === 'Auto' ? 'Detect the game automatically' : undefined} on={game === g} onPress={() => { setGame(g); setGameSheet(false); }} />)}
          </Sheet>
          <Sheet visible={!!chipSheet} onClose={() => setChipSheet(null)} title={chipSheet === 'finish' ? 'Finish / parallel' : chipSheet === 'grade' ? 'Grade' : 'Condition'}>
            {chipSheet === 'finish' && last
              ? finishes.map((c) => {
                  const [v] = catValue(c);
                  return <SheetOption key={c.key} label={`${c.variant || 'Normal'}${c.printRun ? ` ${printRunLabel(c.printRun)}` : ''}`} sub={v ? money(v) : undefined} on={c.key === last.catalog_key} onPress={() => { pickFinish(last, c); setChipSheet(null); }} />;
                })
              : null}
            {chipSheet === 'grade' ? SCAN_GRADES.map((g) => <SheetOption key={g} label={g} on={choice.grade === g} onPress={() => { setChoice((c) => ({ ...c, grade: g })); setChipSheet(null); }} />) : null}
            {chipSheet === 'cond' ? SCAN_CONDS.map((g) => <SheetOption key={g} label={g} sub={{ NM: 'Near mint', LP: 'Lightly played', MP: 'Moderately played', HP: 'Heavily played', DMG: 'Damaged' }[g]} on={choice.cond === g} onPress={() => { setChoice((c) => ({ ...c, cond: g })); setChipSheet(null); }} />) : null}
          </Sheet>
        </View>
      );
    }
    return (
      <View style={S.screen} onLayout={(e) => setCamBox(e.nativeEvent.layout)}>
        <CameraView ref={cam} style={StyleSheet.absoluteFill} facing="back" />
        {shade}
        {frame(bulk ? `BULK SCAN${tally.n ? ` · ${tally.n} added · ${money(tally.value)}` : ''}` : side === 'front' ? 'Front · step 1 of 2' : 'Back · step 2 of 2')}
        <View pointerEvents="box-none" style={{ position: 'absolute', left: L.gutter, right: L.gutter, top: L.top + L.sp(6), gap: L.sp(8) }}>
          <View style={[S.row, { gap: L.sp(8) }]}>
            <RoundBtn icon="back" onPress={() => setMode('live')} label="Back to the live scanner" />
            <View style={{ flex: 1, height: L.sp(40), borderRadius: 999, backgroundColor: 'rgba(16,18,28,0.78)', justifyContent: 'center', paddingHorizontal: L.sp(14) }}>
              <Text style={{ color: C.lime, fontWeight: '800', letterSpacing: 1, fontSize: L.fs(12) }} numberOfLines={1}>{side === 'front' ? 'GRADING · FRONT' : 'GRADING · BACK'}</Text>
            </View>
          </View>
          <Text style={{ color: '#fff', fontSize: L.fs(12.5), textAlign: 'center', textShadowColor: '#000', textShadowRadius: 4 }}>
            Card out of its sleeve, flat on a plain dark surface, edges lined up with the frame. A held or tilted card still works; it gets straightened.
          </Text>
        </View>
        <View style={[S.row, { position: 'absolute', left: 0, right: 0, bottom: 0, justifyContent: 'space-around', paddingTop: L.sp(16), paddingBottom: L.bottom + L.sp(20), backgroundColor: 'rgba(10,11,16,0.7)' }]}>
          <Pressable style={st.side} onPress={pick}>
            <Icon name="photo" size={L.fs(22)} color="#fff" />
            <Text style={st.sideText}>Photos</Text>
          </Pressable>
          <Pressable style={[st.shutter, { width: L.sp(76), height: L.sp(76), borderRadius: L.sp(38) }]} onPress={snap} disabled={busy} accessibilityLabel="Take photo">
            {busy ? <ActivityIndicator color={C.accentInk} /> : <View style={[st.shutterIn, { width: L.sp(60), height: L.sp(60), borderRadius: L.sp(30) }]} />}
          </Pressable>
          {side === 'back' ? (
            <Pressable style={st.side} onPress={() => setPhase('review')}>
              <Icon name="forward" size={L.fs(22)} color="#fff" />
              <Text style={st.sideText}>Skip back</Text>
            </Pressable>
          ) : (
            <View style={st.side} />
          )}
        </View>
      </View>
    );
  }

  /* ---------- render: review / working / result ---------- */
  const setF = (k: keyof CardFields) => (v: string) => setFields((f) => ({ ...f, [k]: v }));
  return (
    <ScrollView style={S.screen} contentContainerStyle={[S.pad, { paddingHorizontal: L.gutter, paddingTop: L.top + L.sp(6), paddingBottom: 50, width: '100%', maxWidth: L.tablet ? 720 : undefined, alignSelf: 'center' }]} keyboardShouldPersistTaps="handled">
      <View style={[S.row, { gap: L.sp(10) }]}>
        <RoundBtn icon="back" label="Back to the scanner" onPress={() => { abort.current?.abort(); reset(); setMode('live'); }} />
        <Text style={{ flex: 1, color: C.ink, fontWeight: '900', fontSize: L.fs(22) }} numberOfLines={1}>{phase === 'result' ? 'Scan result' : phase === 'working' ? 'Scanning…' : 'Check your photos'}</Text>
      </View>
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

function RoundBtn({ icon, onPress, label }: { icon: 'back' | 'close'; onPress: () => void; label: string }) {
  const L = useLayout();
  const d = L.sp(40);
  return (
    <Pressable onPress={onPress} hitSlop={8} accessibilityLabel={label} style={({ pressed }) => [{ width: d, height: d, borderRadius: d / 2, backgroundColor: 'rgba(16,18,28,0.78)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' }, pressed && { opacity: 0.7 }]}>
      <Icon name={icon} size={L.fs(18)} color="#fff" />
    </Pressable>
  );
}

/** One control inside the scanner's top pill bar. */
function BarSeg({ label, onPress, on, flex = 1 }: { label: string; onPress: () => void; on?: boolean; flex?: number }) {
  const L = useLayout();
  return (
    <Pressable onPress={onPress} hitSlop={4} style={{ flex, height: '100%', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 2 }}>
      <Text style={{ color: on ? C.lime : '#fff', fontWeight: '800', fontSize: L.fs(12.5) }} numberOfLines={1}>{label}</Text>
    </Pressable>
  );
}
const BarDiv = () => <View style={{ width: 1, height: '50%', backgroundColor: 'rgba(255,255,255,0.16)' }} />;

function SmallPill({ label, onPress, icon }: { label: string; onPress: () => void; icon?: 'photo' }) {
  const L = useLayout();
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [S.row, { gap: 5, backgroundColor: 'rgba(16,18,28,0.72)', borderRadius: 999, paddingHorizontal: L.sp(11), paddingVertical: L.sp(6) }, pressed && { opacity: 0.7 }]}>
      {icon ? <Icon name={icon} size={L.fs(13)} color="#fff" /> : null}
      <Text style={{ color: '#fff', fontWeight: '700', fontSize: L.fs(12) }}>{label}</Text>
    </Pressable>
  );
}

/** Dropdown chip under a scan result (finish / grade / condition). */
function DropChip({ label, onPress, disabled, hot, arrow = true }: { label: string; onPress: () => void; disabled?: boolean; hot?: boolean; arrow?: boolean }) {
  const L = useLayout();
  return (
    <Pressable onPress={onPress} disabled={disabled} style={[S.row, { gap: 4, backgroundColor: hot ? C.blue : C.surface2, borderRadius: 999, paddingHorizontal: L.sp(11), paddingVertical: L.sp(6), opacity: disabled ? 0.5 : 1 }]}>
      <Text style={{ color: '#fff', fontWeight: '800', fontSize: L.fs(12) }} numberOfLines={1}>{label}</Text>
      {arrow && !disabled ? <Icon name="down" size={L.fs(10)} color={C.ink2} /> : null}
    </Pressable>
  );
}

function HistoryView({ items, onClose, onAdd, onGrade, error }: { items: ScanItem[]; onClose: () => void; onAdd: (it: ScanItem) => void; onGrade: (it: ScanItem) => void; error: string }) {
  const L = useLayout();
  const [filter, setFilter] = useState<'all' | 'not added'>('not added');
  const list = filter === 'all' ? items : items.filter((x) => !x.added);
  const total = list.reduce((a, x) => a + (x.price || 0), 0);
  return (
    <ScrollView style={S.screen} contentContainerStyle={[S.pad, { paddingHorizontal: L.gutter, paddingTop: L.top + L.sp(6), paddingBottom: 60, gap: 10, width: '100%', maxWidth: L.tablet ? 720 : undefined, alignSelf: 'center' }]}>
      <View style={[S.row, { gap: L.sp(10) }]}>
        <RoundBtn icon="back" label="Back to camera" onPress={onClose} />
        <Text style={{ flex: 1, color: C.ink, fontWeight: '900', fontSize: L.fs(24) }}>All scans</Text>
      </View>
      <View style={[S.row, { gap: 8 }]}>
        {(['not added', 'all'] as const).map((f) => (
          <Pressable key={f} onPress={() => setFilter(f)} style={[S.pill, { paddingVertical: L.sp(7), paddingHorizontal: L.sp(13) }, filter === f && S.pillOn]}>
            <Text style={{ color: filter === f ? '#fff' : C.ink2, fontWeight: '700', fontSize: L.fs(13) }}>{f === 'all' ? `All (${items.length})` : `Not in collection (${items.filter((x) => !x.added).length})`}</Text>
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
  side: { width: 84, alignItems: 'center', gap: 4 },
  sideText: { color: '#fff', fontWeight: '700' },
  thumbBox: { flex: 1, aspectRatio: 63 / 88, backgroundColor: C.surface, borderRadius: 12, borderWidth: 1, borderColor: C.line, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  retake: { position: 'absolute', bottom: 8, backgroundColor: 'rgba(0,0,0,.7)', color: '#fff', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999, fontSize: 12, overflow: 'hidden' },
  candRow: { flexDirection: 'row', gap: 10, alignItems: 'center', backgroundColor: C.surface2, borderRadius: 10, padding: 8, borderWidth: 1, borderColor: 'transparent' },
  cl: { position: 'absolute', top: 0, bottom: 0, width: 2, backgroundColor: C.accent },
  ch: { position: 'absolute', left: 0, right: 0, height: 2, backgroundColor: C.accent },
  vbox: { flex: 1, backgroundColor: C.surface2, borderRadius: 12, padding: 12, gap: 2 },
  big: { color: C.ink, fontSize: 24, fontWeight: '800', fontVariant: ['tabular-nums'] },
});
