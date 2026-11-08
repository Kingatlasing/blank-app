"""LAB: at what resolution can we see the marks TAG lists on Pokemon card backs, and does a "mint back model" help?

Every English Pokemon card has the same back, so the back of any one card can be compared, pixel by pixel, with
what that spot looks like on most backs (the median of many backs; the occasional mark on one card doesn't move a
median). Two models:
  - edge model: cards lined up by their cut edges (for corner / edge marks, which sit on the cut);
  - print model: cards lined up by the printed design (for surface marks; back centering differs between cards).
A spot's score is how far it is from the model, in units of how much backs normally vary there.
For comparison, a model-free score: how much a spot differs from its own surroundings (1 mm median).

For each TAG mark (position known), the score within 0.5 mm of it is compared with the score at the same position on
other cards that have no TAG mark nearby: AUC 0.5 = can't tell them apart, 1.0 = perfect. Run at 10, 20, 40 px/mm
(the app inspects at about 10; a 12 MP phone photo of a card filling the frame is about 45; TAG's scans are ~68).
Saves numbers only. Usage: python lab/back_model_recall.py <reports url,...> <model cards> <out.json>
"""
import io, json, sys, time

import cv2, numpy as np, requests
from PIL import Image
from scipy.ndimage import median_filter, maximum_filter

sys.path.insert(0, ".")
from lab.edge_guides_eval import game_of


def card_box(a):
    """The card inside TAG's image (plain orange background); same as lab/edge_features.card_box."""
    bg = np.median(np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)]), 0)
    m = np.abs(a.astype(np.int16) - bg.astype(np.int16)).sum(2) > 90
    rows, cols = m.mean(1), m.mean(0)
    ys, xs = np.where(rows > 0.5)[0], np.where(cols > 0.5)[0]
    if len(ys) < a.shape[0] * 0.5 or len(xs) < a.shape[1] * 0.5:
        return None
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1

urls, NMODEL, out = sys.argv[1].split(","), int(sys.argv[2]), sys.argv[3]
reps = {}
for u in urls:
    for c, o in requests.get(u, timeout=60).json().items():
        if isinstance(o, dict) and o.get("u"):
            reps.setdefault(c, {}).update(o)
poke = {c: o for c, o in reps.items() if game_of(o) == "pokemon"}
evalc = [(c, o) for c, o in poke.items() if o.get("d") is not None]
modelc = [(c, o) for c, o in poke.items() if o.get("d") is None][:NMODEL]
print("pokemon", len(poke), "eval", len(evalc), "model", len(modelc), flush=True)
T0 = time.time()
CDN = "https://d39lwrz0lm7c9r.cloudfront.net/card-images/{}_BACK_MAIN.jpg"
SCALES = (10, 20, 40)


def fetch(o):
    r = requests.get(CDN.format(o["u"]), timeout=60)
    if r.status_code != 200:
        return None
    a = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))
    box = card_box(a)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    return a[y0:y1, x0:x1], box


def grid(card, s):
    return cv2.cvtColor(cv2.resize(card, (int(63 * s), int(88 * s)), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2LAB)


ref = None


def print_warp(lab10):
    """Affine that lines this back's printed design up with the reference back (found at 10 px/mm)."""
    g = cv2.GaussianBlur(lab10[..., 0].astype(np.float32), (5, 5), 0)
    W = np.eye(2, 3, dtype=np.float32)
    try:
        _, W = cv2.findTransformECC(ref, g, W, cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), None, 5)
    except cv2.error:
        return None
    return W


def warp(lab, W, s):
    W2 = W.copy()
    W2[:, 2] *= s / 10.0
    return cv2.warpAffine(lab, W2, (lab.shape[1], lab.shape[0]), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)


def robust(stack):
    """Per-pixel median and spread (MAD) of a uint8 stack, in row chunks to keep memory down."""
    n, h, w, c = stack.shape
    med = np.zeros((h, w, c), np.float32)
    mad = np.zeros((h, w, c), np.float32)
    for y in range(0, h, 64):
        blk = stack[:, y:y + 64].astype(np.float32)
        m = np.median(blk, 0)
        med[y:y + 64] = m
        mad[y:y + 64] = np.median(np.abs(blk - m), 0) * 1.4826
    return med, np.maximum(mad, 3.0)


