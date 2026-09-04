# Asset Credits

All art and audio embedded in `app/index.html` is CC0-licensed (public domain
equivalent — free for any use, no attribution legally required). Credit here
is given anyway because it's appreciated by the original creators.

Assets were sourced from two public CC0 GitHub mirrors so they could be
fetched directly (this environment's network policy does not allow reaching
kenney.nl, itch.io, or opengameart.org directly):

- **[github.com/ETdoFresh/kenney.nl](https://github.com/ETdoFresh/kenney.nl)** —
  a mirror of [Kenney](https://kenney.nl)'s asset packs. Packs used: Nature Kit,
  Graveyard Kit, Weapon Pack, Casino Audio, Digital Audio, Impact Sounds,
  Interface Sounds, UI Audio, RPG Audio, Music Jingles, UI Pack, Game Icons
  (+ expansion), Medals Pack, Emotes Pack.
- **[github.com/Tiddybub/2d-assets](https://github.com/Tiddybub/2d-assets)** —
  a curated CC0 index (license verified per-asset via its `catalog.json`) of
  Kenney and OpenGameArt.org contributor packs. Packs used: Toon Characters
  (male adventurer, female adventurer, and zombie skins — same pose set
  across all three), Animal Pack Remastered, Fish Pack, Modular Characters,
  Shooting Gallery, Crosshair Pack, Playing Cards Pack, Board Game Pack,
  Board Game Icons, and several OpenGameArt.org CC0 items (cemetery/graveyard
  art, "Two Pistols," "The Hooded One" portrait).

Fonts are loaded from Google Fonts at runtime (Rye, Special Elite, Nunito).

Sound effects not available as clean CC0 samples (gunshots, zombie growls,
splashes, wood cracks) are synthesized live in-browser with the Web Audio
API rather than downloaded, in the same spirit as this repo's earlier
Lemonade Stand Tycoon build.

The casino minigames (Roulette, Blackjack, Baccarat, Coin Flip, Shell Game),
when ported in, will reuse original code from this repo's own
`claude/courtside-card-pack-mock-app-99fqki` branch (project name:
ChaseBreak) — not third-party assets.
