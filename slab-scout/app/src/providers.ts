/**
 * One function that talks to whichever AI provider the user picked.
 * Every provider gets the same prompt + photos and returns plain text
 * (plus any web sources it used). The app parses JSON out of that text.
 */
import type { ProviderId, Settings } from './types';

export interface ProviderInfo {
  id: ProviderId;
  name: string;
  defaultModel: string;
  keyHint: string;
  keyUrl: string;
  searchNote: string;
}

export const PROVIDERS: ProviderInfo[] = [
  {
    id: 'anthropic',
    name: 'Claude (Anthropic)',
    defaultModel: 'claude-sonnet-5',
    keyHint: 'sk-ant-…',
    keyUrl: 'https://console.anthropic.com/settings/keys',
    searchNote: 'Uses Claude web search for sold listings (turn it on in the Anthropic Console if prices fail).',
  },
  {
    id: 'openai',
    name: 'OpenAI (ChatGPT)',
    defaultModel: 'gpt-5.5',
    keyHint: 'sk-…',
    keyUrl: 'https://platform.openai.com/api-keys',
    searchNote: 'Uses OpenAI web search for sold listings.',
  },
  {
    id: 'gemini',
    name: 'Google Gemini (free key)',
    defaultModel: 'gemini-3.8-flash',
    keyHint: 'AIza…',
    keyUrl: 'https://aistudio.google.com/apikey',
    searchNote: 'Free tier: no credit card. Google may use free-tier requests to improve its products.',
  },
  {
    id: 'compatible',
    name: 'Other (OpenAI-compatible)',
    defaultModel: '',
    keyHint: 'your key',
    keyUrl: 'https://openrouter.ai/keys',
    searchNote: 'No built-in web search. On OpenRouter, add ":online" to the model name to enable it.',
  },
];

export const providerInfo = (id: ProviderId) => PROVIDERS.find((p) => p.id === id)!;
// Show the free option first.
PROVIDERS.sort((a, b) => (a.id === 'gemini' ? -1 : b.id === 'gemini' ? 1 : 0));

export interface CallInput {
  prompt: string;
  imagesBase64?: string[]; // JPEG, no data: prefix
  webSearch?: boolean;
  maxTokens?: number;
  signal?: AbortSignal;
}

export interface CallOutput {
  text: string;
  sources: { title: string; url: string }[];
  searched: boolean;
}

export class ProviderError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

function friendlyError(provider: string, status: number, body: string): ProviderError {
  let detail = '';
  try {
    const j = JSON.parse(body);
    detail = j?.error?.message || j?.message || '';
  } catch {
    detail = body.slice(0, 200);
  }
  const map: Record<number, string> = {
    400: `${provider} rejected the request.`,
    401: `${provider} says the API key is invalid. Check it in Settings.`,
    403: `${provider} says this key isn't allowed to do that.`,
    404: `${provider} doesn't recognize that model name. Check it in Settings.`,
    429: `${provider} rate limit or credit limit reached. Wait a minute or add credit.`,
  };
  const head = map[status] || (status >= 500 ? `${provider} is having problems right now. Try again shortly.` : `${provider} returned an error (${status}).`);
  return new ProviderError(detail ? `${head}\n\n${detail}` : head, status);
}

async function post(provider: string, url: string, headers: Record<string, string>, body: unknown, signal?: AbortSignal) {
  let res: Response;
  try {
    res = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: JSON.stringify(body), signal });
  } catch (e: any) {
    if (e?.name === 'AbortError') throw e;
    throw new ProviderError(`Couldn't reach ${provider}. Check your internet connection.`);
  }
  const text = await res.text();
  if (!res.ok) throw friendlyError(provider, res.status, text);
  try {
    return JSON.parse(text);
  } catch {
    throw new ProviderError(`${provider} sent back something unreadable.`);
  }
}

/* ---------------- Anthropic ---------------- */
async function callAnthropic(key: string, model: string, input: CallInput): Promise<CallOutput> {
  const content: any[] = (input.imagesBase64 || []).map((data) => ({
    type: 'image',
    source: { type: 'base64', media_type: 'image/jpeg', data },
  }));
  content.push({ type: 'text', text: input.prompt });
  const messages: any[] = [{ role: 'user', content }];
  const tools = input.webSearch ? [{ type: 'web_search_20250305', name: 'web_search', max_uses: 6 }] : undefined;

  let texts: string[] = [];
  const sources: { title: string; url: string }[] = [];
  let searched = false;
  // pause_turn: a long search turn is paused; send it back unchanged to continue.
  for (let round = 0; round < 4; round++) {
    const data = await post(
      'Claude',
      'https://api.anthropic.com/v1/messages',
      { 'x-api-key': key, 'anthropic-version': '2023-06-01' },
      { model, max_tokens: input.maxTokens ?? 8000, messages, ...(tools ? { tools } : {}) },
      input.signal,
    );
    for (const block of data.content || []) {
      if (block.type === 'text') {
        texts.push(block.text);
        for (const c of block.citations || []) if (c.url) sources.push({ title: c.title || c.url, url: c.url });
      }
      if (block.type === 'server_tool_use') searched = true;
      if (block.type === 'web_search_tool_result' && Array.isArray(block.content)) {
        for (const r of block.content) if (r.url) sources.push({ title: r.title || r.url, url: r.url });
      }
    }
    if (data.stop_reason !== 'pause_turn') break;
    messages.push({ role: 'assistant', content: data.content });
    texts = [];
  }
  return { text: texts.join(''), sources, searched };
}

