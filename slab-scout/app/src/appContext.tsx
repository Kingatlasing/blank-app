import React, { createContext, useContext } from 'react';
import type { Store, VaultRecord } from './core/community';
import type { Settings } from './types';

export type Tab = 'home' | 'scan' | 'explore' | 'collection' | 'settings';

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
}

export const Ctx = createContext<AppCtx | null>(null);
export const useApp = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error('App context missing');
  return c;
};
