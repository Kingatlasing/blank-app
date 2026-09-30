"""Live centering tool: drag the card-edge and inner-border lines (or tap the corners) and the
L/R, T/B split and PSA centering cap update live as you move. Works with mouse and touch.

Two sets of lines:
  - blue dashed = the card's outer edge (starts at the photo edge, because the photo is already straightened)
  - orange      = the inner border (where the artwork frame starts)
"""
from __future__ import annotations

import base64
import io

import streamlit as st
from PIL import Image

from core import vision

_HTML = """
<div class="cen">
  <div class="bar">
    <button data-mode="drag" class="on">Drag lines</button>
    <button data-mode="tap">Tap corners</button>
    <button data-act="grid" class="on">Grid</button>
    <button data-act="reset" class="ghost">Re-detect</button>
  </div>
  <div class="status"></div>
  <div class="hint"></div>
  <div class="stage"><img alt="card"/><svg></svg></div>
  <div class="nudge">
    <span class="sel">Tap a line to select it</span>
    <button data-n="-5">«</button><button data-n="-1">‹</button><button data-n="1">›</button><button data-n="5">»</button>
  </div>
  <input class="slide" type="range" min="0" max="630" step="1" value="0" disabled aria-label="Move the selected line"/>
  <div class="read"><div><b class="lr">—</b><span>left / right</span></div><div><b class="tb">—</b><span>top / bottom</span></div><div><b class="cap">—</b><span>PSA centering cap</span></div></div>
</div>
"""

_CSS = """
.cen{font-family:inherit;color:var(--st-text-color);display:flex;flex-direction:column;gap:8px}
.bar{display:flex;gap:6px;flex-wrap:wrap}
.bar button,.nudge button{border:1px solid rgba(128,128,128,.35);background:var(--st-secondary-background-color);color:inherit;border-radius:999px;padding:6px 12px;font-weight:700;font-size:13px;cursor:pointer}
.bar button.on{background:var(--st-primary-color);border-color:var(--st-primary-color);color:#140A05}
.bar .ghost{margin-left:auto}
.hint{font-size:13px;opacity:.8;min-height:54px}
.stage{position:relative;width:100%;max-width:420px;margin:0 auto;touch-action:none;user-select:none}
.stage img{width:100%;display:block;border-radius:6px}
.stage svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.nudge{display:flex;gap:6px;align-items:center;justify-content:center;flex-wrap:wrap}
.nudge .sel{font-size:13px;opacity:.85;margin-right:4px}
.slide{width:100%;accent-color:var(--st-primary-color);height:28px}
.status{font-size:12px;opacity:.75}
.read{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.read div{background:var(--st-secondary-background-color);border-radius:10px;padding:8px 10px;display:flex;flex-direction:column}
.read b{font-size:20px;font-variant-numeric:tabular-nums}
.read span{font-size:11px;opacity:.7;text-transform:uppercase;letter-spacing:.06em}
"""

