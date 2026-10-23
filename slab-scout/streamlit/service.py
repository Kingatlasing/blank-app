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
from core import autograph, catalog, colour, community, condition, gradebench, grading, identify, ocr, pipeline, refdiff, slab, vision  # noqa: E402

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


def photo_check(f: dict, fi, res: dict, rc: dict | None = None) -> dict:
    """Can this photo show the card's condition well enough for an accurate grade? If not, what to fix. The grade is
    still worked out (best effort) for anyone who wants it anyway."""
    reasons = []
    if not f.get("found"):
        reasons.append("The card's edges weren't found. Lay it flat on a plain, darker background with all four corners in the frame.")
    if min(f["full"].size) < 700:
        reasons.append("The photo is too small to see corners and edges. Use the camera (no zoom, no screenshot) with the card filling most of the frame.")
    sharp = fi.metrics.get("sharpness")
    if sharp is not None and sharp < 60:
        reasons.append("The photo is blurry. Hold the phone steady, add light, and tap the card to focus.")
    if (fi.metrics.get("glare_pct") or 0) > 3:
        reasons.append("There's glare on the card. Tilt it slightly away from the light so reflections don't hide the surface.")
    if res.get("_in_slab"):
        reasons.append("The card is inside a slab, so the plastic hides wear. The label grade is the official one; take the card out for a raw grade.")
    hidden = [k for k in ("left", "right", "top", "bottom") if rc and k not in rc.get("measured", [])]
    if hidden:
        reasons.append(f"The {', '.join(hidden)} edge is covered (fingers, sleeve or glare). Show the whole card.")
    ok = not reasons
    return {"ok": ok, "reasons": reasons,
            "message": "" if ok else "This photo can't show the card's condition clearly, so a grade from it may be off. "
                                     "Take a better photo for an accurate grade, or grade it anyway for a best guess."}


REF_SURFACE_LIVE = False  # turned on once fitted against real grades (core/gradebench results)
REF_WEAR_LIVE = False
REF_MIN_PX = 600  # clean picture at least this many pixels on its short side to judge surface against it


def _grade_extras(res: dict, f: dict, b: dict | None, subs: dict, defects: list, rad: int) -> dict | None:
    """Use the optional grading photos: each finding becomes a named defect at the companies' rubric level and caps
    its subgrade. Corner close-ups replace the whole-card corner reading for that corner (they see far more)."""
    import io
    from PIL import Image
    from core import tagmeasure
    ex = res.get("_extras") or {}
    if not ex:
        return None
    out: dict = {}
    def img(k):
        try:
            return Image.open(io.BytesIO(ex[k])).convert("RGB")
        except Exception:
            return None
    # surface from tilted photos
    tilts = [("front", k, f) for k in ("tilt_front", "tilt_front_2", "tilt_front_3", "tilt_front_4")] + \
            [("back", k, b) for k in ("tilt_back", "tilt_back_2")]
    for side, key, base in tilts:
        if key in ex and base and base.get("full") is not None:
            t = tagmeasure.tilt_surface(base["full"], img(key)) if img(key) else None
            out[key] = t
            for d in tagmeasure.tilt_defects(t, side):
                d["cap"] = grading.defect_cap(d["kind"], d["level"], side)
                d["what"] = grading.DEFECTS[d["kind"]]["what"]
                d["sure"] = "likely"
                d["area"] = "surface"
                defects.append(d)
                subs["surface"] = min(subs["surface"], d["cap"])
    # corners from close-ups
    rmm = rad / 630 * 63.0 if rad is not None else 3.0
    cl = []
    for side, prefix, base in (("front", "corner_", f), ("back", "back_corner_", b)):
        for c in ("tl", "tr", "bl", "br"):
            k = prefix + c
            if k in ex and base and base.get("full") is not None and img(k):
                r = tagmeasure.corner_closeup(base["full"], img(k), c, rmm)
                out[k] = r
                if r and r.get("matched") and r.get("outline"):
                    cl.append((side, c, r))
    if cl:
        # whitening over all close-up corners, scaled to eight corners, against the caps fitted on TAG's grades
        tot = sum((r.get("fray_mm2") or 0) for _, _, r in cl) * 8 / len(cl)
        wcap = tagmeasure.whitening_cap(tot)
        out["corner_whitening_mm2"] = round(tot, 2)
        if wcap < 10:
            defects.append({"kind": "corner_whitening", "level": "several corners, visible", "side": "both", "cap": wcap,
                            "what": f"whitening at the corners ({tot:.1f} mm2 over eight corners)", "sure": "likely", "area": "corners", "source": "corner close-ups"})
        caps = [wcap] if wcap < 10 else []
        for side, c, r in cl:
            for d in tagmeasure.corner_defects(r, side):
                d["cap"] = grading.defect_cap(d["kind"], d["level"], side)
                d["what"] = grading.DEFECTS[d["kind"]]["what"]
                d["sure"] = "likely"
                d["area"] = "corners"
                d["where"] = f"{side} {c}"
                defects.append(d)
                caps.append(d["cap"])
        # close-ups seen and clean: the corner reading comes from them, not from the whole-card photo
        subs["corners"] = min(caps) if caps else max(subs["corners"], 9.5)
        out["corners_from_closeups"] = len(cl)
    return out


