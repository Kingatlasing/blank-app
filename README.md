# 🏆 Sideline Rips

A mock trading-card "pack rip" app in the spirit of Courtside — pick a category (Pokémon, Yu-Gi-Oh!, Basketball, Baseball, Football), buy a pack with mock coins, tear it open, and watch cards flip one-by-one with rarity-based holo shine and particle effects. Pulls land in a collection binder with per-set completion tracking.

This is a self-contained HTML/CSS/JS app (`app/index.html`) with real card/player photos (`data/cards.json`) embedded and rendered full-screen through a thin Streamlit wrapper (`streamlit_app.py`).

- **Packs** — 5 themed packs, each with its own rarity odds (common → legendary).
- **Rip animation** — tap to tear the pack, cards cascade-flip with a 3D card-back → card-front animation.
- **Holo/rare effects** — epic and legendary pulls get an animated foil sweep plus a particle burst.
- **Collection** — a binder grid per category with lock icons for un-pulled cards, duplicate counts, and completion %.
- **Mock economy** — coins to buy packs, a "+ Get Coins" button since this is a demo with no real money involved.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
