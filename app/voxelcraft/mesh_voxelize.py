"""A blocky Minecraft-style head voxelized from the real polygon-mesh face
(`mesh_face.py`), instead of a flat 8x8x8 cube with a hand-painted pixel-art
texture. Minecraft's own player-skin format *is* a flat textured cube (a
head is just a cube with a 2D image wrapped on it — `shapes.minecraft_face`
is accurate to that), but it is not the only way to build something blocky:
plenty of real Minecraft builds and resource packs sculpt a head out of many
small cubes to actually show a nose, jaw, and ears, which is what this
module does — quantizing `mesh_face`'s real, landmark-bearing geometry
(including whatever `proportions` a caller passes, so a random or
photo-matched face voxelizes into a recognizably different blocky shape,
not always the same cube) down to a voxel grid, so the bump of the nose,
the taper of the jaw, and the ears are real consequences of the mesh's own
shape, not a handful of pre-placed pixels.

**Voxelizing the mesh.** No numpy/trimesh dependency at runtime (matching
`mesh_face.py`'s own stdlib-only design — this is a per-request, possibly
randomized shape, not something that can be pre-baked once offline).
Standard column-wise ray casting: for each (x, z) grid column, test every
triangle for whether its 2D (x, z) projection contains that column's
center (a barycentric point-in-triangle test, the same kind `raster.py`-
style rasterizers use); each hit contributes one y-crossing, found by
interpolating the triangle's y at that (x, z) with the same barycentric
weights. Sorting a column's crossings and pairing them up (1st-2nd,
3rd-4th, ...) gives its inside/outside intervals by the standard even-odd
rule — one ray per column rather than one ray per voxel cell, which is
what keeps this fast enough in pure Python (a few hundred columns against
~1000 triangles, not grid_x * grid_y * grid_z against them).

**Coloring it.** The mesh itself carries no color — it's one uniform
skin-tone sculpt in the realistic viewer — so eyes/eyebrows/mouth/nose-
shadow/hairline are placed using the *same real 3D landmarks*
`mesh_face.py` already uses to steer its deformation (eye corners, mouth
corners, nose bridge/tip, forehead/crown, ears), not a fixed pixel
template: each landmark is mapped to its nearest grid column, and the
*frontmost occupied voxel in that column* (largest z — the mesh's own
"toward the viewer" direction) is painted, so a feature lands in the right
place on the real shape underneath it rather than a generic flat cube.
"""
from __future__ import annotations

from app.voxelcraft import mesh_face
from app.voxelcraft.palette import hex_of

Voxel = tuple[int, int, int, str]

GRID_X = 16
GRID_Y = 18
GRID_Z = 16

# margin (in the mesh's own baked units, where crown-to-chin = 2.3) added
# around the tight per-call bounding box so the voxelized surface doesn't
# get clipped flush against the grid edge
_MARGIN = 0.12


def _bary_2d(px: float, pz: float, ax: float, az: float, bx: float, bz: float, cx: float, cz: float):
    denom = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
    if abs(denom) < 1e-12:
        return None
    w0 = ((bz - cz) * (px - cx) + (cx - bx) * (pz - cz)) / denom
    w1 = ((cz - az) * (px - cx) + (ax - cx) * (pz - cz)) / denom
    w2 = 1.0 - w0 - w1
    eps = 1e-6
    if w0 < -eps or w1 < -eps or w2 < -eps:
        return None
    return w0, w1, w2


