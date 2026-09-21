#!/usr/bin/env python3
"""Automatically build VoxelCraft's bundled reference library.

This is the automated replacement for hand-curating ``library/manifest.json``
and ``known_facts.py`` one landmark at a time. For each subject it:

1. finds the matching Wikipedia article (title + intro text),
2. classifies how the photo should be rebuilt in 3D (``revolve`` vs
   ``relief``) with the *same* classifier the live app uses, so a bundled
   entry behaves identically to a live lookup,
3. pulls real-world dimensions from Wikidata,
4. finds a reference photo whose licence we are actually allowed to
   redistribute, and downloads it,
5. writes ``library/manifest.json``, ``library/facts.json``,
   ``library/ATTRIBUTION.md`` and the images themselves.

Licence gate
------------
``library/README.md`` sets the policy: only images we can confirm are
public domain / CC0, or CC-BY with attribution recorded, may be bundled.
Share-alike (CC-BY-SA) and non-free/fair-use files are *rejected*, not
downloaded — see ``_licence_ok``. Every accepted entry records its licence
and a source URL, and ``ATTRIBUTION.md`` is regenerated from those records.

Usage
-----
    python tools/ingest_library.py                      # default subject list
    python tools/ingest_library.py --subjects "eiffel tower" "lighthouse"
    python tools/ingest_library.py --facts-only         # dimensions, no images
    python tools/ingest_library.py --dry-run            # report, write nothing
    python tools/ingest_library.py --refresh            # re-do existing entries

``--api-base`` points every endpoint at a different origin; it exists so the
pipeline can be exercised end-to-end against local fixtures without hitting
the real services.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.voxelcraft.known_facts import iter_known_entries  # noqa: E402
from app.voxelcraft.research import (  # noqa: E402
    BlueprintFacts,
    _classify_build_method,
    _quantity_in_meters,
)

LIBRARY_DIR = REPO_ROOT / "app" / "voxelcraft" / "library"
IMAGES_DIR = LIBRARY_DIR / "images"
MANIFEST_PATH = LIBRARY_DIR / "manifest.json"
FACTS_PATH = LIBRARY_DIR / "facts.json"
ATTRIBUTION_PATH = LIBRARY_DIR / "ATTRIBUTION.md"

TIMEOUT_S = 20
HEADERS = {"User-Agent": "VoxelCraft/1.0 (reference-library ingest; +https://github.com/Kingatlasing/blank-app)"}

# Subjects worth bundling beyond the named landmarks: the common nouns the
# procedural shape table in text_generator.py already recognises, where a
# real photo gives a much better model than a hand-built primitive.
COMMON_SUBJECTS = [
    "lighthouse", "windmill", "water tower", "grain silo", "church steeple",
    "dog", "cat", "horse", "elephant", "owl",
    "oak tree", "pine tree", "cactus",
    "sailboat", "steam locomotive", "hot air balloon", "rocket",
    "acoustic guitar", "teapot", "wooden barrel", "park bench",
]


# --------------------------------------------------------------------------
# Licence gate
# --------------------------------------------------------------------------

# Normalised Wikimedia ``License`` values (and Openverse licence slugs) we are
# allowed to redistribute. Deliberately excludes every ``*-sa-*`` variant and
# anything non-free: see the module docstring.
_ALLOWED_EXACT = {"cc0", "pdm", "pd", "publicdomain", "public domain", "cc-pd-mark"}
_ALLOWED_SHORT_NAME_HINTS = ("public domain", "cc0")


def _licence_ok(license_code: str, short_name: str) -> bool:
    """True only for licences the bundle policy permits (PD/CC0/CC-BY)."""
    code = (license_code or "").strip().lower()
    short = (short_name or "").strip().lower()

    # Share-alike and non-commercial/no-derivatives are out, whatever else
    # the string says — check this before any accept rule.
    for banned in ("-sa", " sa", "share", "nc", "nd", "fair use", "non-free"):
        if banned in code or banned in short:
            return False

    if code in _ALLOWED_EXACT:
        return True
    if any(hint in short for hint in _ALLOWED_SHORT_NAME_HINTS):
        return True
    # "cc-by-4.0", "cc-by-3.0", "by" (Openverse's slug for plain CC-BY)
    if code == "by" or re.fullmatch(r"cc-by(-\d(\.\d)?)?", code):
        return True
    if re.fullmatch(r"cc by \d(\.\d)?", short):
        return True
    return False


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


# --------------------------------------------------------------------------
# Endpoints (overridable for fixture-based testing)
# --------------------------------------------------------------------------

@dataclass
class Endpoints:
    wikipedia: str = "https://en.wikipedia.org/w/api.php"
    wikidata: str = "https://www.wikidata.org/w/api.php"
    commons: str = "https://commons.wikimedia.org/w/api.php"
    openverse: str = "https://api.openverse.org/v1/images/"

    @classmethod
    def rooted_at(cls, base: str) -> "Endpoints":
        base = base.rstrip("/")
        return cls(
            wikipedia=f"{base}/wikipedia/w/api.php",
            wikidata=f"{base}/wikidata/w/api.php",
            commons=f"{base}/commons/w/api.php",
            openverse=f"{base}/openverse/v1/images/",
        )


def _get_json(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=TIMEOUT_S, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


# --------------------------------------------------------------------------
# Per-source lookups
# --------------------------------------------------------------------------

@dataclass
class Candidate:
    """A licence-cleared image we are allowed to bundle."""
    url: str
    source_label: str
    source_url: str
    license_code: str
    attribution: str


def wikipedia_article(ep: Endpoints, subject: str) -> tuple[str, str, str] | None:
    """(title, intro extract, lead image file name) for `subject`, or None."""
    data = _get_json(ep.wikipedia, {
        "action": "query", "generator": "search", "gsrsearch": subject, "gsrlimit": 1,
        "prop": "extracts|pageimages|info", "exintro": 1, "explaintext": 1, "exchars": 600,
        "piprop": "name", "inprop": "url", "format": "json",
    })
    for page in data.get("query", {}).get("pages", {}).values():
        title = page.get("title")
        if not title:
            continue
        return title, page.get("extract", "") or "", page.get("pageimage", "") or ""
    return None


def wikidata_facts(ep: Endpoints, title: str) -> BlueprintFacts:
    """Real-world dimensions for `title` from Wikidata, or an empty record."""
    data = _get_json(ep.wikipedia, {
        "action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
        "titles": title, "format": "json",
    })
    qid = None
    for page in data.get("query", {}).get("pages", {}).values():
        qid = page.get("pageprops", {}).get("wikibase_item")
        if qid:
            break
    if not qid:
        return BlueprintFacts()

    entity = _get_json(ep.wikidata, {
        "action": "wbgetentities", "ids": qid, "props": "claims", "format": "json",
    })
    claims = entity.get("entities", {}).get(qid, {}).get("claims", {})

    floors = None
    try:
        floors = int(round(float(claims["P1101"][0]["mainsnak"]["datavalue"]["value"]["amount"])))
    except Exception:
        pass

    return BlueprintFacts(
        height_m=_quantity_in_meters(claims, "P2048"),
        width_m=_quantity_in_meters(claims, "P2049"),
        diameter_m=_quantity_in_meters(claims, "P2386"),
        floors=floors,
    )


def commons_candidate(ep: Endpoints, file_name: str, max_dim: int) -> Candidate | None:
    """The article's lead image, but only if its licence clears the gate."""
    if not file_name:
        return None
    title = file_name if file_name.lower().startswith("file:") else f"File:{file_name}"
    data = _get_json(ep.commons, {
        "action": "query", "titles": title, "prop": "imageinfo",
        "iiprop": "extmetadata|url", "iiurlwidth": max_dim, "format": "json",
    })
    for page in data.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        code = (meta.get("License", {}) or {}).get("value", "")
        short = (meta.get("LicenseShortName", {}) or {}).get("value", "")
        if not _licence_ok(code, short):
            return None
        artist = _strip_html((meta.get("Artist", {}) or {}).get("value", "")) or "unknown"
        url = info.get("thumburl") or info.get("url")
        if not url:
            return None
        return Candidate(
            url=url,
            source_label=f"Wikimedia Commons: {title[5:]} by {artist} ({short or code})",
            source_url=info.get("descriptionurl", f"https://commons.wikimedia.org/wiki/{title}"),
            license_code=(code or short).lower(),
            attribution=artist,
        )
    return None


