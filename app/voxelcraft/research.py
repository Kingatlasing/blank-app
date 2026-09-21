""""Research" a prompt: look up a real reference photo for it, and work out
how to turn that photo into an actual 3D shape (not just a flat picture).

This is what lets VoxelCraft turn an arbitrary noun phrase ("the Eiffel
Tower", "a golden retriever", "a lighthouse") into a model that actually
looks like the thing, instead of only ever matching one of the small set
of hand-built shapes in ``shapes.py``. It tries Wikipedia first (great for
named/real-world subjects, and its article text tells us what *kind* of
object we're looking at), then falls back to Openverse (openly-licensed
photo search) for anything Wikipedia doesn't have. Both are free, keyless
public APIs. If neither turns up a usable image, the caller should fall
back to the procedural generator.

The "how to build it" part: a photo only shows one side of something, so
turning it into a solid 3D voxel model needs a reconstruction strategy,
not just stacking the pixels on a slab. We pick between two, based on what
kind of subject Wikipedia says this is:

- ``revolve`` — subjects that are round about a vertical axis (towers,
  bottles, statues, trees, domes, ...). We spin the photo's silhouette
  around its central axis like a lathe, which turns a single flat photo
  into a properly solid, roughly-correct 3D volume.
- ``relief`` — everything else (buildings, animals, vehicles, ...), where
  rotational symmetry would be wrong. We extrude the silhouette into a
  bas-relief sculpture instead (see ``image_generator.py``).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import requests
from PIL import Image

from .palette import COLOR_WORDS

_TIMEOUT_S = 6
_HEADERS = {"User-Agent": "VoxelCraft/1.0 (text-to-voxel research step)"}

# Subjects that are (roughly) symmetric about a vertical axis, where
# "spin the silhouette into a lathe" is a good reconstruction strategy.
_REVOLVE_KEYWORDS = [
    "tower", "spire", "column", "obelisk", "silo", "chimney", "lighthouse",
    "bottle", "vase", "dome", "statue", "monument", "trunk", "cylindrical",
    "rocket", "missile", "pillar", "urn", "well", "fountain", "minaret",
    "vessel", "jar", "cup", "mug", "barrel", "cannon", "candle", "totem",
    "planet", "globe", "sphere", "balloon", "silo", "steeple", "flask",
]


@dataclass
class ResearchResult:
    image: Image.Image
    subject: str
    source_label: str
    source_url: str
    build_method: str  # "revolve" or "relief" — how to turn the photo into 3D
    reason: str  # human-readable explanation of why that method was picked


def extract_subject(prompt: str) -> str:
    """Strip filler words/clauses/colors from a prompt to get a search-able subject.

    "a red house with a garden and a fence" -> "house"
    """
    text = prompt.strip().lower()
    for article in ("a ", "an ", "the "):
        if text.startswith(article):
            text = text[len(article):]
            break
    for sep in (" with ", " that ", " which ", " standing ", " sitting ",
                " holding ", " wearing ", " and ", " in ", " on ", " near ", ","):
        idx = text.find(sep)
        if idx != -1:
            text = text[:idx]
    color_words = set(COLOR_WORDS.keys())
    words = [w for w in text.split() if w not in color_words]
    subject = " ".join(words).strip()
    return subject or text.strip() or prompt.strip()


def _classify_build_method(title: str, extract: str) -> tuple[str, str]:
    text = f"{title} {extract}".lower()
    hit = next((k for k in _REVOLVE_KEYWORDS if re.search(rf"\b{k}\w*\b", text)), None)
    if hit:
        return "revolve", f"'{hit}' suggests a shape that's round about a vertical axis"
    return "relief", "no rotational-symmetry cue found, so treated as a flatter/profile shape"


def _fetch_image(url: str) -> Image.Image | None:
    try:
        resp = requests.get(url, timeout=_TIMEOUT_S, headers=_HEADERS)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception:
        return None


def _fetch_wikipedia_extract(title: str) -> str:
    """Best-effort: the article's intro text, used only to help pick a
    reconstruction strategy. Any failure here just means we fall back to
    guessing from the title alone — it must never break the image lookup."""
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "exchars": 600,
                "titles": title,
                "format": "json",
            },
            timeout=_TIMEOUT_S,
            headers=_HEADERS,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            extract = page.get("extract")
            if extract:
                return extract
    except Exception:
        pass
    return ""


def _search_wikipedia(query: str) -> ResearchResult | None:
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 1,
                "prop": "pageimages|info",
                "piprop": "thumbnail",
                "pithumbsize": 640,
                "inprop": "url",
                "format": "json",
            },
            timeout=_TIMEOUT_S,
            headers=_HEADERS,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
    except Exception:
        return None

    for page in pages.values():
        thumb = page.get("thumbnail", {}).get("source")
        if not thumb:
            continue
        image = _fetch_image(thumb)
        if image is None:
            continue
        title = page.get("title", query)
        extract = _fetch_wikipedia_extract(title)
        method, reason = _classify_build_method(title, extract)
        return ResearchResult(
            image=image,
            subject=query,
            source_label=f"Wikipedia: {title}",
            source_url=page.get("fullurl", "https://en.wikipedia.org/wiki/" + query.replace(" ", "_")),
            build_method=method,
            reason=reason,
        )
    return None


def _search_openverse(query: str) -> ResearchResult | None:
    try:
        resp = requests.get(
            "https://api.openverse.org/v1/images/",
            params={"q": query, "page_size": 1, "license_type": "all"},
            timeout=_TIMEOUT_S,
            headers=_HEADERS,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception:
        return None

    for result in results:
        thumb = result.get("thumbnail") or result.get("url")
        if not thumb:
            continue
        image = _fetch_image(thumb)
        if image is None:
            continue
        creator = result.get("creator") or "unknown"
        license_name = (result.get("license") or "").upper()
        title = result.get("title") or query
        method, reason = _classify_build_method(title, "")
        return ResearchResult(
            image=image,
            subject=query,
            source_label=f"Openverse photo by {creator} ({license_name})",
            source_url=result.get("foreign_landing_url", "https://openverse.org"),
            build_method=method,
            reason=reason,
        )
    return None


def research_reference_image(prompt: str) -> ResearchResult | None:
    """Try to find a real reference photo for `prompt`, plus how to build it
    in 3D. Returns None if nothing usable was found (caller should fall back
    to procedural shapes)."""
    subject = extract_subject(prompt)
    if not subject:
        return None
    return _search_wikipedia(subject) or _search_openverse(subject)
