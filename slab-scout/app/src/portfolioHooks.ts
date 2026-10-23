/** Collection totals + daily value history, shared by Discover and the Collection Insights tab. */
import { useEffect, useMemo, useState } from 'react';
import { useApp } from './appContext';
import { currentValue, inCollection, today } from './core/portfolio';

export function useCollection() {
  const app = useApp();
  const items = useMemo(() => app.vault.filter(inCollection), [app.vault]);
  const total = useMemo(() => items.reduce((s, r) => s + currentValue(r), 0), [items]);
  return { items, total };
}

/** Loads the value history and records today's total (one point per day). */
export function useValueHistory(total: number) {
  const app = useApp();
  const [hist, setHist] = useState<{ day: string; value: number }[]>([]);
  useEffect(() => {
    if (app.needsCode || app.vaultLoading) return;
    let live = true;
    (async () => {
      try {
        let h = await app.store.historyList(app.settings.vaultCode);
        const last = h[h.length - 1];
        if (!last || last.day !== today() || Math.abs(last.value - total) > 0.005) {
          await app.store.historyAdd(app.settings.vaultCode, today(), total);
          h = await app.store.historyList(app.settings.vaultCode);
        }
        if (live) setHist(h);
      } catch {
        if (live) setHist([{ day: today(), value: total }]);
      }
    })();
    return () => {
      live = false;
    };
  }, [total, app.needsCode, app.vaultLoading, app.store, app.settings.vaultCode]);
  return hist;
}