def _tm_slim(m: dict | None) -> dict | None:
    """The TAG-style measurement without bulky per-pixel detail."""
    if not m:
        return None
    return {"outline": m.get("outline"), "px_per_mm": m.get("px_per_mm"), "summary": m.get("summary"),
            "corners": m.get("corners"), "edges": m.get("edges")}


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
    if style in ("standard", "vintage"):
        # plain printed border: measure it by its colour (matches TAG's measured centering to ~1.5 points on 110
        # graded cards; the edge finder alone was often caught by name bars and art frames)
        try:
            Lc = vision.border_by_colour(f["card"], expect)
        except Exception:
            Lc = None
        if Lc and Lc.get("spread", 99) < 8:
            L = Lc
    front_c = vision.Centering(L["il"] - L["ol"], L["or"] - L["ir"], L["it"] - L["ot"], L["ob"] - L["ib"]) if L else f["centering"]
    off = (x.get("c") or {}).get("_official") if x and x["kind"] == "tcgdb" else None
    # factory corner shape: the set's own (published / measured on its clean photos), else what this photo clearly
    # shows, else the game's / era's standard - a square-cut card is never judged as rounded, nor the reverse
    try:
        from core import learn
        corner_meas = learn.corner_radius(f["card"])
    except Exception:
        corner_meas = None
    rad, corner_kind, corner_src = condition.factory_corner(catalog.corner_radius_px(sid) if sid else None, corner_meas, game, style)
    fi = condition.inspect_card(vision.tight_card(f["card"], L), official=off, corner_radius=rad, foil_border=style == "full_art")
    sp = catalog.set_profile(sid) if sid else None
    condition.apply_baseline(fi, (sp or {}).get("sub"))  # this set's design, learned from clean photos
    # the card against a clean picture of the same card: scratches / scuffs anywhere (artwork and foil too), and the
    # border's last millimetre against the border just inside it (wear / whitening), above this set's own baseline
    tight = vision.tight_card(f["card"], L)
    ref_cmp, wear, ref = None, None, None
    try:
        ref = scan._ref_image(x) if x else None
        if ref is not None:
            ref_cmp = refdiff.compare(tight, ref)
    except Exception:
        ref_cmp = None
    try:
        # against the clean picture too when the card was lined up with it (full art / borderless have no plain border)
        aligned = ref_cmp is not None and bool(f.get("recut")) and ref is not None
        wear = gradebench.border_wear(tight, radius=rad, ref=ref if aligned else None)
    except Exception:
        wear = None
    # surface against the clean picture only when the photo can show it: big and sharp enough, card not behind
    # slab plastic (reflections read as scuffs), and the clean picture lined up well
    sharp = fi.metrics.get("sharpness")
    can_see = min(tight.size) >= 450 and (sharp is None or sharp >= 60) and not res.get("_in_slab")
    # calibration on 200+ graded cards showed the whole-card scuff / scratch numbers track lighting and print
    # differences, not damage (PSA 10s at 27% "scuffed"), so they are recorded but don't lower the grade yet
    ref_hi = ref is not None and min(ref.size) >= REF_MIN_PX  # small price-guide pictures can't show fine surface
    if (REF_SURFACE_LIVE or ref_hi) and can_see and ref_cmp and ref_cmp.get("ok") and ref_cmp.get("agree", 0) >= 0.5 and ref_cmp.get("glare_pct", 0) < 8:
        sg = grading.surface_from_reference(ref_cmp["surface_sev"])
        if sg < fi.subgrades["surface"]:
            fi.findings.append(condition.Finding("surface", "front", f"Compared with a clean copy of this card: {ref_cmp['scratch_mm']:.0f} mm of "
                                                 f"scratch lines, {ref_cmp['damage_pct']:.1f}% of the surface marked, {ref_cmp['scuff_pct']:.1f}% scuffed / dulled",
                                                 ref_cmp["surface_sev"]))
        fi.subgrades["surface"] = min(fi.subgrades["surface"], sg)
    usable = wear and min(tight.size) >= 300 and (
        ((wear.get("plain_sides") or 0) >= 2 and style in ("standard", "vintage")) or ((REF_WEAR_LIVE or (ref is not None and min(ref.size) >= REF_MIN_PX)) and wear.get("vs_reference")))
    if usable:
        base = (sp or {}).get("wear") or {}
        cks = [k for k in ("tl", "tr", "bl", "br") if k in wear]
        eks = [k for k in ("top", "bottom", "left", "right") if k in wear]
        if cks:
            cw = max(max(0.0, wear[k] - base.get(k, 0)) for k in cks)
            fi.subgrades["corners"] = min(fi.subgrades["corners"], grading.corners_from_wear(cw))
        if eks:
            ew = max(max(0.0, wear[k] - base.get(k, 0)) for k in eks)
            fi.subgrades["edges"] = min(fi.subgrades["edges"], grading.edges_from_wear(ew))
    if wear:
        fi.metrics["border_wear"] = wear
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
    subs_raw = {k: min(fi.subgrades[k], bi.subgrades[k]) if bi else fi.subgrades[k] for k in ("corners", "edges", "surface")}
    # back edge whitening: measured on Pokemon's blue back only - fitted there on TAG grades; MTG's brown back and
    # printed sports backs read as "whitening" even on clean cards (tested on 99 TAG-graded MTG / sports cards)
    bw = None
    wb_cap = 10.0
    if b and b.get("card") is not None and not res.get("_in_slab") and "pok" in (game or "").lower():
        try:
            bw = gradebench.back_edge_whitening(b["card"])
        except Exception:
            bw = None
        if bw:
            wb_cap = gradebench.back_whitening_cap(bw["sum"])
            if bi and wb_cap < 10:
                bi.findings.append(condition.Finding("edges", "back edges", f"Whitening along the back edges ({bw['sum']:.0f}/1000 of the edge band)", min(1.0, bw["sum"] / 600)))
    subs = dict(subs_raw)
    # the companies' defect rubric (grading.DEFECTS): each likely defect caps its subgrade at the rubric's limit
    defects = grading.findings_to_defects(fi.findings, "front") + (grading.findings_to_defects(bi.findings, "back") if bi else [])
    for d in defects:
        if d["sure"] == "likely" and d["cap"] < subs.get(d["area"], 10):
            subs[d["area"]] = d["cap"]
    # extra grading photos: tilted toward one light (surface relief) and corner close-ups (grader-level corners)
    extra_out = _grade_extras(res, f, b, subs, defects, rad)
    # how much the photo inspection is trusted (grading.EVIDENCE): on 159 TAG-graded cards its corner / edge / surface
    # readings barely tracked the real grade, so they only nudge a typical grade; measured whitening still caps
    subs = {k: grading.weigh_evidence(v) for k, v in subs.items()}
    subs["edges"] = min(subs["edges"], wb_cap)
    back_c = b["centering"] if b else None
    if b and b.get("card") is not None:
        try:
            Lb = vision.border_by_colour(b["card"])
        except Exception:
            Lb = None
        if Lb and Lb.get("spread", 99) < 8:
            back_c = vision.Centering(Lb["il"] - Lb["ol"], Lb["or"] - Lb["ir"], Lb["it"] - Lb["ot"], Lb["ob"] - Lb["ib"])
    g = grading.estimate(front_c.worst() if front_c else None, back_c.worst() if back_c else None, subs["corners"], subs["edges"], subs["surface"],
                         tcg=game not in SPORTS)
    g = {k: (_num(v) if isinstance(v, float) else v) for k, v in g.items()}
    # the card's format (die-cut, relic, mini, plate, square corners...) changes what is judged and who grades it
    cs = catalog.corner_shape(sid) if sid else None
    fmt = grading.card_format(variant, name, style, rad)
    if fmt == "standard" and (corner_kind == "square" or (cs and cs.get("shape") == "square")):
        fmt = "square"
    fd = grading.CARD_FORMATS.get(fmt, {})
    g["format"] = fmt
    g["format_notes"] = list(fd.get("notes", []))
    for comp in fd.get("not_graded_by", []):
        if comp in (g.get("graders") or {}):
            g["graders"][comp] = {"grade": "", "label": f"{comp} doesn't grade {fd['what'].split(' (')[0]} cards", "note": "not eligible"}
    g["game_profile"] = grading.game_profile(game, year, variant, style)
    if cs:
        g["corner_shape"] = {k: cs.get(k) for k in ("shape", "text", "radius_mm", "source", "agrees") if cs.get(k) is not None}
        g["format_notes"].insert(0, f"This set has {cs['text']}" + (f" (about {cs['radius_mm']:g} mm)" if cs.get("radius_mm") else "") +
                                 ": the corner check judges wear against that shape, not against a standard corner.")
    g["corner_radius_px"] = rad
    # TAG's own corner / edge attributes (Angle, Residual, Fill, Fray; edge Residual, Fray, Colour), measured the way
    # their patent describes, front and back - recorded for calibration against TAG's grades
    try:
        from core import tagmeasure
        g["tag_measure"] = {"front": _tm_slim(tagmeasure.measure_photo(f["full"], rad))}
        if b and b.get("full") is not None:
            g["tag_measure"]["back"] = _tm_slim(tagmeasure.measure_photo(b["full"], rad))
    except Exception as e:
        g["tag_measure"] = {"error": str(e)[:120]}
    g["corner_factory"] = {"shape": corner_kind, "source": corner_src, "measured_per_mille": corner_meas}
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
    rc = f.get("recut")
    if rc:
        hidden = [k for k in ("left", "right", "top", "bottom") if k not in rc.get("measured", [])]
        if hidden:
            tips.insert(0, f"The {', '.join(hidden)} edge was covered (fingers / glare), so centering on that side is less sure: hold the card by its edges or lay it flat.")
    g_recut = bool(rc)
    if min(f["full"].size) < 700:
        tips.append("Photo is small: take it with the camera, card filling most of the frame, for corners and edges to be judged.")
    g["tips"] = tips
    g["recut"] = g_recut  # cut out at its exact edges by matching it with a clean picture of the same card
    # how much to trust it: the four things that most often make a photo grade wrong
    issues = sum([not f.get("found"), not fi.photo_ok, min(f["full"].size) < 700, not b])
    g["confidence"] = "high" if issues == 0 else "medium" if issues == 1 else "low"
    g["photo_check"] = photo_check(f, fi, res, rc)
    g["sharpness"] = fi.metrics.get("sharpness")
    g["metrics"] = {k: (round(float(v), 4) if isinstance(v, (int, float)) else v) for k, v in fi.metrics.items()
                    if isinstance(v, (int, float, str, bool)) or v is None}
    g["metrics"]["photo_px"] = list(f["full"].size)
    g["metrics"]["ref_px"] = list(ref.size) if ref is not None else None
    g["subgrades_inspect"] = dict(fi.subgrades)
    g["border_wear"] = fi.metrics.get("border_wear")
    g["back_whitening"] = bw
    g["subs_raw"] = subs_raw  # before the back-whitening and defect-rubric caps (for tuning them)
    g["defects"] = [d for d in defects if d["cap"] < 10]
    if extra_out:
        g["extra_photos"] = extra_out
    if ref_cmp and ref_cmp.get("ok"):
        g["reference_check"] = {k: v for k, v in ref_cmp.items() if k != "maps"}
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
        lines = ocr.read_card(card)
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


