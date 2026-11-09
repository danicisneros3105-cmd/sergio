/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
  readonly VITE_DEMO?: string;
  readonly VITE_LEGAL_OPERATOR?: string;
  readonly VITE_LEGAL_CONTACT?: string;
  readonly VITE_LEGAL_JURISDICTION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Resolved by vite.config.ts: the demo's in-browser server, or nothing.
declare module 'sergio-demo';
