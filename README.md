# 🎴 ChaseBreak

A mock trading-card "pack rip" app in the spirit of Courtside — pick a category (Pokémon, Yu-Gi-Oh!, Basketball, Baseball, Football), a pack size, tear it open, and watch cards flip one-by-one with rarity-based holo shine and particle effects. Pulls land in a collection binder with per-set completion tracking.

This is a self-contained HTML/CSS/JS app (`app/index.html`) with real card/player photos (`data/cards.json`) embedded and rendered full-screen through a thin Streamlit wrapper (`streamlit_app.py`).

> **This app uses simulated in-app "Cash" only.** There is no real payment processing anywhere in this codebase, and nothing here can be redeemed, cashed out, or exchanged for real money — the "Add Funds" button just adds to a local mock balance. Pack prices and card "values" are themed to look like real dollar amounts for realism, but they are entirely fictional. This is intentional: pay-real-money-for-a-random-reward-of-uncertain-value is a gambling mechanic in most jurisdictions, and this project deliberately stays a closed, non-redeemable simulation rather than becoming one.

- **Packs & tiers** — 5 themed categories, each offering 7 pack sizes (1 through 6 cards, plus a 6-card "mega" tier), priced on a simulated $1–$500 ladder. Bigger/pricier tiers noticeably raise the odds floor across every card in the pack, not just the last one.
- **Rip flow** — tap anywhere on the top card to flip it, one at a time (Pokémon TCGP-style) — the rarest pull always lands last, and you can tilt the whole stack to catch each card's own rarity-tinted shine on its face-down edge before flipping.
- **Holo/rare effects** — rare, epic, and legendary pulls get an animated prismatic foil sweep and a particle burst; a legendary pull gets a full cinematic moment (screen flash, spotlight, shockwave rings).
- **Collection & Vault** — a binder grid per category with lock icons for un-pulled cards, duplicate counts, completion %, and a "Value"/"Est. value" tag per card. Duplicates can be "vaulted" for 87% of that value in simulated Cash — again, never real money.
- **1,022 real cards** — the first 4 English Pokémon TCG sets complete (Base Set, Jungle, Fossil, Team Rocket — 311 cards) and the first 4 English Yu-Gi-Oh! TCG sets complete (Legend of Blue-Eyes White Dragon, Metal Raiders, Spell Ruler, Pharaoh's Servant — 479 cards, rarities matched to their real historical print rarity), plus 80+ real players each for basketball, baseball, and football.
- **Real market values, fully researched** — all 790 TCG cards (311 Pokémon + 479 Yu-Gi-Oh, 100%) carry a `realValue` sourced from an actual web search per card, not estimated — from $0.10 commons up to a $400 Base Set Charizard. Cards with a real price show "Value"; sports entries (which aren't tied to a specific real card/product) show a rarity-scaled "Est. value."

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
