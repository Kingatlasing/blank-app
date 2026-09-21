# Local reference library

A small, curated set of reference photos bundled directly with the app,
checked *before* any live Wikipedia/Openverse lookup. The point is
reliability: a bundled image never depends on network access, never rate
limits, and has already been vetted once by a human instead of trusted
blind at generation time.

This is deliberately **not** an attempt at "all of Wikipedia" — that's
neither storable (millions of images) nor legal to mirror wholesale (most
of Wikipedia's images are hosted there under fair-use or share-alike terms
that don't permit bulk-copying into an unrelated project). Every entry
here must be individually confirmed openly-licensed (CC0 or CC-BY with
the required attribution recorded) before it's added.

## Schema (`manifest.json`)

```json
{
  "dog": {
    "image": "images/dog.jpg",
    "source_label": "Openverse photo by <creator> (CC-BY 4.0)",
    "source_url": "https://openverse.org/image/...",
    "build_method": "relief",
    "height_m": null,
    "width_m": null,
    "diameter_m": null,
    "floors": null
  }
}
```

- `image`: path relative to this directory.
- `source_label` / `source_url`: shown to the user and required for
  attribution — never add an entry without them.
- `build_method`: `"relief"` or `"revolve"` (see `research.py` for what
  each means) — set by whoever curates the entry, since it's a one-time
  judgment call per subject rather than something worth re-deriving from
  article text every time.
- The dimension fields are optional; leave any you don't have as `null`.

## Adding an entry

1. Find an image you can confirm is CC0 or CC-BY (Openverse's search UI
   shows license per-image; Wikimedia Commons category pages show it per
   file). Save it into `images/`.
2. Add a manifest entry with real `source_label`/`source_url` values.
3. `app.voxelcraft.local_library.get_local_reference(subject)` will pick
   it up automatically — no other code changes needed.

This repo's own development sandbox has no outbound network access, so
entries have to be added from an environment that does.
