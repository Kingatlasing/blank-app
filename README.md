# Slab Scout · phone app on Streamlit (test branch)

This branch only hosts the **phone app** (built with Expo, from the `slab-scout` branch, folder `slab-scout/app`)
as a web page on Streamlit Community Cloud, so it can be tried in a browser. Nothing here changes the
`slab-scout` branch, the Streamlit web app or Expo Go.

- `static/` – the phone app exported for the web (`npx expo export --platform web` with `experiments.baseUrl` = `/app/static`)
- `streamlit_app.py` – shows the app (and a link to open it full screen at `/app/static/index.html`)
- Same data as the other apps: card catalog from the `catalog-data` branch; the shared community catalog / vault
  when the same Supabase settings are entered in the app's Settings.

Deploy: share.streamlit.io → Create app → repo `Kingatlasing/blank-app`, branch `mobile-web`, main file `streamlit_app.py`.
