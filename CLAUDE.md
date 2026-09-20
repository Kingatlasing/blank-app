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

## Real mesh generation via LocalAI's own image-to-3D backend

The user asked directly whether "LocalAI" specifically can generate a
real textured mesh in `.glb` format, with image-to-3D. Every earlier
"can it just download/generate a real 3D file" ask in this project's
history was declined because no chat LLM (local or Anthropic) can do
that — it needs a genuinely different model architecture. This question
named a specific piece of software, so rather than reflexively give the
same answer again, it was checked directly via `WebSearch` (this
sandbox's own network egress blocks `WebFetch` to `localai.io` itself,
so this is search-engine-corroborated across multiple independent
results, not a live docs read — flagged honestly below in the code
comments too): **LocalAI genuinely has this.** Separately from its
OpenAI-compatible chat/completions surface (the one `callLocalForShape`
already talks to), LocalAI exposes its own `/3d/generations` endpoint,
powered by `trellis2cpp` — a C++/GGML port of Microsoft's TRELLIS.2 —
that reconstructs an actual textured `.glb` mesh from a single
conditioning photo. This is a real, non-chat model doing real mesh
reconstruction, not a prompting trick, and it changes the answer: this
was buildable, and building it fits the letter of the standing "no fake
3D file generation" line rather than violating it, since the file really
is generated by a real 3D-generation model this time.

**Important limitation carried over honestly**: this backend is
image-conditioned ONLY — there is no text-to-3D path on this endpoint at
all, per LocalAI's own docs. So this can't replace AI Generate mode's
text-to-code approach; it needs an actual photo.

**Where it lives**: added to Import mode (`#import-controls`), not AI
Generate mode — architecturally, "take some external 3D asset and
voxelize it" is exactly what Import mode already does for a manually
uploaded `.glb`, and a LocalAI-generated mesh is just another way to
produce that same kind of asset. Concretely: `handleImportedFile` was
split into a thin file-reading wrapper plus a new shared
`processGLBArrayBuffer(buf, displayName)` that holds ALL the actual
parse/voxelize logic (previously only reachable via a `File` object).
The new `callLocalAiGenerate3D()` gets an image either from a direct
upload (`#localai-image-file`) or, if left empty, by reusing the exact
same `fetchWikimediaReferenceImage()` built for AI Generate's photo
lookup — so describing something by name works here too, not just
uploading your own picture. It POSTs to `{baseUrl}/3d/generations` via
the new `callLocalAiGenerations()`, then feeds the resulting bytes
straight into `processGLBArrayBuffer` — the EXACT same voxelizer a
manual upload uses, not a second parallel implementation.