# ---- models
models = {}
store = {s: {"edge": [], "print": []} for s in SCALES}
for i, (c, o) in enumerate(modelc):
    f = fetch(o)
    if f is None:
        continue
    lab10 = grid(f[0], 10)
    if ref is None:
        ref = cv2.GaussianBlur(lab10[..., 0].astype(np.float32), (5, 5), 0)
    W = print_warp(lab10)
    for s in SCALES:
        lab = lab10 if s == 10 else grid(f[0], s)
        store[s]["edge"].append(lab)
        if W is not None:
            store[s]["print"].append(warp(lab, W, s))
    print("model", i, c, round(time.time() - T0), "s", flush=True)
    time.sleep(0.3)
for s in SCALES:
    models[s] = {k: robust(np.stack(v)) for k, v in store[s].items()}
    store[s] = None
print("models built", flush=True)


def zmap(lab, med, mad):
    z = np.abs(lab.astype(np.float32) - med) / mad
    return cv2.GaussianBlur(z.max(2), (3, 3), 0)


def local_z(lab, s):
    L = lab[..., 0]
    k = max(3, int(s)) | 1
    d = np.abs(L.astype(np.float32) - cv2.medianBlur(np.ascontiguousarray(L), k).astype(np.float32))   # cv2 median: fast on uint8
    return d / (np.median(d) * 1.4826 + 1.0)


