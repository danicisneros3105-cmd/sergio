// Goals, medications and reminders (server: src/openjarvis/reminders).

import { apiFetch } from './api';

export type ReminderKind = 'medicina' | 'meta' | 'recordatorio';

export interface Reminder {
  id: string;
  kind: ReminderKind;
  title: string;
  detail: string;
  times: string[];
  days: number[];
  date: string;
  active: boolean;
  extra: { dose?: string; why?: string; [k: string]: unknown };
  adherence?: { due: number; taken: number; share: number | null };
}

export interface DueReminder extends Reminder {
  slot: string;
  at: string;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(`/v1/reminders${path}`, init);
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return (await res.json()) as T;
}

const body = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
});

export const reminders = {
  list: (kind = '') => call<{ items: Reminder[]; upcoming: DueReminder[] }>(kind ? `?kind=${kind}` : ''),
  add: (item: Partial<Reminder> & { kind: ReminderKind; title: string }) => call<Reminder>('', body('POST', item)),
  change: (id: string, changes: Partial<Reminder>) => call<Reminder>(`/${encodeURIComponent(id)}`, body('PUT', changes)),
  remove: (id: string) => call<{ ok: boolean }>(`/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  due: () => call<{ due: DueReminder[] }>('/due').then((r) => r.due),
  done: (id: string, slot: string, status: 'hecho' | 'saltado' = 'hecho') =>
    call<{ ok: boolean }>(`/${encodeURIComponent(id)}/done`, body('POST', { slot, status })),
};

export const DAY_LETTERS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