**Tolerant response parsing, on purpose**: since the exact wire format
couldn't be confirmed by reading the live docs page directly (only
inferred from search-result summaries, which weren't even fully
internally consistent about whether the response holds inline base64 or
a URL to fetch), `callLocalAiGenerations` handles three different
plausible shapes rather than betting on one: a raw binary response
(`content-type: model/gltf-binary` or `application/octet-stream`, used
directly), inline base64 under `b64_json`/`base64`/`data` (top-level or
inside a `data[0]` entry, matching the OpenAI-images-API convention this
endpoint's own request shape otherwise mirrors), or a `url` field to
fetch the file from (relative to the same server). An HTTP error surfaces
a message explicitly suggesting the likely real cause — the 3D backend
not being installed/downloaded on that LocalAI instance, since the docs
describe it degrading gracefully rather than always being present. A
missing image AND missing description is a plain validation error, not a
silent no-op or a crash.

Same fixed-abort bug class caught here as a byproduct: cancelling during
the Wikimedia lookup phase used to surface a confusing "no usable
reference photo found" instead of "Cancelled", because
`fetchWikimediaReferenceImage` deliberately swallows every failure
(including an abort) into a plain `null` for its OTHER caller's
best-effort semantics. Fixed by checking `controller.signal.aborted`
explicitly before treating a `null` result as "no photo found."

Verified via a dedicated 16-check jsdom test covering: the request body
sent (model/image fields, correct endpoint path), all three response
shapes actually producing a voxelized result, an uploaded photo vs. a
Wikimedia-looked-up one, a missing-backend HTTP error surfacing a clear
message with no stale state left behind, the missing-input validation
error, and Cancel aborting cleanly (including during the photo-lookup
phase specifically, to catch the bug above). All prior AI-feature test
suites (58 checks) and the full `dom-test.js` regression suite (34
checks) still pass unchanged.

## AI Generate: fill/hollow is now the AI's own call too, and photo lookup works for local models

Two follow-ups from the same conversation as the LocalAI mesh feature
above.

**Fill/hollow.** The user's running "I should not need to input anything
beyond a description" requirement (already applied to scale and blocks)
had one gap left: the "Body" control (filled vs. hollow, and wall
thickness when hollow) in the "Structure & interior" fieldset was still
a manual, always-visible choice in AI mode. Closed the same way scale/
blocks were: `AI_SHAPE_JSON_SCHEMA` gained `fillMode` ("filled"/"hollow")
and `wallThickness` fields (both in `required`, matching the existing
pattern for "required but has a sane default" fields), the system prompt
gained a paragraph telling the model to weigh this exactly like a human
builder would — hollow past roughly 40-50m on the longest side (a large
build's own invisible interior stops being worth the block count),
filled below that (a thin shell can look structurally wrong on something
small) — and `callAiGenerate()` now sets `#fill-mode`/`#wall-thickness`
from the AI's answer (falling back to filled/1 on an invalid value,
never a stale leftover). The `#fill-mode`/`#wall-thickness` controls
(wrapped in a new `#fill-mode-controls` div) are hidden in AI mode next
to Scale and Blocks, with the existing `#ai-blocks-scale-hint` reworded
to cover all three. `#interior-toggle` itself needed no change — it's
already always disabled with an explanatory hint for AI-generated shapes
via `currentInteriorMode()` returning `null` for `isAiMode()`, since
there's no real modeled-interior concept for an arbitrary AI-authored
`solid()`, same as Import mode.

**Photo lookup now works for the local/self-hosted provider too**,
prompted directly by the user pointing out their own local setup
"already can search and browse the internet" and asking why the app's
own reference-photo feature was Anthropic-only. Worth being precise
about what's actually true here versus what changed: a plain Ollama (or
any other raw OpenAI-compatible) server has NO built-in web browsing of
its own — if a separate chat UI on top of one (Open WebUI, for instance)
has ever appeared to browse, that's a capability that UI's own
orchestration layer adds by calling a search API and feeding results
back into the chat turn, not something inherent to the model or to
hitting its plain `/chat/completions` endpoint the way this app does.
BUT the actual reference-photo lookup this app already built
(`fetchWikimediaReferenceImage`) was never gated on any provider-specific
tool-calling capability in the first place — it's this app's OWN
client-side code doing the fetch, then simply attaching the result as
image content on the outgoing request. That part never needed Anthropic
specifically; it was scoped there for the FIRST version only because the
real Anthropic `web_search` TOOL (a genuinely Anthropic-specific
server-side feature, for TEXT facts) rode along in the same checkbox.
Split the two capabilities apart: a new `#ai-local-photo` checkbox (in
`#ai-local-fields`) triggers the exact same `fetchWikimediaReferenceImage`
call as the Anthropic checkbox, with its own honest hint explaining
exactly the "this app does the searching, not the model" point above,
and that it only helps a model that's actually vision-capable (llava,
qwen2-vl, gemma3's multimodal variants, minicpm-v — not a text/code-only
model like the user's own qwen2.5-coder, which has no image input at
all regardless of provider). `buildAiSystemPrompt()` took a new `hasPhoto`
parameter, independent from `canWebSearch` (previously the same flag
controlled both the web-search-tool paragraph and the photo paragraph,
which was never actually correct even for Anthropic, since photo and
tool-use are logically separable), and `callLocalForShape`/
`callAnthropicForShape` both now take `hasPhoto` explicitly.
`callAiGenerate()` builds the outgoing image content in whichever wire
shape the target provider actually needs — Anthropic's
`{type:'image', source:{type:'base64',...}}` vs. the OpenAI-compatible
`{type:'image_url', image_url:{url:'data:...;base64,...'}}}` — since the
two are genuinely different formats, not a shared one. There is still no
local equivalent of Anthropic's real web-search TOOL for text facts (no
generic local server exposes an equivalent this app could declare the
same way), so that half of the original checkbox stays Anthropic-only;
only the photo half was ever provider-agnostic to begin with.

Also worth restating for the record, since it came up directly: the
scale/ratio the AI picks was ALREADY driven by the model's own suggested
real-world bounding box (`realHeightMeters`/`realBaseXMeters`/
`realBaseZMeters`, see "Auto-scale" above) — this round's system-prompt
update made that mechanism explicit to the model itself (previous
prompts never told the model this connection existed, they just asked
for the three numbers) so it understands WHY those numbers matter
before deciding fillMode based on the resulting scale.

Verified via a new 14-check jsdom test: `#fill-mode-controls` visibility
toggling with AI mode, `fillMode`/`wallThickness` from a mocked AI
response landing correctly on `#fill-mode`/`#wall-thickness` (including
an invalid-value fallback case), the local provider's outgoing request
using `image_url` (not the Anthropic `image` shape) when
`#ai-local-photo` is checked, the local system prompt actually including
the photo paragraph in that case, and confirming Wikimedia is never
queried at all for the local provider when the checkbox is off. All
prior AI-feature suites (74 checks total) and the full `dom-test.js`
regression suite (34 checks) still pass unchanged.

## Research now happens by default, and the two-step flow is stated explicitly

The user pushed back one more time on the same underlying point across
several messages now: they wanted the app to actually tell whatever
model it's talking to (their own words: "Ollama or whatever AI I'm
using") that it needs to research the prompt FIRST and only then
produce output in a form this modeler can actually use — not something
they have to remember to opt into by finding and checking a box.

Two real changes, not just wording:

