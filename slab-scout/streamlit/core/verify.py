"""Extra checks that pin down the exact card after the first match:

- Serial numbers: a stamped "023/099", "/25" or "1/1" names the parallel exactly (only the Gold /10 has a /10
  print run), which colours alone can't do.
- The card back (sports): the card number, the © year and the set name are printed on the back, so base cards
  that look alike across years can be told apart.

Both only re-rank the matches already found (and offer the right parallel of the top card); they never name a
card on their own.
"""
from __future__ import annotations

import re

# 023/099, 23 / 99, #/25, 1/1, 1 of 1, one of one. Pokémon-style 201/198 collector numbers look the same, so a
# serial only counts when its total is a print run one of the card's parallels actually has.
SERIAL = re.compile(r"(?<![\d/])(\d{1,4})\s*(?:/|of)\s*(\d{1,4})(?![\d/])", re.I)
ONE_OF_ONE = re.compile(r"\b(?:1\s*(?:/|of)\s*1|one\s+of\s+one|1-of-1)\b", re.I)


def serials(text: str) -> list[tuple[int, int]]:
    out = []
    if ONE_OF_ONE.search(text or ""):
        out.append((1, 1))
    for a, b in SERIAL.findall(text or ""):
        n, of = int(a), int(b)
        if 0 < n <= of <= 9999 and (n, of) not in out:
            out.append((n, of))
    return out


def serial_fit(text: str, print_runs: set[int]) -> int | None:
    """The print run a serial on the card points to, if it is one the card's parallels have."""
    for n, of in serials(text):
        if of in print_runs:
            return of
    return None


# ---------- card back ----------
COPYRIGHT = re.compile(r"(?:©|\(c\)|copyright)\s*((?:19|20)\d\d)", re.I)
BACK_NUMBER = re.compile(r"(?:^|\s)(?:no\.?|#|card\s*(?:no\.?|#))\s*([A-Z]{0,4}-?\d{1,4}[A-Z]?)\b", re.I)


def back_facts(lines: list[tuple]) -> dict:
    """{'number', 'year', 'text'} read from the back of a sports card. The card number is usually printed near the
    top corner (often alone or after 'No.'/'#'); the © line gives the year it was printed."""
    text = "\n".join(t for t, *_ in lines)
    years = [int(y) for y in COPYRIGHT.findall(text)]
    year = max(years) if years else None
    number = ""
    m = BACK_NUMBER.search(text)
    if m:
        number = m.group(1)
    else:
        # a short number standing alone in the top fifth of the back
        for t, conf, y in lines:
            if y < 0.2 and conf > 0.6 and re.fullmatch(r"[A-Z]{0,4}-?\d{1,4}[A-Z]?", t.strip()):
                number = t.strip()
                break
    return {"number": number, "year": year, "text": text}


def number_matches(card_number: str, back_number: str) -> bool:
    a = re.sub(r"[^0-9a-z]", "", (card_number or "").lower()).lstrip("0")
    b = re.sub(r"[^0-9a-z]", "", (back_number or "").lower()).lstrip("0")
    return bool(a and b) and (a == b or a.endswith(b) or b.endswith(a))


def year_matches(set_year, printed: int | None) -> bool | None:
    """© year vs the set's year: equal, or one year later for season sets (2023-24 sets printed in 2024)."""
    try:
        sy = int(str(set_year)[:4])
    except (TypeError, ValueError):
        return None
    if not printed:
        return None
    return printed in (sy, sy + 1)
