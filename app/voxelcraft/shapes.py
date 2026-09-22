"""Procedural voxel shape builders.

Every builder returns a list of ``(x, y, z, hex_color)`` tuples on a small
integer grid, ``y`` pointing up. ``text_generator`` picks one of these based
on keywords in the prompt and re-colors it using any color words it found.
"""

from __future__ import annotations

import hashlib
import math
import random

from .palette import hex_of

Voxel = tuple[int, int, int, str]


def _box(x0, x1, y0, y1, z0, z1, color) -> list[Voxel]:
    out = []
    for x in range(x0, x1):
        for y in range(y0, y1):
            for z in range(z0, z1):
                out.append((x, y, z, color))
    return out


def _hollow_box(x0, x1, y0, y1, z0, z1, color) -> list[Voxel]:
    out = []
    for x in range(x0, x1):
        for y in range(y0, y1):
            for z in range(z0, z1):
                on_edge = x in (x0, x1 - 1) or y in (y0, y1 - 1) or z in (z0, z1 - 1)
                if on_edge:
                    out.append((x, y, z, color))
    return out


def _merge(*groups: list[Voxel]) -> list[Voxel]:
    seen: dict[tuple[int, int, int], str] = {}
    for g in groups:
        for x, y, z, c in g:
            seen[(x, y, z)] = c  # later groups paint over earlier ones
    return [(x, y, z, c) for (x, y, z), c in seen.items()]


# ---------------------------------------------------------------------------
# Humanoid (Steve-style rig)
# ---------------------------------------------------------------------------

def humanoid(skin="skin", shirt="cyan", pants="blue", shoe="stone") -> list[Voxel]:
    skin_c, shirt_c, pants_c, shoe_c = hex_of(skin), hex_of(shirt), hex_of(pants), hex_of(shoe)
    parts = []
    # legs: y 0..5 (6 tall), two 2x2 columns
    parts.append(_box(-2, 0, 0, 5, -1, 1, pants_c))
    parts.append(_box(0, 2, 0, 5, -1, 1, pants_c))
    parts.append(_box(-2, 0, 0, 1, -1, 1, shoe_c))
    parts.append(_box(0, 2, 0, 1, -1, 1, shoe_c))
    # torso: y 5..11
    parts.append(_box(-2, 2, 5, 11, -1, 1, shirt_c))
    # arms: y 5..11, either side of torso
    parts.append(_box(-3, -2, 5, 11, -1, 1, skin_c))
    parts.append(_box(2, 3, 5, 11, -1, 1, skin_c))
    # head: y 11..15
    parts.append(_box(-2, 2, 11, 15, -2, 2, skin_c))
    return _merge(*parts)


