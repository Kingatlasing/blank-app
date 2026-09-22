"""A machine-readable catalog of every named shape in ``shapes.py``: its
real bounding-box size (in voxels), what it actually is, and which
resolution "tier" it belongs to.

This exists so a caller — chiefly ``llm_builder``'s system prompt — can
tell a model how big things are *relative to each other* without the model
having to guess. Dimensions are computed by actually calling each builder
with its defaults and measuring the result, so they can never drift out of
sync with the real shapes the way a hand-maintained number table would.

**Tiers.** The shape library was built in two passes at two different
resolutions:

- ``"blocky"`` — the original Minecraft-block scale. A `house`'s walls
  are 5 voxels tall; a `humanoid` is 15 voxels tall (~3 "blocks"), the
  same rough unit `castle`, `dog`, `car`, and the furniture shapes below
  all share. Anything in this tier can be placed directly alongside
  anything else in it.
- ``"detailed"`` — `human_face`/`human_body`, built at roughly 8x the
  blocky tier's linear resolution (~9x taller than `humanoid`) for a
  proportioned, shaded, anatomically-landmarked look. They are **not**
  scale-compatible with the blocky tier without deliberate rescaling: a
  `human_body` (well over a hundred voxels tall) placed next to a blocky
  `house` (~5 voxels per floor) would dwarf it. A blocky scene that needs
  a person-sized figure should use `humanoid` instead; the detailed tier
  is for a standalone "realistic person" request. (Exact dimensions are
  measured below, not hand-maintained — check there for current numbers.)
"""

from __future__ import annotations

from dataclasses import dataclass

from . import shapes

Voxel = tuple[int, int, int, str]


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    tier: str  # "blocky" or "detailed"
    category: str
    description: str
    width: int
    height: int
    depth: int
    voxel_count: int


# (function name, tier, category, one-line description) — hand-curated;
# dimensions are measured, not guessed. Every entry must be callable with
# zero arguments (all shape builders take only optional kwargs).
_REGISTRY: list[tuple[str, str, str, str]] = [
    ("house", "blocky", "structure", "a house; floors=N and staircase=True for multi-story"),
    ("temple", "blocky", "structure", "a Greek temple with a genuinely hollow, walkable interior"),
    ("tower", "blocky", "structure", "a round crenellated tower"),
    ("castle", "blocky", "structure", "a central keep with 4 corner towers"),
    ("pyramid", "blocky", "structure", "a stepped pyramid"),
    ("table", "blocky", "furniture", "a 4-legged table; fits inside a house's rooms"),
    ("chair", "blocky", "furniture", "a small chair with a backrest"),
    ("bed", "blocky", "furniture", "a single bed with a headboard"),
    ("sofa", "blocky", "furniture", "a sofa with armrests"),
    ("shelf", "blocky", "furniture", "a bookcase/shelf, thin — meant to sit flush against a wall"),
    ("lamp", "blocky", "furniture", "a floor lamp"),
    ("rug", "blocky", "furniture", "a flat floor rug"),
    ("humanoid", "blocky", "creature", "a blocky Steve-style person — the person-sized figure to use in blocky scenes"),
    ("dog", "blocky", "creature", "a standing dog"),
    ("cat", "blocky", "creature", "a standing cat"),
    ("horse", "blocky", "creature", "a standing horse"),
    ("bird", "blocky", "creature", "a small perched bird"),
    ("fish", "blocky", "creature", "a fish"),
    ("snake", "blocky", "creature", "an S-curved snake"),
    ("dragon", "blocky", "creature", "a winged dragon with a tail"),
    ("quadruped", "blocky", "creature", "a generic 4-legged animal (pig/cow/sheep-shaped)"),
    ("tree", "blocky", "nature", "a tree with a round canopy"),
    ("sphere", "blocky", "nature", "a plain sphere"),
    ("car", "blocky", "vehicle", "a car"),
    ("boat", "blocky", "vehicle", "a small boat hull"),
    ("airplane", "blocky", "vehicle", "a commercial-jet silhouette"),
    ("sword", "blocky", "item", "a flat sword silhouette, 2 voxels thick"),
    ("pickaxe", "blocky", "item", "a flat pickaxe silhouette, 2 voxels thick"),
    ("heart_3d", "blocky", "item", "a solid 3D heart (implicit-surface, not a flat cutout)"),
    ("star", "blocky", "item", "a flat star silhouette, 2 voxels thick"),
    ("cube", "blocky", "item", "a plain cube; hollow=True for a shell"),
    ("human_face", "detailed", "human", "a rounded, proportioned bust with eyes/nose/mouth/ears — standalone, not blocky-scene-compatible"),
    ("human_body", "detailed", "human", "a rounded, proportioned standing figure — standalone, not blocky-scene-compatible"),
]


def build_catalog() -> list[CatalogEntry]:
    """Call every registered shape with its defaults and measure it."""
    entries = []
    for name, tier, category, description in _REGISTRY:
        builder = getattr(shapes, name)
        voxels: list[Voxel] = builder()
        xs = [v[0] for v in voxels]
        ys = [v[1] for v in voxels]
        zs = [v[2] for v in voxels]
        entries.append(CatalogEntry(
            name=name, tier=tier, category=category, description=description,
            width=max(xs) - min(xs) + 1, height=max(ys) - min(ys) + 1,
            depth=max(zs) - min(zs) + 1, voxel_count=len(voxels),
        ))
    return entries


def catalog_prompt_text() -> str:
    """A compact, table-like rendering of the catalog for a system prompt."""
    entries = build_catalog()
    lines = []
    for tier in ("blocky", "detailed"):
        tier_entries = [e for e in entries if e.tier == tier]
        if not tier_entries:
            continue
        lines.append(f"[{tier} tier]")
        for e in tier_entries:
            lines.append(
                f"  {e.name}(...) -> ~{e.width}w x {e.height}h x {e.depth}d voxels, "
                f"{e.category}: {e.description}"
            )
    return "\n".join(lines)
