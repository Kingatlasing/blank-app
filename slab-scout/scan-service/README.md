# Slab Scout scan service

The scanning engine behind the Slab Scout phone app: card identification (text read in English, Japanese and
Korean, photo fingerprint, colour-matched parallels, serial numbers, card backs, slab labels) and PSA / TAG-style
grade estimates. Photos are processed in memory and never stored.

## Free: Streamlit Community Cloud (recommended)

1. share.streamlit.io → **Create app** → **Deploy a public app from GitHub**.
2. Repository `Kingatlasing/blank-app`, branch `slab-scout`, main file path `slab-scout/streamlit/api_app.py`.
3. App URL: pick a name, e.g. `slab-scout-scan` → **Deploy**. Wait until the page says "Running".
4. In the phone app: Settings → Scan server → paste `slab-scout-scan.streamlit.app` → Test connection.

Endpoints: `POST /api/scan` (form: `front`, optional `back`, `game`, `grade`), `POST /api/ocr` (form: `photo`),
`GET /api/health`. A sleeping app wakes when someone opens its page.

## Docker hosts (Hugging Face Spaces on a paid plan, a home PC, any VPS)

The `Dockerfile` here runs `streamlit/service.py` (FastAPI) on port 7860, with the same endpoints without `/api`.
