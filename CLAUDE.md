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
