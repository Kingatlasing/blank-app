import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { PROVIDERS, callModel, providerInfo } from '../providers';
import { getApiKey, setApiKey } from '../storage';
import { C, S } from '../theme';
import type { ProviderId, Settings } from '../types';
import { Btn } from '../components/ui';
import { ocrAvailable } from '../core/ocr';

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

      <Text style={S.muted}>Text reading on this device: {ocrAvailable() ? 'available' : 'not available in Expo Go. Install the app build to enable it.'}</Text>
      <Text style={S.muted}>Grades are estimates from photos. PSA and TAG inspect cards under magnification, so use these to decide what's worth submitting.</Text>
    </ScrollView>
  );
}

const st = StyleSheet.create({
  opt: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, borderRadius: 12, padding: 14 },
  optOn: { borderColor: C.accent },
  radio: { width: 18, height: 18, borderRadius: 9, borderWidth: 2, borderColor: C.ink2 },
  radioOn: { borderColor: C.accent, backgroundColor: C.accent },
});
