"""Slab Scout scan service: the web app's full scanning engine for the phone app (and the mobile-web test page).

    uvicorn service:app --host 0.0.0.0 --port 7860        (run from the streamlit/ folder)

POST /scan   photo of the front (+ optional back) -> identification, text read (English / Japanese / Korean),
             fingerprint, colours, serial / back checks, slab label, grade estimate, autograph check.
POST /ocr    one photo -> the text lines on the card (English, plus Japanese / Korean when it sees them).
GET  /health is the service awake.

Same code as the Scan page (ui/scan.py), so a photo gets the same answer in both apps. Photos are processed in
memory and never stored.
"""
from __future__ import annotations

import base64
import dataclasses
import io
import os
import re
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
_WARM = os.environ.get("SLABSCOUT_WARM", "1") == "1"

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

import ui.common as common  # noqa: E402
from core import autograph, catalog, colour, community, condition, grading, identify, ocr, pipeline, slab, vision  # noqa: E402

# Shared corrections + community cards when the Supabase keys are set (same as the web app), else a local file
_store = None


def get_store():
    global _store
    if _store is None:
        url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_ANON_KEY", "")
        _store = community.Store(url, key, local_path=os.path.join(tempfile.gettempdir(), "slabscout-service.db"))
    return _store


common.get_store = get_store
import ui.scan as scan  # noqa: E402

scan.get_store = get_store

MAX_BYTES = 15 * 1024 * 1024
TCG = ("Pokémon", "Pokémon Japanese / Korean", "Yu-Gi-Oh!", "Magic: The Gathering", "Lorcana", "One Piece", "Dragon Ball", "Digimon")
SPORTS = ("Sports", "Baseball", "Basketball", "Football", "Soccer", "Hockey", "Racing", "Wrestling", "UFC", "Golf", "Tennis", "Boxing")

