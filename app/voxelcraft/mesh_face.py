"""A genuine polygon-mesh human head: real (x, y, z) vertices and triangle
faces at arbitrary angles, not axis-aligned voxel cubes.

This exists because voxels — even at very high resolution — can't produce
the look of a sculpted low-poly head (flat facets meeting at real angles,
a smoothly tapered jaw, a point-like crown/chin from a triangle fan): a
cube grid is fundamentally the wrong primitive for that, regardless of how
small the cubes get. This module builds that shape directly instead.

The technique: a UV-sphere parametrization (latitude rings from a top
pole/crown to a bottom pole/chin, longitude segments around), which
already matches the reference low-poly head style well on its own — the
pole triangle-fans are exactly the "rings converging to a point" look a
sculpted head's crown and chin actually have. `_width_factor` reshapes the
per-latitude radius so it stays close to full width through the
forehead/cheek/jaw range (unlike a raw sphere, which shrinks continuously
toward each pole) — that's what makes it read as a head and not an egg.
Facial features (brow, eye sockets, nose, cheeks, mouth, chin, ears) are
then layered on as localized Gaussian bumps/dents in that per-latitude,
per-longitude radius.

Every fix in this file's history came from actually rendering the
intermediate mesh and looking at it (front/side/top + a real z-buffered
rasterizer, not just 3D-camera renders, which turned out to hide real
defects and show fake ones depending on the angle) — including a real bug
worth documenting: splitting every quad along the same fixed diagonal
folded a visible crease into any concave (saddle-curved) patch, like the
rim of an eye socket. The fix is a standard one — pick whichever diagonal
is shorter, per quad — but it's not optional at this curvature; without
it, the eye/nose region rendered as a garbled mess of inverted triangles
in more than one independent renderer, confirming it was a real geometry
defect, not a rendering-angle artifact.

"Realistic" here means a proportioned, faceted, low-poly *sculpt* in the
style of the reference images this was built against — not a literal
photorealistic scan, and not a reconstruction of any specific real
person's face (this module has no way to do that; it designs a face from
proportions and Gaussian feature placement, the same way the voxel shape
library designs a house from wall/roof primitives).
"""

from __future__ import annotations

import math

Vertex = tuple[float, float, float]
Face = tuple[int, int, int]

# (t, width_factor) keypoints, t = theta/pi (0 = crown, 1 = chin), piecewise
# linear between them. This is the actual head-shape control: unlike a raw
# sphere (whose radius ~ sin(theta) always shrinks toward each pole), this
# stays close to full width through the forehead/cheek/jaw range and only
# tapers in the narrow band right at the crown and right at the chin.
_WIDTH_KEYPOINTS = [
    (0.00, 0.0), (0.07, 0.82), (0.16, 0.94), (0.28, 1.0), (0.46, 1.03),
    (0.60, 0.95), (0.72, 0.78), (0.86, 0.5), (0.95, 0.22), (1.00, 0.0),
]

# name -> [theta0, phi0, sigma_theta, sigma_phi, amplitude] — phi0=0 is
# straight ahead (+z), positive phi sweeps toward +x. sigma_theta/sigma_phi
# must be comfortably wider than the mesh's own vertex spacing
# (2*pi/n_segments, pi/n_rings): a Gaussian narrower than that plunges a
# single vertex while its neighbors barely move, which (combined with the
# fixed-diagonal bug described in the module docstring) is what produced
# the garbled-mesh defect during development.
#
# Keyed by name (rather than a plain list) so `face_reconstruction.py` can
# retarget specific features — widen eye spacing, scale nose size, etc. —
# from measurements taken off a real photo, without touching the others.
_FEATURES: dict[str, list[float]] = {
    "brow": [1.05, 0.0, 0.10, 0.55, 0.06],
    "eye_l": [1.18, 0.40, 0.15, 0.24, -0.15],
    "eye_r": [1.18, -0.40, 0.15, 0.24, -0.15],
    "nose": [1.40, 0.0, 0.32, 0.16, 0.28],
    "cheek_l": [1.58, 0.52, 0.18, 0.22, 0.08],
    "cheek_r": [1.58, -0.52, 0.18, 0.22, 0.08],
    "mouth": [1.88, 0.0, 0.11, 0.20, -0.08],
    "chin": [2.05, 0.0, 0.12, 0.22, 0.06],
    "ear_l": [1.45, 1.5, 0.18, 0.19, 0.20],
    "ear_r": [1.45, -1.5, 0.18, 0.19, 0.20],
}

