"""A small, curated set of reference photos bundled with the app itself
(see ``library/README.md`` for the schema and how to add entries).

Checked before any live Wikipedia/Openverse lookup in ``research.py``: a
bundled entry never depends on network access, never rate-limits, and has
already been vetted by a human rather than trusted blind at generation
time. When the manifest has no entry for a subject (currently always,
since the bundled manifest ships empty) this is a no-op and the caller
falls through to the live research path exactly as before.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .research import BlueprintFacts, ResearchResult, _classify_build_method

_LIBRARY_DIR = Path(__file__).parent / "library"
_MANIFEST_PATH = _LIBRARY_DIR / "manifest.json"


def _load_manifest() -> dict:
    try:
        with open(_MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_local_reference(subject: str) -> ResearchResult | None:
    """Return a bundled ``ResearchResult`` for `subject` if the local
    library has one, else None. Never raises: any missing/malformed entry
    is treated the same as "not found" so a bad local file can't break
    generation."""
    manifest = _load_manifest()
    entry = manifest.get(subject.strip().lower())
    if not entry:
        return None

    image_path = _LIBRARY_DIR / entry.get("image", "")
    try:
        image = Image.open(image_path).convert("RGBA")
    except Exception:
        return None

    build_method = entry.get("build_method")
    if build_method not in ("revolve", "relief"):
        build_method, _reason = _classify_build_method(subject, "")
    reason = f"served from the bundled local reference library ({build_method})"

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
    )
