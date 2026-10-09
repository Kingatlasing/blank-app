// TCDB non-sport pull (runs in a www.tcdb.com tab). Resumes on its own: sets already saved in IndexedDB
// 'slabscout-tcdb2' / 'sets' are skipped. Status: window.__ts; warnings: window.__tl.
// Phase 1: every non-sport set, year by year (cached in localStorage 'slabscout-tcdb-sets').
// Phase 2: each set's checklist (card id, number, name, notes, has-photo), parsed in a worker so a hidden tab
// isn't throttled. One request at a time with a pause between, backing off on 429 / 403 / Cloudflare pages.
(async () => {
const SP = window.__TSP || 'Non-Sport';
const Y0 = window.__TY0 || 1850, Y1 = window.__TY1 || new Date().getFullYear() + 1;
window.__ts = {state: 'starting'};
const W = `
const SP='${SP}';const O='${location.origin}';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const open=()=>new Promise((r,j)=>{const q=indexedDB.open('slabscout-tcdb2',1);q.onupgradeneeded=()=>{q.result.createObjectStore('sets')};q.onsuccess=()=>r(q.result);q.onerror=()=>j(q.error)});
const txt=h=>h.replace(/<figcaption[\\s\\S]*?<\\/figcaption>/g,' ').replace(/<br\\s*\\/?>/g,' ').replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&').replace(/&#39;|&rsquo;/g,"'").replace(/&quot;/g,'"').replace(/\\s+/g,' ').trim();
const notesOf=h=>[...h.matchAll(/<figcaption[^>]*>([\\s\\S]*?)<\\/figcaption>/g)].map(m=>txt(m[1])).join(' ; ');
let reqs=0,pause=8000;const MINP=8000;
async function get(p){
  for(let t=0;t<8;t++){try{
    const ac=new AbortController();const to=setTimeout(()=>ac.abort(),25000);
    const r=await fetch(O+p,{signal:ac.signal,credentials:'include'});clearTimeout(to);
    if(r.status===404)return '';
    const h=await r.text();
    if(r.status===429||r.status===403||/<title>Just a moment/i.test(h.slice(0,3000))){postMessage({warn:'slow down '+r.status,p});pause=Math.min(pause*1.5,30000);await sleep(300000*(t+1));continue}
    if(!r.ok)throw new Error('http '+r.status);
    reqs++;await sleep(pause);if(pause>MINP)pause=Math.max(MINP,pause*0.98);return h}
  catch(e){postMessage({warn:String(e),p});await sleep(5000*(t+1))}}
  throw new Error('failed '+p)}
function rowsOf(h,sid){
  const out=[];
  for(const tr of h.split(/<tr[\\s>]/).slice(1)){
    const body=tr.split(/<\\/tr>/)[0];
    const m=body.match(/ViewCard\\.cfm\\/sid\\/(\\d+)\\/cid\\/(\\d+)\\//);if(!m||m[1]!==String(sid))continue;
    const tds=body.split(/<td(?=[\\s>])/).slice(1).map(x=>x.slice(x.indexOf('>')+1).split(/<\\/td>/)[0]);
    const img=(body.match(/(?:data-original|src)="([^"]*(?:Thumb\\.jpg|AddImage\\.gif)[^"]*)"/)||[])[1]||'';
    let num='',name='',notes='';
    for(let i=0;i<tds.length;i++){const td=tds[i];
      if(!num&&/ViewCard\\.cfm/.test(td)&&!/<img/.test(td)&&txt(td)){num=txt(td);
        for(let k=i+1;k<tds.length;k++){if(txt(tds[k])){name=txt(tds[k].split(/<figcaption/)[0]);notes=notesOf(tds[k]);break}}break}}
    out.push([+m[2],num,name,notes,/Thumb\\.jpg/.test(img)?1:0])}
  return out}
async function one(s){
  const [sid,slug]=s;const cards=[];const seen=new Set();
  for(let pg=1;pg<=60;pg++){
    const h=await get('/Checklist.cfm/sid/'+sid+'/'+slug+(pg>1?'?PageIndex='+pg:''));
    const rs=rowsOf(h,sid).filter(r=>!seen.has(r[0]));
    rs.forEach(r=>{seen.add(r[0]);cards.push(r)});
    if(rs.length<100)break}
  return {sid,slug,title:s[2],year:s[3],sp:SP,cards}}
onmessage=async e=>{
  const db=await open();
  const have=new Set(await new Promise(r=>{const q=db.transaction('sets').objectStore('sets').getAllKeys();q.onsuccess=()=>r(q.result)}));
  const todo=e.data.sets.filter(s=>!have.has(s[0]));let i=0,done=0,cards=0,photos=0,fail=[];
  setInterval(()=>postMessage({i,done,cards,photos,reqs,pause,fail:fail.length,todo:todo.length,have:have.size}),5000);
  async function lane(){while(i<todo.length){const s=todo[i++];
    try{const v=await one(s);cards+=v.cards.length;photos+=v.cards.filter(c=>c[4]).length;
      await new Promise(r=>{const t=db.transaction('sets','readwrite');t.objectStore('sets').put(v,s[0]);t.oncomplete=r;t.onerror=r});done++}
    catch(err){fail.push(s[0])}}}
  await Promise.all(Array.from({length:e.data.lanes||1},lane));
  postMessage({i,done,cards,photos,reqs,fail:fail.length,failed:fail,finished:true})};
`;
// Phase 1: the set list, year by year (main page: DOMParser), cached
const LS = 'slabscout-tcdb-sets-' + SP;
let sets = null;
try { sets = JSON.parse(localStorage.getItem(LS) || 'null'); } catch (e) {}
if (!sets) {
  sets = [];
  const seen = new Set();
  for (let y = Y1; y >= Y0; y--) {
    window.__ts = {state: 'listing sets', year: y, sets: sets.length};
    let h = '';
    for (let t = 0; t < 5; t++) {
      try { const r = await fetch('/ViewAll.cfm/sp/' + SP + '/year/' + y); h = await r.text(); if (r.ok && !/Just a moment/.test(h.slice(0, 3000))) break; } catch (e) {}
      await new Promise(r => setTimeout(r, 20000 * (t + 1)));
    }
    const d = new DOMParser().parseFromString(h, 'text/html');
    for (const a of d.querySelectorAll('a[href*="/ViewSet.cfm/sid/"]')) {
      const m = (a.getAttribute('href') || '').match(/ViewSet\.cfm\/sid\/(\d+)\/([^/?#]+)/);
      if (!m || seen.has(+m[1])) continue;
      seen.add(+m[1]);
      sets.push([+m[1], m[2], a.textContent.trim(), y]);
    }
  }
  try { localStorage.setItem(LS, JSON.stringify(sets)); } catch (e) {}
}
window.__tsets = sets;
const PRIO = window.__TPRIO || /simpson|rick-and-morty|stranger-things|futurama|family-guy|spongebob|x-files|lord-of-the-rings|jurassic|star-trek|ghostbusters|back-to-the-future|alien|predator|terminator|batman|superman|dc-|marvel|star-wars|garbage-pail|wacky-packages|harry-potter|game-of-thrones|walking-dead|breaking-bad|the-office|seinfeld|friends|south-park|scooby|looney|teenage-mutant|transformers|g-i-joe|he-man|masters-of-the-universe/i;
const ordered = [...sets].sort((a, b) => (PRIO.test(b[1]) - PRIO.test(a[1])) || (b[3] - a[3]));
window.__tl = [];
window.__tw && window.__tw.terminate();
const w = new Worker(URL.createObjectURL(new Blob([W], {type: 'text/javascript'})));
window.__tw = w;
w.onmessage = e => { if (e.data.warn) { window.__tl.push({...e.data, t: Date.now()}); if (window.__tl.length > 50) window.__tl.shift(); } else window.__ts = {...e.data, sets: sets.length, t: Date.now()}; };
w.onerror = e => { window.__ts = {err: e.message}; };
w.postMessage({sets: ordered, lanes: window.__TLANES || 1});
})();
