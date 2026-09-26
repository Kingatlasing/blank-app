"""Turn a free-text prompt into a voxel model.

Strategy: look for recognizable subjects in the prompt (a person, a tree, a
house, a sword, ...) and hand off to the matching builder(s) in
``shapes.py``, recoloring with any color words mentioned. A prompt that
names more than one subject ("a castle with a knight and dragon") gets
each one built and composed side by side into a single scene, rather than
only ever returning the first match. If nothing matches at all, falls back
to a deterministic procedural sculpture so *every* prompt still produces a
model.
"""

from __future__ import annotations

import re

from . import shapes
from .matching import word_matches
from .palette import find_color_words

Voxel = tuple[int, int, int, str]

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "a": 1, "an": 1, "single": 1, "double": 2, "triple": 3,
}


def _parse_floor_count(text: str) -> int | None:
    m = re.search(r"(\d+)\s*[- ]?(?:floor|floors|stor(?:y|ies))", text)
    if m:
        return max(1, int(m.group(1)))
    m2 = re.search(r"(\w+)[- ](?:floor|floors|stor(?:y|ies))", text)
    if m2 and m2.group(1) in _NUMBER_WORDS:
        return _NUMBER_WORDS[m2.group(1)]
    if re.search(r"multi[- ]stor(?:y|ies)|multiple floors|multiple stories", text):
        return 2
    return None


def _wants_staircase(text: str) -> bool:
    return bool(re.search(r"(spiral|helix|helical|winding)\s*stair", text))


# Ordered (specific-first) keyword -> builder table. Keywords are matched
# as whole words (``matching.word_matches``), never as substrings: "a
# lighthouse" used to build a lighthouse *and* a house side by side, and
# "a multi-story mansion" used to build a person, because "house" and
# "man" are inside those words. Anything that should still match a longer
# word therefore needs its own entry ("mansion", "snowman").
#
# Every builder takes the
# shared `colors` list (from any color words in the prompt); the handful
# that read `_last_prompt` do so to pick up cues (a "witch's" castle, a
# "box" vs a "cube", floor count) that aren't colors.
_RULES: list[tuple[list[str], object]] = [
    (["pickaxe", "pick axe"], lambda colors: shapes.pickaxe(
        head=colors[0] if colors else "iron")),
    (["sword", "blade", "katana"], lambda colors: shapes.sword(
        blade=colors[0] if colors else "iron")),
    (["heart", "love"], lambda colors: shapes.heart_3d(
        color=colors[0] if colors else "red")),
    (["star"], lambda colors: shapes.star(color=colors[0] if colors else "yellow")),
    (["dragon", "wyvern"], lambda colors: shapes.dragon(
        body=colors[0] if colors else "green")),
    (["castle", "fortress"], lambda colors: shapes.castle(
        color=colors[0] if colors else ("purple" if word_matches("witch", _last_prompt[0]) else "cobblestone"))),
    (["tower", "turret", "lighthouse"], lambda colors: shapes.tower(
        color=colors[0] if colors else "cobblestone")),
    (["temple", "parthenon", "acropolis", "colonnade"], lambda colors: shapes.temple(
        stone=colors[0] if colors else "sand",
        roof=colors[1] if len(colors) > 1 else "light_gray")),
    (["house", "cabin", "cottage", "home", "hut", "mansion"], lambda colors: shapes.house(
        wall=colors[0] if colors else "oak_planks",
        roof=colors[1] if len(colors) > 1 else "red",
        floors=_parse_floor_count(_last_prompt[0]) or 1,
        staircase=_wants_staircase(_last_prompt[0]))),
    (["pyramid"], lambda colors: shapes.pyramid(color=colors[0] if colors else "sand")),
    (["tree", "oak", "pine", "forest"], lambda colors: shapes.tree()),
    (["planet", "globe", "moon", "world", "orb", "ball", "sphere"], lambda colors: shapes.sphere(
        color=colors[0] if colors else "light_blue")),
    (["cube", "block", "box"], lambda colors: shapes.cube(
        color=colors[0] if colors else "stone", hollow=word_matches("box", _last_prompt[0]))),
    (["car", "truck", "vehicle"], lambda colors: shapes.car(
        body=colors[0] if colors else "red")),
    (["boat", "ship", "canoe"], lambda colors: shapes.boat()),
    (["dog", "puppy", "wolf", "fox"], lambda colors: shapes.dog(
        body=colors[0] if colors else "brown")),
    (["cat", "kitten"], lambda colors: shapes.cat(
        body=colors[0] if colors else "light_gray")),
    (["horse", "pony", "stallion", "mare"], lambda colors: shapes.horse(
        body=colors[0] if colors else "brown")),
    (["bird", "parrot", "chicken", "eagle", "owl", "duck"], lambda colors: shapes.bird(
        body=colors[0] if colors else "red")),
    (["fish", "shark", "goldfish", "salmon", "tuna"], lambda colors: shapes.fish(
        body=colors[0] if colors else "orange")),
    (["snake", "serpent", "python", "cobra"], lambda colors: shapes.snake(
        body=colors[0] if colors else "green")),
    (["plane", "airplane", "aircraft", "jet", "jumbo jet"], lambda colors: shapes.airplane(
        body=colors[0] if colors else "light_gray")),
    (["pig", "cow", "sheep", "animal", "creature", "beast"],
     lambda colors: shapes.quadruped(
         body=colors[0] if colors else "brown", head=colors[0] if colors else "brown")),
    (["face", "portrait"], lambda colors: shapes.human_face(
        skin=colors[0] if colors else "skin", hair=colors[1] if len(colors) > 1 else "brown")),
    (["body", "torso", "physique"], lambda colors: shapes.human_body(
        skin=colors[0] if colors else "skin", shirt=colors[1] if len(colors) > 1 else "cyan")),
    (["robot", "person", "human", "steve", "alex", "character", "man", "woman",
      "knight", "warrior", "hero", "zombie", "player", "snowman"], lambda colors: shapes.humanoid(
        shirt=colors[0] if colors else "cyan", pants=colors[1] if len(colors) > 1 else "blue")),
]

