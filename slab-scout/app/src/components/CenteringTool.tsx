/**
 * Live centering tool: drag the card-edge (blue, dashed) and inner-border (orange) lines on the photo,
 * or tap the four corners, and the left/right and top/bottom split and PSA cap update as you move.
 * Coordinates are in the 630x880 card image.
 */
import React, { useMemo, useRef, useState } from 'react';
import { LayoutChangeEvent, PanResponder, Pressable, StyleSheet, Text, View, Image } from 'react-native';
import { C, S } from '../theme';
import { CARD_H, CARD_W, Centering } from '../core/imageTools';

type Lines = { ol: number; ot: number; or: number; ob: number; il: number; it: number; ir: number; ib: number };
type Key = keyof Lines;
const CAPS: [number, number][] = [[10, 55], [9, 60], [8, 65], [7, 70], [6, 80], [5, 85], [4, 85], [3, 90], [2, 95], [1, 100]];
const LABEL: Record<Key, string> = { ol: 'Card edge · left', or: 'Card edge · right', ot: 'Card edge · top', ob: 'Card edge · bottom', il: 'Border · left', ir: 'Border · right', it: 'Border · top', ib: 'Border · bottom' };
const TAP_STEPS = ["Tap the card's TOP-LEFT outer corner", "Tap the card's BOTTOM-RIGHT outer corner", 'Tap the TOP-LEFT corner of the inner border (where the art frame starts)', 'Tap the BOTTOM-RIGHT corner of the inner border'];

const fromCentering = (c: Centering): Lines => ({ ol: 0, ot: 0, or: CARD_W, ob: CARD_H, il: c.left, it: c.top, ir: CARD_W - c.right, ib: CARD_H - c.bottom });
export const toCentering = (v: Lines): Centering => ({
  left: Math.max(1, Math.round(v.il - v.ol)), right: Math.max(1, Math.round(v.or - v.ir)), top: Math.max(1, Math.round(v.it - v.ot)), bottom: Math.max(1, Math.round(v.ob - v.ib)),
});
const split = (a: number, b: number) => {
  const p = Math.round((a / Math.max(a + b, 0.0001)) * 100);
  return [p, 100 - p];
};
function clamp(v: Lines): Lines {
  const o = { ...v };
  o.ol = Math.max(0, Math.min(o.ol, o.il - 1));
  o.il = Math.min(o.il, o.ir - 10);
  o.or = Math.min(CARD_W, Math.max(o.or, o.ir + 1));
  o.ot = Math.max(0, Math.min(o.ot, o.it - 1));
  o.it = Math.min(o.it, o.ib - 10);
  o.ob = Math.min(CARD_H, Math.max(o.ob, o.ib + 1));
  return o;
}

