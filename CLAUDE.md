# Notes for Claude (persistent across sessions)

## Armor-piece audit against the wiki (done)

The deferred full armor-piece-vs-wiki audit described here in earlier
sessions has been completed: every real armor tier in `ARMOR_STAND_TIERS`
(`none`, `leather`, `copper`, `golden`, `chainmail`, `iron`, `diamond`,
`netherite`) was checked via `WebSearch` against real vanilla facts (since
direct `WebFetch` to `minecraft.wiki`/`minecraft.fandom.com` is blocked by
this environment's own network egress policy) — confirming the real
weakest-to-strongest ordering (copper genuinely sits between leather and
golden, added in The Copper Age, Sept 30 2025) and each material's real,
non-dyeable color.

One real mismatch was found and fixed: `ARMOR_TIER_COLORS.copper` was
`0xb87333`, the generic web "copper" color — actually a muted
brownish-orange, not real vanilla copper armor's own "striking orange"
look. Fixed to `0xd97b4a`, reusing this same app's own
`COPPER_GOLEM_OXIDATION_COLORS[0]` (the identical real material,
unoxidized — copper ARMOR itself never oxidizes, unlike copper
blocks/golems). Every other tier's color and the shared per-tier armor
geometry in `armorStandParts()` / the `armor_stand` render branch were
checked and are accurate; real vanilla armor uses identical geometry
across materials (only color differs), which this app already matched.

## Voxelizing a real 3D-scanned model (any preset, new or old)

Two lessons learned the hard way on the Darth Vader Helmet preset
(`vaderHelmetScanSolid`), general to any future or existing real-model
preset here (currently also the Statue of Liberty's `libertyScanSolid`,
though that one's source was already exact voxel art on a grid and isn't
affected the same way):

1. **Prefer a thin shell + flood-fill-sealed-cavity voxelization over a
   solid column/ray fill.** A shell (rasterize the mesh's own surface,
   then flood-fill AIR in from outside to seal any fully-enclosed
   cavity while leaving real openings like a neck hole genuinely open)
   preserves real concave detail — cheek/jaw guards, recesses, anything
   narrower than the shape's own overall bounding column. A solid fill
   (mark every cell between the topmost and bottommost surface hit in
   each column solid, guaranteeing no pinholes by construction) silently
   ERASES any concavity bounded above and below by shallower surface in
   the same column — confirmed directly by comparing rendered side
   profiles of both approaches on the same source mesh: the solid-fill
   version smoothed away real cheek/jaw guards the shell version kept.
   A solid fill is tempting because it can't have a pinhole, but that
   robustness comes from deleting exactly the kind of detail a "real
   scanned model, not hand-tuned geometry" preset exists to preserve.

2. **Always default this kind of preset's scale close to its own scan
   data's native resolution**, not an arbitrary small ratio. A coarse
   OUTPUT block count (nearest-neighbor-downsampled far below the scan's
   own resolution) is what actually makes real detail unreadable and
   makes rare sampling-density gaps look big and ugly — not the
   underlying data or technique. Rendering the exact same embedded data
   at native resolution (compute a scale so `real.height * scale` ≈ the
   scan's own `H` dimension, etc.) made both problems disappear at once:
   real geometry read clearly, and residual pinholes (a few dozen cells
   out of ~150,000+) became visually negligible. Check the output
   dims/volume stay well under `MAX_VOXEL_VOLUME` (6,000,000) and that
   generation time is still reasonable (a few seconds) before defaulting
   to it.

## Live in-browser .glb import ("Import 3D model" mode)

Added an "Import 3D model (.glb)" mode (third radio option alongside
"Famous structure"/"Custom shape") that runs the exact same shell +
flood-fill technique above LIVE in the browser instead of as an offline
one-off script: `parseGLBContainer`/`extractGLBTriangles` hand-parse the
glTF binary container (no library — the same manual approach already used
offline for every scan preset, just ported to JS), and
`IMPORT_VOXELIZE_WORKER_SRC` runs the rasterize + flood-fill in a Web
Worker (built from an inline string via a Blob URL, keeping this a single
HTML file) so a large model doesn't freeze the tab. The resulting grid is
sampled by `importedScanSolid` exactly like every embedded preset's own
scan shape.

Explicitly scoped to **.glb only, never USDZ** (per direct user
instruction): USDZ is a zip around Pixar's USD format with no simple
binary spec to hand-parse the way glTF has — every USDZ handled in this
app's history was read by pulling raw strings out of the binary, never a
real parse. A genuine USD parser (or a large WASM build of Pixar's own USD
library) would be a much bigger undertaking than this feature; don't
attempt to extend this import mode to USDZ without that being a
deliberate, separately-scoped decision.

Unlike every hand-built preset, there's no human calibration step here:
real-world scale and orientation are taken directly from the file's own
raw units/axes (glTF spec mandates meters + Y-up), which can be wrong in
practice — this app's own manual pipeline has hit exactly that twice
(the Golden Gate Bridge's un-calibrated raw units needed a real-dimension
calibration factor; Kip's own vertical axis needed checking against its
raw axes directly rather than assumed). This import mode's fix-up path
for that is the existing live Rotate tool + editable detected
height/width/depth fields, not a guessed automatic correction — don't try
to add automatic up-axis detection or scale calibration heuristics here;
they'd be guessing at exactly the kind of thing this app's own hand-built
presets needed real research or direct silhouette verification to get
right.

## Walk-mode spawn point defaults to a modeled entrance when one exists

`generateModel()` computes `currentModel.spawnPoint` from whatever real
entrance an interior mode actually carved — the pyramid interior's own
returned passage-threshold coords (`buildPyramidInterior` now returns
`{x,y,z,axis}` instead of nothing), or the first `door` decor entry for
"floors"-mode buildings — via the shared `computeEntranceSpawn(dims,
entry)` helper (near `dirFromYawPitch`/`yawPitchFromDir`). `setCameraMode`
uses it for Walk/first-person instead of the old universal "drop the
player from directly overhead at the horizontal center" default, which
lands ON TOP of anything with a real roof or sloped exterior (a pyramid's
own apex, a house's own roof ridge) rather than inside it — confirmed
directly: the Great Pyramid's real Giza-style entrance sits partway up a
smooth sloped face with no exterior ramp/stairs modeled to it at all, so
a walking player could never reach it from the ground regardless of spawn
point; spawning them already standing at the passage threshold (which
`buildPyramidInterior` always carves to air) sidesteps that entirely.
Any future interior mode that carves its own real entrance should return/
push equivalent `{x,y,z,axis}` info so this keeps working automatically —
shapes with no interior entrance at all keep falling back to the old
drop-from-above default unchanged.

## "AI Generate" mode (experimental, direct-from-browser Anthropic API calls)

A 4th "What to build" mode alongside preset/custom/import: describe a
shape in plain language (even vague) and Claude writes a real
`solid(x, y, z, dims)` function — the exact same contract every
hand-written shape in `SHAPES` already uses — which gets compiled with
`new Function(...)` and run through the existing generation pipeline
completely unchanged (same scale system, same fill/hollow modes, same
material pickers). `SHAPES.aiGenerated` is a stable indirection to
whatever `aiGeneratedFn` currently holds, so each Generate/refine call
swaps the active shape without needing its own SHAPES entry per design.

Calls `POST https://api.anthropic.com/v1/messages` directly from browser
`fetch` with a key the user pastes in and this file never sees beyond
passing it straight through as the `x-api-key` header — there is no
backend here to keep it server-side, by this project's own single-HTML-
file, no-build design. The key is persisted only to `localStorage`
(`mc3d_ai_api_key`), with an explicit in-UI warning about what that
means. Verified via WebFetch against the live Anthropic docs (not
guessed) before building this: the TypeScript SDK's own `browser usage`
docs confirm direct browser calls are an officially supported pattern
(gated client-side by `dangerouslyAllowBrowser` in the SDK — irrelevant
here since this is raw `fetch`, not the SDK) and the Structured Outputs
docs confirm `output_config.format` with a `json_schema` works with plain
`fetch`, no SDK required — used here to force back `{summary, code,
realHeightMeters, realBaseXMeters, realBaseZMeters, exteriorBlock,
interiorBlock, accentBlock}` in one shot instead of a tool-use round trip.

"Keep the original design unless cleared/told to remake" (an explicit
user requirement) is implemented two ways at once: the full running
`aiConversation` message history is replayed on every call (so Claude
sees its own prior JSON reply as context), AND the system prompt
separately re-embeds the current code's literal source under a "CURRENT
CODE" heading with an explicit instruction to revise it incrementally
unless the user's new message clearly asks to start over/scratch it/
remake it — belt-and-suspenders so this still works even if conversation
replay is ever changed. A response is validated (compiles, doesn't throw,
isn't a completely empty shape over a random sample) BEFORE it's allowed
to replace `aiCurrentFn`/`aiCurrentCode`, so one bad follow-up can never
destroy prior good progress — matching the same requirement.

Model defaults to `claude-opus-5` (editable in the UI) per this session's
`claude-api` skill's own explicit non-negotiable default. No sandboxing
beyond what every other shape function here already gets (none) — running
AI-authored JS in the user's own browser tab, from their own request,
with their own key, is the same risk level as them hand-writing a Custom
shape themselves, not a new untrusted-content boundary; don't add Web
Worker isolation or similar for this without a concrete reason, since
that'd be scope creep beyond what was asked.

### Local/self-hosted provider option

Added a second provider (radio choice alongside "Anthropic (cloud)"):
"Local / self-hosted", targeting the OpenAI-compatible `/chat/completions`
surface that Ollama, LM Studio, llama.cpp's own server, vLLM,
text-generation-webui, and koboldcpp all implement as their standard
interop layer — one `callLocalForShape()` code path covers all of them,
same as `callAnthropicForShape()` covers Anthropic. Base URL defaults to
Ollama's own local address (`http://localhost:11434/v1`, the single most
common local runner) but is a plain editable text field for any other
port/server. No API key is required by default (most local servers don't
check one) but an optional key field exists and is sent as
`Authorization: Bearer <key>` when non-empty, for anyone proxying a local
endpoint that does check one.

Structured JSON-schema output (`response_format: {type:'json_schema',...}`)
isn't universally supported the way Anthropic's own `output_config.format`
is, so `callLocalForShape` both requests it (harmless if the server
ignores the field) AND falls back to retrying once without it on an HTTP
error, relying purely on an explicit "respond with ONLY this JSON shape"
instruction appended to the system prompt either way. Parsing is
tolerant on this path (extracts the first `{...}` block via regex rather
than assuming the whole response is pure JSON) since local models,
especially smaller ones, don't always follow "JSON only" as reliably as
Claude does — this is a real, expected difference in output quality/
reliability across local models, not a bug to paper over further; a
model that can't follow the contract at all will still surface a clear
compile/empty-shape error rather than silently doing nothing, via the
same validate-before-replacing logic used for both providers.

The provider-switch UI is careful never to clobber a value the user
actually typed: the shared `#ai-model` field only auto-swaps between the
two providers' own defaults (`claude-opus-5` / `llama3.1`) when it's
still sitting at the OTHER provider's untouched default, checked before
every switch.

### Optional web search for real-world reference facts (Anthropic only)

User confusion prompted this: after getting AI Generate working against
local Ollama, the user asked for a way to make it "know it's being used
to generate glb 3d models" and to let it "pull models from online if
needed" — i.e. actually download an existing 3D file it finds, and/or
output a real mesh/`.glb`. Both were explicitly declined, for reasons
worth restating here since this exact ask (autonomous web
search-and-download, sometimes phrased as "just get it from Google/a
website") has come up and been declined multiple times across this
project's history, for a mix of real technical and policy reasons that
still both apply:

- **Real mesh/`.glb` generation is not something a chat LLM does at all**
  (local or Anthropic) — that needs a genuinely different model
  architecture (text-to-3D, e.g. Meshy/Tripo/Shap-E), not a prompting
  change to this feature. Out of scope here, same as USDZ import was
  ruled out above for a different but analogous "this needs a
  fundamentally different technology" reason.
- **Actually downloading a found file cross-origin from a browser page
  almost never works even given real internet access** (unlike this
  coding session's own sandboxed network, which was a separate, earlier
  problem) — most 3D-model sites don't set permissive CORS headers for
  arbitrary third-party pages to fetch their files directly, so this
  would silently fail on the user's own machine too, not just here.
- **Automating unreviewed acquisition of third-party 3D content
  reintroduces the exact copyright-review problem this project has
  consistently held the line on** (see the many declined Hulkbuster
  resubmission attempts elsewhere in this file's history) — a "search
  and use whatever it finds" pipeline has no human review step at all,
  which is a regression from every real-model preset here, all of which
  went through explicit license/authorship verification before being
  embedded.

What WAS legitimately buildable and was built: an opt-in checkbox
(`#ai-web-search`, Anthropic provider only — local/Ollama models don't
get comparable first-class tool support here) that declares Anthropic's
real server-side `web_search_20260209` tool on the request. This lets
Claude look up real-world reference FACTS (approximate dimensions,
shape, color) for whatever's described, the same spirit as the Bald
Eagle preset's own real WebSearch-sourced dimensions — text grounding for
geometry it still writes itself by hand, never a file. Off by default
(costs extra, adds real latency, unnecessary for an abstract/invented
design).

Implementation note: `output_config.format` (structured JSON output) and
a forced/declared tool in the same request is a combination this
session's own `claude-api` skill reference didn't document either way,
so rather than guess, web-search mode simply DROPS `output_config.format`
and relies on the same explicit "respond with ONLY this JSON" system-
prompt instruction (`AI_JSON_ONLY_INSTRUCTION`, shared with the local/
Ollama path) plus the same tolerant `{...}` extraction already proven
there — known-working over an unverified combination. `callAnthropicForShape`
also now looks at the LAST text block in the response (not the first),
since a web-search turn's response includes an earlier `web_search_tool_result`
content block before the model's own final text answer.

Also strengthened `buildAiSystemPrompt()`'s own opening line to explicitly
state up front that the model produces code only, never an image, mesh,
`.glb`, or any downloadable file — directly targeting the user-reported
symptom of a local model (qwen2.5-coder via Ollama) not seeming to understand
what it was being asked to do; this framing fix applies to every
provider, not just the web-search path.

### Per-part block/color control, and no fixed request timeout

Two more follow-ups from the same conversation:

**Per-part materials.** `exteriorBlock`/`interiorBlock`/`accentBlock` are
each ONE material for the whole model — no way to honor "red wool roof,
oak plank walls, gold trim" from those three alone. Added an OPTIONAL 4th
function the AI can write, `materialCode` (schema field, required-but-
often-empty-string so strict/local JSON-schema modes don't choke on a
genuinely optional key): a `material(x, y, z, dims)` function body, same
coordinate space as `solid()`, called only on cells `solid()` already
marked true, returning a block id string for that exact cell or `""` to
leave the app's normal exterior/interior/accent choice there.
`applyAiMaterialPaint(grid, dims)` runs this over the whole grid AFTER
the base fill/hollow pass — the exact same "paint after the fact" pattern
`applyBaldEagleDetail`/`applyBigBenDetail` already use for their own
hand-written per-cell overrides, just driven by AI-authored code instead.
Gated on `shapeType === 'aiGenerated' && aiGeneratedMaterialFn` in
`generateModel()`, right alongside those two existing hooks. A broken or
throwing materialCode is swallowed silently (never blocks the shape
itself from being accepted, only the per-part painting is skipped) —
distinct from `solid()` itself, which must not throw or the whole
response is rejected before touching any working state, since losing the
CORE shape to a bad follow-up is a much bigger regression than just
missing some paint detail. The system prompt explicitly tells the model
to leave this empty when per-part control wasn't actually requested,
so a plain "build a tower" doesn't get color variation nobody asked for.
`aiCurrentMaterialCode` is tracked alongside `aiCurrentCode` and
re-embedded in the CURRENT-CODE context block for follow-up edits, and
both reset together on Clear.

**No fixed request timeout, by explicit request.** The AbortController-
based 90s/150s timeouts are gone entirely — a slow local model (or a
long multi-search Anthropic turn, now compounded by writing a SECOND
function) can legitimately take minutes, and browser `fetch()` has no
built-in timeout of its own to fight. In its place: a `Cancel` button
(`#ai-cancel-btn`, disabled unless a request is actually in flight) that
calls `.abort()` on the same `AbortController` the fetch already uses —
gives the user a real way out of a request that hangs forever (e.g. a
truly dead connection) without silently capping every legitimate slow
generation at some arbitrary number. The status line says as much while
waiting, so a long wait doesn't read as the app being stuck.

### Auto-scale, and leaning on the model's own real-world knowledge

The user pointed out AI Generate still required manual input in one
place that mattered: after a generate, the real height/width/depth
fields got auto-filled from the AI's own answer, but the actual SCALE
RATIO (`#scale-num`/`#scale-den`) was never touched — it silently kept
whatever ratio was left over from a previous preset/custom shape/import.
That's exactly the same bug class as the earlier Vader-Helmet-disappears
fix and the building-presets-too-small-to-walk-into fix, just never
closed for this newest mode. Fixed the same way those were: after a
successful generate, auto-pick `scale-num`/`scale-den` so the longest
real dimension maps to a target block count that scales with how big
that dimension actually is (40 blocks under 5m, 60 under 30m, 100
otherwise — a tiny prop needs a HIGHER relative scale to read as more
than a few blocks; a huge landmark needs a LOWER one to stay a sane
volume), backing the target down in a loop if that would exceed 2M cells
(mirrors `handleImportedFile`'s own native-resolution backoff loop
exactly). Verified directly: a mocked 0.3m "trinket" and a mocked 200m
"tower" both come out at a real, visible block size instead of one
disappearing to near-zero and the other ballooning unreasonably. Material
fields also now fall back to sane defaults (`stone`/`stone`/`gold_block`)
instead of silently keeping a stale leftover selection when the model
returns an invalid block id — the AI should always be the one deciding
blocks/colors here, per the user's explicit "I should not need to input
anything" requirement, never a leftover value from whatever mode was
active before.

Also strengthened the system prompt for short/vague-but-real prompts
("Greek Parthenon"): explicitly told the model to draw on its OWN
general training knowledge of a real thing's proportions/shape/color
when the description names one, even with web search off/unavailable
(the only path local/Ollama models get at all) — a short prompt naming
something real should still produce a recognizable result of that real
thing, not a generic placeholder shape, and this doesn't depend on the
Anthropic-only web-search toggle to work at all.

### "Greek Parthenon just generates a big square" — a code-gen gap, not an image gap

Follow-up complaint from the same conversation. The user's own proposed
fix was "let it look at reference images online for inspiration" —
explicitly declined as the fix here (though not for the same reasons as
the earlier "download a 3D file" asks; see below), because it doesn't
actually address the mechanism of the failure: `solid(x,y,z,dims)` still
has to become exact per-cell math regardless of whether the input was a
text description or a photo, and translating a PICTURE into that math is
arguably a HARDER task for current models than translating a good text
description — a photo doesn't make the code-writing step easier. A
"big square" result is the classic symptom of a model taking the easy
way out: one bounding-box test instead of several combined shape tests
for the thing's actual distinct parts (a temple's platform + colonnade +
pediment; an animal's body + head + legs + tail).

Fixed by giving the model an explicit worked example to pattern-match
against, adapted directly from this app's own real hand-built presets
(the ring-of-columns technique already used for the Pisa Tower's own
loggia and the Taj Mahal's own corner minarets — see `pisaSolid`/
`tajMahalSolid` above): a literal ~20-line `solid()` example in the
system prompt showing 3 parts (a base platform, a ring of individual
columns via a fixed-count loop over an angle, a tapering roof) layered
by height with plain if/return, explicitly labeled as a PATTERN to adapt
rather than numbers to copy. Paired with a direct "DO NOT DEFAULT TO A
PLAIN BOX" instruction naming the failure mode itself and asking the
model to mentally list 2-4 defining parts before writing code. Few-shot
worked examples are one of the most effective levers for lifting a
weaker/local model's structured-output quality — cheaper to try than
building new infrastructure, and more likely to actually address the
reported symptom's real mechanism.

Note for later: unlike the earlier "download a 3D file" asks, fetching a
real 2D reference PHOTO from a CORS-friendly, appropriately-licensed
source (Wikimedia Commons has a genuine public API designed for this,
unlike arbitrary 3D-model sites) and passing it to a vision-capable
model (Anthropic's own vision input, or a multimodal local model) is
technically a different and more feasible proposition than that earlier
ask — it just wasn't judged likely to fix THIS specific reported
symptom, so it wasn't built speculatively. If image grounding is asked
for again after the prompt fix above still isn't good enough, that's the
shape a real version of it should take.

### Real reference-photo lookup, and a "completely empty shape" validation bug

The user asked again for image-based reference (three times total across
this feature's life) and reported a NEW, worse failure: "The AI's code
produced a completely empty shape" outright, on a local qwen2.5-coder
Ollama setup. Two separate things were done.

**1. Built the real reference-photo lookup** the note above scoped as
the legitimate next step, rather than declining a fourth time: a new
`fetchWikimediaReferenceImage(query, signal)` function, gated behind the
same `#ai-web-search` checkbox (Anthropic only). CORS feasibility was
verified live via `WebSearch` (not assumed) before building:
`commons.wikimedia.org/w/api.php` allows unauthenticated cross-origin
requests via its own documented `origin=*` parameter, and
`upload.wikimedia.org` itself sends `Access-Control-Allow-Origin: *` on
a bare GET with no added headers (a custom header, even an innocuous
one, would trigger a preflight that endpoint doesn't allow — confirmed
this matters, so the image fetch stays a plain `fetch(url)` with nothing
added). The function searches Commons for one matching image, fetches
its thumbnail, reads the ACTUAL media type off the response's own
`content-type` header rather than the search metadata's `mime` field
(the thumbnail is always re-rendered to a plain raster format even when
the original file is an SVG/TIFF vision input can't accept), rejects
anything not `image/jpeg|png|gif|webp` or over 5MB, and base64-encodes
it via `arrayBuffer()` + `Uint8Array` + chunked `btoa()` (no `FileReader`
dependency, so this also runs cleanly in the jsdom test harness). On any
failure at any step it returns `null` and generation proceeds exactly as
before with plain text — this is a best-effort enhancement layered on
the existing text-only path, never a new way to fail. When a photo IS
found, `callAiGenerate()` builds the outgoing user message as an
Anthropic content array (`[{type:'image',...}, {type:'text',...}]`)
instead of a plain string, and `buildAiSystemPrompt()` gained a
paragraph telling the model to actually examine an attached photo's real
parts/proportions/colors when present. Still Anthropic-only, and still
genuinely useless for the user's own current model (qwen2.5-coder is a
text-only coding model with no vision input at all, whatever provider
it's served through) — the UI hint next to the checkbox now says so
directly, rather than let it look like a no-op with no explanation.

**2. Found and fixed the actual cause of the new "completely empty
shape" failures.** The sanity-check that runs the AI's `solid()` before
accepting it was sampling 400 random cells in a FIXED `{sx:20,sy:20,
sz:20}` test cube, regardless of the real dimensions the shape would
actually be generated at. This directly collided with the previous
session's own worked-example fix: encouraging thin, dims-proportional
detail (a column radius computed as `dims.sx * 0.035`, for instance)
means a shape that's genuinely substantial at its real target size
(60-100+ blocks, computed from the AI's own `realHeightMeters`/etc.) can
round away to near-nothing at a fixed 20-block test cube, making 400
random samples land on solid cells rarely or never — a false rejection
of otherwise-correct code, not a real bug in it. This is the exact same
lesson already written up above under "Voxelizing a real 3D-scanned
model": validate/render at the real target resolution, not an arbitrary
coarser stand-in. Fixed by moving the real-size + auto-scale computation
(previously done AFTER validation, purely to fill in the height/width/
depth fields and scale ratio) to BEFORE the compile-and-validate step,
and using those actual computed dims as the test cube instead of the
fixed 20-cube. Verified directly with a shape solid only in the outer
few cells along x (empty at a 20-cube, substantial at the real ~80-block
target the mocked `realHeightMeters`/etc. drive) now generating
successfully, while a shape that is GENUINELY always-false is still
correctly rejected at whatever its own real target size is.

**Also**, per the user's explicit "I should not need to input anything
beyond a description" requirement: the Scale and Blocks fieldsets (scale
ratio, exterior/interior/accent block pickers) are now hidden entirely
in AI mode — the AI already decides all of this from its own answer
(`callAiGenerate` auto-fills them under the hood exactly as before),
showing manual controls for values the AI is supposed to own just
invited confusion about whether input was still expected there. A hint
line in their place says as much and that Generate will fill them in.
The full block palette was already being sent to the model in every
system prompt (`MATERIALS.map(m => m.id)`, ~320 real block ids) — that
part of the ask was already true before this round, not a new change.

Also worth restating for later reference: the app already asks every
provider for a single structured JSON object back (`{summary, code,
materialCode, realHeightMeters, ...}` — see `AI_SHAPE_JSON_SCHEMA`) and
always has; there's no separate "make a json file for this app" step
missing here, no exported/saved `.json` file at all, and no way for a
plain-text or coding-only model to opt into a capability (like vision)
its own weights don't have — those are model-capability limits, not gaps
in what this app asks for or how it's wired.
