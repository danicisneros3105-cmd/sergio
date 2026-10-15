// Creator › Prototipos: design by talking. The conversation with Sergio on
// the left, the live design on the right; comment on any element, edit its
// text in place, turn its knobs (the design's CSS variables), go back to any
// version and export it. Every design is one self-contained HTML file kept
// in this browser. Black, white and greys in the interface (owner, 2026-10).

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowUp,
  Code2,
  Copy,
  Download,
  History,
  Monitor,
  MousePointer2,
  MessageSquarePlus,
  Pencil,
  Printer,
  Smartphone,
  SlidersHorizontal,
  Square,
  Tablet,
  Trash2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { streamChat } from '../../lib/sse';
import { useAppStore } from '../../lib/store';
import {
  KINDS,
  cssVars,
  designPrompt,
  setCssVar,
  splitAnswer,
  titleFrom,
  withBridge,
  type ProtoKind,
  type Project,
} from '../../lib/prototypes';
import { newId } from '../../lib/workspace/model';
import './prototypes.css';

const STORE = 'sergio.prototipos';

function loadProjects(): Project[] {
  try {
    return JSON.parse(localStorage.getItem(STORE) || '[]');
  } catch {
    return [];
  }
}
function saveProjects(list: Project[]) {
  try {
    localStorage.setItem(STORE, JSON.stringify(list.slice(0, 30)));
  } catch {
    toast.error('No caben más diseños en este navegador: borre alguno antiguo.');
  }
}

type Tool = 'view' | 'comment' | 'edit';
type Device = 'escritorio' | 'tableta' | 'movil';
const WIDTH: Record<Device, string> = { escritorio: '100%', tableta: '820px', movil: '390px' };

export function Prototypes() {
  const [projects, setProjects] = useState<Project[]>(loadProjects);
  const [openId, setOpenId] = useState<string | null>(null);
  const project = projects.find((p) => p.id === openId) || null;

  const put = (p: Project) => {
    setProjects((all) => {
      const next = [p, ...all.filter((x) => x.id !== p.id)];
      saveProjects(next);
      return next;
    });
  };

  if (!project)
    return (
      <Home
        projects={projects}
        onOpen={setOpenId}
        onDelete={(id) => {
          const next = projects.filter((p) => p.id !== id);
          saveProjects(next);
          setProjects(next);
        }}
        onStart={(kind, request) => {
          const now = Date.now();
          const p: Project = { id: newId('d'), title: titleFrom(request), kind, createdAt: now, updatedAt: now, versions: [], current: -1, messages: [], pending: request };
          put(p);
          setOpenId(p.id);
        }}
      />
    );
  return <Editor key={project.id} project={project} onChange={put} onBack={() => setOpenId(null)} />;
}

