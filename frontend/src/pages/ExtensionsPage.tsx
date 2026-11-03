// Extensiones: everything Sergio can add to itself, in one minimal list.
// Conectores · Programas · Plugins · Skills (laid out like Claude's).

import { useCallback, useEffect, useState } from 'react';
import { NavLink, useParams } from 'react-router';
import { AppWindow, BookOpen, Check, Loader2, Plug, Puzzle, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { usePrograms } from '../components/Creator/Programs';
import { installProgram, openProgram, programState, type Program } from '../lib/creatorPrograms';
import { fetchHub, installPlugin, learnSkill, prettyName, removePlugin, setPluginEnabled, type HubPlugin, type HubSkill } from '../lib/hub';
import { ConnectorsPanel } from '../components/Extensions/ConnectorsPanel';
import { ExtensionSheet as Sheet } from '../components/Extensions/ExtensionSheet';
import { PluginsPanel } from '../components/Extensions/PluginsPanel';

const TABS = [
  { id: 'conectores', label: 'Conectores', icon: Plug },
  { id: 'programas', label: 'Programas', icon: AppWindow },
  { id: 'plugins', label: 'Plugins', icon: Puzzle },
  { id: 'skills', label: 'Skills', icon: BookOpen },
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
    <Sheet label={prettyName(plugin.name)} onClose={onClose}>
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
    </Sheet>
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
        <Sheet label="Enseñar una skill" onClose={() => setOpen(false)}>
          <form
            className="cx-form"
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
            <h2 className="cx-h2">Skill</h2>
            <input className="ext-input" aria-label="Nombre de la skill" placeholder="Nombre" value={name} onChange={(e) => setName(e.target.value)} />
            <textarea className="ext-input" rows={6} aria-label="Instrucciones de la skill" placeholder="Instrucciones" value={text} onChange={(e) => setText(e.target.value)} />
            <input type="file" accept="application/pdf" aria-label="PDF" onChange={(e) => setPdf(e.target.files?.[0])} />
            <button type="submit" className="ext-btn" data-primary disabled={busy || (!text.trim() && !pdf)}>
              {busy ? <Loader2 className="ext-spin" size={15} /> : 'Enseñar'}
            </button>
          </form>
        </Sheet>
      )}
    </>
  );
}

/** *embedded*: inside Configuración → Personalizar (tabs kept in the page, no route). */
export function ExtensionsPage({ embedded = false }: { embedded?: boolean } = {}) {
  const { tab } = useParams();
  const [own, setOwn] = useState<Tab>('conectores');
  const current: Tab = embedded ? own : ((TABS.find((t) => t.id === tab)?.id ?? 'conectores') as Tab);
  const [hub, setHub] = useState<{ plugins: HubPlugin[]; skills: HubSkill[] }>({ plugins: [], skills: [] });
  const reload = useCallback(() => {
    fetchHub().then(setHub, fail);
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  return (
    <div className={embedded ? 'ext-page ext-embedded' : 'ext-page'}>
      {!embedded && <h1 className="ext-title">Extensiones</h1>}
      <nav className="ext-tabs" aria-label="Extensiones">
        {TABS.map(({ id, label, icon: Icon }) =>
          embedded ? (
            <button key={id} type="button" className="ext-tab" aria-current={current === id ? 'page' : undefined} onClick={() => setOwn(id)}>
              <Icon size={15} strokeWidth={1.8} />
              {label}
            </button>
          ) : (
            <NavLink key={id} to={`/extensiones/${id}`} className="ext-tab" aria-current={current === id ? 'page' : undefined}>
              <Icon size={15} strokeWidth={1.8} />
              {label}
            </NavLink>
          ),
        )}
      </nav>
      {current === 'programas' && <Programs />}
      {current === 'plugins' && (
        <PluginsPanel
          legacy={
            hub.plugins.length > 0 ? (
              <section className="cx-section">
                <h3 className="cx-legacy">Plugins de Sergio</h3>
                <Plugins plugins={hub.plugins} reload={reload} />
              </section>
            ) : null
          }
        />
      )}
      {current === 'skills' && <Skills skills={hub.skills} reload={reload} />}
      {current === 'conectores' && <ConnectorsPanel />}
    </div>
  );
}

export default ExtensionsPage;
