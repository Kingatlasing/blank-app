import sys, numpy as np, cv2
sys.path.insert(0, '/home/claude/blank-app/slab-scout/slab-scout/streamlit')
from PIL import Image
from core import multiframe as mf
clean = np.asarray(Image.open(sys.argv[1]).convert('RGB'))
clean = cv2.resize(clean, (clean.shape[1]*2, clean.shape[0]*2), interpolation=cv2.INTER_CUBIC)
h, w = clean.shape[:2]
rng = np.random.default_rng(1)
def frame(i, glare=True):
    a = np.deg2rad(rng.uniform(-2, 2)); s = rng.uniform(0.97, 1.03)
    M = cv2.getRotationMatrix2D((w/2, h/2), np.rad2deg(a), s); M[:, 2] += rng.uniform(-25, 25, 2)
    f = cv2.warpAffine(clean, M, (w, h), borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    f *= rng.uniform(0.95, 1.05)
    if glare:
        cx, cy = rng.uniform(0.2, 0.8)*w, rng.uniform(0.2, 0.8)*h
        yy, xx = np.mgrid[0:h, 0:w]
        g = np.exp(-(((xx-cx)/(0.18*w))**2 + ((yy-cy)/(0.08*h))**2))
        f = f*(1-g[..., None]) + 255*g[..., None]
    f += rng.normal(0, 2, f.shape)
    return np.clip(f, 0, 255).astype(np.uint8), M
frames = [frame(i) for i in range(5)]
base, M0 = frames[0]
ref = cv2.warpAffine(clean, M0, (w, h), borderMode=cv2.BORDER_REPLICATE)  # clean card in frame 0's position
out, info = mf.merge([Image.fromarray(f) for f, _ in frames])
out = np.asarray(out)
gm = mf.glare_mask(base)
inner = np.zeros((h, w), bool); inner[int(.05*h):int(.95*h), int(.05*w):int(.95*w)] = True
def err(x, m): return float(np.abs(x.astype(int) - ref.astype(int))[m].mean())
lap = lambda x, m: float(cv2.Laplacian(cv2.cvtColor(x, cv2.COLOR_RGB2GRAY), cv2.CV_64F)[m].var())
print(info)
print('glare area: single photo error %.1f -> merged %.1f (0 = perfect)' % (err(base, gm & inner), err(out, gm & inner)))
print('no-glare area: single %.1f -> merged %.1f' % (err(base, ~gm & inner), err(out, ~gm & inner)))
print('sharpness (laplacian var) clean %.0f single %.0f merged %.0f' % (lap(ref, ~gm & inner), lap(base, ~gm & inner), lap(out, ~gm & inner)))
for n in (2, 3):
    o, i2 = mf.merge([Image.fromarray(f) for f, _ in frames[:n]])
    print(n, 'photos: glare-area error %.1f' % err(np.asarray(o), gm & inner), i2)
Image.fromarray(np.hstack([base, out])).resize((w, h//2)).save('mf_compare.jpg')
