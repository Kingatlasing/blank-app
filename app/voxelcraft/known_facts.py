"""Verified real-world dimensions for 37 well-known landmarks, hand-curated
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

from .matching import phrase_in_text
from .research import BlueprintFacts

# (aliases, facts) — checked in order, first alias match wins. Aliases are
# full phrases, or a single *distinctive* word ("eiffel", "parthenon"),
# never a generic one like "tower" or "bridge", so a random prompt
# containing that word can't accidentally match. See ``get_known_facts``
# for how they are matched.
_ENTRIES: list[tuple[list[str], BlueprintFacts]] = [
    (["eiffel tower", "eiffel"], BlueprintFacts(height_m=330.0, width_m=125.0)),
    (["statue of liberty", "lady liberty"], BlueprintFacts(height_m=93.0, width_m=19.0)),
    (["big ben", "elizabeth tower"], BlueprintFacts(height_m=96.0, width_m=12.0)),
    (["leaning tower of pisa", "tower of pisa"], BlueprintFacts(height_m=56.0, diameter_m=15.5)),
    (["great pyramid of giza", "pyramid of giza", "pyramids of giza", "pyramid of khufu"],
     BlueprintFacts(height_m=138.5, width_m=230.3)),
    (["parthenon"], BlueprintFacts(height_m=13.7, width_m=30.9)),
    (["golden gate bridge"], BlueprintFacts(height_m=227.0)),
    (["taj mahal"], BlueprintFacts(height_m=73.0, diameter_m=17.7)),
    (["sydney opera house"], BlueprintFacts(height_m=65.0)),
    (["empire state building"], BlueprintFacts(height_m=443.0, floors=103)),
    (["colosseum", "coliseum"], BlueprintFacts(height_m=48.0, width_m=156.0)),
    (["christ the redeemer"], BlueprintFacts(height_m=30.0, width_m=28.0)),
    (["space needle"], BlueprintFacts(height_m=184.0, diameter_m=42.0)),
    (["burj khalifa"], BlueprintFacts(height_m=828.0, floors=163)),
    (["cn tower"], BlueprintFacts(height_m=553.3)),
    (["washington monument"], BlueprintFacts(height_m=169.0, width_m=16.8)),
    (["arc de triomphe"], BlueprintFacts(height_m=49.5, width_m=44.8)),
    (["notre-dame cathedral", "notre dame cathedral", "notre-dame de paris"],
     BlueprintFacts(height_m=96.0)),
    (["sagrada familia", "sagrada família"], BlueprintFacts(height_m=172.5)),
    (["saint basil's cathedral", "st basil's cathedral", "st. basil's cathedral"],
     BlueprintFacts(height_m=47.5)),
    (["hagia sophia"], BlueprintFacts(height_m=55.6, diameter_m=31.7)),
    (["gateway arch"], BlueprintFacts(height_m=192.0, width_m=192.0)),
    (["tokyo tower"], BlueprintFacts(height_m=333.0)),
    (["petronas towers", "petronas twin towers", "petronas"], BlueprintFacts(height_m=452.0, floors=88)),
    (["one world trade center", "freedom tower"], BlueprintFacts(height_m=541.3)),
    (["chrysler building"], BlueprintFacts(height_m=319.0, floors=77)),
    (["mount rushmore"], BlueprintFacts(height_m=18.0)),
    (["stonehenge"], BlueprintFacts(height_m=4.0, diameter_m=30.0)),
    (["neuschwanstein castle", "neuschwanstein"], BlueprintFacts(height_m=65.0)),
    (["angkor wat"], BlueprintFacts(height_m=65.0)),
    (["petra treasury", "al-khazneh", "al khazneh"], BlueprintFacts(height_m=39.0, width_m=25.0)),
    (["el castillo", "chichen itza", "kukulcan pyramid", "pyramid of kukulcan"],
     BlueprintFacts(height_m=30.0, width_m=55.3)),
    (["blue mosque"], BlueprintFacts(height_m=43.0, diameter_m=23.5)),
    (["london eye"], BlueprintFacts(height_m=135.0, diameter_m=120.0)),
    (["willis tower", "sears tower"], BlueprintFacts(height_m=442.3, floors=110)),
    (["shanghai tower"], BlueprintFacts(height_m=632.0, floors=128)),
    (["burj al arab"], BlueprintFacts(height_m=321.0, floors=56)),
]


def get_known_facts(subject: str) -> BlueprintFacts | None:
    """Return hand-curated facts for `subject` if it names one of the
    entries above, else None.

    Matching is on whole words in both directions:

    - alias inside subject, so "the eiffel tower in paris" finds the
      Eiffel Tower;
    - subject inside alias, so a partial name like "notre-dame cathedral"
      still finds "notre-dame de paris" — but only when the subject is at
      least two words.

    That two-word floor is the whole point of this function being more
    than an ``in`` check. A bare "a cat" used to come back as Notre-Dame
    (``"cat" in "notre-dame cathedral"``), "a house" as the Sydney Opera
    House, and "a tower" as the Eiffel Tower, which then stretched those
    models to a landmark's real-world proportions. A one-word subject now
    has to be an alias in its own right (hence "eiffel" and "petronas"
    appearing explicitly above).
    """
    text = subject.strip().lower()
    if not text:
        return None
    subject_is_specific = len(text.split()) >= 2
    for aliases, facts in _ENTRIES:
        for alias in aliases:
            if phrase_in_text(alias, text):
                return facts
            if subject_is_specific and phrase_in_text(text, alias):
                return facts
    return None


def iter_known_entries() -> list[tuple[list[str], BlueprintFacts]]:
    """The curated table as ``(aliases, facts)`` pairs, in match order.

    Exposed for ``tools/ingest_library.py``, which reuses these aliases so an
    automatically-ingested landmark matches every phrasing this table already
    matches, instead of only its canonical name."""
    return [(list(aliases), facts) for aliases, facts in _ENTRIES]
