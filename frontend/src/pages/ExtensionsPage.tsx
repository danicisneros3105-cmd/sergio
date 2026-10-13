// Extensiones: everything Sergio can add to itself, in one minimal list.
// Programas · Plugins · Skills · Conectores.

import { useCallback, useEffect, useState } from 'react';
import { NavLink, useNavigate, useParams } from 'react-router';
import { AppWindow, BookOpen, Check, Loader2, Plug, Puzzle, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { usePrograms } from '../components/Creator/Programs';
import { installProgram, openProgram, programState, type Program } from '../lib/creatorPrograms';
import { fetchHub, installPlugin, learnSkill, prettyName, removePlugin, setPluginEnabled, type HubPlugin, type HubSkill } from '../lib/hub';
import { listConnectors } from '../lib/connectors-api';
import type { ConnectorInfo } from '../types/connectors';

const TABS = [
  { id: 'programas', label: 'Programas', icon: AppWindow },
  { id: 'plugins', label: 'Plugins', icon: Puzzle },
  { id: 'skills', label: 'Skills', icon: BookOpen },
  { id: 'conectores', label: 'Conectores', icon: Plug },
] as const;
type Tab = (typeof TABS)[number]['id'];

function fail(e: unknown) {
  toast.error(e instanceof Error ? e.message : String(e));
}

function Row({ name, title, on, children }: { name: string; title?: string; on?: boolean; children?: React.ReactNode }) {
  return (
    <li className="ext-row" title={title}>
      <span className="ext-dot" data-on={on || undefined} aria-hidden />
      <span className="ext-name">{name}</span>
      <span className="ext-actions">{children}</span>
    </li>
  );
}

function Programs() {
  const { programs, reload } = usePrograms();
  const [busy, setBusy] = useState('');
  const act = async (p: Program, fn: () => Promise<{ message?: string }>) => {
    setBusy(p.id);
    try {
      const out = await fn();
      if (out.message) toast.success(out.message);
      reload();
    } catch (e) {
      fail(e);
    } finally {
      setBusy('');
    }
  };
  if (!programs) return <Loader2 className="ext-spin" size={18} />;
  return (
    <ul className="ext-list">
      {programs.map((p) => {
        const state = programState(p);
        return (
          <Row key={p.id} name={p.name} title={p.what} on={state === 'listo'}>
            {state === 'instalando' || busy === p.id ? (
              <Loader2 className="ext-spin" size={16} />
            ) : state === 'listo' ? (
              p.where === 'windows' ? (
                <button type="button" className="ext-btn" onClick={() => act(p, () => openProgram(p.id))}>
                  Abrir
                </button>
              ) : (
                <Check size={16} aria-label="Instalado" />
              )
            ) : state === 'falta' ? (
              <button type="button" className="ext-btn" data-primary onClick={() => act(p, () => installProgram(p.id))}>
                Instalar
              </button>
            ) : null}
          </Row>
        );
      })}
    </ul>
  );
}

function PermissionSheet({ plugin, onClose, onDone }: { plugin: HubPlugin; onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="ext-sheet" role="dialog" aria-modal="true" aria-label={prettyName(plugin.name)}>
      <div className="ext-sheet-card">
        <button type="button" className="ext-x" aria-label="Cerrar" onClick={onClose}>
          <X size={16} />
        </button>
        <h2>{prettyName(plugin.name)}</h2>
        <ul className="ext-perms">
          {plugin.permissions.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
        <button
          type="button"
          className="ext-btn"
          data-primary
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await installPlugin(plugin.name, true);
              onDone();
            } catch (e) {
              fail(e);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <Loader2 className="ext-spin" size={15} /> : 'Permitir e instalar'}
        </button>
      </div>
    </div>
  );
}

function Plugins({ plugins, reload }: { plugins: HubPlugin[]; reload: () => void }) {
  const [asking, setAsking] = useState<HubPlugin | null>(null);
  const install = async (p: HubPlugin) => {
    if (p.permissions.length) return setAsking(p);
    try {
      await installPlugin(p.name, false);
      reload();
    } catch (e) {
      fail(e);
    }
  };
  return (
    <>
      <ul className="ext-list">
        {plugins.map((p) => (
          <Row key={p.name} name={prettyName(p.name)} title={p.description} on={p.installed && p.enabled}>
            {p.installed ? (
              <>
                <button
                  type="button"
                  role="switch"
                  aria-checked={p.enabled}
                  aria-label={`${prettyName(p.name)} activo`}
                  className="ext-switch"
                  onClick={() => setPluginEnabled(p.name, !p.enabled).then(reload, fail)}
                />
                <button type="button" className="ext-icon" aria-label="Quitar" onClick={() => removePlugin(p.name).then(reload, fail)}>
                  <Trash2 size={15} />
                </button>
              </>
            ) : (
              <button type="button" className="ext-btn" data-primary onClick={() => void install(p)}>
                Instalar
              </button>
            )}
          </Row>
        ))}
      </ul>
      {asking && (
        <PermissionSheet
          plugin={asking}
          onClose={() => setAsking(null)}
          onDone={() => {
            setAsking(null);
            reload();
          }}
        />
      )}
    </>
  );
}

function Skills({ skills, reload }: { skills: HubSkill[]; reload: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [text, setText] = useState('');
  const [pdf, setPdf] = useState<File | undefined>();
  const [busy, setBusy] = useState(false);
  return (
    <>
      <ul className="ext-list">
        {skills.map((s) => (
          <Row key={s.name} name={prettyName(s.name)} title={s.keys.join(' · ')} on />
        ))}
        <li>
          <button type="button" className="ext-add" onClick={() => setOpen(true)}>
            + Enseñar una skill
          </button>
        </li>
      </ul>
      {open && (
        <div className="ext-sheet" role="dialog" aria-modal="true" aria-label="Enseñar una skill">
          <form
            className="ext-sheet-card"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                await learnSkill(name.trim() || 'manual', text, pdf);
                setOpen(false);
                setName('');
                setText('');
                setPdf(undefined);
                reload();
              } catch (err) {
                fail(err);
              } finally {
                setBusy(false);
              }
            }}
          >
            <button type="button" className="ext-x" aria-label="Cerrar" onClick={() => setOpen(false)}>
              <X size={16} />
            </button>
            <h2>Skill</h2>
            <input className="ext-input" placeholder="Nombre" value={name} onChange={(e) => setName(e.target.value)} />
            <textarea className="ext-input" rows={6} placeholder="Instrucciones" value={text} onChange={(e) => setText(e.target.value)} />
            <input type="file" accept="application/pdf" aria-label="PDF" onChange={(e) => setPdf(e.target.files?.[0])} />
            <button type="submit" className="ext-btn" data-primary disabled={busy || (!text.trim() && !pdf)}>
              {busy ? <Loader2 className="ext-spin" size={15} /> : 'Enseñar'}
            </button>
          </form>
        </div>
      )}
    </>
  );
}

