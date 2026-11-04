// The organiser (owner, 3 Nov 2026: «hacer workspace funcional con
// recordatorios, pendientes, correos… o decidir si esconderlo»). The Notion
// workspace alone had no daily use, so the page opens on what does: today's
// reminders, a to-do list to tick, the mail (through the account he
// connects; Sergio only drafts, never sends) and the notes, as a tab.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { Bell, Check, CheckSquare, Mail, NotebookPen, Plus, Trash2 } from 'lucide-react';
import { reminders, type DueReminder, type Reminder } from '../lib/reminders';
import { apiFetch } from '../lib/api';
import { WorkspacePage } from './WorkspacePage';
import './organizer.css';

type Tab = 'hoy' | 'pendientes' | 'correo' | 'notas';
const TABS: { key: Tab; label: string; icon: typeof Bell }[] = [
  { key: 'hoy', label: 'Hoy', icon: Bell },
  { key: 'pendientes', label: 'Pendientes', icon: CheckSquare },
  { key: 'correo', label: 'Correo', icon: Mail },
  { key: 'notas', label: 'Notas', icon: NotebookPen },
];
const TAB_KEY = 'sergio-organizador-tab';

/** Ask Sergio in the chat (the message is his to send there). */
export function askSergio(navigate: (to: string) => void, text: string) {
  navigate('/chat');
  window.setTimeout(() => window.dispatchEvent(new CustomEvent('sergio:send', { detail: text })), 450);
}

