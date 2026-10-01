/** Drawing helpers with no extra native packages: gradients made of thin colour slices,
 * icons made of Views, and a smooth area chart made of columns + line segments. */
import React, { useMemo, useState } from 'react';
import { StyleProp, StyleSheet, Text, View, ViewStyle } from 'react-native';
import { C } from '../theme';

/* ---------- colour ---------- */
type RGBA = [number, number, number, number];
function parse(c: string): RGBA {
  if (c.startsWith('#')) {
    const h = c.length === 4 ? c.slice(1).split('').map((x) => x + x).join('') : c.slice(1);
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), h.length >= 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1];
  }
  const m = c.match(/[\d.]+/g) || ['0', '0', '0', '1'];
  return [+m[0], +m[1], +m[2], m[3] != null ? +m[3] : 1];
}
export function mix(colors: string[], t: number): string {
  if (colors.length === 1) return colors[0];
  const pos = Math.min(0.9999, Math.max(0, t)) * (colors.length - 1);
  const i = Math.floor(pos);
  const f = pos - i;
  const a = parse(colors[i]);
  const b = parse(colors[i + 1]);
  const v = a.map((x, k) => x + (b[k] - x) * f);
  return `rgba(${Math.round(v[0])},${Math.round(v[1])},${Math.round(v[2])},${v[3].toFixed(3)})`;
}
export const alpha = (c: string, a: number) => {
  const [r, g, b] = parse(c);
  return `rgba(${r},${g},${b},${a})`;
};

/** Fake linear gradient: `steps` slices across (horizontal) or down (vertical). Put it first inside a view with overflow hidden. */
export function Gradient({ colors, vertical, steps = 24, style }: { colors: string[]; vertical?: boolean; steps?: number; style?: StyleProp<ViewStyle> }) {
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, { flexDirection: vertical ? 'column' : 'row' }, style]}>
      {Array.from({ length: steps }).map((_, i) => (
        <View key={i} style={{ flex: 1, backgroundColor: mix(colors, (i + 0.5) / steps), marginRight: vertical ? 0 : -0.5, marginBottom: vertical ? -0.5 : 0 }} />
      ))}
    </View>
  );
}

/** A soft glow blob (a few stacked translucent circles). */
export function Glow({ color, size, style }: { color: string; size: number; style?: StyleProp<ViewStyle> }) {
  return (
    <View pointerEvents="none" style={[{ position: 'absolute', width: size, height: size, alignItems: 'center', justifyContent: 'center' }, style]}>
      {[1, 0.75, 0.5].map((k) => (
        <View key={k} style={{ position: 'absolute', width: size * k, height: size * k, borderRadius: size, backgroundColor: alpha(color, 0.12) }} />
      ))}
    </View>
  );
}

/** Rounded box with a multicolour gradient outline (blue -> purple -> orange). */
export function GradientBorder({ children, radius = 16, width = 1.5, colors = [C.blue, C.purple, C.orange], style, innerStyle }: { children: React.ReactNode; radius?: number; width?: number; colors?: string[]; style?: StyleProp<ViewStyle>; innerStyle?: StyleProp<ViewStyle> }) {
  return (
    <View style={[{ borderRadius: radius, overflow: 'hidden', padding: width }, style]}>
      <Gradient colors={colors} steps={28} />
      <View style={[{ borderRadius: radius - width, backgroundColor: C.bg }, innerStyle]}>{children}</View>
    </View>
  );
}

/* ---------- icons (drawn with Views) ---------- */
export type IconName =
  | 'discover' | 'collection' | 'feed' | 'explore' | 'search' | 'gear' | 'plus' | 'check' | 'close'
  | 'back' | 'forward' | 'down' | 'up' | 'share' | 'edit' | 'grid' | 'photo' | 'bolt' | 'heart'
  | 'cards' | 'sort' | 'filter' | 'more' | 'refresh' | 'binder' | 'lock' | 'list';

