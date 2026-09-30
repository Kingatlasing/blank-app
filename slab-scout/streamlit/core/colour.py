"""Card colour signature: tells parallels / rarities apart by colour (Prizm Silver vs Blue vs Gold, a
Refractor's rainbow border, a black 1/1). The same signature is computed for every price-guide photo (in the
browser, see data/README) and for the scan, so a scan's colours can be compared with what each parallel
looks like.

Signature (26 hex chars): the card shrunk to a 24x34 grid (exact area average), colours as simple opponent
channels L=(r+g+b)/3, A=r-g, B=(r+g)/2-b.
  [0:6]   outer ring (2 cells = ~8% of the card on every side): L, A/2+128, B/2+128
  [6:12]  inside of the card: same three
  [12:24] hue histogram, 12 bins of cells with chroma > 25, weighted by chroma, scaled so the top bin is 15
  [24:26] rainbow: how spread the ring's hues are (0 = one colour, 255 = every colour, e.g. refractor/prizm)

Photos differ with lighting, sleeves and white balance, so colour is used to rank a card's parallels against
each other (same player + number) and to flag a clear mismatch, never on its own to name a card.
"""
from __future__ import annotations

import math
import re

import numpy as np
from PIL import Image

CW, CH = 24, 34


def signature(card: Image.Image) -> str:
    im = np.asarray(card.convert("RGB").resize((CW, CH), Image.BOX), dtype=np.float64)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    L, A, B = (r + g + b) / 3, r - g, (r + g) / 2 - b
    ch = np.hypot(A, B)
    ring = np.zeros((CH, CW), bool)
    ring[:2, :] = ring[-2:, :] = ring[:, :2] = ring[:, -2:] = True
    q = lambda v: "%02x" % int(max(0, min(255, round(float(v)))))
    enc = lambda m: q(L[m].mean()) + q(A[m].mean() / 2 + 128) + q(B[m].mean() / 2 + 128)
    hue = np.arctan2(B, A)
    sat = ch > 25
    bins = (np.floor((hue + math.pi) / (2 * math.pi) * 12).astype(int)) % 12
    hist = np.bincount(bins[sat], weights=ch[sat], minlength=12)
    mx = hist.max()
    hh = "".join("%x" % (int(round(15 * v / mx)) if mx > 0 else 0) for v in hist)
    rs = ring & sat
    vw = ch[rs].sum()
    spread = 1 - math.hypot((np.cos(hue[rs]) * ch[rs]).sum(), (np.sin(hue[rs]) * ch[rs]).sum()) / vw if vw > 0 else 0.0
    return enc(ring) + enc(~ring) + hh + q(spread * 255)


def decode(sig: str) -> dict | None:
    if not sig or len(sig) < 26:
        return None
    v = [int(sig[i:i + 2], 16) for i in range(0, 12, 2)]
    return {"ring": (v[0], (v[1] - 128) * 2, (v[2] - 128) * 2), "center": (v[3], (v[4] - 128) * 2, (v[5] - 128) * 2),
            "hist": [int(c, 16) for c in sig[12:24]], "rainbow": int(sig[24:26], 16) / 255}


def distance(a: str, b: str) -> float:
    """0 = same colours; ~1 = clearly different; >2 = nothing alike."""
    x, y = decode(a), decode(b)
    if not x or not y:
        return 1.0
    ring = math.dist(x["ring"], y["ring"]) / 90
    cen = math.dist(x["center"], y["center"]) / 120
    hx, hy = np.array(x["hist"], float), np.array(y["hist"], float)
    hist = float(np.abs(hx / max(hx.sum(), 1) - hy / max(hy.sum(), 1)).sum()) / 2 if hx.sum() and hy.sum() else (0.0 if hx.sum() == hy.sum() else 0.5)
    return 0.5 * ring + 0.2 * cen + 0.2 * hist + 0.6 * abs(x["rainbow"] - y["rainbow"])


