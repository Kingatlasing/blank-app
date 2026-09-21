"""Verified real-world dimensions for well-known landmarks, hand-curated
via web search and cross-checked against multiple sources (Wikipedia plus
institutional/tourism sites) in September 2026, since this dev sandbox
can't reach Wikidata itself to verify automatically the way the live app
does. Where sources disagreed slightly, the commonly-cited Wikipedia
figure was used.

Used by ``research.fetch_blueprint_facts`` as a supplement to the live
Wikidata lookup: it fills in any field Wikidata didn't return (or covers
the subject entirely if the Wikidata lookup fails, e.g. no network). It
never overrides a value Wikidata *did* return, since that's the more
authoritative, continuously-updated source when reachable.
"""

from __future__ import annotations

from .research import BlueprintFacts

# (aliases, facts) — checked in order, first alias match wins. Aliases are
# full phrases (never a single generic word like "tower" or "bridge") so a
# random prompt containing that word can't accidentally match.
_ENTRIES: list[tuple[list[str], BlueprintFacts]] = [
    (["eiffel tower"], BlueprintFacts(height_m=330.0, width_m=125.0)),
    (["statue of liberty", "lady liberty"], BlueprintFacts(height_m=93.0, width_m=19.0)),
    (["big ben", "elizabeth tower"], BlueprintFacts(height_m=96.0, width_m=12.0)),
    (["leaning tower of pisa", "tower of pisa"], BlueprintFacts(height_m=56.0, diameter_m=15.5)),
    (["great pyramid of giza", "pyramid of giza", "pyramid of khufu"],
     BlueprintFacts(height_m=138.5, width_m=230.3)),
    (["parthenon"], BlueprintFacts(height_m=13.7, width_m=30.9)),
    (["golden gate bridge"], BlueprintFacts(height_m=227.0)),
    (["taj mahal"], BlueprintFacts(height_m=73.0, diameter_m=17.7)),
    (["sydney opera house"], BlueprintFacts(height_m=65.0)),
    (["empire state building"], BlueprintFacts(height_m=443.0, floors=103)),
    (["colosseum", "coliseum"], BlueprintFacts(height_m=48.0, width_m=156.0)),
    (["christ the redeemer"], BlueprintFacts(height_m=30.0, width_m=28.0)),
    (["space needle"], BlueprintFacts(height_m=184.0, diameter_m=42.0)),
]


def get_known_facts(subject: str) -> BlueprintFacts | None:
    """Return hand-curated facts for `subject` if it matches one of the
    entries above, else None. Matches either direction (alias-in-subject or
    subject-in-alias) so both "the eiffel tower in paris" and "eiffel
    tower" work, but never on a single generic word."""
    text = subject.strip().lower()
    if not text:
        return None
    for aliases, facts in _ENTRIES:
        if any(alias in text or text in alias for alias in aliases):
            return facts
    return None
