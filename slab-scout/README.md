# Slab Scout

Scan any trading card with your phone camera, and it will:

- **Identify the card and its exact rarity.** Pokémon, Yu-Gi-Oh!, Magic and Lorcana are matched against free databases that list every card. Sports and non-sport cards (Topps, Panini, Upper Deck, Kakawow, Wild Card, history sets, music sets…) are read from the card and matched against a **community catalog that learns from every confirmed scan**.
- **Check authenticity.** It compares your card's artwork to the official image, flags cards the community reported as fake, and (with the AI boost) inspects fonts, symbols, holo pattern and card stock. It never refuses a card: fakes, customs and proxies still get scanned and graded, just flagged.
- **Estimate a PSA grade and a TAG-style score.** Centering is measured from the photo against PSA's published limits. Corners, edges and surface come from a quick checklist, or from the AI.
- **Value it.** Raw market prices come from TCGplayer/Cardmarket data in the free databases. Graded and sports prices come from sales the community adds, plus one-tap eBay sold, 130point, PriceCharting, Google and Google Lens links.
- **Track your collection like a portfolio** (Rare Candy style): total value on the home screen with a daily value chart, most valuable and recently added cards, a wishlist, and a collection grouped by **brand, type, category or most valuable**.
- **Explore every set.** A built-in card database covers 58 niche and sports sets (21,000+ cards, every parallel). Each set page shows a **rarity ladder** (print runs such as 1 of 1, /5 or /25, pull odds and typical sold price per parallel), a full checklist and your completion. Each card page shows raw, PSA 9 and PSA 10 prices, how many copies exist, every version of the card, and recent sales.
- **Accurate identification:** the text on the card is checked against every real card name in the official database, then narrowed by card number, printed set size (006/165), HP, attack names, illustrator and set name. The result shows the real name and rarity (e.g. *Charizard ex · Special Illustration Rare · #199/165 · 151*) plus what it matched on. If it isn't sure, it says so, and you can search by name and number.
- **Automatic condition inspection** (following the published PSA / TAG / CGC rules): zoomed corners and edges, whitening and chipping, scratches, specks and dents, stains, possible creases, fading and photo quality. Includes inverted-colour, black-and-white and contrast-boosted views, a defect map, and an error / misprint check against the official image. The automatic subgrades feed the PSA and TAG estimates, and you can override any of them.
- **Live centering tool:** drag the border lines, or tap the four corners, and the left/right and top/bottom split and PSA cap update as you move.
- **Graded slabs:** scan a PSA, CGC, BGS, TAG or SGC slab to read the company, grade, qualifiers, BGS subgrades and cert number (with a verify-cert link), then identify the card from the label.
- **Card photos** for about 94% of the built-in database.
- **Bulk scan:** turn on *Bulk mode* and scan a stack in a row. Each card adds with one tap.

**It's free.** No API key is needed. An optional free Google Gemini key adds AI identification for any card, an authenticity check and AI grading. Claude, OpenAI or any OpenAI-compatible key also work.

There are two versions. They share the same community catalog and the same vault, so a card you scan on one shows up on the other:

| | Streamlit web app | Phone app (Expo) |
|---|---|---|
| iPhone | ✅ Free: open in Safari and add it to your Home Screen | Expo Go only (no text reading), or $99/yr Apple account for a real install |
| Android | ✅ | ✅ Free installable APK |
| Camera | Safari/Chrome camera or photo upload | Live camera with card guide |
| Card detection | Automatic: finds the card edges and straightens it | Line the card up with the frame, then it trims to the edge |
| Needs a computer | Only once, to put the code on GitHub | Once, to build |

**For iPhone, start with Streamlit.** It's free and nothing needs installing.

---

## Part 1 · Streamlit app (free hosting, works on iPhone)

1. Make a free account at **github.com**, then create a new repository called `slab-scout`.
2. Upload everything inside the `streamlit/` folder to it: `app.py`, `requirements.txt`, and the `core/`, `ui/`, `catalog/` and `.streamlit/` folders. On github.com: **Add file → Upload files**, then drag them in.
3. Go to **share.streamlit.io**, sign in with GitHub, and choose **Create app → Deploy a public app from GitHub**. Pick your repo, set the main file to `app.py`, open **Advanced settings** and choose **Python 3.12** (the text reader does not support 3.13 yet), then tap **Deploy**. The first build takes a few minutes.
4. On your iPhone, open the app link in Safari, then tap **Share → Add to Home Screen**. It now opens like an app.
5. In the app's left menu (the **»** button), set a private **vault code**.

Free Streamlit apps go to sleep when nobody uses them for a while. The first visit after that takes about 30 seconds to wake up.

**Run it on your own computer instead:** `cd streamlit`, then `pip install -r requirements.txt`, then `streamlit run app.py`.

## Part 2 · Community catalog & synced vault (free Supabase, optional but recommended)

Without this, each app keeps its own catalog and vault. On free Streamlit hosting, that data resets whenever the app restarts. With it, every scan by anyone makes the app smarter, and your vault syncs between the phone app and Streamlit.

1. Make a free account at **supabase.com**, then create a **New project** (any name and password).
2. Open **SQL Editor**, paste the whole of `supabase/schema.sql`, and tap **Run**.
3. Open **Project Settings → API** and copy the **Project URL** and the **anon public** key.
4. **Streamlit:** on share.streamlit.io, open your app's **Settings → Secrets** and paste:
   ```
   SUPABASE_URL = "https://xxxx.supabase.co"
   SUPABASE_ANON_KEY = "eyJ..."
   ```
5. **Phone app:** paste the same two values in **Settings → Vault & community**, or put them in `app/app.json` under `extra` before building, so everyone who installs your build is connected.

What's shared: card details, a small thumbnail, the image fingerprint, fake reports and sales people add. Your **vault** is private to your vault code. Anyone who knows the code can see and edit that vault, so pick something hard to guess.

## Part 3 · Free AI boost (optional)

1. Go to **aistudio.google.com/apikey**, sign in with Google, and choose **Create API key**. No credit card is needed.
2. **Streamlit:** in the left menu, set **AI boost → Google Gemini (free key)** and paste the key. To avoid pasting it every visit, add `GEMINI_API_KEY = "..."` to Secrets. Only do this if the app is just for you, because everyone using your app would then use your key.
3. **Phone app:** go to **Settings → AI boost → Google Gemini (free key)**, paste the key, and tap **Test connection**.

Google's free tier has daily limits, and Google may use free-tier requests to improve its products. If you hit the limit, the app keeps working in free mode.

## Part 4 · Phone app (Expo)

You need a computer with **Node.js LTS** (nodejs.org). In the `app` folder, run `npm install`.

- **Try it with Expo Go (iPhone or Android):** install *Expo Go* from the app store, run `npx expo start --tunnel`, and scan the QR code. Everything works except automatic text reading (you type the name and number instead).
- **Install it as a real Android app (free, with text reading):**
  ```
  npx eas-cli@latest login          # free expo.dev account
  npx eas-cli@latest build -p android --profile preview
  ```
  Open the link it gives you on your phone and install the APK.
- **iPhone real install:** `npx eas-cli@latest build -p ios --profile preview` needs an Apple Developer account ($99/year). Without one, use the Streamlit app or Expo Go.

---

## The card database (and how to refresh prices)

`data/catalog/` holds the built database (a copy sits in `streamlit/catalog/` so the web app can find it). It covers:

- **Kakawow:** Cosmos Disney (and Chill), Phantom Disney, Chinese Zodiac, Signature, Stained Glass, Aura Harry Potter, Marvel Phantom and Cosmos.
- **Upper Deck:** 2025-26 Series 1 and 2, Dazzlers, UD Canvas.
- **Wild Card:** 13 sets.
- **Keepsake:** Michael Jackson Bad World Tour.
- **Historic Autographs:** 1963 Moments That Became History (official checklist: 495 cards with print runs and box odds).

Prices are **sold-listing** prices from PriceCharting and SportsCardsPro, plus eBay sold medians for each parallel. When a card has no sale of its own yet, the app shows the typical sold price for its parallel with a `~`. Where no sales exist, it shows Google AI price ranges, labelled **(est.)**.

To refresh:
1. Save new exports into `data/raw/` (`slabscout-pricecharting*.json`, `slabscout-sportscardspro*.json`, `slabscout-ebay-sold.json`) and checklists into `data/checklists/`.
2. Run `python data/build_catalog.py`.
3. Copy `data/catalog` to `streamlit/catalog` and to `app/assets/catalog`, then rebuild the phone app.

Pokémon, Yu-Gi-Oh!, Magic and Lorcana don't need this, because they're looked up live in their free databases.

If you set up Supabase before this version, run `supabase/schema.sql` again. It adds the `vault_history` table the value chart uses, and it's safe to re-run.

## How it works

1. **Find and straighten the card.** Streamlit uses OpenCV edge detection with a perspective warp. The phone app crops the camera frame, then trims to the card's edge.
2. **Read the text** on the device (RapidOCR in Streamlit, Apple Vision / Google ML Kit on the phone): name or player, card number such as `199/165` or `LOB-EN005`, year, brand, serial numbering such as `12/50`.
3. **Fingerprint the image** with a perceptual hash. Both apps produce identical fingerprints, so one catalog serves both.
4. **Match it:**
   - **Community catalog:** instant recognition of any card someone has confirmed before, sports and niche sets included.
   - **Free databases:** TCGdex (Pokémon), YGOPRODeck (Yu-Gi-Oh!), Scryfall (Magic), Lorcast (Lorcana). These give the official rarity, set, number and market price. The app downloads the official image and compares artwork, which picks the right printing and flags art that doesn't match.
   - **AI boost** (optional): identifies anything from the photo, including rarity evidence and parallels.
5. **Grade:** centering is measured against PSA limits (10 = 55/45 front and 75/25 back; 9 = 60/40 and 90/10; …). The checklist or the AI covers corners, edges and surface. The TAG-style score uses approximate bands, not TAG's official conversion.
6. **Value:** the database market price for raw cards, the median of community sales for your estimated grade, and sold-listing links.
7. **Learn:** *Confirm for community* teaches the catalog, *Report as fake* flags look-alikes, and *Add a sale* improves prices for everyone.

## Limits

- **Grades are estimates.** PSA and TAG grade under magnification and controlled light, and phone photos hide fine scratches. Use the grade to decide what's worth submitting.
- **Sports and non-sport sets outside the built-in database** rely on text reading, community confirmations and the AI boost until someone adds them. Sets inside it are recognised from the card code (for example `CDT-BBG-199`), which pins the exact parallel.
- **Card photos:** the built-in database has no images yet, so tiles show your own scan photo (or the card name).
- **One Piece** has no reliable free database yet, so it works like sports cards (community plus AI).
- **Graded prices** come only from sales people add, since no free source provides them. The sold-listing links always work.
- **Google Lens** has no API. The Lens button opens Lens on the official card image when one is available. You can also share your own photo to the Google app.

## Files

```
streamlit/              web app (Python)
  app.py                navigation: Portfolio, Scan, Explore, Collection, Wishlist
  ui/*.py               the pages (home, scan, explore + set page, card page, collection)
  core/catalog.py       built-in card database: search, card codes, parallels, odds
  catalog/              the database files (copy of data/catalog)
  core/vision.py        card detection, straightening, centering, fingerprints
  core/ocr.py           on-device text reading + parsing
  core/databases.py     TCGdex, YGOPRODeck, Scryfall, Lorcast + sold links
  core/grading.py       PSA centering limits, checklist grade, TAG-style score
  core/ai.py            optional AI boost (Gemini free, Claude, OpenAI, compatible)
  core/community.py     Supabase catalog, sales and vault (SQLite fallback)
  core/pipeline.py      matching + authenticity signals
data/build_catalog.py   builds the card database from data/raw + data/checklists
supabase/schema.sql     community database (paste into Supabase SQL editor)
app/                    phone app (Expo / React Native, TypeScript)
  App.tsx               tabs: Portfolio, Scan, Explore, Collection, More (Settings + Community)
  assets/catalog/       the card database (copy of data/catalog; re-copy after rebuilding it)
  src/core/catalog.ts   card database: search, card codes, parallels, odds, sold listings
  src/core/*            same logic as the Python core, ported
  src/screens/*         Home (portfolio), Scan (bulk mode), Explore, Set, Card, Collection/Wishlist, Settings
```