function Connectors() {
  const [list, setList] = useState<ConnectorInfo[] | null>(null);
  const navigate = useNavigate();
  useEffect(() => {
    listConnectors().then(setList, () => setList([]));
  }, []);
  if (!list) return <Loader2 className="ext-spin" size={18} />;
  return (
    <ul className="ext-list">
      {[...list]
        .sort((a, b) => Number(b.connected) - Number(a.connected) || a.display_name.localeCompare(b.display_name, 'es'))
        .map((c) => (
          <Row key={c.connector_id} name={c.display_name} on={c.connected}>
            <button
              type="button"
              className="ext-btn"
              data-primary={!c.connected || undefined}
              onClick={() => navigate(`/data-sources?connect=${encodeURIComponent(c.connector_id)}`)}
            >
              {c.connected ? 'Ajustes' : 'Conectar'}
            </button>
          </Row>
        ))}
    </ul>
  );
}

export function ExtensionsPage() {
  const { tab } = useParams();
  const current: Tab = (TABS.find((t) => t.id === tab)?.id ?? 'programas') as Tab;
  const [hub, setHub] = useState<{ plugins: HubPlugin[]; skills: HubSkill[] }>({ plugins: [], skills: [] });
  const reload = useCallback(() => {
    fetchHub().then(setHub, fail);
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  return (
    <div className="ext-page">
      <h1 className="ext-title">Extensiones</h1>
      <nav className="ext-tabs" aria-label="Extensiones">
        {TABS.map(({ id, label, icon: Icon }) => (
          <NavLink key={id} to={`/extensiones/${id}`} className="ext-tab" aria-current={current === id ? 'page' : undefined}>
            <Icon size={15} strokeWidth={1.8} />
            {label}
          </NavLink>
        ))}
      </nav>
      {current === 'programas' && <Programs />}
      {current === 'plugins' && <Plugins plugins={hub.plugins} reload={reload} />}
      {current === 'skills' && <Skills skills={hub.skills} reload={reload} />}
      {current === 'conectores' && <Connectors />}
    </div>
  );
}

export default ExtensionsPage;
