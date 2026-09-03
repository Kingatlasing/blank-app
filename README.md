# 🏆 Sideline Rips

A mock trading-card "pack rip" app in the spirit of Courtside — pick a category (Pokémon, Yu-Gi-Oh!, Basketball, Baseball, Football), buy a pack with mock coins, tear it open, and watch cards flip one-by-one with rarity-based holo shine and particle effects. Pulls land in a collection binder with per-set completion tracking.

This is a self-contained HTML/CSS/JS app (`app/index.html`) with real card/player photos (`data/cards.json`) embedded and rendered full-screen through a thin Streamlit wrapper (`streamlit_app.py`).

- **Packs** — 5 themed packs, each with its own rarity odds (common → legendary) and a branded foil pack design.
- **Rip flow** — tap anywhere on the top card to flip it, one at a time (Pokémon TCGP-style) — the rarest pull always lands last, and you can tilt the whole stack to catch each card's own foil shine on its face-down edge before flipping.
- **Holo/rare effects** — rare, epic, and legendary pulls get an animated prismatic foil sweep and a particle burst; a legendary pull gets a full cinematic moment (screen flash, spotlight, shockwave rings).
- **Collection** — a binder grid per category with lock icons for un-pulled cards, duplicate counts, and completion %. 460 real cards total: the complete 102-card Pokémon Base Set, the complete 126-card Yu-Gi-Oh! Legend of Blue-Eyes White Dragon set, and 80+ real players each for basketball, baseball, and football.
- **Mock economy** — coins to buy packs, a "+ Get Coins" button since this is a demo with no real money involved.

**Design credits** — typography is Google Fonts (Sora / Manrope). Icons are Font Awesome Free solid icons (© Fonticons, Inc., [CC BY 4.0](https://fontawesome.com/license/free)), bundled as an inline SVG sprite. Foil/grain textures are generated procedurally (SVG `feTurbulence` + CSS gradients) rather than downloaded, so the app never depends on an external texture host at runtime.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
