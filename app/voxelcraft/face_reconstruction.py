"""Shape `mesh_face.py`'s generic parametric head toward a specific
photo's measured facial proportions, using Google's MediaPipe Face
Landmarker (a real, pretrained single-image 3D face landmark model — not
something built from scratch here).

**What this actually does, stated plainly**: it detects ~478 3D
landmarks on a face in a photo, derives a handful of *ratios* from them
(face width-to-height, eye spacing, nose width/length/protrusion, mouth
width, jaw width relative to cheekbone width), and uses those ratios to
retarget `mesh_face.build_head_mesh`'s existing Gaussian feature
parameters. The output is still the same faceted, low-poly *sculpt*
`mesh_face.py` always produces — now proportioned like the photo's
subject, rather than the built-in average proportions.

**What this does NOT do**: reproduce the photo's actual surface geometry,
skin texture, or exact bone structure. A single 2D photo doesn't contain
enough information for that without a much heavier model (a full 3D
Morphable Model fit, or a monocular-depth network) — MediaPipe's z values
are a rough relative-depth estimate, useful for a coarse protrusion
signal (see `_protrusion`) but not a depth scan. This is proportion-
matching, not photogrammetry.

The face landmark model (~3.6 MB) is downloaded from Google's model CDN
on first use and cached to disk — the one part of this module that needs
network access. Detection itself (once the model is cached) runs fully
offline.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import requests
from PIL import Image

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
_MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"
_DOWNLOAD_TIMEOUT_S = 30

# Well-known landmark indices in MediaPipe's standard 468-point face mesh
# topology (widely documented; stable across model versions since the
# mesh topology itself is fixed, only the weights predicting it change).
_L = {
    "forehead_top": 10, "chin_bottom": 152,
    "cheek_r": 234, "cheek_l": 454,          # face oval, widest point
    "eye_r_outer": 33, "eye_r_inner": 133,
    "eye_l_inner": 362, "eye_l_outer": 263,
    "nose_bridge": 168, "nose_tip": 1,
    "nose_ala_r": 98, "nose_ala_l": 327,     # nostril width
    "mouth_r": 61, "mouth_l": 291,
    "jaw_r": 172, "jaw_l": 397,               # approximate jaw-angle points
}


class FaceReconstructionError(RuntimeError):
    """Raised for any failure downloading the model or detecting a face —
    the caller is expected to catch this and fall back to the generic
    (non-photo-informed) head."""


def _ensure_model() -> str:
    if _MODEL_PATH.exists():
        return str(_MODEL_PATH)
    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(_MODEL_URL, timeout=_DOWNLOAD_TIMEOUT_S)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise FaceReconstructionError(
            "Couldn't download the face-landmark model (needs network access, once — "
            "it's cached after that)."
        ) from exc
    tmp_path = _MODEL_PATH.with_suffix(".tmp")
    tmp_path.write_bytes(resp.content)
    tmp_path.rename(_MODEL_PATH)  # atomic-ish: never leaves a half-written model file in place
    return str(_MODEL_PATH)


def _detect_landmarks(image: Image.Image) -> list[tuple[float, float, float]]:
    """Returns the 468+ (x, y, z) landmarks (image-normalized x/y in
    [0, 1], z a relative-depth estimate) for the first detected face.
    Raises FaceReconstructionError if the model can't be loaded or no
    face is found."""
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except ImportError as exc:
        raise FaceReconstructionError(
            "The mediapipe package isn't installed — photo-based face reconstruction needs it "
            "(`pip install mediapipe`)."
        ) from exc

    model_path = _ensure_model()
    try:
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            num_faces=1,
        )
        detector = vision.FaceLandmarker.create_from_options(options)
        arr = np.array(image.convert("RGB"))
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
        result = detector.detect(mp_image)
    except Exception as exc:
        raise FaceReconstructionError(f"Face landmark detection failed: {exc}") from exc

    if not result.face_landmarks:
        raise FaceReconstructionError(
            "No face found in that photo — try a clearer, front-facing, well-lit photo of one face."
        )
    landmarks = result.face_landmarks[0]
    return [(lm.x, lm.y, lm.z) for lm in landmarks]


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.dist(a[:2], b[:2])  # image-plane distance (x, y only)


def _measure(landmarks: list[tuple[float, float, float]]) -> dict[str, float]:
    p = {name: landmarks[idx] for name, idx in _L.items()}
    face_width = _dist(p["cheek_r"], p["cheek_l"])
    face_height = _dist(p["forehead_top"], p["chin_bottom"])
    cheek_z = (p["cheek_r"][2] + p["cheek_l"][2]) / 2
    return {
        "face_aspect": face_height / face_width if face_width else 1.0,
        "eye_span": _dist(p["eye_r_outer"], p["eye_l_outer"]) / face_width,
        "eye_width": ((_dist(p["eye_r_outer"], p["eye_r_inner"])
                       + _dist(p["eye_l_inner"], p["eye_l_outer"])) / 2) / face_width,
        "nose_width": _dist(p["nose_ala_r"], p["nose_ala_l"]) / face_width,
        "nose_length": _dist(p["nose_bridge"], p["nose_tip"]) / face_height,
        "nose_protrusion_z": cheek_z - p["nose_tip"][2],  # MediaPipe z: smaller/more negative = closer to camera
        "mouth_width": _dist(p["mouth_r"], p["mouth_l"]) / face_width,
        "jaw_width": _dist(p["jaw_r"], p["jaw_l"]) / face_width,
    }


# "Typical" values for each measurement above, from the same generic
# proportions `mesh_face.py`'s defaults already encode — a detected photo
# is compared against these to produce a multiplier, not an absolute
# size, since we have no true physical scale from a single 2D photo.
_BASELINE = {
    "eye_span": 0.46, "eye_width": 0.13, "nose_width": 0.14, "nose_length": 0.45,
    "nose_protrusion_z": 0.03, "mouth_width": 0.27, "jaw_width": 0.72, "face_aspect": 1.35,
}


def photo_to_proportions(image: Image.Image) -> tuple[dict[str, float], float]:
    """The main entry point: detect a face in `image` and return
    (feature_proportions, height_scale).

    `feature_proportions` is ready to pass straight to
    `mesh_face.build_head_mesh(proportions=...)`. `height_scale` is
    separate because it retargets the head's overall aspect ratio (how
    tall vs. wide), not a single Gaussian feature — multiply it onto
    `build_head_mesh`'s `ry` argument (e.g. `ry=1.15 * height_scale`).

    Raises FaceReconstructionError (never silently) if no face is found
    or the model can't be reached — the caller decides whether/how to
    fall back to the generic head."""
    landmarks = _detect_landmarks(image)
    m = _measure(landmarks)

    def ratio(key: str, clamp=(0.55, 1.8)) -> float:
        return max(clamp[0], min(clamp[1], m[key] / _BASELINE[key]))

    proportions = {
        "eye_spacing": ratio("eye_span"),
        "eye_size": ratio("eye_width"),
        "nose_width": ratio("nose_width"),
        "nose_length": ratio("nose_length"),
        "nose_protrusion": max(0.6, min(1.8, 1.0 + (m["nose_protrusion_z"] - _BASELINE["nose_protrusion_z"]) * 8)),
        "mouth_width": ratio("mouth_width"),
        "jaw_width": ratio("jaw_width"),
    }
    height_scale = ratio("face_aspect", clamp=(0.8, 1.25))
    return proportions, height_scale
