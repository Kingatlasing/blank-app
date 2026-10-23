# Slab Scout scan service on a free Hugging Face Space (Docker).
# The code comes from GitHub (Kingatlasing/blank-app, branch slab-scout) and is refreshed every time the Space
# restarts, so "Restart this Space" picks up the latest scanning code. Card data downloads on first use.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 \
    REPO=https://github.com/Kingatlasing/blank-app.git BRANCH=slab-scout
WORKDIR /home/user

# only the scanning engine + the card index (about 55 MB), not the phone app or the raw price files
RUN git clone --depth 1 --filter=blob:none --sparse --branch $BRANCH $REPO repo \
    && git -C repo sparse-checkout set slab-scout/streamlit slab-scout/data/catalog
RUN pip install --no-cache-dir --user -r repo/slab-scout/streamlit/requirements.txt \
    && pip install --no-cache-dir --user fastapi "uvicorn[standard]" python-multipart

EXPOSE 7860
CMD git -C repo pull --depth 1 -q origin $BRANCH || true; \
    pip install --no-cache-dir --user -q -r repo/slab-scout/streamlit/requirements.txt || true; \
    cd repo/slab-scout/streamlit && exec uvicorn service:app --host 0.0.0.0 --port 7860
