"""The reference library bundled with the app itself: photos and real-world
dimensions ingested ahead of time by ``tools/ingest_library.py`` (see
``library/README.md`` for the schema and the licence policy).

Checked before any live Wikipedia/Openverse lookup in ``research.py``: a
bundled entry never depends on network access, never rate-limits, and its
licence has already been verified at ingest time rather than trusted blind
at generation time. When the manifest has no entry for a subject this is a
no-op and the caller falls through to the live research path exactly as
before, so an empty library changes nothing.

``facts.json`` is the same idea for dimensions alone: a cache of what
Wikidata returned at ingest time, consulted by
``research.fetch_blueprint_facts`` when the live lookup is unavailable.
Both files are written by the ingest tool, not by hand.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PIL import Image

from .matching import phrase_in_text
from .research import BlueprintFacts, ResearchResult, _classify_build_method

_LIBRARY_DIR = Path(__file__).parent / "library"
_MANIFEST_PATH = _LIBRARY_DIR / "manifest.json"
_FACTS_PATH = _LIBRARY_DIR / "facts.json"


def _load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _manifest() -> dict:
    return _load_json(_MANIFEST_PATH)


@lru_cache(maxsize=1)
def _facts_index() -> dict:
    return _load_json(_FACTS_PATH)


def _match(index: dict, subject: str) -> dict | None:
    """Find `subject`'s entry: exact key first, then any recorded alias.

    Alias matching is what makes an ingested entry usable at all — without
    it, an entry would only ever match a prompt that happened to reduce to
    its exact manifest key. It goes through ``matching.phrase_in_text``:
    a plain substring test resolves "cat" to "cathedral" and "at" to
    "vatican city", and a manifest keyed by landmark name is exactly where
    that bites. Longest alias first, so a specific entry beats a generic
    one that happens to be contained in it.
    """
    text = subject.strip().lower()
    if not text:
        return None
    entry = index.get(text)
    if entry:
        return entry
    # Same rule as known_facts.get_known_facts, so a prompt resolves to the
    # same subject whether its facts come from the bundle or the curated
    # table: alias-inside-subject always, subject-inside-alias only when the
    # subject is at least two words. The two-word floor is what stops a bare
    # "cat" matching an entry aliased "notre-dame cathedral".
    subject_is_specific = len(text.split()) >= 2
    candidates = []
    for key, entry in index.items():
        for alias in (entry.get("aliases") or [key]):
            alias = alias.strip().lower()
            if phrase_in_text(alias, text) or (subject_is_specific and phrase_in_text(text, alias)):
                candidates.append((len(alias), entry))
    if not candidates:
        return None
    return max(candidates, key=lambda pair: pair[0])[1]


def get_cached_facts(subject: str) -> BlueprintFacts | None:
    """Dimensions recorded for `subject` at ingest time, or None."""
    entry = _match(_facts_index(), subject)
    if not entry:
        return None
    return BlueprintFacts(
        height_m=entry.get("height_m"),
        width_m=entry.get("width_m"),
        diameter_m=entry.get("diameter_m"),
        floors=entry.get("floors"),
    )


def get_local_reference(subject: str) -> ResearchResult | None:
    """Return a bundled ``ResearchResult`` for `subject` if the local
    library has one, else None. Never raises: any missing/malformed entry
    is treated the same as "not found" so a bad local file can't break
    generation."""
    entry = _match(_manifest(), subject)
    if not entry or not entry.get("image"):
        return None

    image_path = _LIBRARY_DIR / entry["image"]
    try:
        image = Image.open(image_path).convert("RGBA")
    except Exception:
        return None

    # Re-derived on every request from the stored article text, so a fix to
    # _classify_build_method reaches bundled entries immediately instead of
    # leaving them on whatever verdict was current when they were ingested.
    # An explicit override wins, for entries a human has corrected by hand.
    override = entry.get("build_method_override")
    if override in ("revolve", "relief"):
        build_method, reason = override, "set by hand in the reference library manifest"
    else:
        build_method, reason = _classify_build_method(
            entry.get("wikipedia_title", subject), entry.get("extract", "")
        )

    facts = BlueprintFacts(
        height_m=entry.get("height_m"),
        width_m=entry.get("width_m"),
        diameter_m=entry.get("diameter_m"),
        floors=entry.get("floors"),
    )
    if facts.summary():
        facts.source = entry.get("facts_source", "the bundled reference library")

    return ResearchResult(
        image=image,
        subject=subject,
        source_label=entry.get("source_label", "bundled local reference"),
        source_url=entry.get("source_url", ""),
        build_method=build_method,
        reason=reason,
        facts=facts,
        origin="library",
    )


def library_status() -> tuple[int, int]:
    """(bundled photos, cached dimension records) — for the UI's status line."""
    return (
        sum(1 for e in _manifest().values() if e.get("image")),
        len(_facts_index()),
    )