export function Icon({ name, size = 22, color = C.ink, stroke }: { name: IconName; size?: number; color?: string; stroke?: number }) {
  const s = size;
  const w = stroke ?? Math.max(1.6, s * 0.09);
  const box: ViewStyle = { width: s, height: s, alignItems: 'center', justifyContent: 'center' };
  const abs = (st: ViewStyle): ViewStyle => ({ position: 'absolute', ...st });
  const bar = (len: number, rot: number, extra: ViewStyle = {}): ViewStyle => abs({ width: len, height: w, borderRadius: w, backgroundColor: color, transform: [{ rotate: `${rot}deg` }], ...extra });
  const chev = (rot: number, k = 0.42) => (
    <View style={box}>
      <View style={{ width: s * k, height: s * k, borderLeftWidth: w, borderBottomWidth: w, borderColor: color, borderBottomLeftRadius: w / 2, transform: [{ rotate: `${rot}deg` }], marginLeft: rot === 45 ? s * 0.14 : rot === 225 ? -s * 0.14 : 0, marginTop: rot === 135 ? s * 0.14 : rot === -45 ? -s * 0.14 : 0 }} />
    </View>
  );
  switch (name) {
    case 'discover':
      return (
        <View style={box}>
          <View style={{ width: s * 0.86, height: s * 0.86, borderRadius: s, borderWidth: w, borderColor: color }} />
          <View style={abs({ width: s * 0.3, height: s * 0.3, backgroundColor: color, borderRadius: 2, transform: [{ rotate: '45deg' }, { scaleY: 1.6 }] })} />
          <View style={abs({ width: s * 0.1, height: s * 0.1, borderRadius: s, backgroundColor: C.bg })} />
        </View>
      );
    case 'collection':
      return (
        <View style={box}>
          <View style={abs({ width: s * 0.52, height: s * 0.7, borderRadius: s * 0.1, borderWidth: w, borderColor: color, transform: [{ rotate: '-12deg' }, { translateX: -s * 0.1 }], opacity: 0.6 })} />
          <View style={abs({ width: s * 0.52, height: s * 0.7, borderRadius: s * 0.1, borderWidth: w, borderColor: color, transform: [{ rotate: '8deg' }, { translateX: s * 0.08 }] })} />
        </View>
      );
    case 'feed':
      return (
        <View style={box}>
          <View style={{ width: s * 0.84, height: s * 0.66, borderRadius: s * 0.18, borderWidth: w, borderColor: color, justifyContent: 'center', paddingHorizontal: s * 0.14, gap: s * 0.09 }}>
            <View style={{ height: w, borderRadius: w, backgroundColor: color, width: '85%' }} />
            <View style={{ height: w, borderRadius: w, backgroundColor: color, width: '55%' }} />
          </View>
          <View style={abs({ bottom: s * 0.04, left: s * 0.24, width: s * 0.18, height: s * 0.18, borderLeftWidth: w, borderBottomWidth: w, borderColor: color, transform: [{ rotate: '-20deg' }] })} />
        </View>
      );
    case 'explore':
    case 'search':
      return (
        <View style={box}>
          <View style={abs({ top: s * 0.1, left: s * 0.1, width: s * 0.6, height: s * 0.6, borderRadius: s, borderWidth: w, borderColor: color })} />
          <View style={bar(s * 0.3, 45, { right: s * 0.06, bottom: s * 0.16 })} />
        </View>
      );
    case 'gear':
      return (
        <View style={box}>
          {[0, 45, 90, 135, 180, 225, 270, 315].map((r) => (
            <View key={r} style={[StyleSheet.absoluteFill, { alignItems: 'center', transform: [{ rotate: `${r}deg` }] }]}>
              <View style={{ marginTop: s * 0.04, width: s * 0.2, height: s * 0.2, borderRadius: s * 0.04, backgroundColor: color }} />
            </View>
          ))}
          <View style={{ width: s * 0.68, height: s * 0.68, borderRadius: s, borderWidth: s * 0.17, borderColor: color }} />
        </View>
      );
    case 'plus':
      return (
        <View style={box}>
          <View style={bar(s * 0.7, 0)} />
          <View style={bar(s * 0.7, 90)} />
        </View>
      );
    case 'close':
      return (
        <View style={box}>
          <View style={bar(s * 0.75, 45)} />
          <View style={bar(s * 0.75, -45)} />
        </View>
      );
    case 'check':
      return (
        <View style={box}>
          <View style={{ width: s * 0.62, height: s * 0.34, borderLeftWidth: w * 1.2, borderBottomWidth: w * 1.2, borderColor: color, transform: [{ rotate: '-45deg' }], marginTop: -s * 0.12 }} />
        </View>
      );
    case 'back':
      return chev(45);
    case 'forward':
      return chev(225);
    case 'down':
      return chev(-45, 0.36);
    case 'up':
      return chev(135, 0.36);
    case 'share':
      return (
        <View style={box}>
          <View style={abs({ bottom: s * 0.08, width: s * 0.7, height: s * 0.5, borderWidth: w, borderTopWidth: 0, borderColor: color, borderBottomLeftRadius: s * 0.12, borderBottomRightRadius: s * 0.12 })} />
          <View style={abs({ top: s * 0.06, width: w, height: s * 0.6, backgroundColor: color, borderRadius: w })} />
          <View style={abs({ top: s * 0.08, width: s * 0.3, height: s * 0.3, borderLeftWidth: w, borderTopWidth: w, borderColor: color, transform: [{ rotate: '45deg' }] })} />
        </View>
      );
    case 'edit':
      return (
        <View style={box}>
          <View style={abs({ width: s * 0.22, height: s * 0.78, borderWidth: w, borderColor: color, borderRadius: 2, borderBottomLeftRadius: s * 0.11, borderBottomRightRadius: s * 0.11, transform: [{ rotate: '45deg' }] })} />
        </View>
      );
    case 'grid':
      return (
        <View style={[box, { flexDirection: 'row', flexWrap: 'wrap', gap: s * 0.1, padding: s * 0.1 }]}>
          {[0, 1, 2, 3].map((i) => <View key={i} style={{ width: s * 0.35, height: s * 0.35, borderRadius: s * 0.08, borderWidth: w, borderColor: color }} />)}
        </View>
      );
    case 'photo':
      return (
        <View style={box}>
          <View style={{ width: s * 0.86, height: s * 0.68, borderRadius: s * 0.14, borderWidth: w, borderColor: color, overflow: 'hidden' }}>
            <View style={abs({ left: s * 0.1, bottom: -s * 0.12, width: s * 0.4, height: s * 0.4, backgroundColor: color, transform: [{ rotate: '45deg' }] })} />
            <View style={abs({ right: s * 0.12, top: s * 0.1, width: s * 0.14, height: s * 0.14, borderRadius: s, backgroundColor: color })} />
          </View>
        </View>
      );
    case 'bolt':
      return (
        <View style={box}>
          <Text style={{ color, fontSize: s * 0.85, fontWeight: '900', lineHeight: s }}>ϟ</Text>
        </View>
      );
    case 'cards':
      return (
        <View style={box}>
          <View style={abs({ width: s * 0.5, height: s * 0.68, borderRadius: s * 0.08, borderWidth: w, borderColor: color, transform: [{ translateX: -s * 0.1 }, { translateY: s * 0.04 }], opacity: 0.55 })} />
          <View style={abs({ width: s * 0.5, height: s * 0.68, borderRadius: s * 0.08, borderWidth: w, borderColor: color, backgroundColor: 'transparent', transform: [{ translateX: s * 0.1 }, { translateY: -s * 0.04 }] })} />
        </View>
      );
    case 'sort':
      return (
        <View style={box}>
          <View style={abs({ left: s * 0.2, top: s * 0.16, width: w, height: s * 0.66, backgroundColor: color, borderRadius: w })} />
          <View style={abs({ left: s * 0.11, top: s * 0.14, width: s * 0.2, height: s * 0.2, borderLeftWidth: w, borderTopWidth: w, borderColor: color, transform: [{ rotate: '45deg' }] })} />
          <View style={abs({ right: s * 0.2, top: s * 0.18, width: w, height: s * 0.66, backgroundColor: color, borderRadius: w })} />
          <View style={abs({ right: s * 0.11, bottom: s * 0.14, width: s * 0.2, height: s * 0.2, borderRightWidth: w, borderBottomWidth: w, borderColor: color, transform: [{ rotate: '45deg' }] })} />
        </View>
      );
    case 'filter':
      return (
        <View style={[box, { gap: s * 0.14 }]}>
          {[0.78, 0.52, 0.26].map((k) => <View key={k} style={{ width: s * k, height: w, borderRadius: w, backgroundColor: color }} />)}
        </View>
      );
    case 'list':
      return (
        <View style={[box, { gap: s * 0.15, alignItems: 'flex-start', paddingLeft: s * 0.12 }]}>
          {[0, 1, 2].map((k) => <View key={k} style={{ width: s * 0.76, height: w, borderRadius: w, backgroundColor: color }} />)}
        </View>
      );
    case 'more':
      return (
        <View style={[box, { flexDirection: 'row', gap: s * 0.12 }]}>
          {[0, 1, 2].map((k) => <View key={k} style={{ width: s * 0.16, height: s * 0.16, borderRadius: s, backgroundColor: color }} />)}
        </View>
      );
    case 'refresh':
      return (
        <View style={box}>
          <View style={{ width: s * 0.7, height: s * 0.7, borderRadius: s, borderWidth: w, borderColor: color, borderTopColor: 'transparent', transform: [{ rotate: '45deg' }] }} />
          <View style={abs({ top: s * 0.1, right: s * 0.14, width: 0, height: 0, borderLeftWidth: s * 0.14, borderRightWidth: s * 0.14, borderBottomWidth: s * 0.2, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderBottomColor: color, transform: [{ rotate: '120deg' }] })} />
        </View>
      );
    case 'binder':
      return (
        <View style={box}>
          <View style={{ width: s * 0.66, height: s * 0.82, borderRadius: s * 0.1, borderWidth: w, borderColor: color }} />
          {[0.26, 0.5, 0.74].map((k) => <View key={k} style={abs({ left: s * 0.12, top: s * k - w / 2, width: s * 0.14, height: w, borderRadius: w, backgroundColor: color })} />)}
        </View>
      );
    case 'lock':
      return (
        <View style={box}>
          <View style={abs({ top: s * 0.08, width: s * 0.44, height: s * 0.44, borderRadius: s, borderWidth: w, borderColor: color })} />
          <View style={abs({ bottom: s * 0.08, width: s * 0.66, height: s * 0.48, borderRadius: s * 0.1, backgroundColor: color })} />
        </View>
      );
    case 'heart':
      return (
        <View style={box}>
          <Text style={{ color, fontSize: s * 0.9, lineHeight: s }}>♡</Text>
        </View>
      );
  }
}

