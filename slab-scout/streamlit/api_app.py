"""Slab Scout scan service on Streamlit Community Cloud (free): the same engine as service.py (FastAPI, for
Docker hosts) served from a Streamlit app, with the API under /api.

    streamlit run api_app.py          (Streamlit 1.64+ runs the `app` below as an ASGI app)

POST /api/scan  form: front (photo), back (optional photo), game, grade -> identification + grade (JSON)
GET  /api/scan_url?url=&back=&game=&grade=   same, from photo links (testing with photos found online)
POST /api/ocr   form: photo, lang (auto | ja | ko)                    -> text lines on the card
GET  /api/health
GET  /api/learn/start | status | stop | result   learn each set's clean-card baseline (core/learn.py)
GET  /web/index.html  the phone app in a browser (mobile-web build), already pointed at this server
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402
from starlette.middleware import Middleware  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

MAX_BYTES = 15 * 1024 * 1024
_engine = None

# The phone app's browser build (mobile-web branch), served from here too at /web/index.html: a browser only
# lets a page call the scan API when both come from the same address.
WEB_DIR = os.path.join(os.environ.get("TMPDIR", "/tmp"), "slabscout-web")
WEB_ZIP = "https://codeload.github.com/Kingatlasing/blank-app/zip/refs/heads/mobile-web"


def _fetch_web():
    import io
    import shutil
    import zipfile

    import requests
    try:
        z = zipfile.ZipFile(io.BytesIO(requests.get(WEB_ZIP, timeout=120).content))
        tmp = WEB_DIR + ".new"
        shutil.rmtree(tmp, ignore_errors=True)
        for n in z.namelist():
            part = n.split("/", 1)[1] if "/" in n else ""
            if part.startswith("static/") and not n.endswith("/"):
                dest = os.path.join(tmp, part[len("static/"):])
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as fh:
                    fh.write(z.read(n))
        shutil.rmtree(WEB_DIR, ignore_errors=True)
        os.replace(tmp, WEB_DIR)
    except Exception:
        pass


os.makedirs(WEB_DIR, exist_ok=True)
import threading  # noqa: E402

threading.Thread(target=_fetch_web, daemon=True).start()


def engine():
    """The scanning engine, loaded on first use (keeps the app quick to start)."""
    global _engine
    if _engine is None:
        for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):  # share corrections with the web app when set
            try:
                if k not in os.environ and k in st.secrets:
                    os.environ[k] = str(st.secrets[k])
            except Exception:
                pass
        import service
        _engine = service
    return _engine


async def _photo(form, field: str) -> bytes | None:
    f = form.get(field)
    if f is None or isinstance(f, str):
        return None
    data = await f.read()
    if len(data) > MAX_BYTES:
        raise ValueError("Photo is over 15 MB")
    return data or None


async def health(request: Request):
    svc = await run_in_threadpool(engine)
    return JSONResponse({"ok": True, "sets": len(svc.catalog.sets())})


async def scan(request: Request):
    try:
        form = await request.form()
        front, back = await _photo(form, "front"), await _photo(form, "back")
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=413)
    if not front:
        return JSONResponse({"detail": "No photo of the front"}, status_code=400)
    grade = str(form.get("grade", "true")).lower() not in ("false", "0", "no")
    svc = await run_in_threadpool(engine)
    out = await run_in_threadpool(svc.do_scan, front, back, str(form.get("game") or "Auto"), grade)
    return JSONResponse(out)


async def read(request: Request):
    try:
        form = await request.form()
        photo = await _photo(form, "photo")
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=413)
    if not photo:
        return JSONResponse({"detail": "No photo"}, status_code=400)
    svc = await run_in_threadpool(engine)
    return JSONResponse(await run_in_threadpool(svc.do_ocr, photo, str(form.get("lang") or "auto")))


def _get_public_image(url: str) -> bytes:
    """Download a photo from a public https address (for testing identification with photos found online).
    Only https, only public internet addresses (no local / private network), images only, 15 MB at most;
    redirects are followed by hand so each hop is checked."""
    import ipaddress
    import socket
    from urllib.parse import urljoin, urlparse

    import requests
    for _ in range(4):
        u = urlparse(url)
        if u.scheme != "https" or not u.hostname:
            raise ValueError("Only https photo links")
        for info in socket.getaddrinfo(u.hostname, 443):
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                raise ValueError("That address isn't on the public internet")
        r = requests.get(url, timeout=25, stream=True, allow_redirects=False, headers={"User-Agent": "Mozilla/5.0 SlabScout"})
        if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, r.headers.get("location", ""))
            continue
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image/"):
            raise ValueError("That link isn't a photo")
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > MAX_BYTES:
                raise ValueError("Photo is over 15 MB")
        return data
    raise ValueError("Too many redirects")


async def scan_url(request: Request):
    """GET /api/scan_url?url=<photo link>&back=<photo link>&game=Auto&grade=false: scan a photo from the web."""
    q = request.query_params
    try:
        front = await run_in_threadpool(_get_public_image, q.get("url", ""))
        back = await run_in_threadpool(_get_public_image, q["back"]) if q.get("back") else None
    except Exception as e:
        return JSONResponse({"detail": f"Couldn't get the photo: {e}"}, status_code=400)
    svc = await run_in_threadpool(engine)
    grade = str(q.get("grade", "false")).lower() in ("true", "1", "yes")
    try:
        out = await run_in_threadpool(svc.do_scan, front, back, q.get("game") or "Auto", grade)
    except Exception as e:
        import traceback
        return JSONResponse({"detail": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}, status_code=500)
    out.pop("card_jpeg", None)
    return JSONResponse(out)


_GRADE_LABELS = {
    "PSA 10": "PSA 10", "BGS 10": "BGS 10 Pristine", "BGS 10 Black": "BGS 10 Black Label", "CGC 10": "CGC 10",
    "CGC 10 Pristine": "CGC 10 Pristine", "CGC 10 Prist.": "CGC 10 Pristine", "SGC 10": "SGC 10", "TAG 10": "TAG 10",
    "ACE 10": "ACE 10", "Grade 9.5": "Grade 9.5", "Grade 9": "Grade 9", "Grade 8": "Grade 8", "Grade 7": "Grade 7",
    "Grade 6": "Grade 6", "Grade 5": "Grade 5", "Grade 4": "Grade 4", "Grade 3": "Grade 3", "Grade 2": "Grade 2",
    "Grade 1": "Grade 1", "Ungraded": "RAW",
}
_grade_cache: dict[str, dict] = {}


def parse_grade_page(html: str) -> dict:
    """Real sold prices per grade from a PriceCharting / SportsCardsPro card page (same rules as app/src/core/grades.ts):
    only grades with at least one sold listing are kept, so the site's own estimates are skipped."""
    import re
    counts: dict[str, int] = {}
    for m in re.finditer(r'<option value="completed-auctions[^"]*">\s*([^<(]+?)\s*\((\d+)\)\s*</option>', html):
        k = _GRADE_LABELS.get(m.group(1).strip())
        if k:
            counts[k] = max(counts.get(k, 0), int(m.group(2)))
    out = {}
    for m in re.finditer(r'<td>\s*([^<]{2,30}?)\s*</td>\s*<td class="price js-price">\s*([^<]*?)\s*</td>', html):
        k = _GRADE_LABELS.get(m.group(1).strip())
        try:
            v = float(m.group(2).replace("$", "").replace(",", ""))
        except ValueError:
            continue
        if k and v > 0 and counts.get(k, 0) > 0:
            out[k] = {"v": v, "sales": counts[k]}
    return out