/* ---------------- OpenAI (Responses API) ---------------- */
async function callOpenAI(key: string, model: string, input: CallInput): Promise<CallOutput> {
  const content: any[] = [{ type: 'input_text', text: input.prompt }];
  for (const b64 of input.imagesBase64 || []) content.push({ type: 'input_image', image_url: `data:image/jpeg;base64,${b64}`, detail: 'high' });
  const data = await post(
    'OpenAI',
    'https://api.openai.com/v1/responses',
    { authorization: `Bearer ${key}` },
    {
      model,
      input: [{ role: 'user', content }],
      max_output_tokens: input.maxTokens ?? 8000,
      ...(input.webSearch ? { tools: [{ type: 'web_search' }] } : {}),
    },
    input.signal,
  );
  const texts: string[] = [];
  const sources: { title: string; url: string }[] = [];
  let searched = false;
  for (const item of data.output || []) {
    if (item.type === 'web_search_call') searched = true;
    if (item.type === 'message') {
      for (const c of item.content || []) {
        if (c.type === 'output_text') {
          texts.push(c.text);
          for (const a of c.annotations || []) if (a.url) sources.push({ title: a.title || a.url, url: a.url });
        }
      }
    }
  }
  return { text: texts.join('') || data.output_text || '', sources, searched };
}

/* ---------------- Google Gemini ---------------- */
async function callGemini(key: string, model: string, input: CallInput): Promise<CallOutput> {
  const parts: any[] = (input.imagesBase64 || []).map((data) => ({ inline_data: { mime_type: 'image/jpeg', data } }));
  parts.push({ text: input.prompt });
  const data = await post(
    'Gemini',
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,
    { 'x-goog-api-key': key },
    {
      contents: [{ role: 'user', parts }],
      generationConfig: { maxOutputTokens: input.maxTokens ?? 8000 },
      ...(input.webSearch ? { tools: [{ google_search: {} }] } : {}),
    },
    input.signal,
  );
  const cand = data.candidates?.[0];
  const text = (cand?.content?.parts || []).map((p: any) => p.text || '').join('');
  const chunks = cand?.groundingMetadata?.groundingChunks || [];
  const sources = chunks.filter((c: any) => c.web?.uri).map((c: any) => ({ title: c.web.title || c.web.uri, url: c.web.uri }));
  return { text, sources, searched: !!cand?.groundingMetadata };
}

/* ---------------- Any OpenAI-compatible service ---------------- */
async function callCompatible(key: string, model: string, baseUrl: string, input: CallInput): Promise<CallOutput> {
  const content: any[] = [{ type: 'text', text: input.prompt }];
  for (const b64 of input.imagesBase64 || []) content.push({ type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } });
  const url = baseUrl.replace(/\/+$/, '') + '/chat/completions';
  const data = await post('Your provider', url, { authorization: `Bearer ${key}` }, { model, max_tokens: input.maxTokens ?? 8000, messages: [{ role: 'user', content }] }, input.signal);
  const msg = data.choices?.[0]?.message;
  const text = typeof msg?.content === 'string' ? msg.content : (msg?.content || []).map((c: any) => c.text || '').join('');
  const sources = (msg?.annotations || []).filter((a: any) => a.url_citation?.url).map((a: any) => ({ title: a.url_citation.title || a.url_citation.url, url: a.url_citation.url }));
  return { text, sources, searched: sources.length > 0 };
}

export async function callModel(settings: Settings, apiKey: string, input: CallInput): Promise<CallOutput> {
  if (settings.provider === 'off') throw new ProviderError('AI boost is off. Turn it on in Settings.');
  if (!apiKey) throw new ProviderError('Add your API key in Settings first.');
  const model = settings.models[settings.provider] || providerInfo(settings.provider).defaultModel;
  if (!model) throw new ProviderError('Enter a model name in Settings.');
  switch (settings.provider) {
    case 'anthropic':
      return callAnthropic(apiKey, model, input);
    case 'openai':
      return callOpenAI(apiKey, model, input);
    case 'gemini':
      return callGemini(apiKey, model, input);
    case 'compatible':
      if (!settings.compatibleBaseUrl) throw new ProviderError('Enter the base URL for your provider in Settings.');
      return callCompatible(apiKey, model, settings.compatibleBaseUrl, { ...input, webSearch: false });
  }
}

/** Pull one JSON object out of a model reply (handles ``` fences and chatter around it). */
export function extractJson<T = any>(text: string): T {
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidates = [fence?.[1], text];
  for (const c of candidates) {
    if (!c) continue;
    const start = c.indexOf('{');
    const end = c.lastIndexOf('}');
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(c.slice(start, end + 1));
      } catch {}
    }
  }
  throw new ProviderError("The AI's answer wasn't in the expected format. Try again, or try a stronger model in Settings.");
}
