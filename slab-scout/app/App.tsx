import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { setScanServer } from './src/core/server';
import { BackHandler, Pressable, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import HomeScreen from './src/screens/HomeScreen';
import ScanScreen from './src/screens/ScanScreen';
import ExploreScreen from './src/screens/ExploreScreen';
import SetScreen from './src/screens/SetScreen';
import CardScreen from './src/screens/CardScreen';
import VaultScreen from './src/screens/VaultScreen';
import CommunityScreen from './src/screens/CommunityScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import { Header } from './src/components/cards';
import { Icon, IconName } from './src/components/visual';
import { DEFAULT_SETTINGS, EMPTY_PROFILE, getApiKey, loadProfile, loadSettings, Profile, saveProfile, saveSettings } from './src/storage';
import { Store, VaultRecord } from './src/core/community';
import { getCard, loadKeys, savePhotos, useCatalogVersion } from './src/core/catalog';
import { AppCtx, Ctx, Tab } from './src/appContext';
import { C } from './src/theme';
import { useLayout } from './src/layout';
import type { Settings } from './src/types';

type Route = { kind: 'set'; id: string } | { kind: 'card'; key: string } | { kind: 'settings' };

/** Bottom tabs: Discover, Collection, Scan (centre, lime outline), Feed, Explore. Settings opens from the gear on Discover. */
const TABS: [Tab, IconName | null, string][] = [
  ['home', 'discover', 'Discover'],
  ['collection', 'collection', 'Collection'],
  ['scan', null, 'Scan'],
  ['feed', 'feed', 'Feed'],
  ['explore', 'explore', 'Explore'],
];

export default function App() {
  return (
    <SafeAreaProvider style={{ backgroundColor: C.bg }}>
      <Main />
    </SafeAreaProvider>
  );
}

function Main() {
  const L = useLayout();
  const [tab, setTabRaw] = useState<Tab>('home');
  const [prevTab, setPrevTab] = useState<Tab>('home');
  const setTab = (t: Tab) => {
    if (t === 'settings') {
      setStack((s) => [...s, { kind: 'settings' }]);
      return;
    }
    setTabRaw((cur) => {
      if (cur !== t && cur !== 'scan') setPrevTab(cur);
      return t;
    });
  };
  const [stack, setStack] = useState<Route[]>([]);
  const [profile, setProfileState] = useState<Profile>(EMPTY_PROFILE);
  const [searchToken, setSearchToken] = useState(0);
  const [immersive, setImmersive] = useState(false);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [apiKey, setKey] = useState('');
  const [ready, setReady] = useState(false);
  const [vault, setVault] = useState<VaultRecord[]>([]);
  const [vaultLoading, setVaultLoading] = useState(false);
  const [vaultErr, setVaultErr] = useState('');
  useCatalogVersion(); // re-render screens when downloaded card lists arrive
  setScanServer(settings.scanServer); // full scanning engine online (core/server.ts)

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
      const keys = list.map((r) => r.match?.catalog_key);
      loadKeys(keys)
        .then(() => savePhotos(keys.map((k) => getCard(k)))) // collection photos work offline
        .catch(() => {});
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
      setProfileState(await loadProfile());
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
      if (tab === 'scan') {
        setTabRaw(prevTab);
        return true;
      }
      if (tab !== 'home') {
        setTabRaw('home');
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [stack.length, tab, prevTab]);

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
      if (t === 'settings') return setStack((s) => [...s, { kind: 'settings' }]);
      setStack([]);
      setTab(t);
    },
    openSearch: () => {
      setStack([]);
      setSearchToken((n) => n + 1);
      setTab('explore');
    },
    modeLabel: settings.provider === 'off' ? 'FREE' : apiKey ? 'AI BOOST' : 'ADD KEY',
    openSettings: () => setStack((s) => [...s, { kind: 'settings' }]),
    profile,
    setProfile: (p) => {
      setProfileState(p);
      saveProfile(p).catch(() => {});
    },
    displayName: profile.name.trim() || 'My Collection',
  };

  if (!ready) return <View style={{ flex: 1, backgroundColor: C.bg }} />;
  const top = stack[stack.length - 1];
  const pop = () => setStack((s) => s.slice(0, -1));
  const hideTabs = !top && tab === 'scan' && immersive;
  // the Collection profile header and the scanner draw under the status bar themselves
  const ownTop = tab === 'scan' || tab === 'collection';
  const column = { flex: 1, width: '100%' as const, maxWidth: L.tablet ? L.maxW : undefined, alignSelf: 'center' as const };

  return (
    <Ctx.Provider value={ctx}>
      <StatusBar style="light" />
      <View style={{ flex: 1, backgroundColor: C.bg }}>
        <View style={{ flex: 1 }}>
          {top ? (
            <View style={[column, { paddingTop: L.top }]}>
              {top.kind === 'set' ? <SetScreen key={top.id} setId={top.id} onBack={pop} /> : null}
              {top.kind === 'card' ? <CardScreen key={top.key} cardKey={top.key} onBack={pop} /> : null}
              {top.kind === 'settings' ? (
                <View style={{ flex: 1 }}>
                  <View style={{ paddingHorizontal: L.gutter, paddingTop: L.sp(6) }}>
                    <Header onBack={pop} title="Settings" right={<Text style={st.mode}>{ctx.modeLabel}</Text>} />
                  </View>
                  <SettingsScreen settings={settings} onChange={changeSettings} onKeyChange={() => refreshKey(settings)} />
                </View>
              ) : null}
            </View>
          ) : null}
          {/* The current tab stays mounted underneath, so a scan in progress isn't lost when you open its card page. */}
          <View style={{ flex: 1, display: top ? 'none' : 'flex' }}>
            {tab === 'scan' ? (
              <ScanScreen settings={settings} apiKey={apiKey} store={store} goSettings={ctx.openSettings} onSaved={() => {}} onBack={() => setTabRaw(prevTab)} onImmersive={setImmersive} paused={!!top} />
            ) : (
              <View style={[column, { paddingTop: ownTop ? 0 : L.top }]}>
                {tab === 'home' && <HomeScreen />}
                {tab === 'explore' && <ExploreScreen searchToken={searchToken} />}
                {tab === 'collection' && <VaultScreen />}
                {tab === 'feed' && <CommunityScreen store={store} />}
              </View>
            )}
          </View>
        </View>
        {hideTabs ? null : (
          <View style={[st.tabs, { height: L.tabBarH, paddingBottom: Math.max(L.bottom, 6) }]}>
            <View style={{ flexDirection: 'row', flex: 1, width: '100%', maxWidth: L.tablet ? 640 : undefined, alignSelf: 'center' }}>
              {TABS.map(([id, icon, label]) => {
                const on = tab === id && !top;
                const color = on ? C.ink : C.ink2;
                if (id === 'scan') {
                  const d = L.sp(46);
                  return (
                    <Pressable key={id} style={st.tab} accessibilityLabel="Scan a card" onPress={() => { setStack([]); setTab('scan'); }}>
                      <View style={[st.scanBtn, { width: d, height: d, borderRadius: L.sp(16), marginTop: -L.sp(12) }]}>
                        <Icon name="plus" size={L.fs(22)} color={C.lime} stroke={2.6} />
                      </View>
                      <Text style={[st.tabText, { fontSize: L.fs(10.5), color }]} numberOfLines={1}>{label}</Text>
                    </Pressable>
                  );
                }
                return (
                  <Pressable key={id} style={st.tab} accessibilityLabel={label} onPress={() => { setStack([]); setTab(id); if (id === 'collection' || id === 'home') refreshVault(); }}>
                    <View style={{ height: L.sp(28), justifyContent: 'center' }}>
                      <Icon name={icon!} size={L.fs(23)} color={color} />
                    </View>
                    <Text style={[st.tabText, { fontSize: L.fs(10.5), color, fontWeight: on ? '800' : '600' }]} numberOfLines={1}>{label}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        )}
      </View>
    </Ctx.Provider>
  );
}

const st = StyleSheet.create({
  mode: { color: C.ink2, fontSize: 11, fontWeight: '800', letterSpacing: 1.2 },
  tabs: { backgroundColor: C.tabBar, paddingTop: 6, paddingHorizontal: 4 },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'flex-start', gap: 3 },
  scanBtn: { borderWidth: 2, borderColor: C.lime, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center' },
  tabText: { fontWeight: '600' },
});
