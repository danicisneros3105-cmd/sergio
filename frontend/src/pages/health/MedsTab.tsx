// Medicinas: each one with its dose and times, a tap for «tomada», and the week
// drawn as dots (only real answers; nothing is guessed). Sergio reminds at the time.

import { useCallback, useEffect, useState } from 'react';
import { Pause, Play, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { DAY_LETTERS, reminders, type DueReminder, type Reminder } from '../../lib/reminders';

function Week({ r }: { r: Reminder }) {
  const a = r.adherence;
  if (!a || a.due === 0) return <span className="med-week-empty">Sin tomas todavía</span>;
  return (
    <span className="med-week" aria-label={`${a.taken} de ${a.due} tomas esta semana`}>
      {Array.from({ length: Math.min(a.due, 14) }, (_, i) => (
        <i key={i} data-on={i < a.taken} />
      ))}
      <b>{Math.round((a.share ?? 0) * 100)} %</b>
    </span>
  );
}

function NewMed({ onAdded }: { onAdded: () => void }) {
  const [title, setTitle] = useState('');
  const [dose, setDose] = useState('');
  const [times, setTimes] = useState<string[]>(['08:00']);
  const [days, setDays] = useState<number[]>([]);
  const add = async () => {
    if (!title.trim()) return;
    try {
      await reminders.add({ kind: 'medicina', title: title.trim(), times, days, extra: { dose: dose.trim() } });
      setTitle('');
      setDose('');
      onAdded();
      toast.success('Le avisaré a su hora.');
    } catch {
      toast.error('No pude guardarla.');
    }
  };
  return (
    <form
      className="med-new"
      onSubmit={(e) => {
        e.preventDefault();
        void add();
      }}
    >
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Medicina" aria-label="Medicina" />
      <input value={dose} onChange={(e) => setDose(e.target.value)} placeholder="Dosis (p. ej. 1 pastilla)" aria-label="Dosis" />
      <div className="med-times">
        {times.map((t, i) => (
          <span key={i} className="med-time">
            <input type="time" value={t} aria-label={`Hora ${i + 1}`} onChange={(e) => setTimes(times.map((x, j) => (j === i ? e.target.value : x)))} />
            {times.length > 1 && (
              <button type="button" aria-label="Quitar hora" onClick={() => setTimes(times.filter((_, j) => j !== i))}>
                ×
              </button>
            )}
          </span>
        ))}
        {times.length < 6 && (
          <button type="button" className="med-add-time" onClick={() => setTimes([...times, '20:00'])}>
            <Plus size={14} /> Hora
          </button>
        )}
      </div>
      <div className="med-days" role="group" aria-label="Días (ninguno = todos)">
        {DAY_LETTERS.map((d, i) => (
          <button
            key={d}
            type="button"
            aria-pressed={days.includes(i)}
            onClick={() => setDays(days.includes(i) ? days.filter((x) => x !== i) : [...days, i].sort())}
          >
            {d}
          </button>
        ))}
      </div>
      <button type="submit" className="paper-button" disabled={!title.trim()}>
        Añadir
      </button>
    </form>
  );
}

export function MedsTab() {
  const [items, setItems] = useState<Reminder[] | null>(null);
  const [due, setDue] = useState<DueReminder[]>([]);
  const load = useCallback(() => {
    reminders
      .list('medicina')
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
    reminders
      .due()
      .then((d) => setDue(d.filter((x) => x.kind === 'medicina')))
      .catch(() => setDue([]));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="med">
      {due.length > 0 && (
        <section className="med-due" aria-label="Ahora">
          {due.map((d) => (
            <div key={d.id + d.slot} className="med-due-row">
              <span>
                <b>{d.title}</b> {d.extra.dose ? `· ${d.extra.dose}` : ''} · {d.at}
              </span>
              <button
                type="button"
                className="paper-button"
                onClick={async () => {
                  await reminders.done(d.id, d.slot, 'hecho');
                  load();
                }}
              >
                Tomada
              </button>
              <button
                type="button"
                className="paper-button"
                data-variant="quiet"
                onClick={async () => {
                  await reminders.done(d.id, d.slot, 'saltado');
                  load();
                }}
              >
                Saltar
              </button>
            </div>
          ))}
        </section>
      )}
      <ul className="med-list">
        {(items ?? []).map((r) => (
          <li key={r.id} data-paused={!r.active}>
            <div className="med-main">
              <b>{r.title}</b>
              <span>
                {[r.extra.dose, r.times.join(' · '), r.days.length ? r.days.map((d) => DAY_LETTERS[d]).join(' ') : 'Todos los días']
                  .filter(Boolean)
                  .join(' — ')}
              </span>
            </div>
            <Week r={r} />
            <div className="med-actions">
              <button
                type="button"
                className="mac-icon-btn"
                aria-label={r.active ? 'Pausar' : 'Reanudar'}
                onClick={async () => {
                  await reminders.change(r.id, { active: !r.active });
                  load();
                }}
              >
                {r.active ? <Pause size={15} /> : <Play size={15} />}
              </button>
              <button
                type="button"
                className="mac-icon-btn"
                aria-label="Quitar"
                onClick={async () => {
                  if (!window.confirm(`¿Quitar ${r.title}?`)) return;
                  await reminders.remove(r.id);
                  load();
                }}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </li>
        ))}
      </ul>
      {items && items.length === 0 && <p className="paper-meta">Añada su primera medicina y Sergio le avisará a su hora.</p>}
      <NewMed onAdded={load} />
      <p className="paper-meta med-note">Solo recordatorios: Sergio no cambia dosis ni da consejo médico.</p>
    </div>
  );
}
