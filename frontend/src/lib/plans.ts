// Plans, account, billing and usage: the shapes of GET /v1/plans and
// /v1/plans/me, and the visitor's country (for the price in their currency).

export interface PlanPrice {
  usd: number;
  currency: string;
  amount: number;
  text: string;
}

export interface Plan {
  id: 'free' | 'go' | 'work' | 'dev' | 'founders';
  name: string;
  tagline: string;
  includes: string[];
  usd: number;
  mult: number;
  price: PlanPrice;
  can_pay: boolean;
  stretch?: { mult_min: number; mult_max: number; usd_min: number; usd_max: number; from: string; to: string };
}

export interface Catalog {
  country: string;
  country_name: string;
  currency: string;
  rates_date: string;
  rates_live: boolean;
  countries: Array<{ code: string; name: string }>;
  plans: Plan[];
}

export interface Account {
  plan: Plan['id'];
  plan_name: string;
  holder: string;
  seats: number;
  expires: number | null;
  expires_text: string;
  mult: number;
  problem: string;
  features: Array<{ id: string; label: string; on: boolean; plan: string; soon?: boolean }>;
}

export interface Me {
  account: Account;
  usage: {
    multiplier: number;
    blocking: boolean;
    items: Array<{ kind: string; label: string; used: number; limit: number }>;
  };
  billing: { portal: string; payments_on: boolean; invoices: Array<{ date: string; text: string; url?: string }> };
  support: string;
}

const KEY = 'sergio.country';

/** The country for prices: the one the owner chose, else the browser's region, else Ecuador. */
export function detectCountry(): string {
  try {
    const saved = (localStorage.getItem(KEY) || '').toUpperCase();
    if (/^[A-Z]{2}$/.test(saved)) return saved;
  } catch {
    // private window
  }
  const langs = typeof navigator !== 'undefined' ? [...(navigator.languages || []), navigator.language] : [];
  for (const tag of langs) {
    const region = /[-_]([A-Za-z]{2})\b/.exec(tag || '')?.[1];
    if (region) return region.toUpperCase();
  }
  return 'EC';
}

export function saveCountry(code: string): void {
  try {
    localStorage.setItem(KEY, code.toUpperCase());
  } catch {
    // private window: lasts this visit
  }
}

export function percent(used: number, limit: number): number {
  return limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
}

/** How much of today's limit is used, 0-100 (rounded, never above 100). */
export function percentUsed(item: { used: number; limit: number }): number {
  if (!item.limit) return 0;
  return Math.min(100, Math.round((item.used / item.limit) * 100));
}

/** The fullest one decides: «12 %» means nothing is closer than that to its limit. */
export function overallPercent(items: Array<{ used: number; limit: number }>): number {
  return items.reduce((top, item) => Math.max(top, percentUsed(item)), 0);
}
