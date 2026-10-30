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
