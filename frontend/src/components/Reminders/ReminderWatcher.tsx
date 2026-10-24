// The reminder that arrives on time: every minute the app asks what is due;
// a new one shows a notice («Hecho» / «Luego») and, with permission, a system
// notification. Only for the owner himself.

import { useEffect } from 'react';
import { toast } from 'sonner';
import { reminders, type DueReminder } from '../../lib/reminders';

const EVERY_MS = 60_000;

function label(d: DueReminder): string {
  if (d.kind === 'medicina') return `Hora de ${d.title}${d.extra.dose ? ` (${d.extra.dose})` : ''}`;
  if (d.kind === 'meta') return `¿Cómo va «${d.title}»?`;
  return d.title;
}

export function ReminderWatcher() {
  useEffect(() => {
    const shown = new Set<string>();
    let stopped = false;
    const check = async () => {
      let due: DueReminder[] = [];
      try {
        due = await reminders.due();
      } catch {
        return;
      }
      for (const d of due) {
        const key = `${d.id}@${d.slot}`;
        if (shown.has(key) || stopped) continue;
        shown.add(key);
        const text = label(d);
        toast(text, {
          duration: 60_000,
          action: {
            label: 'Hecho',
            onClick: () => void reminders.done(d.id, d.slot).then(() => window.dispatchEvent(new CustomEvent('sergio:reminders'))),
          },
          cancel: { label: 'Luego', onClick: () => shown.delete(key) },
        });
        try {
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted' && document.hidden) {
            new Notification('Sergio', { body: text, tag: key });
          }
        } catch {
          // Some browsers refuse notifications outside a service worker.
        }
      }
      if (due.length) window.dispatchEvent(new CustomEvent('sergio:reminders'));
    };
    void check();
    const id = window.setInterval(() => void check(), EVERY_MS);
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
  }, []);
  return null;
}
