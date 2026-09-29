"""Shared UI helpers: theme, formatting, stores, settings, card tiles, collection access."""
from __future__ import annotations

import base64
import html
from datetime import date, datetime

import streamlit as st

from core import ai, catalog, community

CSS = """
<style>
.block-container{padding-top:1rem;max-width:820px}
h1,h2,h3{letter-spacing:.01em}
.hero{border-radius:18px;padding:18px 20px;background:linear-gradient(135deg,#1b2029,#161a21);border:1px solid #2a303b}
.hero .lbl{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#9BA4B3}
.hero .big{font-size:40px;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums}
.up{color:#43C47A}.down{color:#F0625F}.muted{color:#9BA4B3}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;background:#20252E;color:#ECEFF4;margin:0 4px 4px 0}
.pill.gold{background:#2B2413;color:#E6B94B}.pill.red{background:#3A1616;color:#F0625F}.pill.green{background:#123524;color:#43C47A}
.tile{border:1px solid #2a303b;background:#161A21;border-radius:14px;padding:10px;height:100%}
.tile .nm{font-weight:700;font-size:14px;line-height:1.25;margin-top:6px}
.tile .sub{font-size:12px;color:#9BA4B3}
.tile .px{font-weight:800;font-size:16px;color:#E6B94B;font-variant-numeric:tabular-nums}
.ph{aspect-ratio:63/88;border-radius:8px;background:linear-gradient(160deg,#20252E,#2a303b);display:flex;align-items:center;justify-content:center;color:#9BA4B3;font-size:12px;text-align:center;padding:6px}
.slab{border:1px solid #343B48;border-radius:12px;padding:6px;background:#1B2029}
.slab-in{border:1px solid #343B48;border-radius:8px;padding:10px 12px;background:#161A21}
.slab-who{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#9BA4B3}
.slab-grade{font-size:42px;font-weight:800;line-height:1.05}
.slab-lbl{font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#ECEFF4}
.slab-sub{font-size:13px;color:#9BA4B3}
.verdict{border-radius:10px;padding:10px 14px;margin:6px 0}
table.ladder{width:100%;border-collapse:collapse;font-size:14px}
table.ladder td,table.ladder th{padding:7px 6px;border-bottom:1px solid #2a303b;text-align:right;font-variant-numeric:tabular-nums}
table.ladder th{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#9BA4B3;font-weight:600}
table.ladder td:first-child,table.ladder th:first-child{text-align:left}
table.ladder tr.me td{color:#FF6A33;font-weight:700}
/* keep card grids and button rows side by side on phones, like a native app */
[data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important;gap:.5rem}
[data-testid="stColumn"]{min-width:0 !important}
.tile .nm{overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
@media (max-width:640px){.hero .big{font-size:34px}.tile{padding:6px}.tile .nm{font-size:12px}.tile .px{font-size:14px}.tile .sub{font-size:10px}}
[data-testid="stImage"] img{max-height:460px;object-fit:contain}
</style>
"""

VERDICTS = {
    "looks_genuine": ("#123524", "#43C47A", "Looks genuine"),
    "unsure": ("#2A2112", "#E3A83E", "Can't confirm, check closely"),
    "likely_fake": ("#3A1616", "#F0625F", "Likely fake"),
    "custom_or_proxy": ("#2A1F33", "#C08BF0", "Custom card or proxy"),
    "not_checked": ("#20252E", "#9BA4B3", "Not checked"),
}


def esc(s) -> str:
    return html.escape(str(s or ""))


def money(v, cur: str = "USD") -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    sym = "€" if cur == "EUR" else "$"
    return f"{sym}{v:,.2f}" if v < 100 else f"{sym}{v:,.0f}"


def grade_color(g) -> str:
    try:
        g = float(g)
    except (TypeError, ValueError):
        return "#9BA4B3"
    return "#43C47A" if g >= 9 else "#E3A83E" if g >= 7 else "#F0625F"


def secrets_get(k: str) -> str:
    try:
        return st.secrets.get(k, "")
    except Exception:
        return ""


@st.cache_resource
def get_store() -> community.Store:
    return community.Store(secrets_get("SUPABASE_URL"), secrets_get("SUPABASE_ANON_KEY"))


def ss():
    return st.session_state


