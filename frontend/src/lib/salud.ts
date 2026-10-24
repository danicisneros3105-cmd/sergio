// Salud: the owner's health data on the Sergio server (/v1/healthdata).
import { apiFetch } from './api';

export type Status = 'ok' | 'low' | 'high' | '';

export interface MetricDef {
  key: string;
  label: string;
  unit: string;
  category: string;
  daily: string;
  better: string;
  low: number | null;
  high: number | null;
  guide: string;
  decimals: number;
}

export interface MetricSummary {
  metric: string;
  label: string;
  unit: string;
  category: string;
  day: string;
  value: number;
  baseline: number | null;
  change_pct: number | null;
  status: Status;
  partial?: boolean;
  goal: number | null;
  spark: Array<[string, number]>;
}

export interface Device {
  id: string;
  name: string;
  ways: Array<'api' | 'push' | 'file'>;
  how: string;
}

export interface Catalog {
  metrics: MetricDef[];
  categories: Array<{ key: string; label: string }>;
  devices: Device[];
}

export interface Readiness {
  score: number | null;
  word?: string;
  inputs: string[];
  missing: string[];
}

export interface Summary {
  metrics: Record<string, MetricSummary>;
  categories: Array<{ key: string; label: string; metrics: MetricSummary[] }>;
  pins: string[];
  highlights: Array<{ metric: string; text: string; good: boolean | null }>;
  readiness: Readiness;
  goals: Record<string, number>;
  sources: Record<string, { count: number; last: number }>;
  connected: string[];
  today: string;
  note: { text: string; tags: string[] };
  empty: boolean;
}

export interface Area {
  key: string;
  label: string;
  state: 'en_rango' | 'atencion' | 'sin_datos';
  checks: Array<{ metric: string; label: string; value: number; unit: string; status: Status; guide: string; days: number }>;
}

export interface MetricDetail {
  metric: MetricDef;
  summary: MetricSummary | null;
  daily: Array<[string, number]>;
  readings: Array<{ uid: string; at: number; value: number; source: string }>;
  goal: number | null;
}

export interface Correlation {
  kind: 'metric' | 'tag';
  metric?: string;
  tag?: string;
  label: string;
  r?: number;
  with?: number;
  without?: number;
  days: number;
}

export interface SyncInfo {
  path: string;
  key: string;
  header: string;
  example: unknown;
  sources: Record<string, { count: number; last: number }>;
  last_push: { at: number; read: number; added: number } | null;
}

export interface SurveyOption {
  value: number;
  label: string;
}

export interface SurveyItem {
  id: string;
  kind: 'picture' | 'choice' | 'open';
  text: string;
  image?: string;
  alt?: string;
  options?: SurveyOption[];
}

export interface SurveySection {
  key: string;
  title: string;
  stem?: string;
  items: SurveyItem[];
}

export interface SurveySource {
  scale: string;
  cite: string;
  url: string;
}

/** The few-question cards (validated scales, one per card). */
export type WidgetKey = 'w_animo' | 'w_nervios' | 'w_bienestar' | 'w_soledad' | 'w_autoestima';
export type SurveyVariant = 'corta' | 'larga' | WidgetKey;

export interface MindWidget {
  key: WidgetKey;
  label: string;
  count: number;
  scale: string;
  cite: string;
  last: SurveyResult | null;
}

export interface SurveyDefinition {
  variant: SurveyVariant;
  label: string;
  minutes: number;
  sections: SurveySection[];
  count: number;
  delay_minutes: number;
  sources: SurveySource[];
  variants: Array<{ key: SurveyVariant; label: string; minutes: number; count: number }>;
}

export interface CreditsInfo {
  scope: string;
  notice: string;
  logos_added_by_owner: boolean;
  studies: Array<{
    topic: string;
    cite: string;
    url: string;
    institutions: Array<{ key: string; name: string; logo: boolean }>;
  }>;
}

export interface ScaleScore {
  key: string;
  label: string;
  score: number | null;
  min: number;
  max: number;
  band: string;
  words: string;
  answered: number;
  items: number;
  higher_is_better: boolean;
  orientative: boolean;
  subscales?: Array<{ key: string; label: string; score: number; min: number; max: number; band: string; words: string; higher_is_better: boolean }>;
}

export interface SurveyResult {
  id: string;
  variant: SurveyVariant;
  created: number;
  ready_at: number;
  status: 'waiting' | 'ready';
  crisis: boolean;
  crisis_text?: string;
  professional: boolean;
  scores?: { scales: ScaleScore[]; pictures: Array<{ id: string; domain: string; value: number | null; label: string }>; crisis: boolean };
  reading?: string;
  reading_by?: 'ia' | 'codigo';
  answers?: Record<string, string>;
  sources?: SurveySource[];
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(String((body as { detail?: string }).detail ?? `Error ${res.status}`));
  return body as T;
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
});

