"""A genuine polygon-mesh human male head: real (x, y, z) vertices and
triangle faces at arbitrary angles, not axis-aligned voxel cubes, and not
a hand-designed parametric shape either — this is a real, artist-modeled
reference head mesh, decimated down to a low-poly facet count and then
locally deformed per proportion.

**Where the base shape comes from.** An earlier version of this module
built the head from scratch: a UV-sphere reshaped by a width-factor curve,
with facial features layered on as Gaussian bumps/dents. It never
actually looked like a face — a plausible *silhouette* is not the same
thing as correct anatomy, and hand-tuning Gaussian amplitudes by eye
cannot substitute for a real model. This version starts from an actual
reference head mesh (a clean, well-proportioned male head sourced from a
real 3D asset, MIT/royalty-free), decimated with quadric edge-collapse
from ~3700 to 1000 triangles — chosen by rendering several target
triangle counts side by side (1500/1000/600) and picking the one that
kept every feature (eye socket, nose bridge, nostril wings, lips, jaw
line, ear) clearly readable while landing in the same faceted low-poly
range the rest of this app's "realistic face" mode already uses. The
baked vertex/face data lives in `assets/male_head.json`.

**How proportions retarget it.** Rather than re-deriving Gaussian bump
parameters, this locates real 3D landmarks *on that actual mesh* — nose
tip, eye corners, mouth corners, jaw points, etc. — the same way a real
photo gets measured: render the mesh from the front, run it through
Google's MediaPipe Face Landmarker (the same pretrained model
`face_reconstruction.py` uses on real photos), then ray-cast each
detected 2D landmark back into 3D against the actual mesh geometry to get
its true surface position. `assets/male_head.json` bakes in the result
(`landmarks`), so this cost is paid once, offline, not on every call.

Each proportion knob (`eye_spacing`, `eye_size`, `nose_width`,
`nose_length`, `nose_protrusion`, `mouth_width`, `jaw_width`) then works
by real per-vertex geometric operations, weighted by a smooth Gaussian
falloff in (y, z) from the relevant landmark(s) — never touching a whole
feature uniformly, and never touching unrelated features:

- `*_width`/`eye_spacing`: scale the vertex's own x (offset from the
  mesh's true centerline) by the multiplier — since the mesh is
  bilaterally symmetric about x=0, this widens/narrows a region
  symmetrically for free, no separate left/right bookkeeping needed.
- `eye_size`: scale radially in 3D around that eye's own landmark center
  (whichever eye — left or right — the vertex is actually closest to).
- `nose_length`: stretch vertically around the nose bridge landmark.
- `nose_protrusion`: scale the vertex's z *offset from the cheek plane*
  (not its raw z) — so it's the nose's actual forward protrusion that
  grows or shrinks, not an arbitrary absolute depth.

This is the same `proportions` dict shape (and the same multiplier
convention: 1.0 = unchanged) `face_reconstruction.photo_to_proportions`
and `random_proportions` already produced for the old Gaussian-bump
version, so neither of those, nor any caller, needed to change.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

Vertex = tuple[float, float, float]
Face = tuple[int, int, int]

with (Path(__file__).parent / "assets" / "male_head.json").open(encoding="utf-8") as _fh:
    _ASSET = json.load(_fh)

_BASE_VERTS: list[Vertex] = [tuple(v) for v in _ASSET["vertices"]]
_FACES: list[Face] = [tuple(f) for f in _ASSET["faces"]]
_LM: dict[str, Vertex] = {k: tuple(v) for k, v in _ASSET["landmarks"].items()}


def _mid(a: Vertex, b: Vertex) -> Vertex:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


_EYE_R_CENTER = _mid(_LM["eye_r_inner"], _LM["eye_r_outer"])
_EYE_L_CENTER = _mid(_LM["eye_l_inner"], _LM["eye_l_outer"])
_NOSE_CENTER = _mid(_LM["nose_bridge"], _LM["nose_tip"])
_MOUTH_CENTER = _mid(_LM["mouth_r"], _LM["mouth_l"])
_CHEEK_Z = (_LM["cheek_r"][2] + _LM["cheek_l"][2]) / 2
_JAW_Y = (_LM["jaw_r"][1] + _LM["jaw_l"][1]) / 2
_JAW_Z = (_LM["jaw_r"][2] + _LM["jaw_l"][2]) / 2
_NOSE_BRIDGE_Y = _LM["nose_bridge"][1]

# How far each proportion's influence reaches from its landmark, in the
# mesh's own baked units (crown-to-chin height = 2.3) — tuned by rendering
# extreme multipliers (see the module docstring's decimation-count
# process) and checking the affected region matched the named feature
# without bleeding into its neighbors (e.g. "nose_width" widening the
# cheeks, or "eye_size" puffing out the brow).
_EYE_RADIUS = 0.34
_NOSE_RADIUS = 0.5
_MOUTH_RADIUS = 0.38
_JAW_RADIUS = 1.0

# Safety bound on total per-vertex displacement — see its use in
# build_head_mesh for why this exists (a handful of shared-influence
# vertices can sum multiple simultaneous deltas past where the mesh stays
# clean, even when no single delta or pair does).
_MAX_DISPLACEMENT = 0.4


def _falloff(dy: float, dz: float, radius: float) -> float:
    return math.exp(-(dy * dy + dz * dz) / (radius * radius))


def build_head_mesh(
    proportions: dict[str, float] | None = None, ry: float = 1.15,
) -> tuple[list[Vertex], list[Face]]:
    """The real reference head (see module docstring), deformed per
    `proportions` and uniformly scaled so its crown-to-chin height is
    `2 * ry` (the default `ry=1.15` reproduces the mesh's own baked
    scale, i.e. no extra scaling).

    `proportions`, if given, is a `{name: multiplier}` dict (1.0 = the
    reference mesh's own proportions) — see the module docstring for
    exactly what each of the 7 recognized keys moves. This is what lets
    `face_reconstruction.py` shape the head toward a specific photo's
    measured proportions, or `random_proportions` toward a seeded
    "random" one, without either of them knowing this is a real mesh
    underneath rather than a parametric one."""
    scale = ry / 1.15
    p = proportions or {}
    eye_spacing = p.get("eye_spacing", 1.0)
    eye_size = p.get("eye_size", 1.0)
    nose_width = p.get("nose_width", 1.0)
    nose_length = p.get("nose_length", 1.0)
    nose_protrusion = p.get("nose_protrusion", 1.0)
    mouth_width = p.get("mouth_width", 1.0)
    jaw_width = p.get("jaw_width", 1.0)

    out: list[Vertex] = []
    for x0, y0, z0 in _BASE_VERTS:
        w_eye_r = _falloff(y0 - _EYE_R_CENTER[1], z0 - _EYE_R_CENTER[2], _EYE_RADIUS)
        w_eye_l = _falloff(y0 - _EYE_L_CENTER[1], z0 - _EYE_L_CENTER[2], _EYE_RADIUS)
        w_nose = _falloff(y0 - _NOSE_CENTER[1], z0 - _NOSE_CENTER[2], _NOSE_RADIUS)
        w_mouth = _falloff(y0 - _MOUTH_CENTER[1], z0 - _MOUTH_CENTER[2], _MOUTH_RADIUS)
        w_jaw = _falloff(y0 - _JAW_Y, z0 - _JAW_Z, _JAW_RADIUS)

        # Where two regions' falloffs both reach a vertex at close to full
        # strength — the glabella/nose-bridge saddle between the eyes and
        # the nose is the real case that surfaced this — each pulling
        # toward its *own* landmark at up to 100% would let their deltas
        # fight each other and fold that patch of geometry, even though
        # every individual region (and most pairs, tested in isolation)
        # stayed clean on its own. Rather than keep shrinking radii to
        # chase every such saddle point individually, cap the *total*
        # demand on any one vertex to 1.0 and let overlapping regions
        # share that budget proportionally — isolated regions (the
        # overwhelming majority of vertices, sum well under 1) are
        # completely unaffected by this.
        demand = max(w_eye_r, w_eye_l) + w_nose + w_mouth + w_jaw
        if demand > 1.0:
            k = 1.0 / demand
            w_eye_r *= k
            w_eye_l *= k
            w_nose *= k
            w_mouth *= k
            w_jaw *= k

        # Every term below is a delta computed from the *original* (x0, y0,
        # z0), then all summed once at the end — never chained (an earlier
        # term's already-modified x feeding into a later term).
        dx = x0 * (eye_spacing - 1) * max(w_eye_r, w_eye_l)
        dy = dz = 0.0

        # eye_size: which eye a vertex belongs to has to be decided by the
        # vertex's own x0 sign, not by comparing w_eye_r/w_eye_l — those
        # weights are deliberately x-blind (see _falloff, used unmodified
        # by eye_spacing above to widen both sides symmetrically from one
        # shared per-row weight), so on their own they can't tell a vertex
        # near the *left* eye's height/depth from one actually at the same
        # height/depth on the right side of the face. Picking "whichever
        # weight is larger" as a side-selector produced exactly that:
        # opposite-side vertices occasionally won the comparison and then
        # got their delta measured from the *wrong* eye's center — a
        # false "radial distance" of 0.7-0.8 units instead of ~0.1-0.15,
        # which is what turned a clean face into self-intersecting
        # geometry the moment eye_size got large (first caught not on a
        # synthetic test but on a real photo's detected proportions).
        eye_center = _EYE_L_CENTER if x0 >= 0 else _EYE_R_CENTER
        w_eye = w_eye_l if x0 >= 0 else w_eye_r
        eye_delta = (eye_size - 1) * w_eye
        dx += (x0 - eye_center[0]) * eye_delta
        dy += (y0 - eye_center[1]) * eye_delta
        dz += (z0 - eye_center[2]) * eye_delta

        dx += x0 * (nose_width - 1) * w_nose
        dy += (y0 - _NOSE_BRIDGE_Y) * (nose_length - 1) * w_nose
        dz += (z0 - _CHEEK_Z) * (nose_protrusion - 1) * w_nose

        dx += x0 * (mouth_width - 1) * w_mouth
        dx += x0 * (jaw_width - 1) * w_jaw

        # Every pair of these deltas was individually checked against
        # every extreme (and every real photo-derived combination found
        # during testing) and stays clean — but some 5-way combinations
        # (all of eye_spacing/eye_size/nose_width/nose_length/
        # nose_protrusion at once, near their clamp ceilings, as an
        # actual detected photo produced) still summed to enough combined
        # displacement at a handful of shared-influence vertices to
        # self-intersect, even though no single term or pair did. Rather
        # than keep chasing which N-way combination breaks next, cap the
        # total displacement magnitude directly: this is a safety bound
        # on the deformation, not a per-feature tuning knob, so it stays
        # generous enough that every individual feature's own tested
        # range (see the isolated-parameter renders this was verified
        # against) is nowhere near it alone.
        mag = math.sqrt(dx * dx + dy * dy + dz * dz)
        if mag > _MAX_DISPLACEMENT:
            k = _MAX_DISPLACEMENT / mag
            dx, dy, dz = dx * k, dy * k, dz * k

        out.append(((x0 + dx) * scale, (y0 + dy) * scale, (z0 + dz) * scale))

    return out, _FACES


# Bounds for `random_proportions` — wide enough to give visibly distinct
# faces, narrow enough that every combination still lands within the
# clamp range `face_reconstruction.py` uses for real photos (0.55-1.8 on
# most features), so a "unique" face stays as anatomically plausible as a
# photo-derived one rather than wandering into the geometry's breaking
# strain.
_RANDOM_RANGES: dict[str, tuple[float, float]] = {
    "eye_spacing": (0.85, 1.2),
    "eye_size": (0.8, 1.3),
    "nose_width": (0.75, 1.35),
    "nose_length": (0.8, 1.25),
    "nose_protrusion": (0.7, 1.4),
    "mouth_width": (0.8, 1.25),
    "jaw_width": (0.8, 1.3),
}


def random_proportions(seed: str) -> tuple[dict[str, float], float]:
    """A deterministic "unique face" for any `seed` string — same
    (proportions, height_scale) shape `face_reconstruction.photo_to_
    proportions` returns, so both plug into `build_head_mesh` the same
    way. Same idea as `shapes.procedural_blob`: hash the seed so the same
    text always gives the same face, instead of a fresh random face on
    every rerun."""
    rng = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16))
    proportions = {name: rng.uniform(lo, hi) for name, (lo, hi) in _RANDOM_RANGES.items()}
    height_scale = rng.uniform(0.9, 1.12)
    return proportions, height_scale
