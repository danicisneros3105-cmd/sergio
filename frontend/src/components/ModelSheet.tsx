// «Cambiar de modelo», simply: the chat models of every company Sergio can use
// (Google, OpenAI, Anthropic, DeepSeek and any other through OpenRouter),
// grouped by company, and how hard Sergio thinks. A company without its key
// shows one line to connect it (the key goes to this computer's settings).
// «Otro modelo» takes any model id. A change plays the model moment
// (lib/celebrate.ts). Local models stay under «Avanzado» (the older palette).

import { useEffect, useMemo, useState } from 'react';
import { Check, ExternalLink, X } from 'lucide-react';
import { useAppStore } from '../lib/store';
import { CommandPalette } from './CommandPalette';
import { celebrate } from '../lib/celebrate';
import { EFFORTS, fetchModelOptions, modelName, type Company, type Effort, type ModelOption } from '../lib/modelChoice';
import { saveCloudKey, fetchModels } from '../lib/api';

export function ModelSheet() {
  const [advanced, setAdvanced] = useState(false);
  const [models, setModels] = useState<ModelOption[] | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [problem, setProblem] = useState('');
  const [open, setOpen] = useState<string>('');
  const [key, setKey] = useState('');
  const [other, setOther] = useState('');
  const selected = useAppStore((s) => s.selectedModel);
  const setSelected = useAppStore((s) => s.setSelectedModel);
  const effort = useAppStore((s) => s.settings.effort);
  const updateSettings = useAppStore((s) => s.updateSettings);
  const close = () => useAppStore.getState().setCommandPaletteOpen(false);

  const load = () =>
    fetchModelOptions()
      .then((d) => {
        setModels(d.modelos);
        setCompanies(d.empresas ?? []);
      })
      .catch(() => setProblem('Sergio no responde ahora; pruebe en un momento.'));
  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const groups = useMemo(() => {
    const list = companies.length ? companies : [{ id: 'google', nombre: 'Google', clave: 'GEMINI_API_KEY', donde: '', conectada: true }];
    return list.map((c) => ({ company: c, models: (models ?? []).filter((m) => (m.empresa ?? 'google') === c.id) }));
  }, [companies, models]);

  if (advanced) return <CommandPalette />;

  const choose = (id: string, name: string) => {
    if (id !== selected) {
      setSelected(id);
      celebrate({ kind: 'model', title: name, detail: 'Ahora piensa con este modelo.' });
    }
    close();
  };
  const pickEffort = (id: Effort) => {
    if (id === effort) return;
    updateSettings({ effort: id });
    const e = EFFORTS.find((x) => x.id === id);
    celebrate({ kind: 'model', title: `${modelName(selected, models ?? [])} · ${e?.nombre ?? id}`, detail: e?.para });
  };
  const connect = async (c: Company) => {
    if (!key.trim()) return;
    try {
      await saveCloudKey(c.clave, key.trim());
      setKey('');
      setOpen('');
      useAppStore.getState().setModels(await fetchModels());
      await load();
      celebrate({ kind: 'connector', title: `${c.nombre} conectado`, detail: 'Ya puede elegir sus modelos.' });
    } catch (e) {
      setProblem((e as Error).message || 'No se pudo guardar la clave.');
    }
  };
  const useOther = () => {
    const id = other.trim();
    if (!id) return;
    // A bare «vendor/model» is an OpenRouter id.
    const full = id.includes('/') && !id.startsWith('openrouter/') ? `openrouter/${id}` : id;
    choose(full, modelName(full));
  };

  return (
    <div className="msheet-layer" onClick={close}>
      <div className="msheet" role="dialog" aria-label="Modelo" onClick={(e) => e.stopPropagation()}>
        <header className="msheet-head">
          <h2>Modelo</h2>
          <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={close}><X size={18} /></button>
        </header>

        <div className="msheet-effort" role="radiogroup" aria-label="Esfuerzo">
          {EFFORTS.map((e) => (
            <button key={e.id} type="button" role="radio" aria-checked={effort === e.id} title={e.para} onClick={() => pickEffort(e.id)}>
              {e.nombre}
            </button>
          ))}
        </div>

        <div className="msheet-scroll">
          {groups.map(({ company: c, models: list }) => (
            <section key={c.id} className="msheet-group">
              <h3>
                {c.nombre}
                {!c.conectada && (
                  <button type="button" className="msheet-advanced" onClick={() => { setOpen(open === c.id ? '' : c.id); setKey(''); }}>
                    Conectar
                  </button>
                )}
              </h3>
              {open === c.id && (
                <div className="msheet-connect">
                  <p>
                    <a href={c.donde} target="_blank" rel="noreferrer">Cree su clave en {c.nombre} <ExternalLink size={12} /></a> y péguela aquí. El uso queda en su cuenta.
                  </p>
                  <div className="msheet-keyrow">
                    <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder={`Clave de ${c.nombre}`} aria-label={`Clave de ${c.nombre}`} />
                    <button type="button" className="msheet-primary" onClick={() => void connect(c)} disabled={!key.trim()}>Conectar</button>
                  </div>
                </div>
              )}
              <ul className="msheet-list">
                {list.map((m) => (
                  <li key={m.id}>
                    <button type="button" disabled={!m.disponible} aria-current={m.id === selected} onClick={() => m.disponible && choose(m.id, m.nombre)}>
                      <span className="msheet-name">{m.nombre}</span>
                      {m.para && <span className="msheet-for">{m.para}</span>}
                      {(m.cuenta ?? 1) > 1 && <span className="msheet-for">Cada respuesta cuenta como {m.cuenta} mensajes</span>}
                      {m.id === selected && <Check size={16} className="msheet-check" aria-hidden />}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {!models && !problem && <p className="msheet-for">Cargando…</p>}
          <section className="msheet-group">
            <h3>Otro modelo</h3>
            <div className="msheet-keyrow">
              <input value={other} onChange={(e) => setOther(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && useOther()} placeholder="Por ejemplo: mistralai/mistral-small" aria-label="Otro modelo" />
              <button type="button" className="msheet-primary" onClick={useOther} disabled={!other.trim()}>Usar</button>
            </div>
          </section>
        </div>
        {problem && <p className="msheet-problem">{problem}</p>}
        <button type="button" className="msheet-advanced" onClick={() => setAdvanced(true)}>Avanzado: modelos en este equipo</button>
      </div>
    </div>
  );
}