# Colour words in parallel names -> hue bins of the opponent-hue histogram (None = neutral) and a lightness hint.
# Bins (atan2(B, A) from -pi, 12 bins), measured on pure colours: teal/cyan 0, light blue 1, blue 2-3,
# purple 4-5, magenta/pink 5-6, red 6, orange 7-8, gold 8, yellow 9, green 10-11.
NAME_COLOURS = [
    (r"\bpink\b|magenta|fuchsia|rose\b", {"bins": (5, 6), "L": None}),
    (r"\bred\b|ruby|crimson|scarlet", {"bins": (6,), "L": None}),
    (r"\borange\b|copper|bronze", {"bins": (7, 8), "L": None}),
    (r"\bgold\b|golden|yellow|canary|lemon", {"bins": (8, 9), "L": None}),
    (r"\bgreen\b|emerald|lime|jade", {"bins": (10, 11), "L": None}),
    (r"\bteal\b|aqua|turquoise|cyan", {"bins": (0, 1), "L": None}),
    (r"\bblue\b|sapphire|navy|\bice\b", {"bins": (1, 2, 3), "L": None}),
    (r"\bpurple\b|violet|amethyst|lavender", {"bins": (4, 5), "L": None}),
    (r"\bblack\b|onyx|noir", {"bins": None, "L": "dark"}),
    (r"\bwhite\b|snow|pearl", {"bins": None, "L": "light"}),
    (r"\bsilver\b|platinum", {"bins": None, "L": "neutral"}),
]
BIN_NAMES = ["teal", "light blue", "blue", "blue", "purple", "purple/pink", "red/pink", "orange", "gold", "yellow", "green", "green"]
RAINBOW = re.compile(r"refractor|prizm|holo|rainbow|mojo|shimmer|wave|lazer|laser|hyper|disco|pulsar|cracked ice|mosaic", re.I)


def name_colour_score(variant: str, sig: str) -> float | None:
    """How well the scan's colours fit the colour the parallel's name says (0 good .. 1 bad); None when the
    name has no colour word."""
    x = decode(sig)
    if not x or not variant:
        return None
    v = variant.lower()
    for pat, spec in NAME_COLOURS:
        if re.search(pat, v):
            h = np.array(x["hist"], float)
            tot = h.sum()
            if spec["bins"]:
                if not tot:
                    return 0.8  # colourless scan for a coloured parallel
                share = sum(h[i] for i in spec["bins"]) / tot
                # neighbouring hues count a little (white balance shifts hues)
                near = sum(h[(i + d) % 12] for i in spec["bins"] for d in (-1, 1) if (i + d) % 12 not in spec["bins"]) / tot
                return float(max(0.0, 1 - 1.2 * (share + 0.4 * near)))
            L = (x["ring"][0] + x["center"][0]) / 2
            chroma = math.hypot(*x["ring"][1:])
            if spec["L"] == "dark":
                return float(min(1, max(0, (L - 70) / 90)))
            if spec["L"] == "light":
                return float(min(1, max(0, (200 - x["ring"][0]) / 80)))
            return float(min(1, chroma / 60))  # silver: grey / neutral border
    return None


def rank_parallels(sig: str, options: list[dict], profiles: dict) -> list[dict]:
    """options: [{'set': id, 'variant': name, ...}] for the same card. Adds 'colour_fit' (0 best .. 1 worst) and
    'colour_why'; returns them best first. profiles: {set: {variant: signature}} learned from price-guide photos."""
    out = []
    for o in options:
        prof = (profiles.get(o.get("set"), {}) or {}).get(o.get("variant") or "Base")
        fit, why = None, ""
        if prof:
            fit, why = min(1.0, distance(sig, prof) / 1.5), "colours of this parallel's photos"
        n = name_colour_score(o.get("variant") or "", sig)
        if n is not None:
            fit, why = (n, "colour in the name") if fit is None else ((fit * 2 + n) / 3, why + " + colour in the name")
        out.append({**o, "colour_fit": fit, "colour_why": why})
    return sorted(out, key=lambda o: 0.5 if o["colour_fit"] is None else o["colour_fit"])


def describe(sig: str) -> str:
    """Plain words for the scan's colours (shown next to the match)."""
    x = decode(sig)
    if not x:
        return ""
    names = BIN_NAMES
    h = x["hist"]
    L, A, B = x["ring"]
    border = "black" if L < 60 else "white" if L > 215 and math.hypot(A, B) < 25 else "silver/grey" if math.hypot(A, B) < 25 else names[int(np.argmax(h))] if sum(h) else "grey"
    top = [names[i] for i in np.argsort(h)[::-1][:2] if h[i] >= 6]
    s = f"border {border}"
    if top:
        s += ", mostly " + " and ".join(dict.fromkeys(top))
    if x["rainbow"] > 0.55:
        s += ", rainbow/refractor shine"
    return s