# When a prompt matches one of the realistic face/body rules above, the
# generic catch-all person rule below is redundant (and produces an
# unwanted extra blocky figure composed alongside it, since "a realistic
# human body" contains both "body" and "human"): drop it in that case.
_GENERIC_PERSON_KEYWORDS = {
    "robot", "person", "human", "steve", "alex", "character", "man", "woman",
    "knight", "warrior", "hero", "zombie", "player", "snowman",
}

# a little closure-friendly slot so rules above can read cues from the raw
# prompt (floor count, "witch's", "box" vs "cube") without changing every
# lambda's signature
_last_prompt: list[str] = [""]


def _footprint(voxels: list[Voxel]) -> int:
    xs = [v[0] for v in voxels]
    zs = [v[2] for v in voxels]
    return (max(xs) - min(xs) + 1) * (max(zs) - min(zs) + 1)


def _compose_scene(built: list[tuple[str, list[Voxel]]]) -> list[Voxel]:
    """Place multiple built subjects side by side along x, biggest
    footprint first (treated as the scene's main structure), so a prompt
    naming several things gets all of them instead of just the first match."""
    built = sorted(built, key=lambda t: _footprint(t[1]), reverse=True)
    placed: list[Voxel] = []
    cursor_x = 0
    for _name, voxels in built:
        xs = [v[0] for v in voxels]
        width = max(xs) - min(xs) + 1
        offset = cursor_x - min(xs)
        placed.extend((x + offset, y, z, c) for x, y, z, c in voxels)
        cursor_x += width + 3  # gap so adjacent subjects don't touch
    return placed


def generate_from_text(prompt: str) -> tuple[list[Voxel], str, bool]:
    """Returns (voxels, description-of-what-was-built, chunkable).

    ``chunkable`` says whether the caller's chunkiness post-processing
    (blowing each voxel up into a factor^3 cluster, for the deliberately
    blocky Minecraft look) should apply. It's False whenever the result
    includes anything from the high-resolution "detailed" tier
    (`human_face`/`human_body`, see `catalog.py`) — forcibly re-blocking a
    model built *for* smoothness would undo the entire point of it."""
    prompt_lower = prompt.lower()
    _last_prompt[0] = prompt_lower
    colors = find_color_words(prompt_lower)

    matches = []
    for keywords, builder in _RULES:
        matched = next((k for k in keywords if word_matches(k, prompt_lower)), None)
        if matched:
            matches.append((matched, builder))

    matched_keys = {k for k, _ in matches}
    detailed_tier_keys = {"face", "portrait", "body", "torso", "physique"}
    if matched_keys & detailed_tier_keys:
        matches = [(k, b) for k, b in matches if k not in _GENERIC_PERSON_KEYWORDS]
    chunkable = not (matched_keys & detailed_tier_keys)

    if not matches:
        voxels = shapes.procedural_blob(prompt_lower, colors=colors or None)
        return voxels, "No specific object recognized — generated an abstract voxel sculpture from your prompt.", chunkable

    if len(matches) == 1:
        matched, builder = matches[0]
        voxels = builder(colors)
        return voxels, f"Recognized '{matched}' in your prompt.", chunkable

    built = [(matched, builder(colors)) for matched, builder in matches]
    voxels = _compose_scene(built)
    names = ", ".join(name for name, _ in built)
    return voxels, f"Recognized multiple subjects ({names}) and composed them into one scene, side by side.", chunkable