_JS = r"""
export default function (component) {
  const { data, parentElement, setStateValue } = component;
  const root = parentElement.querySelector('.cen');
  const img = root.querySelector('img');
  const svg = root.querySelector('svg');
  const hint = root.querySelector('.hint');
  const selLabel = root.querySelector('.sel');
  const W = data.w, H = data.h;
  const NS = 'http://www.w3.org/2000/svg';
  // PSA front centering caps: grade -> max larger side %
  const CAPS = [[10,55],[9,60],[8,65],[7,70],[6,80],[5,85],[4,85],[3,90],[2,95],[1,100]];

  if (img.getAttribute('src') !== data.img) img.setAttribute('src', data.img);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio', 'none');

  // state lives on the root so re-renders during a drag don't reset it
  const st = root.__st || (root.__st = { mode: 'drag', sel: null, tapStep: 0 });
  if (!st.dragging) {
    st.v = { ol: data.v.ol, ot: data.v.ot, or: data.v.or, ob: data.v.ob, il: data.v.il, it: data.v.it, ir: data.v.ir, ib: data.v.ib };
  }
  const v = st.v;

  const LINES = {
    ol: ['x', 'outer', 'Card edge · left'], or: ['x', 'outer', 'Card edge · right'],
    ot: ['y', 'outer', 'Card edge · top'], ob: ['y', 'outer', 'Card edge · bottom'],
    il: ['x', 'inner', 'Border · left'], ir: ['x', 'inner', 'Border · right'],
    it: ['y', 'inner', 'Border · top'], ib: ['y', 'inner', 'Border · bottom'],
  };

  function split(a, b) {
    const t = Math.max(a + b, 0.0001);
    const p = Math.round(a / t * 100);
    return [p, 100 - p];
  }
  function clampAll() {
    v.ol = Math.max(0, Math.min(v.ol, v.il - 1)); v.il = Math.min(v.il, v.ir - 10);
    v.or = Math.min(W, Math.max(v.or, v.ir + 1));
    v.ot = Math.max(0, Math.min(v.ot, v.it - 1)); v.it = Math.min(v.it, v.ib - 10);
    v.ob = Math.min(H, Math.max(v.ob, v.ib + 1));
  }
  const slide = root.querySelector('.slide');
  function syncSlide() {
    if (!st.sel) { slide.disabled = true; return; }
    slide.disabled = false;
    slide.max = LINES[st.sel][0] === 'x' ? W : H;
    slide.value = Math.round(v[st.sel]);
  }
  root.querySelector('.status').textContent = data.status || '';
  function readout() {
    const L = v.il - v.ol, R = v.or - v.ir, T = v.it - v.ot, B = v.ob - v.ib;
    const lr = split(L, R), tb = split(T, B);
    const worst = Math.max(...lr, ...tb);
    const cap = (CAPS.find(([, m]) => worst <= m) || [1])[0];
    root.querySelector('.lr').textContent = `${lr[0]}/${lr[1]}`;
    root.querySelector('.tb').textContent = `${tb[0]}/${tb[1]}`;
    const c = root.querySelector('.cap');
    c.textContent = cap === 10 ? '10 ✓' : `max ${cap}`;
    c.style.color = cap >= 9 ? '#43C47A' : cap >= 7 ? '#E3A83E' : '#F0625F';
  }
  function draw() {
    svg.innerHTML = '';
    const sw = W / 260;
    // shade the border area
    const shade = document.createElementNS(NS, 'path');
    shade.setAttribute('d', `M${v.ol} ${v.ot}H${v.or}V${v.ob}H${v.ol}Z M${v.il} ${v.it}V${v.ib}H${v.ir}V${v.it}Z`);
    shade.setAttribute('fill', 'rgba(255,106,51,.12)');
    shade.setAttribute('fill-rule', 'evenodd');
    svg.appendChild(shade);
    if (st.grid !== false) {
      // alignment mesh: a 6 x 8 grid spanning the card edge, plus the centre lines of the card (blue) and of the
      // inner frame (orange). On a perfectly centred card the two centre lines sit on top of each other.
      const mk = (x1, y1, x2, y2, col, w, dash) => {
        const l = document.createElementNS(NS, 'line');
        Object.entries({ x1, y1, x2, y2 }).forEach(([a, b]) => l.setAttribute(a, b));
        l.setAttribute('stroke', col); l.setAttribute('stroke-width', w);
        if (dash) l.setAttribute('stroke-dasharray', dash);
        l.style.pointerEvents = 'none';
        svg.appendChild(l);
      };
      const gw = (v.or - v.ol) / 6, gh = (v.ob - v.ot) / 8;
      for (let i = 1; i < 6; i++) mk(v.ol + gw * i, v.ot, v.ol + gw * i, v.ob, 'rgba(255,255,255,.28)', sw * 0.6);
      for (let i = 1; i < 8; i++) mk(v.ol, v.ot + gh * i, v.or, v.ot + gh * i, 'rgba(255,255,255,.28)', sw * 0.6);
      const cxo = (v.ol + v.or) / 2, cyo = (v.ot + v.ob) / 2, cxi = (v.il + v.ir) / 2, cyi = (v.it + v.ib) / 2;
      mk(cxo, v.ot, cxo, v.ob, '#4FA8FF', sw * 0.9, `${sw * 2} ${sw * 2}`);
      mk(v.ol, cyo, v.or, cyo, '#4FA8FF', sw * 0.9, `${sw * 2} ${sw * 2}`);
      mk(cxi, v.it, cxi, v.ib, '#FF6A33', sw * 0.9);
      mk(v.il, cyi, v.ir, cyi, '#FF6A33', sw * 0.9);
      // corner brackets on the card edge (where each corner should sit)
      const b = Math.min(gw, gh) * 0.6;
      [[v.ol, v.ot, 1, 1], [v.or, v.ot, -1, 1], [v.ol, v.ob, 1, -1], [v.or, v.ob, -1, -1]].forEach(([x, y, dx, dy]) => {
        mk(x, y, x + dx * b, y, '#FFFFFF', sw * 1.4); mk(x, y, x, y + dy * b, '#FFFFFF', sw * 1.4);
      });
    }
    for (const [k, [axis, kind]] of Object.entries(LINES)) {
      const pos = v[k];
      const [x1, y1, x2, y2] = axis === 'x' ? [pos, 0, pos, H] : [0, pos, W, pos];
      const vis = document.createElementNS(NS, 'line');
      Object.entries({ x1, y1, x2, y2 }).forEach(([a, b]) => vis.setAttribute(a, b));
      const col = kind === 'outer' ? '#4FA8FF' : '#FF6A33';
      vis.setAttribute('stroke', st.sel === k ? '#FFFFFF' : col);
      vis.setAttribute('stroke-width', st.sel === k ? sw * 1.8 : sw);
      if (kind === 'outer') vis.setAttribute('stroke-dasharray', `${sw * 4} ${sw * 3}`);
      svg.appendChild(vis);
      if (st.mode === 'drag') {
        const hit = document.createElementNS(NS, 'line');
        Object.entries({ x1, y1, x2, y2 }).forEach(([a, b]) => hit.setAttribute(a, b));
        hit.setAttribute('stroke', 'transparent');
        hit.setAttribute('stroke-width', sw * 14);
        hit.style.cursor = axis === 'x' ? 'ew-resize' : 'ns-resize';
        hit.dataset.k = k;
        svg.appendChild(hit);
      }
    }
    // tap-mode markers
    (st.taps || []).forEach(([x, y]) => {
      const c = document.createElementNS(NS, 'circle');
      c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('r', sw * 5);
      c.setAttribute('fill', '#FFFFFF'); c.setAttribute('stroke', '#FF6A33'); c.setAttribute('stroke-width', sw);
      svg.appendChild(c);
    });
    readout();
    selLabel.textContent = st.sel ? LINES[st.sel][2] : 'Tap a line to select it';
    syncSlide();
  }
  function toPoint(e) {
    const r = svg.getBoundingClientRect();
    return [(e.clientX - r.left) / r.width * W, (e.clientY - r.top) / r.height * H];
  }
  function commit() {
    setStateValue('lines', { ...v });
  }
  const TAP_STEPS = [
    'Tap the card’s TOP-LEFT outer corner',
    'Tap the card’s BOTTOM-RIGHT outer corner',
    'Tap the TOP-LEFT corner of the inner border (where the art frame starts)',
    'Tap the BOTTOM-RIGHT corner of the inner border',
  ];
  function setHint() {
    hint.textContent = st.mode === 'tap'
      ? `Step ${st.tapStep + 1} of 4: ${TAP_STEPS[st.tapStep]}`
      : 'Lines were placed automatically. Drag any line (or tap it and use the slider) to adjust: orange = inner border, blue dashed = card edge. Grid: when the orange and blue centre lines overlap, the card is perfectly centred.';
  }

  // one-time listeners (the component function re-runs on every Streamlit rerun)
  if (!root.__wired) {
    root.__wired = true;
    svg.addEventListener('pointerdown', (e) => {
      if (st.mode === 'tap') {
        const [x, y] = toPoint(e);
        st.taps = [...(st.taps || []), [x, y]];
        if (st.tapStep === 0) { v.ol = x; v.ot = y; }
        if (st.tapStep === 1) { v.or = x; v.ob = y; }
        if (st.tapStep === 2) { v.il = x; v.it = y; }
        if (st.tapStep === 3) { v.ir = x; v.ib = y; }
        clampAll();
        st.tapStep += 1;
        if (st.tapStep >= 4) { st.tapStep = 0; st.taps = []; st.mode = 'drag'; syncButtons(); commit(); }
        setHint(); draw();
        return;
      }
      const k = e.target.dataset && e.target.dataset.k;
      if (!k) return;
      st.sel = k; st.dragging = k;
      svg.setPointerCapture(e.pointerId);
      e.preventDefault();
      draw();
    });
    svg.addEventListener('pointermove', (e) => {
      if (!st.dragging) return;
      const [x, y] = toPoint(e);
      const k = st.dragging;
      v[k] = LINES[k][0] === 'x' ? Math.max(0, Math.min(W, x)) : Math.max(0, Math.min(H, y));
      clampAll();
      draw();
    });
    const end = () => { if (st.dragging) { st.dragging = null; commit(); } };
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointercancel', end);
    root.querySelectorAll('.bar [data-mode]').forEach((b) => b.addEventListener('click', () => {
      st.mode = b.dataset.mode; st.tapStep = 0; st.taps = []; syncButtons(); setHint(); draw();
    }));
    root.querySelector('[data-act=grid]').addEventListener('click', (e) => {
      st.grid = st.grid === false; e.currentTarget.classList.toggle('on', st.grid !== false); draw();
    });
    root.querySelector('[data-act=reset]').addEventListener('click', () => {
      Object.assign(v, data.auto); st.sel = null; st.tapStep = 0; st.taps = []; draw(); commit();
    });
    slide.addEventListener('input', () => {  // live while sliding
      if (!st.sel) return;
      v[st.sel] = Number(slide.value); clampAll(); draw();
    });
    slide.addEventListener('change', () => commit());
    root.querySelectorAll('.nudge [data-n]').forEach((b) => b.addEventListener('click', () => {
      if (!st.sel) return;
      v[st.sel] += Number(b.dataset.n);
      clampAll(); draw(); commit();
    }));
  }
  function syncButtons() {
    root.querySelectorAll('.bar [data-mode]').forEach((b) => b.classList.toggle('on', b.dataset.mode === st.mode));
  }
  syncButtons(); setHint(); draw();
}
"""

