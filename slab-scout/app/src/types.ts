export type ProviderId = 'anthropic' | 'openai' | 'gemini' | 'compatible';

export interface Settings {
  /** 'off' = fully free mode (no AI). */
  provider: ProviderId | 'off';
  models: Record<ProviderId, string>;
  compatibleBaseUrl: string;
  /** Shared community catalog + vault (free Supabase project). Empty = this phone only. */
  supabaseUrl: string;
  supabaseKey: string;
  /** Private vault code; the same code shows the same vault in the Streamlit app. */
  vaultCode: string;
  /** Which price the lists show: raw (ungraded), PSA 9, or PSA 10 Gem Mint. */
  priceMode?: 'raw' | 'psa9' | 'psa10';
  /** Scan server address (free Streamlit app running the web app's engine (streamlit/api_app.py)); empty = phone only. */
  scanServer?: string;
  /** The grading company the grade estimate is shown for first (each company has its own rules). */
  gradingCompany?: 'PSA' | 'BGS' | 'CGC' | 'SGC' | 'TAG' | 'ACE';
  /** see-through outline in the grading camera showing where to put the card (default on) */
  positionGuide?: boolean;
}
