/** Optional AI boost (identify any card from photos, authenticity check, grade). Uses providers.ts. */
import { callModel, extractJson } from '../providers';
import type { Settings } from '../types';

const SHAPE = `{
 "card": {"game": "Pokémon | Yu-Gi-Oh! | Magic: The Gathering | Lorcana | One Piece | Baseball | Basketball | Football | Soccer | Hockey | Non-sport | Other TCG", "name": "", "set": "", "year": "", "number": "", "brand": "manufacturer e.g. Topps, Panini, Upper Deck, Kakawow, Wild Card, The Pokémon Company, Konami", "rarity": "exact official rarity or parallel", "rarity_evidence": "", "variant": "", "card_type": "Base | Holo | Reverse Holo | Full Art | Secret Rare | Rookie | Parallel | Insert | Autograph | Relic | Promo | Custom | Other", "language": "", "confidence": 0.0, "alternatives": []},
 "authenticity": {"verdict": "looks_genuine | unsure | likely_fake | custom_or_proxy", "reasons": []},
 "condition": {"centering": {"front": "", "back": "", "score": 0}, "corners": {"score": 0, "notes": ""}, "edges": {"score": 0, "notes": ""}, "surface": {"score": 0, "notes": ""}, "defects": [], "photo_limits": ""},
 "psa": {"grade": 0, "label": "", "range": "", "reasoning": ""},
 "tag": {"score": 0, "grade": "", "label": "", "reasoning": ""}
}`;

export async function analyzeWithAI(settings: Settings, key: string, frontB64: string, backB64: string | null, ocrText: string, dbHint: string, signal?: AbortSignal) {
  const prompt = `You are an expert trading card identifier, authenticator and grader who knows PSA's grading standards and TAG Grading's 1000-point scoring.
Image 1 is the FRONT of one card.${backB64 ? ' Image 2 is the BACK.' : ' There is no back photo; widen the grade range.'}
${ocrText ? `Text read from the card (may contain errors): ${ocrText.slice(0, 800)}` : ''}
${dbHint ? `Possible database matches: ${dbHint.slice(0, 1500)}` : ''}

Always analyze the card, even if it looks fake, custom, a proxy, damaged or unknown. Never refuse.
1. Identify the exact card, set, year, number, brand and exact official rarity or parallel (rarity symbols, set number vs total, foil pattern, serial numbering, stamps). Confidence 0-1, alternatives if unsure.
2. Authenticity: compare with how genuine cards of this set look (font, alignment, symbols, colour saturation, holo pattern, card back, borders, copyright line, stock). Verdict + specific reasons.
3. Condition: centering ratios, scores 1-10 for centering, corners, edges, surface; every visible defect.
4. PSA grade (1-10, half grades allowed) with range, and TAG 1000-point score with grade and label.
Reply with ONLY this JSON (numbers as numbers):
${SHAPE}`;
  const out = await callModel(settings, key, { prompt, imagesBase64: backB64 ? [frontB64, backB64] : [frontB64], signal });
  return extractJson<any>(out.text);
}
