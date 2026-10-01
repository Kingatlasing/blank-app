// Sports set pull (runs in a sportscardspro.com tab). Resumes on its own: skips sets already in IndexedDB
// 'slabscout' / 'sets'. Status: window.__ss (progress), window.__sl (recent warnings), window.__ls (set lists).
(async () => {
const O = 'https://www.sportscardspro.com';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const PRI = ['basketball', 'soccer', 'baseball', 'football', 'hockey', 'racing', 'wrestling', 'ufc', 'golf', 'tennis', 'boxing'];
window.__ss = {state: 'loading set lists'};
// 1. every set on the site (category page + every brand page), cached in localStorage
let all = null;
try { all = JSON.parse(localStorage.getItem('slabscout-all-sets') || 'null'); } catch (e) {}
if (!all) {
  const grab = async p => {
    for (let t = 0; t < 5; t++) {
      try {
        const r = await fetch(O + p); if (!r.ok) throw r.status;
        const d = new DOMParser().parseFromString(await r.text(), 'text/html');
        const sets = [...new Set([...d.querySelectorAll('a[href*="/console/"]')].map(a => a.getAttribute('href').split('/console/')[1]).filter(Boolean))];
        if (!sets.length) throw 'empty';
        return {sets, brands: [...new Set([...d.querySelectorAll('a')].map(a => a.getAttribute('href') || '').filter(h => h.startsWith('/brand/')))]};
      } catch (e) { await sleep(4000 * (t + 1)); }
    }
    return {sets: [], brands: []};
  };
  all = {};
  for (const sp of PRI) {
    const c = sp + '-cards', g = await grab('/category/' + c), S = new Set(g.sets);
    for (const b of g.brands.filter(b => b.startsWith('/brand/' + c + '/'))) { await sleep(700); (await grab(b)).sets.forEach(s => S.add(s)); }
    all[c] = [...S];
    window.__ls = Object.fromEntries(Object.entries(all).map(([k, v]) => [k, v.length]));
  }
  try { localStorage.setItem('slabscout-all-sets', JSON.stringify(all)); } catch (e) {}
}
const dec = s => { try { return decodeURIComponent(s.replace(/&amp;/g, '&')); } catch (e) { return s.replace(/&amp;/g, '&'); } };
window.__all = all;
window.__todo = [...new Set(Object.values(all).flat().map(dec))].sort((a, b) => PRI.indexOf(a.split('-cards-')[0]) - PRI.indexOf(b.split('-cards-')[0]));
// 2. the worker: 3 lanes, 0.7 s pause per page, 20 s timeout per request, backs off on 429
const W = `
const O='https://www.sportscardspro.com';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const BR=['upper-deck','topps','panini','bowman','donruss','fleer','score','leaf','skybox','hoops','o-pee-chee','pinnacle','playoff','pacific','stadium-club','finest','ultra','select','prizm','mosaic','optic','futera','merlin','press-pass','wheels','sage','onyx','parkside','wild-card'];
const cap=s=>s.split('-').map(w=>w?w[0].toUpperCase()+w.slice(1):w).join(' ');
const title=s=>{const rest=s.includes('-cards-')?s.split('-cards-')[1]:s;return cap(rest).replace(/\\bUd\\b/g,'UD').replace(/\\bSp\\b/g,'SP')};
const brand=s=>{const b=BR.find(x=>s.includes('-'+x));return b?cap(b):''};
const open=()=>new Promise((r,j)=>{const q=indexedDB.open('slabscout');q.onsuccess=()=>r(q.result);q.onerror=()=>j(q.error)});
const money=v=>v?String(v).replace(/[$,]/g,''):'';
let pages=0;
async function page(slug,cursor){
  for(let t=0;t<6;t++){try{
    const ac=new AbortController();const to=setTimeout(()=>ac.abort(),20000);
    const r=await fetch(O+'/console/'+encodeURIComponent(slug),{signal:ac.signal,method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'sort=&when=none&release-date=&cursor='+cursor+'&format=json'});
    if(r.status===404)return {products:[]};
    if(!r.ok)throw new Error('http '+r.status);
    const j=await r.json();clearTimeout(to);pages++;await sleep(700);return j}catch(e){postMessage({warn:String(e),slug});await sleep(3000*(t+1)*(String(e).includes('429')?4:1))}}
  throw new Error('failed '+slug)}
async function one(slug){
  const c=[];let cursor=0;
  for(let p=0;p<300;p++){const j=await page(slug,cursor);const ps=j.products||[];
    for(const x of ps){const im=((x.imageUri||'').match(/images\\.pricecharting\\.com\\/([^/]+)\\//)||[])[1]||'';
      c.push([x.productName,x.productUri,x.printRun?String(x.printRun):'',money(x.price1),money(x.price3),money(x.price2),im])}
    if(ps.length<150||!j.cursor||String(j.cursor)===String(cursor))break;cursor=j.cursor}
  return {title:title(slug),brand:brand(slug),host:'sportscardspro',c}}
onmessage=async e=>{const db=await open();
  const have=new Set(await new Promise(r=>{const q=db.transaction('sets').objectStore('sets').getAllKeys();q.onsuccess=()=>r(q.result)}));
  const todo=e.data.todo.filter(s=>!have.has(s));let i=0,done=0,cards=0,fail=[];const L=e.data.lanes||3;
  setInterval(()=>postMessage({i,done,cards,pages,fail:fail.length,todo:todo.length,have:have.size}),5000);
  async function lane(){while(i<todo.length){const s=todo[i++];
    try{const v=await one(s);cards+=v.c.length;await new Promise(r=>{const t=db.transaction('sets','readwrite');t.objectStore('sets').put(v,s);t.oncomplete=r;t.onerror=r});done++}
    catch(err){fail.push(s)}}}
  await Promise.all(Array.from({length:L},lane));postMessage({i,done,cards,pages,fail:fail.length,failed:fail,finished:true})};
`;
window.__sw && window.__sw.terminate();
const w = new Worker(URL.createObjectURL(new Blob([W], {type: 'text/javascript'})));
window.__sw = w; window.__sl = [];
w.onmessage = e => { if (e.data.warn) { window.__sl.push({...e.data, t: Date.now()}); if (window.__sl.length > 50) window.__sl.shift(); } else window.__ss = {...e.data, t: Date.now()}; };
w.onerror = e => { window.__ss = {err: e.message}; };
w.postMessage({todo: window.__todo, lanes: 3});
})();
