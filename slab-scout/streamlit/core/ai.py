"""Optional AI boost: any provider, including Google Gemini's free tier.

The app works without this. With a key, the AI reads the card photos, identifies
the card, checks authenticity and grades condition.
"""
from __future__ import annotations

import json
import re

import requests

PROVIDERS = {
    "Off (free, no key)": None,
    "Google Gemini (free key)": {"id": "gemini", "model": "gemini-3.8-flash", "key_url": "https://aistudio.google.com/apikey"},
    "Claude (Anthropic)": {"id": "anthropic", "model": "claude-sonnet-5", "key_url": "https://console.anthropic.com/settings/keys"},
    "OpenAI": {"id": "openai", "model": "gpt-5.5", "key_url": "https://platform.openai.com/api-keys"},
    "Other (OpenAI-compatible)": {"id": "compatible", "model": "", "key_url": "https://openrouter.ai/keys"},
}

SHAPE = """{
 "card": {"game": "Pokémon | Yu-Gi-Oh! | Magic: The Gathering | Lorcana | One Piece | Baseball | Basketball | Football | Soccer | Hockey | Non-sport | Other TCG", "name": "", "set": "", "year": "", "number": "", "brand": "manufacturer e.g. Topps, Panini, Upper Deck, Kakawow, Wild Card, The Pokémon Company, Konami", "rarity": "exact official rarity or parallel e.g. Special Illustration Rare, Gold Refractor /50", "rarity_evidence": "", "variant": "", "card_type": "Base | Holo | Reverse Holo | Full Art | Secret Rare | Rookie | Parallel | Insert | Autograph | Relic | Promo | Custom | Other", "language": "", "confidence": 0.0, "alternatives": []},
 "authenticity": {"verdict": "looks_genuine | unsure | likely_fake | custom_or_proxy", "reasons": ["specific observations"]},
 "condition": {"centering": {"front": "55/45 L/R, 52/48 T/B", "back": "", "score": 0}, "corners": {"score": 0, "notes": ""}, "edges": {"score": 0, "notes": ""}, "surface": {"score": 0, "notes": ""}, "defects": [], "photo_limits": ""},
 "psa": {"grade": 0, "label": "", "range": "", "reasoning": ""},
 "tag": {"score": 0, "grade": "", "label": "", "reasoning": ""}
}"""


def grade_prompt(hint: str, has_back: bool, ocr_text: str, db_hint: str) -> str:
    return f"""You are an expert trading card identifier, authenticator and grader who knows PSA's grading standards and TAG Grading's 1000-point scoring.
Image 1 is the FRONT of one card.{' Image 2 is the BACK.' if has_back else ' There is no back photo; widen the grade range.'}
{f'Owner note: "{hint[:300]}"' if hint else ''}
{f'Text read from the card by OCR (may contain errors): {ocr_text[:800]}' if ocr_text else ''}
{f'Possible database matches: {db_hint[:1500]}' if db_hint else ''}

Always analyze the card, even if it looks fake, custom, a proxy, damaged or unknown. Never refuse.
1. Identify the exact card, set, year, number, brand and the exact official rarity or parallel (read rarity symbols, set number vs total, foil pattern, serial numbering, stamps). Give confidence 0-1 and alternatives if unsure.
2. Authenticity: compare against how genuine cards of this set look (font, text alignment, energy/attribute symbols, colour saturation, holo pattern, card-back print, border widths, copyright line, card stock sheen). Give a verdict and the specific reasons.
3. Condition: centering ratios front/back, scores 1-10 for centering, corners, edges and surface, and every visible defect.
4. PSA grade (1-10, half grades allowed) with range, and TAG 1000-point score with grade and label.
Reply with ONLY this JSON (numbers as numbers):
{SHAPE}"""


class AIError(Exception):
    pass


def _post(url: str, headers: dict, body: dict) -> dict:
    try:
        r = requests.post(url, headers={"content-type": "application/json", **headers}, data=json.dumps(body), timeout=120)
    except requests.RequestException:
        raise AIError("Couldn't reach the AI provider. Check the connection.")
    if r.status_code != 200:
        msg = ""
        try:
            j = r.json()
            msg = (j.get("error") or {}).get("message") if isinstance(j.get("error"), dict) else j.get("error") or j.get("message") or ""
        except Exception:
            msg = r.text[:200]
        hints = {401: "The API key is invalid.", 403: "This key isn't allowed to do that.", 404: "That model name isn't recognized.", 429: "Rate or free-tier limit reached. Wait a minute and try again."}
        raise AIError(f"{hints.get(r.status_code, f'Provider error {r.status_code}.')} {msg}".strip())
    return r.json()


def call(provider: dict, key: str, model: str, prompt: str, images_b64: list[str], base_url: str = "") -> str:
    pid = provider["id"]
    if pid == "gemini":
        parts = [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in images_b64] + [{"text": prompt}]
        d = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", {"x-goog-api-key": key},
                  {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"maxOutputTokens": 8000}})
        return "".join(p.get("text", "") for p in ((d.get("candidates") or [{}])[0].get("content") or {}).get("parts", []))
    if pid == "anthropic":
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}} for b in images_b64] + [{"type": "text", "text": prompt}]
        d = _post("https://api.anthropic.com/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"},
                  {"model": model, "max_tokens": 8000, "messages": [{"role": "user", "content": content}]})
        return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    if pid == "openai":
        content = [{"type": "input_text", "text": prompt}] + [{"type": "input_image", "image_url": f"data:image/jpeg;base64,{b}", "detail": "high"} for b in images_b64]
        d = _post("https://api.openai.com/v1/responses", {"authorization": f"Bearer {key}"},
                  {"model": model, "input": [{"role": "user", "content": content}], "max_output_tokens": 8000})
        texts = [c.get("text", "") for it in d.get("output", []) if it.get("type") == "message" for c in it.get("content", []) if c.get("type") == "output_text"]
        return "".join(texts) or d.get("output_text", "")
    # OpenAI-compatible
    content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in images_b64]
    d = _post(base_url.rstrip("/") + "/chat/completions", {"authorization": f"Bearer {key}"},
              {"model": model, "max_tokens": 8000, "messages": [{"role": "user", "content": content}]})
    msg = (d.get("choices") or [{}])[0].get("message") or {}
    c = msg.get("content")
    return c if isinstance(c, str) else "".join(x.get("text", "") for x in (c or []))


def extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    for chunk in (m.group(1) if m else None, text):
        if not chunk:
            continue
        a, b = chunk.find("{"), chunk.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(chunk[a:b + 1])
            except json.JSONDecodeError:
                pass
    raise AIError("The AI's answer wasn't in the expected format. Try again.")
