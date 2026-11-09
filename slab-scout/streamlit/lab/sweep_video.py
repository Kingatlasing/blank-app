"""LAB: run the light-sweep surface check (core/lightsweep.py) on a real phone video.

  python lab/sweep_video.py <video> <out_dir> [frames=48]

Frames are taken evenly across the video (iPhone HEVC .MOV is decoded with ffmpeg), the card is found in the first
frame and every frame is cut to it, and lightsweep.analyse lines the frames up and builds the damage map. Writes to
out_dir (outside git: these are the user's own photos):
  first.jpg       the first frame, cut to the card
  damage.png      the card with likely damage marked in red
  maps.png        the separate signals (highlight timing, gloss), for checking
  report.json     frames used, share of the card the light reached, flagged areas (position in mm, size)
"""
import json, os, subprocess, sys, tempfile

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, ".")
from core import lightsweep, vision


def frames_from(video, n):
    d = tempfile.mkdtemp()
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                               capture_output=True, text=True).stdout.strip() or 0)
    fps = max(1.0, n / max(dur, 0.1))
    subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={fps:.3f},scale='min(2160,iw)':-2", "-frames:v", str(n), f"{d}/f%03d.jpg"], check=True)
    out = []
    for f in sorted(os.listdir(d)):
        out.append(np.asarray(Image.open(os.path.join(d, f)).convert("RGB")))
    return out, dur


def main():
    video, out_dir = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 48
    os.makedirs(out_dir, exist_ok=True)
    frames, dur = frames_from(video, n)
    # cut every frame to the card found in the first one (alignment then removes the hand / phone wobble)
    try:
        crop = vision.detect_and_crop(Image.fromarray(frames[0]))
        card0 = np.asarray(crop[0] if isinstance(crop, tuple) else crop)
    except Exception:
        card0 = frames[0]
    res = lightsweep.analyse([card0] + frames[1:])
    rep = {"video_seconds": round(dur, 2), **res["info"]}
    if not res.get("ok"):
        json.dump(rep, open(os.path.join(out_dir, "report.json"), "w"), indent=1)
        print(json.dumps(rep))
        return
    dmg = res["damage"]
    h, w = dmg.shape
    base = cv2.resize(card0, (w, h), interpolation=cv2.INTER_AREA)
    Image.fromarray(base).save(os.path.join(out_dir, "first.jpg"), quality=92)
    over = base.copy()
    m = dmg > 0.3
    over[m] = (0.4 * over[m] + 0.6 * np.array([255, 0, 0])).astype(np.uint8)
    nlab, lab, stats, cents = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    spots = []
    mm = 88.0 / h
    for i in range(1, nlab):
        x, y, bw, bh, area = stats[i]
        if area < 12:
            continue
        cv2.rectangle(over, (x - 3, y - 3), (x + bw + 3, y + bh + 3), (255, 255, 0), 2)
        spots.append({"x_mm": round(cents[i][0] * mm, 1), "y_mm": round(cents[i][1] * mm, 1), "w_mm": round(bw * mm, 1), "h_mm": round(bh * mm, 1),
                      "strength": round(float(dmg[lab == i].mean()), 2)})
    Image.fromarray(over).save(os.path.join(out_dir, "damage.png"))
    M = res["maps"]
    vis = [np.clip(M[k] / 8, 0, 1) for k in ("z_peak", "z_gloss")] + [M["valid"].astype(float)]
    Image.fromarray((np.hstack(vis) * 255).astype(np.uint8)).save(os.path.join(out_dir, "maps.png"))
    rep["spots"] = sorted(spots, key=lambda s: -s["strength"])[:20]
    json.dump(rep, open(os.path.join(out_dir, "report.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "spots"}), len(spots), "spots")


if __name__ == "__main__":
    main()
