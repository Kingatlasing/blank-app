import React, { createContext, useContext } from 'react';
import type { Store, VaultRecord } from './core/community';
import type { Settings } from './types';
import type { Profile } from './storage';

export type Tab = 'home' | 'collection' | 'scan' | 'feed' | 'explore' | 'settings';

export interface AppCtx {
  settings: Settings;
  store: Store;
  vault: VaultRecord[];
  vaultLoading: boolean;
  vaultErr: string;
  needsCode: boolean;
  refreshVault: () => Promise<void>;
  addRecord: (rec: Omit<VaultRecord, 'id'>, list?: 'collection' | 'wishlist') => Promise<void>;
  removeRecord: (id: string) => Promise<void>;
  openSet: (id: string) => void;
  openCard: (key: string) => void;
  goTab: (t: Tab) => void;
  /** open Explore with the search box focused */
  openSearch: () => void;
  /** 'FREE' | 'AI BOOST' | 'ADD KEY' */
  modeLabel: string;
  openSettings: () => void;
  /** name / photo / cover shown on Discover and Collection (this phone only) */
  profile: Profile;
  setProfile: (p: Profile) => void;
  /** display name: the profile name, else "My Collection" */
  displayName: string;
}

export const Ctx = createContext<AppCtx | null>(null);
export const useApp = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error('App context missing');
  return c;
};
