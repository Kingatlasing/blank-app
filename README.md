# 🔥 Emberwild Trails

An original creature-taming RPG in the spirit of classic Game Boy Advance-era
monster games — pick a starter, explore a connected world of towns and
routes, catch and train creatures, battle Arena Leaders and a rival crime
syndicate, and take on the Champion.

This is a self-contained HTML/CSS/JS game (`app/index.html`, canvas-rendered)
served full-screen through a thin Streamlit wrapper (`streamlit_app.py`), in
the same self-contained-single-file style as this repo's previous games.

- **165 original creatures** — full stat lines, movesets, and evolution
  chains across 13 elemental types
- **A connected world** — five hand-built-into-real-Tiled-maps locations
  (Cottonwood Town, Route 1, Ashveld Town, Route 2, Crysthaven City) plus a
  villain hideout and a final Summit, all rendered from real tile art (roads,
  buildings, fences, fountains, trees)
- **Turn-based battles** — type effectiveness, capture mechanics, leveling,
  evolution, trainer battles
- **Story & side quests** — a main quest through two Arena Leaders and the
  "Enforcers" crime syndicate, plus a lost-pet quest and a hidden-item hunt
- **A mini-game** — Berry Toss, a timing reflex game
- **Save/continue** — autosave-style save via `localStorage`

### Where the assets come from

Every texture, building, tile, creature sprite, item icon, and character
sprite is adapted from two **open-source** projects (Tuxemon and a
Phaser/Tiled sample map project) under their CC BY-SA / GPL / WTFPL licenses
— no Nintendo/Game Freak/Pokémon assets are used anywhere. Full credit and
license details are in [`ATTRIBUTIONS.md`](ATTRIBUTIONS.md).

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

You can also just open `app/index.html` directly in a browser.
