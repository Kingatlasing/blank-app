"""LAB: run the reflected-stripe surface check (core/deflect.py) on a phone video of the Stripe Scan page.

  python lab/deflect_video.py <video> <out_dir> [period=40 hold=0.8 steps=8]

The page shows: 3 s countdown (black), 1.5 s black, 0.6 s WHITE (sync), 0.6 s black, `steps` stripe steps one way
(`hold` s each), 0.5 s black, `steps` steps the other way, 0.6 s black, 0.6 s white, 1 s black.
The first white flash is found from the video's brightness; each step's frames are averaged over the middle half of
its hold (away from the switch between steps). Writes (outside git: the user's own video):
  damage.png   the scene with likely damage in red;  maps.png   slope / gloss / stripe contrast;  report.json
"""
import json, os, subprocess, sys, tempfile

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, ".")
from core import deflect

FLASH, GAP, MID = 0.6, 0.6, 0.5


def read_frames(video, width=1400):
    d = tempfile.mkdtemp()
    subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"scale='min({width},iw)':-2", "-q:v", "3", f"{d}/f%05d.jpg"], check=True)
    rate = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", video],
                          capture_output=True, text=True).stdout.strip()
    num, den = (rate.split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    files = sorted(os.listdir(d))
    frames = [cv2.cvtColor(cv2.imread(os.path.join(d, f)), cv2.COLOR_BGR2GRAY) for f in files]
    return frames, fps


def find_flash(frames):
    m = np.array([f.mean() for f in frames])
    lo, hi = np.percentile(m, 10), m.max()
    on = m > lo + 0.6 * (hi - lo)
    idx = np.where(on)[0]
    if not len(idx):
        return None, m
    return int(idx[0]), m


def main():
    video, out_dir = sys.argv[1], sys.argv[2]
    period = float(sys.argv[3]) if len(sys.argv) > 3 else 40
    hold = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8
    steps = int(sys.argv[5]) if len(sys.argv) > 5 else 8
    os.makedirs(out_dir, exist_ok=True)
    frames, fps = read_frames(video)
    f0, bright = find_flash(frames)
    rep = {"fps": round(fps, 2), "frames": len(frames), "flash_frame": f0}
    if f0 is None:
        rep["error"] = "no white flash found: the video must include the scan's first white flash"
        json.dump(rep, open(os.path.join(out_dir, "report.json"), "w"), indent=1)
        print(json.dumps(rep))
        return
    t0 = f0 / fps

    def step_frames(start):
        out = []
        for k in range(steps):
            a, b = start + k * hold + 0.25 * hold, start + k * hold + 0.75 * hold
            ia, ib = int(round(a * fps)), int(round(b * fps))
            sel = frames[ia:max(ia + 1, ib)]
            if not sel:
                return None
            out.append(np.mean(np.stack(sel).astype(np.float32), 0))
        return out
    sx = t0 + FLASH + GAP
    sy = sx + steps * hold + MID
    fx, fy = step_frames(sx), step_frames(sy)
    if fx is None or fy is None:
        rep["error"] = "video ends before the stripes finish"
        json.dump(rep, open(os.path.join(out_dir, "report.json"), "w"), indent=1)
        print(json.dumps(rep))
        return
    res = deflect.analyse(fx, fy)
    rep.update(res["info"])
    dmg = res["damage"]
    base = np.mean(np.stack(fx + fy), 0).astype(np.uint8)
    over = cv2.cvtColor(base, cv2.COLOR_GRAY2RGB)
    m = dmg > 0.3
    over[m] = (0.4 * over[m] + 0.6 * np.array([255, 0, 0])).astype(np.uint8)
    Image.fromarray(over).save(os.path.join(out_dir, "damage.png"))
    M = res["maps"]
    vis = np.hstack([np.clip(M["z_slope"] / 20, 0, 1), np.clip(M["z_gloss"] / 10, 0, 1), np.clip(M["contrast"] / max(1, M["contrast"].max()), 0, 1)])
    Image.fromarray((vis * 255).astype(np.uint8)).save(os.path.join(out_dir, "maps.png"))
    n, lab, stats, cents = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    rep["spots"] = sorted([{"x": int(cents[i][0]), "y": int(cents[i][1]), "w": int(stats[i][2]), "h": int(stats[i][3]),
                            "strength": round(float(dmg[lab == i].mean()), 2)} for i in range(1, n) if stats[i][4] >= 12],
                          key=lambda s: -s["strength"])[:25]
    json.dump(rep, open(os.path.join(out_dir, "report.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "spots"}), len(rep["spots"]), "spots")


if __name__ == "__main__":
    main()