function Today() {
  const [items, setItems] = useState<Reminder[]>([]);
  const [upcoming, setUpcoming] = useState<DueReminder[]>([]);
  const [title, setTitle] = useState('');
  const [time, setTime] = useState('09:00');
  const [failed, setFailed] = useState(false);
  const load = useCallback(async () => {
    try {
      const r = await reminders.list('recordatorio');
      setItems(r.items.filter((i) => i.active));
      setUpcoming(r.upcoming ?? []);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);
  useEffect(() => void load(), [load]);
  const add = async () => {
    if (!title.trim()) return;
    await reminders.add({ kind: 'recordatorio', title: title.trim(), times: [time] });
    setTitle('');
    void load();
  };
  return (
    <section className="org-card" aria-label="Recordatorios">
      <h2>Recordatorios</h2>
      <form className="org-add" onSubmit={(e) => (e.preventDefault(), void add())}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Recordarme…" aria-label="Qué recordar" />
        <input type="time" value={time} onChange={(e) => setTime(e.target.value)} aria-label="Hora" />
        <button type="submit" aria-label="Añadir recordatorio"><Plus size={16} /></button>
      </form>
      {failed && <p className="org-note">No pude leer los recordatorios: el servidor de Sergio no responde.</p>}
      {upcoming.length > 0 && (
        <ul className="org-list">
          {upcoming.slice(0, 8).map((u) => (
            <li key={u.slot}>
              <span className="org-time">{u.at}</span>
              <span>{u.title}</span>
            </li>
          ))}
        </ul>
      )}
      {items.length === 0 && !failed && <p className="org-note">Nada para hoy. Escriba arriba o dígale a Sergio «recuérdame…».</p>}
      {items.length > 0 && (
        <ul className="org-list">
          {items.map((i) => (
            <li key={i.id}>
              <span className="org-time">{i.times.join(' · ') || i.date || 'sin hora'}</span>
              <span>{i.title}</span>
              <button type="button" className="org-icon" aria-label={`Borrar «${i.title}»`} onClick={() => void reminders.remove(i.id).then(load)}>
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Todos() {
  const [items, setItems] = useState<Reminder[]>([]);
  const [title, setTitle] = useState('');
  const load = useCallback(async () => {
    try {
      setItems((await reminders.list('pendiente')).items);
    } catch {
      setItems([]);
    }
  }, []);
  useEffect(() => void load(), [load]);
  const open = useMemo(() => items.filter((i) => i.active), [items]);
  const done = useMemo(() => items.filter((i) => !i.active).slice(0, 10), [items]);
  const add = async () => {
    if (!title.trim()) return;
    await reminders.add({ kind: 'pendiente', title: title.trim() });
    setTitle('');
    void load();
  };
  const toggle = async (i: Reminder) => {
    await reminders.change(i.id, { active: !i.active });
    void load();
  };
  return (
    <section className="org-card" aria-label="Pendientes">
      <h2>Pendientes <small>{open.length}</small></h2>
      <form className="org-add" onSubmit={(e) => (e.preventDefault(), void add())}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Añadir un pendiente" aria-label="Nuevo pendiente" />
        <button type="submit" aria-label="Añadir pendiente"><Plus size={16} /></button>
      </form>
      <ul className="org-list">
        {open.map((i) => (
          <li key={i.id}>
            <button type="button" className="org-check" aria-label={`Hecho: ${i.title}`} onClick={() => void toggle(i)} />
            <span>{i.title}</span>
          </li>
        ))}
      </ul>
      {open.length === 0 && <p className="org-note">Sin pendientes.</p>}
      {done.length > 0 && (
        <details className="org-done">
          <summary>Hechos ({done.length})</summary>
          <ul className="org-list">
            {done.map((i) => (
              <li key={i.id} data-done>
                <button type="button" className="org-check" data-on aria-label={`Volver a abrir: ${i.title}`} onClick={() => void toggle(i)}>
                  <Check size={12} />
                </button>
                <span>{i.title}</span>
                <button type="button" className="org-icon" aria-label={`Borrar «${i.title}»`} onClick={() => void reminders.remove(i.id).then(load)}>
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function MailTab() {
  const navigate = useNavigate();
  const [mail, setMail] = useState<'?' | 'si' | 'no'>('?');
  useEffect(() => {
    apiFetch('/v1/connectors')
      .then((r) => (r.ok ? r.json() : { connectors: [] }))
      .then((d: { connectors: { connector_id: string; connected: boolean }[] }) =>
        setMail(d.connectors.some((c) => /gmail|outlook|imap|mail/.test(c.connector_id) && c.connected) ? 'si' : 'no'),
      )
      .catch(() => setMail('no'));
  }, []);
  const asks = [
    { label: 'Resumir lo importante', text: 'Revisa mi correo sin leer y dime en 5 líneas lo importante, lo urgente primero.' },
    { label: 'Borradores de respuesta', text: 'Prepara borradores de respuesta para los correos que esperan contestación. No envíes nada.' },
    { label: 'Pendientes desde el correo', text: 'Saca de mi correo de hoy las tareas que me piden y añádelas a mis pendientes.' },
  ];
  return (
    <section className="org-card" aria-label="Correo">
      <h2>Correo</h2>
      {mail === 'no' && (
        <>
          <p className="org-note">Conecte su correo una vez y Sergio lo podrá leer, resumir y preparar borradores. Nunca envía nada sin usted.</p>
          <button type="button" className="org-primary" onClick={() => navigate('/settings?tab=personalizar')}>
            Conectar mi correo
          </button>
        </>
      )}
      {mail === 'si' && <p className="org-note">Correo conectado. Sergio solo prepara borradores: usted los revisa y los envía.</p>}
      <div className="org-asks">
        {asks.map((a) => (
          <button key={a.label} type="button" disabled={mail !== 'si'} onClick={() => askSergio(navigate, a.text)}>
            {a.label}
          </button>
        ))}
      </div>
    </section>
  );
}

/** The useful part, for Cowork: today's reminders and the to-dos (no mail or
 *  notes: those stay in the full Organizer). */
export function OrganizerPeek() {
  return (
    <div className="org org-peek">
      <div className="org-grid">
        <Today />
        <Todos />
      </div>
    </div>
  );
}

export function OrganizerPage() {
  const [tab, setTab] = useState<Tab>(() => {
    try {
      return (localStorage.getItem(TAB_KEY) as Tab) || 'hoy';
    } catch {
      return 'hoy';
    }
  });
  const pick = (t: Tab) => {
    setTab(t);
    try {
      localStorage.setItem(TAB_KEY, t);
    } catch {
      /* per-viewer only */
    }
  };
  return (
    <div className="org">
      <header className="org-head">
        <h1>Organizador</h1>
        <nav className="org-tabs" role="tablist" aria-label="Organizador">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => pick(key)}>
              <Icon size={15} strokeWidth={1.8} /> {label}
            </button>
          ))}
        </nav>
      </header>
      {tab === 'hoy' && (
        <div className="org-grid">
          <Today />
          <Todos />
        </div>
      )}
      {tab === 'pendientes' && <Todos />}
      {tab === 'correo' && <MailTab />}
      {tab === 'notas' && (
        <div className="org-notes">
          <WorkspacePage />
        </div>
      )}
    </div>
  );
}

export default OrganizerPage;