def _plain(v):
    """numpy numbers / arrays and tuples -> plain JSON values (the engine mixes them in)."""
    try:
        import numpy as np
        if isinstance(v, np.generic):
            return v.item()
        if isinstance(v, np.ndarray):
            return v.tolist()
    except Exception:
        pass
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    if isinstance(v, float) and v != v:
        return None
    return v


def do_scan(fdata: bytes, bdata: bytes | None = None, game: str = "Auto", grade: bool = True, extras: dict | None = None) -> dict:
    """Everything the Scan page works out for a photo, as plain JSON. extras: optional grading photos
    (tilt_front / tilt_back: the side tilted toward one light; corner_xx / back_corner_xx: corner close-ups)."""
    t = time.time()
    with _lock:
        catalog.trim()  # free the previous scans' downloaded card lists if they've grown large
        res = scan._analyze(fdata, bdata, game or "Auto")
        if extras:
            res["_extras"] = extras
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
            "timing": res.get("timing", {}),
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
            if grade:
                # the card inside the slab, graded as a raw card would be (what another company might give it); cut out
                # by matching a clean picture when there is one, otherwise from the card outline found in the photo
                try:
                    ref = scan._ref_image(top) if top else None
                    r = vision.recut_with_reference(f["full"], ref) if ref is not None else None
                    if r is not None:
                        card, info = r
                        L = vision.find_lines(card, True)
                        inner = {**f, "card": card, "found": True, "edges": L,
                                 "centering": vision.Centering(L["il"] - L["ol"], L["or"] - L["ir"], L["it"] - L["ot"], L["ob"] - L["ib"])}
                    else:
                        inner = f
                    gi = _grade({**res, "front": inner, "_in_slab": True}, top)
                    gi["note"] = "Estimated from the card inside the slab (the label grade above is the official one)."
                    if r is None:
                        gi["confidence"] = "low"
                    out["grade"] = gi
                except Exception as e:
                    out["grade"] = {"error": f"couldn't grade the card inside the slab: {e}"}
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
    return _plain(out)


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
