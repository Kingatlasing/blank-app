"""A regression sweep over everything VoxelCraft has to get *right* rather
than merely not crash on: which landmark a prompt resolves to, which
reconstruction strategy a subject gets, which shape a prompt builds, and
which colors it picks up.

Run it with ``python3 tests/accuracy_sweep.py`` (no test framework, no
network — every case is a fixture, because the sandbox this is developed
in can't reach Wikipedia or Wikidata). It exits non-zero if anything
fails, and prints one line per case either way.

Nearly every case below is here because it once failed. The recurring
cause was substring matching standing in for word matching: "cat" inside
"cathedral", "man" inside "mansion", "house" inside "lighthouse", "night"
inside "knight", "structure" inside a description of literally any
landmark. ``app/voxelcraft/matching.py`` exists to keep that from coming
back, and the false-positive sections below are what prove it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from app.voxelcraft import (  # noqa: E402
    exporters, image_generator, local_library, text_generator, transform,
)
from app.voxelcraft.known_facts import _ENTRIES, get_known_facts  # noqa: E402
from app.voxelcraft.palette import PALETTE, find_color_words  # noqa: E402
from app.voxelcraft.matching import phrase_in_text, word_matches  # noqa: E402
from app.voxelcraft.research import (  # noqa: E402
    CURATED_SOURCE, BlueprintFacts, _classify_build_method, extract_subject,
    fetch_blueprint_facts, merge_facts,
)

KNOWN_HEX = {s.hex for s in PALETTE}
_failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {label}{(' :: ' + detail) if detail else ''}")
    if not ok:
        _failures.append(label)


def section(name: str) -> None:
    print(f"\n--- {name} ---")


# --------------------------------------------------------------------------
section("the word matcher itself")
for keyword, text, expected in [
    ("cat", "a cathedral", False),
    ("cat", "a cat", True),
    ("cat", "two cats", True),
    ("man", "a mansion", False),
    ("house", "a lighthouse", False),
    ("dome", "a domesticated dog", False),
    ("cup", "a cupboard", False),
    ("wishing well", "a wishing well", True),
    # Needles that begin or end in punctuation: \b is a word/non-word
    # transition, so it never matches beside one. Alias tables really do
    # contain these, so the matcher uses lookarounds instead.
    ("st.", "st. basil's cathedral", True),
    ("bench (furniture)", "a bench (furniture) listing", True),
]:
    got = word_matches(keyword, text)
    check(got == expected, f"word_matches({keyword!r}, {text!r}) is {expected}", f"got {got}")

for phrase, text, expected in [
    ("big ben", "the big ben clock tower", True),
    ("ben", "big ben", True),
    ("cat", "notre-dame cathedral", False),
    ("st. basil's cathedral", "st. basil's cathedral", True),
    ("bench (furniture)", "bench (furniture)", True),
]:
    got = phrase_in_text(phrase, text)
    check(got == expected, f"phrase_in_text({phrase!r}, {text!r}) is {expected}", f"got {got}")

# --------------------------------------------------------------------------
section("known landmark facts: every alias finds its own entry")
for index, (aliases, facts) in enumerate(_ENTRIES):
    for alias in aliases:
        got = get_known_facts(alias)
        owner = next((i for i, (_a, f) in enumerate(_ENTRIES) if f is got), None)
        check(got is facts, f"alias {alias!r}", f"resolved to entry {owner}, want {index}")

section("known landmark facts: partial and decorated names still match")
for prompt, expect_alias in [
    ("the eiffel tower in paris", "eiffel tower"),
    ("eiffel", "eiffel tower"),
    ("the colosseum in rome", "colosseum"),
    ("the pyramids of giza", "great pyramid of giza"),
    ("notre dame", "notre-dame cathedral"),
    ("petronas", "petronas towers"),
    ("the golden gate bridge", "golden gate bridge"),
]:
    got = get_known_facts(extract_subject(prompt))
    want = get_known_facts(expect_alias)
    check(got is want and got is not None, f"{prompt!r} -> {expect_alias!r}", repr(got))

section("known landmark facts: no false positives on generic prompts")
# Each of these used to match a landmark by substring and then stretch the
# model to that landmark's real-world proportions.
for prompt in [
    "a house", "a tower", "a bridge", "a statue", "a cathedral", "a monument",
    "an arch", "a pyramid", "a church", "a temple", "a castle", "a dog", "a cat",
    "a tree", "a sword", "a red car", "a lighthouse", "a boat", "a dragon",
    "a space ship", "a needle", "a big dog", "a ben", "liberty bell",
    "a modern office building", "a wooden bridge over a river", "a small church",
    "a garden gate", "a pisa pizza", "the great wall of china", "a windmill",
]:
    got = get_known_facts(extract_subject(prompt))
    matched = next((a[0] for a, f in _ENTRIES if f is got), None)
    check(got is None, f"{prompt!r} matches no landmark", f"matched {matched!r}")

# --------------------------------------------------------------------------
section("build-method classifier")
# (title, article intro, expected method). The intros are shortened but
# keep the wording that used to mislead the classifier.
for title, extract, expected in [
    ("Eiffel Tower", "The Eiffel Tower is a wrought-iron lattice tower on the Champ de "
     "Mars in Paris, France. It is the tallest structure in Paris.", "revolve"),
    ("Statue of Liberty", "The Statue of Liberty is a colossal neoclassical sculpture "
     "on Liberty Island in New York Harbor.", "revolve"),
    ("Leaning Tower of Pisa", "The Leaning Tower of Pisa is the campanile, or "
     "freestanding bell tower, of Pisa Cathedral.", "revolve"),
    ("Lighthouse", "A lighthouse is a tower, building, or other type of physical "
     "structure designed to emit light.", "revolve"),
    ("Washington Monument", "The Washington Monument is an obelisk on the National "
     "Mall in Washington, D.C.", "revolve"),
    ("Space Needle", "The Space Needle is an observation tower in Seattle.", "revolve"),
    ("Silo", "A silo is a structure for storing bulk materials.", "revolve"),
    ("Oak", "An oak is a tree or shrub in the genus Quercus.", "revolve"),
    ("Parthenon", "The Parthenon is a former temple on the Athenian Acropolis, "
     "Greece, dedicated to the goddess Athena.", "relief"),
    ("Golden Gate Bridge", "The Golden Gate Bridge is a suspension bridge.", "relief"),
    ("Sydney Opera House", "The Sydney Opera House is a multi-venue performing arts "
     "centre in Sydney.", "relief"),
    ("Dog", "The dog is a domesticated descendant of the gray wolf.", "relief"),
    ("Cat", "The cat is a small domesticated carnivorous mammal.", "relief"),
    ("Car", "A car is a wheeled motor vehicle used for transportation.", "relief"),
    ("Colosseum", "The Colosseum is an elliptical amphitheatre in Rome.", "relief"),
    ("Great Pyramid of Giza", "The Great Pyramid of Giza is the largest Egyptian "
     "pyramid and the tomb of pharaoh Khufu.", "relief"),
    ("Cupboard", "A cupboard is a piece of furniture with doors and shelves.", "relief"),
]:
    got, reason = _classify_build_method(title, extract)
    check(got == expected, f"{title} -> {expected}", f"got {got} ({reason})")

# --------------------------------------------------------------------------
section("subject extraction")
for prompt, expected in [
    ("a red house with a garden and a fence", "house"),
    ("a blue dragon", "dragon"),
    ("the eiffel tower in paris", "eiffel tower"),
    ("the golden gate bridge", "golden gate bridge"),   # color is part of the name
    ("the White House", "white house"),                 # capitalised -> a name
    ("the white house", "house"),                       # lowercase -> a description
    ("the Blue Mosque", "blue mosque"),
    ("an orange", "orange"),                            # nothing left if stripped
    ("Stonehenge", "stonehenge"),
]:
    got = extract_subject(prompt)
    check(got == expected, f"{prompt!r} -> {expected!r}", f"got {got!r}")

# --------------------------------------------------------------------------
section("color words")
for prompt, expected in [
    ("a knight", []),            # "night"
    ("a skyscraper", []),        # "sky"
    ("a sandwich", []),          # "sand"
    ("a police car", []),        # "ice"
    ("rosemary", []),            # "rose"
    ("a red house", ["red"]),
    ("a golden pickaxe", ["gold"]),
    ("a light blue sphere", ["light_blue", "blue"]),
]:
    got = find_color_words(prompt)
    check(got == expected, f"{prompt!r} -> {expected}", f"got {got}")

# --------------------------------------------------------------------------
section("prompt -> shape")
for prompt, expected_match in [
    ("a red house", "house"),
    ("a lighthouse", "lighthouse"),        # not lighthouse + house
    ("a multi-story mansion", "mansion"),  # not "man"
    ("a snowman", "snowman"),              # not "man" by luck
    ("a green dragon", "dragon"),
    ("an oak tree", "tree"),
    ("a diamond sword", "sword"),
    ("a cat", "cat"),
    ("a dog", "dog"),
    ("a greek temple", "temple"),
    ("a cube", "cube"),
]:
    _voxels, note = text_generator.generate_from_text(prompt)
    check(f"'{expected_match}'" in note, f"{prompt!r} builds {expected_match!r}", note)

section("prompt -> a valid model, whatever the prompt")
for prompt in [
    "a red house", "a wizard", "a castle with a knight and dragon", "a heart",
    "a 3 floor house with a spiral staircase", "two story house",
    "a purple witch's castle", "", "   ", "xyzzy plugh",
    "a blue sphere and a red cube", "a snowman riding a bicycle",
]:
    try:
        voxels, _note = text_generator.generate_from_text(prompt)
        assert voxels, "empty model"
        for voxel in voxels:
            x, y, z, color = voxel
            assert all(isinstance(n, int) for n in (x, y, z)), f"non-integer coord {voxel}"
            assert color in KNOWN_HEX, f"off-palette color {color}"
        placed = transform.normalize(voxels)
        assert min(v[0] for v in placed) == 0
        assert min(v[1] for v in placed) == 0
        assert min(v[2] for v in placed) == 0
        exporters.to_json(voxels)
        exporters.to_obj(voxels)
        exporters.to_mcfunction(voxels)
        transform.scale_voxels(voxels, 2)
        kept, _trimmed = transform.voxel_count_limit(voxels, 50)
        assert len(kept) <= 50
        check(True, f"{prompt!r}", f"{len(voxels)} voxels")
    except Exception as exc:  # noqa: BLE001 - the sweep reports, never crashes
        check(False, f"{prompt!r}", f"{type(exc).__name__}: {exc}")

# --------------------------------------------------------------------------
section("image reconstruction")


def _fixture(kind: str) -> Image.Image:
    image = Image.new("RGBA", (200, 300), (250, 250, 250, 255))
    draw = ImageDraw.Draw(image)
    if kind == "tower":
        draw.polygon([(100, 20), (150, 280), (50, 280)], fill=(120, 90, 60, 255))
    elif kind == "house":
        draw.rectangle([40, 150, 160, 280], fill=(180, 60, 50, 255))
        draw.polygon([(30, 150), (100, 70), (170, 150)], fill=(90, 60, 40, 255))
    return image


for kind in ("tower", "house"):
    for mode in ("flat", "relief", "revolve"):
        try:
            voxels = image_generator.image_to_voxels(_fixture(kind), resolution=24, mode=mode)
            assert voxels, "empty model"
            for x, y, z, color in voxels:
                assert all(isinstance(n, int) for n in (x, y, z))
                assert color in KNOWN_HEX, f"off-palette color {color}"
            exporters.to_obj(voxels)
            check(True, f"{kind}/{mode}", f"{len(voxels)} voxels")
        except Exception as exc:  # noqa: BLE001
            check(False, f"{kind}/{mode}", f"{type(exc).__name__}: {exc}")

# A uniform image is all background, so background removal correctly leaves
# nothing and the caller falls back to the procedural generator.
for kind, image in [("uniform", Image.new("RGBA", (200, 300), (70, 120, 200, 255))),
                    ("3x4 px", Image.new("RGBA", (3, 4), (0, 0, 0, 255)))]:
    voxels = image_generator.image_to_voxels(image, resolution=24, mode="relief")
    check(voxels == [], f"{kind} image yields nothing to build", f"{len(voxels)} voxels")

section("proportion correction from real dimensions")
tower = _fixture("tower")
natural = image_generator.image_to_voxels(tower, resolution=24, mode="revolve")


def _height_over_width(voxels: list[tuple[int, int, int, str]]) -> float:
    ys = [v[1] for v in voxels]
    xs = [v[0] for v in voxels]
    return (max(ys) - min(ys) + 1) / (max(xs) - min(xs) + 1)


base = _height_over_width(natural)
taller = _height_over_width(
    image_generator.image_to_voxels(tower, resolution=24, mode="revolve", target_ratio=8.0))
squatter = _height_over_width(
    image_generator.image_to_voxels(tower, resolution=24, mode="revolve", target_ratio=0.5))
check(taller > base, "a tall target ratio stretches the model", f"{base:.2f} -> {taller:.2f}")
check(squatter < base, "a squat target ratio squashes it", f"{base:.2f} -> {squatter:.2f}")
check(_height_over_width(image_generator.image_to_voxels(
    tower, resolution=24, mode="revolve", target_ratio=100.0)) <= base * 4.01,
    "an absurd target ratio is clamped, not obeyed")

section("blueprint facts")
for facts, ratio in [
    (BlueprintFacts(height_m=330.0, width_m=125.0), 330.0 / 125.0),
    (BlueprintFacts(height_m=56.0, diameter_m=15.5), 56.0 / 15.5),
    (BlueprintFacts(width_m=10.0), None),
    (BlueprintFacts(height_m=100.0, width_m=0.0), None),   # no division by zero
    (BlueprintFacts(), None),
]:
    check(facts.ratio == ratio, f"ratio of {facts.summary() or 'nothing'}", f"got {facts.ratio}")

# Offline, Wikidata is unreachable, so anything we do have must be
# attributed to the curated table rather than claimed as Wikidata's.
offline = fetch_blueprint_facts("Eiffel Tower")
check(offline.summary() != "" and offline.source is not None
      and "Wikidata" not in offline.source,
      "curated facts are not labelled as Wikidata", f"source={offline.source!r}")
check(fetch_blueprint_facts("Some Unknown Thing").source is None,
      "no facts means no source claim")

# merge_facts is what any additional source (an ingested photo/facts
# cache, say) slots into, so the attribution has to survive three-way
# merges and name only the sources that actually contributed.
three_way = merge_facts([
    ("Wikidata", BlueprintFacts(height_m=330.0)),
    ("ingested cache", BlueprintFacts(height_m=1.0, floors=7)),
    (CURATED_SOURCE, BlueprintFacts(width_m=125.0, floors=99)),
])
check(three_way.height_m == 330.0 and three_way.floors == 7 and three_way.width_m == 125.0,
      "each source only fills gaps the ones above it left", three_way.summary())
check(three_way.source == f"Wikidata, ingested cache and {CURATED_SOURCE}",
      "every contributing source is named", f"got {three_way.source!r}")
shadowed = merge_facts([
    ("Wikidata", BlueprintFacts(height_m=330.0, width_m=125.0)),
    (CURATED_SOURCE, BlueprintFacts(height_m=1.0)),
])
check(shadowed.source == "Wikidata",
      "a source that contributed nothing is not named", f"got {shadowed.source!r}")
check(merge_facts([("Wikidata", BlueprintFacts()), ("absent", None)]).source is None,
      "merging nothing claims no source")

section("local reference library")
check(local_library.get_local_reference("eiffel tower") is None,
      "an empty manifest is a clean miss, not an error")

# --------------------------------------------------------------------------
print(f"\n{'=' * 60}")
if _failures:
    print(f"{len(_failures)} FAILURES:")
    for failure in _failures:
        print(f"  - {failure}")
    sys.exit(1)
print("All checks passed.")
