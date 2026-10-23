/**
 * In-camera guide for grading photos, the phone's version of a grader's imaging rig (TAG photographs each side from
 * a fixed height under 7-9 light angles; PSA adds a backlight). For every grading shot it shows:
 *  - where to hold the phone: a level for flat shots (phone parallel to the card) and a target angle for the tilted
 *    shots (phone tipped ~30 degrees from one side, so the light skims across the surface and shows scratches / dents),
 *    read live from the phone's motion sensor;
 *  - how high: the card must fill the frame outline (about 15-20 cm above it for most phones);
 *  - whether the light is good enough: the camera picture is sampled every ~1.5 s, too dark or too much glare is
 *    called out before the photo is taken.
 * The shutter stays usable (a person can always take the photo), but the guide turns green only when all is right.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { DeviceMotion } from 'expo-sensors';
import { C } from '../theme';

export type ShotAim = { kind: 'flat' } | { kind: 'tilt'; from: 'top' | 'bottom' | 'left' | 'right'; deg: number } | { kind: 'closeup' };

export type GuideState = { angleOk: boolean; light: 'ok' | 'dark' | 'glare' | 'unknown'; pitch: number; roll: number };

const FLAT_TOL = 4;   // degrees either way for a flat shot
const TILT_TOL = 8;   // degrees either way around the target for a tilted shot

/** Phone pitch (top edge down = +) and roll (right edge down = +) in degrees, from the motion sensor. */
function useTilt(active: boolean) {
  const [t, setT] = useState({ pitch: 0, roll: 0, ok: false });
  useEffect(() => {
    if (!active) return;
    let sub: { remove: () => void } | null = null;
    let alive = true;
    (async () => {
      try {
        if (!(await DeviceMotion.isAvailableAsync())) return;
        DeviceMotion.setUpdateInterval(120);
        sub = DeviceMotion.addListener((m) => {
          if (!alive || !m.rotation) return;
          // beta: rotation around the phone's x axis (front-back tilt), gamma: around y (left-right)
          const pitch = (m.rotation.beta * 180) / Math.PI;
          const roll = (m.rotation.gamma * 180) / Math.PI;
          setT({ pitch, roll, ok: true });
        });
      } catch {
        /* no sensor: the guide shows text only */
      }
    })();
    return () => {
      alive = false;
      sub?.remove();
    };
  }, [active]);
  return t;
}

/** Where the phone should be, as target pitch / roll. */
function target(aim: ShotAim): { pitch: number; roll: number } {
  if (aim.kind !== 'tilt') return { pitch: 0, roll: 0 };
  const d = aim.deg;
  return aim.from === 'top' ? { pitch: d, roll: 0 } : aim.from === 'bottom' ? { pitch: -d, roll: 0 } : aim.from === 'left' ? { pitch: 0, roll: -d } : { pitch: 0, roll: d };
}

export function aimText(aim: ShotAim): string {
  if (aim.kind === 'flat') return 'Hold the phone flat over the card, parallel to the table, about 15-20 cm up so the card fills the outline.';
  if (aim.kind === 'closeup') return 'Move in on the corner until it fills about a third of the screen. Hold still until it is sharp.';
  const side = { top: "card's top edge", bottom: "card's bottom edge", left: "card's left edge", right: "card's right edge" }[aim.from];
  return `Move the phone toward the ${side} and tip it about ${aim.deg}° so it looks back across the card, whole card still in the outline. Light from the opposite side skims the surface: scratches and dents show up.`;
}

export default function GraderGuide({ aim, light, onState }: { aim: ShotAim; light: GuideState['light']; onState?: (s: GuideState) => void }) {
  const tilt = useTilt(aim.kind !== 'closeup');
  const tg = target(aim);
  const dp = tilt.pitch - tg.pitch;
  const dr = tilt.roll - tg.roll;
  const tol = aim.kind === 'tilt' ? TILT_TOL : FLAT_TOL;
  const angleOk = aim.kind === 'closeup' || !tilt.ok || (Math.abs(dp) <= tol && Math.abs(dr) <= tol);
  const last = useRef('');
  useEffect(() => {
    const k = `${angleOk}|${light}|${Math.round(tilt.pitch)}|${Math.round(tilt.roll)}`;
    if (k !== last.current) {
      last.current = k;
      onState?.({ angleOk, light, pitch: tilt.pitch, roll: tilt.roll });
    }
  });
  const good = angleOk && light !== 'dark' && light !== 'glare';
  const R = 46;
  // bubble: offset from the target, clamped to the ring
  const k = R / 25;
  let bx = dr * k;
  let by = -dp * k;
  const mag = Math.hypot(bx, by);
  if (mag > R) {
    bx *= R / mag;
    by *= R / mag;
  }
  const hint = !tilt.ok || aim.kind === 'closeup' ? '' : Math.abs(dp) > tol ? (dp > 0 ? 'tip the top edge up' : 'tip the top edge down') : Math.abs(dr) > tol ? (dr > 0 ? 'tip the right side up' : 'tip the right side down') : '';
  return (
    <View pointerEvents="none" style={{ alignItems: 'center', gap: 6 }}>
      {aim.kind !== 'closeup' && tilt.ok ? (
        <View style={{ width: 2 * R + 12, height: 2 * R + 12, borderRadius: R + 6, borderWidth: 2, borderColor: angleOk ? C.lime : 'rgba(255,255,255,0.6)', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(10,11,16,0.45)' }}>
          <View style={{ position: 'absolute', width: 14, height: 14, borderRadius: 7, borderWidth: 2, borderColor: angleOk ? C.lime : '#fff' }} />
          <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: angleOk ? C.lime : '#FFB020', transform: [{ translateX: bx }, { translateY: by }] }} />
          <Text style={{ position: 'absolute', bottom: 6, color: '#fff', fontSize: 10, fontWeight: '800' }}>
            {aim.kind === 'tilt' ? `${Math.round(Math.hypot(tilt.pitch, tilt.roll))}° / ${aim.deg}°` : `${Math.round(Math.hypot(tilt.pitch, tilt.roll))}°`}
          </Text>
        </View>
      ) : null}
      <View style={{ backgroundColor: good ? 'rgba(80,170,60,0.9)' : 'rgba(200,120,20,0.92)', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 5 }}>
        <Text style={{ color: '#fff', fontWeight: '800', fontSize: 12 }}>
          {light === 'dark' ? 'Too dark to grade: add light (a lamp or a window, no flash)'
            : light === 'glare' ? 'Glare on the card: move the light to the side or tilt the card slightly'
            : !angleOk ? `Angle: ${hint || 'adjust'}`
            : good ? 'Good: hold still and take the photo' : 'Checking light…'}
        </Text>
      </View>
    </View>
  );
}

/** Light level from a tiny sample of the camera picture: mean brightness and share of clipped (glare) pixels. */
export function lightFrom(data: Uint8Array): GuideState['light'] {
  let sum = 0;
  let clipped = 0;
  const n = data.length / 3;
  for (let i = 0; i < data.length; i += 3) {
    const l = 0.3 * data[i] + 0.59 * data[i + 1] + 0.11 * data[i + 2];
    sum += l;
    if (l > 248) clipped++;
  }
  const mean = sum / Math.max(1, n);
  if (mean < 55) return 'dark';
  if (clipped / Math.max(1, n) > 0.06) return 'glare';
  return 'ok';
}
