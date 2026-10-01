---
title: Slab Scout Scan
emoji: 🃏
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Slab Scout scan service

The scanning engine behind the Slab Scout phone app: card identification (text read in English, Japanese and
Korean, photo fingerprint, colour-matched parallels, serial numbers, card backs, slab labels) and PSA / TAG-style
grade estimates. Photos are processed in memory and never stored.

- `POST /scan` (form fields `front`, optional `back`, `game`): the match, price, grade and text read
- `POST /ocr` (form field `photo`): the text lines on a card
- `GET /health`

Code: https://github.com/Kingatlasing/blank-app/tree/slab-scout/slab-scout/streamlit/service.py
