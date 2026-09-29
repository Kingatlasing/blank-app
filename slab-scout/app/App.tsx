import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BackHandler, Pressable, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import HomeScreen from './src/screens/HomeScreen';
import ScanScreen from './src/screens/ScanScreen';
import ExploreScreen from './src/screens/ExploreScreen';
import SetScreen from './src/screens/SetScreen';
import CardScreen from './src/screens/CardScreen';
import VaultScreen from './src/screens/VaultScreen';
import CommunityScreen from './src/screens/CommunityScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import { Segmented } from './src/components/cards';
import { DEFAULT_SETTINGS, getApiKey, loadSettings, saveSettings } from './src/storage';
import { Store, VaultRecord } from './src/core/community';
import { loadKeys, useCatalogVersion } from './src/core/catalog';
import { AppCtx, Ctx, Tab } from './src/appContext';
import { C, S } from './src/theme';
import type { Settings } from './src/types';

type Route = { kind: 'set'; id: string } | { kind: 'card'; key: string };

const TABS: [Tab, string, string][] = [
  ['home', '▤', 'Portfolio'],
  ['scan', '◉', 'Scan'],
  ['explore', '⌕', 'Explore'],
  ['collection', '▦', 'Collection'],
  ['settings', '⋯', 'More'],
];