# Which single scalar in each feature's [theta0, phi0, sigma_t, sigma_p,
# amp] a given proportion knob adjusts, and how — used by
# `_apply_proportions`. "amp" knobs change feature prominence (nose size,
# mouth width read as amplitude+sigma together); "phi0" knobs change
# position (eye/ear spacing away from center).
_PROPORTION_TARGETS: dict[str, list[tuple[str, str]]] = {
    "eye_spacing": [("eye_l", "phi0"), ("eye_r", "phi0")],
    "eye_size": [("eye_l", "amp"), ("eye_r", "amp")],
    "nose_width": [("nose", "sigma_p")],
    "nose_length": [("nose", "sigma_t")],
    "nose_protrusion": [("nose", "amp")],
    "mouth_width": [("mouth", "sigma_p")],
    "jaw_width": [("cheek_l", "amp"), ("cheek_r", "amp")],
}
_FIELD_INDEX = {"theta0": 0, "phi0": 1, "sigma_t": 2, "sigma_p": 3, "amp": 4}


def _apply_proportions(features: dict[str, list[float]], proportions: dict[str, float]) -> None:
    """Mutates `features` in place: each `proportions` value is a
    multiplier (1.0 = unchanged) on the target field(s) `_PROPORTION_TARGETS`
    names, except `phi0` targets, which are multiplicative on position
    *away from center* (so eye spacing widens/narrows symmetrically rather
    than sliding sideways)."""
    for name, scale in proportions.items():
        for feature_name, field in _PROPORTION_TARGETS.get(name, []):
            idx = _FIELD_INDEX[field]
            features[feature_name][idx] *= scale


def _width_factor(theta: float) -> float:
    t = theta / math.pi
    pts = _WIDTH_KEYPOINTS
    for (t0, f0), (t1, f1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            frac = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return f0 + (f1 - f0) * frac
    return pts[-1][1]


def _gauss(theta: float, phi: float, theta0: float, phi0: float,
           sigma_t: float, sigma_p: float, amp: float) -> float:
    dphi = (phi - phi0 + math.pi) % (2 * math.pi) - math.pi  # shortest angular diff
    return amp * math.exp(-((theta - theta0) ** 2 / sigma_t ** 2 + dphi ** 2 / sigma_p ** 2))


def _dist2(p: Vertex, q: Vertex) -> float:
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2


def build_head_mesh(
    n_rings: int = 22, n_segments: int = 26,
    rx: float = 1.05, ry: float = 1.15, rz: float = 0.95,
    proportions: dict[str, float] | None = None,
) -> tuple[list[Vertex], list[Face]]:
    """A head as (vertices, triangle faces). y is up, +z is the face's
    front, scaled to roughly [-1.2, 1.2] on every axis — the caller scales
    this to whatever final size it wants.

    `proportions`, if given, retargets specific features by a multiplier
    each (1.0 = the generic default) — see `_PROPORTION_TARGETS` for the
    recognized keys. This is what lets `face_reconstruction.py` shape the
    generic parametric head toward a specific photo's measured
    proportions (face width/height, eye spacing, nose/mouth size, jaw
    width) without hand-writing a second copy of the whole feature set."""
    features = {name: list(vals) for name, vals in _FEATURES.items()}
    if proportions:
        _apply_proportions(features, proportions)

    verts: list[Vertex] = []
    faces: list[Face] = []

    def radius(theta: float, phi: float) -> float:
        r = _width_factor(theta)
        for (t0, p0, st, sp, amp) in features.values():
            r += _gauss(theta, phi, t0, p0, st, sp, amp)
        return max(r, 0.02)

    def point(theta: float, phi: float) -> Vertex:
        r = radius(theta, phi)
        x = rx * r * math.sin(phi)
        y = ry * math.cos(theta)
        z = rz * r * math.cos(phi)
        return (x, y, z)

    verts.append(point(0.0, 0.0))  # top pole (crown)
    ring_start: dict[int, int] = {}
    for i in range(1, n_rings):
        theta = i * math.pi / n_rings
        ring_start[i] = len(verts)
        for j in range(n_segments):
            phi = j * 2 * math.pi / n_segments
            verts.append(point(theta, phi))
    bottom_pole_idx = len(verts)
    verts.append(point(math.pi, 0.0))  # bottom pole (chin)

    r1 = ring_start[1]
    for j in range(n_segments):
        a, b = r1 + j, r1 + (j + 1) % n_segments
        faces.append((0, b, a))

    for i in range(1, n_rings - 1):
        r_i, r_ip1 = ring_start[i], ring_start[i + 1]
        for j in range(n_segments):
            a, b = r_i + j, r_i + (j + 1) % n_segments
            c, d = r_ip1 + j, r_ip1 + (j + 1) % n_segments
            # A quad on a curved surface isn't flat, so the diagonal choice
            # matters — see the module docstring. Picking the shorter one
            # keeps both triangles closer to co-planar and avoids a fold.
            if _dist2(verts[a], verts[d]) <= _dist2(verts[b], verts[c]):
                faces.append((a, b, d))
                faces.append((a, d, c))
            else:
                faces.append((a, b, c))
                faces.append((b, d, c))

    r_last = ring_start[n_rings - 1]
    for j in range(n_segments):
        a, b = r_last + j, r_last + (j + 1) % n_segments
        faces.append((a, bottom_pole_idx, b))

    return verts, faces
