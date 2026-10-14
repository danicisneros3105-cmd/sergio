// The Workspace's own panels: one calendar for everything, one inbox for
// every account (with an agent that summarises, extracts tasks and drafts a
// reply — never sends), every share link in one place, search by meaning
// and the web clipper.

import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, Copy, Globe, Inbox, Loader2, Scissors, Search, ShieldCheck, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { datedItems, searchPages } from '../../lib/workspace/brain';
import { aiTriage, type Triage } from '../../lib/workspace/ai';
import { block as makeBlock, type Block } from '../../lib/workspace/model';
import { useWorkspace } from '../../lib/workspace/store';
import { useAppStore } from '../../lib/store';

export type HubPanel = 'agenda' | 'mail' | 'shares' | 'search' | 'clip';

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || 'Sergio no respondió.');
  return body as T;
}

function Sheet({ title, icon, onClose, children }: { title: string; icon: React.ReactNode; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="ws-modal" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className="ws-hub" onClick={(e) => e.stopPropagation()}>
        <header>
          {icon}
          <b>{title}</b>
          <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={onClose}>
            <X size={15} />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

interface AgendaItem {
  date: string;
  time?: string;
  title: string;
  where: string;
  page?: string;
  kind: string;
  done?: boolean;
}

function Agenda({ onClose }: { onClose: () => void }) {
  const pages = useWorkspace((s) => s.pages);
  const open = useWorkspace((s) => s.open);
  const local = useMemo<AgendaItem[]>(() => datedItems(Object.values(pages)).map((d) => ({ date: d.date, title: d.title, where: d.where, page: d.pageId, kind: 'tarea', done: d.done })), [pages]);
  const [remote, setRemote] = useState<AgendaItem[]>([]);
  useEffect(() => {
    getJson<{ items: AgendaItem[] }>('/v1/workspace/agenda').then((r) => setRemote(r.items.filter((i) => i.kind === 'evento')), () => undefined);
  }, []);
  const items = [...local, ...remote].sort((a, b) => (a.date + (a.time || '')).localeCompare(b.date + (b.time || '')));
  const today = new Date().toISOString().slice(0, 10);
  const days = [...new Set(items.map((i) => i.date))].filter((d) => d >= today).slice(0, 30);
  return (
    <Sheet title="Calendario" icon={<CalendarDays size={16} />} onClose={onClose}>
      {!days.length && <p className="ws-empty">Nada por delante.</p>}
      {days.map((d) => (
        <section key={d} className="ws-agenda-day">
          <h5>{new Date(`${d}T12:00:00`).toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' })}</h5>
          {items
            .filter((i) => i.date === d)
            .map((i, k) => (
              <button key={k} type="button" className="ws-agenda-item" data-kind={i.kind} data-done={i.done || undefined} onClick={() => i.page && (open(i.page), onClose())}>
                <span>{i.time || ''}</span>
                <b>{i.title}</b>
                <small>{i.where}</small>
              </button>
            ))}
        </section>
      ))}
    </Sheet>
  );
}

interface Mail {
  id: string;
  account: string;
  from: string;
  subject: string;
  date: string;
  preview: string;
}

function MailPanel({ onClose, onToPage }: { onClose: () => void; onToPage: (title: string, blocks: Block[]) => void }) {
  const model = useAppStore((s) => s.selectedModel);
  const [q, setQ] = useState('');
  const [mail, setMail] = useState<Mail[] | null>(null);
  const [account, setAccount] = useState('');
  const [triage, setTriage] = useState<Record<string, Triage | 'busy'>>({});
  useEffect(() => {
    const t = setTimeout(() => {
      getJson<{ messages: Mail[] }>(`/v1/workspace/mail?q=${encodeURIComponent(q)}`).then((r) => setMail(r.messages), () => setMail([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);
  const accounts = [...new Set((mail || []).map((m) => m.account))];
  const shown = (mail || []).filter((m) => !account || m.account === account);
  return (
    <Sheet title="Correo" icon={<Inbox size={16} />} onClose={onClose}>
      <label className="mac-field text-[13px]">
        <Search size={13} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar en todas las cuentas" className="flex-1 bg-transparent outline-none" />
      </label>
      {accounts.length > 1 && (
        <div className="ws-chips-row">
          <button type="button" className="mac-chip" aria-pressed={!account} onClick={() => setAccount('')}>
            Todas
          </button>
          {accounts.map((a) => (
            <button key={a} type="button" className="mac-chip" aria-pressed={account === a} onClick={() => setAccount(a)}>
              {a}
            </button>
          ))}
        </div>
      )}
      {mail === null && <Loader2 size={16} className="ext-spin" />}
      {mail && !shown.length && <p className="ws-empty">Sin correo. Conecte sus cuentas en Extensiones → Conectores.</p>}
      <ul className="ws-mail">
        {shown.map((m) => {
          const t = triage[m.id];
          return (
            <li key={m.id}>
              <div className="ws-mail-top">
                <b>{m.subject}</b>
                <small>
                  {m.from} · {new Date(m.date).toLocaleDateString('es')}
                </small>
              </div>
              {t && t !== 'busy' ? (
                <div className="ws-mail-triage">
                  <p>{t.summary}</p>
                  {t.tasks.length > 0 && (
                    <ul>
                      {t.tasks.map((x) => (
                        <li key={x}>☐ {x}</li>
                      ))}
                    </ul>
                  )}
                  {t.reply && <pre>{t.reply}</pre>}
                  <div className="ws-chips-row">
                    {t.reply && (
                      <button type="button" className="paper-tab" onClick={() => void navigator.clipboard.writeText(t.reply).then(() => toast.success('Borrador copiado.'))}>
                        <Copy size={12} /> Borrador
                      </button>
                    )}
                    <button
                      type="button"
                      className="paper-tab"
                      onClick={() =>
                        onToPage(m.subject, [
                          makeBlock('callout', `${m.from}: ${t.summary}`),
                          ...t.tasks.map((x) => makeBlock('todo', x)),
                          ...(t.reply ? [makeBlock('h3', 'Borrador de respuesta'), makeBlock('quote', t.reply)] : []),
                        ])
                      }
                    >
                      A una página
                    </button>
                  </div>
                </div>
              ) : (
                <p className="ws-mail-preview">{m.preview.slice(0, 180)}</p>
              )}
              {!t && (
                <button
                  type="button"
                  className="paper-tab"
                  onClick={async () => {
                    setTriage((s) => ({ ...s, [m.id]: 'busy' }));
                    try {
                      const out = await aiTriage(m, model);
                      setTriage((s) => ({ ...s, [m.id]: out }));
                    } catch (e) {
                      toast.error(e instanceof Error ? e.message : String(e));
                      setTriage(({ [m.id]: _x, ...rest }) => rest);
                    }
                  }}
                >
                  Sergio
                </button>
              )}
              {t === 'busy' && <Loader2 size={13} className="ext-spin" />}
            </li>
          );
        })}
      </ul>
    </Sheet>
  );
}

interface ShareRow {
  token: string;
  page: string;
  scope: string;
  created: number;
  expires?: number;
}

function Shares({ onClose }: { onClose: () => void }) {
  const pages = useWorkspace((s) => s.pages);
  const update = useWorkspace((s) => s.update);
  const [rows, setRows] = useState<ShareRow[] | null>(null);
  const load = () => getJson<{ shares: ShareRow[] }>('/v1/workspace/shares').then((r) => setRows(r.shares), () => setRows([]));
  useEffect(() => {
    void load();
  }, []);
  const SCOPE = { page: 'Página', block: 'Bloque', rows: 'Filas', view: 'Vista' } as Record<string, string>;
  return (
    <Sheet title="Permisos" icon={<ShieldCheck size={16} />} onClose={onClose}>
      {rows && !rows.length && <p className="ws-empty">Nada compartido.</p>}
      <ul className="ws-mail">
        {(rows || []).map((r) => {
          const p = pages[r.page];
          return (
            <li key={r.token} className="ws-share-row">
              <b>{p?.title || 'Página'}</b>
              <small>
                {SCOPE[r.scope] || r.scope} · {r.expires ? `hasta ${new Date(r.expires * 1000).toLocaleDateString('es')}` : 'sin caducidad'}
              </small>
              <span className="ws-chips-row">
                <button type="button" className="mac-icon-btn" aria-label="Copiar enlace" onClick={() => void navigator.clipboard.writeText(`${location.origin}/s/${r.token}`).then(() => toast.success('Enlace copiado.'))}>
                  <Copy size={13} />
                </button>
                {p && (
                  <button
                    type="button"
                    className="mac-icon-btn"
                    aria-label="Sitio web"
                    title="Publicar como sitio"
                    aria-pressed={!!p.site?.on}
                    onClick={() => update(p.id, (x) => ({ ...x, site: { theme: 'claro', accent: '#0d0d0d', font: 'marca', nav: true, ...(x.site || {}), on: !x.site?.on } }))}
                  >
                    <Globe size={13} />
                  </button>
                )}
                <button
                  type="button"
                  className="mac-icon-btn"
                  aria-label="Revocar"
                  onClick={async () => {
                    await getJson(`/v1/workspace/shares/${r.token}`, { method: 'DELETE' });
                    void load();
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </Sheet>
  );
}

function SearchPanel({ onClose }: { onClose: () => void }) {
  const pages = useWorkspace((s) => s.pages);
  const open = useWorkspace((s) => s.open);
  const [q, setQ] = useState('');
  const hits = useMemo(() => (q.trim() ? searchPages(Object.values(pages), q) : []), [q, pages]);
  return (
    <Sheet title="Buscar" icon={<Search size={16} />} onClose={onClose}>
      <label className="mac-field text-[14px]">
        <Search size={14} />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Por significado, en texto, tablas, fotos y audios" className="flex-1 bg-transparent outline-none" />
      </label>
      <ul className="ws-mail">
        {hits.map((h) => (
          <li key={h.page.id}>
            <button type="button" className="ws-intel-related" onClick={() => (open(h.page.id), onClose())}>
              <span>{h.page.title || 'Sin título'}</span>
              <small>{h.snippet}</small>
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

function Clip({ onClose, onToPage }: { onClose: () => void; onToPage: (title: string, blocks: Block[]) => void }) {
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <Sheet title="Recortar web" icon={<Scissors size={16} />} onClose={onClose}>
      <form
        className="ws-formula-words"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const out = await getJson<{ title: string; blocks: Block[] }>('/v1/workspace/clip', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ url }),
            });
            onToPage(out.title || url, out.blocks);
            onClose();
          } catch (err) {
            toast.error(err instanceof Error ? err.message : String(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Globe size={13} />
        <input autoFocus value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" aria-label="Enlace" />
        {busy && <Loader2 size={13} className="ext-spin" />}
      </form>
    </Sheet>
  );
}

export function HubPanels({ panel, onClose }: { panel: HubPanel; onClose: () => void }) {
  const create = useWorkspace((s) => s.create);
  const update = useWorkspace((s) => s.update);
  const toPage = (title: string, blocks: Block[]) => {
    const p = create({ title });
    update(p.id, (x) => ({ ...x, blocks }));
    toast.success('Página creada.');
  };
  if (panel === 'agenda') return <Agenda onClose={onClose} />;
  if (panel === 'mail') return <MailPanel onClose={onClose} onToPage={toPage} />;
  if (panel === 'shares') return <Shares onClose={onClose} />;
  if (panel === 'search') return <SearchPanel onClose={onClose} />;
  return <Clip onClose={onClose} onToPage={toPage} />;
}
