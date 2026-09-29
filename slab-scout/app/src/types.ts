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
}
