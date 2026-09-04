# 🎴 ChaseBreak

A mock trading-card "pack rip" app in the spirit of Courtside — pick a category (Pokémon, Yu-Gi-Oh!, Basketball, Baseball, Football), a pack size, tear it open, and watch cards flip one-by-one with rarity-based holo shine and particle effects. Pulls land in a collection binder with per-set completion tracking.

This is a self-contained HTML/CSS/JS app (`app/index.html`) with real card/player photos (`data/cards.json`) embedded and rendered full-screen through a thin Streamlit wrapper (`streamlit_app.py`).

> **This app uses simulated in-app "Cash" only.** There is no real payment processing anywhere in this codebase, and nothing here can be redeemed, cashed out, or exchanged for real money — the "Add Funds" button just adds to a local mock balance. Pack prices, card "values", and every wager in the Games section are themed to look like real dollar amounts for realism, but they are entirely fictional. This is intentional: pay-real-money-for-a-random-reward-of-uncertain-value is a gambling mechanic in most jurisdictions, and this project deliberately stays a closed, non-redeemable simulation rather than becoming one.

- **Packs & tiers** — 5 themed categories, each offering 7 pack sizes (1 through 6 cards, plus a 6-card "mega" tier), priced on a simulated $1–$500 ladder. Each tier advertises a card-value range (e.g. "$0.15 – $5.00"), computed live from the category's actual price distribution, and every card pulled from that tier is drawn from within its advertised range.
- **Rip flow** — tap anywhere on the top card to flip it, one at a time (Pokémon TCGP-style) — the rarest pull always lands last, and you can tilt the whole stack to catch each card's own rarity-tinted shine on its face-down edge before flipping. Each pack card has a hand-illustrated foil back (medallion seal, corner gems, engraved frame) themed to its category.
- **Sell or Vault, your choice** — after flipping each card you decide, on the spot: sell it back for instant Cash (87% of its value, min $1) or send it to your Vault to keep. Selling is always optional, never required — it's just a way to fund more packs if you want to.
- **Holo/rare effects** — rare and epic pulls get their own animated flash/shockwave moment; a legendary pull gets a full cinematic moment (screen flash, spotlight, shockwave rings).
- **Vault** — scrollable (the pack-opening and game screens never scroll, but there's a full collection to browse here). Split into its own section per category — Pokémon with Pokémon, Yu-Gi-Oh! with Yu-Gi-Oh!, and so on — with lock icons for un-pulled cards, duplicate counts, completion %, a "Value"/"Est. value" tag per card, and an "Owned Only" toggle that hides every locked slot so you can see just what you've actually collected. Any owned card (including your last copy) can be sold back for Cash straight from the Vault.
- **1,022 real cards** — the first 4 English Pokémon TCG sets complete (Base Set, Jungle, Fossil, Team Rocket — 311 cards) and the first 4 English Yu-Gi-Oh! TCG sets complete (Legend of Blue-Eyes White Dragon, Metal Raiders, Spell Ruler, Pharaoh's Servant — 479 cards, rarities matched to their real historical print rarity), plus 80+ real players each for basketball, baseball, and football.
- **Real market values, fully researched** — all 790 TCG cards (311 Pokémon + 479 Yu-Gi-Oh, 100%) carry a `realValue` sourced from an actual web search per card, not estimated — from $0.10 commons up to a $400 Base Set Charizard. Cards with a real price show "Value"; sports entries (which aren't tied to a specific real card/product) show a rarity-scaled "Est. value."
- **Games** — five standalone casino-style games (Coin Flip, Roulette, Blackjack, Baccarat, Shell Game), each on its own no-scroll page, wagering the same simulated Cash balance as the pack store. Every game shares a collapsible sidebar menu (hamburger icon, top-left) for jumping straight to another game or back to the pack store with one tap, plus a gold particle-burst celebration on a win (a bigger gold ring effect on a jackpot-tier hit). Roulette is a full American double-zero table — straight numbers (36x), dozens and columns (3x), and the usual red/black/odd/even/high/low outside bets (2x) — with a real spinning wheel (complete with 8 deflector pins the ball visibly bounces off) and an animated ball that keeps rolling and bouncing after the wheel stops before dropping into the winning pocket. Blackjack and Baccarat follow standard casino rules (blackjack pays 3:2, baccarat banker bets carry a 5% commission, ties push on Player/Banker bets) and deal from a classic red diamond-lattice card back.

**Design credits** — the ChaseBreak logo is original artwork made for this project. Typography is Google Fonts (Sora / Manrope). Icons are Font Awesome Free solid icons (© Fonticons, Inc., [CC BY 4.0](https://fontawesome.com/license/free)), bundled as an inline SVG sprite. Foil/grain textures are generated procedurally (SVG `feTurbulence` + CSS gradients) rather than downloaded, so the app never depends on an external texture host at runtime.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