/* ---------- charts ---------- */
export interface Pt {
  day: string;
  value: number;
}

/** Catmull-Rom resample: `n` smooth values through the points. */
function smooth(vals: number[], n: number): number[] {
  if (vals.length === 1) return Array(n).fill(vals[0]);
  const out: number[] = [];
  for (let k = 0; k < n; k++) {
    const t = (k / (n - 1)) * (vals.length - 1);
    const i = Math.min(vals.length - 2, Math.floor(t));
    const f = t - i;
    const p0 = vals[Math.max(0, i - 1)];
    const p1 = vals[i];
    const p2 = vals[i + 1];
    const p3 = vals[Math.min(vals.length - 1, i + 2)];
    const v = 0.5 * (2 * p1 + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f + (-p0 + 3 * p1 - 3 * p2 + p3) * f * f * f);
    out.push(Math.min(Math.max(v, Math.min(p1, p2)), Math.max(p1, p2))); // no overshoot
  }
  return out;
}

const shortDay = (d: string) => {
  const t = new Date(`${d}T12:00:00`);
  return isNaN(+t) ? d : t.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};
const compact = (v: number) => (v >= 1000 ? `$${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k` : `$${v >= 100 ? Math.round(v) : v.toFixed(v >= 10 ? 0 : 2)}`);

