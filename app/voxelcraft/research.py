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

On top of that, for named real-world subjects we also pull actual
"blueprint" facts (height, width/diameter, floor count) from Wikidata —
the structured-data sibling of Wikipedia — and use them to correct the
model's proportions to match the real object, instead of whatever
foreshortening/cropping the photo happened to have.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import requests
from PIL import Image

from .matching import word_matches
from .palette import COLOR_WORDS

_TIMEOUT_S = 6
_HEADERS = {"User-Agent": "VoxelCraft/1.0 (text-to-voxel research step)"}

# Wikidata unit entities -> metres.
_UNIT_TO_METERS = {
    "Q11573": 1.0,       # metre
    "Q828224": 1000.0,   # kilometre
    "Q174728": 0.01,     # centimetre
    "Q174789": 0.001,    # millimetre
    "Q3710": 0.3048,     # foot
    "Q218593": 0.0254,   # inch
    "Q5745": 1609.34,    # mile
}

# Subjects that are (roughly) symmetric about a vertical axis, where
# "spin the silhouette into a lathe" is a good reconstruction strategy.
# NOTE: matched as whole words with an optional trailing "s" (see
# ``matching.word_matches``) — never a bare common word like "well",
# which would trip on "as well as" in virtually every article.
_REVOLVE_KEYWORDS = [
    "tower", "spire", "column", "obelisk", "silo", "chimney", "lighthouse",
    "bottle", "vase", "dome", "statue", "monument", "trunk", "cylindrical",
    "rocket", "missile", "pillar", "urn", "wishing well", "fountain", "minaret",
    "vessel", "jar", "cup", "mug", "barrel", "cannon", "candle", "totem",
    "planet", "globe", "sphere", "balloon", "steeple", "flask", "tree",
]

# Multi-part structures checked *before* the revolve keywords above: a
# temple described as having "columns" is still a whole rectangular
# building, not a single round object, so these always win.
# NOTE: deliberately excludes filler nouns that describe almost any
# landmark without saying anything about its shape. "structure" alone
# misclassified the Eiffel Tower ("the tallest structure in Paris") and a
# silo ("a structure for storing bulk materials"); "complex" and
# "compound" are both also common adjectives ("a complex lattice").
_BUILDING_KEYWORDS = [
    "temple", "building", "house", "palace", "church", "cathedral", "stadium",
    "bridge", "mansion", "fortress", "castle", "school", "museum", "library",
    "mosque", "synagogue", "parliament", "capitol", "colonnade", "portico",
    "peristyle", "hall",
]


@dataclass
class BlueprintFacts:
    """Real-world dimensions for a named subject, when we have any.

    ``source`` names where the numbers actually came from, so the UI can
    say so honestly: they may be live Wikidata, the hand-curated table in
    ``known_facts.py`` (which is what answers when Wikidata is
    unreachable), or both.
    """
    height_m: float | None = None
    width_m: float | None = None
    diameter_m: float | None = None
    floors: int | None = None
    source: str | None = None

    @property
    def ratio(self) -> float | None:
        """height / (diameter, or width if no diameter) — the proportion
        image_generator uses to correct the model's shape."""
        base = self.diameter_m or self.width_m
        if self.height_m and base:
            return self.height_m / base
        return None

    def summary(self) -> str:
        parts = []
        if self.height_m:
            parts.append(f"height {self.height_m:.0f} m")
        if self.diameter_m:
            parts.append(f"diameter {self.diameter_m:.0f} m")
        elif self.width_m:
            parts.append(f"width {self.width_m:.0f} m")
        if self.floors:
            parts.append(f"{self.floors} floors")
        return ", ".join(parts)


@dataclass
class ResearchResult:
    image: Image.Image
    subject: str
    source_label: str
    source_url: str
    build_method: str  # "revolve" or "relief" — how to turn the photo into 3D
    reason: str  # human-readable explanation of why that method was picked
    facts: BlueprintFacts = field(default_factory=BlueprintFacts)


def extract_subject(prompt: str) -> str:
    """Strip filler words/clauses/colors from a prompt to get a search-able subject.

    "a red house with a garden and a fence" -> "house"

    Color words are dropped because they describe the model's palette
    rather than what to search for ("a blue dragon" should find a dragon,
    not the blue sea slug of that name). Two exceptions keep the color
    when it is part of a *name* rather than a description: the phrase
    already names a landmark we have dimensions for ("the golden gate
    bridge"), or the user capitalised it the way English capitalises
    proper nouns ("the White House" keeps the "White", "a white house"
    does not).
    """
    original = prompt.strip()
    text = original.lower()
    cut = len(original)
    for article in ("a ", "an ", "the "):
        if text.startswith(article):
            text = text[len(article):]
            original = original[len(article):]
            break
    for sep in (" with ", " that ", " which ", " standing ", " sitting ",
                " holding ", " wearing ", " and ", " in ", " on ", " near ", ","):
        idx = text.find(sep)
        if idx != -1:
            text = text[:idx]
            cut = min(cut, idx)
    original = original[:cut]

    from .known_facts import get_known_facts
    if get_known_facts(text):
        return text

    capitalized = {w.lower() for w in original.split() if w[:1].isupper()}
    color_words = set(COLOR_WORDS.keys()) - capitalized
    words = [w for w in text.split() if w not in color_words]
    subject = " ".join(words).strip()
    return subject or text.strip() or prompt.strip()


