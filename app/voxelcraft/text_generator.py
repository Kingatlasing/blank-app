"""Turn a free-text prompt into a voxel model.

Strategy: look for a recognizable subject in the prompt (a person, a tree, a
house, a sword, ...) and hand off to the matching builder in ``shapes.py``,
recoloring it with any color words mentioned. If nothing matches, fall back
to a deterministic procedural sculpture so *every* prompt still produces a
model.
"""

from __future__ import annotations

from . import shapes
from .palette import find_color_words

Voxel = tuple[int, int, int, str]

# Ordered (specific-first) keyword -> builder table.
_RULES: list[tuple[list[str], object]] = [
    (["pickaxe", "pick axe"], lambda colors: shapes.pickaxe(
        head=colors[0] if colors else "iron")),
    (["sword", "blade", "katana"], lambda colors: shapes.sword(
        blade=colors[0] if colors else "iron")),
    (["heart", "love"], lambda colors: shapes.heart(color=colors[0] if colors else "red")),
    (["star"], lambda colors: shapes.star(color=colors[0] if colors else "yellow")),
    (["castle", "fortress"], lambda colors: shapes.castle(
        color=colors[0] if colors else "cobblestone")),
    (["tower", "turret", "lighthouse"], lambda colors: shapes.tower(
        color=colors[0] if colors else "cobblestone")),
    (["temple", "parthenon", "acropolis", "colonnade"], lambda colors: shapes.temple(
        stone=colors[0] if colors else "sand",
        roof=colors[1] if len(colors) > 1 else "light_gray")),
    (["house", "cabin", "cottage", "home", "hut"], lambda colors: shapes.house(
        wall=colors[0] if colors else "oak_planks",
        roof=colors[1] if len(colors) > 1 else "red")),
    (["pyramid"], lambda colors: shapes.pyramid(color=colors[0] if colors else "sand")),
    (["tree", "oak", "pine", "forest"], lambda colors: shapes.tree()),
    (["planet", "globe", "moon", "world", "orb", "ball", "sphere"], lambda colors: shapes.sphere(
        color=colors[0] if colors else "light_blue")),
    (["cube", "block", "box"], lambda colors: shapes.cube(
        color=colors[0] if colors else "stone", hollow="box" in _last_prompt[0])),
    (["car", "truck", "vehicle"], lambda colors: shapes.car(
        body=colors[0] if colors else "red")),
    (["boat", "ship", "canoe"], lambda colors: shapes.boat()),
    (["dog", "cat", "wolf", "fox", "pig", "cow", "sheep", "animal", "creature", "beast"],
     lambda colors: shapes.quadruped(
         body=colors[0] if colors else "brown", head=colors[0] if colors else "brown")),
    (["robot", "person", "human", "steve", "alex", "character", "man", "woman",
      "knight", "warrior", "hero", "zombie", "player"], lambda colors: shapes.humanoid(
        shirt=colors[0] if colors else "cyan", pants=colors[1] if len(colors) > 1 else "blue")),
]

# a little closure-friendly slot so the "cube vs box" rule above can peek
# at the raw prompt without changing every lambda's signature
_last_prompt: list[str] = [""]


def generate_from_text(prompt: str) -> tuple[list[Voxel], str]:
    """Returns (voxels, description-of-what-was-built)."""
    prompt_lower = prompt.lower()
    _last_prompt[0] = prompt_lower
    colors = find_color_words(prompt_lower)

    for keywords, builder in _RULES:
        matched = next((k for k in keywords if k in prompt_lower), None)
        if matched:
            voxels = builder(colors)
            return voxels, f"Recognized '{matched}' in your prompt."

    # Fallback: deterministic procedural sculpture, tinted by any colors found.
    voxels = shapes.procedural_blob(prompt_lower, colors=colors or None)
    return voxels, "No specific object recognized — generated an abstract voxel sculpture from your prompt."
