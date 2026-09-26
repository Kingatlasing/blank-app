"""The block palette VoxelCraft draws from.

Every color VoxelCraft ever places is one of these swatches, so that the
final model can always be re-expressed as real Minecraft blocks (see
``exporters.to_mcfunction``), not just arbitrary RGB cubes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .matching import word_matches


@dataclass(frozen=True)
class Swatch:
    name: str
    hex: str
    block: str  # a real Minecraft (Java Edition) block id, minecraft:-prefixed

    @property
    def rgb(self) -> tuple[int, int, int]:
        h = self.hex.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


PALETTE: list[Swatch] = [
    Swatch("white", "#F9FFFE", "minecraft:white_wool"),
    Swatch("light_gray", "#9D9D97", "minecraft:light_gray_wool"),
    Swatch("gray", "#474F52", "minecraft:gray_wool"),
    Swatch("black", "#1D1D21", "minecraft:black_wool"),
    Swatch("red", "#B02E26", "minecraft:red_wool"),
    Swatch("orange", "#F9801D", "minecraft:orange_wool"),
    Swatch("yellow", "#FED83D", "minecraft:yellow_wool"),
    Swatch("lime", "#80C71F", "minecraft:lime_wool"),
    Swatch("green", "#5E7C16", "minecraft:green_wool"),
    Swatch("cyan", "#169C9C", "minecraft:cyan_wool"),
    Swatch("light_blue", "#3AB3DA", "minecraft:light_blue_wool"),
    Swatch("blue", "#3C44AA", "minecraft:blue_wool"),
    Swatch("purple", "#8932B8", "minecraft:purple_wool"),
    Swatch("magenta", "#C74EBD", "minecraft:magenta_wool"),
    Swatch("pink", "#F38BAA", "minecraft:pink_wool"),
    Swatch("brown", "#724728", "minecraft:brown_wool"),
    Swatch("skin", "#E0AC85", "minecraft:terracotta"),
    Swatch("skin_light", "#EFC29D", "minecraft:white_terracotta"),
    Swatch("skin_dark", "#8B5A3C", "minecraft:brown_terracotta"),
    Swatch("oak_planks", "#B08F55", "minecraft:oak_planks"),
    Swatch("oak_log", "#6F5330", "minecraft:oak_log"),
    Swatch("leaves", "#3B6A1D", "minecraft:oak_leaves"),
    Swatch("grass", "#5D7C15", "minecraft:grass_block"),
    Swatch("dirt", "#866043", "minecraft:dirt"),
    Swatch("stone", "#7F7F7F", "minecraft:stone"),
    Swatch("cobblestone", "#6C6C6C", "minecraft:cobblestone"),
    Swatch("sand", "#DBD3A0", "minecraft:sand"),
    Swatch("snow", "#F0FBFB", "minecraft:snow_block"),
    Swatch("ice", "#7DACE3", "minecraft:ice"),
    Swatch("water", "#3F76E4", "minecraft:blue_stained_glass"),
    Swatch("lava", "#E25822", "minecraft:lava"),
    Swatch("gold", "#FCEE4B", "minecraft:gold_block"),
    Swatch("iron", "#D8D8D8", "minecraft:iron_block"),
    Swatch("diamond", "#63DBDB", "minecraft:diamond_block"),
    Swatch("emerald", "#17DD62", "minecraft:emerald_block"),
    Swatch("redstone", "#AA0000", "minecraft:redstone_block"),
    Swatch("obsidian", "#15121C", "minecraft:obsidian"),
    Swatch("glass", "#DDEEEE", "minecraft:glass"),
    Swatch("netherrack", "#6E3634", "minecraft:netherrack"),
]

_BY_NAME = {s.name: s for s in PALETTE}
_BY_HEX = {s.hex: s for s in PALETTE}


def swatch(name: str) -> Swatch:
    return _BY_NAME[name]


def hex_of(name: str) -> str:
    return _BY_NAME[name].hex


# Words a prompt might use to steer color, mapped to a palette swatch name.
COLOR_WORDS: dict[str, str] = {
    "white": "white", "snow": "snow", "snowy": "snow", "ivory": "white",
    "light gray": "light_gray", "light grey": "light_gray", "silver": "light_gray",
    "gray": "gray", "grey": "gray", "ash": "gray",
    "black": "black", "dark": "black", "shadow": "black",
    "red": "red", "crimson": "red", "scarlet": "red", "ruby": "red",
    "orange": "orange", "pumpkin": "orange", "amber": "orange",
    "yellow": "yellow", "golden": "gold", "gold": "gold", "banana": "yellow",
    "lime": "lime", "chartreuse": "lime",
    "green": "green", "emerald": "emerald", "jade": "green", "forest": "green",
    "cyan": "cyan", "teal": "cyan", "turquoise": "cyan", "diamond": "diamond",
    "light blue": "light_blue", "sky": "light_blue", "azure": "light_blue",
    "blue": "blue", "navy": "blue", "sapphire": "blue", "water": "water", "ocean": "water",
    "purple": "purple", "violet": "purple", "amethyst": "purple",
    "magenta": "magenta", "fuchsia": "magenta",
    "pink": "pink", "rose": "pink",
    "brown": "brown", "chocolate": "brown", "wood": "oak_planks", "wooden": "oak_planks",
    "tan": "sand", "sand": "sand", "sandy": "sand", "desert": "sand", "beige": "sand",
    "stone": "stone", "gray stone": "stone", "concrete": "stone",
    "iron": "iron", "steel": "iron", "metal": "iron", "metallic": "iron",
    "lava": "lava", "fire": "lava", "flame": "lava", "molten": "lava",
    "ice": "ice", "icy": "ice", "frozen": "ice", "glacier": "ice",
    "glass": "glass", "clear": "glass", "crystal": "diamond",
    "obsidian": "obsidian", "night": "obsidian",
    "redstone": "redstone",
}


def find_color_words(prompt_lower: str) -> list[str]:
    """Return palette-swatch names mentioned in the prompt, longest phrase
    first.

    Matched on whole words: substring matching turned "a knight" black
    ("night"), "a skyscraper" light blue ("sky") and "a sandwich" sand.
    """
    hits = []
    for phrase in sorted(COLOR_WORDS, key=len, reverse=True):
        if word_matches(phrase, prompt_lower):
            hits.append(COLOR_WORDS[phrase])
    # de-dupe, preserve order
    seen: set[str] = set()
    ordered = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            ordered.append(h)
    return ordered


def nearest_swatch(rgb: tuple[int, int, int]) -> Swatch:
    """Quantize an arbitrary RGB color to the closest palette swatch."""
    r, g, b = rgb
    best = None
    best_d = float("inf")
    for s in PALETTE:
        sr, sg, sb = s.rgb
        d = (sr - r) ** 2 + (sg - g) ** 2 + (sb - b) ** 2
        if d < best_d:
            best_d = d
            best = s
    assert best is not None
    return best
