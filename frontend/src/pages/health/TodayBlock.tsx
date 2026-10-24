// Hoy: what is due now, what comes next, and the owner's goals (Sergio keeps
// them in mind in every conversation and asks how they are going).

import { useCallback, useEffect, useState } from 'react';
import { Check, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { reminders, type DueReminder, type Reminder } from '../../lib/reminders';

export function TodayBlock() {
  const [due, setDue] = useState<DueReminder[]>([]);
  const [next, setNext] = useState<DueReminder[]>([]);
  const [goals, setGoals] = useState<Reminder[]>([]);
  const [goal, setGoal] = useState('');
  const load = useCallback(() => {
    reminders.due().then(setDue).catch(() => setDue([]));
    reminders
      .list()
      .then((r) => {
        setNext(r.upcoming.slice(0, 4));
        setGoals(r.items.filter((i) => i.kind === 'meta' && i.active));
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    load();
    window.addEventListener('sergio:reminders', load);
    return () => window.removeEventListener('sergio:reminders', load);
  }, [load]);

  return (
    <section className="today" aria-label="Hoy">
      <div className="today-col">
        <h3 className="paper-label">Ahora</h3>
        {due.length === 0 ? (
          <p className="today-empty">Nada pendiente.</p>
        ) : (
          <ul className="today-list">
            {due.map((d) => (
              <li key={d.id + d.slot}>
                <span>
                  <b>{d.title}</b> {d.at}
                </span>
                <button
                  type="button"
                  className="mac-icon-btn"
                  aria-label="Hecho"
                  onClick={async () => {
                    await reminders.done(d.id, d.slot);
                    load();
                  }}
                >
                  <Check size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <h3 className="paper-label">Después</h3>
        {next.length === 0 ? (
          <p className="today-empty">Sin recordatorios.</p>
        ) : (
          <ul className="today-list">
            {next.map((d) => (
              <li key={d.id + d.slot}>
                <span>
                  <b>{d.title}</b> {d.at}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="today-col">
        <h3 className="paper-label">Metas</h3>
        <ul className="today-list">
          {goals.map((g) => (
            <li key={g.id}>
              <span>
                <b>{g.title}</b>
              </span>
              <button
                type="button"
                className="mac-icon-btn"
                aria-label="Quitar meta"
                onClick={async () => {
                  await reminders.remove(g.id);
                  load();
                }}
              >
                <Trash2 size={15} />
              </button>
            </li>
          ))}
        </ul>
        <form
          className="today-add"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!goal.trim()) return;
            try {
              await reminders.add({ kind: 'meta', title: goal.trim(), times: ['20:00'] });
              setGoal('');
              load();
              toast.success('Sergio la tendrá presente y le preguntará cómo va.');
            } catch {
              toast.error('No pude guardarla.');
            }
          }}
        >
          <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Una meta: correr 5 km, leer más…" aria-label="Nueva meta" />
          <button type="submit" className="mac-icon-btn" aria-label="Añadir meta" disabled={!goal.trim()}>
            <Plus size={16} />
          </button>
        </form>
      </div>
    </section>
  );
}
