"""Read a graded slab's label: grading company, grade, cert number, and the card described on the label.

Label layouts (top of the slab):
  PSA:  "2023 POKEMON SV 151 #199 / CHARIZARD EX / SPECIAL ILLUSTRATION RARE" · "GEM MT 10" · cert "12345678"
  CGC:  "Charizard ex" · "Pokémon (2023) · 151 · 199/165" · "GEM MINT 10" · cert "1234567890"
  BGS:  "2023 Pokemon 151 #199 Charizard ex" · "GEM MINT 9.5" · subgrades "CENTERING 9.5 EDGES 9.5 ..." · cert
  TAG:  card line · "GEM MINT 10" / score · cert
  SGC:  card line · "10 GEM MINT" · cert
"""
from __future__ import annotations

import re

COMPANIES = {
    "PSA": [r"\bPSA\b", r"PSACARD", r"PSA/DNA"],
    "CGC": [r"\bCGC\b", r"CGCCARDS", r"CERTIFIED GUARANTY"],
    "BGS": [r"\bBGS\b", r"BECKETT", r"\bBVG\b", r"\bBCCG\b"],
    "TAG": [r"\bTAG\b(?!\s*TEAM)", r"TAGGRADING", r"TAG GRADING"],
    "SGC": [r"\bSGC\b", r"SPORTSCARD GUARANTY"],
}
GRADE_WORDS = [
    (r"BLACK\s*LABEL|PRISTINE\s*10", 10, "PRISTINE"),
    (r"GEM\s*-?\s*M(IN)?T\.?\s*10|GEM\s*MINT\s*10|10\s*GEM\s*M(IN)?T", 10, "GEM MINT"),
    (r"MINT\s*\+\s*9\.5|GEM\s*MINT\s*9\.5|9\.5\s*(GEM\s*)?MINT\+?", 9.5, "MINT+"),
    (r"(?<!NM-)(?<!NM )MINT\s*9(?!\.)|9\s*MINT", 9, "MINT"),
    (r"NM\s*-?\s*MT\s*\+?\s*8\.5|8\.5\s*NM", 8.5, "NM-MT+"),
    (r"NM\s*-?\s*MT\s*8(?!\.)|NEAR\s*MINT\s*-?\s*MINT\s*8|8\s*NM\s*-?\s*MT", 8, "NM-MT"),
    (r"\bNM\s*7|NEAR\s*MINT\s*7|7\s*NM\b", 7, "NM"),
    (r"EX\s*-?\s*MT\s*6|6\s*EX\s*-?\s*MT", 6, "EX-MT"),
    (r"\bEX\s*5|5\s*EX\b", 5, "EX"),
    (r"VG\s*-?\s*EX\s*4|4\s*VG\s*-?\s*EX", 4, "VG-EX"),
    (r"\bVG\s*3|3\s*VG\b", 3, "VG"),
    (r"GOOD\s*2|2\s*GOOD", 2, "GOOD"),
    (r"FAIR\s*1\.5|1\.5\s*FAIR", 1.5, "FAIR"),
    (r"POOR\s*1|1\s*POOR", 1, "POOR"),
    (r"\bAUTHENTIC\b", None, "AUTHENTIC"),
]
QUALIFIERS = ["OC", "ST", "PD", "OF", "MK", "MC"]
CERT_LOOKUP = {
    "PSA": "https://www.psacard.com/cert/{c}",
    "CGC": "https://www.cgccards.com/certlookup/{c}/",
    "BGS": "https://www.beckett.com/grading/card-lookup?item_type=BGS&item_id={c}",
    "TAG": "https://my.taggrading.com/card/{c}",
    "SGC": "https://gosgc.com/cert-code-lookup?certCode={c}",
}


