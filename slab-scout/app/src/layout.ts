/** Screen-size aware sizing: one hook every screen uses instead of hard-coded sizes.
 * Phones from iPhone SE (375x667) to Pro Max (440x956), Android phones, and iPads (content centred). */
import { useMemo } from 'react';
import { Platform, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

const BASE_W = 393; // iPhone 15 / 16 / 17 width the designs are drawn at
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
export const CARD_RATIO = 63 / 88;

export interface Layout {
  width: number;
  height: number;
  tablet: boolean;
  landscape: boolean;
  /** width the content uses (centred on tablets) */
  contentW: number;
  maxW: number;
  /** 0.85 – 1.25 */
  scale: number;
  /** scaled size (fonts, icons, spacing) */
  fs: (n: number) => number;
  sp: (n: number) => number;
  gutter: number;
  /** grid columns for card tiles */
  cols: number;
  /** width of one grid tile for `cols` columns inside contentW - 2*gutter */
  tileW: (cols?: number, gap?: number) => number;
  /** width of a carousel card: shows `n` cards plus a peek of the next */
  carouselW: (n?: number) => number;
  top: number;
  bottom: number;
  tabBarH: number;
  /** scanner: space the top bar and bottom panel take, and the card frame fitted between them */
  scan: { topBar: number; bottomPanel: number; frame: { w: number; h: number; x: number; y: number } };
}

export function computeLayout(width: number, height: number, insets: { top: number; bottom: number }): Layout {
  const tablet = Math.min(width, height) >= 600;
  const landscape = width > height;
  // iPad: content centred in a column (wider in landscape, never edge to edge)
  const maxW = tablet ? Math.min(width, landscape ? 900 : 860) : width;
  const contentW = Math.min(width, maxW);
  const scale = clamp(contentW / BASE_W, 0.85, tablet ? 1.18 : 1.25);
  const fs = (n: number) => Math.round(n * scale);
  const sp = (n: number) => Math.round(n * scale);
  const gutter = sp(16);
  const cols = tablet ? (contentW >= 800 ? 5 : 4) : width >= 400 ? 3 : 2;
  const inner = contentW - gutter * 2;
  const tileW = (c = cols, gap = sp(10)) => Math.floor((inner - gap * (c - 1)) / c);
  const carouselW = (n = tablet ? 4.3 : width >= 400 ? 2.6 : 2.25) => Math.floor((inner - sp(12) * Math.floor(n)) / n);
  const top = insets.top;
  const bottom = Math.max(insets.bottom, Platform.OS === 'android' ? 8 : 0);
  const tabBarH = sp(56) + Math.max(bottom, 6);

  // scanner: card frame (63:88) fitted between the top bar and the result panel
  const topBar = top + sp(64);
  const bottomPanel = bottom + sp(232);
  const availH = height - topBar - bottomPanel - sp(20);
  const maxFw = Math.min(width * 0.82, tablet ? 460 : width);
  let fh = Math.max(160, availH);
  let fw = fh * CARD_RATIO;
  if (fw > maxFw) {
    fw = maxFw;
    fh = fw / CARD_RATIO;
  }
  fw = Math.round(fw);
  fh = Math.round(fh);
  const frame = { w: fw, h: fh, x: Math.round((width - fw) / 2), y: Math.round(topBar + Math.max(0, (height - topBar - bottomPanel - fh) / 2)) };

  return { width, height, tablet, landscape, contentW, maxW, scale, fs, sp, gutter, cols, tileW, carouselW, top, bottom, tabBarH, scan: { topBar, bottomPanel, frame } };
}

export function useLayout(): Layout {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  return useMemo(() => computeLayout(width, height, insets), [width, height, insets.top, insets.bottom]);
}
