// Automatizar (owner, 27 Oct 2026): channels that make and post their own
// videos, replies he approves, clients and jobs found for him, trading with
// limits, and how healthy Sergio is — five cards, each with one clear action.
// Nothing here sends a message or a proposal on its own: replies go out only
// with «Enviar las aprobadas», proposals stay drafts, trading starts on paper.

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Activity, Briefcase, Clapperboard, LineChart, MessageCircle } from 'lucide-react';
import { PaperPage } from '../components/Paper/PaperPage';
import { apiFetch } from '../lib/api';
import './automatizar.css';

interface Estado {
  canales: {
    youtube: { conectado: boolean; canal: string; cliente_oauth: boolean; nota: string };
    instagram: { conectado: boolean; usuario: string; enlace_publico: boolean };
    por_dia: number;
    respuestas_pendientes: number;
  };
  programados: Array<{ id: string; idea?: string; cada_horas?: number; auto?: boolean; publicar_en?: string[] }>;
  oportunidades: { perfil: Perfil; total: number };
  trading: {
    activo: boolean;
    real: boolean;
    estrategia: string;
    simbolos: string[];
    dinero_real: boolean;
    broker: boolean;
    detenido: boolean;
    ultimas: Array<Record<string, unknown>>;
    aviso: string;
  };
  skills: Record<string, number>;
}

interface Perfil {
  busco: string;
  habilidades: string[];
  servicio: string;
  tarifa: string;
}

interface Item {
  id: string;
  tipo?: string;
  titulo?: string;
  empresa?: string;
  url?: string;
  puntos?: number;
  estado?: string;
  borrador?: string;
}

interface Reply {
  id: string;
  autor?: string;
  texto?: string;
  respuesta?: string;
}

interface Check {
  nombre: string;
  estado: 'ok' | 'aviso' | 'falla';
  detalle: string;
  arreglo: string;
}

