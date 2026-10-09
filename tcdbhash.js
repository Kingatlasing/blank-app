// TCDB photo fingerprints (runs in a www.tcdb.com tab, next to tcdb.js). Same maths as hasher.js; ids are
// 'td:<set id>-<card id>' for every TCDB card whose checklist row has a photo (front scan of that exact card,
// never another card's). Results -> IndexedDB 'slabscout-color' (this origin) store 'r'; failures -> 'bad'.
// Status: window.__hs. Re-run to pick up sets downloaded since.
(async () => {
const W = `
const URL_OF=id=>{const m=id.match(/^td:(\\d+)-(\\d+)$/);return '/Images/Cards/'+(self.SP||'Non-Sport')+'/'+m[1]+'/'+m[1]+'-'+m[2]+'Fr.jpg'};let O='';
let db;
const open=()=>new Promise(r=>{const q=indexedDB.open('slabscout-color',1);q.onupgradeneeded=()=>{q.result.createObjectStore('r');q.result.createObjectStore('bad')};q.onsuccess=()=>r(q.result)});
function cells(px,w,h,cw,ch,x0,y0,x1,y1){ // exact box filter (fractional edges) = PIL/cv2 area resize
  const out=new Float64Array(cw*ch*3);const sx=(x1-x0)/cw,sy=(y1-y0)/ch;
  for(let j=0;j<ch;j++){const ya=y0+j*sy,yb=ya+sy;
   for(let i=0;i<cw;i++){const xa=x0+i*sx,xb=xa+sx;let r=0,g=0,b=0,n=0;
    for(let y=Math.floor(ya);y<Math.ceil(yb);y++){const wy=Math.min(yb,y+1)-Math.max(ya,y);if(wy<=0)continue;
     for(let x=Math.floor(xa);x<Math.ceil(xb);x++){const wx=Math.min(xb,x+1)-Math.max(xa,x);if(wx<=0)continue;const ww=wx*wy,o=(y*w+x)*4;r+=px[o]*ww;g+=px[o+1]*ww;b+=px[o+2]*ww;n+=ww}}
    const k=(j*cw+i)*3;out[k]=r/n;out[k+1]=g/n;out[k+2]=b/n}}return out}
const C=new Float64Array(32*32);for(let u=0;u<32;u++)for(let x=0;x<32;x++)C[u*32+x]=Math.cos(Math.PI*(2*x+1)*u/64);
function phash(px,w,h){
  const x0=Math.floor(w*0.08),y0=Math.floor(h*0.06),x1=Math.floor(w*0.92),y1=Math.floor(h*0.94);
  const c=cells(px,w,h,32,32,x0,y0,x1,y1);const g=new Float64Array(1024);
  for(let k=0;k<1024;k++)g[k]=(299*c[k*3]+587*c[k*3+1]+114*c[k*3+2])/1000;
  const t=new Float64Array(8*32); // rows DCT: t[u][y]
  for(let u=0;u<8;u++)for(let y=0;y<32;y++){let s=0;for(let x=0;x<32;x++)s+=g[y*32+x]*C[u*32+x];t[u*32+y]=s}
  const d=[];for(let v=0;v<8;v++)for(let u=0;u<8;u++){let s=0;for(let y=0;y<32;y++)s+=t[u*32+y]*C[v*32+y];d.push(s)}
  // d is [v][u] = row v (vertical freq), col u
  const srt=[...d].sort((a,b)=>a-b);const med=(srt[31]+srt[32])/2;
  let hex='';for(let i=0;i<64;i+=4){let n=0;for(let k=0;k<4;k++)n=n*2+(d[i+k]>med?1:0);hex+=n.toString(16)}return hex}
function colour(px,w,h){
  const CW=24,CH=34,c=cells(px,w,h,CW,CH,0,0,w,h);
  const ring=[0,0,0],cen=[0,0,0];let nr=0,nc=0;const hist=new Float64Array(12);let vx=0,vy=0,vw=0;
  for(let j=0;j<CH;j++)for(let i=0;i<CW;i++){const k=(j*CW+i)*3,r=c[k],g=c[k+1],b=c[k+2];
    const L=(r+g+b)/3,A=r-g,B=(r+g)/2-b,ch=Math.hypot(A,B);
    const isR=i<2||i>=CW-2||j<2||j>=CH-2;
    if(isR){ring[0]+=L;ring[1]+=A;ring[2]+=B;nr++}else{cen[0]+=L;cen[1]+=A;cen[2]+=B;nc++}
    if(ch>25){const hu=Math.atan2(B,A);hist[Math.floor((hu+Math.PI)/(2*Math.PI)*12)%12]+=ch;
      if(isR){vx+=Math.cos(hu)*ch;vy+=Math.sin(hu)*ch;vw+=ch}}}
  const q=(v)=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0');
  const enc=(m,n)=>q(m[0]/n)+q(m[1]/n/2+128)+q(m[2]/n/2+128);
  const mx=Math.max(...hist);let hh='';for(const v of hist)hh+=(mx>0?Math.round(15*v/mx):0).toString(16);
  const spread=vw>0?1-Math.hypot(vx,vy)/vw:0;
  return enc(ring,nr)+enc(cen,nc)+hh+q(spread*255)}
async function one(id){
  const ac=new AbortController();const to=setTimeout(()=>ac.abort(),20000);const r=await fetch(O+URL_OF(id),{signal:ac.signal});await new Promise(r=>setTimeout(r,250));if(!r.ok)throw new Error('http '+r.status);clearTimeout(to);
  const bm=await createImageBitmap(await r.blob());const w=bm.width,h=bm.height;
  const cv=new OffscreenCanvas(w,h);const x=cv.getContext('2d');x.drawImage(bm,0,0);bm.close();
  const px=x.getImageData(0,0,w,h).data;return [phash(px,w,h),colour(px,w,h)]}
onmessage=async(e)=>{
  db=await open();const ids=e.data.ids;O=e.data.origin;
  
  const has=async(st,list)=>{const out=new Set();for(let s=0;s<list.length;s+=5000){const ch=list.slice(s,s+5000);await new Promise(r=>{const t=db.transaction(st);const o=t.objectStore(st);for(const id of ch){const q=o.getKey(id);q.onsuccess=()=>{if(q.result!==undefined)out.add(id)}}t.oncomplete=r});postMessage({state:'checking',at:s,total:list.length})}return out};const done=await has('r',ids);const bad=await has('bad',ids);
  const todo=ids.filter(i=>!done.has(i)&&!bad.has(i));let i=0,ok=0,fail=0,buf=[],bbuf=[];
  const flush=()=>{if(!buf.length&&!bbuf.length)return;const t=db.transaction(['r','bad'],'readwrite');
    for(const [k,v] of buf)t.objectStore('r').put(v,k);for(const k of bbuf)t.objectStore('bad').put(1,k);buf=[];bbuf=[]};
  postMessage({total:ids.length,todo:todo.length,ok,fail});
  async function lane(){while(i<todo.length){const id=todo[i++];
    let tries=0;for(;;){try{buf.push([id,await one(id)]);ok++;break}catch(err){if(++tries>=3||String(err).includes('http 404')){bbuf.push(id);fail++;break}await new Promise(r=>setTimeout(r,1500))}}
    if(buf.length+bbuf.length>=200){flush();postMessage({total:ids.length,todo:todo.length,ok,fail,at:i})}}}
  await Promise.all(Array.from({length:4},lane));flush();postMessage({total:ids.length,todo:todo.length,ok,fail,at:i,finished:true})};
`;
window.__hw && window.__hw.terminate();
window.__hs = {state: 'reading checklists'};
const db = await new Promise((r, j) => { const q = indexedDB.open('slabscout-tcdb2', 1); q.onupgradeneeded = () => q.result.createObjectStore('sets'); q.onsuccess = () => r(q.result); q.onerror = () => j(q.error); });
const ids = [];
await new Promise(r => { const q = db.transaction('sets').objectStore('sets').openCursor(); q.onsuccess = () => { const c = q.result; if (!c) return r(); for (const card of c.value.cards) if (card[4]) ids.push('td:' + c.value.sid + '-' + card[0]); c.continue(); }; });
const w = new Worker(URL.createObjectURL(new Blob([W], {type: 'text/javascript'})));
window.__hw = w;
w.onmessage = e => { window.__hs = {...e.data, t: Date.now()}; };
w.onerror = e => { window.__hs = {err: e.message}; };
w.postMessage({ids, origin: location.origin});
})();
