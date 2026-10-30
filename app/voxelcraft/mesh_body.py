"""A genuine polygon-mesh human body: real (x, y, z) vertices and triangle
faces decimated from a real reference mesh, then locally deformed per
proportion -- the same technique mesh_face.py uses for the head, applied to
a full body.

The base mesh is `assets/body.json`, baked offline (see
scripts/bake_body_asset.py-equivalent work in the repo history) from
MakeHuman's `data/3dobjs/base.obj` "body" group: a real, artist-modeled
reference body mesh (https://github.com/makehumancommunity/makehuman),
explicitly released as CC0 (public domain) in September 2020 per that
file's own header. It was decimated from ~13,400 to ~1,000 vertices via
quadric edge-collapse and is watertight both before and after (unlike the
open-neck head bust used for the face, this source mesh is a complete,
closed character body, which is why the head is part of this mesh rather
than the separately-built, more detailed face mesh -- grafting the two
together would mean welding two independently-decimated, differently
shaped neck openings, which is a real seam-quality risk left for a
follow-up rather than gambled on here).

Landmarks (crotch height, shoulder joint positions, foot/crown extent) were
measured directly from the real reference mesh's geometry via cross-section
analysis (trimesh mesh.section at varying heights, watching where the leg
cross-sections merge into one torso loop for the crotch, and where the arm
cross-sections separate from the torso loop for the shoulder joints) rather
than guessed.

Two deformation strategies are used, matching what each body part actually
needs:
- Torso width bands (shoulder/chest/waist/hip) use the same compact,
  Gaussian-falloff-by-height technique as mesh_face.py's eye/nose/mouth
  regions: a vertex's weight depends on how close its height is to the
  band's center, and its x (or x and z) offset from the centerline is
  scaled by that weight. This works well for compact regions.
- Limbs (arms, legs) do NOT work with that technique: a Gaussian falloff
  compact enough to be a useful "region" leaves the far end of a long limb
  (a fingertip 7+ units from the shoulder joint) barely affected, which
  isn't what "arm length" should mean. Instead, a limb uses a hard
  geometric membership mask (which side of a position threshold a vertex
  falls on, ramped smoothly right at the boundary to avoid a seam) so the
  *entire* limb, fingertips and toes included, scales together as one
  unit around its joint.

Real anatomical proportions used for the "male" / "female" presets below
are cited in _SEX_PRESETS -- see the comment there for exactly which
numbers are measured research findings versus reasoned, direction-correct
adjustments (the same honesty distinction the face module draws for its
own eye/lip corrections).
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

Vertex = tuple[float, float, float]
Face = tuple[int, int, int]

with (Path(__file__).parent / "assets" / "body.json").open(encoding="utf-8") as _fh:
    _ASSET = json.load(_fh)

_BASE_VERTS: list[Vertex] = [tuple(v) for v in _ASSET["vertices"]]
_FACES: list[Face] = [tuple(f) for f in _ASSET["faces"]]
_LM = _ASSET["landmarks"]

_CROWN_Y = _LM["crown"][1]
_FEET_Y = _LM["feet_y"]
_CROTCH_Y = _LM["crotch_y"]
_SHOULDER_R = tuple(_LM["shoulder_r"])
_SHOULDER_L = tuple(_LM["shoulder_l"])
_SHOULDER_Y = _SHOULDER_R[1]

# Torso band centers, in head-height units measured from real geometry
# (crotch_y is a measured landmark; total height / 8 approximates one real
# head-height per the standard "8 heads tall" figure-drawing convention
# used throughout this module as the unit for spacing the remaining bands,
# since only crotch and shoulder were themselves directly measurable from
# cross-sections).
_HEAD_UNIT = (_CROWN_Y - _FEET_Y) / 8.0
_CHEST_Y = _SHOULDER_Y - 0.7 * _HEAD_UNIT
_WAIST_Y = _SHOULDER_Y - 1.9 * _HEAD_UNIT
_HIP_Y = _CROTCH_Y + 0.6 * _HEAD_UNIT
_KNEE_Y = _CROTCH_Y - (_CROTCH_Y - _FEET_Y) * 0.5

_TORSO_RADIUS = 1.15 * _HEAD_UNIT
_MAX_DISPLACEMENT = 1.4 * _HEAD_UNIT

# how far outside the torso silhouette (in x) a vertex must sit to count as
# fully "arm", and how wide the smooth ramp into that is -- both in the
# same real units as the mesh itself, calibrated from the measured
# shoulder-joint x-offset (~0.30) so the ramp sits right at the armpit
_ARM_MASK_START = 0.20
_ARM_MASK_RAMP = 0.35
_LEG_MASK_RAMP = 0.6 * _HEAD_UNIT

# the x-only arm mask above also matches wide hip/thigh vertices (a thigh
# sits just as far from the centerline in x as an arm does), which were
# getting wrongly pulled toward the shoulder joint -- a real bug found via
# the flip-detection sweep below, not a hypothetical. A vertex only counts
# as "arm" if it's also within the arm's actual vertical span, tapered at
# the shoulder/fingertip ends the same way the x-mask tapers at the armpit.
_ARM_Y_CENTER = (_SHOULDER_Y + _LM["fingertip_r"][1]) / 2
_ARM_Y_HALF = (_SHOULDER_Y - _LM["fingertip_r"][1]) / 2 + 0.3
_ARM_Y_RAMP = 0.5


def _falloff(dy: float, radius: float) -> float:
    return math.exp(-(dy * dy) / (radius * radius))


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def build_body_mesh(
    proportions: dict[str, float] | None = None, height: float = 1.0
) -> tuple[list[Vertex], list[Face]]:
    p = proportions or {}
    shoulder_width = p.get("shoulder_width", 1.0)
    chest_width = p.get("chest_width", 1.0)
    waist_width = p.get("waist_width", 1.0)
    hip_width = p.get("hip_width", 1.0)
    arm_length = p.get("arm_length", 1.0)
    leg_length = p.get("leg_length", 1.0)

    out: list[Vertex] = []
    for x0, y0, z0 in _BASE_VERTS:
        w_shoulder = _falloff(y0 - _SHOULDER_Y, _TORSO_RADIUS)
        w_chest = _falloff(y0 - _CHEST_Y, _TORSO_RADIUS)
        w_waist = _falloff(y0 - _WAIST_Y, _TORSO_RADIUS)
        w_hip = _falloff(y0 - _HIP_Y, _TORSO_RADIUS)

        demand = w_shoulder + w_chest + w_waist + w_hip
        if demand > 1.0:
            k = 1.0 / demand
            w_shoulder *= k
            w_chest *= k
            w_waist *= k
            w_hip *= k

        dx = x0 * (shoulder_width - 1) * w_shoulder
        dx += x0 * (chest_width - 1) * w_chest
        dx += x0 * (waist_width - 1) * w_waist
        dz = z0 * (waist_width - 1) * w_waist * 0.5
        dx += x0 * (hip_width - 1) * w_hip
        dy = 0.0

        # arms: hard membership mask (which side of the torso silhouette),
        # ramped smoothly at the armpit boundary, then a full 3D radial
        # scale around that side's own shoulder joint so the whole limb
        # (including the hand) moves together
        joint = _SHOULDER_R if x0 < 0 else _SHOULDER_L
        w_arm_x = _clamp01((abs(x0) - _ARM_MASK_START) / _ARM_MASK_RAMP)
        w_arm_y = _clamp01(1 - max(0.0, abs(y0 - _ARM_Y_CENTER) - _ARM_Y_HALF) / _ARM_Y_RAMP)
        w_arm = w_arm_x * w_arm_y
        dx += (x0 - joint[0]) * (arm_length - 1) * w_arm
        dy += (y0 - joint[1]) * (arm_length - 1) * w_arm
        dz += (z0 - joint[2]) * (arm_length - 1) * w_arm

        # legs: hard membership mask (below the crotch line), ramped
        # smoothly, then a vertical-only scale from the crotch line (legs
        # hang straight down in this reference pose, so no radial 3D
        # scale is needed the way the angled arms needed one)
        w_leg = _clamp01((_CROTCH_Y - y0) / _LEG_MASK_RAMP)
        dy += (y0 - _CROTCH_Y) * (leg_length - 1) * w_leg

        mag = math.sqrt(dx * dx + dy * dy + dz * dz)
        if mag > _MAX_DISPLACEMENT:
            k = _MAX_DISPLACEMENT / mag
            dx, dy, dz = dx * k, dy * k, dz * k

        out.append(((x0 + dx) * height, (y0 + dy) * height, (z0 + dz) * height))

    return out, _FACES


# Real proportions this module draws on (see module docstring for the
# figure-drawing source): total height ~= 8 head-heights; adult males
# average ~7-8% taller than adult females; male shoulder width trends
# 2.5-3 head-widths versus female 2-2.5 (a ~15-20% relative difference),
# with male shoulders noticeably wider than the pelvis and female
# shoulder/pelvis width much closer together. The multipliers below are
# this module's own reasoned translation of those *directional* real
# findings onto this specific, already-roughly-neutral base mesh (an
# actual precise average-population multiplier isn't something a single
# reference mesh or a short research pass can responsibly claim) -- the
# same honesty distinction the face module draws for its own
# reference-informed-but-not-measured lip correction.
_SEX_PRESETS = {
    "male": {
        "height": 1.05,
        "shoulder_width": 1.12,
        "chest_width": 1.08,
        "waist_width": 0.96,
        "hip_width": 0.90,
        "arm_length": 1.03,
        "leg_length": 1.02,
    },
    "female": {
        "height": 0.95,
        "shoulder_width": 0.92,
        "chest_width": 0.95,
        "waist_width": 1.0,
        "hip_width": 1.12,
        "arm_length": 0.97,
        "leg_length": 0.98,
    },
}

_RANDOM_RANGES = {
    "shoulder_width": (0.85, 1.25),
    "chest_width": (0.85, 1.2),
    "waist_width": (0.8, 1.25),
    "hip_width": (0.8, 1.3),
    "arm_length": (0.9, 1.15),
    "leg_length": (0.9, 1.15),
}


def sex_proportions(sex: str) -> tuple[dict[str, float], float]:
    preset = _SEX_PRESETS[sex]
    proportions = {k: v for k, v in preset.items() if k != "height"}
    return proportions, preset["height"]


def random_proportions(seed: str, sex: str) -> tuple[dict[str, float], float]:
    rng = random.Random(int(hashlib.sha256((seed + sex).encode("utf-8")).hexdigest(), 16))
    base, base_height = sex_proportions(sex)
    proportions = {}
    for name, (lo, hi) in _RANDOM_RANGES.items():
        # jitter around this sex's own preset rather than the generic
        # random range, so a random male stays recognizably male-shaped
        jitter = rng.uniform(0.85, 1.15)
        proportions[name] = max(lo, min(hi, base[name] * jitter))
    height = base_height * rng.uniform(0.93, 1.07)
    return proportions, height