def _cast_axis(
    vertices: list[mesh_face.Vertex], faces: list[mesh_face.Face],
    ray_axis: int, bbox: tuple[float, float, float, float, float, float],
    dims: tuple[int, int, int],
) -> set[tuple[int, int, int]]:
    """Ray-casts along one axis (0=x, 1=y, 2=z) and returns the set of
    occupied (ix,iy,iz) cells, by the same column/even-odd technique the
    module docstring describes (generalized to cast along any axis, not
    just y)."""
    u, v = (a for a in range(3) if a != ray_axis)  # the two "column" axes
    lo = [bbox[0], bbox[2], bbox[4]]
    hi = [bbox[1], bbox[3], bbox[5]]
    steps = [(hi[a] - lo[a]) / dims[a] for a in range(3)]

    occupied: set[tuple[int, int, int]] = set()
    for iu in range(dims[u]):
        pu = lo[u] + (iu + 0.5) * steps[u]
        for iv in range(dims[v]):
            pv = lo[v] + (iv + 0.5) * steps[v]
            hits: list[float] = []
            for ia, ib, ic in faces:
                a, b, c = vertices[ia], vertices[ib], vertices[ic]
                w = _bary_2d(pu, pv, a[u], a[v], b[u], b[v], c[u], c[v])
                if w is None:
                    continue
                w0, w1, w2 = w
                hits.append(w0 * a[ray_axis] + w1 * b[ray_axis] + w2 * c[ray_axis])
            if not hits:
                continue
            hits.sort()
            hits = hits[: len(hits) // 2 * 2]  # drop a straggler from a degenerate/edge-on hit
            for k in range(0, len(hits), 2):
                r_lo, r_hi = hits[k], hits[k + 1]
                ir_lo = max(0, int((r_lo - lo[ray_axis]) / steps[ray_axis]))
                ir_hi = min(dims[ray_axis] - 1, int((r_hi - lo[ray_axis]) / steps[ray_axis]))
                for ir in range(ir_lo, ir_hi + 1):
                    cell = [0, 0, 0]
                    cell[ray_axis], cell[u], cell[v] = ir, iu, iv
                    occupied.add(tuple(cell))
    return occupied


def _voxelize(vertices: list[mesh_face.Vertex], faces: list[mesh_face.Face], y_lo: float, y_hi: float):
    """Returns (occupied: set[(ix,iy,iz)], bbox: (x_lo,x_hi,y_lo,y_hi,z_lo,z_hi)).

    Casts along all 3 axes and unions the results, not just straight down
    (y). A single direction leaves real gaps at any concavity it runs
    parallel to — the eye sockets and nose bridge are exactly that, and a
    y-only first version showed a real hole through the face at eye height
    when viewed from the side (an actual gap in the occupied set, not a
    rendering artifact — confirmed by checking the raw data before fixing
    it this way). Casting along x and z too fills those gaps, since a
    concavity that defeats a straight-down ray rarely also runs parallel
    to the other two directions at the same spot."""
    xs = [v[0] for v in vertices]
    zs = [v[2] for v in vertices]
    x_lo, x_hi = min(xs) - _MARGIN, max(xs) + _MARGIN
    z_lo, z_hi = min(zs) - _MARGIN, max(zs) + _MARGIN
    bbox = (x_lo, x_hi, y_lo, y_hi, z_lo, z_hi)
    dims = (GRID_X, GRID_Y, GRID_Z)

    occupied: set[tuple[int, int, int]] = set()
    for axis in (1, 0, 2):
        occupied |= _cast_axis(vertices, faces, axis, bbox, dims)

    return occupied, bbox


def _grid_index(point: mesh_face.Vertex, bbox) -> tuple[int, int]:
    x_lo, x_hi, y_lo, y_hi, _, _ = bbox
    ix = int((point[0] - x_lo) / (x_hi - x_lo) * GRID_X)
    iy = int((point[1] - y_lo) / (y_hi - y_lo) * GRID_Y)
    return max(0, min(GRID_X - 1, ix)), max(0, min(GRID_Y - 1, iy))


def _frontmost(occupied: set[tuple[int, int, int]], ix: int, iy: int, spread: int = 0) -> list[tuple[int, int, int]]:
    """The surface voxel(s) nearest the viewer (max z) at/near a grid
    column — `spread` widens the search to a small (2*spread+1)-wide
    neighborhood so a single landmark can paint a short feature (an
    eyebrow, a mouth) rather than exactly one voxel."""
    out = []
    for dx in range(-spread, spread + 1):
        best_iz = -1
        for (ox, oy, oz) in occupied:
            if ox == ix + dx and oy == iy and oz > best_iz:
                best_iz = oz
        if best_iz >= 0:
            out.append((ix + dx, iy, best_iz))
    return out


def minecraft_face_from_mesh(
    proportions: dict[str, float] | None = None,
    ry: float = 1.15,
    skin: str = "skin", hair: str = "brown", eye: str = "black", mouth: str = "skin_dark",
) -> list[Voxel]:
    """The blocky-Minecraft counterpart to `mesh_face.build_head_mesh`:
    same `proportions`/`ry` (so a random seed or photo-matched face
    produces a correspondingly different blocky head, not always the same
    cube), voxelized and colored as described in the module docstring."""
    vertices, faces = mesh_face.build_head_mesh(proportions=proportions, ry=ry)
    lm = mesh_face._LM

    y_lo = lm["chin_bottom"][1] - _MARGIN
    y_hi = lm["crown"][1] + _MARGIN
    occupied, bbox = _voxelize(vertices, faces, y_lo, y_hi)
    if not occupied:
        return []

    skin_c, hair_c = hex_of(skin), hex_of(hair)
    eye_c, mouth_c = hex_of(eye), hex_of(mouth)
    white_c, shadow_c = hex_of("white"), hex_of("skin_dark")

    colors: dict[tuple[int, int, int], str] = {v: skin_c for v in occupied}

    # hair: scalp (everything at/above the forehead) plus the back of the
    # skull down to ear height, mirroring real short hair coverage — using
    # the mesh's own forehead/ear landmarks instead of fixed rows. The
    # "back of the skull" cutoff has to be the *ears'* depth, not the
    # cheeks' — the cheeks sit in front of the ears, so using cheek depth
    # as the threshold marked almost the entire head as hair (everything
    # except the nose, which is the only thing that pokes out past the
    # cheek plane); a real bug caught by rendering this and checking the
    # actual occupied-cell colors, not assumed from the formula alone.
    forehead_iy = _grid_index(lm["forehead_top"], bbox)[1]
    ear_iy = _grid_index(lm["ear_r"], bbox)[1]
    ear_z_mid = (lm["ear_r"][2] + lm["ear_l"][2]) / 2
    x_lo, x_hi, _, _, z_lo, z_hi = bbox
    ear_iz = int((ear_z_mid - z_lo) / (z_hi - z_lo) * GRID_Z)
    for (ox, oy, oz) in occupied:
        if oy >= forehead_iy or (oy >= ear_iy and oz <= ear_iz):
            colors[(ox, oy, oz)] = hair_c

    # eyebrows/eyes: the mesh's own left/right landmark y-values differ by
    # a small, real amount (an actual, if minor, asymmetry in the source
    # geometry) — at full mesh resolution that's invisible, but rounded to
    # this grid's coarse rows it can round the two sides to *different*
    # rows and make an otherwise-symmetric face look lopsided (caught by
    # rendering and comparing the actual left/right row indices, not
    # assumed). Each matched pair's row is taken from their *averaged* y
    # instead of each landmark's own, so both sides always land on the
    # same row; only the column (x) comes from each landmark individually.
    outer_iy = _grid_index((0.0, (lm["eye_l_outer"][1] + lm["eye_r_outer"][1]) / 2, 0.0), bbox)[1]
    inner_iy = _grid_index((0.0, (lm["eye_l_inner"][1] + lm["eye_r_inner"][1]) / 2, 0.0), bbox)[1]
    eye_iy = {"eye_l_outer": outer_iy, "eye_r_outer": outer_iy, "eye_l_inner": inner_iy, "eye_r_inner": inner_iy}

    # eyebrows: a short bar one row above each eye
    for key in ("eye_l_outer", "eye_l_inner", "eye_r_outer", "eye_r_inner"):
        ix = _grid_index(lm[key], bbox)[0]
        for vx, vy, vz in _frontmost(occupied, ix, eye_iy[key] + 1):
            colors[(vx, vy, vz)] = hair_c

    # eyes: outer corner = white (sclera), inner corner = eye color (iris/pupil)
    for key, c in (
        ("eye_l_outer", white_c), ("eye_l_inner", eye_c),
        ("eye_r_outer", white_c), ("eye_r_inner", eye_c),
    ):
        ix = _grid_index(lm[key], bbox)[0]
        for vx, vy, vz in _frontmost(occupied, ix, eye_iy[key]):
            colors[(vx, vy, vz)] = c

    # nose: a shadow at the bridge/tip
    for key in ("nose_bridge", "nose_tip"):
        ix, iy = _grid_index(lm[key], bbox)
        for vx, vy, vz in _frontmost(occupied, ix, iy):
            colors[(vx, vy, vz)] = shadow_c

    # mouth: a bar spanning the full width between the two mouth corners
    mx_l, my_l = _grid_index(lm["mouth_l"], bbox)
    mx_r, _ = _grid_index(lm["mouth_r"], bbox)
    for ix in range(min(mx_l, mx_r), max(mx_l, mx_r) + 1):
        for vx, vy, vz in _frontmost(occupied, ix, my_l):
            colors[(vx, vy, vz)] = mouth_c

    return [(x, y, z, c) for (x, y, z), c in colors.items()]