def read_label(lines: list[tuple[str, float, float]]) -> dict | None:
    """Returns slab info if the text looks like a grading label, else None."""
    texts = [t for t, c, _ in lines if c > 0.45]
    up = "\n".join(texts).upper()
    company = ""
    for name, pats in COMPANIES.items():
        if any(re.search(p, up) for p in pats):
            company = name
            break
    # OCR often runs label words together or reads G as 6 ("6EMMT"): normalise before matching
    upn = re.sub(r"6EM(?=\s*M)", "GEM", up)
    upn = re.sub(r"GEM\s*M(IN)?T", lambda m: "GEM MINT" if m.group(1) else "GEM MT", upn)
    upn = re.sub(r"NM\s*-?\s*MT", "NM-MT", upn)
    grade, label = None, ""
    for pat, g, lab in GRADE_WORDS:
        m = re.search(pat, upn)
        if m:
            grade = g
            label = re.sub(r"\s+", " ", re.sub(r"(?<!\S)[\d.]+(?!\S)|\d+(\.\d)?$|^\d+(\.\d)?", " ", m.group(0))).strip(" -") or lab
            break
    if grade is None:
        # grade words and the number are often separate lines: "GEM MT" … "10"
        words = [(r"PRISTINE", "PRISTINE", 10), (r"GEM\s*M(INT|T)", "GEM MINT", 10), (r"MINT\s*\+", "MINT+", 9.5),
                 (r"NM-MT\s*\+", "NM-MT+", 8.5), (r"NM-MT", "NM-MT", 8), (r"EX-MT", "EX-MT", 6), (r"VG-EX", "VG-EX", 4),
                 (r"(?<![A-Z-])MINT(?![A-Z])", "MINT", 9), (r"\bNM\b|NEAR MINT", "NM", 7)]
        for pat, lab, dflt in words:
            if re.search(pat, upn):
                label = lab
                nums = [float(t) for t, c, _ in lines if re.fullmatch(r"\s*(10|9\.5|[1-9](\.5)?)\s*", t) and c > 0.45]
                grade = nums[0] if nums else dflt
                grade = int(grade) if grade == int(grade) else grade
                break
    tag_score = None
    if company == "TAG":
        m = re.search(r"\b(\d{3,4})\s*(?:/\s*1000|PTS|SCORE)", up) or re.search(r"SCORE\s*(\d{3,4})", up)
        if m and 100 <= int(m.group(1)) <= 1000:
            tag_score = int(m.group(1))
    if not company and grade is None:
        return None
    if grade is None:  # a lone grade number on the label
        m = re.search(r"(?<![\d#/.])(10|9\.5|[1-9](?:\.5)?)(?![\d/])", up)
        if m and company:
            grade = float(m.group(1))
            if grade == int(grade):
                grade = int(grade)
    # cert number: the longest 7-10 digit run that isn't a year
    certs = [c for c in re.findall(r"(?<!\d)(\d{7,10})(?!\d)", up.replace(" ", "")) if not re.fullmatch(r"(19|20)\d{2}", c)]
    cert = max(certs, key=len) if certs else ""
    quals = [q for q in QUALIFIERS if re.search(rf"\b{q}\b", up) and company == "PSA"]
    subs = {}
    for k in ("CENTERING", "CORNERS", "EDGES", "SURFACE"):
        m = re.search(rf"{k}\s*(\d{{1,2}}(?:\.5)?)", up)
        if m:
            subs[k.lower()] = float(m.group(1))

    # card description = label lines minus company / grade / cert / boilerplate
    texts = [re.sub(r"6EM\s*M(IN)?T|GEM\s*M(IN)?T|NM\s*-?\s*MT", " ", t, flags=re.I) for t in texts]
    skip = re.compile(r"PSA|CGC|BGS|BECKETT|SGC|TAG\b|CERT|GRADING|GUARANT|AUTHENTIC|PRISTINE|GEM|MINT|NM-MT|NM\b|EX-MT|VG|"
                      r"CENTERING|CORNERS|EDGES|SURFACE|^\d{7,10}$|^\s*(10|9\.5|[1-9](\.5)?)\s*$", re.I)
    desc = [t for t in texts if not skip.search(t.upper()) and len(t.strip()) > 1][:4]
    blob = " ".join(desc)
    ym = re.search(r"\b(19[4-9]\d|20[0-3]\d)\b", blob)
    year = ym.group(1) if ym else ""
    num = ""
    m = re.search(r"#\s*([A-Z]{0,4}-?\d{1,4}[A-Z]?)", blob, re.I) or re.search(r"\b(\d{1,3}/\d{2,3})\b", blob)
    if m:
        num = m.group(1)
    return {
        "company": company or "Unknown", "grade": grade, "label": label, "cert": cert, "qualifiers": quals,
        "subgrades": subs, "tag_score": tag_score, "desc": blob.strip(), "desc_lines": desc, "year": year, "number": num,
        "lookup": CERT_LOOKUP.get(company, "").format(c=cert) if cert and company in CERT_LOOKUP else "",
    }


def grade_text(s: dict) -> str:
    g = s.get("grade")
    g = f"{g:g}" if isinstance(g, (int, float)) else (s.get("label") or "?")
    q = (" " + " ".join(s["qualifiers"])) if s.get("qualifiers") else ""
    lab = f" {s['label']}" if s.get("label") and s.get("label") != "AUTHENTIC" else ""
    return f"{s['company']}{lab} {g}{q}".replace("  ", " ").strip()


def name_guess(s: dict) -> str:
    """Card name from the label description, e.g. 'CHARIZARD EX' from '2023 POKEMON SV 151 #199 CHARIZARD EX'."""
    t = s.get("desc", "")
    t = re.sub(r"\b(19[4-9]\d|20[0-3]\d)\b", " ", t)
    t = re.sub(r"#\s*\S+", " ", t)
    t = re.sub(r"\b\d{1,3}/\d{2,3}\b", " ", t)
    t = re.sub(r"\b(POKEMON|POKÉMON|JAPANESE|ENGLISH|TOPPS|PANINI|PRIZM|BOWMAN|UPPER DECK|DONRUSS|KAKAWOW|YU-GI-OH!?|MAGIC|HOLO|REV(ERSE)?\.?\s*HOLO|1ST EDITION|SPECIAL ILLUSTRATION RARE|ILLUSTRATION RARE|FULL ART|SECRET|PROMO)\b", " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()