# ---- evaluation maps for each eval card, kept small: only the max-pooled score around each point is needed,
# so store per scale a max-filtered (0.5 mm) map downsampled to 5 px/mm
maps, marks, regions_src = {}, [], {}
for i, (c, o) in enumerate(evalc):
    f = fetch(o)
    if f is None:
        continue
    card, (x0, y0, x1, y1) = f
    lab10 = grid(card, 10)
    W = print_warp(lab10)
    mm = {}
    for s in SCALES:
        lab = lab10 if s == 10 else grid(card, s)
        r = max(1, int(0.5 * s))
        ze = zmap(lab, *models[s]["edge"])
        zp = zmap(warp(lab, W, s), *models[s]["print"]) if W is not None else ze
        if W is not None:   # bring the print-model map back to the card's own coordinates
            W2 = W.copy(); W2[:, 2] *= s / 10.0
            zp = cv2.warpAffine(zp, W2, (zp.shape[1], zp.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        zl = local_z(lab, s)
        for name, z in (("edge_model", ze), ("print_model", zp), ("local", zl)):
            pooled = cv2.dilate(z.astype(np.float32), np.ones((2 * r + 1, 2 * r + 1), np.uint8))
            mm[(s, name)] = cv2.resize(pooled, (315, 440), interpolation=cv2.INTER_AREA if s > 10 else cv2.INTER_NEAREST).astype(np.float16)
    # the app's current check (condition.inspect_card at 630 x 880): its whitening mask as a map, for comparison
    try:
        from core import condition
        cap = {}
        orig = condition._views

        def _spy(card_, a_, gray_, white_m, *rest):
            cap["w"] = white_m
            return {}
        condition._views = _spy
        try:
            condition.inspect_card(Image.fromarray(cv2.resize(card, (630, 880), interpolation=cv2.INTER_AREA)), is_back=True,
                                   corner_radius=condition.corner_radius_px("pokemon"))
        finally:
            condition._views = orig
        wm = cv2.dilate(cap["w"].astype(np.float32), np.ones((5, 5), np.uint8))
        mm[(10, "app_now")] = cv2.resize(wm, (315, 440), interpolation=cv2.INTER_AREA).astype(np.float16)
    except Exception as e:
        print("app baseline failed", e, flush=True)
    # pixels that are card (not TAG's orange background showing at the rounded corners), shrunk by 0.2 mm
    a_ = card.astype(np.int16)
    bgc = np.array([255, 118, 40], np.int16)
    inside = (np.abs(a_ - bgc).sum(2) > 120).astype(np.uint8)
    inside = cv2.resize(inside, (315, 440), interpolation=cv2.INTER_AREA)
    inside = cv2.erode(inside, np.ones((3, 3), np.uint8))
    mm["inside"] = inside.astype(bool)
    maps[c] = mm
    regions_src[c] = (x0, y0, x1 - x0, y1 - y0, [d for d in o["d"] if d[0] == "B"])
    cw, ch = x1 - x0, y1 - y0
    for d in o["d"]:
        if d[0] != "B":
            continue
        x, y = (d[2] - x0) / cw * 315, (d[3] - y0) / ch * 440
        if 0 <= x < 315 and 0 <= y < 440:
            marks.append({"cert": c, "type": d[1], "sev": d[4], "x": int(x), "y": int(y)})
    print("eval", i, c, round(time.time() - T0), "s", flush=True)
    time.sleep(0.3)

# ---- AUC per scale / method / mark type
rng = np.random.default_rng(1)
pts = {c: [(m["x"], m["y"]) for m in marks if m["cert"] == c] for c in maps}
res = {}
for (s, name) in [k for k in next(iter(maps.values())).keys() if k != "inside" and k[1] != "app_now"]:
    by = {}
    for m in marks:
        v = float(maps[m["cert"]][(s, name)][m["y"], m["x"]])
        others = [c for c in maps if c != m["cert"] and not any(abs(px - m["x"]) < 10 and abs(py - m["y"]) < 10 for px, py in pts[c])]
        ctl = [float(maps[c][(s, name)][m["y"], m["x"]]) for c in rng.choice(others, size=min(10, len(others)), replace=False)]
        for t in (m["type"], "ALL"):
            b = by.setdefault(t, [0.0, 0])
            b[0] += np.mean([1.0 if v > cv else 0.5 if v == cv else 0.0 for cv in ctl])
            b[1] += 1
    res[f"{s}px/mm {name}"] = {t: (round(a / n, 3), n) for t, (a, n) in by.items()}
    print(f"{s}px/mm {name}", res[f"{s}px/mm {name}"], flush=True)

# ---- region test: TAG pins a corner mark to the corner itself (not to the exact worn spot), so score whole regions:
# each corner (3 x 3 mm) and each 8 mm stretch of edge (1.5 mm deep), labelled by whether TAG marked it.
PX = 5   # stored maps are 5 px per mm
def regions():
    out = []
    for k, (cx, cy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
        x0_, y0_ = (0 if cx == 0 else 315 - 3 * PX), (0 if cy == 0 else 440 - 3 * PX)
        out.append(("corner", k, (x0_, y0_, x0_ + 3 * PX, y0_ + 3 * PX)))
    for side in ("top", "bottom", "left", "right"):
        L = 63 if side in ("top", "bottom") else 88
        for j, a in enumerate(range(3, L - 3 - 7, 8)):
            if side == "top":
                b = (a * PX, 0, (a + 8) * PX, int(1.5 * PX))
            elif side == "bottom":
                b = (a * PX, 440 - int(1.5 * PX), (a + 8) * PX, 440)
            elif side == "left":
                b = (0, a * PX, int(1.5 * PX), (a + 8) * PX)
            else:
                b = (315 - int(1.5 * PX), a * PX, 315, (a + 8) * PX)
            out.append(("edge", (side, j), b))
    return out
REG = regions()


def label(src):
    x0_, y0_, cw_, ch_, ds = src
    corners, edges = set(), set()
    for d in ds:
        xm = min(63, max(0, (d[2] - x0_) / cw_ * 63)); ym = min(88, max(0, (d[3] - y0_) / ch_ * 88))
        if "CORNER" in d[1].upper():
            corners.add((1 if xm > 31.5 else 0) + (2 if ym > 44 else 0))
        elif "EDGE" in d[1].upper():
            dist = {"top": ym, "bottom": 88 - ym, "left": xm, "right": 63 - xm}
            side = min(dist, key=dist.get)
            a = xm if side in ("top", "bottom") else ym
            edges.add((side, int((a - 3) // 8)))
    return corners, edges


def auc(pos, neg):
    if not pos or not neg:
        return None
    allv = np.concatenate([pos, neg]); r = np.argsort(np.argsort(allv)).astype(float)
    # ties: average ranks
    from scipy.stats import rankdata
    r = rankdata(allv)
    return round(float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))), 3)


reg_res = {}
for key in [k for k in next(iter(maps.values())).keys() if k != "inside"]:
    P = {"corner": [], "edge": []}; N = {"corner": [], "edge": []}
    for c, mm in maps.items():
        if key not in mm:
            continue
        corners, edges = label(regions_src[c])
        m = mm[key].astype(np.float32)
        ins = mm.get("inside")
        for kind, rid, (a, b, c2, d2) in REG:
            blk = m[b:d2, a:c2]
            ib = ins[b:d2, a:c2] if ins is not None else np.ones_like(blk, bool)
            if ib.sum() < 3:
                continue
            v = float(np.percentile(blk[ib], 95))   # card pixels only, robust to one stray pixel
            hit = (rid in corners) if kind == "corner" else (rid in edges)
            (P if hit else N)[kind].append(v)
    name = f"{key[0]}px/mm {key[1]}"
    reg_res[name] = {k: {"auc": auc(P[k], N[k]), "marked": len(P[k]), "unmarked": len(N[k])} for k in P}
    print("REGION", name, reg_res[name], flush=True)
json.dump({"auc": res, "regions": reg_res, "marks": len(marks), "eval_cards": len(maps), "model_cards": len(modelc)}, open(out, "w"), indent=1)