function Home({
  projects,
  onOpen,
  onStart,
  onDelete,
}: {
  projects: Project[];
  onOpen: (id: string) => void;
  onStart: (kind: ProtoKind, request: string) => void;
  onDelete: (id: string) => void;
}) {
  const [kind, setKind] = useState<ProtoKind>('prototipo');
  const [text, setText] = useState('');
  return (
    <div className="pt-home">
      <h2 className="pt-hero">¿Qué diseñamos hoy?</h2>
      <form
        className="pt-start"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) onStart(kind, text.trim());
        }}
      >
        <textarea
          value={text}
          rows={3}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (text.trim()) onStart(kind, text.trim());
            }
          }}
          placeholder="Describa lo que quiere: «la app de reservas de mi barbería, con agenda y pagos»"
          aria-label="Describa su diseño"
        />
        <div className="pt-start-bar">
          <div className="pt-kinds" role="radiogroup" aria-label="Tipo">
            {KINDS.map((k) => (
              <button key={k.key} type="button" role="radio" aria-checked={kind === k.key} title={k.hint} onClick={() => setKind(k.key)}>
                {k.label}
              </button>
            ))}
          </div>
          <button type="submit" className="pt-send" disabled={!text.trim()} aria-label="Empezar">
            <ArrowUp size={18} />
          </button>
        </div>
      </form>

      {projects.length > 0 && (
        <section className="pt-recent">
          <h3>Recientes</h3>
          <div className="pt-grid">
            {projects.map((p) => {
              const html = p.versions[p.current]?.html || '';
              return (
                <div key={p.id} className="pt-card">
                  <button type="button" className="pt-thumb" onClick={() => onOpen(p.id)} aria-label={`Abrir ${p.title}`}>
                    {html ? <iframe title={p.title} srcDoc={html} sandbox="" tabIndex={-1} /> : <span>Sin diseño</span>}
                  </button>
                  <div className="pt-card-row">
                    <button type="button" className="pt-card-title" onClick={() => onOpen(p.id)}>
                      {p.title}
                    </button>
                    <button type="button" className="pt-icon" aria-label={`Borrar ${p.title}`} onClick={() => window.confirm(`¿Borrar «${p.title}»?`) && onDelete(p.id)}>
                      <Trash2 size={15} />
                    </button>
                  </div>
                  <span className="pt-dim">{KINDS.find((k) => k.key === p.kind)?.label} · {new Date(p.updatedAt).toLocaleDateString('es')}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}

function Editor({ project, onChange, onBack }: { project: Project; onChange: (p: Project) => void; onBack: () => void }) {
  const model = useAppStore((s) => s.selectedModel);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [streamed, setStreamed] = useState('');
  const [tool, setTool] = useState<Tool>('view');
  const [device, setDevice] = useState<Device>('escritorio');
  const [panel, setPanel] = useState<null | 'ajustes' | 'versiones' | 'codigo' | 'exportar'>(null);
  const [comments, setComments] = useState<Array<{ target: string; text: string; draft?: boolean }>>([]);
  const [pane, setPane] = useState<'chat' | 'design'>('design');
  const frame = useRef<HTMLIFrameElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);
  const live = useRef(project);
  live.current = project;

  const version = project.versions[project.current];
  const html = version?.html || '';
  const partial = busy ? splitAnswer(streamed).html : '';
  const shown = partial.length > 400 ? partial : html;
  const vars = useMemo(() => cssVars(html), [html]);

  const update = (change: Partial<Project>) => {
    const next = { ...live.current, ...change, updatedAt: Date.now() };
    live.current = next; // later updates in the same turn build on this one
    onChange(next);
  };
  const addVersion = (newHtml: string, note: string, extra: Partial<Project> = {}) => {
    const p = live.current;
    const versions = [...p.versions.slice(0, p.current + 1), { html: newHtml, at: Date.now(), note }];
    update({ versions, current: versions.length - 1, ...extra });
  };

  const ask = async (request: string) => {
    const p = live.current;
    const pending = comments.filter((c) => !c.draft && c.text.trim());
    if (!request.trim() && !pending.length) return;
    const said = request.trim() || 'Aplica los comentarios.';
    const messages = [...p.messages, { role: 'user' as const, text: said + (pending.length ? `\n(${pending.length} comentario${pending.length > 1 ? 's' : ''})` : ''), at: Date.now() }];
    update({ messages });
    setInput('');
    setComments([]);
    setBusy(true);
    setStreamed('');
    setTool('view');
    const ac = new AbortController();
    abort.current = ac;
    let answer = '';
    try {
      const prompt = designPrompt({ kind: p.kind, request: said, html: p.versions[p.current]?.html, comments: pending });
      for await (const ev of streamChat({ model: model || 'default', stream: true, messages: [{ role: 'user', content: prompt }] }, ac.signal)) {
        try {
          const delta = JSON.parse(ev.data)?.choices?.[0]?.delta?.content;
          if (delta) {
            answer += delta;
            setStreamed(answer);
          }
        } catch {
          /* not a content chunk */
        }
      }
      const { html: out, note } = splitAnswer(answer);
      const reply = { role: 'sergio' as const, text: note || (out ? 'Listo.' : answer.trim() || 'No recibí el diseño.'), at: Date.now() };
      if (out) addVersion(out, said, { messages: [...messages, reply] });
      else update({ messages: [...messages, reply] });
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        update({ messages: [...messages, { role: 'sergio', text: `No pude terminar: ${err instanceof Error ? err.message : String(err)}`, at: Date.now() }] });
      }
    } finally {
      setBusy(false);
      setStreamed('');
      abort.current = null;
    }
  };

  // The first request, typed on the home screen.
  const started = useRef(false);
  useEffect(() => {
    const first = live.current.pending;
    if (!first || started.current) return;
    started.current = true;
    update({ pending: undefined });
    void ask(first);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // The preview tells us what was clicked (comment) or edited.
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.source !== frame.current?.contentWindow) return;
      const d = e.data || {};
      if (d.sergio === 'pick') setComments((c) => [...c.filter((x) => !x.draft || x.text), { target: d.text ? `«${d.text}» (${d.target})` : d.target, text: '', draft: true }]);
      if (d.sergio === 'edited' && typeof d.html === 'string') addVersion(d.html, 'Edición directa');
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    frame.current?.contentWindow?.postMessage({ sergio: 'mode', mode: tool }, '*');
  }, [tool, shown]);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [project.messages.length, busy]);

  const download = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    a.download = `${project.title.replace(/[^\p{L}\p{N} _-]/gu, '').trim() || 'diseno'}.html`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };

  return (
    <div className="pt" data-pane={pane}>
      <section className="pt-chat" aria-label="Conversación">
        <header className="pt-chat-head">
          <button type="button" className="pt-icon" aria-label="Volver" onClick={onBack}>
            <ArrowLeft size={18} />
          </button>
          <input className="pt-title" value={project.title} onChange={(e) => update({ title: e.target.value })} aria-label="Nombre del diseño" />
        </header>
        <div className="pt-log" ref={log}>
          {project.messages.map((m, i) => (
            <div key={i} className="pt-msg" data-role={m.role}>
              {m.text}
            </div>
          ))}
          {busy && (
            <div className="pt-msg" data-role="sergio">
              <span className="pt-working">Diseñando… {streamed.length > 0 && `${Math.round(streamed.length / 1000)} k caracteres`}</span>
            </div>
          )}
        </div>
        {comments.length > 0 && (
          <div className="pt-comments">
            {comments.map((c, i) => (
              <div key={i} className="pt-comment">
                <span className="pt-comment-target">{c.target}</span>
                <input
                  autoFocus={c.draft}
                  value={c.text}
                  placeholder="¿Qué cambio aquí?"
                  onChange={(e) => setComments(comments.map((x, k) => (k === i ? { ...x, text: e.target.value, draft: false } : x)))}
                  aria-label="Comentario"
                />
                <button type="button" className="pt-icon" aria-label="Quitar" onClick={() => setComments(comments.filter((_, k) => k !== i))}>
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
        <form
          className="pt-composer"
          onSubmit={(e) => {
            e.preventDefault();
            void ask(input);
          }}
        >
          <textarea
            value={input}
            rows={2}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void ask(input);
              }
            }}
            placeholder={html ? 'Pida un cambio a Sergio…' : 'Describa el diseño…'}
            aria-label="Mensaje para Sergio"
            disabled={busy}
          />
          {busy ? (
            <button type="button" className="pt-send" aria-label="Detener" onClick={() => abort.current?.abort()}>
              <Square size={14} fill="currentColor" />
            </button>
          ) : (
            <button type="submit" className="pt-send" aria-label="Enviar" disabled={!input.trim() && !comments.some((c) => c.text.trim())}>
              <ArrowUp size={18} />
            </button>
          )}
        </form>
      </section>

      <section className="pt-canvas" aria-label="Diseño">
        <header className="pt-bar">
          <div className="pt-seg" role="radiogroup" aria-label="Herramienta">
            <button type="button" role="radio" aria-checked={tool === 'view'} title="Usar" onClick={() => setTool('view')}>
              <MousePointer2 size={16} />
            </button>
            <button type="button" role="radio" aria-checked={tool === 'comment'} title="Comentar un elemento" onClick={() => setTool('comment')} disabled={!html}>
              <MessageSquarePlus size={16} />
            </button>
            <button type="button" role="radio" aria-checked={tool === 'edit'} title="Editar el texto" onClick={() => setTool('edit')} disabled={!html}>
              <Pencil size={16} />
            </button>
          </div>
          <div className="pt-seg" role="radiogroup" aria-label="Pantalla">
            {(
              [
                ['escritorio', Monitor],
                ['tableta', Tablet],
                ['movil', Smartphone],
              ] as const
            ).map(([d, Icon]) => (
              <button key={d} type="button" role="radio" aria-checked={device === d} title={d} onClick={() => setDevice(d)}>
                <Icon size={16} />
              </button>
            ))}
          </div>
          <span className="pt-spacer" />
          <button type="button" className="pt-tab" aria-pressed={panel === 'ajustes'} onClick={() => setPanel(panel === 'ajustes' ? null : 'ajustes')} disabled={!vars.length}>
            <SlidersHorizontal size={15} /> Ajustes
          </button>
          <button type="button" className="pt-tab" aria-pressed={panel === 'versiones'} onClick={() => setPanel(panel === 'versiones' ? null : 'versiones')} disabled={!project.versions.length}>
            <History size={15} /> Versiones
          </button>
          <button type="button" className="pt-tab" aria-pressed={panel === 'codigo'} onClick={() => setPanel(panel === 'codigo' ? null : 'codigo')} disabled={!html}>
            <Code2 size={15} /> Código
          </button>
          <button type="button" className="pt-primary" onClick={() => setPanel(panel === 'exportar' ? null : 'exportar')} disabled={!html}>
            <Download size={15} /> Exportar
          </button>
        </header>

        <div className="pt-stage">
          {shown ? (
            <div className="pt-device" style={{ width: WIDTH[device] }}>
              <iframe ref={frame} title="Diseño" srcDoc={withBridge(shown)} sandbox="allow-scripts allow-modals" />
            </div>
          ) : (
            <div className="pt-empty">{busy ? 'Sergio está diseñando…' : 'Describa el diseño a la izquierda y aparecerá aquí.'}</div>
          )}

          {panel && (
            <aside className="pt-panel" aria-label={panel}>
              <header>
                <strong>{panel === 'ajustes' ? 'Ajustes' : panel === 'versiones' ? 'Versiones' : panel === 'codigo' ? 'Código' : 'Exportar'}</strong>
                <button type="button" className="pt-icon" aria-label="Cerrar" onClick={() => setPanel(null)}>
                  <X size={16} />
                </button>
              </header>
              {panel === 'ajustes' && (
                <div className="pt-vars">
                  {vars.map((v) => (
                    <label key={v.name} className="pt-var">
                      <span>{v.name.replace(/^--/, '').replace(/-/g, ' ')}</span>
                      {v.kind === 'color' && /^#([0-9a-f]{6})$/i.test(v.value) ? (
                        <input type="color" value={v.value} onChange={(e) => update({ versions: project.versions.map((x, i) => (i === project.current ? { ...x, html: setCssVar(x.html, v.name, e.target.value) } : x)) })} />
                      ) : v.kind === 'length' ? (
                        <input
                          type="range"
                          min={0}
                          max={Math.max(64, parseFloat(v.value) * 3)}
                          step={v.value.endsWith('px') ? 1 : 0.05}
                          value={parseFloat(v.value)}
                          onChange={(e) => {
                            const unit = v.value.replace(/^-?[\d.]+/, '');
                            update({ versions: project.versions.map((x, i) => (i === project.current ? { ...x, html: setCssVar(x.html, v.name, `${e.target.value}${unit}`) } : x)) });
                          }}
                        />
                      ) : (
                        <input className="pt-var-text" value={v.value} onChange={(e) => update({ versions: project.versions.map((x, i) => (i === project.current ? { ...x, html: setCssVar(x.html, v.name, e.target.value) } : x)) })} />
                      )}
                    </label>
                  ))}
                </div>
              )}
              {panel === 'versiones' && (
                <ol className="pt-versions">
                  {project.versions.map((v, i) => (
                    <li key={i}>
                      <button type="button" aria-current={i === project.current} onClick={() => update({ current: i })}>
                        <span>Versión {i + 1}</span>
                        <span className="pt-dim">{v.note.slice(0, 60)}</span>
                        <span className="pt-dim">{new Date(v.at).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              )}
              {panel === 'codigo' && (
                <textarea
                  className="pt-code"
                  spellCheck={false}
                  value={html}
                  onChange={(e) => update({ versions: project.versions.map((x, i) => (i === project.current ? { ...x, html: e.target.value } : x)) })}
                  aria-label="Código del diseño"
                />
              )}
              {panel === 'exportar' && (
                <div className="pt-export">
                  <button type="button" onClick={download}>
                    <Download size={16} /> Descargar HTML
                  </button>
                  <button type="button" onClick={() => frame.current?.contentWindow?.postMessage({ sergio: 'print' }, '*')}>
                    <Printer size={16} /> PDF (imprimir)
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      navigator.clipboard
                        .writeText(html)
                        .then(() => toast.success('Código copiado.'))
                        .catch(() => setPanel('codigo'))
                    }
                  >
                    <Copy size={16} /> Copiar el código
                  </button>
                </div>
              )}
            </aside>
          )}
        </div>
        {tool !== 'view' && (
          <div className="pt-hint">{tool === 'comment' ? 'Toque un elemento del diseño para comentarlo.' : 'Escriba directamente sobre el diseño. Se guarda solo.'}</div>
        )}
      </section>

      <nav className="pt-switch" aria-label="Vista">
        <button type="button" aria-pressed={pane === 'chat'} onClick={() => setPane('chat')}>
          Conversación
        </button>
        <button type="button" aria-pressed={pane === 'design'} onClick={() => setPane('design')}>
          Diseño
        </button>
      </nav>
    </div>
  );
}

export default Prototypes;
