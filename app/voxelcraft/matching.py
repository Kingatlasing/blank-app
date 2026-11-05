"""Whole-word keyword matching, shared by every part of VoxelCraft that
decides what a prompt or an article is *about*.

Substring matching is the obvious thing to reach for and it is wrong in a
way that is easy to miss: "cat" is inside "cathedral", "man" is inside
"mansion", "house" is inside "lighthouse", "dome" is inside
"domesticated". Every one of those produced a real wrong model before this
module existed, so all subject matching goes through here.
"""

from __future__ import annotations

import re
from functools import lru_cache


# Both matchers bound their needle with ``(?<!\w)`` / ``(?!\w)`` rather
# than ``\b``. ``\b`` is defined as a word/non-word transition, so it
# silently fails to match next to a needle that itself begins or ends in
# punctuation: ``\bst\.\b`` never matches "st. basil", because "." and
# " " are both non-word. Keywords like "bench (furniture)" or "st." are
# ordinary entries in a manifest, so the lookarounds are the safe form.
@lru_cache(maxsize=2048)
def _pattern(keyword: str) -> re.Pattern[str]:
    if " " in keyword or "-" in keyword:
        # Multi-word keywords take no trailing 's': the plural, if any,
        # belongs on the last word and is rare in practice.
        return re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)")
    return re.compile(rf"(?<!\w){re.escape(keyword)}s?(?!\w)")


def word_matches(keyword: str, text: str) -> bool:
    """True if `keyword` appears in `text` as a whole word (optionally
    pluralized with a trailing 's'), rather than merely as a substring.

    ``\\b{keyword}\\w*\\b`` looks like the same thing and is a trap: it
    matches any word that merely *starts with* the keyword, so "dome"
    matched "domesticated" and "cup" matched "cupboard" in testing.
    """
    return _pattern(keyword).search(text) is not None


def phrase_in_text(phrase: str, text: str) -> bool:
    """True if `phrase` occurs in `text` on word boundaries. Unlike
    ``word_matches`` this never accepts a plural, so it is the right
    check for proper names ("big ben" in "the big ben clock tower") and
    for alias tables, whose entries may be parenthesized or abbreviated
    ("bench (furniture)", "st. basil's cathedral")."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None
