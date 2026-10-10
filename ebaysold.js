// eBay sold listings for a list of searches (runs in a www.ebay.com tab, the user's own signed-in browser).
// One search page every ~8 s; keeps each sold listing's title, price, date, photo and item id.
// Stops (state 'check') if eBay shows its bot check; never tries to get past it.
// Status: window.__es ; results: localStorage 'slabscout-ebay-ns' {set id: {q, items: {item id: {t,p,d,img}}}}
(async () => {
const LIST = window.__ELIST;
const KEY = window.__EKEY || 'slabscout-ebay-ns';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let store = {};
try { store = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
const doneKey = KEY + '-saved';  // sets already saved to a part file (when saving in parts)
let saved = new Set();
try { saved = new Set(JSON.parse(localStorage.getItem(doneKey) || '[]')); } catch (e) {}
// save what's collected as a file (slabscout-ebay-ns-<part>.json.gz) and clear it from the tab's storage
async function savePart() {
  const n = (window.__EPARTNO = (window.__EPARTNO || window.__EPART) + 0);
  const out = JSON.stringify({sets: store, fetched_at: new Date().toISOString()});
  const gz = await new Response(new Blob([out]).stream().pipeThrough(new CompressionStream('gzip'))).blob();
  const a = document.createElement('a'); a.href = URL.createObjectURL(gz); a.download = 'slabscout-ebay-ns-' + n + '.json.gz';
  document.body.appendChild(a); a.click();
  Object.keys(store).forEach(k => saved.add(k));
  try { localStorage.setItem(doneKey, JSON.stringify([...saved])); } catch (e) {}
  store = {}; window.__EPARTNO = n + 1;
  window.__es.parts = (window.__es.parts || []).concat(['slabscout-ebay-ns-' + n + '.json.gz']);
}
const todo = (await fetch(LIST).then(r => r.json())).filter(x => !store[x.set] && !saved.has(x.set));
window.__es = {state: 'running', todo: todo.length, done: 0, items: 0};
for (const x of todo) {
  const items = {};
  for (let pg = 1; pg <= 3; pg++) {
    const url = '/sch/i.html?_nkw=' + encodeURIComponent(x.q) + '&LH_Sold=1&LH_Complete=1&_ipg=240&_pgn=' + pg;
    let h = '';
    try { const r = await fetch(url, {credentials: 'include'}); h = await r.text(); } catch (e) { await sleep(30000); continue; }
    if (/Pardon Our Interruption|captcha|Checking your browser/i.test(h.slice(0, 20000))) {
      window.__es = {...window.__es, state: 'check', at: x.q};
      try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) {}
      return;  // eBay wants a human check: stop and let the user handle it
    }
    const d = new DOMParser().parseFromString(h, 'text/html');
    const lis = [...d.querySelectorAll('ul.srp-results > li')];
    let n = 0;
    for (const li of lis) {
      const t = ((li.querySelector('.s-card__title') || {}).textContent || '').replace(/Opens in a new window or tab/, '').trim();
      const p = ((li.querySelector('.s-card__price') || {}).textContent || '').trim();
      const dd = ((li.querySelector('.s-card__caption') || {}).textContent || '').replace(/^\s*Sold\s*/, '').trim();
      const a = li.querySelector('a[href*="/itm/"]');
      const id = a ? ((a.getAttribute('href').match(/\/itm\/(\d+)/) || [])[1] || '') : '';
      const im = li.querySelector('img');
      let img = im ? (im.getAttribute('src') || im.getAttribute('data-src') || '') : '';
      if (!/^https:\/\/i\.ebayimg\.com\//.test(img)) img = '';
      if (!id || !p || !t || /^Shop on eBay$/i.test(t)) continue;
      items[id] = {t: t.slice(0, 250), p, d: dd.slice(0, 40), img};
      n++;
    }
    await sleep(8000);
    if (n < 200) break;
  }
  store[x.set] = {q: x.q, items};
  window.__es.done++; window.__es.items += Object.keys(items).length;
  if (window.__EPART && Object.keys(store).length >= (window.__EPARTN || 120)) await savePart();
  try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) { window.__es.state = 'storage full'; return; }
}
if (window.__EPART && Object.keys(store).length) await savePart();
window.__es.state = 'done';
})();
