# 🐎 Westward: The Trail

A from-scratch reimagining of the Oregon Trail genre with two full campaigns in one game: the classic 1848 pioneer journey, and **Trail of the Dead**, a zombie-outbreak version of the same 2,000-mile route where you're racing west toward the last safe ground instead of a new homestead.

This is a self-contained HTML/CSS/JS game (`app/index.html`, DOM-rendered with procedural + CC0 Web Audio sound effects) rendered full-screen through a thin Streamlit wrapper (`streamlit_app.py`). All character, animal, weapon, and scenery art is real, downloaded CC0-licensed assets (Kenney.nl and OpenGameArt.org contributors, sourced via their public CC0 GitHub mirrors) — see `CREDITS.md` for the full list. Everything is embedded as base64 image/audio data, so the whole game ships as one file with no runtime network requests for art or sound.

**This is an in-progress build, shipped in playable milestones.** Current status:

### ✅ Built so far
- **Two full campaigns** — pick Oregon Trail (1848 pioneers) or Trail of the Dead (zombie outbreak survivors), each with its own palette, HUD labels, professions/roles, story text, and random-event pool.
- **Three difficulty settings** per campaign (Easy/Medium/Hard), affecting food consumption, event frequency, prices, and starting resources.
- **Party setup** — name your three travelers, pick their look, and choose a starting background (Banker/Carpenter/Farmer, or Ex-Soldier/Mechanic/Field Medic in zombie mode) that sets your starting funds and skills.
- **Trail map hub** — a real map of the historical Oregon Trail landmarks (Independence → Kansas River → Fort Kearney → Chimney Rock → Fort Laramie → South Pass → Fort Bridger → Soda Springs → Fort Hall → Snake River → Blue Mountains → The Dalles → Willamette Valley), reskinned for the zombie campaign, with your party's position tracked live.
- **Travel simulation** — choose pace and rations each leg, watch food and party health drift accordingly, and hit a pool of mode-specific random events (bandits/raiders, river crossings, sickness/infection, wagon breakdowns, trading encounters) with real branching choices and consequences.
- **Pre-trip outfitting shop** — spend your starting funds on food/ammo/medical supplies/spare parts at Independence (or the checkpoint) before you set out, on top of a small starting stockpile.
- **Town hub & General Store** — arrive at a landmark town, rest to heal up, or buy more supplies at the same shop, now mid-trip.
- **Hunting minigame** — a real canvas shooting session: animals (buffalo, bear, moose, goat, rabbit, duck, chicken) cross the field on a timer, click to fire using your actual ammo supply, downed animals add to your real food stock. In zombie mode, infected occasionally shamble through too — shoot them for a bonus, or take a small health hit if one reaches the far edge.
- **Walking animation** — your lead party member's sprite now animates through its walk cycle on the trail map while you're travelling between landmarks (vehicles like the zombie-mode convoy rig stay as their icon).
- **Party roster & health tracking** — per-member health bars, sickness/infection status, and permadeath.
- **Win/lose states** — reach the end of the trail to win, or lose your whole party along the way.

- **Shooting Range** — a carnival-style target range at every town, built from a real shooting-gallery CC0 kit (wooden stall backdrop, curtains, clouds, targets, ducks). Costs real ammo to play, pays out real cash based on score — available at any town alongside the General Store, Camp & Rest, and the (still-placeholder) saloon.
- **Fishing** — a reflex minigame using a real fish sprite set: cast a line, wait for the bobber to dip, and click fast before the fish gets away. No ammo cost, available both on the open trail and at towns — a free (but time-limited) alternative to hunting.
- **Trapping** — a lighter, passive activity: stake out a line of traps (costs a spare part, camps overnight) and check them the next morning for a random yield of food, occasionally a pelt worth cash. Available on the open trail.

### 🚧 Coming in the next milestones
- **A raft river-run** near the end of the trail (Columbia River) — dodge rocks and logs; wreck the raft and you finish the journey on foot.
- **A dueling-pistols standoff** minigame.
- **A saloon/casino** (Roulette, Blackjack, Baccarat, Coin Flip, Shell Game), offered as a side activity at towns and rest stops — ported and re-themed from this repo's own `claude/courtside-card-pack-mock-app-99fqki` branch (ChaseBreak), which already has these games fully built with real casino rules and animations.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