export default function CenteringTool({ uri, auto, onChange }: { uri: string; auto: Centering; onChange: (c: Centering) => void }) {
  const autoLines = useMemo(() => fromCentering(auto), [auto]);
  const [v, setV] = useState<Lines>(autoLines);
  const [mode, setMode] = useState<'drag' | 'tap'>('drag');
  const [step, setStep] = useState(0);
  const [sel, setSel] = useState<Key | null>(null);
  const [box, setBox] = useState({ w: 1, h: 1 });
  const live = useRef({ v, mode, step, sel, box, dragging: null as Key | null, onChange });
  if (!live.current.dragging) live.current = { ...live.current, v, mode, step, sel, box, onChange };

  const commit = (nv: Lines) => {
    setV(nv);
    live.current.v = nv;
    live.current.onChange(toCentering(nv));
  };
  const toCard = (x: number, y: number) => [(x / live.current.box.w) * CARD_W, (y / live.current.box.h) * CARD_H];

  const pan = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: (e) => {
          const { locationX, locationY } = e.nativeEvent;
          const [cx, cy] = toCard(locationX, locationY);
          const cur = live.current.v;
          if (live.current.mode === 'tap') {
            const s = live.current.step;
            const nv = { ...cur };
            if (s === 0) Object.assign(nv, { ol: cx, ot: cy });
            if (s === 1) Object.assign(nv, { or: cx, ob: cy });
            if (s === 2) Object.assign(nv, { il: cx, it: cy });
            if (s === 3) Object.assign(nv, { ir: cx, ib: cy });
            const c = clamp(nv);
            if (s >= 3) {
              setStep(0);
              setMode('drag');
              commit(c);
            } else {
              setStep(s + 1);
              setV(c);
            }
            return;
          }
          // pick the nearest line within ~26 px on screen
          const tol = (26 / live.current.box.w) * CARD_W;
          let best: Key | null = null;
          let bestD = tol;
          (Object.keys(cur) as Key[]).forEach((k) => {
            const d = k === 'ol' || k === 'or' || k === 'il' || k === 'ir' ? Math.abs(cx - cur[k]) : Math.abs(cy - cur[k]);
            if (d < bestD) {
              bestD = d;
              best = k;
            }
          });
          live.current.dragging = best;
          setSel(best);
        },
        onPanResponderMove: (e) => {
          const k = live.current.dragging;
          if (!k) return;
          const [cx, cy] = toCard(e.nativeEvent.locationX, e.nativeEvent.locationY);
          const nv = { ...live.current.v, [k]: k === 'ol' || k === 'or' || k === 'il' || k === 'ir' ? Math.max(0, Math.min(CARD_W, cx)) : Math.max(0, Math.min(CARD_H, cy)) };
          const c = clamp(nv);
          live.current.v = c;
          setV(c); // live readout while dragging
        },
        onPanResponderRelease: () => {
          if (live.current.dragging) commit(live.current.v);
          live.current.dragging = null;
        },
        onPanResponderTerminate: () => {
          live.current.dragging = null;
        },
      }),
    [],
  );

  const L = v.il - v.ol, R = v.or - v.ir, T = v.it - v.ot, B = v.ob - v.ib;
  const lr = split(L, R), tb = split(T, B);
  const worst = Math.max(...lr, ...tb);
  const cap = (CAPS.find(([, m]) => worst <= m) || [1])[0];
  const capColor = cap >= 9 ? C.good : cap >= 7 ? C.warn : C.crit;
  const sx = (x: number) => (x / CARD_W) * box.w;
  const sy = (y: number) => (y / CARD_H) * box.h;
  const line = (k: Key) => {
    const vertical = k === 'ol' || k === 'or' || k === 'il' || k === 'ir';
    const outer = k[0] === 'o';
    const color = sel === k ? '#FFFFFF' : outer ? '#4FA8FF' : C.accent;
    const th = sel === k ? 3 : 2;
    return (
      <View
        key={k}
        pointerEvents="none"
        style={[
          { position: 'absolute', backgroundColor: color, opacity: outer ? 0.85 : 1 },
          vertical ? { left: sx(v[k]) - th / 2, top: 0, bottom: 0, width: th } : { top: sy(v[k]) - th / 2, left: 0, right: 0, height: th },
          outer ? { borderStyle: 'dashed' } : null,
        ]}
      />
    );
  };
  const nudge = (d: number) => {
    if (!sel) return;
    commit(clamp({ ...v, [sel]: v[sel] + d }));
  };

  return (
    <View style={{ gap: 8 }}>
      <View style={S.row}>
        {(['drag', 'tap'] as const).map((m) => (
          <Pressable key={m} onPress={() => { setMode(m); setStep(0); }} style={[S.chip, { paddingVertical: 7, paddingHorizontal: 12 }, mode === m && { backgroundColor: C.accent }]}>
            <Text style={[S.chipText, mode === m && { color: C.accentInk }]}>{m === 'drag' ? 'Drag lines' : 'Tap corners'}</Text>
          </Pressable>
        ))}
        <Pressable onPress={() => { setSel(null); setStep(0); commit(autoLines); }} style={[S.chip, { paddingVertical: 7, paddingHorizontal: 12, marginLeft: 'auto' }]}>
          <Text style={S.chipText}>Reset</Text>
        </Pressable>
      </View>
      <Text style={[S.muted, { minHeight: 36 }]}>
        {mode === 'tap' ? `Step ${step + 1} of 4: ${TAP_STEPS[step]}` : 'Drag the orange lines onto the inner border and the blue lines onto the card edge. The numbers update as you drag.'}
      </Text>
      <View style={{ alignSelf: 'center', width: '88%', aspectRatio: CARD_W / CARD_H }} onLayout={(e: LayoutChangeEvent) => setBox({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })} {...pan.panHandlers}>
        <Image source={{ uri }} style={StyleSheet.absoluteFill} />
        {(Object.keys(v) as Key[]).map(line)}
      </View>
      <View style={[S.row, { justifyContent: 'center' }]}>
        <Text style={[S.muted, { marginRight: 4 }]}>{sel ? LABEL[sel] : 'Tap a line to select it'}</Text>
        {[-5, -1, 1, 5].map((d) => (
          <Pressable key={d} onPress={() => nudge(d)} disabled={!sel} style={[S.chip, { paddingHorizontal: 12, paddingVertical: 7, opacity: sel ? 1 : 0.4 }]}>
            <Text style={S.chipText}>{d === -5 ? '«' : d === -1 ? '‹' : d === 1 ? '›' : '»'}</Text>
          </Pressable>
        ))}
      </View>
      <View style={S.row}>
        {([[`${lr[0]}/${lr[1]}`, 'Left / right', C.ink], [`${tb[0]}/${tb[1]}`, 'Top / bottom', C.ink], [cap === 10 ? '10 ✓' : `max ${cap}`, 'PSA centering cap', capColor]] as [string, string, string][]).map(([big, lab, col]) => (
          <View key={lab} style={{ flex: 1, backgroundColor: C.surface2, borderRadius: 10, padding: 8 }}>
            <Text style={{ color: col, fontSize: 18, fontWeight: '800', fontVariant: ['tabular-nums'] }}>{big}</Text>
            <Text style={S.eyebrow}>{lab}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