def openverse_candidate(ep: Endpoints, subject: str) -> Candidate | None:
    """Fallback photo search, restricted at the API to CC0/CC-BY only."""
    data = _get_json(ep.openverse, {
        "q": subject, "page_size": 5, "license": "cc0,pdm,by",
    })
    for result in data.get("results", []):
        code = (result.get("license") or "").lower()
        if not _licence_ok(code, result.get("license_version", "")):
            continue
        url = result.get("url") or result.get("thumbnail")
        if not url:
            continue
        creator = result.get("creator") or "unknown"
        return Candidate(
            url=url,
            source_label=f"Openverse photo by {creator} ({code.upper()})",
            source_url=result.get("foreign_landing_url", "https://openverse.org"),
            license_code=code,
            attribution=creator,
        )
    return None


def download_image(url: str, dest: Path, max_dim: int) -> tuple[int, int]:
    """Fetch, normalise and save an image; returns its final (w, h).

    Re-encoded to a bounded-size PNG so the bundled library stays small and
    every entry loads identically regardless of the source's format.
    """
    resp = requests.get(url, timeout=TIMEOUT_S, headers=HEADERS)
    resp.raise_for_status()
    image = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    image.thumbnail((max_dim, max_dim), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, format="PNG", optimize=True)
    return image.size


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------

