// Card checklists from article pages (TraderCracks, Cardboard Connection, Beckett...). Runs in a tab of the site:
// window.__CLURLS = [same-site article urls]; result window.__cl = {state, sets: {slug: {title, url, rows: [[name, number, section, print run]]}}}.
// Rows are numbered lines ('S1 Homer Simpson', '01 Title Card', 'CB02 Morty Smith #/25') under the section heading they follow.
(async () => {
const sleep = ms => new Promise(r => setTimeout(r, ms));
window.__cl = {state: 'running', done: 0, sets: {}};
const NUM = /^\s*(?:#\s*)?([A-Z]{0,5}-?[A-Z]{0,3}\d{1,3}[a-zA-Z]?)\s*[.:)\-–—]?\s+(.{2,120})$/;
for (const u of window.__CLURLS) {
  try {
    const h = await fetch(u).then(r => r.text());
    const d = new DOMParser().parseFromString(h, 'text/html');
    const art = d.querySelector('.set-checklist') || d.querySelector('.entry-content, article .entry-content, article, .post-content, main') || d.body;
    const rows = [];
    let section = 'Base Set';
    const walk = el => {
      for (const n of el.children) {
        const tag = n.tagName;
        if (/^(SCRIPT|STYLE|NOSCRIPT|FIGURE|IMG|ASIDE|NAV|FORM|IFRAME)$/.test(tag)) continue;
        const txt = (n.innerText || n.textContent || '').trim();
        if (/^H[1-6]$/.test(tag) || (tag === 'P' && n.children.length === 1 && /^(STRONG|B)$/.test(n.children[0].tagName) && txt.length < 90 && !NUM.test(txt))) {
          if (txt && !/buy on ebay|shop now|shop on|related|share this|comments?|advertis|subscribe|you may also|popular|newsletter/i.test(txt)) section = txt.replace(/\s*(checklist|card list)\s*$/i, '').replace(/\s+/g, ' ').trim();
          continue;
        }
        if (/^(DIV|SPAN|UL|OL|TABLE|TBODY|TR|TD|SECTION)$/.test(tag) && [...n.children].some(c => !/^(BR|STRONG|B|EM|I|A|SPAN)$/.test(c.tagName))) { walk(n); continue; }
        const raw = (n.innerHTML || '').split(/<br\s*\/?>|\n/i);
        for (const r of raw) {
          const p = r.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&#8217;|&rsquo;/g, "'").replace(/&nbsp;/g, ' ').trim();
          if (!p) continue;
          if (/^\s*<(strong|b)\b/i.test(r) && !NUM.test(p) && p.length < 90) {  // bold line at the top of a paragraph: a section name
            if (!/buy on ebay|shop now|shop on|related|share this|comments?|advertis|subscribe|you may also|popular|newsletter/i.test(p)) section = p.replace(/\s*(checklist|card list)\s*$/i, '').replace(/\s+/g, ' ').trim();
            continue;
          }
          const m = p.match(NUM);
          if (!m || /^\d+\s+(cards?|packs?|boxes|per)\b/i.test(p)) continue;
          let name = m[2].trim(), pr = '';
          const s = name.match(/#?\s*\/\s*(\d{1,5})\b/);
          if (s) { pr = s[1]; name = name.replace(s[0], '').trim(); }
          rows.push([name.replace(/\s+-\s*$/, ''), m[1], section, pr]);
        }
      }
    };
    walk(art);
    window.__cl.sets[u.split('/').filter(Boolean).pop()] = {title: d.title.replace(/\s*(Checklist|Trading Cards?).*$/i, '').replace(/[|–-]\s*$/, '').trim(), url: u, rows};
  } catch (e) { window.__cl.sets[u] = {err: String(e)}; }
  window.__cl.done++;
  await sleep(2500);
}
window.__cl.state = 'done';
})();
