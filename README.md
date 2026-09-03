# 🍋 Lemonade Stand Tycoon

A polished, fully playable lemonade-stand management game in the spirit of the classic 2000s tycoon sims — mix your recipe, price your cups, stock your supplies, and run a real-time day at the stand with animated customers, weather, day/night cycles, and random events.

This is a self-contained HTML/CSS/JS game (`app/index.html`, canvas-rendered with procedural Web Audio sound effects) rendered full-screen through a thin Streamlit wrapper (`streamlit_app.py`), with all art embedded as base64 image data so the whole game ships as one file with no network requests.

**Art credits**: the stand, scenery, food props, satisfaction icons, and the distant town skyline are from [Kenney](https://kenney.nl)'s CC0-licensed packs (Fantasy Town Kit, Food Kit, Background Elements, Emotes, Animal Pack, Isometric Buildings — no attribution required, credited here anyway). Customer and robber sprites are composited from the [Liberated Pixel Cup (LPC) / Universal LPC Spritesheet](https://opengameart.org/content/liberated-pixel-cup-lpc-base-assets-sprites-map-tiles) asset collection (CC-BY-SA 3.0 / GPL 3.0 / GPL 2.0 / OGA-BY 3.0, mixed per piece), built by a large community of contributors including bluecarrot16, Benjamin K. Smith (BenCreating), Evert, Eliza Wyatt (ElizaWy), TheraHedwig, MuffinElZangano, Durrani, Johannes Sjölund (wulax), Stephen Challener (Redshrike), JaidynReiman, Lanea Zimmerman (Sharm), Luke Mehl, Mandi Paugh, Marcel van de Steeg (MadMarcel), Mark Weyer, Matthew Krohn (makrohn), Nila122, Nyom, Pierre Vigier (pvigier), Joe White, dalonedrau, and kheftel, assembled via the [Universal LPC Spritesheet Character Generator](https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator). Full license texts: [CC-BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/), [GPL 3.0](https://www.gnu.org/licenses/gpl-3.0.html), [GPL 2.0](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html), [OGA-BY 3.0](https://opengameart.org/content/oga-by-30-faq).

- **Recipe lab** — tune lemons, sugar, and ice per cup and watch live sweetness/tartness/coldness bars, cost-per-cup, and profit margin update instantly.
- **Supply run** — buy lemons, sugar, ice, and cups before opening; run out mid-day and customers walk away.
- **Live day simulation** — animated customers walk up from the sidewalk, queue, "think it over" in a thought bubble, and either buy happily (with a little cheer) or walk off showing exactly what went wrong: too sweet 🍬, too tart 🍋, too cold ❄️, too warm 🥵, or too expensive 💸.
- **Weather, seasons & day/night** — eleven weather types (including heatwaves, wind, fog, and freak snow) roll with season-aware odds across a rotating spring/summer/fall/winter calendar, all rendered with a full sky/sun/moon/cloud/rain/snow/fog system and a 3-day forecast.
- **Catch the Robber** — a timed reflex mini-game: a robber creeps toward your cash box in random spots — click him before he gets away or he steals a cut of your cash.
- **Lemon Squeeze Frenzy** — a random bonus mini-game where tapping lemons quickly earns free supplies and tips.
- **Ice Delivery Catch** — a random mouse-controlled mini-game: catch falling ice in your cup and dodge the rotten lemons for bonus ice and tips.
- **Story & progression** — narrative beats roll in as the days pass (a rival cart competing for customers, a food critic visit worth a big reputation swing, franchise milestones), and your stand itself visibly levels up the more you earn.
- **Upgrade shop** — signs, umbrellas, a second pitcher, fancy cups, a guard dog, a neon sign, a tip jar, and a rain awning, each with a real gameplay effect.
- **Day summary & reputation** — end-of-day breakdown of revenue, complaints, and star reputation, with autosave via `localStorage` so you can pick up where you left off.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