app = FastAPI(title="Slab Scout scan service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_lock = threading.Semaphore(2)  # the free host has 2 CPUs: at most two scans at once


def _num(v):
    return None if v is None else round(float(v), 2)


def _b64(img, width: int) -> str:
    return vision.thumbnail_b64(img, width)


def _match(x: dict) -> dict:
    """One candidate as plain JSON."""
    out = {"kind": x["kind"], "score": round(float(x.get("score", 0)), 1), "why": list(x.get("why", []))}
    if x["kind"] == "catalog":
        c = x["card"]
        s = catalog.sets().get(c.set_id, {})
        v, est = catalog.value(c)
        out.update(key=c.key, name=c.name, number=c.number, variant=c.variant or "Base", print_run=c.print_run, set_id=c.set_id,
                   set=s.get("name", ""), year=str(s.get("year", "")), game=s.get("category", ""), price=_num(v), price_estimated=bool(est),
                   psa9=_num(c.psa9), psa10=_num(c.psa10), image_url=catalog.image_url(c, 240)[0] if c.img else "", label=c.label)
    elif x["kind"] == "community":
        r = x["row"]
        out.update(name=r.get("name", ""), number=r.get("number", ""), set=r.get("set_name", ""), variant=r.get("variant", ""),
                   rarity=r.get("rarity", ""), game=r.get("game", ""), year=str(r.get("year", "")), price=None)
    else:
        c = x.get("c") or {}
        out.update(name=c.get("name", ""), number=c.get("number", ""), set=c.get("set", ""), rarity=c.get("rarity", ""),
                   variant=c.get("variant", ""), game=c.get("game", ""), year=str(c.get("year", "")),
                   price=_num((c.get("raw") or {}).get("mid")), currency=c.get("currency", "USD"), image_url=c.get("image_url", ""),
                   ref_id=c.get("ref_id", ""), url=c.get("url", ""), official_distance=c.get("official_distance"))
    return out


def _inspection(insp) -> dict | None:
    if insp is None:
        return None
    return {"subgrades": {k: _num(v) for k, v in insp.subgrades.items()},
            "findings": [dataclasses.asdict(f) if dataclasses.is_dataclass(f) else f for f in insp.findings][:20],
            "photo_ok": insp.photo_ok, "photo_notes": list(insp.photo_notes)}


def _centering_json(c) -> dict | None:
    if not c:
        return None
    return {"left": int(c.left), "right": int(c.right), "top": int(c.top), "bottom": int(c.bottom), "text": c.text(), "worst": int(c.worst())}


def _grade(res: dict, x: dict | None) -> dict:
    """Grade estimate with no person in the loop: same steps as the Scan page (card style, this set's border
    widths, corner shape, inspection of front and back), minus the manual line and checklist adjustments."""
    f, b = res["front"], res.get("back")
    game = res.get("game") or res["parsed"].get("game") or ""
    sid, variant, name, year, number = scan._card_facts(x) if x else ("", "", "", "", "")
    printed = res["parsed"].get("number", "") or ""
    pno, prar = vision.printed_rarity(res["parsed"].get("raw_text", ""))
    printed = printed if "/" in printed else pno
    style = vision.card_style(f"{variant} {prar}".strip(), name, year, printed or number)
    if style == "standard" and vision.looks_full_art(f["card"], f["edges"]):
        style = "full_art"
    prof = catalog.border_profile(sid, variant) if sid else None
    if not prof and sid and (catalog.set_profile(sid) or {}).get("border"):
        sb = catalog.set_profile(sid)
        prof = {"l": sb["border"][0], "r": sb["border"][1], "t": sb["border"][2], "b": sb["border"][3], "n": sb.get("n", 1), "borderless": sb.get("borderless", 0)}
    expect = {k: prof[k] for k in ("l", "r", "t", "b")} if prof and prof.get("n", 0) >= 2 and (prof.get("borderless") or 0) < 0.5 else None
    L = f["edges"]
    if style != "standard" or expect:
        L = vision.find_lines(f["card"], f["found"], expect=expect, style=style)
    front_c = vision.Centering(L["il"] - L["ol"], L["or"] - L["ir"], L["it"] - L["ot"], L["ob"] - L["ib"]) if L else f["centering"]
    off = (x.get("c") or {}).get("_official") if x and x["kind"] == "tcgdb" else None
    rad = condition.corner_radius_px(game, style)
    if sid and style != "vintage":
        rad = catalog.corner_radius_px(sid) or rad  # this set's own corner shape, measured on its photos
    fi = condition.inspect_card(vision.tight_card(f["card"], L), official=off, corner_radius=rad, foil_border=style == "full_art")
    sp = catalog.set_profile(sid) if sid else None
    condition.apply_baseline(fi, (sp or {}).get("sub"))  # this set's design, learned from clean photos
    dco = catalog.die_cut_outline(x["card"]) if x and x["kind"] == "catalog" else None
    if dco:  # die-cut: the points of the shape are the corners; compare the outline with the set's cut
        dcr = condition.die_cut_check(vision.tight_card(f["card"], L), dco["mask"], dco.get("agree", 1.0))
        g_dc = condition._sev_to_grade(dcr["sev"])
        fi.subgrades["corners"] = g_dc
        fi.subgrades["edges"] = min(fi.subgrades["edges"], g_dc)
        fi.findings += [condition.Finding("edges", "die-cut outline", n, dcr["sev"], "possible") for n in dcr["notes"]]
        fi.metrics["die_cut"] = dcr
        style = "die_cut"
    bi = (b or {}).get("inspect")
    subs = {k: min(fi.subgrades[k], bi.subgrades[k]) if bi else fi.subgrades[k] for k in ("corners", "edges", "surface")}
    back_c = b["centering"] if b else None
    g = grading.estimate(front_c.worst() if front_c else None, back_c.worst() if back_c else None, subs["corners"], subs["edges"], subs["surface"],
                         tcg=game not in SPORTS)
    g = {k: (_num(v) if isinstance(v, float) else v) for k, v in g.items()}
    g["corner_radius_px"] = rad
    g["method"] = "automatic inspection"
    g["style"] = style
    g["centering"] = {"front": _centering_json(front_c), "back": _centering_json(back_c)}
    g["caps"] = grading.grader_caps(front_c.worst() if front_c else None, back_c.worst() if back_c else None, tcg=game not in SPORTS)
    g["front"] = _inspection(fi)
    g["back"] = _inspection(bi)
    g["lines"] = {k: round(float(v), 1) for k, v in L.items() if isinstance(v, (int, float))} if L else None
    g["straightened"] = bool((f.get("skew") or {}).get("applied"))
    tips = list(fi.photo_notes) + ([] if b else ["Add a photo of the back: PSA and TAG grade centering, corners and edges on both sides."])
    if not f.get("found"):
        tips.insert(0, "The card's outline wasn't found: lay it flat on a plain, darker background with all four corners showing.")
    if min(f["full"].size) < 700:
        tips.append("Photo is small: take it with the camera, card filling most of the frame, for corners and edges to be judged.")
    g["tips"] = tips
    # how much to trust it: the four things that most often make a photo grade wrong
    issues = sum([not f.get("found"), not fi.photo_ok, min(f["full"].size) < 700, not b])
    g["confidence"] = "high" if issues == 0 else "medium" if issues == 1 else "low"
    g["sharpness"] = fi.metrics.get("sharpness")
    return g


def _read_file(u: UploadFile | None) -> bytes | None:
    if u is None:
        return None
    data = u.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo is over 15 MB")
    return data or None


@app.get("/health")
def health():
    return {"ok": True, "sets": len(catalog.sets())}


@app.get("/")
def root():
    return {"service": "Slab Scout scan service", "endpoints": ["/scan", "/ocr", "/health"]}


def do_ocr(data: bytes, lang: str = "auto") -> dict:
    """Text lines on the card in a photo (English, plus Japanese / Korean when it sees them)."""
    with _lock:
        img = vision.load_image(data)
        card, found = vision.detect_and_crop(img)
        lines = ocr.read_text(card)
        langs = ["en"]
        if lang in ("ja", "ko", "auto") and (lang != "auto" or ocr.has_cjk(lines) or len(re.findall(r"[A-Za-z]{4,}", " ".join(t for t, *_ in lines))) < 5):
            if lang in ("ja", "auto"):
                jl = ocr.read_text_cjk(card)
                if lang == "ja" or any(re.search(r"[぀-ヿ一-鿿]", t) for t, *_ in jl):
                    lines, langs = jl, ["en", "ja"]
            if lang == "ko" or (lang == "auto" and langs == ["en"]):
                kl = ocr.read_text_ko(card)
                if lang == "ko" or any(re.search(r"[가-힣]", t) for t, *_ in kl):
                    lines, langs = kl, ["en", "ko"]
    return {"lines": [t for t, *_ in lines], "boxes": [{"text": t, "conf": round(float(c), 3), "y": round(float(y), 4)} for t, c, y in lines],
            "found": found, "langs": langs}


def do_scan(fdata: bytes, bdata: bytes | None = None, game: str = "Auto", grade: bool = True) -> dict:
    """Everything the Scan page works out for a photo, as plain JSON."""
    t = time.time()
    with _lock:
        res = scan._analyze(fdata, bdata, game or "Auto")
        f = res["front"]
        cands = res.get("cands", [])
        top = cands[0] if cands else None
        out = {
            "is_back": res.get("is_back") or "",
            "game": res.get("game") or res["parsed"].get("game") or "",
            "parsed": {k: v for k, v in res["parsed"].items() if isinstance(v, (str, int, float))},
            "lines": [t_ for t_, *_ in f["lines"]],
            "back_lines": [t_ for t_, *_ in (res.get("back") or {}).get("lines", [])],
            "phash": f["phash"],
            "found": f["found"],
            "matches": [_match(x) for x in cands[:8]],
            "fakes": [{"name": r.get("name", ""), "reasons": r.get("fake_reasons", ""), "distance": r.get("distance")} for r in res.get("fakes", [])],
            "card_jpeg": _b64(f["card"], 420),
        }
        try:
            out["colours"] = colour.describe(colour.signature(vision.tight_card(f["card"], f["edges"])))
        except Exception:
            out["colours"] = ""
        sl = res.get("slab")
        if sl:
            out["slab"] = {k: sl.get(k) for k in ("company", "grade", "label", "cert", "qualifiers", "subgrades", "tag_score", "lookup", "year", "number", "desc")}
            out["slab"]["grade_text"] = slab.grade_text(sl)
            if top:
                out["slab"]["price_at_grade"] = _num(scan._slab_price(top, sl))
        elif grade and not res.get("is_back"):
            try:
                out["grade"] = _grade(res, top)
            except Exception as e:  # never lose the identification over a grading problem
                out["grade"] = {"error": str(e)}
            try:
                _, variant, name, _, _ = scan._card_facts(top) if top else ("", "", "", "", "")
                signed = bool(re.search(r"\bauto(graph)?s?\b|signature|signed", f"{variant} {name}", re.I))
                a = autograph.check(f["card"], res["parsed"].get("raw_text", ""), " ".join(out["back_lines"]), "Autograph" if signed else "")
                if a.get("found") or a.get("certified") or signed:
                    out["autograph"] = {k: v for k, v in a.items() if k in ("found", "kind", "certified", "box", "auto_grade", "notes", "verify")}
            except Exception:
                pass
            if top:
                chosen = top.get("c") if top["kind"] == "tcgdb" else None
                out["authenticity"] = pipeline.authenticity_signals(chosen, res.get("fakes", []), None)
    out["seconds"] = round(time.time() - t, 2)
    return out


@app.post("/ocr")
def read(photo: UploadFile = File(...), lang: str = Form("auto")):
    data = _read_file(photo)
    if not data:
        raise HTTPException(400, "No photo")
    return do_ocr(data, lang)


@app.post("/scan")
def scan_card(front: UploadFile = File(...), back: UploadFile | None = File(None), game: str = Form("Auto"), grade: bool = Form(True)):
    fdata, bdata = _read_file(front), _read_file(back)
    if not fdata:
        raise HTTPException(400, "No photo of the front")
    return do_scan(fdata, bdata, game or "Auto", grade)


def _warm():
    """Load the reading models and the card index in the background so the first scan is quicker."""
    try:
        from PIL import Image
        img = Image.new("RGB", (630, 880), (240, 240, 240))
        ocr.read_text(img)
        ocr.read_text_cjk(img)
        catalog.sets()
        catalog.photo_lookup("0" * 16, max_distance=0)  # picture fingerprints for every game
    except Exception:
        pass


if _WARM:
    threading.Thread(target=_warm, daemon=True).start()