# ---------------- settings (sidebar) ----------------
def settings_sidebar():
    s = st.session_state
    with st.sidebar:
        st.header("Settings")
        st.subheader("Your collection")
        qp = st.query_params.get("vault", "")
        code = st.text_input("Vault code", value=s.get("vault_code", qp), type="password",
                             help="A private code (6+ characters). Use it on any device, or in the phone app, to see the same collection.")
        if code != s.get("vault_code"):
            s.vault_code = code
            s.pop("vault_cache", None)
        if code and len(code) < 6:
            st.warning("Use at least 6 characters.")
        st.divider()
        prov_name = st.selectbox("AI boost", list(ai.PROVIDERS), index=list(ai.PROVIDERS).index(s.get("prov_name", "Off (free, no key)")),
                                 help="Off is free. A free Google Gemini key adds photo ID for any card, an authenticity check and AI grading.")
        s.prov_name = prov_name
        prov = ai.PROVIDERS[prov_name]
        s.ai = None
        if prov:
            default_key = secrets_get({"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}.get(prov["id"], "COMPATIBLE_API_KEY"))
            key = st.text_input("API key", value=s.get("ai_key_" + prov["id"], default_key), type="password")
            s["ai_key_" + prov["id"]] = key
            st.caption(f"[Get a key]({prov['key_url']})" + (" · free, no credit card" if prov["id"] == "gemini" else ""))
            model = st.text_input("Model", value=prov["model"])
            base = st.text_input("Base URL", value="https://openrouter.ai/api/v1") if prov["id"] == "compatible" else ""
            if key and model:
                s.ai = {"prov": prov, "key": key, "model": model, "base": base, "name": prov_name}
        st.divider()
        store = get_store()
        st.caption("Community catalog: " + ("connected (shared)" if store.shared else "this device only"))
        sets_ = catalog.sets()
        st.caption(f"Card database: {len(sets_)} sets · {len(catalog.cards()):,} cards" + (f" · prices from {max((x.get('prices_as_of') or '') for x in sets_.values())}" if sets_ else ""))


def vault_code() -> str:
    c = st.session_state.get("vault_code", "")
    if len(c) >= 6:
        return c
    # Without a shared database, the device's own file is private, so a default code is fine.
    return "" if get_store().shared else "local-device"


def need_code() -> bool:
    """True (and shows a prompt) when a shared database is connected but no vault code is set."""
    if vault_code():
        return False
    st.info("Set a private **vault code** in the menu (top-left ») to start your collection. Use the same code on any device.")
    return True


# ---------------- collection ----------------
def collection(refresh: bool = False) -> list[dict]:
    s = st.session_state
    code = vault_code()
    if refresh or "vault_cache" not in s:
        try:
            s.vault_cache = get_store().vault_list(code)
        except Exception as e:
            st.error(f"Couldn't load your collection: {e}")
            s.vault_cache = []
    return s.vault_cache


def add_to_collection(record: dict, wishlist: bool = False) -> None:
    code = vault_code()
    rec = dict(record)
    rec["list"] = "wishlist" if wishlist else "collection"
    rec.setdefault("added_at", datetime.utcnow().isoformat() + "Z")
    get_store().vault_add(code, rec)
    collection(refresh=True)


def remove_from_collection(card_id: str) -> None:
    get_store().vault_delete(vault_code(), card_id)
    collection(refresh=True)


def current_value(rec: dict) -> float:
    """Latest catalog price when the card is linked to the catalog, else the price saved at scan time."""
    key = (rec.get("match") or {}).get("catalog_key")
    if key:
        c = catalog_card(key)
        v = catalog.value(c)[0] if c else None
        if v:
            return v
    try:
        return float(((rec.get("pricing") or {}).get("raw") or {}).get("mid") or 0)
    except (TypeError, ValueError):
        return 0.0


@st.cache_data(show_spinner=False)
def _card_map() -> dict:
    return {c.key: i for i, c in enumerate(catalog.cards())}


def catalog_card(key: str):
    i = _card_map().get(key)
    return catalog.cards()[i] if i is not None else None


def record_from_catalog(c, thumb: str = "", extra: dict | None = None) -> dict:
    s = catalog.sets().get(c.set_id, {})
    t = catalog.tier(c) or {}
    rec = {
        "v": 1,
        "card": {"game": s.get("category", ""), "name": c.name, "set": s.get("name", ""), "number": c.number, "year": s.get("year", ""),
                 "brand": s.get("brand", ""), "rarity": (c.variant or "Base") + (f" /{c.print_run}" if c.print_run else ""),
                 "variant": c.variant, "card_type": "Parallel" if c.variant else "Base"},
        "grade": {}, "authenticity": {"verdict": "not_checked", "reasons": []},
        "pricing": {"raw": {"low": None, "mid": catalog.value(c)[0], "high": None}, "currency": "USD", "note": f"{s.get('source','')} sold-listing price ({s.get('prices_as_of','')})",
                    "graded_label": "PSA 10", "graded_mid": c.psa10, "priced_at": datetime.utcnow().isoformat() + "Z"},
        "match": {"source": "catalog", "catalog_key": c.key, "url": catalog.price_url(c), "image_url": ""},
        "thumb": thumb, "phash": "", "print_run": c.print_run, "odds": t.get("odds", ""),
    }
    if extra:
        rec.update(extra)
    return rec


def portfolio_history(total: float) -> list[dict]:
    """Keeps one value point per day for the portfolio chart."""
    store = get_store()
    code = vault_code()
    try:
        hist = store.history_list(code)
        today = date.today().isoformat()
        if not hist or hist[-1]["day"] != today or abs(hist[-1]["value"] - total) > 0.005:
            store.history_add(code, today, total)
            hist = store.history_list(code)
        return hist
    except Exception:
        return [{"day": date.today().isoformat(), "value": total}]


# ---------------- tiles ----------------
def thumb_html(b64: str | None, label: str = "") -> str:
    if b64:
        return f'<img src="data:image/jpeg;base64,{b64}" style="width:100%;aspect-ratio:63/88;object-fit:cover;border-radius:8px">'
    return f'<div class="ph">{esc(label)[:40]}</div>'


def tile(title: str, sub: str, price: str, thumb: str | None = None, pills: str = "") -> str:
    return (f'<div class="tile">{thumb_html(thumb, title)}<div class="nm">{esc(title)}</div>'
            f'<div class="sub">{esc(sub)}</div><div>{pills}</div><div class="px">{price}</div></div>')


def price_label(c) -> str:
    """Catalog card price for tiles; '~' marks the parallel's typical price when the exact card hasn't sold."""
    v, est = catalog.value(c)
    return ("~" if est else "") + money(v) if v else "—"


def rarity_pill(print_run) -> str:
    if not print_run:
        return ""
    cls = "red" if print_run <= 5 else "gold" if print_run <= 25 else ""
    return f'<span class="pill {cls}">{"1 of 1" if print_run == 1 else f"/{print_run}"}</span>'


def open_card(key: str):
    st.session_state.card_key = key
    st.switch_page(st.session_state.pages["card"])


def open_set(set_id: str):
    st.session_state.set_id = set_id
    st.switch_page(st.session_state.pages["set"])
