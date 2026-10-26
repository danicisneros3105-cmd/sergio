// «Cambiar de modelo», simply: every Gemini chat model this key can use and
// how hard Sergio thinks. A change plays the model moment (lib/celebrate.ts).
// Local models and API keys stay one tap away under «Avanzado» (the older
// CommandPalette). Without a Google key, Sergio says how to connect one's own
// account in three steps: the person's key, the person's usage — nobody
// creates accounts or keys for them.

import { useEffect, useState } from 'react';
import { Check, ExternalLink, X } from 'lucide-react';
import { useAppStore } from '../lib/store';
import { CommandPalette } from './CommandPalette';
import { celebrate } from '../lib/celebrate';
import { EFFORTS, fetchModelOptions, modelName, type Effort, type ModelOption } from '../lib/modelChoice';
import { getCloudKeyStatus, saveCloudKey, fetchModels } from '../lib/api';

export function ModelSheet() {
  const [advanced, setAdvanced] = useState(false);
  const [models, setModels] = useState<ModelOption[] | null>(null);
  const [problem, setProblem] = useState('');
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  const [key, setKey] = useState('');
  const selected = useAppStore((s) => s.selectedModel);
  const setSelected = useAppStore((s) => s.setSelectedModel);
  const effort = useAppStore((s) => s.settings.effort);
  const updateSettings = useAppStore((s) => s.updateSettings);
  const close = () => useAppStore.getState().setCommandPaletteOpen(false);

  useEffect(() => {
    fetchModelOptions()
      .then((d) => setModels(d.modelos))
      .catch(() => setProblem('Sergio no responde ahora; pruebe en un momento.'));
    getCloudKeyStatus()
      .then((s) => setHasKey(Boolean(s.GEMINI_API_KEY || s.GOOGLE_API_KEY)))
      .catch(() => setHasKey(null));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (advanced) return <CommandPalette />;

  const pick = (m: ModelOption) => {
    if (!m.disponible) return;
    if (m.id !== selected) {
      setSelected(m.id);
      celebrate({ kind: 'model', title: m.nombre, detail: 'Ahora piensa con este modelo.' });
    }
    close();
  };
  const pickEffort = (id: Effort) => {
    if (id === effort) return;
    updateSettings({ effort: id });
    const e = EFFORTS.find((x) => x.id === id);
    celebrate({ kind: 'model', title: `${modelName(selected, models ?? [])} · ${e?.nombre ?? id}`, detail: e?.para });
  };
  const connect = async () => {
    if (!key.trim()) return;
    try {
      await saveCloudKey('GEMINI_API_KEY', key.trim());
      setKey('');
      setHasKey(true);
      useAppStore.getState().setModels(await fetchModels());
      const d = await fetchModelOptions();
      setModels(d.modelos);
      celebrate({ kind: 'connector', title: 'Google conectado', detail: 'Sergio ya usa su propia cuenta.', brand: { name: 'Google Gemini', id: 'googlegemini' } });
    } catch (e) {
      setProblem((e as Error).message || 'No se pudo guardar la clave.');
    }
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

        {hasKey === false && (
          <div className="msheet-connect">
            <p><b>Use su propia cuenta de Google.</b> Es gratis para empezar y su uso queda en su cuenta.</p>
            <ol>
              <li><a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Abra Google AI Studio <ExternalLink size={12} /></a> y pulse «Create API key».</li>
              <li>Copie la clave y péguela aquí.</li>
            </ol>
            <div className="msheet-keyrow">
              <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Su clave de Google" aria-label="Clave de Google" />
              <button type="button" className="msheet-primary" onClick={() => void connect()} disabled={!key.trim()}>Conectar</button>
            </div>
          </div>
        )}

        <ul className="msheet-list">
          {(models ?? []).map((m) => (
            <li key={m.id}>
              <button type="button" disabled={!m.disponible} aria-current={m.id === selected} onClick={() => pick(m)}>
                <span className="msheet-name">{m.nombre}</span>
                {m.para && <span className="msheet-for">{m.para}</span>}
                {!m.disponible && <span className="msheet-for">No disponible con esta clave</span>}
                {m.id === selected && <Check size={16} className="msheet-check" aria-hidden />}
              </button>
            </li>
          ))}
          {!models && !problem && <li className="msheet-for">Cargando…</li>}
        </ul>
        {problem && <p className="msheet-problem">{problem}</p>}
        <button type="button" className="msheet-advanced" onClick={() => setAdvanced(true)}>Avanzado: modelos locales y claves</button>
      </div>
    </div>
  );
}
