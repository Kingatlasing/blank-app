"""Small geometric utilities shared by the generators."""

from __future__ import annotations

Voxel = tuple[int, int, int, str]


def scale_voxels(voxels: list[Voxel], factor: int) -> list[Voxel]:
    """Blow each voxel up into a factor^3 cluster of voxels (chunkier model)."""
    if factor <= 1:
        return voxels
    out = []
    for x, y, z, c in voxels:
        bx, by, bz = x * factor, y * factor, z * factor
        for dx in range(factor):
            for dy in range(factor):
                for dz in range(factor):
                    out.append((bx + dx, by + dy, bz + dz, c))
    return out


def normalize(voxels: list[Voxel]) -> list[Voxel]:
    """Shift a model so its minimum x/y/z sit at 0 (y also floored at 0)."""
    if not voxels:
        return voxels
    min_x = min(v[0] for v in voxels)
    min_y = min(v[1] for v in voxels)
    min_z = min(v[2] for v in voxels)
    return [(x - min_x, y - min_y, z - min_z, c) for x, y, z, c in voxels]


def voxel_count_limit(voxels: list[Voxel], limit: int) -> tuple[list[Voxel], bool]:
    """Guard against pathologically large models blowing up the browser."""
    if len(voxels) <= limit:
        return voxels, False
    return voxels[:limit], True
