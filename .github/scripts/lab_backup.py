"""Fetch the server's holding area and grading-test results and merge them into lab-data/ without ever shrinking
what is already saved (a freshly restarted server has less, not newer, data). Restart an interrupted grading test
from the saved results."""
import gzip
import json
import os
import re
import requests

BASE = "https://mobilecards.streamlit.app/~/+/api/"
RAW = "https://raw.githubusercontent.com/Kingatlasing/blank-app/slab-scout-work/"
D = "lab-data"
os.makedirs(D, exist_ok=True)


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def save(path, obj):
    json.dump(obj, open(path, "w"), separators=(",", ":"), sort_keys=True)


def get(path, **kw):
    r = requests.get(BASE + path, timeout=120, **kw)
    r.raise_for_status()
    return r


# 1. holding area (collector reports etc.): merge dicts key by key, keep the longer list
try:
    store = get("labstore").json()
    for key, data in store.items():
        fn = os.path.join(D, re.sub(r"[^\w.-]", "_", key) + ".json")
        old = load(fn, None)
        if isinstance(old, dict) and isinstance(data, dict):
            merged = {**old, **data}
        elif isinstance(old, list) and isinstance(data, list) and len(old) > len(data):
            merged = old
        else:
            merged = data
        save(fn, merged)
        print(key, len(merged) if hasattr(merged, "__len__") else "")
except Exception as e:
    print("labstore:", e)

# 2. grading test: save results per list (never fewer than already saved), resume if the server lost the run
cur_fn = os.path.join(D, "gradebench-current.json")
cur = load(cur_fn, {})
try:
    st = get("gradebench/status").json()
except Exception as e:
    st = {}
    print("status:", e)
lst = st.get("list") or cur.get("list")
if lst:
    name = re.sub(r"\.json$", "", lst.rstrip("/").split("/")[-1])
    res_fn = os.path.join(D, f"gradebench-{name}.json")
    saved = load(res_fn, [])
    if st.get("state") in ("running", "done", "stopped") and st.get("list") == lst:
        try:
            res = json.loads(gzip.decompress(get("gradebench/result").content))
            if len(res) >= len(saved):
                save(res_fn, res)
                saved = res
        except Exception as e:
            print("result:", e)
        cur = {"list": lst, "n": st.get("n"), "done": len(saved), "state": st.get("state")}
    elif cur.get("state") == "running" and st.get("state") in (None, "idle", "error"):
        # the server restarted mid-run: start again, skipping the cards already saved
        try:
            r = get("gradebench/start", params={"list": lst, "limit": 3000, "resume": RAW + res_fn})
            print("resumed:", r.json())
        except Exception as e:
            print("resume:", e)
    save(cur_fn, cur)
    print("gradebench", name, len(saved), cur.get("state"))