def _cue_in(text: str) -> tuple[str, str] | None:
    """First shape cue found in `text`, as (method, reason), or None.
    Buildings are checked first: a temple described as having "columns" is
    still a whole rectangular building, not a single round object."""
    building_hit = next((k for k in _BUILDING_KEYWORDS if word_matches(k, text)), None)
    if building_hit:
        return "relief", f"'{building_hit}' suggests a multi-part building, not a single round object"
    revolve_hit = next((k for k in _REVOLVE_KEYWORDS if word_matches(k, text)), None)
    if revolve_hit:
        return "revolve", f"'{revolve_hit}' suggests a shape that's round about a vertical axis"
    return None


def _classify_build_method(title: str, extract: str) -> tuple[str, str]:
    """Pick a reconstruction strategy from the article's title first, and
    only then from its body text.

    Title-first matters: the Leaning Tower of Pisa's intro mentions "Pisa
    Cathedral" and a lighthouse's says "a tower, building, or other type
    of physical structure", so scanning title and body as one blob let an
    incidental noun in the body outvote the subject's own name.
    """
    cue = _cue_in(title.lower())
    if cue:
        return cue
    cue = _cue_in(extract.lower())
    if cue:
        return cue
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


def _wikidata_qid_for_title(title: str) -> str | None:
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                "titles": title, "format": "json",
            },
            timeout=_TIMEOUT_S, headers=_HEADERS,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                return qid
    except Exception:
        pass
    return None


def _quantity_in_meters(claims: dict, prop: str) -> float | None:
    try:
        value = claims[prop][0]["mainsnak"]["datavalue"]["value"]
        amount = float(value["amount"])
        unit_qid = value.get("unit", "").rsplit("/", 1)[-1]
        factor = _UNIT_TO_METERS.get(unit_qid)
        return amount * factor if factor else None
    except Exception:
        return None


def _fetch_wikidata_facts(title: str) -> BlueprintFacts:
    """Best-effort: real-world height/width/diameter/floor-count for a named
    subject, from Wikidata (free, keyless). Any failure just means we fall
    back to the hand-curated table (or the photo's own proportions) instead
    — this must never raise."""
    qid = _wikidata_qid_for_title(title)
    if not qid:
        return BlueprintFacts()
    try:
        resp = requests.get(
            "https://www.wikidata.org/w/api.php",
            params={"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"},
            timeout=_TIMEOUT_S, headers=_HEADERS,
        )
        resp.raise_for_status()
        claims = resp.json().get("entities", {}).get(qid, {}).get("claims", {})
    except Exception:
        return BlueprintFacts()

    floors = None
    try:
        amount = claims["P1101"][0]["mainsnak"]["datavalue"]["value"]["amount"]
        floors = int(round(float(amount)))
    except Exception:
        pass

    return BlueprintFacts(
        height_m=_quantity_in_meters(claims, "P2048"),
        width_m=_quantity_in_meters(claims, "P2049"),
        diameter_m=_quantity_in_meters(claims, "P2386"),
        floors=floors,
    )


CURATED_SOURCE = "VoxelCraft's curated landmark table"

_FACT_FIELDS = ("height_m", "width_m", "diameter_m", "floors")


def merge_facts(candidates: list[tuple[str, BlueprintFacts | None]]) -> BlueprintFacts:
    """Merge candidate facts field by field, highest precedence first, and
    record which sources actually contributed in ``source``.

    Each source only fills fields the ones before it left empty, so a
    result can legitimately be one source's height and another's floor
    count. ``source`` therefore names every source that contributed
    rather than one winner, because that is what the UI has to be able
    to say truthfully. Sources that contributed nothing are not named,
    and a result with no facts at all gets no source.
    """
    merged = BlueprintFacts()
    contributors: list[str] = []
    for label, facts in candidates:
        if facts is None:
            continue
        contributed = False
        for field_name in _FACT_FIELDS:
            if getattr(merged, field_name) is None and getattr(facts, field_name) is not None:
                setattr(merged, field_name, getattr(facts, field_name))
                contributed = True
        if contributed:
            contributors.append(label)
    if len(contributors) > 1:
        merged.source = f"{', '.join(contributors[:-1])} and {contributors[-1]}"
    elif contributors:
        merged.source = contributors[0]
    return merged


def fetch_blueprint_facts(title: str) -> BlueprintFacts:
    """Real-world dimensions for a named subject: live Wikidata first, with
    a hand-curated table of well-known landmarks (``known_facts.py``) used
    to fill in whatever Wikidata didn't return (or the whole thing, if
    Wikidata has nothing or isn't reachable). Wikidata's own values are
    never overridden — it's the more current source when reachable.

    Another source (a locally ingested cache, say) slots into the list
    below at its precedence; ``merge_facts`` handles the attribution.
    """
    from .known_facts import get_known_facts
    return merge_facts([
        ("Wikidata", _fetch_wikidata_facts(title)),
        (CURATED_SOURCE, get_known_facts(title)),
    ])


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
        facts = fetch_blueprint_facts(title)
        return ResearchResult(
            image=image,
            subject=query,
            source_label=f"Wikipedia: {title}",
            source_url=page.get("fullurl", "https://en.wikipedia.org/wiki/" + query.replace(" ", "_")),
            build_method=method,
            reason=reason,
            facts=facts,
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
    from .local_library import get_local_reference
    return (get_local_reference(subject)
            or _search_wikipedia(subject)
            or _search_openverse(subject))