const B = '/v1/healthdata';

export const salud = {
  catalog: () => json<Catalog>(`${B}/catalog`),
  summary: () => json<Summary>(`${B}/summary`),
  longevity: () => json<{ areas: Area[] }>(`${B}/longevity`).then((r) => r.areas),
  metric: (key: string, days = 90) => json<MetricDetail>(`${B}/metric/${key}?days=${days}`),
  add: (metric: string, value: number, at?: string) => json<{ ok: boolean }>(`${B}/samples`, send('POST', { metric, value, at })),
  remove: (uid: string) => json<{ ok: boolean }>(`${B}/samples/${encodeURIComponent(uid)}`, send('DELETE')),
  pins: (pins: string[]) => json<{ pins: string[] }>(`${B}/pins`, send('PUT', { pins })),
  goal: (key: string, value: number | null) => json<{ goals: Record<string, number> }>(`${B}/goals/${key}`, send('PUT', { value })),
  notes: (days = 90) => json<{ notes: Record<string, { text: string; tags: string[] }>; tags: string[] }>(`${B}/notes?days=${days}`),
  note: (day: string, text: string, tags: string[]) => json(`${B}/notes/${day}`, send('PUT', { text, tags })),
  correlations: (target: string) => json<{ target: string; label: string; found: Correlation[]; min_days: number }>(`${B}/correlations?target=${target}`),
  importFile: async (file: File, source = '') => {
    const form = new FormData();
    form.append('file', file, file.name);
    return json<{ ok: boolean; read: number; added: number }>(`${B}/import?source=${encodeURIComponent(source)}`, { method: 'POST', body: form });
  },
  sync: () => json<SyncInfo>(`${B}/sync`),
  rotate: () => json<{ key: string }>(`${B}/sync/rotate`, send('POST', {})),
  deviceKey: (id: string, token: string) => json<{ read: number; added: number }>(`${B}/devices/${id}/key`, send('POST', { token })),
  deviceSync: (id: string) => json<{ read: number; added: number }>(`${B}/devices/${id}/sync`, send('POST', {})),
  deviceForget: (id: string) => json(`${B}/devices/${id}`, send('DELETE')),
  dropSource: (source: string) => json<{ removed: number }>(`${B}/sources/${encodeURIComponent(source)}`, send('DELETE')),
  report: () => json<{ generated: string; rows: Array<{ label: string; unit: string; avg: number; min: number; max: number; days: number; status: Status; guide: string }>; areas: Area[]; notes: Record<string, { text: string; tags: string[] }> }>(`${B}/report`),
  ask: (message: string) => json<{ reply: string }>(`${B}/ask`, send('POST', { message })),
  exportUrl: `${B}/export.csv`,
  survey: (variant: SurveyVariant = 'larga') => json<SurveyDefinition>(`${B}/mind/survey?variant=${variant}`),
  submitSurvey: (answers: Record<string, number | string>, variant: SurveyVariant = 'larga') =>
    json<SurveyResult>(`${B}/mind/surveys`, send('POST', { answers, variant })),
  credits: (scope: 'mente' | 'gimnasio') => json<CreditsInfo>(`${B}/credits?scope=${scope}`),
  /** A logo the owner added with the institution's permission (needs the app's auth, so it is fetched). */
  logo: async (key: string) => {
    const res = await apiFetch(`${B}/instituciones/${encodeURIComponent(key)}/logo`);
    if (!res.ok) throw new Error('sin logo');
    return res.blob();
  },
  surveys: () => json<{ surveys: SurveyResult[] }>(`${B}/mind/surveys`).then((r) => r.surveys),
  widgets: () => json<{ widgets: MindWidget[]; delay_minutes: number }>(`${B}/mind/widgets`),
  surveyResult: (id: string) => json<SurveyResult>(`${B}/mind/surveys/${encodeURIComponent(id)}`),
  dropSurvey: (id: string) => json<{ ok: boolean }>(`${B}/mind/surveys/${encodeURIComponent(id)}`, send('DELETE')),
};

/** "15:42" for a unix time in seconds. */
export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
}

/** Whole minutes and seconds left until a unix time: "12:05". */
export function countdown(ts: number, now = Date.now()): string {
  const left = Math.max(0, Math.round(ts - now / 1000));
  return `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
}

/** "8 421 pasos", "7,2 h", "58 lpm". */
export function fmt(value: number | null | undefined, unit = '', decimals = 0): string {
  if (value === null || value === undefined) return '—';
  const n = value.toLocaleString('es', { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
  if (!unit) return n;
  return unit.startsWith('/') || unit === '%' ? `${n}${unit}` : `${n} ${unit}`;
}

export const STATUS_ES: Record<Status, string> = { ok: 'En rango', low: 'Por debajo', high: 'Por encima', '': '' };
