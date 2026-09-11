# Notes for Claude (persistent across sessions)

## Pending task: full armor-piece audit against the wiki's own image pages

**Status: NOT STARTED. Do not start this until every mob, animal, item,
and block the user has asked for is otherwise complete** — this is an
explicit final audit pass requested by the user, deliberately deferred
until the rest of the work is done, not something to interleave with it.

The user's own instruction (verbatim intent): check every armor piece
already modeled in this app against the Minecraft wiki's own reference
images for that exact piece, not against memory. They gave this specific
starting point:

    https://minecraft.fandom.com/wiki/Special:Search?scope=internal&query=Helmet&ns%5B0%5D=6

That's a Fandom internal search scoped to the File namespace (`ns[0]=6`),
which returns image files whose name/tags match "Helmet" — i.e. every
helmet texture/render Fandom has on file, each with its own file
description page (open each result's own page, not just the thumbnail —
the user was explicit that "they have descriptions").

When this task is picked up:
1. Run the equivalent search once per armor slot — swap the `query=`
   value for `Chestplate`, `Leggings`, and `Boots` — to cover every piece,
   not just helmets.
2. Open each real result's own file page and read its description, not
   just the thumbnail image.
3. Cross-reference against every armor piece this app has actually built
   — see `ARMOR_TIER_COLORS`, `armorStandParts()`, and the `armor_stand`
   render branch in `app/index.html` (the Armor Tier Rack preset is the
   visual proof of current state) — and fix any real mismatch found
   (color, shape, a missing per-tier or per-slot visual detail).
4. Direct `WebFetch` to `minecraft.wiki` / `minecraft.fandom.com` has been
   blocked by this environment's own network egress policy in past
   sessions — use `WebSearch` (works) or a research subagent instead, the
   same workaround already used for the mob wiki-audit pass earlier in
   this project's history.
5. Test, screenshot, and commit the same way every other change in this
   project has been (see README.md's own mob-by-mob paragraphs for the
   established citation/verification/commit pattern) — this is a
   correctness pass, not a new feature, so it likely doesn't need its own
   README paragraph unless a fix is significant enough to warrant one
   (matching the precedent already set by the mob wiki-audit commit).

This file exists specifically so this instruction survives a session
compaction or a fresh session picking up this branch later. Once this
audit is actually done, this section can be removed.
