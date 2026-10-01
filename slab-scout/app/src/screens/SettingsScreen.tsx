import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { PROVIDERS, callModel, providerInfo } from '../providers';
import { getApiKey, setApiKey } from '../storage';
import { C, S } from '../theme';
import type { ProviderId, Settings } from '../types';
import { Btn } from '../components/ui';
import { ocrAvailable } from '../core/ocr';
import { serverOn, setScanServer, wakeServer } from '../core/server';
import { clearOffline, downloadAll, offlineStatus, OfflineStatus } from '../core/catalog';

export default function SettingsScreen({ settings, onChange, onKeyChange }: { settings: Settings; onChange: (s: Settings) => void; onKeyChange: () => void }) {
  const [key, setKey] = useState('');
  const [show, setShow] = useState(false);
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const on = settings.provider !== 'off';
  const info = on ? providerInfo(settings.provider as ProviderId) : null;

  useEffect(() => {
    getApiKey(settings.provider).then(setKey);
    setStatus(null);
  }, [settings.provider]);

  async function saveKey(v: string) {
    setKey(v);
    if (on) await setApiKey(settings.provider as ProviderId, v);
    onKeyChange();
  }
  async function test() {
    setTesting(true);
    setStatus(null);
    try {
      const out = await callModel(settings, key.trim(), { prompt: 'Reply with only the word OK.', maxTokens: 20 });
      setStatus({ ok: true, msg: `Connected. The model replied “${out.text.trim().slice(0, 30)}”.` });
    } catch (e: any) {
      setStatus({ ok: false, msg: e?.message || 'Connection failed.' });
    } finally {
      setTesting(false);
    }
  }
  const opt = (id: ProviderId | 'off', label: string, sub?: string) => {
    const sel = settings.provider === id;
    return (
      <Pressable key={id} style={[st.opt, sel && st.optOn]} onPress={() => onChange({ ...settings, provider: id })}>
        <View style={[st.radio, sel && st.radioOn]} />
        <View style={{ flex: 1 }}>
          <Text style={[S.body, { fontWeight: sel ? '800' : '500' }]}>{label}</Text>
          {sub ? <Text style={S.muted}>{sub}</Text> : null}
        </View>
      </Pressable>
    );
  };

  return (
    <ScrollView style={S.screen} contentContainerStyle={[S.pad, { paddingBottom: 60 }]} keyboardShouldPersistTaps="handled">
      <Text style={S.h2}>AI boost</Text>
      <Text style={S.muted}>Slab Scout works for free with no key: it reads the card, matches free databases and the community catalog, measures centering, and grades from your checklist. AI adds photo-based ID for any card, an authenticity check and an AI grade.</Text>
      <View style={{ gap: 8 }}>
        {opt('off', 'Off (free, no key)', 'Everything free; you answer the condition checklist')}
        {PROVIDERS.map((p) => opt(p.id, p.name, p.id === 'gemini' ? 'Free key from Google AI Studio, no credit card' : undefined))}
      </View>

      {on && info ? (
        <View style={S.card}>
          <Text style={S.h3}>API key</Text>
          <View style={S.row}>
            <TextInput style={[S.input, { flex: 1 }]} value={key} onChangeText={saveKey} placeholder={info.keyHint} placeholderTextColor={C.ink2} secureTextEntry={!show} autoCapitalize="none" autoCorrect={false} />
            <Btn label={show ? 'Hide' : 'Show'} onPress={() => setShow(!show)} style={{ paddingVertical: 11 }} />
          </View>
          <Text style={[S.muted, { color: C.accent }]} onPress={() => Linking.openURL(info.keyUrl)}>Get a {info.name} key ↗</Text>
          <Text style={S.muted}>{info.searchNote} The key stays in your phone's secure keychain and is only sent to {info.name}.</Text>
          {settings.provider === 'compatible' && (
            <>
              <Text style={S.eyebrow}>Base URL</Text>
              <TextInput style={S.input} value={settings.compatibleBaseUrl} onChangeText={(v) => onChange({ ...settings, compatibleBaseUrl: v.trim() })} autoCapitalize="none" autoCorrect={false} />
            </>
          )}
          <Text style={S.eyebrow}>Model</Text>
          <TextInput
            style={S.input}
            value={settings.models[settings.provider as ProviderId]}
            onChangeText={(v) => onChange({ ...settings, models: { ...settings.models, [settings.provider]: v.trim() } })}
            placeholder={info.defaultModel || 'a vision model'}
            placeholderTextColor={C.ink2}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Pressable style={[S.btn, S.primary]} onPress={test} disabled={testing || !key}>
            {testing ? <ActivityIndicator color={C.accentInk} /> : <Text style={S.primaryText}>Test connection</Text>}
          </Pressable>
          {status ? <Text style={[S.body, { color: status.ok ? C.good : C.crit }]}>{status.msg}</Text> : null}
        </View>
      ) : null}

      <Text style={[S.h2, { marginTop: 8 }]}>Show prices as</Text>
      <View style={[S.row, { gap: 6, flexWrap: 'wrap' }]}>
        {([['raw', 'Raw'], ['psa9', 'PSA 9'], ['psa10', 'PSA 10 (Gem Mint)']] as const).map(([id, label]) => {
          const on = (settings.priceMode || 'raw') === id;
          return (
            <Pressable key={id} onPress={() => onChange({ ...settings, priceMode: id })} style={[S.chip, { paddingVertical: 8, paddingHorizontal: 12 }, on && { backgroundColor: C.accent }]}>
              <Text style={[S.chipText, on && { color: C.accentInk }]}>{label}</Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={S.muted}>Graded views show the PSA price when the card has graded sales, otherwise its raw price marked "raw".</Text>

      <OfflineCatalog />

      <Text style={[S.h2, { marginTop: 8 }]}>Vault & community</Text>
      <View style={S.card}>
        <Text style={S.eyebrow}>Vault code</Text>
        <TextInput style={S.input} value={settings.vaultCode} onChangeText={(v) => onChange({ ...settings, vaultCode: v.trim() })} placeholder="a private code, 6+ characters" placeholderTextColor={C.ink2} secureTextEntry autoCapitalize="none" autoCorrect={false} />
        <Text style={S.muted}>Use the same code in the Streamlit app to see the same vault. Anyone with the code can see and edit that vault, so keep it private.</Text>
        <Text style={S.eyebrow}>Supabase project URL</Text>
        <TextInput style={S.input} value={settings.supabaseUrl} onChangeText={(v) => onChange({ ...settings, supabaseUrl: v.trim() })} placeholder="https://xxxx.supabase.co" placeholderTextColor={C.ink2} autoCapitalize="none" autoCorrect={false} />
        <Text style={S.eyebrow}>Supabase anon key</Text>
        <TextInput style={S.input} value={settings.supabaseKey} onChangeText={(v) => onChange({ ...settings, supabaseKey: v.trim() })} placeholder="eyJ…" placeholderTextColor={C.ink2} autoCapitalize="none" autoCorrect={false} secureTextEntry />
        <Text style={S.muted}>
          {settings.supabaseUrl && settings.supabaseKey
            ? 'Connected settings saved. Your vault and the community catalog sync online.'
            : 'Leave blank to keep everything on this phone. With a free Supabase project (see README), everyone shares one catalog that learns from every scan.'}
        </Text>
      </View>

      <ScanServerBox settings={settings} onChange={onChange} />

      <Text style={S.muted}>Text reading: {ocrAvailable() ? (serverOn() ? 'on (scan server: English, Japanese, Korean)' : 'on (this phone)') : 'off in Expo Go and the browser. Add a scan server above to turn it on.'}</Text>
      <Text style={S.muted}>Grades are estimates from photos. PSA and TAG inspect cards under magnification, so use these to decide what's worth submitting.</Text>
    </ScrollView>
  );
}

/** The scan server: the web app's full engine (text in English / Japanese / Korean, grading) for this phone. */
function ScanServerBox({ settings, onChange }: { settings: Settings; onChange: (s: Settings) => void }) {
  const [state, setState] = useState<'' | 'checking' | 'ok' | 'down'>('');
  const test = async () => {
    setScanServer(settings.scanServer);
    setState('checking');
    setState((await wakeServer()) ? 'ok' : 'down');
  };
  return (
    <>
      <Text style={[S.h2, { marginTop: 8 }]}>Scan server</Text>
      <View style={S.card}>
        <Text style={S.eyebrow}>Address</Text>
        <TextInput style={S.input} value={settings.scanServer || ''} onChangeText={(v) => { setState(''); onChange({ ...settings, scanServer: v.trim() }); }}
          placeholder="your-scan-app.streamlit.app" placeholderTextColor={C.ink2} autoCapitalize="none" autoCorrect={false} keyboardType="url" />
        <Btn label={state === 'checking' ? 'Waking it up… (up to a minute)' : 'Test connection'} onPress={test} disabled={!settings.scanServer || state === 'checking'} />
        <Text style={S.muted}>
          {state === 'ok' ? 'Connected. Scans now read text (English, Japanese, Korean) and grade with the full engine.'
            : state === 'down' ? "Couldn't reach it. Check the address. If the app is asleep, open the address in your browser, tap the button to wake it, then test again."
            : 'Your free Streamlit scan app. With it, scans read the words on the card in English, Japanese and Korean and use the same grading as the web app. Without it, scanning runs on the phone only.'}
        </Text>
      </View>
    </>
  );
}

const st = StyleSheet.create({
  opt: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, borderRadius: 16, padding: 14 },
  optOn: { borderColor: C.blue },
  radio: { width: 18, height: 18, borderRadius: 9, borderWidth: 2, borderColor: C.ink2 },
  radioOn: { borderColor: C.blue, backgroundColor: C.blue },
});


/** Save the whole card database on the phone so search, sets and prices work without internet. */
function OfflineCatalog() {
  const [st, setSt] = useState<OfflineStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [prog, setProg] = useState<[number, number] | null>(null);
  const [err, setErr] = useState('');
  const sig = React.useRef({ cancelled: false });
  const refresh = () => offlineStatus().then(setSt).catch(() => setSt(null));
  useEffect(() => {
    refresh();
  }, []);
  const mb = (b: number) => `${(b / 1e6).toFixed(0)} MB`;
  const all = st && st.total > 0 && st.files >= st.total;
  async function go() {
    setBusy(true);
    setErr('');
    sig.current = { cancelled: false };
    try {
      await downloadAll((d, t) => setProg([d, t]), sig.current);
    } catch (e: any) {
      setErr(`${e?.message || e}. Check your connection and try again; finished files are kept.`);
    } finally {
      setBusy(false);
      setProg(null);
      refresh();
    }
  }
  return (
    <View style={{ gap: 8 }}>
      <Text style={[S.h2, { marginTop: 8 }]}>Offline card database</Text>
      <Text style={S.muted}>
        The phone always has the smaller sets. The big ones (every Upper Deck and Topps baseball set, and more) download when you open them. Save everything once and search, sets, prices and photo IDs work with no internet.
      </Text>
      {st ? (
        <Text style={S.body}>
          {all ? '✓ Everything is saved on this phone' : `Saved: ${st.files.toLocaleString()} of ${st.total.toLocaleString()} files`} · {mb(st.bytes)} of {mb(st.totalBytes)}
        </Text>
      ) : (
        <Text style={S.muted}>Checking…</Text>
      )}
      {prog ? (
        <View style={{ gap: 4 }}>
          <View style={{ height: 8, borderRadius: 4, backgroundColor: C.surface2, overflow: 'hidden' }}>
            <View style={{ height: 8, backgroundColor: C.accent, width: `${(prog[0] / Math.max(1, prog[1])) * 100}%` }} />
          </View>
          <Text style={S.muted}>{prog[0].toLocaleString()} / {prog[1].toLocaleString()} files</Text>
        </View>
      ) : null}
      {err ? <Text style={[S.muted, { color: C.crit }]}>{err}</Text> : null}
      <View style={[S.row, { gap: 8 }]}>
        {busy ? (
          <Btn label="Stop" onPress={() => (sig.current.cancelled = true)} />
        ) : (
          <Btn primary label={all ? 'Check for updates' : st && st.files ? 'Finish download' : `Download everything${st ? ` (${mb(st.totalBytes)})` : ''}`} onPress={go} />
        )}
        {st && st.files && !busy ? <Btn danger label="Delete saved copy" onPress={() => { clearOffline(); refresh(); }} /> : null}
      </View>
      <Text style={S.muted}>Photos of the cards in your collection are saved on the phone automatically. Other card photos load from the price guide when you're online. Best on Wi-Fi.</Text>
    </View>
  );
}