def _slug(subject: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-") or "subject"


def _facts_dict(facts: BlueprintFacts) -> dict:
    return {
        "height_m": facts.height_m,
        "width_m": facts.width_m,
        "diameter_m": facts.diameter_m,
        "floors": facts.floors,
    }


def _load_json(path: Path, default: dict) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return dict(default)


def ingest_subject(ep: Endpoints, subject: str, aliases: list[str], args) -> dict | None:
    """Ingest one subject. Returns its manifest entry, or None if nothing
    usable (no article, or no licence-cleared photo) was found."""
    article = wikipedia_article(ep, subject)
    if article is None:
        print(f"  ! no Wikipedia article for {subject!r}")
        return None
    title, extract, lead_file = article

    # Store the *inputs* to the 3D-reconstruction decision (title + article
    # extract), not the verdict. Storing the verdict would freeze it: every
    # later fix to _classify_build_method would silently miss entries already
    # ingested, and nothing would flag them as stale. Re-deriving per request
    # costs one regex pass over ~600 characters and cannot rot.
    # `build_method_override` stays available for a human correction.
    build_method, reason = _classify_build_method(title, extract)
    facts = wikidata_facts(ep, title)

    entry = {
        "aliases": sorted({subject, title.lower(), *aliases}),
        "wikipedia_title": title,
        "extract": extract,
        "build_method_override": None,
        **_facts_dict(facts),
    }

    if args.facts_only:
        entry["image"] = None
        print(f"  + {subject}: facts only ({facts.summary() or 'no dimensions'})")
        return entry

    candidate = commons_candidate(ep, lead_file, args.max_dim) or openverse_candidate(ep, subject)
    if candidate is None:
        print(f"  - {subject}: no licence-cleared photo (article image rejected or absent)")
        return None

    rel_path = f"images/{_slug(subject)}.png"
    if args.dry_run:
        print(f"  ~ {subject}: would fetch {candidate.url} -> {rel_path} [{candidate.license_code}]")
    else:
        size = download_image(candidate.url, LIBRARY_DIR / rel_path, args.max_dim)
        print(f"  + {subject}: {rel_path} {size[0]}x{size[1]} [{candidate.license_code}] "
              f"{build_method}, {facts.summary() or 'no dimensions'}")

    entry.update({
        "image": rel_path,
        "source_label": candidate.source_label,
        "source_url": candidate.source_url,
        "license": candidate.license_code,
        "attribution": candidate.attribution,
    })
    return entry


def write_attribution(manifest: dict) -> str:
    lines = [
        "# Bundled reference photo attribution",
        "",
        "Generated by `tools/ingest_library.py` — do not edit by hand.",
        "",
        "Every image below was accepted only because its licence is public domain,",
        "CC0, or CC-BY. Share-alike and non-free files are rejected by the ingest.",
        "",
    ]
    for key in sorted(manifest):
        entry = manifest[key]
        if not entry.get("image"):
            continue
        lines.append(f"- **{key}** — `{entry['image']}` — {entry.get('source_label', 'unknown source')} "
                     f"— [source]({entry.get('source_url', '')}) — licence: `{entry.get('license', 'unknown')}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--subjects", nargs="+", help="subjects to ingest (default: landmarks + common nouns)")
    parser.add_argument("--facts-only", action="store_true", help="record dimensions only, download no images")
    parser.add_argument("--dry-run", action="store_true", help="report what would happen; write nothing")
    parser.add_argument("--refresh", action="store_true", help="re-ingest subjects already in the manifest")
    parser.add_argument("--max-dim", type=int, default=640, help="longest edge of a bundled image (default 640)")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between subjects, to stay polite to the APIs")
    parser.add_argument("--api-base", help="override every endpoint's origin (for fixture-based testing)")
    args = parser.parse_args(argv)

    ep = Endpoints.rooted_at(args.api_base) if args.api_base else Endpoints()

    # Subject -> aliases. Landmarks reuse the aliases already curated in
    # known_facts.py so an ingested entry matches every phrasing that table
    # matches; common nouns are their own single alias.
    known = {aliases[0]: list(aliases) for aliases, _facts in iter_known_entries()}
    if args.subjects:
        targets = {s.strip().lower(): known.get(s.strip().lower(), [s.strip().lower()]) for s in args.subjects}
    else:
        targets = dict(known)
        for noun in COMMON_SUBJECTS:
            targets.setdefault(noun, [noun])

    manifest = _load_json(MANIFEST_PATH, {})
    facts_cache = _load_json(FACTS_PATH, {})

    ingested = skipped = failed = 0
    print(f"Ingesting {len(targets)} subject(s) into {LIBRARY_DIR}")
    for subject, aliases in targets.items():
        if subject in manifest and not args.refresh:
            skipped += 1
            continue
        try:
            entry = ingest_subject(ep, subject, aliases, args)
        except requests.RequestException as exc:
            print(f"  ! {subject}: lookup failed ({exc.__class__.__name__}: {exc})")
            failed += 1
            continue
        except Exception as exc:  # noqa: BLE001 - one bad subject must not end the run
            print(f"  ! {subject}: {exc.__class__.__name__}: {exc}")
            failed += 1
            continue

        if entry is None:
            failed += 1
            continue
        ingested += 1
        if entry.get("image"):
            manifest[subject] = entry
        dims = {k: v for k, v in _facts_dict(BlueprintFacts(
            height_m=entry["height_m"], width_m=entry["width_m"],
            diameter_m=entry["diameter_m"], floors=entry["floors"],
        )).items() if v is not None}
        if dims:
            facts_cache[subject] = {"aliases": entry["aliases"], **dims}
        if args.delay:
            time.sleep(args.delay)

    print(f"\n{ingested} ingested, {skipped} already present, {failed} without usable data")

    if args.dry_run:
        print("(dry run — nothing written)")
        return 0

    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    FACTS_PATH.write_text(json.dumps(facts_cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ATTRIBUTION_PATH.write_text(write_attribution(manifest), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH.name} ({len(manifest)} entries), "
          f"{FACTS_PATH.name} ({len(facts_cache)} entries), {ATTRIBUTION_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
