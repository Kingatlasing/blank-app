""""Research" a prompt: look up a real reference photo for it online.

This is what lets VoxelCraft turn an arbitrary noun phrase ("the Eiffel
Tower", "a golden retriever", "a lighthouse") into a model that actually
looks like the thing, instead of only ever matching one of the small set
of hand-built shapes in ``shapes.py``. It tries Wikipedia first (great for
named/real-world subjects), then falls back to Openverse (openly-licensed
photo search) for anything Wikipedia doesn't have. Both are free, keyless
public APIs. If neither turns up a usable image, the caller should fall
back to the procedural generator.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import requests
from PIL import Image

from .palette import COLOR_WORDS

_TIMEOUT_S = 6
_HEADERS = {"User-Agent": "VoxelCraft/1.0 (text-to-voxel research step)"}


@dataclass
class ResearchResult:
    image: Image.Image
    subject: str
    source_label: str
    source_url: str


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


def _fetch_image(url: str) -> Image.Image | None:
    try:
        resp = requests.get(url, timeout=_TIMEOUT_S, headers=_HEADERS)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception:
        return None


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
        return ResearchResult(
            image=image,
            subject=query,
            source_label=f"Wikipedia: {page.get('title', query)}",
            source_url=page.get("fullurl", "https://en.wikipedia.org/wiki/" + query.replace(" ", "_")),
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
        return ResearchResult(
            image=image,
            subject=query,
            source_label=f"Openverse photo by {creator} ({license_name})",
            source_url=result.get("foreign_landing_url", "https://openverse.org"),
        )
    return None


def research_reference_image(prompt: str) -> ResearchResult | None:
    """Try to find a real reference photo for `prompt`. Returns None if
    nothing usable was found (caller should fall back to procedural shapes)."""
    subject = extract_subject(prompt)
    if not subject:
        return None
    return _search_wikipedia(subject) or _search_openverse(subject)