_component = st.components.v2.component("slab_centering", html=_HTML, css=_CSS, js=_JS)


def _data_url(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _auto_lines(card: Image.Image, auto: vision.Centering | None, edges: dict | None = None) -> dict:
    if edges:
        return {k: int(edges[k]) for k in ("ol", "ot", "or", "ob", "il", "it", "ir", "ib")}
    w, h = card.size
    a = auto or vision.Centering(round(w * 0.06), round(w * 0.06), round(h * 0.05), round(h * 0.05))
    return {"ol": 0, "ot": 0, "or": w, "ob": h, "il": a.left, "it": a.top, "ir": w - a.right, "ib": h - a.bottom}


def _to_centering(lines: dict) -> vision.Centering:
    return vision.Centering(
        max(1, round(lines["il"] - lines["ol"])), max(1, round(lines["or"] - lines["ir"])),
        max(1, round(lines["it"] - lines["ot"])), max(1, round(lines["ob"] - lines["ib"])),
    )


def current(card: Image.Image, auto: vision.Centering | None, key: str, edges: dict | None = None) -> vision.Centering:
    """The centering currently set in the tool (or the automatic placement), without drawing anything."""
    return _to_centering(st.session_state.get(f"_cenlines_{key}") or _auto_lines(card, auto, edges))


def centering_tool(card: Image.Image, auto: vision.Centering | None, key: str, edges: dict | None = None) -> vision.Centering:
    """Shows the interactive tool and returns the centering the person set (border widths in px)."""
    w, h = card.size
    auto_lines = _auto_lines(card, auto, edges)
    found = (edges or {}).get("found") or {}
    missing = [k for k, ok in found.items() if not ok]
    status = ("Auto-placed: card edges and inner border found on all four sides." if edges and not missing else
              f"Auto-placed, but no clear border on the {', '.join(missing)} (full-art card?). Set those lines yourself." if edges else "")
    skey = f"_cenlines_{key}"
    img_key = f"_cenimg_{key}"
    if img_key not in st.session_state:
        st.session_state[img_key] = _data_url(card)

    def _changed():
        val = (st.session_state.get(key) or {}).get("lines")
        if val:
            st.session_state[skey] = val

    lines = st.session_state.get(skey, auto_lines)
    _component(key=key, data={"img": st.session_state[img_key], "w": w, "h": h, "v": lines, "auto": auto_lines, "status": status},
               on_lines_change=_changed)
    return _to_centering(st.session_state.get(skey, auto_lines))
