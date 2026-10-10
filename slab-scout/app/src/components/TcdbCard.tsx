/**
 * Cards whose checklist comes from TCDB (Trading Card Database) have no photo the app may keep or show directly.
 * Instead the card's own TCDB page is shown live in its place (phone: a web view; browser: an embedded frame),
 * opened at the page content so the card scan is in view. Nothing is downloaded or stored by the app.
 */
import React, { createElement, useState } from 'react';
import { ActivityIndicator, Platform, Text, View } from 'react-native';
import type { Card } from '../core/catalog';

/** The card's TCDB page, or '' when the card isn't from TCDB.
 *  path 'tcdb:<set id>/<card id>/<card slug>' -> the card's own page;
 *  path 'tcdbset:<set id>/<card id>/<set slug>' -> the set checklist, scrolled to that card's row. */
export function tcdbPage(card: Card | null | undefined): string {
  const m = card?.path?.match(/^tcdb:(\d+)\/(\d+)\/(.+)$/);
  if (m) return `https://www.tcdb.com/ViewCard.cfm/sid/${m[1]}/cid/${m[2]}/${m[3]}#content`;
  const s = card?.path?.match(/^tcdbset:(\d+)\/(\d+)\/(.+)$/);
  return s ? `https://www.tcdb.com/Checklist.cfm/sid/${s[1]}/${s[3]}#${s[2]}` : '';
}

export function TcdbCard({ card, width, radius = 12 }: { card: Card; width: number; radius?: number }) {
  const url = tcdbPage(card);
  const height = Math.round((width / 63) * 88);
  const [loading, setLoading] = useState(true);
  if (!url) return null;
  const frame: any = { width, height, borderRadius: radius, overflow: 'hidden', backgroundColor: '#fff' };
  if (Platform.OS === 'web') {
    return (
      <View style={frame}>
        {createElement('iframe', {
          src: url,
          title: `${card.name} on TCDB`,
          loading: 'lazy',
          style: { width: '100%', height: '100%', border: 0 },
        })}
      </View>
    );
  }
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { WebView } = require('react-native-webview');
  return (
    <View style={frame}>
      <WebView
        source={{ uri: url }}
        style={{ flex: 1 }}
        onLoadEnd={() => setLoading(false)}
        setSupportMultipleWindows={false}
        allowsBackForwardNavigationGestures
      />
      {loading ? (
        <View style={{ position: 'absolute', inset: 0, alignItems: 'center', justifyContent: 'center' } as any}>
          <ActivityIndicator />
          <Text style={{ marginTop: 6, fontSize: 12, color: '#666' }}>Loading card from TCDB…</Text>
        </View>
      ) : null}
    </View>
  );
}
