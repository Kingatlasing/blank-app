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
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image

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


def _alias_matches(alias: str, text: str) -> bool:
    """True when `alias` occurs in `text` as a whole word/phrase.

    Deliberately *not* a plain substring test in either direction. Checking
    ``text in alias`` lets a short subject match inside a longer alias, which
    is a false-positive machine: "cat" matches "cathedral" and "at" matches
    "vatican city". Checking ``alias in text`` without word boundaries has
    the same problem in reverse. So an entry matches only when its alias
    appears as an actual word run, which still lets "the eiffel tower in
    paris" hit the "eiffel tower" entry.

    Boundaries are lookarounds rather than ``\b`` because an alias can end in
    punctuation — ``\b`` never matches after the ")" in "bench (furniture)",
    so that alias could never match itself.

    NOTE: this duplicates the whole-word logic in ``research._word_matches``;
    both should move to the shared matcher module when it lands.
    """
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text) is not None


def _match(index: dict, subject: str) -> dict | None:
    """Find `subject`'s entry: exact key first, then any recorded alias.

    Alias matching is what makes an ingested entry usable at all — without
    it, an entry would only ever match a prompt that happened to reduce to
    its exact manifest key. Longest alias first, so a specific entry beats a
    generic one that happens to be a prefix of it.
    """
    text = subject.strip().lower()
    if not text:
        return None
    entry = index.get(text)
    if entry:
        return entry
    candidates = []
    for key, entry in index.items():
        for alias in (entry.get("aliases") or [key]):
            if _alias_matches(alias.strip().lower(), text):
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

    build_method = entry.get("build_method")
    if build_method not in ("revolve", "relief"):
        build_method, _reason = _classify_build_method(subject, "")
    reason = entry.get("classified_because") or f"bundled reference library entry ({build_method})"

    facts = BlueprintFacts(
        height_m=entry.get("height_m"),
        width_m=entry.get("width_m"),
        diameter_m=entry.get("diameter_m"),
        floors=entry.get("floors"),
    )

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