1. **`#ai-web-search` (Anthropic: text facts + reference photo) now
   defaults to `checked`.** It was off by default in every earlier round
   specifically to avoid surprise cost/latency on every single request —
   that reasoning was sound, but conflicted directly with what the user
   kept asking for. Resolved in the user's favor: research now happens
   automatically for every Anthropic request unless they explicitly turn
   it off (worth doing for a purely invented/abstract design, or a fast
   text-only follow-up tweak that doesn't need fresh research) — the
   hint text next to it now explains that tradeoff instead of just
   stating a default.
2. **`#ai-local-photo` (local provider) stays OFF by default, on
   purpose, and this is NOT the same tradeoff as #1.** Attaching an
   image to every request has a real chance of actively breaking
   generation on a typical local setup: most local/coding models
   (including a default Ollama pull like `qwen2.5-coder` or `llama3.1`)
   are text-only, and some servers error on an unexpected image content
   block rather than silently ignoring it — unlike Anthropic, where
   every current Claude model is genuinely vision-capable, so turning it
   on can never hurt there. Research from the model's own general
   knowledge still always happens for local models regardless (see the
   STEP 1/STEP 2 framing below) — this checkbox only adds an actual
   photo on top, and should only be turned on once the user knows their
   loaded model can actually see.

**Also made the two-step sequence explicit in the system prompt itself**,
directly matching how the user described wanting this to work: a new
opening block states "STEP 1 — RESEARCH" (use general knowledge, always;
the real web_search tool, when available this turn; an attached
reference photo, when one exists this turn) followed by "STEP 2 — BUILD"
(the JSON response — a `solid()` function body — IS the finished
deliverable; there's no other output form for this app to receive).
Previously this same behavior was described in scattered prose across
several paragraphs (short-prompt guidance, the web-search paragraph, the
photo paragraph) without ever stating outright that these two things
happen as an ordered sequence every time — this makes that sequencing a
literal instruction instead of something only implied by the rest of
the prompt, which matters more for weaker/local models that follow
explicit structure more reliably than implication.

Verified via a new 11-check test confirming: both checkboxes' actual
default states straight off the page (not just checking JS logic), the
system prompt containing the STEP 1/STEP 2 language, and — the real
point of this round — that a plain Anthropic AI Generate call with
NOTHING touched beyond typing a prompt and clicking Generate already
searches Wikimedia, fetches the matching photo, declares the real
`web_search` tool, and attaches the photo to the outgoing request, all
with zero manual setup. All prior AI-feature suites (96 checks total)
and the full `dom-test.js` regression suite (34 checks) still pass
unchanged.

## A real Ollama-specific web search tool, and firmly declining "search for and download a 3D file" again

The user asked again — now framed as "my local AI can already search the
web, just tell it to go online first, download a 3D model if it finds
one, and generate one from scratch as good as Meshy if it doesn't."
Worth documenting precisely what was and wasn't done here, since this is
the most detailed version of an ask this project has declined
repeatedly, and it's worth being exact about which parts are real new
capability vs. which parts remain genuinely impossible the way this app
is built.

**Verified, not assumed, before answering**: "my local AI can already
search the web" is true because of `https://ollama.com/api/web_search`
— a real, separately-hosted Ollama Cloud service requiring its own free
account/API key, confirmed live via `WebSearch`. Critically, its own
docs confirm this is a **client-orchestrated tool**, the same pattern as
every other tool-calling setup: the model only emits a request to call
`web_search`; something else (a wrapper app, a custom script — whatever
gives the user's own setup its apparent browsing) has to actually make
that HTTP call and hand results back. Ollama's bare server has no way to
reach the internet on its own, and this app's own `callLocalForShape`
had no such round-trip loop at all before this — it sent one request and
read one response.

**What WAS built**: a real one, not a token gesture. `callOllamaWebSearch
(query, apiKey, signal)` calls that real endpoint (`{query, max_results:
5}` → `{results: [{title, url, content}]}`, verified live). A new
`#ai-local-websearch` checkbox (local-provider fields) plus a separate
`#ollama-search-key` field (a distinct credential from the base-URL/key
above it, since this always talks to ollama.com regardless of which
server is actually running the model, persisted to its own
localStorage key) drive a genuine OpenAI-style tool-calling loop now
built into `callLocalForShape`: declares a `web_search` function tool,
and if the model's response comes back with `tool_calls` instead of
content, this app itself executes `callOllamaWebSearch` and feeds the
result back as a `role:'tool'` message (matched by `tool_call_id`)
before asking again — up to 3 rounds (same ceiling as the Anthropic
tool), then one final tools-free call to force an answer if a model
just won't stop searching. `response_format` is dropped for this path
for the same "don't rely on an unverified tool+schema combination"
reason already established for Anthropic's own web-search mode. A
failed search (bad key, network error) is fed back to the model as an
error string rather than throwing — the model can fall back to its own
knowledge exactly as it does with search off, instead of the whole
generation crashing over one bad lookup.

**What was NOT built, again, and won't be**: actually finding and
downloading a pre-made 3D file from the search results, or having the
chat model "generate one from scratch as good as Meshy." Both remain
real, not policy-squeamish, impossibilities given how this actually
works:
- Ollama's web search API returns TEXT — titles, URLs, short content
  snippets — the same shape as Anthropic's own web_search tool. It
  cannot search "3D model marketplaces" as a distinct category, and
  even if a result linked to an actual mesh file, fetching that file
  from this browser tab would hit the same wall this project has hit
  every time this exact ask has come up: essentially no 3D-asset site
  (Sketchfab, TurboSquid, CGTrader, Free3D, etc.) sets the CORS headers
  needed to let an arbitrary third-party page fetch their files
  directly — Wikimedia Commons remains the one confirmed exception,
  and it hosts photos, not meshes.
- "Generate correctly, like Meshy" is an architecture gap, not a
  prompting one: Meshy/Tripo/Shap-E are 3D-native generative models;
  a chat model, however good at search, is still only ever writing
  `solid(x,y,z,dims)` JavaScript. No system-prompt wording changes what
  kind of model is actually answering. The one genuine architecture
  match already in this app to "generate correctly like Meshy" is the
  LocalAI `/3d/generations` backend (see above) — a real non-chat
  mesh-generation model — which is the honest answer whenever "an
  actual generated mesh, not code" is really what's wanted.

Verified via a new 15-check jsdom test: the key-row visibility toggle,
a clean validation error with zero network calls when the checkbox is
on but the key is empty, a full round trip (tool declared → app calls
the real endpoint with the right Bearer auth and the model's own query
→ result fed back with the matching `tool_call_id` → final design
applied), and a failed search still completing generation via the
model's own fallback rather than crashing. All prior AI-feature suites
(96 checks) and the full `dom-test.js` regression suite (34 checks)
still pass unchanged.

## Second worked example: multi-floor interiors with real door openings + a spiral staircase

The user asked a concrete, well-scoped question: how to get "a red house
with two floors and a spiral/helix staircase inside" out of AI Generate
mode. Worth being precise about which of this app's two AI pipelines
even applies here, since it's easy to conflate them: the LocalAI
image-to-3D backend (above) is photo-conditioned only — an invented
design with no real-world photo has nothing for it to reconstruct from,
so it's not a candidate here at all. AI Generate's text-to-code pipeline
is the only one that can produce this, since it's pure procedural
geometry, not reconstruction.

The gap: the existing "DO NOT DEFAULT TO A PLAIN BOX" worked example
(temple: platform + ring of columns + roof) teaches solid EXTERIOR
architecture with repeated positional elements, but a walkable, hollow,
MULTI-FLOOR interior with a real door and a real staircase is a
genuinely different technique class the prompt never taught: this app
has no decor/door-placement system for AI-generated shapes at all (that
machinery only exists for hand-built presets) — a door or a staircase
here has to be actual carved AIR inside `solid()` itself, not a
separate object.

Added a SECOND worked example, right after the first, teaching exactly
that: a hollow multi-floor shell (outer walls + floor slabs by height
band) with a real door opening carved via an explicit `return false`
INSIDE the wall rule (checked before the wall's own `return true` —
never a hole left by omission), plus a helical staircase technique:
divide height into a fixed step count, compute each step's rotation
angle as a function of its position in that sequence, and mark a small
solid platform at the resulting rotating (x,z) position — the same
"position as a function of a loop variable" idea as the column ring,
just driven by height/step-index instead of a fixed loop count. Also
honestly tells the MODEL ITSELF (not just documented for the user) that
Walk-mode has no automatic spawn-at-the-door for AI-generated shapes the
way some hand-built presets get via `computeEntranceSpawn` — the
geometry can be entirely correct and still drop the player on the roof
by default, and that's a property of the app's camera system the
model's own code can't fix.

Verified more rigorously than a text-only worked example usually needs:
extracted BOTH worked-example `solid()` function bodies straight out of
the actual system prompt string and ran them for real (`new Function`
over a 20×20×20 test grid), confirming the second example doesn't just
read plausibly — it genuinely compiles, produces a real non-trivial
mixed solid/air shape, and the door cell it claims to carve is actually
air when the code runs, not just described that way in a comment. All
prior AI-feature suites (111 checks) and the full `dom-test.js`
regression suite (34 checks) still pass unchanged.

## "Add a second AI modeler like Meshy" — it already existed; made that undeniable, and closed the one real gap

The user asked for "a second ai modeler that works like meshy... still
using local ai to do all searching... a new backend that's separate but
can work together... to make a compiled 3d model." The honest answer:
that second, Meshy-style pipeline already existed (the LocalAI
`/3d/generations` backend documented above) — it just wasn't obviously
legible AS a second, separate AI modeler, tucked under Import mode's
drop zone with a plain one-line "— or generate a mesh instead of
uploading one —" divider. Two things were done rather than declaring
this done and moving on.

**1. Made it read as what it actually is.** The panel is now its own
`<fieldset>` with an explicit legend — "A second, separate AI modeler
(Meshy-style): generate a real mesh instead of uploading one" — and an
opening hint stating outright that this is a genuinely different
pipeline from AI Generate (a real 3D-generative backend producing an
actual mesh, vs. a chat model writing voxel code) and why the two can't
just be merged into one (different kinds of model entirely) even though
they both end up feeding the same voxelizer.

**2. Built the one part that was genuinely new: "local AI does the
searching."** Before this, the Wikimedia photo lookup here used the
user's typed description as a literal keyword search — fine for a
specific named thing, weaker for a vague one ("that old British phone
box" won't match as well as "red K2 telephone box London"). Added
`refineSearchQueryWithLocalAI(description, baseUrl, model, signal)` and
an opt-in `#localai-refine-search` checkbox (off by default, since the
literal search already works for a specific description) with its own
base-URL/model fields (can be pointed at the exact same local server as
AI Generate's own local provider, or a different one) — when on, this
app itself sends the raw description to that chat model asking ONLY for
a sharper search phrase, then uses whatever comes back (or the original
description, on ANY failure — bad URL, no such model, timeout — since
this is a best-effort refinement layered onto an already-working
default, never a new way for generation to fail) as the actual
Wikimedia query. Same "the model only picks the words, this app
performs the real HTTP call" shape as every other tool-use path in this
file (Anthropic's web_search, Ollama's own web_search API above) — no
new exception to that pattern.

What still hasn't changed, because the reasons haven't: this remains
image-to-3D only (LocalAI's backend has no text-to-3D path), and the
"local AI" in "local AI does the searching" refers to it choosing
search WORDS, never to it browsing or downloading a 3D file on its own
— those remain the same real technical walls documented above (search
APIs return text, not files; almost no 3D-asset site's CORS policy
allows a third-party page to fetch files directly).

Verified via a new 9-check test: the refine-fields visibility toggle,
confirming the REFINED phrase (not the raw typed description) is what
actually gets searched on Wikimedia when the checkbox is on, a failed
refine call falling back to the raw description without blocking
generation, and confirming zero chat-completion calls happen at all
when the checkbox is left off. All prior AI-feature suites (119 checks)
and the full `dom-test.js` regression suite (34 checks) still pass
unchanged.

## Multi-concept research: separate reference photos for an invented combination's real parts

Direct follow-up to the spiral-staircase house example: the user pointed
out, correctly, that even though "a red house with two floors and a
spiral staircase inside" has no single real photo, each real, distinct
PART of it does — a two-story house exterior, a spiral staircase — and
asked for research to work at that level rather than one query for the
whole invented combination (which was the existing behavior: a single
`fetchWikimediaReferenceImage(promptText, ...)` call using the raw,
whole prompt as the search string, which finds nothing useful for a
made-up combination even though its ingredients are common).

Added `askModelForReferenceConcepts(local, promptText, opts, signal)`:
a lightweight, schema-free, tool-free completion call to the SAME model/
provider already selected, asking it to output a JSON array of 1-3
short search phrases for distinct real-world visual components worth a
separate reference photo — explicitly instructed to collapse back to a
single phrase (the whole description) when it already names one
well-documented real thing, so a normal single-subject prompt like
"Greek Parthenon" isn't needlessly split. `callAiGenerate()` now calls
this whenever photo research is wanted (either provider), then runs
`fetchWikimediaReferenceImage` once per returned concept in parallel via
`Promise.all`, and attaches EVERY photo that was actually found (not
just the first) to the outgoing message — Anthropic gets multiple
`{type:'image',...}` blocks, local gets multiple `{type:'image_url',...}`
entries, same per-provider shapes as the single-photo path already used.
`buildAiSystemPrompt()`'s photo paragraph now explicitly describes the
multi-photo case, telling the model each photo may correspond to a
different real part of an invented combination and to reason out which
photo maps to which part from the original description.

Failure handling follows the same "can only add value, never break
what worked before" discipline as everything else in this file:
`askModelForReferenceConcepts` catches every possible failure (bad
response, unparseable JSON, non-2xx, a cancelled request) and falls
back to `[promptText]` — the exact old single-query behavior — so
a generation that worked before this change still works identically if
this new step fails for any reason. This was verified directly, not
just asserted: every one of the 12 pre-existing test suites that
exercise the photo-lookup paths was re-run completely UNMODIFIED after
this change and all still passed, because their mocked chat-completion
responses (shaped for the final generate schema, not a bare JSON array)
naturally fail `askModelForReferenceConcepts`'s array-parsing check and
fall back to the single-concept path exactly as before — proving the
fallback is genuinely transparent, not just designed to be.

One real cost worth being upfront about: this adds one more full
model round-trip before every research-enabled generate call (which is
now default-on for Anthropic) — a real latency/cost increase on top of
an already-default-on feature. The Cancel button remains the way out of
a request that's taking too long.

Verified via a new 10-check test built around the user's own exact
example ("a red two-story house with a spiral staircase inside"):
confirms the decomposition call is plain (no tools/schema) and receives
the real prompt text, that it genuinely drives two SEPARATE Wikimedia
searches for two distinct real components rather than one search for
the whole invented phrase, and that BOTH resulting photos — not just
one — end up attached to the final generate request alongside the
original prompt text. All prior AI-feature suites (128 checks total,
run unmodified) and the full `dom-test.js` regression suite (34 checks)
still pass unchanged.

## A real chest object, and AI Generate can now place real furnishings, not just voxel fill

The user pushed on the same "does the local AI actually do everything by
itself" architecture question one more time — insisting the HTTP calls a
tool-calling loop makes should be made "by the ai not the modeler app."
Same answer as every earlier round of this exact question, re-verified
rather than just repeated: no LLM's weights can perform network I/O
themselves, confirmed concretely this time via Ollama's own
`OLLAMA_API_KEY` — that key is used by the CLIENT application (whatever
orchestrates a tool-calling loop), never sent to the local `ollama serve`
process itself, so even Ollama's own first-party tooling can't make "the
local server" do this autonomously. This is a universal architectural
fact, not a limitation specific to this app.

Separately, the user clarified (after some crossed wires) that their real
concern was license review, not architecture — asserting their local AI
"is only searching the web not downloading models automatically" and
that therefore some "license/verification pipeline" should be removed.
Checked directly via `grep` rather than assumed: there is no runtime
license-checking code anywhere in this app gating search/generate. The
only license-related content at all is static attribution comments/README
credits for the 5 hand-embedded real-model presets (Statue of Liberty,
Vader Helmet, Golden Gate Bridge, Colosseum, Kip), required by their own
CC-BY-4.0 terms — unrelated to and never in the AI pipeline's path. No
code change was needed; there was nothing to remove.

The user then asked the concrete, well-scoped question this session
actually answers: can AI Generate build a two-floor building with a
staircase AND a chest inside, and does the app already have a chest asset
it can tell the AI about. Checked the second part directly via `grep`
first rather than take the premise on faith: **no chest asset of any kind
existed** — not a decor object, not even a plain reused block texture.
More fundamentally, AI Generate had no mechanism at all to place any
discrete furnishing object (a door, a torch, a chest) — its only two
outputs were `solid()` (voxel fill) and `materialCode` (per-cell paint),
never a placed-object list, even for object types (door, torch, ladder)
that already existed elsewhere in the app for hand-built presets.

**Part A: a real chest, added to the app's general decor system** (not
AI-specific — any preset or the freeform builder can use it too).
`DECOR_TYPES.chest` reuses `oak_planks` as a texture stand-in (no unique
chest texture exists in this app's atlas — chests are a block-entity in
real vanilla, not part of the basic block set that atlas was extracted
from), but the real distinguishing SHAPE is built as genuine geometry via
a new `chestParts(tileKey)`: a squat 14×10×14px main body (vanilla's own
real footprint, a 1px margin on every side), a separate, slightly raised
14×4×14px lid section on top, and a small dark 2×4×1px latch straddling
the body/lid seam on the front face — three real parts, not one flat
textured cube, which is what actually reads as "a chest" rather than a
plain box. Wired into `buildDecorMeshesForEntry()` as a new dispatch
branch (a `THREE.Group` of the three parts, oriented via the same
`FACING_YAW` lookup every other facing-aware decor type already uses),
and into the `/fill` export loop as `setblock ... minecraft:chest[facing=...]`,
matching the pattern every other decor type's export line already
follows.

**Part B: AI Generate's JSON contract gained an optional `decor` array**,
so the AI's response can now place real furnishing objects at exact
coordinates, not just choose fill/paint. Added `AI_PLACEABLE_DECOR_TYPES`
— a deliberately curated 16-entry subset of the app's full `DECOR_TYPES`:
`door, trapdoor, window, ladder, bars, lever, button, pressure_plate,
chair, torch, soul_torch, chest, flower, dandelion, grass_tuft, tree`.
Two categories of the app's full decor set were deliberately excluded and
documented as such directly in the constant's own comment: every
mob/animal type (their wander/look-at AI is wired up by specific
hand-built interior-builder functions for specific contexts, not verified
safe to trigger generically from an arbitrary AI-chosen coordinate), and
every multi-entry contraption piece that only makes sense wired together
across several coordinated cells (rail, redstone_wire, redstone_torch,
tripwire/tripwire_hook, hopper, minecart) — a lone AI-placed rail segment
or wire dot from a model with no understanding of real redstone wiring
would read as a mistake, not a feature. This is furnishing-a-building
scope: doors, openings, light, simple interactables, storage, and basic
greenery.

`AI_SHAPE_JSON_SCHEMA` gained a `decor` field (array of `{type, x, y, z}`,
required-but-empty-array-is-valid, matching the existing pattern for
"required but has a sane empty default" fields like `materialCode`) and
`AI_JSON_ONLY_INSTRUCTION`/`buildAiSystemPrompt()` were updated to name
it under a new "PLACEABLE OBJECTS" section, explicitly listing the 16
allowed types, telling the model to only place one at a cell its OWN
`solid()` already leaves as open air (never inside a solid cell, where
it'd be invisible), and — a mistake I caught and fixed in my own first
draft before running any test — explicitly clarifying that "chair" is a
single piece of seating furniture, NOT how to build an actual staircase;
a real walkable staircase is still voxel geometry built directly in
`solid()` (the existing spiral/helical worked example), never a decor
placement.

`callAiGenerate()` validates each returned decor entry independently
(never lets one bad entry block the others, or the core shape): a real
allowed type, and integer x/y/z actually inside `testDims` — the same
real target-size bounding box the existing "completely empty shape"
sanity check already validates `solid()` against. Valid entries are
tracked in new `aiCurrentDecor`/`aiGeneratedDecor` state (alongside the
existing `aiCurrentCode`/`aiGeneratedFn` pair, reset together on Clear,
re-embedded in the system prompt's "CURRENT DECOR" block for follow-ups
exactly like current code/materials already are). `generateModel()` pushes
`aiGeneratedDecor` into the SAME shared `decor` array every hand-built
preset's own interior-builder already populates — deliberately not a
parallel/separate mechanism — so an AI-placed object renders, exports via
`/fill`, and gets one genuine bonus for free with zero extra plumbing:
Walk-mode's existing `computeEntranceSpawn`/`decor.find(d => d.type ===
'door')` entrance-spawn detection already scans the shared `decor` array,
so an AI-placed `door` now gets a real spawn-at-the-doorway just like a
hand-built preset's own door, not the old drop-from-above default.
Coordinates are re-validated a second time here against the real `dims`
in effect at generate time (not just the `testDims` checked earlier in
`callAiGenerate()`), since the user can edit the real height/width/depth
fields after the AI answers but before clicking "Generate model," which
could shift the valid coordinate range out from under previously-valid
AI-chosen coordinates.

Verified via a new 11-check test (`chest` registered with real 3-part
geometry via `buildDecorMeshesForEntry`; the system prompt's PLACEABLE
OBJECTS section and its chair-is-not-a-staircase clarification; and,
using the user's own exact scenario — a hut with a chest inside — an
end-to-end mocked Anthropic response with 3 decor entries (1 valid chest,
1 invalid type, 1 out-of-bounds) correctly filtering down to exactly the
1 valid entry, which lands in `currentModel.decor` at the exact AI-chosen
coordinates after clicking Generate, and is re-embedded correctly in a
follow-up system prompt). All 13 prior AI-feature test suites (138 checks
total) were re-run UNMODIFIED and still passed, and the full `dom-test.js`
regression suite (34 checks) still passed — bringing the AI-feature total
to 149 checks.

### Follow-up: the chest's own color was wrong, not just placeholder-flavored

The user pushed back hard on "no chest asset exists," pointing out chest
is a real, official Minecraft block/texture and this app should already
have it. That pushback surfaced a real distinction worth being precise
about, since both things are true at once: the *reason* chest isn't in
this app's atlas is real and structural (confirmed by grepping the whole
`ATLAS_UV` key list — every one of its ~320 entries is a plain square
block-face texture; real vanilla chests are a block-entity rendered from
their own non-square `chest.png-atlas` sheet with distinct front/back/
left/right/top/underside regions, which doesn't fit this atlas's
one-square-tile-per-key system at all) — but reusing `oak_planks` as the
color stand-in was a real, avoidable inaccuracy on top of that, not just
an inherent limitation. Checked via `WebSearch` (not assumed) rather than
just asserted a fix: Minecraft's own feedback-site threads on "Wooden
Variants for Chests and Barrels" explicitly describe vanilla's own chest
color as "an odd orange-brown that doesn't match any of the other wood/
wood-derived blocks in the game" — i.e., a chest is NOT oak-plank colored
in real vanilla, confirming the placeholder was a wrong stand-in, not
just an approximate one. Separately corroborated (indirectly but
solidly): the Trapped Chest variant's own wiki page documents it tinting
its own latch RED specifically to visually distinguish itself from a
normal chest — which only makes sense if a normal chest's latch/trim is
some neutral dark tone to begin with, not gold.

Fixed by dropping the oak_planks tile reuse entirely and reproducing the
real distinguishing COLORS directly: `CHEST_WOOD_COLOR = 0xa5672d` (a
saturated orange-brown, distinctly warmer/more orange than oak planks)
for the body/lid, `CHEST_TRIM_COLOR = 0x33302b` (dark iron-gray, not
gold) for the latch and 4 new vertical corner trim posts spanning the
body+lid height — matching every real reference image's own visible
corner/edge banding, which the original single-latch-only version didn't
have at all. `chestParts()` no longer takes a `tileKey`/calls `remapUV`
since there's no atlas tile to sample anymore; `DECOR_TYPES.chest` lost
its now-inaccurate `tile: 'oak_planks'` field entirely (confirmed via
grep that `tile` is only read by kind-specific render branches, never a
required schema field — `cow`/`pig`/`sheep` and other non-textured decor
kinds already have no `tile` field at all, so this isn't a new pattern).

Verified by updating the existing chest test in place: the chest group
now has 7 children (body, lid, latch, 4 posts) instead of 3, and a new
assertion reads the body mesh's actual material color and confirms it's
the real `0xa5672d`, not oak-plank brown — re-run and passing (12/12,
the one prior assertion count moved by +1 for the new color check). The
full `dom-test.js` regression suite (34 checks) was also re-run and
still passes unchanged.

## AI Generate gets the real interior-builder too, not just hand-carved solid()/decor

The user asked directly: "can you add the interior builder and integrate it
for the AI to design [with]." Up to this point, AI Generate's only path to
a walkable multi-floor interior was entirely on the model's own shoulders —
hand-write the floor slabs, stairwell, door, and windows all inside
`solid()` itself (the existing spiral-staircase worked example), a
genuinely harder task than describing the exterior shape, and one this
project's own notes already flagged as a common failure point for a
weaker/local model. Meanwhile this app already has a proven, reusable,
non-preset-specific interior builder sitting right there: `buildFloorsInterior
(grid, silhouette, dims, blocksPerFloor, exteriorMat, accentMat, decorOut)`
— used by every hand-built multi-story building preset (village house,
windmill, watchtower, lighthouse) — which works from nothing but an
arbitrary silhouette (it scans outward from the center to find the real
wall at any height, so it already handles a tapering shape like a dome or
stepped tower correctly) and carves a real hollow shell + floor slabs +
one ladder stairwell + a front door + windows + a chair, entirely
independent of any specific building's own geometry. That genericity is
exactly what made it safe to point at an AI-generated silhouette too,
without writing a second, parallel interior-builder implementation.

**What was built**: a new `interiorMode` field (enum `"none"`/`"floors"`)
and `floorHeightMeters` field added to `AI_SHAPE_JSON_SCHEMA` (both
required, matching the existing "required but has a sane default" pattern
already used for `fillMode`/`wallThickness`/`materialCode`). When the AI
sets `interiorMode: "floors"`, `generateModel()` calls
`buildFloorsInterior(grid, silhouette, dims, bpf, matExt, matAcc, decor)`
— `bpf` computed the exact same way a hand-built floors-mode preset
computes it (`Math.round(floorHeightMeters * scale)`) — right before
`applyAiMaterialPaint`, since `buildFloorsInterior` REBUILDS the entire
grid from the silhouette (discarding whatever the AI's own `solid()`
carved on the inside, and overriding whatever `fillMode`/`wallThickness`
it chose, exactly like a hand-built preset's own "floors" interiorMode
already does), so any `materialCode` per-part painting needs to land on
the real final wall/floor/window cells this produces, not cells that get
carved to air afterward. `buildFloorsInterior` pushes its own real
door/ladder/chair/window entries into the SAME shared `decor` array the
AI's own `decor` field (chest, torch, etc. — see the section above) also
feeds, so both coexist automatically, and the existing `entranceEntry =
interiorEntrance || decor.find(d => d.type === 'door')` Walk-mode
spawn-detection logic picks up the builder's own door with zero new code
— an AI-generated design placed at a real doorway automatically now,
without a hand-carved door needing that separately.

Validation follows the same "never blocks the core shape, fall back to a
sane default" discipline as everything else in this pipeline: an
`interiorMode` value other than `"floors"` silently falls back to
`"none"` rather than rejecting the whole response, and `floorHeightMeters`
falls back to a real ordinary room height (3m) when non-numeric and is
clamped to [2, 15] when it's a real but absurd number — protecting
`buildFloorsInterior`'s own `blocksPerFloor` computation from a
degenerate (zero, or absurdly tall) floor spacing a weaker model might
return. New `aiCurrentInteriorMode`/`aiGeneratedInteriorMode` and
`aiCurrentFloorHeightMeters`/`aiGeneratedFloorHeightMeters` state pairs
follow the exact same track-current/reset-on-Clear/re-embed-in-follow-up
pattern already established for `aiCurrentDecor`/`aiGeneratedDecor`.

The system prompt gained a new "BUILT-IN MULTI-FLOOR INTERIOR BUILDER"
paragraph, placed right before the existing hand-carved multi-floor
worked example, explicitly telling the model to PREFER `interiorMode:
"floors"` for an ordinary walkable multi-story building (simpler, more
reliable than hand-carving the equivalent by hand) and reserve the
hand-carved `solid()` approach for when a genuinely custom interior is
needed that the generic builder can't produce — most commonly a real
SPIRAL/HELICAL staircase specifically, since the builder's own stairwell
is a plain straight ladder shaft, or several distinct named rooms. The
existing hand-carved worked example's own intro text was corrected at
the same time: it previously claimed outright that "this app has no
separate decor/door-placement system for AI-generated shapes," which
was already stale from the chest/decor work documented in the section
above — reworded to point at the decor array (for placing an extra
object at an already-carved-open cell) and at `interiorMode:"floors"`
(for when a plain interior would do) as the two real alternatives, and
to note that a hand-carved door specifically does NOT get automatic
Walk-mode entrance-spawn the way the builder's own door or a placed
`door` decor entry both do — narrowing that limitation to exactly the
case it still applies to, rather than describing it as a blanket
property of AI Generate mode.

Verified via a new 14-check jsdom test: the system prompt actually
contains the new section and both new field names; an end-to-end mocked
Anthropic response with `interiorMode: "floors"` genuinely produces a
real carved door and a real ladder stairwell in the final rendered
model's own `decor` array, that the AI's OWN separately-specified decor
entry (a chest) survives alongside the builder's own decor rather than
being overwritten, and that `currentModel.spawnPoint` ends up set purely
from the builder's own door (proving the existing entrance-spawn logic
picked it up with no new wiring); an invalid `interiorMode` string falls
back to `"none"` without rejecting the design; an absurdly large and a
non-numeric `floorHeightMeters` both fall back to sane values (15 and 3
respectively); a follow-up prompt correctly re-embeds `CURRENT INTERIOR
MODE: "floors"`; and Clear resets all 4 new state variables back to
their defaults. All 14 prior AI-feature test suites (150 checks total)
were re-run UNMODIFIED and still passed, and the full `dom-test.js`
regression suite (34 checks) still passed.

## Strafe direction was backwards in Walk/third-person mode (real sign bug, not a design choice)

The user reported that A/D strafing in Walk (first-person) and third-person
mode didn't move relative to the camera/player's own facing direction the
way it should. Traced this to `updateFreeCamera(dt)` — the single shared
movement function behind free-fly, Walk, AND third-person alike (so any fix
here applies to all three at once) — which computed:

```js
const right = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 1, 0)).normalize().negate();
```

Verified the actual math independently rather than guessing which sign was
"probably" right: `dirFromYawPitch(0, 0)` returns `(0, 0, -1)` (this app's
own convention: yaw 0 faces -Z, matching Three.js's standard camera-forward
axis). For a viewer facing that direction with +Y up, the real right-hand
side — the direction the D key is supposed to strafe toward — is `+X`,
confirmed by the standard `right = cross(forward, up)` lookAt-basis formula
(the same convention this app's own `dirFromYawPitch`/mouselook math is
already built on, so this isn't introducing a new convention, just
correcting an inconsistency with the one already in use). `cross(dir, up)`
alone already evaluates to `(1, 0, 0)` — the correct answer — but the
code's own trailing `.negate()` flipped it to `(-1, 0, 0)`, the LEFT side,
and that inverted vector is exactly what `KeyD`/`KeyA` were both wired to
(`mx += right.x` for D, `mx -= right.x` for A) two lines below. Net effect:
D strafed left and A strafed right, backwards from the direction the
camera/player model was actually facing, in every mode that shares this
function (free-fly included, though the user only reported it in Walk/
third-person).

Fixed by simply dropping the erroneous `.negate()`. `right` is used
NOWHERE else in the file (confirmed via grep) except the two `KeyD`/`KeyA`
lines immediately below its declaration, so this was a fully isolated,
one-line fix with no other call site to reconcile.

Verified via a new 4-check jsdom test rather than trusting the hand-derived
math alone: generates a real flat platform, sets `flyState.yaw`/`pitch`
directly, and confirms `KeyD`/`KeyA` move the player toward the
mathematically-correct side of two DIFFERENT facing directions (yaw 0,
facing -Z, and yaw -90°, facing +X — the second case exists specifically
to rule out the fix only working by coincidence at yaw 0), plus one more
check confirming third-person mode — the mode named in the report —
shares the exact same corrected behavior. The full `dom-test.js` regression
suite (34 checks) was re-run and still passes unchanged, confirming this
one-line fix didn't disturb anything else (collision, gravity, pressure
plates, and every other consumer of `updateFreeCamera`'s own movement
math all still behave identically aside from the corrected strafe
direction).
