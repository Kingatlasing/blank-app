# 🃏 Slab Scout

Scan a trading card with your phone camera to identify it, estimate its grade and see what it's worth, then track your collection like a portfolio. Pokémon, Yu-Gi-Oh!, Magic, Lorcana, sports and non-sport cards.

The app lives in [`slab-scout/`](slab-scout/README.md): a Streamlit web app (`slab-scout/streamlit`), an Expo phone app (`slab-scout/app`) and the card database builders (`slab-scout/data`). The full guide, including the free community catalog and AI boost setup, is in [slab-scout/README.md](slab-scout/README.md).

### Run it

- **Free hosting:** on [share.streamlit.io](https://share.streamlit.io), deploy this repo with branch `main` and main file `streamlit_app.py`. Any Python version works.
- **On your own computer:**

  ```
  $ pip install -r requirements.txt
  $ streamlit run streamlit_app.py
  ```

The old Lemonade Stand Tycoon game is still in `app/index.html`.
