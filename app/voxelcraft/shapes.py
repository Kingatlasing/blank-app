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

def house(width=9, depth=9, wall_h=5, wall="oak_planks", roof="red") -> list[Voxel]:
    wall_c, roof_c = hex_of(wall), hex_of(roof)
    hw, hd = width // 2, depth // 2
    parts = [_hollow_box(-hw, hw + 1, 0, wall_h, -hd, hd + 1, wall_c)]
    # door gap
    door = _box(-1, 1, 0, 2, -hd, -hd + 1, "#00000000")
    door_keys = {(x, y, z) for x, y, z, _ in door}
    base = [v for v in parts[0] if (v[0], v[1], v[2]) not in door_keys]
    # pitched roof, shrinking each layer
    roof_layers = []
    layer_hw, layer_hd = hw + 1, hd + 1
    y = wall_h
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