def _get_grades(url: str) -> dict:
    import re
    import requests
    if not re.match(r"^https://www\.(pricecharting|sportscardspro)\.com/game/[\w%&'.,()+-]+/[\w%&'.,()+-]+$", url):
        raise ValueError("Only PriceCharting / SportsCardsPro card pages")
    hit = _grade_cache.get(url)
    if hit is not None:
        return hit
    r = requests.get(url, timeout=20, allow_redirects=False, headers={"User-Agent": "Mozilla/5.0 SlabScout", "Accept": "text/html"})
    if r.status_code != 200:
        raise ValueError(f"price page returned {r.status_code}")
    out = parse_grade_page(r.text[:3_000_000])
    if len(_grade_cache) > 5000:
        _grade_cache.clear()
    _grade_cache[url] = out
    return out


async def grades(request: Request):
    """GET /api/grades?url=<PriceCharting / SportsCardsPro card page>: real sold prices for every grade of that card."""
    try:
        g = await run_in_threadpool(_get_grades, request.query_params.get("url", ""))
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    return JSONResponse({"grades": g})


async def learn_status(request: Request):
    from core import learn
    return JSONResponse(learn.status())


async def learn_start(request: Request):
    from core import learn
    await run_in_threadpool(engine)
    url = request.query_params.get("list") or learn.LIST_URL
    workers = int(request.query_params.get("workers") or 3)
    return JSONResponse(await run_in_threadpool(learn.start, url, min(max(workers, 1), 6)))


async def learn_stop(request: Request):
    from core import learn
    return JSONResponse(learn.stop())


async def learn_result(request: Request):
    from core import learn
    from starlette.responses import Response
    data = await run_in_threadpool(learn.result_gz)
    return Response(data, media_type="application/gzip",
                    headers={"Content-Disposition": 'attachment; filename="slabscout-learn-1.json.gz"'})


app = st.App(
    "scan_page.py",
    routes=[Route("/api/health", health), Route("/api/scan", scan, methods=["POST"]), Route("/api/scan_url", scan_url), Route("/api/grades", grades), Route("/api/ocr", read, methods=["POST"]),
            Route("/api/learn/status", learn_status), Route("/api/learn/start", learn_start, methods=["GET", "POST"]),
            Route("/api/learn/stop", learn_stop, methods=["GET", "POST"]), Route("/api/learn/result", learn_result),
            Mount("/web", app=StaticFiles(directory=WEB_DIR, html=True, check_dir=False))],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
)