async function call<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await apiFetch(`/v1/automatiza${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail || 'No se pudo.');
  return data as T;
}

const pct = (n: unknown) => `${(Number(n) * 100).toFixed(1)} %`;

export function AutomatizarPage() {
  const [st, setSt] = useState<Estado | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState('');
  const load = useCallback(() => {
    call<Estado>('')
      .then((d) => (setSt(d), setErr('')))
      .catch((e: Error) => setErr(e.message));
  }, []);
  useEffect(load, [load]);

  const act = async (key: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(key);
    try {
      await fn();
      if (ok) toast.success(ok);
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No se pudo.');
    } finally {
      setBusy('');
    }
  };

  return (
    <PaperPage title="Automatizar" wide>
      {err && <p className="auto-note">{err}</p>}
      <div className="auto-grid">
        <Channels st={st} busy={busy} act={act} />
        <Replies busy={busy} act={act} pending={st?.canales.respuestas_pendientes ?? 0} />
        <Opportunities st={st} busy={busy} act={act} />
        <Trading st={st} busy={busy} act={act} />
        <Health />
      </div>
    </PaperPage>
  );
}

type Act = (key: string, fn: () => Promise<unknown>, ok?: string) => Promise<void>;

function Card({ icon: Icon, title, children }: { icon: typeof Clapperboard; title: string; children: React.ReactNode }) {
  return (
    <section className="auto-card">
      <header>
        <span className="auto-icon" aria-hidden="true">
          <Icon size={18} />
        </span>
        <h2>{title}</h2>
      </header>
      {children}
    </section>
  );
}

function Channels({ st, busy, act }: { st: Estado | null; busy: string; act: Act }) {
  const [idea, setIdea] = useState('');
  const [perDay, setPerDay] = useState(3);
  const [shape, setShape] = useState('9:16');
  const [auto, setAuto] = useState(true);
  const [where, setWhere] = useState<string[]>(['youtube']);
  const [ig, setIg] = useState({ user_id: '', token: '' });
  const yt = st?.canales.youtube;
  const insta = st?.canales.instagram;
  const toggle = (w: string) => setWhere((v) => (v.includes(w) ? v.filter((x) => x !== w) : [...v, w]));
  return (
    <Card icon={Clapperboard} title="Canales">
      <div className="auto-rows">
        <div className="auto-row">
          <b>YouTube</b>
          <span>{yt?.conectado ? yt.canal || 'Conectado' : 'Sin conectar'}</span>
          {yt?.conectado ? (
            <button className="paper-button" data-variant="quiet" disabled={!!busy} onClick={() => void act('yt-off', () => call('/canal/youtube', 'DELETE'))}>
              Quitar
            </button>
          ) : (
            <button
              className="paper-button"
              disabled={!!busy}
              onClick={() =>
                void act('yt', async () => {
                  const d = await call<{ url: string }>('/youtube/conectar');
                  window.open(d.url, '_blank', 'noopener');
                })
              }
            >
              Conectar
            </button>
          )}
        </div>
        {yt && !yt.cliente_oauth && <p className="auto-note">Falta la app de Google (YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET en sergio.env).</p>}
        {yt?.conectado && <p className="auto-note">{yt.nota}</p>}
        <div className="auto-row">
          <b>Instagram</b>
          <span>{insta?.conectado ? insta.usuario || 'Conectado' : 'Sin conectar'}</span>
          {insta?.conectado && (
            <button className="paper-button" data-variant="quiet" disabled={!!busy} onClick={() => void act('ig-off', () => call('/canal/instagram', 'DELETE'))}>
              Quitar
            </button>
          )}
        </div>
        {insta && !insta.conectado && (
          <form
            className="auto-form"
            onSubmit={(e) => {
              e.preventDefault();
              void act('ig', () => call('/instagram', 'POST', ig), 'Instagram conectado.');
            }}
          >
            <input className="paper-input" placeholder="ID de la cuenta profesional" value={ig.user_id} onChange={(e) => setIg({ ...ig, user_id: e.target.value })} />
            <input className="paper-input" type="password" placeholder="Token de Meta" value={ig.token} onChange={(e) => setIg({ ...ig, token: e.target.value })} />
            <button className="paper-button" disabled={!!busy || !ig.user_id || !ig.token}>
              Conectar
            </button>
          </form>
        )}
      </div>
      <form
        className="auto-form"
        onSubmit={(e) => {
          e.preventDefault();
          void act(
            'canal',
            () => call('/canal', 'POST', { idea, por_dia: perDay, formato: shape, auto, publicar_en: where }),
            auto ? 'Canal creado: publicará solo.' : 'Canal creado: los videos esperan su «Publicar».',
          ).then(() => setIdea(''));
        }}
      >
        <input className="paper-input" placeholder="Tema del canal (p. ej. datos curiosos de historia)" value={idea} onChange={(e) => setIdea(e.target.value)} required />
        <div className="auto-inline">
          <label>
            Por día
            <select className="paper-select" value={perDay} onChange={(e) => setPerDay(Number(e.target.value))}>
              {[1, 2, 3, 4, 6].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <label>
            Formato
            <select className="paper-select" value={shape} onChange={(e) => setShape(e.target.value)}>
              <option value="9:16">Shorts / Reels</option>
              <option value="16:9">Video largo</option>
            </select>
          </label>
        </div>
        <div className="auto-inline">
          {['youtube', 'instagram'].map((w) => (
            <label key={w} className="auto-check">
              <input type="checkbox" checked={where.includes(w)} onChange={() => toggle(w)} />
              {w === 'youtube' ? 'YouTube' : 'Instagram'}
            </label>
          ))}
          <label className="auto-check">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            Publicar solo
          </label>
        </div>
        <button className="paper-button" disabled={!!busy || !where.length}>
          Crear canal
        </button>
      </form>
      {!!st?.programados.length && (
        <ul className="auto-list">
          {st.programados.map((p) => (
            <li key={p.id}>
              <span>{p.idea}</span>
              <small>
                cada {p.cada_horas} h · {p.auto ? 'publica solo' : 'espera su toque'}
              </small>
            </li>
          ))}
        </ul>
      )}
      <p className="auto-note">Tope: {st?.canales.por_dia ?? 3} publicaciones al día. Las cuentas nuevas las crea usted; Sergio no abre cuentas.</p>
    </Card>
  );
}

function Replies({ busy, act, pending }: { busy: string; act: Act; pending: number }) {
  const [list, setList] = useState<Reply[]>([]);
  const [pick, setPick] = useState<string[]>([]);
  const load = useCallback(() => {
    call<{ pendientes: Reply[] }>('/respuestas')
      .then((d) => setList(d.pendientes || []))
      .catch(() => setList([]));
  }, []);
  useEffect(load, [load, pending]);
  return (
    <Card icon={MessageCircle} title="Respuestas">
      <p className="auto-note">Sergio redacta; solo sale lo que usted aprueba.</p>
      <ul className="auto-list">
        {list.map((r) => (
          <li key={r.id}>
            <label className="auto-check">
              <input type="checkbox" checked={pick.includes(r.id)} onChange={() => setPick((v) => (v.includes(r.id) ? v.filter((x) => x !== r.id) : [...v, r.id]))} />
              <span>
                <small>{r.autor}: {r.texto}</small>
                <br />
                {r.respuesta}
              </span>
            </label>
          </li>
        ))}
        {!list.length && <li className="auto-empty">Nada esperando.</li>}
      </ul>
      <div className="auto-inline">
        <button className="paper-button" data-variant="quiet" disabled={!!busy} onClick={() => void act('redactar', () => call('/respuestas/redactar', 'POST').then(load))}>
          Leer comentarios nuevos
        </button>
        <button
          className="paper-button"
          disabled={!!busy || !pick.length}
          onClick={() => void act('enviar', () => call('/respuestas/enviar', 'POST', { ids: pick }).then(() => (setPick([]), load())), 'Respuestas enviadas.')}
        >
          Enviar las aprobadas ({pick.length})
        </button>
      </div>
    </Card>
  );
}

function Opportunities({ st, busy, act }: { st: Estado | null; busy: string; act: Act }) {
  const [items, setItems] = useState<Item[]>([]);
  const [open, setOpen] = useState('');
  const [skills, setSkills] = useState('');
  const [service, setService] = useState('');
  const [kind, setKind] = useState('ambos');
  const prof = st?.oportunidades.perfil;
  useEffect(() => {
    if (!prof) return;
    setSkills((prof.habilidades || []).join(', '));
    setService(prof.servicio || '');
    setKind(prof.busco || 'ambos');
  }, [prof]);
  const load = useCallback(() => {
    call<{ lista: Item[] }>('/oportunidades')
      .then((d) => setItems(d.lista || []))
      .catch(() => setItems([]));
  }, []);
  useEffect(load, [load, st?.oportunidades.total]);
  return (
    <Card icon={Briefcase} title="Clientes y empleos">
      <form
        className="auto-form"
        onSubmit={(e) => {
          e.preventDefault();
          void act(
            'buscar',
            async () => {
              await call('/oportunidades/perfil', 'PUT', { ...prof, busco: kind, servicio: service, habilidades: skills.split(',').map((s) => s.trim()).filter(Boolean) });
              await call('/oportunidades/buscar', 'POST');
              load();
            },
            'Búsqueda lista: revise los borradores.',
          );
        }}
      >
        <input className="paper-input" placeholder="Habilidades (separadas por comas)" value={skills} onChange={(e) => setSkills(e.target.value)} required />
        <input className="paper-input" placeholder="Qué ofrece a clientes (opcional)" value={service} onChange={(e) => setService(e.target.value)} />
        <div className="auto-inline">
          <select className="paper-select" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Qué busca">
            <option value="ambos">Clientes y empleo</option>
            <option value="clientes">Solo clientes</option>
            <option value="trabajo">Solo empleo</option>
          </select>
          <button className="paper-button" disabled={!!busy}>
            {busy === 'buscar' ? 'Buscando…' : 'Buscar ahora'}
          </button>
        </div>
      </form>
      <ul className="auto-list">
        {items.slice(0, 30).map((it) => (
          <li key={it.id}>
            <button type="button" className="auto-item" onClick={() => setOpen(open === it.id ? '' : it.id)}>
              <span>
                {it.titulo}
                {it.empresa ? ` · ${it.empresa}` : ''}
              </span>
              <small>
                {it.tipo} · {it.puntos ?? 0} pts · {it.estado}
              </small>
            </button>
            {open === it.id && (
              <div className="auto-draft">
                {it.borrador ? <pre>{it.borrador}</pre> : <p className="auto-note">Sin borrador todavía.</p>}
                <div className="auto-inline">
                  {it.url && (
                    <a className="paper-button" data-variant="quiet" href={it.url} target="_blank" rel="noopener noreferrer">
                      Abrir
                    </a>
                  )}
                  {it.borrador && (
                    <button className="paper-button" data-variant="quiet" onClick={() => void navigator.clipboard?.writeText(it.borrador || '').then(() => toast.success('Copiado.'))}>
                      Copiar borrador
                    </button>
                  )}
                  {(['enviada', 'descartada'] as const).map((s) => (
                    <button key={s} className="paper-button" data-variant="quiet" disabled={!!busy} onClick={() => void act('estado', () => call(`/oportunidades/${it.id}`, 'PUT', { estado: s }).then(load))}>
                      {s === 'enviada' ? 'La envié yo' : 'Descartar'}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </li>
        ))}
        {!items.length && <li className="auto-empty">Aún no hay resultados.</li>}
      </ul>
      <p className="auto-note">Las propuestas son borradores: usted las revisa y las envía.</p>
    </Card>
  );
}

function Trading({ st, busy, act }: { st: Estado | null; busy: string; act: Act }) {
  const t = st?.trading;
  const [symbol, setSymbol] = useState('SPY');
  const [test, setTest] = useState<Record<string, unknown> | null>(null);
  const strategy = t?.estrategia || 'cruce_medias';
  return (
    <Card icon={LineChart} title="Trading">
      <div className="auto-rows">
        <div className="auto-row">
          <b>Estado</b>
          <span>
            {!t ? '…' : t.detenido ? 'Detenido' : t.activo ? (t.dinero_real ? 'Dinero real' : 'En papel') : 'Apagado'}
          </span>
          {t?.detenido ? (
            <button className="paper-button" disabled={!!busy} onClick={() => void act('reanudar', () => call('/trading/reanudar', 'POST'))}>
              Reanudar
            </button>
          ) : (
            <button className="paper-button" data-variant="quiet" disabled={!!busy} onClick={() => void act('detener', () => call('/trading/detener', 'POST'), 'Trading detenido.')}>
              Detener todo
            </button>
          )}
        </div>
        {!t?.broker && <p className="auto-note">Falta la cuenta del bróker (claves de Alpaca en sergio.env).</p>}
      </div>
      <div className="auto-inline">
        <select className="paper-select" value={strategy} aria-label="Estrategia" onChange={(e) => void act('ajuste', () => call('/trading', 'PUT', { estrategia: e.target.value }))}>
          <option value="cruce_medias">Cruce de medias</option>
          <option value="momentum">Momentum</option>
          <option value="reversion">Reversión</option>
        </select>
        <button className="paper-button" disabled={!!busy || !t} onClick={() => void act('activo', () => call('/trading', 'PUT', { activo: !t?.activo, real: false }))}>
          {t?.activo ? 'Apagar' : 'Activar en papel'}
        </button>
      </div>
      <div className="auto-inline">
        <input className="paper-input" value={symbol} aria-label="Símbolo" onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
        <button
          className="paper-button"
          data-variant="quiet"
          disabled={!!busy}
          onClick={() => void act('prueba', () => call<Record<string, unknown>>('/trading/prueba', 'POST', { simbolo: symbol, estrategia: strategy }).then(setTest))}
        >
          {busy === 'prueba' ? 'Probando…' : 'Probar con el pasado'}
        </button>
      </div>
      {test && (
        <div className="auto-stats">
          <span>
            <b>{pct(test.rentabilidad)}</b>
            <small>total</small>
          </span>
          <span>
            <b>{pct(test.anual)}</b>
            <small>al año</small>
          </span>
          <span>
            <b>{pct(test.peor_caida)}</b>
            <small>peor caída</small>
          </span>
          <span>
            <b>{String(test.operaciones)}</b>
            <small>operaciones</small>
          </span>
        </div>
      )}
      <p className="auto-note">{t?.aviso}</p>
    </Card>
  );
}

function Health() {
  const [d, setD] = useState<{ resumen: string; chequeos: Check[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    call<{ resumen: string; chequeos: Check[] }>('/estabilidad')
      .then(setD)
      .catch(() => setD(null));
  }, []);
  useEffect(load, [load]);
  return (
    <Card icon={Activity} title="Estabilidad">
      <p>{d?.resumen ?? '…'}</p>
      <ul className="auto-list">
        {d?.chequeos.map((c) => (
          <li key={c.nombre} data-state={c.estado}>
            <span>
              <i className="auto-dot" aria-hidden="true" /> {c.nombre}
            </span>
            <small>{c.arreglo || c.detalle}</small>
          </li>
        ))}
      </ul>
      <button
        className="paper-button"
        data-variant="quiet"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const r = await call<{ liberado_mb: number }>('/estabilidad/reparar', 'POST');
            toast.success(`Reparado: ${r.liberado_mb} MB libres de nuevo.`);
            load();
          } catch (e) {
            toast.error(e instanceof Error ? e.message : 'No se pudo.');
          } finally {
            setBusy(false);
          }
        }}
      >
        Reparar ahora
      </button>
    </Card>
  );
}

export default AutomatizarPage;
