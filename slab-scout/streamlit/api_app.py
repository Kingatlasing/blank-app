"""Slab Scout scan service on Streamlit Community Cloud (free): the same engine as service.py (FastAPI, for
Docker hosts) served from a Streamlit app, with the API under /api.

    streamlit run api_app.py          (Streamlit 1.64+ runs the `app` below as an ASGI app)

POST /api/scan  form: front (photo), back (optional photo), game, grade -> identification + grade (JSON)
POST /api/ocr   form: photo, lang (auto | ja | ko)                    -> text lines on the card
GET  /api/health
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


app = st.App(
    "scan_page.py",
    routes=[Route("/api/health", health), Route("/api/scan", scan, methods=["POST"]), Route("/api/ocr", read, methods=["POST"]),
            Mount("/web", app=StaticFiles(directory=WEB_DIR, html=True, check_dir=False))],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
)
