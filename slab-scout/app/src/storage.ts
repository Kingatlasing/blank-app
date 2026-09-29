import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';
import { PROVIDERS } from './providers';
import type { ProviderId, Settings } from './types';

const SETTINGS_KEY = 'slabscout.settings.v2';
const extra = (Constants.expoConfig?.extra || {}) as { supabaseUrl?: string; supabaseAnonKey?: string };

export const DEFAULT_SETTINGS: Settings = {
  provider: 'off',
  models: Object.fromEntries(PROVIDERS.map((p) => [p.id, p.defaultModel])) as Record<ProviderId, string>,
  compatibleBaseUrl: 'https://openrouter.ai/api/v1',
  supabaseUrl: extra.supabaseUrl || '',
  supabaseKey: extra.supabaseAnonKey || '',
  vaultCode: '',
};

export async function loadSettings(): Promise<Settings> {
  try {
    const raw = await AsyncStorage.getItem(SETTINGS_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const s = JSON.parse(raw);
    return {
      ...DEFAULT_SETTINGS,
      ...s,
      models: { ...DEFAULT_SETTINGS.models, ...(s.models || {}) },
      supabaseUrl: s.supabaseUrl || DEFAULT_SETTINGS.supabaseUrl,
      supabaseKey: s.supabaseKey || DEFAULT_SETTINGS.supabaseKey,
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}
export async function saveSettings(s: Settings) {
  await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
}

/** API keys live in the phone's secure keychain, one per provider. */
export const getApiKey = async (p: ProviderId | 'off') => (p === 'off' ? '' : (await SecureStore.getItemAsync(`apikey_${p}`)) || '');
export const setApiKey = async (p: ProviderId, key: string) =>
  key ? SecureStore.setItemAsync(`apikey_${p}`, key.trim()) : SecureStore.deleteItemAsync(`apikey_${p}`);
