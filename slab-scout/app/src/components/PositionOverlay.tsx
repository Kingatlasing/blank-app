/**
 * See-through outline of where the card should sit in the camera for each grading photo, so the person can line the
 * real card up with it:
 *  - flat shots: the card's outline filling the frame, straight on;
 *  - angled shots: the card as it looks from ~30 degrees off one side (the near edge wide, the far edge narrow), with
 *    the lamp drawn beyond the far edge;
 *  - corner close-ups: that one corner, large, with a little table beyond it and some of the card inside it.
 * Purely visual (no touches) and can be switched off.
 */
import React from 'react';
import { Text, View } from 'react-native';
import type { ShotAim } from './GraderGuide';

const LINE = 'rgba(200,255,120,0.95)';
const FILL = 'rgba(200,255,120,0.10)';

export default function PositionOverlay({ aim, corner, width, height }: { aim: ShotAim; corner?: 'TL' | 'TR' | 'BL' | 'BR'; width: number; height: number }) {
  if (!width || !height) return null;
  // card proportions inside the frame (63 x 88 mm)
  const cw = Math.min(width * 0.92, height * 0.92 * (63 / 88));
  const ch = cw * (88 / 63);
  const radius = cw * (3.2 / 63); // a standard card's ~3 mm corner rounding

  if (aim.kind === 'closeup' && corner) {
    // the corner fills about a third of the screen: draw a big rounded corner whose tip sits off-centre toward
    // the corner's own direction, with "table" beyond it
    const big = Math.min(width, height) * 1.25;
    const r = big * (3.2 / 63);
    const left = corner.endsWith('L') ? width * 0.28 : width * 0.72 - big;
    const top = corner.startsWith('T') ? height * 0.3 : height * 0.7 - big;
    return (
      <View pointerEvents="none" style={{ position: 'absolute', left: 0, top: 0, width, height, overflow: 'hidden' }}>
        <View style={{ position: 'absolute', left, top, width: big, height: big, borderRadius: r, borderWidth: 3, borderColor: LINE, backgroundColor: FILL, borderStyle: 'dashed' }} />
        <Label text="Put the card's corner here, with some table beyond it" bottom />
      </View>
    );
  }

  if (aim.kind === 'tilt') {
    const vertical = aim.from === 'top' || aim.from === 'bottom';
    // perspective: the edge nearest the phone looks wider than the far one
    const rot = vertical ? { rotateX: `${aim.from === 'bottom' ? 30 : -30}deg` } : { rotateY: `${aim.from === 'right' ? 30 : -30}deg` };
    const lamp = { top: { bottom: 6, alignSelf: 'center' as const }, bottom: { top: 6, alignSelf: 'center' as const }, left: { right: 6, top: height / 2 - 14 }, right: { left: 6, top: height / 2 - 14 } }[aim.from];
    return (
      <View pointerEvents="none" style={{ position: 'absolute', left: 0, top: 0, width, height, alignItems: 'center', justifyContent: 'center' }}>
        <View style={{ width: cw * 0.86, height: ch * 0.86, borderRadius: radius, borderWidth: 3, borderColor: LINE, backgroundColor: FILL,
          transform: [{ perspective: 600 }, rot] }} />
        <Text style={{ position: 'absolute', fontSize: 22, ...lamp }}>💡</Text>
        <Label text={`Phone at the ${aim.from} edge, tipped ~${aim.deg}°: the near edge looks wider`} />
      </View>
    );
  }

  // flat: the card straight on, filling the frame
  return (
    <View pointerEvents="none" style={{ position: 'absolute', left: 0, top: 0, width, height, alignItems: 'center', justifyContent: 'center' }}>
      <View style={{ width: cw, height: ch, borderRadius: radius, borderWidth: 3, borderColor: LINE, backgroundColor: FILL, borderStyle: 'dashed' }} />
      <View style={{ position: 'absolute', width: 18, height: 2, backgroundColor: LINE }} />
      <View style={{ position: 'absolute', width: 2, height: 18, backgroundColor: LINE }} />
      <Label text="Line the card's edges up with the outline" />
    </View>
  );
}

function Label({ text, bottom }: { text: string; bottom?: boolean }) {
  return (
    <View style={{ position: 'absolute', [bottom ? 'bottom' : 'top']: 8, alignSelf: 'center', backgroundColor: 'rgba(10,11,16,0.72)', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}>
      <Text style={{ color: '#fff', fontSize: 11, fontWeight: '700' }}>{text}</Text>
    </View>
  );
}
