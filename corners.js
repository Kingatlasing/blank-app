// Runs in a storage.googleapis.com tab. Measures how round each set's corners are from its price-guide photos:
// for each corner, the background showing between the photo's corner and the card along the diagonal gives the
// corner radius (gap = r * (sqrt2 - 1)). Results -> IndexedDB 'slabscout-corners' store 'r' {imageId: [tl,tr,bl,br]}
// as radius / card width * 1000 (-1 = could not measure). window.__cs = progress. window.__CLIST = url of
// {set: [imageIds]} (default corner-todo.json on the work branch).
(() => {
const W = `
const ORIGIN='https://storage.googleapis.com/images.pricecharting.com/';
const open=()=>new Promise(r=>{const q=indexedDB.open('slabscout-corners',1);q.onupgradeneeded=()=>{q.result.createObjectStore('r');q.result.createObjectStore('bad')};q.onsuccess=()=>r(q.result)});
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1],a[2]-b[2]);
function px(d,w,x,y){const o=(y*w+x)*4;return [d[o],d[o+1],d[o+2]]}
function avg(list){const s=[0,0,0];for(const p of list){s[0]+=p[0];s[1]+=p[1];s[2]+=p[2]}return s.map(v=>v/list.length)}
function med(list){const r=[0,1,2].map(i=>list.map(p=>p[i]).sort((a,b)=>a-b)[list.length>>1]);return r}
// one corner, in a frame where (0,0) is the photo corner and +x / +y run along the two edges
function corner(d,w,h,fx,fy){
  const P=(x,y)=>px(d,w,fx?w-1-x:x,fy?h-1-y:y);
  const bg=avg([P(0,0),P(1,0),P(0,1),P(1,1)]);
  // the card's own colour along both edges, 25-40% of the way along, 2 px in
  const card=med([...Array(8)].flatMap((_,i)=>[P(Math.round(w*(0.25+i*0.02)),2),P(2,Math.round(h*(0.25+i*0.02)))]));
  if(dist(bg,card)<45) return -1;            // card and background look alike: can't tell where the card starts
  // the photo must be cropped to the card: the edges near the corner are card-coloured, not background
  const e1=P(Math.round(w*0.12),1),e2=P(1,Math.round(h*0.12));
  if(dist(e1,bg)<dist(e1,card)||dist(e2,bg)<dist(e2,card)) return -1;
  const lim=Math.round(w*0.12);let dgap=0;
  for(let k=0;k<lim;k++){const p=P(k,k);if(dist(p,bg)<dist(p,card)) dgap=k+1; else break}
  if(dgap>=lim) return -1;
  return Math.round(dgap/0.4142/w*1000);
}
async function one(id){
  const ac=new AbortController();const to=setTimeout(()=>ac.abort(),20000);const r=await fetch(ORIGIN+id+'/240.jpg',{signal:ac.signal});if(!r.ok)throw new Error('http '+r.status);clearTimeout(to);
  const bm=await createImageBitmap(await r.blob());const w=bm.width,h=bm.height;
  const cv=new OffscreenCanvas(w,h);const x=cv.getContext('2d');x.drawImage(bm,0,0);bm.close();
  const d=x.getImageData(0,0,w,h).data;return [corner(d,w,h,0,0),corner(d,w,h,1,0),corner(d,w,h,0,1),corner(d,w,h,1,1),w,h]}
onmessage=async(e)=>{
  const db=await open();const ids=e.data.ids;
  const done=new Set(await new Promise(r=>{const q=db.transaction('r').objectStore('r').getAllKeys();q.onsuccess=()=>r(q.result)}));
  const bad=new Set(await new Promise(r=>{const q=db.transaction('bad').objectStore('bad').getAllKeys();q.onsuccess=()=>r(q.result)}));
  const todo=ids.filter(i=>!done.has(i)&&!bad.has(i));let i=0,ok=0,fail=0,buf=[],bbuf=[];
  const flush=()=>{if(!buf.length&&!bbuf.length)return;const t=db.transaction(['r','bad'],'readwrite');
    for(const [k,v] of buf)t.objectStore('r').put(v,k);for(const k of bbuf)t.objectStore('bad').put(1,k);buf=[];bbuf=[]};
  postMessage({total:ids.length,todo:todo.length,ok,fail});
  async function lane(){while(i<todo.length){const id=todo[i++];
    let tries=0;for(;;){try{buf.push([id,await one(id)]);ok++;break}catch(err){if(++tries>=3||String(err).includes('http 404')){bbuf.push(id);fail++;break}await new Promise(r=>setTimeout(r,1500))}}
    if(buf.length+bbuf.length>=200){flush();postMessage({total:ids.length,todo:todo.length,ok,fail,at:i})}}}
  await Promise.all(Array.from({length:8},lane));flush();postMessage({total:ids.length,todo:todo.length,ok,fail,at:i,finished:true})};
`;
if (window.__TEST) { window.__cornerW = W; return; }
window.__cw && window.__cw.terminate();
window.__cs = {state: 'loading list'};
(async () => {
  const list = await (await fetch(window.__CLIST || 'https://raw.githubusercontent.com/Kingatlasing/blank-app/slab-scout-work/corner-todo.json')).json();
  window.__cset = list;
  const ids = [...new Set(Object.values(list).flat())];
  const w = new Worker(URL.createObjectURL(new Blob([W], {type: 'text/javascript'})));
  window.__cw = w;
  w.onmessage = e => { window.__cs = {...e.data, t: Date.now()}; };
  w.onerror = e => { window.__cs = {err: e.message}; };
  w.postMessage({ids});
})();
})();
