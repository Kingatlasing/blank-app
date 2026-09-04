# 🐎 Westward: The Trail

A from-scratch reimagining of the Oregon Trail genre with two full campaigns in one game: the classic 1848 pioneer journey, and **Trail of the Dead**, a zombie-outbreak version of the same 2,000-mile route where you're racing west toward the last safe ground instead of a new homestead.

This is a self-contained HTML/CSS/JS game (`app/index.html`, DOM- and canvas-rendered, with procedural + CC0 Web Audio sound effects) rendered full-screen through a thin Streamlit wrapper (`streamlit_app.py`). All character, animal, weapon, and scenery art is real, downloaded CC0-licensed assets (Kenney.nl and OpenGameArt.org contributors, sourced via their public CC0 GitHub mirrors) — see `CREDITS.md` for the full list. Everything is embedded as base64 image/audio data, so the whole game ships as one file with no runtime network requests for art or sound.

### Two campaigns
Pick **Oregon Trail** (1848 pioneers) or **Trail of the Dead** (zombie outbreak survivors), each with its own palette, HUD labels, professions/roles, story text, and random-event pool. Three difficulty settings per campaign (Easy/Medium/Hard) affect food consumption, event frequency, prices, and starting resources.

### The trail
- **Party setup** — name your three travelers, pick their look, and choose a starting background (Banker/Carpenter/Farmer, or Ex-Soldier/Mechanic/Field Medic in zombie mode) that sets your starting funds and skills.
- **Pre-trip outfitting shop** — spend your starting funds on food/ammo/medical supplies/spare parts before you set out, on top of a small starting stockpile.
- **Trail map hub** — a real map of the historical Oregon Trail landmarks (Independence → Kansas River → Fort Kearney → Chimney Rock → Fort Laramie → South Pass → Fort Bridger → Soda Springs → Fort Hall → Snake River → Blue Mountains → The Dalles → Willamette Valley), reskinned for the zombie campaign, with your party's position — and lead traveler's walking animation — tracked live.
- **Travel simulation** — choose pace and rations each leg, watch food and party health drift accordingly, and hit a pool of mode-specific random events (bandits/raiders, river crossings, sickness/infection, wagon breakdowns, trading encounters, a gunslinger's challenge) with real branching choices and consequences.
- **Town hub & General Store** — arrive at a landmark town, rest to heal up, or buy more supplies.
- **Party roster & health tracking** — per-member health bars, sickness/infection status, and permadeath. Win by reaching the end of the trail; lose your whole party and the journey ends.

### Minigames & side activities
- **Hunting** — a real canvas shooting session: animals (buffalo, bear, moose, goat, rabbit, duck, chicken) cross the field on a timer, click to fire using your actual ammo supply, downed animals add to your real food stock. In zombie mode, infected occasionally shamble through too — shoot them for a bonus, or take a small health hit if one reaches the far edge.
- **Shooting Range** — a carnival-style target range at every town, built from a real shooting-gallery CC0 kit (wooden stall backdrop, curtains, clouds, targets, ducks). Costs real ammo to play, pays out real cash based on score.
- **Fishing** — a reflex minigame using a real fish sprite set: cast a line, wait for the bobber to dip, and click fast before the fish gets away. No ammo cost, available both on the open trail and at towns.
- **Trapping** — a lighter, passive activity: stake out a line of traps (costs a spare part, camps overnight) and check them the next morning for a random yield of food, occasionally a pelt worth cash.
- **Raft River-Run** — near the end of the trail (the Columbia River / The Dalles), a side-view dodge minigame: steer a real canoe sprite with your mouse past rocks and floating logs. Take three hits and the raft breaks apart — the rest of the journey continues on foot (slower pace, and you lose some food in the wreck). A clean run gains extra miles.
- **Dueling Standoff** — a quick-draw reaction minigame that can trigger as a random encounter: a gunslinger (or, in zombie mode, a raider) challenges you. Talk your way out, walk away, or accept — wait for the "DRAW!" signal and click as fast as you can. React before the signal and you lose your nerve; react slower than your opponent and you lose. Winning pays out real cash; losing ends the journey — real risk for real stakes.
- **The Saloon** — a full casino at every town: Coin Flip, Roulette (real American double-zero wheel with straight/dozen/column/outside bets), Blackjack (3:2 blackjack payout, dealer stands on 17), Baccarat (Player/Banker/Tie with proper third-card drawing rules), and Shell Game. Ported and re-themed from this repo's own `claude/courtside-card-pack-mock-app-99fqki` branch (ChaseBreak) — real rules and payouts kept faithful, visuals rebuilt in this game's own art style. Wagers real in-game money.

### A bug worth mentioning
While building the raft sequence, testing surfaced a real bug: landmarks were only recognized by landing within 1 mile of their exact position, but a travel day covers 12–30 miles — so in normal play, most landmarks (and the raft trigger) would silently get skipped rather than reliably stopping the party there. Travel now clamps to the next landmark/trigger's exact mile instead of freely adding the day's full distance, so arrivals are always hit exactly. Caught by writing an automated playthrough that actually walked the trail instead of teleporting to test positions.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
