import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';
import { File, Paths } from 'expo-file-system';
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

/* ---------- profile (name, photo, cover): this phone only ---------- */
export interface Profile {
  name: string;
  /** local file uri of the profile photo */
  avatar: string;
  /** local file uri of the cover image */
  cover: string;
}
const PROFILE_KEY = 'slabscout.profile.v1';
export const EMPTY_PROFILE: Profile = { name: '', avatar: '', cover: '' };

export async function loadProfile(): Promise<Profile> {
  try {
    return { ...EMPTY_PROFILE, ...JSON.parse((await AsyncStorage.getItem(PROFILE_KEY)) || '{}') };
  } catch {
    return EMPTY_PROFILE;
  }
}
export async function saveProfile(p: Profile) {
  await AsyncStorage.setItem(PROFILE_KEY, JSON.stringify(p));
}

/** Copy a picked photo into the app's documents folder so it survives cache clean-ups (falls back to the picked uri). */
export async function keepPhoto(uri: string, name: 'avatar' | 'cover', previous = ''): Promise<string> {
  try {
    const ext = (/\.(jpe?g|png|heic|webp)(\?|$)/i.exec(uri)?.[1] || 'jpg').toLowerCase();
    const dst = new File(Paths.document, `profile-${name}-${Date.now()}.${ext}`);
    await new File(uri).copy(dst);
    if (previous && previous.includes('/profile-')) {
      try {
        new File(previous).delete();
      } catch {}
    }
    return dst.uri;
  } catch {
    return uri;
  }
}