export default function App() {
  const [tab, setTab] = useState<Tab>('home');
  const [stack, setStack] = useState<Route[]>([]);
  const [more, setMore] = useState<'settings' | 'community'>('settings');
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [apiKey, setKey] = useState('');
  const [ready, setReady] = useState(false);
  const [vault, setVault] = useState<VaultRecord[]>([]);
  const [vaultLoading, setVaultLoading] = useState(false);
  const [vaultErr, setVaultErr] = useState('');
  useCatalogVersion(); // re-render screens when downloaded card lists arrive

  const store = useMemo(() => new Store(settings.supabaseUrl, settings.supabaseKey), [settings.supabaseUrl, settings.supabaseKey]);
  const needsCode = store.shared && settings.vaultCode.length < 6;

  const refreshKey = useCallback(async (s: Settings) => setKey(await getApiKey(s.provider)), []);
  const refreshVault = useCallback(async () => {
    if (needsCode) return setVault([]);
    setVaultLoading(true);
    setVaultErr('');
    try {
      const list = await store.vaultList(settings.vaultCode);
      setVault(list);
      // cards from downloadable sets: fetch their sets so photos and prices show
      loadKeys(list.map((r) => r.match?.catalog_key)).catch(() => {});
    } catch (e: any) {
      setVaultErr(String(e?.message || e));
    } finally {
      setVaultLoading(false);
    }
  }, [store, settings.vaultCode, needsCode]);

  useEffect(() => {
    (async () => {
      const s = await loadSettings();
      setSettings(s);
      await refreshKey(s);
      setReady(true);
    })();
  }, [refreshKey]);
  useEffect(() => {
    if (ready) refreshVault();
  }, [ready, refreshVault]);

  // Android back button walks back through card/set pages.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (stack.length) {
        setStack((s) => s.slice(0, -1));
        return true;
      }
      if (tab !== 'home') {
        setTab('home');
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [stack.length, tab]);

  const changeSettings = (s: Settings) => {
    setSettings(s);
    saveSettings(s);
    refreshKey(s);
  };

  const ctx: AppCtx = {
    settings, store, vault, vaultLoading, vaultErr, needsCode, refreshVault,
    addRecord: async (rec, list = 'collection') => {
      await store.vaultAdd(settings.vaultCode, { ...rec, list });
      await refreshVault();
    },
    removeRecord: async (id) => {
      await store.vaultDelete(settings.vaultCode, id);
      await refreshVault();
    },
    openSet: (id) => setStack((s) => [...s, { kind: 'set', id }]),
    openCard: (key) => setStack((s) => [...s, { kind: 'card', key }]),
    goTab: (t) => {
      setStack([]);
      setTab(t);
    },
  };

  if (!ready) return <View style={{ flex: 1, backgroundColor: C.bg }} />;
  const top = stack[stack.length - 1];
  const pop = () => setStack((s) => s.slice(0, -1));
  const count = vault.filter((r) => (r.list || 'collection') === 'collection').length;

  return (
    <Ctx.Provider value={ctx}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']}>
          {!top ? (
            <View style={st.header}>
              <View style={st.mark}><View style={st.markLabel} /></View>
              <Text style={st.title}>{TABS.find((t) => t[0] === tab)?.[2] === 'Portfolio' ? 'Slab Scout' : TABS.find((t) => t[0] === tab)?.[2]}</Text>
              <Text style={st.mode}>{settings.provider === 'off' ? 'FREE' : apiKey ? 'AI BOOST' : 'ADD KEY'}</Text>
            </View>
          ) : null}
          <View style={{ flex: 1 }}>
            {top?.kind === 'set' ? <SetScreen key={top.id} setId={top.id} onBack={pop} /> : null}
            {top?.kind === 'card' ? <CardScreen key={top.key} cardKey={top.key} onBack={pop} /> : null}
            {/* The current tab stays mounted underneath, so a scan in progress isn't lost when you open its card page. */}
            <View style={{ flex: 1, display: top ? 'none' : 'flex' }}>
              {tab === 'home' && <HomeScreen />}
              {tab === 'scan' && <ScanScreen settings={settings} apiKey={apiKey} store={store} goSettings={() => setTab('settings')} onSaved={() => {}} />}
              {tab === 'explore' && <ExploreScreen />}
              {tab === 'collection' && <VaultScreen />}
              {tab === 'settings' && (
                <View style={{ flex: 1 }}>
                  <View style={{ paddingHorizontal: 16, paddingTop: 12 }}>
                    <Segmented options={[['settings', 'Settings'], ['community', 'Community']]} value={more} onChange={setMore} />
                  </View>
                  {more === 'settings' ? <SettingsScreen settings={settings} onChange={changeSettings} onKeyChange={() => refreshKey(settings)} /> : <CommunityScreen store={store} />}
                </View>
              )}
            </View>
          </View>
        </SafeAreaView>
        <SafeAreaView edges={['bottom']} style={st.tabs}>
          {TABS.map(([id, icon, label]) => {
            const on = tab === id && !top;
            return (
              <Pressable key={id} style={st.tab} onPress={() => { setStack([]); setTab(id); if (id === 'collection' || id === 'home') refreshVault(); }}>
                <View style={[st.iconWrap, id === 'scan' && st.scanBtn]}>
                  <Text style={[st.icon, on && { color: C.accent }, id === 'scan' && { color: C.accentInk }]}>{icon}</Text>
                </View>
                <Text style={[st.tabText, on && { color: C.ink }]} numberOfLines={1}>{label}{id === 'collection' && count ? ` ${count}` : ''}</Text>
              </Pressable>
            );
          })}
        </SafeAreaView>
      </SafeAreaProvider>
    </Ctx.Provider>
  );
}

const st = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.line },
  mark: { width: 22, height: 28, borderRadius: 4, borderWidth: 2, borderColor: C.ink, padding: 2 },
  markLabel: { height: 6, borderRadius: 2, backgroundColor: C.accent },
  title: { ...S.h2, flex: 1, fontWeight: '800' },
  mode: { color: C.ink2, fontSize: 11, fontWeight: '700', letterSpacing: 1.2 },
  tabs: { flexDirection: 'row', paddingHorizontal: 6, paddingTop: 6, backgroundColor: C.surface, borderTopWidth: 1, borderTopColor: C.line },
  tab: { flex: 1, alignItems: 'center', paddingBottom: 6, gap: 2 },
  iconWrap: { height: 30, minWidth: 30, alignItems: 'center', justifyContent: 'center' },
  scanBtn: { backgroundColor: C.accent, borderRadius: 15, paddingHorizontal: 12 },
  icon: { color: C.ink2, fontSize: 18, fontWeight: '800' },
  tabText: { color: C.ink2, fontWeight: '700', fontSize: 11 },
});
