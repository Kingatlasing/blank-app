"""A holding area for test data (collector reports, test results) until it is copied into the GitHub repo.

The server's memory and disk are wiped whenever the app sleeps or restarts, so nothing is meant to live here long:
a scheduled GitHub workflow (.github/workflows/lab-backup.yml) fetches GET /api/labstore every 30 minutes and
commits it to the slab-scout-work branch (lab-data/), where it is kept for good. Browser collectors POST what
they gathered; dict data is merged key by key, so re-sending the same reports is harmless.

POST /api/labstore  {"key": "tag-reports", "data": {...} | [...]}      GET /api/labstore -> {key: data, ...}
"""
from __future__ import annotations

import json
import os
import threading

_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "slabscout-labstore.json")
_lock = threading.Lock()
_data: dict = {}


def _load() -> None:
    global _data
    if not _data and os.path.exists(_PATH):
        try:
            _data = json.load(open(_PATH))
        except Exception:
            _data = {}


def put(key: str, data) -> dict:
    with _lock:
        _load()
        cur = _data.get(key)
        if isinstance(cur, dict) and isinstance(data, dict):
            cur.update(data)
        else:
            _data[key] = data
        tmp = _PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_data, f)
        os.replace(tmp, _PATH)
        v = _data[key]
        return {"key": key, "n": len(v) if hasattr(v, "__len__") else 1}


def dump() -> dict:
    with _lock:
        _load()
        return dict(_data)