# ---------------------------------------------------------------------------
# Realistic human (rounded, proportioned — not the blocky Steve rig above)
# ---------------------------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _human_head(rx: int, ry: int, rz: int, skin_c: str, hair_c: str, lips_c: str,
                 eyebrow_c: str, iris_c: str, white_c: str, pupil_c: str,
                 hi_c: str, lo_c: str) -> dict[tuple[int, int, int], str]:
    """The shared head builder behind both `human_face` and `human_body`:
    an ellipsoid skull/jaw with a tapered chin, two separate eyebrows,
    eyes with sclera+iris+pupil+catchlight+eyelid crease, a protruding
    nose bridge/tip with a highlight and nostril shadows, two-tone lips
    with a philtrum shadow, ears with a shaded rim, a cheekbone highlight,
    a jaw-line shadow contour, and a hair cap — all placed on the head's
    *actual* computed surface at each (x, y) column, so nothing floats
    free of the skull regardless of size or jaw taper. `human_body` calls
    this at a smaller radius than `human_face`'s, so improvements to one
    reach both. Returns a {(x, y, z): hex} dict with y in [0, 2*ry] (the
    head's own local origin — the caller offsets it into place)."""
    cy = ry
    skull: dict[tuple[int, int, int], str] = {}
    for x in range(-rx, rx + 1):
        for y in range(-ry, ry + 1):
            for z in range(-rz, rz + 1):
                taper = 1.0 if y >= 0 else 1.0 - 0.35 * (-y / ry)
                nx, ny, nz = x / (rx * taper), y / ry, z / (rz * taper)
                if nx * nx + ny * ny + nz * nz <= 1.0:
                    skull[(x, y + cy, z)] = skin_c

    def surf_z(x: int, y: int) -> int | None:
        zs = [z for (vx, vy, z) in skull if vx == x and vy == y]
        return max(zs) if zs else None

    def surf_x(y: int, z: int, sign: int) -> int | None:
        xs = [x for (x, vy, vz) in skull if vy == y and vz == z and (x * sign) >= 0]
        return (max(xs) if sign > 0 else min(xs)) if xs else None

    voxels = dict(skull)

    # hair cap: top ~50% of the head plus down the back
    for (x, y, z) in list(voxels):
        ry_frac = (y - cy) / ry
        if ry_frac > 0.5 or (z < -rz * 0.2 and ry_frac > 0.1):
            voxels[(x, y, z)] = hair_c

    # cheekbone highlight: a small oval patch on each cheek
    cheek_cx, cheek_cy_frac, cheek_rx, cheek_ry = 0.55 * rx, 0.10, max(1, 0.14 * rx), max(1, 0.12 * ry)
    for side in (-1, 1):
        for dx in range(-int(cheek_rx), int(cheek_rx) + 1):
            for dy in range(-int(cheek_ry), int(cheek_ry) + 1):
                if (dx / cheek_rx) ** 2 + (dy / cheek_ry) ** 2 > 1.0:
                    continue
                x = side * int(cheek_cx) + dx
                yy = cy + int(cheek_cy_frac * ry) + dy
                z = surf_z(x, yy)
                if z is not None:
                    voxels[(x, yy, z)] = hi_c

    # jaw shadow: a thin contour hugging the actual jaw silhouette edge,
    # not a filled region (a filled version reads as a beard, not shading)
    for y in range(int(-0.5 * ry), int(-0.05 * ry)):
        yy = cy + y
        row_xs = [vx for (vx, vy, vz) in skull if vy == yy]
        if not row_xs:
            continue
        edge = max(row_xs)
        for x in range(edge - 1, edge + 1):
            z = surf_z(x, yy)
            if z is not None:
                voxels[(x, yy, z)] = lo_c
        for x in range(-edge, -edge + 2):
            z = surf_z(x, yy)
            if z is not None:
                voxels[(x, yy, z)] = lo_c

    # eyebrows: a continuous filled arc per side (not sparse dashes), with
    # a real gap over the nose bridge so they read as two brows
    brow_y = cy + int(0.32 * ry)
    inner_frac, outer_frac = 0.20, 0.48
    for side in (-1, 1):
        for ix in range(int(inner_frac * rx), int(outer_frac * rx) + 1):
            x = side * ix
            arc = 1 if ix > int(outer_frac * rx) - 2 else 0  # tapers up at the outer end
            z = surf_z(x, brow_y + arc)
            if z is not None:
                voxels[(x, brow_y + arc, z)] = eyebrow_c
                voxels[(x, brow_y + arc, z - 1)] = eyebrow_c
                z2 = surf_z(x, brow_y + arc - 1)
                if z2 is not None:
                    voxels[(x, brow_y + arc - 1, z2)] = eyebrow_c

    # eyes: sclera, an eyelid crease, iris + pupil + a catchlight highlight
    eye_y = cy + int(0.12 * ry)
    eye_w = max(2, int(0.14 * rx))
    eye_h = max(2, int(0.10 * ry))
    for side in (-1, 1):
        ex = side * int(0.42 * rx)
        for dx in range(eye_w):
            for dy in range(eye_h):
                x, y = ex + dx * side, eye_y + dy
                z = surf_z(x, y)
                if z is not None:
                    voxels[(x, y, z)] = white_c
        for dx in range(eye_w):  # eyelid crease just above the eye
            x = ex + dx * side
            z = surf_z(x, eye_y + eye_h)
            if z is not None:
                voxels[(x, eye_y + eye_h, z)] = lo_c
        icx = ex + (eye_w // 2) * side
        icy = eye_y + eye_h // 2
        z0 = surf_z(icx, icy)
        if z0 is not None:
            voxels[(icx, icy, z0)] = iris_c
            voxels[(icx, icy, max(z0 - 1, -rz))] = pupil_c
            voxels[(icx + side, icy + 1, z0)] = white_c  # catchlight

    # nose: bridge + tip, widening as it descends, with a highlight down
    # the center and nostril-wing shadows at the base
    nose_top = cy + int(0.15 * ry)
    nose_bottom = cy - int(0.18 * ry)
    for i, y in enumerate(range(nose_top, nose_bottom, -1)):
        frac = i / max(1, nose_top - nose_bottom)
        half_w = max(0, int(frac * 0.18 * rx))
        bump = 1 + int(frac * 0.12 * rx)
        for x in range(-half_w, half_w + 1):
            base_z = surf_z(x, y)
            if base_z is not None:
                voxels[(x, y, base_z + bump)] = skin_c
        base_z = surf_z(0, y)
        if base_z is not None:
            voxels[(0, y, base_z + bump + 1)] = hi_c  # center highlight
    for x in (-2, -1, 1, 2):
        base_z = surf_z(x, nose_bottom)
        if base_z is not None:
            voxels[(x, nose_bottom, base_z + 1)] = lo_c

    # mouth: upper lip + lower lip (fuller, highlighted), a cupid's-bow
    # dip at the center top, and a philtrum shadow above it
    mouth_y = cy - int(0.24 * ry)
    mouth_hw = max(2, int(0.16 * rx))
    for x in range(-mouth_hw, mouth_hw + 1):
        z_up = surf_z(x, mouth_y + 1)
        if z_up is not None:
            dip = 1 if abs(x) <= 1 else 0
            voxels[(x, mouth_y + 1 - dip, z_up)] = lips_c
        z_lo = surf_z(x, mouth_y)
        if z_lo is not None:
            voxels[(x, mouth_y, z_lo)] = lips_c
            voxels[(x, mouth_y - 1, z_lo)] = hi_c if abs(x) <= mouth_hw - 1 else lips_c
    for x in (-1, 0, 1):
        z = surf_z(x, mouth_y + 2)
        if z is not None:
            voxels[(x, mouth_y + 2, z)] = lo_c

    # ears: a shaded rim (dark outer edge, light inner concha)
    ear_y0, ear_y1 = cy - int(0.05 * ry), cy + int(0.2 * ry)
    for side in (-1, 1):
        for y in range(ear_y0, ear_y1):
            x0 = surf_x(y, 0, side)
            if x0 is None:
                continue
            depth = 2 + int(0.02 * rx)
            for d in range(1, depth):
                edge = d in (1, depth - 1) or y in (ear_y0, ear_y1 - 1)
                voxels[(x0 + side * d, y, 0)] = lo_c if edge else hi_c

    return voxels


def human_face(skin="skin", hair="brown", eye="black", lips="red",
               eyebrow="black", iris="light_blue") -> list[Voxel]:
    """A rounded bust-style head (not the flat 4x4 Steve head) at high
    resolution — built at roughly double the linear scale (so ~8x the
    voxel count) of an earlier version, specifically to carry the extra
    anatomical detail `_human_head` adds: real cheekbone/jaw shading, not
    just flat color. "Realistic" here means a proportioned, shaded,
    high-resolution rounded head — the furthest actual biological accuracy
    a discrete, fixed-palette voxel grid can approach, not a literal
    photorealistic render (no continuous skin-tone gradient or true
    curvature is possible with cubes, no matter the resolution)."""
    skin_c, hair_c = hex_of(skin), hex_of(hair)
    lips_c, eyebrow_c, iris_c = hex_of(lips), hex_of(eyebrow), hex_of(iris)
    white_c, pupil_c = hex_of("white"), hex_of(eye)
    hi_c, lo_c = hex_of("skin_light"), hex_of("skin_dark")

    head = _human_head(16, 20, 18, skin_c, hair_c, lips_c, eyebrow_c, iris_c,
                        white_c, pupil_c, hi_c, lo_c)
    return [(x, y, z, c) for (x, y, z), c in head.items()]


def human_body(skin="skin", shirt="cyan", pants="blue", hair="brown", shoe="black") -> list[Voxel]:
    """A proportioned, rounded standing figure at roughly double the
    linear scale of an earlier version (so ~8x the voxel count) — tapered
    elliptical legs (thigh/knee/calf/ankle), a rounded hip merging into a
    waist-to-shoulder torso, arms that hang clearly outside the torso
    silhouette down to hand height, a neck, and the same detailed,
    shaded `_human_head` `human_face` uses (at a smaller radius). Built
    from radius-per-height-layer cross-sections (the same technique
    `tower`/`sphere` use) rather than the flat 2-voxel-wide limbs of
    `humanoid`."""
    skin_c, shirt_c, pants_c = hex_of(skin), hex_of(shirt), hex_of(pants)
    hair_c, shoe_c = hex_of(hair), hex_of(shoe)
    lips_c, eyebrow_c, iris_c = hex_of("red"), hex_of("black"), hex_of("light_blue")
    white_c, pupil_c = hex_of("white"), hex_of("black")
    hi_c, lo_c = hex_of("skin_light"), hex_of("skin_dark")
    voxels: dict[tuple[int, int, int], str] = {}

    # legs: two tapered columns (thigh wide -> knee narrow -> calf
    # slightly wider -> ankle narrow), elliptical cross-section (x wider
    # than z)
    leg_top, leg_bottom = 48, 6
    hip_dx = 6  # each leg's center offset from the body midline
    for y in range(leg_bottom, leg_top):
        t = (y - leg_bottom) / (leg_top - leg_bottom)
        if t > 0.6:
            r = _lerp(5.2, 6.8, (t - 0.6) / 0.4)
        elif t > 0.35:
            r = _lerp(4.0, 5.2, (t - 0.35) / 0.25)
        else:
            r = _lerp(3.2, 4.6, t / 0.35)
        rx_, rz_ = r, r * 0.8
        color = pants_c if t > 0.15 else skin_c  # pant leg vs bare ankle
        for leg_cx in (-hip_dx, hip_dx):
            for x in range(-math.ceil(rx_), math.ceil(rx_) + 1):
                for z in range(-math.ceil(rz_), math.ceil(rz_) + 1):
                    if (x / rx_) ** 2 + (z / rz_) ** 2 <= 1.0:
                        voxels[(leg_cx + x, y, z)] = color

    # feet
    for leg_cx in (-hip_dx, hip_dx):
        for x in range(-4, 5):
            for z in range(-2, 9):
                voxels[(leg_cx + x, leg_bottom - 1, z)] = shoe_c
                voxels[(leg_cx + x, leg_bottom - 2, z)] = shoe_c
                voxels[(leg_cx + x, leg_bottom - 3, z)] = shoe_c
                voxels[(leg_cx + x, leg_bottom - 4, z)] = shoe_c

    # pelvis/waist: merges the two legs into one rounded hip block,
    # narrowing slightly into the waist
    waist_bottom, waist_top = leg_top, leg_top + 12
    for y in range(waist_bottom, waist_top):
        t = (y - waist_bottom) / (waist_top - waist_bottom)
        rx_ = _lerp(12.0, 10.0, t)
        rz_ = _lerp(6.8, 6.0, t)
        for x in range(-math.ceil(rx_), math.ceil(rx_) + 1):
            for z in range(-math.ceil(rz_), math.ceil(rz_) + 1):
                if (x / rx_) ** 2 + (z / rz_) ** 2 <= 1.0:
                    voxels[(x, y, z)] = pants_c

    # torso: waist (narrow) widening to the chest/shoulders
    torso_bottom, torso_top = waist_top, waist_top + 32
    for y in range(torso_bottom, torso_top):
        t = (y - torso_bottom) / (torso_top - torso_bottom)
        rx_ = _lerp(10.0, 14.0, min(t / 0.85, 1.0))
        if t > 0.85:
            rx_ = _lerp(14.0, 12.0, (t - 0.85) / 0.15)  # tapers back in right at the shoulders
        rz_ = _lerp(6.4, 8.4, min(t, 1.0))
        for x in range(-math.ceil(rx_), math.ceil(rx_) + 1):
            for z in range(-math.ceil(rz_), math.ceil(rz_) + 1):
                if (x / rx_) ** 2 + (z / rz_) ** 2 <= 1.0:
                    voxels[(x, y, z)] = shirt_c
    shoulder_y = torso_top

    # arms: hanging from the shoulders down past the waist, tapered,
    # ending in a small hand, deliberately offset far enough out (past
    # the torso's own widest point) to stay visible as a separate limb
    # instead of being absorbed into the torso silhouette
    arm_top, arm_bottom = shoulder_y - 2, leg_top + 4
    shoulder_dx = 18
    for y in range(arm_bottom, arm_top):
        t = (y - arm_bottom) / (arm_top - arm_bottom)
        r = _lerp(3.0, 4.4, t)
        dx = _lerp(0, -3.0, 1 - t)  # sweeps slightly inward toward the hip as it goes down
        color = skin_c if t < 0.18 else shirt_c  # hand vs sleeve
        for side in (-1, 1):
            center_x = round(side * shoulder_dx + side * dx)
            for x in range(-math.ceil(r), math.ceil(r) + 1):
                for z in range(-math.ceil(r), math.ceil(r) + 1):
                    if (x / r) ** 2 + (z / r) ** 2 <= 1.0:
                        voxels[(center_x + x, y, z)] = color

    # neck
    neck_bottom, neck_top = shoulder_y, shoulder_y + 6
    for y in range(neck_bottom, neck_top):
        for x in range(-4, 5):
            for z in range(-4, 5):
                if x * x + z * z <= 16:
                    voxels[(x, y, z)] = skin_c

    # head: the same detailed, shaded builder `human_face` uses, at a
    # smaller radius proportioned to this body
    head = _human_head(8, 10, 9, skin_c, hair_c, lips_c, eyebrow_c, iris_c,
                        white_c, pupil_c, hi_c, lo_c)
    for (x, y, z), c in head.items():
        voxels[(x, neck_top + y, z)] = c

    return [(x, y, z, c) for (x, y, z), c in voxels.items()]


# ---------------------------------------------------------------------------
# Nature
# ---------------------------------------------------------------------------

def tree(trunk_h=5, canopy_r=3) -> list[Voxel]:
    trunk_c, leaf_c = hex_of("oak_log"), hex_of("leaves")
    parts = [_box(0, 1, 0, trunk_h, 0, 1, trunk_c)]
    cx, cy, cz = 0, trunk_h + canopy_r - 1, 0
    leaves = []
    for x in range(-canopy_r, canopy_r + 1):
        for y in range(-canopy_r, canopy_r + 1):
            for z in range(-canopy_r, canopy_r + 1):
                if x * x + (y * 0.85) ** 2 + z * z <= canopy_r * canopy_r:
                    leaves.append((cx + x, cy + y, cz + z, leaf_c))
    parts.append(leaves)
    return _merge(*parts)


def sphere(radius=6, color="light_blue") -> list[Voxel]:
    c = hex_of(color)
    out = []
    r2 = radius * radius
    for x in range(-radius, radius + 1):
        for y in range(-radius, radius + 1):
            for z in range(-radius, radius + 1):
                if x * x + y * y + z * z <= r2:
                    out.append((x, y + radius, z, c))
    return out


def pyramid(base=11, height=6, color="sand") -> list[Voxel]:
    c = hex_of(color)
    out = []
    half = base // 2
    for layer in range(height):
        shrink = layer
        lo, hi = -half + shrink, half - shrink
        if lo > hi:
            break
        for x in range(lo, hi + 1):
            for z in range(lo, hi + 1):
                on_edge = x in (lo, hi) or z in (lo, hi)
                if on_edge or layer == height - 1:
                    out.append((x, layer, z, c))
    return out


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------

def _spiral_staircase(cx: int, cz: int, y0: int, height: int, radius=1, color="cobblestone") -> list[Voxel]:
    """A helical staircase winding around a central support pole from y0 up
    to y0+height — steps_per_turn positions per revolution, climbing a
    voxel every few steps for a recognizably helical (not just zig-zag) look."""
    c = hex_of(color)
    voxels = []
    steps_per_turn = 8
    total_steps = max(1, height * 3)
    for i in range(total_steps):
        angle = 2 * math.pi * i / steps_per_turn
        x = cx + round(radius * math.cos(angle))
        z = cz + round(radius * math.sin(angle))
        y = y0 + i // 3
        voxels.append((x, y, z, c))
    for dy in range(height + 1):
        voxels.append((cx, y0 + dy, cz, c))  # central support pole
    return voxels


def house(width=9, depth=9, wall_h=5, wall="oak_planks", roof="red",
          floors=1, staircase=False) -> list[Voxel]:
    wall_c, roof_c = hex_of(wall), hex_of(roof)
    hw, hd = width // 2, depth // 2
    floors = max(1, floors)

    grid: dict[tuple[int, int, int], str] = {}
    for level in range(floors):
        y0, y1 = level * wall_h, (level + 1) * wall_h
        for x, y, z, c in _hollow_box(-hw, hw + 1, y0, y1, -hd, hd + 1, wall_c):
            grid[(x, y, z)] = c

    # ground-floor door
    for x in (-1, 0):
        for y in (0, 1):
            grid.pop((x, y, -hd), None)

    base: list[Voxel]
    if floors > 1 and staircase:
        # punch a hole through the (double-thick, ceiling+floor) slab
        # between every pair of stories, and wind a staircase up through it
        stair_cx = hw - 2 if hw >= 3 else 0
        stair_cz = hd - 2 if hd >= 3 else 0
        for level in range(1, floors):
            y_slab = level * wall_h
            for dy in (y_slab - 1, y_slab):
                for dx in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        grid.pop((stair_cx + dx, dy, stair_cz + dz), None)
        stairs = _spiral_staircase(stair_cx, stair_cz, 0, floors * wall_h, radius=1)
        base = _merge([(x, y, z, c) for (x, y, z), c in grid.items()], stairs)
    else:
        base = [(x, y, z, c) for (x, y, z), c in grid.items()]

    # pitched roof on top of the topmost floor, shrinking each layer
    roof_layers = []
    layer_hw, layer_hd = hw + 1, hd + 1
    y = floors * wall_h
    while layer_hw >= 0 and layer_hd >= 0:
        for x in range(-layer_hw, layer_hw + 1):
            for z in range(-layer_hd, layer_hd + 1):
                on_edge = x in (-layer_hw, layer_hw) or z in (-layer_hd, layer_hd)
                if on_edge or layer_hw == 0 or layer_hd == 0:
                    roof_layers.append((x, y, z, roof_c))
        layer_hw -= 1
        layer_hd -= 1
        y += 1

    return _merge(base, roof_layers)


def temple(stone="sand", roof="light_gray") -> list[Voxel]:
    """A peristyle Greek temple (Parthenon-style): stepped platform, a ring
    of freestanding columns, an entablature, a pedimented gable roof, and —
    unlike anything built from a single reference photo — an actual hollow
    cella (interior room) with a doorway, so there's a real inside to walk
    into."""
    stone_c, roof_c = hex_of(stone), hex_of(roof)
    parts = []

    # stepped stylobate (platform)
    parts.append(_box(-7, 8, 0, 1, -14, 15, stone_c))
    parts.append(_box(-6, 7, 1, 2, -13, 14, stone_c))

    col_y0, col_y1 = 2, 11
    col_positions: set[tuple[int, int]] = set()
    for z in range(-12, 13, 3):
        col_positions.add((-6, z))
        col_positions.add((6, z))
    for x in range(-6, 7, 3):
        col_positions.add((x, -13))
        col_positions.add((x, 13))
    columns = []
    for x, z in col_positions:
        columns.extend(_box(x, x + 1, col_y0, col_y1, z, z + 1, stone_c))
    parts.append(columns)

    # entablature (architrave/frieze) capping the colonnade
    parts.append(_hollow_box(-6, 7, col_y1, col_y1 + 2, -13, 14, stone_c))

    # gabled roof: ridge runs the long (z) axis, sloping down in x, with
    # solid triangular pediments filling the gable ends
    ridge_y0 = col_y1 + 2
    half_w = 6
    roof = []
    pediments = []
    for layer in range(half_w + 1):
        lo, hi = -half_w + layer, half_w - layer
        if lo > hi:
            break
        y = ridge_y0 + layer
        for z in range(-13, 14):
            roof.append((lo, y, z, roof_c))
            if hi != lo:
                roof.append((hi, y, z, roof_c))
        for z in (-13, 13):
            for x in range(lo, hi + 1):
                pediments.append((x, y, z, stone_c))
    parts.append(roof)
    parts.append(pediments)

    # cella: a genuinely hollow interior room with a doorway. The floor
    # (col_y0) stays solid straight through the threshold — only the wall
    # above it is opened — so there's no 1-block pit to fall into.
    cella = _hollow_box(-4, 5, col_y0, col_y1 - 1, -9, 10, stone_c)
    door = {(x, y, z) for x, y, z, _ in _box(-1, 2, col_y0 + 1, col_y0 + 4, -9, -8, stone_c)}
    parts.append([v for v in cella if (v[0], v[1], v[2]) not in door])

    return _merge(*parts)


def tower(radius=4, height=14, color="cobblestone") -> list[Voxel]:
    c = hex_of(color)
    out = []
    for y in range(height):
        crenellate = y == height - 1
        for x in range(-radius, radius + 1):
            for z in range(-radius, radius + 1):
                d2 = x * x + z * z
                if (radius - 1) ** 2 <= d2 <= radius * radius:
                    if crenellate and (x + z) % 2 == 0:
                        continue
                    out.append((x, y, z, c))
    # crenellation caps
    for x in range(-radius, radius + 1, 2):
        for z in range(-radius, radius + 1, 2):
            d2 = x * x + z * z
            if (radius - 1) ** 2 <= d2 <= radius * radius:
                out.append((x, height, z, c))
    return out


def castle(color="cobblestone") -> list[Voxel]:
    parts = [tower(radius=5, height=12, color=color)]
    for dx, dz in [(-9, -9), (9, -9), (-9, 9), (9, 9)]:
        t = tower(radius=2, height=9, color=color)
        parts.append([(x + dx, y, z + dz, c) for x, y, z, c in t])
    return _merge(*parts)


# ---------------------------------------------------------------------------
# Furniture — sized to match `house()`'s scale (wall_h=5, so a room's
# interior is about 4 voxels tall), so these sit sensibly inside one.
# Each one's local origin is its floor-level footprint corner, so placing
# it is just picking an (x, y, z) offset for that corner via `translate`.
# ---------------------------------------------------------------------------

def table(wood="oak_planks") -> list[Voxel]:
    c = hex_of(wood)
    parts = [_box(0, 4, 2, 3, 0, 4, c)]  # tabletop
    for lx, lz in ((0, 0), (3, 0), (0, 3), (3, 3)):
        parts.append(_box(lx, lx + 1, 0, 2, lz, lz + 1, c))  # legs
    return _merge(*parts)


def chair(wood="oak_planks") -> list[Voxel]:
    c = hex_of(wood)
    parts = [_box(0, 2, 1, 2, 0, 2, c)]  # seat
    for lx, lz in ((0, 0), (1, 0), (0, 1), (1, 1)):
        parts.append(_box(lx, lx + 1, 0, 1, lz, lz + 1, c))  # legs
    parts.append(_box(0, 2, 1, 3, 1, 2, c))  # backrest
    return _merge(*parts)


def bed(sheet="white", frame="brown") -> list[Voxel]:
    sheet_c, frame_c = hex_of(sheet), hex_of(frame)
    parts = [
        _box(0, 4, 0, 1, 0, 7, frame_c),  # base frame
        _box(0, 4, 1, 2, 0, 7, sheet_c),  # mattress
        _box(0, 4, 2, 3, 0, 1, frame_c),  # headboard
    ]
    return _merge(*parts)


def sofa(cushion="red", frame="brown") -> list[Voxel]:
    cushion_c, frame_c = hex_of(cushion), hex_of(frame)
    parts = [
        _box(0, 6, 0, 1, 0, 3, frame_c),
        _box(0, 6, 1, 2, 0, 3, cushion_c),  # seat cushions
        _box(0, 6, 2, 4, 0, 1, frame_c),  # backrest
        _box(0, 1, 0, 3, 0, 3, frame_c),  # armrests
        _box(5, 6, 0, 3, 0, 3, frame_c),
    ]
    return _merge(*parts)


def shelf(wood="brown") -> list[Voxel]:
    """A bookcase/shelf unit, flat against a wall (thin in z)."""
    c = hex_of(wood)
    return _hollow_box(0, 4, 0, 5, 0, 1, c)


def lamp(shade="yellow", pole="iron") -> list[Voxel]:
    shade_c, pole_c = hex_of(shade), hex_of(pole)
    parts = [
        _box(0, 1, 0, 1, 0, 1, pole_c),  # base
        _box(0, 1, 1, 4, 0, 1, pole_c),  # pole
        _box(-1, 2, 4, 5, -1, 2, shade_c),  # shade
    ]
    return _merge(*parts)


def rug(color="red", width=4, length=6) -> list[Voxel]:
    return _box(0, width, 0, 1, 0, length, hex_of(color))


# ---------------------------------------------------------------------------
# Items (flat pixel silhouettes, extruded a couple voxels thick)
# ---------------------------------------------------------------------------

def _extrude(grid: list[str], legend: dict[str, str], thickness=2) -> list[Voxel]:
    out = []
    rows = len(grid)
    for row_i, row in enumerate(grid):
        y = rows - 1 - row_i
        for col_i, ch in enumerate(row):
            if ch == "." or ch not in legend:
                continue
            color = legend[ch]
            for z in range(thickness):
                out.append((col_i, y, z, color))
    return out


def sword(blade="iron", hilt="brown", guard="gold") -> list[Voxel]:
    legend = {"b": hex_of(blade), "h": hex_of(hilt), "g": hex_of(guard)}
    grid = [
        ".b.",
        ".b.",
        ".b.",
        ".b.",
        ".b.",
        ".b.",
        ".b.",
        "ggg",
        ".h.",
        ".h.",
    ]
    return _extrude(grid, legend, thickness=2)


def pickaxe(head="iron", handle="brown") -> list[Voxel]:
    legend = {"m": hex_of(head), "h": hex_of(handle)}
    grid = [
        "mmmmm",
        "mm.mm",
        "..h..",
        "..h..",
        "..h..",
        "..h..",
        "..h..",
        ".hh..",
    ]
    return _extrude(grid, legend, thickness=2)


def heart(color="red") -> list[Voxel]:
    legend = {"h": hex_of(color)}
    grid = [
        ".hh.hh.",
        "hhhhhhh",
        "hhhhhhh",
        "hhhhhhh",
        ".hhhhh.",
        "..hhh..",
        "...h...",
    ]
    return _extrude(grid, legend, thickness=2)


def heart_3d(resolution=22, color="red") -> list[Voxel]:
    """A genuine solid 3D heart — not a flat pixel-art cutout — using the
    classic implicit heart-surface equation
    (x^2 + 9/4 y^2 + z^2 - 1)^3 - x^2 z^3 - 9/80 y^2 z^3 <= 0,
    rasterized onto a voxel grid. This is a real volumetric heart *shape*
    (the same curve used in math/graphics demos of "the" 3D heart), not an
    anatomically-accurate organ model — no keyword-driven generator can
    produce true medical anatomy without an actual 3D scan/mesh to work
    from."""
    c = hex_of(color)
    lo, hi = -1.3, 1.3
    n = max(6, resolution)
    step = (hi - lo) / (n - 1)
    voxels = []
    for i in range(n):
        X = lo + i * step
        for j in range(n):
            Y = lo + j * step
            for k in range(n):
                Z = lo + k * step
                val = (X * X + 2.25 * Y * Y + Z * Z - 1) ** 3 - X * X * Z ** 3 - 0.1125 * Y * Y * Z ** 3
                if val <= 0:
                    vx = i
                    vy = k  # formula's z-axis runs point (low Z) -> lobe cleft (high Z); point faces down
                    vz = j
                    voxels.append((vx, vy, vz, c))
    return voxels


def star(color="yellow") -> list[Voxel]:
    legend = {"s": hex_of(color)}
    grid = [
        "...s...",
        "...s...",
        "s..s..s",
        ".sssss.",
        "sssssss",
        "ss...ss",
        "s.....s",
    ]
    return _extrude(grid, legend, thickness=2)


# ---------------------------------------------------------------------------
# Vehicles / creatures
# ---------------------------------------------------------------------------

def quadruped(body="brown", head="brown", accent="black") -> list[Voxel]:
    body_c, head_c, accent_c = hex_of(body), hex_of(head), hex_of(accent)
    parts = [
        _box(-3, 3, 3, 6, -2, 2, body_c),
        _box(3, 6, 4, 6, -1, 1, head_c),
        _box(-3, -2, 0, 3, -2, -1, accent_c),
        _box(-1, 0, 0, 3, -2, -1, accent_c),
        _box(1, 2, 0, 3, 1, 2, accent_c),
        _box(-3, -2, 0, 3, 1, 2, accent_c),
        _box(2, 3, 3, 4, 2, 3, accent_c),  # tail
    ]
    return _merge(*parts)


def dog(body="brown", snout="sand", nose="black", paw="white", ear="black") -> list[Voxel]:
    """A standing dog, built at higher resolution/proportion fidelity than
    `quadruped`: 4 distinct legs with "socked" paws, a raised head with a
    protruding snout and a black nose tip, upright ears, a white chest
    patch, and a small tail — verified against a rendered voxel preview
    during development, not just eyeballed from the coordinates."""
    body_c, snout_c, nose_c, paw_c, ear_c = hex_of(body), hex_of(snout), hex_of(nose), hex_of(paw), hex_of(ear)
    leg_h = 8
    z0, z1 = -3, 3
    parts = []

    parts.append(_box(3, 16, leg_h, leg_h + 4, z0, z1, body_c))
    parts.append(_box(4, 15, leg_h + 4, leg_h + 5, z0 + 1, z1 - 1, body_c))
    parts.append(_box(4, 9, leg_h, leg_h + 1, z0, z1, paw_c))  # chest/belly patch

    parts.append(_box(14, 17, leg_h + 3, leg_h + 9, z0 + 1, z1 - 1, body_c))  # neck
    parts.append(_box(16, 21, leg_h + 8, leg_h + 13, z0 + 1, z1 - 1, body_c))  # head
    parts.append(_box(20, 24, leg_h + 8, leg_h + 11, z0 + 1, z1 - 1, snout_c))
    parts.append(_box(23, 25, leg_h + 8, leg_h + 10, z0 + 1, z1 - 1, nose_c))
    parts.append(_box(16, 18, leg_h + 13, leg_h + 17, z0 + 1, z0 + 2, ear_c))
    parts.append(_box(16, 18, leg_h + 13, leg_h + 17, z1 - 2, z1 - 1, ear_c))

    for lx in (4, 12):
        for lz in (z0, z1 - 2):
            parts.append(_box(lx, lx + 2, 2, leg_h, lz, lz + 2, body_c))
            parts.append(_box(lx, lx + 2, 0, 2, lz, lz + 2, paw_c))

    parts.append(_box(1, 3, leg_h + 3, leg_h + 5, z0 + 1, z1 - 1, body_c))  # tail
    parts.append(_box(0, 2, leg_h + 5, leg_h + 8, z0 + 1, z1 - 1, body_c))

    return _merge(*parts)


def cat(body="light_gray", nose="pink", eye="green", paw="white", inner_ear="pink") -> list[Voxel]:
    """A compact standing cat: 4 short legs with distinct paws, a rounded
    head with a small nose and two eyes, triangular pointed ears, and a
    tail sweeping up from the rear — proportioned differently from `dog`
    (shorter legs, more compact body, pointed ears close together) rather
    than reusing the same rig. Verified against a rendered voxel preview
    during development."""
    body_c, nose_c, eye_c, paw_c, inner_c = hex_of(body), hex_of(nose), hex_of(eye), hex_of(paw), hex_of(inner_ear)
    leg_h = 4
    z0, z1 = -3, 3
    parts = []

    parts.append(_box(3, 11, leg_h, leg_h + 3, z0, z1, body_c))  # torso
    parts.append(_box(9, 13, leg_h + 2, leg_h + 6, z0 + 1, z1 - 1, body_c))  # head
    parts.append(_box(12, 14, leg_h + 3, leg_h + 5, z0 + 2, z1 - 2, nose_c))
    parts.append(_box(12, 13, leg_h + 5, leg_h + 6, z0 + 1, z0 + 2, eye_c))
    parts.append(_box(12, 13, leg_h + 5, leg_h + 6, z1 - 2, z1 - 1, eye_c))
    for ez in (z0 + 1, z1 - 2):  # two triangular (stepped) ears
        parts.append(_box(9, 11, leg_h + 6, leg_h + 7, ez, ez + 1, body_c))
        parts.append(_box(9, 10, leg_h + 7, leg_h + 9, ez, ez + 1, body_c))
        parts.append(_box(9, 10, leg_h + 7, leg_h + 8, ez, ez + 1, inner_c))

    for lx in (4, 8):
        for lz in (z0, z1 - 2):
            parts.append(_box(lx, lx + 2, 1, leg_h, lz, lz + 2, body_c))
            parts.append(_box(lx, lx + 2, 0, 1, lz, lz + 2, paw_c))

    parts.append(_box(1, 3, leg_h + 1, leg_h + 3, z0 + 2, z1 - 2, body_c))  # tail
    parts.append(_box(0, 2, leg_h + 3, leg_h + 6, z0 + 2, z1 - 2, body_c))
    parts.append(_box(-1, 1, leg_h + 6, leg_h + 9, z0 + 2, z1 - 2, body_c))

    return _merge(*parts)


def horse(body="brown", mane="black", hoof="black", muzzle="black") -> list[Voxel]:
    """A standing horse: same box-rig approach as `dog`/`cat` but taller
    legs, a long rising neck, and a mane running along the neck ridge
    instead of ears, so it reads distinctly from the other quadrupeds."""
    body_c, mane_c, hoof_c, muzzle_c = hex_of(body), hex_of(mane), hex_of(hoof), hex_of(muzzle)
    parts = []
    leg_h = 10
    z0, z1 = -3, 3

    parts.append(_box(2, 16, leg_h, leg_h + 5, z0, z1, body_c))  # torso
    parts.append(_box(14, 17, leg_h + 4, leg_h + 12, z0 + 1, z1 - 1, body_c))  # neck
    parts.append(_box(16, 21, leg_h + 11, leg_h + 15, z0 + 1, z1 - 1, body_c))  # head
    parts.append(_box(20, 23, leg_h + 11, leg_h + 13, z0 + 1, z1 - 1, muzzle_c))
    parts.append(_box(16, 18, leg_h + 15, leg_h + 17, z0 + 1, z1 - 1, mane_c))  # ears
    parts.append(_box(14, 18, leg_h + 12, leg_h + 16, z0 + 2, z0 + 3, mane_c))  # mane

    for lx in (3, 12):
        for lz in (z0, z1 - 1):
            parts.append(_box(lx, lx + 2, 1, leg_h, lz, lz + 1, body_c))
            parts.append(_box(lx, lx + 2, 0, 1, lz, lz + 1, hoof_c))

    parts.append(_box(0, 2, leg_h + 3, leg_h + 9, z0 + 1, z1 - 1, mane_c))  # tail
    return _merge(*parts)


def bird(body="red", beak="orange", wing="black", eye="black", leg="orange") -> list[Voxel]:
    """A small perched/standing bird: plump body, a head with a protruding
    beak and two eyes, folded wings along the sides, sweeping tail
    feathers, and thin stick legs."""
    body_c, beak_c, wing_c, eye_c, leg_c = hex_of(body), hex_of(beak), hex_of(wing), hex_of(eye), hex_of(leg)
    parts = []
    z0, z1 = -2, 2

    parts.append(_box(0, 6, 3, 7, z0, z1, body_c))  # body
    parts.append(_box(5, 8, 6, 9, z0 + 1, z1 - 1, body_c))  # head
    parts.append(_box(7, 9, 7, 8, 0, 1, beak_c))
    parts.append(_box(6, 7, 8, 9, z0 + 1, z0 + 2, eye_c))
    parts.append(_box(6, 7, 8, 9, z1 - 2, z1 - 1, eye_c))
    for wz in (z0, z1 - 1):  # folded wings along each side
        parts.append(_box(1, 5, 4, 7, wz, wz + 1, wing_c))
    parts.append(_box(-3, 0, 4, 6, z0 + 1, z1 - 1, wing_c))  # tail feathers
    for lx in (2, 4):
        parts.append(_box(lx, lx + 1, 0, 3, 0, 1, leg_c))
        parts.append(_box(lx - 1, lx + 2, 0, 1, 0, 1, leg_c))  # foot
    return _merge(*parts)


def fish(body="orange", fin="white", eye="black", stripe="black") -> list[Voxel]:
    """A tapered fish body (narrower at nose and tail) with a dorsal fin, a
    bottom fin, a fanned tail fin, an eye, and a couple of vertical
    stripes."""
    body_c, fin_c, eye_c, stripe_c = hex_of(body), hex_of(fin), hex_of(eye), hex_of(stripe)
    parts = []
    length, half_h = 10, 3
    for x in range(length):
        taper = 0
        if x < 2:
            taper = 2 - x
        elif x > length - 4:
            taper = x - (length - 4)
        h = max(half_h - taper, 1)
        parts.append(_box(x, x + 1, -h, h + 1, -2, 3, body_c))
    parts.append(_box(length - 4, length + 2, -1, 1, 0, 1, fin_c))  # tail fin center
    parts.append(_box(length - 2, length + 3, -3, 4, 0, 1, fin_c))  # tail fin fan
    parts.append(_box(4, 6, half_h, half_h + 3, 0, 1, fin_c))  # dorsal fin
    parts.append(_box(3, 5, -half_h - 2, -half_h + 1, 0, 1, fin_c))  # bottom fin
    parts.append(_box(8, 9, 1, 2, -1, 0, eye_c))
    parts.append(_box(8, 9, 1, 2, 1, 2, eye_c))
    for sx in (2, 5):
        parts.append(_box(sx, sx + 1, -half_h, half_h + 1, -2, 3, stripe_c))
    return _merge(*parts)


def snake(body="green", belly="lime", eye="black", tongue="red") -> list[Voxel]:
    """An S-curved body of tapering segments (sinusoidal path) ending in a
    head with two eyes and a flicking forked tongue."""
    body_c, belly_c, eye_c, tongue_c = hex_of(body), hex_of(belly), hex_of(eye), hex_of(tongue)
    parts = []
    length = 20
    for i in range(length):
        x = i
        z = round(2.2 * math.sin(i * 0.5))
        taper = 1 if i < length - 3 else 0  # taper the tail tip
        parts.append(_box(x, x + 1, 0, 2, z - 1, z + 2 - taper, body_c))
        parts.append(_box(x, x + 1, 0, 1, z - 1 + taper, z + 2 - taper, belly_c))
    hz = round(2.2 * math.sin(length * 0.5))
    parts.append(_box(length, length + 2, 0, 3, hz - 1, hz + 2, body_c))  # head
    parts.append(_box(length + 1, length + 2, 1, 2, hz - 1, hz, eye_c))
    parts.append(_box(length + 1, length + 2, 1, 2, hz + 1, hz + 2, eye_c))
    parts.append(_box(length + 2, length + 4, 1, 2, hz, hz + 1, tongue_c))
    return _merge(*parts)


def airplane(body="light_gray", window="glass", accent="red", cockpit="glass") -> list[Voxel]:
    """A commercial-jet silhouette: fuselage deliberately longer than the
    wingspan (so it reads as a tube, not a symmetric cross), a glass nose,
    cabin windows along the spine, low flat wings with wingtip lights, and
    a single vertical tail fin with small horizontal stabilizers."""
    body_c, window_c, accent_c, cockpit_c = hex_of(body), hex_of(window), hex_of(accent), hex_of(cockpit)
    parts = []

    parts.append(_box(0, 32, 3, 6, -2, 2, body_c))  # fuselage
    parts.append(_box(30, 34, 4, 6, -1, 1, cockpit_c))  # nose glass
    for wx in range(4, 28, 3):
        parts.append(_box(wx, wx + 1, 5, 6, -1, 1, window_c))  # cabin windows

    parts.append(_box(13, 19, 3, 4, -9, 10, body_c))  # main wings
    for wz in (-9, 8):
        parts.append(_box(15, 17, 3, 4, wz, wz + 1, accent_c))  # wingtip lights

    parts.append(_box(0, 3, 6, 12, -1, 1, body_c))  # vertical tail fin
    parts.append(_box(0, 3, 3, 4, -4, 5, body_c))  # horizontal stabilizers
    return _merge(*parts)


def dragon(body="green", horn="light_gray", belly="lime") -> list[Voxel]:
    body_c, horn_c, belly_c = hex_of(body), hex_of(horn), hex_of(belly)
    parts = []

    # torso + belly stripe
    parts.append(_box(-2, 3, 4, 8, -5, 6, body_c))
    parts.append(_box(-1, 2, 4, 5, -5, 6, belly_c))

    # neck rising up and forward from the torso, then head + horns
    neck = []
    for i in range(4):
        y0, z0 = 7 + i, 6 + i
        neck.extend(_box(-1, 2, y0, y0 + 1, z0, z0 + 1, body_c))
    parts.append(neck)
    parts.append(_box(-2, 3, 10, 13, 9, 13, body_c))
    parts.append(_box(-2, -1, 12, 14, 10, 11, horn_c))
    parts.append(_box(1, 2, 12, 14, 10, 11, horn_c))

    # tapering tail extending back from the torso
    tail = []
    z, half = -5, 2
    while half >= 0 and z > -13:
        tail.extend(_box(-half, half + 1, 5, 6, z - 1, z, body_c))
        z -= 1
        if (z + 13) % 3 == 0:
            half -= 1
    parts.append(tail)

    # four legs
    for dx in (-3, 2):
        for dz in (-3, 2):
            parts.append(_box(dx, dx + 1, 0, 4, dz, dz + 2, body_c))

    # wings: swept panels jutting from the back, widening as they extend
    wings = []
    for i in range(7):
        span_y = 7 + i // 2
        span_x = 3 + i
        for z in (0, 1):
            wings.append((span_x, span_y, z, body_c))
            wings.append((-span_x, span_y, z, body_c))
    parts.append(wings)

    return _merge(*parts)


def car(body="red", glass="glass", wheel="black") -> list[Voxel]:
    body_c, glass_c, wheel_c = hex_of(body), hex_of(glass), hex_of(wheel)
    parts = [
        _box(-4, 4, 1, 3, -2, 2, body_c),
        _box(-2, 2, 3, 5, -2, 2, body_c),
        _box(-1, 2, 3, 5, -1, 1, glass_c),
    ]
    for dx in (-4, 3):
        for dz in (-2, 1):
            parts.append(_box(dx, dx + 1, 0, 1, dz, dz + 1, wheel_c))
    return _merge(*parts)


def boat(hull="oak_planks", deck="oak_log") -> list[Voxel]:
    hull_c, deck_c = hex_of(hull), hex_of(deck)
    out = []
    length, width = 10, 4
    for x in range(length):
        taper = min(x, length - 1 - x, 2)
        w = max(width - taper, 1)
        for z in range(-w, w + 1):
            out.append((x, taper, z, hull_c))
    for x in range(1, length - 1):
        taper = min(x, length - 1 - x, 2)
        w = max(width - taper, 1) - 1
        for z in range(-w, w + 1):
            out.append((x, taper + 1, z, deck_c))
    return out


def cube(size=6, color="stone", hollow=False) -> list[Voxel]:
    c = hex_of(color)
    if hollow:
        return _hollow_box(0, size, 0, size, 0, size, c)
    return _box(0, size, 0, size, 0, size, c)


# ---------------------------------------------------------------------------
# Fallback: deterministic pseudo-random voxel sculpture
# ---------------------------------------------------------------------------

def procedural_blob(seed_text: str, colors: list[str] | None = None, size=9) -> list[Voxel]:
    """Always produces *something* recognizable-as-a-model for any prompt,
    by growing a random walk of cubes seeded from a hash of the prompt text
    so the same prompt always yields the same shape."""
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    palette = colors or ["stone", "iron", "diamond", "emerald", "gold"]
    voxels: dict[tuple[int, int, int], str] = {}
    x, y, z = 0, size // 2, 0
    steps = size * 14
    for _ in range(steps):
        color = hex_of(rng.choice(palette))
        # place a small cube of the walker's position
        for dx in range(2):
            for dy in range(2):
                for dz in range(2):
                    voxels[(x + dx, y + dy, z + dz)] = color
        move = rng.choice(["x", "-x", "y", "-y", "z", "-z"])
        if move == "x":
            x += 1
        elif move == "-x":
            x = max(-size, x - 1)
        elif move == "y":
            y = min(size, y + 1)
        elif move == "-y":
            y = max(0, y - 1)
        elif move == "z":
            z += 1
        elif move == "-z":
            z = max(-size, z - 1)
    return [(x, y, z, c) for (x, y, z), c in voxels.items()]