/** Smooth filled area chart (or a bare sparkline with `spark`). Width comes from its parent. */
export function AreaChart({ points, height = 180, color = C.blue, spark, lineColor, fillTop = 0.45, bg = C.bg, labelW = 44 }: { points: Pt[]; height?: number; color?: string; spark?: boolean; lineColor?: string; fillTop?: number; bg?: string; labelW?: number }) {
  const [w, setW] = useState(0);
  const pad = spark ? { l: 0, r: 0, t: 3, b: 3 } : { l: labelW, r: 6, t: 10, b: 24 };
  const pw = Math.max(0, w - pad.l - pad.r);
  const ph = height - pad.t - pad.b;
  const data = useMemo(() => {
    const vals = points.map((p) => p.value);
    if (!vals.length || pw <= 0) return null;
    let lo = Math.min(...vals);
    let hi = Math.max(...vals);
    if (hi - lo < 1e-6) {
      hi = hi + Math.max(1, hi * 0.1);
      lo = Math.max(0, lo - Math.max(1, lo * 0.1));
    } else {
      const m = (hi - lo) * 0.12;
      hi += m;
      lo = Math.max(0, lo - m);
    }
    const step = spark ? 3 : 3;
    const n = Math.max(2, Math.floor(pw / step));
    const ys = smooth(vals, n).map((v) => pad.t + ph - ((v - lo) / (hi - lo)) * ph);
    return { lo, hi, n, ys, colW: pw / n };
  }, [points, pw, ph, spark]);

  const lc = lineColor || color;
  return (
    <View style={{ height, width: '100%' }} onLayout={(e) => setW(e.nativeEvent.layout.width)}>
      {data ? (
        <>
          {!spark
            ? [0, 1, 2, 3].map((g) => {
                const y = pad.t + (ph * g) / 3;
                const v = data.hi - ((data.hi - data.lo) * g) / 3;
                return (
                  <View key={g} style={{ position: 'absolute', left: 0, right: 0, top: y - 7, height: 14, flexDirection: 'row', alignItems: 'center' }}>
                    <Text style={{ width: pad.l - 6, marginRight: 6, textAlign: 'left', color: C.ink3, fontSize: 10 }} numberOfLines={1}>{compact(v)}</Text>
                    <View style={{ flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: C.line }} />
                  </View>
                );
              })
            : null}
          {/* fill */}
          <View style={{ position: 'absolute', left: pad.l, top: 0, width: pw, height: pad.t + ph, flexDirection: 'row', alignItems: 'flex-end', overflow: 'hidden' }}>
            {data.ys.map((y, i) => (
              <View key={i} style={{ width: data.colW + 0.6, marginRight: -0.6, height: pad.t + ph - y, backgroundColor: alpha(color, fillTop) }} />
            ))}
            <Gradient vertical steps={14} colors={[alpha(bg, 0), alpha(bg, 0.55), alpha(bg, 0.95)]} />
          </View>
          {/* line */}
          {data.ys.slice(1).map((y2, i) => {
            const y1 = data.ys[i];
            const x1 = pad.l + i * data.colW + data.colW / 2;
            const x2 = x1 + data.colW;
            const dx = x2 - x1;
            const dy = y2 - y1;
            const len = Math.sqrt(dx * dx + dy * dy) + 0.8;
            const th = spark ? 2 : 2.5;
            return (
              <View key={i} style={{ position: 'absolute', left: (x1 + x2) / 2 - len / 2, top: (y1 + y2) / 2 - th / 2, width: len, height: th, borderRadius: th, backgroundColor: lc, transform: [{ rotate: `${Math.atan2(dy, dx)}rad` }] }} />
            );
          })}
          {/* end dot */}
          {!spark ? (
            <View style={{ position: 'absolute', left: pad.l + pw - data.colW / 2 - 5, top: data.ys[data.ys.length - 1] - 5, width: 10, height: 10, borderRadius: 5, backgroundColor: lc, borderWidth: 2, borderColor: bg }} />
          ) : null}
          {!spark && points.length ? (
            <View style={{ position: 'absolute', left: pad.l, width: pw, bottom: 0, flexDirection: 'row', justifyContent: 'space-between' }}>
              {(points.length >= 3 ? [points[0], points[Math.floor((points.length - 1) / 2)], points[points.length - 1]] : [points[0], points[points.length - 1]]).map((p, i) => (
                <Text key={i} style={{ color: C.ink3, fontSize: 10 }}>{shortDay(p.day)}</Text>
              ))}
            </View>
          ) : null}
        </>
      ) : null}
    </View>
  );
}
