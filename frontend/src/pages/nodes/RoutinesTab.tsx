import { useState } from 'react';
import { Plus, RefreshCw, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { describeRoutine, nodesApi, relative, type SergioNode } from '../../lib/nodes';

const DAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

export function RoutinesTab({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const [task, setTask] = useState('');
  const [kind, setKind] = useState<'time' | 'web' | 'app'>('time');
  const [mode, setMode] = useState<'every' | 'at'>('at');
  const [every, setEvery] = useState(60);
  const [at, setAt] = useState('08:00');
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [url, setUrl] = useState('');
  const [app, setApp] = useState(Object.keys(node.apps)[0] || '');
  const [keywords, setKeywords] = useState('');
  const add = async () => {
    try {
      const body =
        kind === 'web'
          ? { task, kind, url, every_minutes: every }
          : kind === 'app'
            ? { task, kind, app, keywords: keywords.split(',').map((k) => k.trim()).filter(Boolean), every_minutes: every }
            : mode === 'every'
              ? { task, every_minutes: every }
              : { task, at, days };
      await nodesApi.addRoutine(node.id, body);
      setTask('');
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude.');
    }
  };
  const everySelect = (
    <select className="paper-input node-time" value={every} onChange={(e) => setEvery(Number(e.target.value))} aria-label="Cada">
      {[15, 30, 60, 120, 240, 720, 1440].map((m) => (
        <option key={m} value={m}>
          {describeRoutine({ every_minutes: m, at: '', days: [] })}
        </option>
      ))}
    </select>
  );
  return (
    <div className="node-routines">
      <p className="node-hint">
        Trabajo que {node.name} repite solo, aunque usted no esté. Las vigilancias las revisa el código: {node.name} solo
        despierta cuando algo cambió de verdad.
      </p>
      <ul>
        {node.routines.map((r) => (
          <li key={r.id}>
            <span className="node-routine-when">{describeRoutine(r)}</span>
            <span className="flex-1">{r.task}</span>
            <button type="button" className="mac-icon-btn" title={r.last_error || ''}
              aria-label={r.enabled ? 'Pausar rutina' : 'Reanudar rutina'}
              onClick={() => void nodesApi.setRoutineEnabled(node.id, r.id, !r.enabled)
                .then(onChanged).catch(() => toast('No pude cambiar la rutina.'))}>
              {r.enabled ? 'Pausar' : `Reanudar${r.failures ? ` (${r.failures} fallos)` : ''}`}
            </button>
            {(r.last_check || r.last_run) > 0 && <span className="node-hint">{relative(r.last_check || r.last_run)}</span>}
            {r.kind && r.kind !== 'time' && (
              <button
                type="button"
                className="mac-icon-btn"
                aria-label="Revisar ahora"
                title="Revisar ahora"
                onClick={async () => {
                  const out = await nodesApi.checkRoutine(node.id, r.id).catch(() => null);
                  toast(out?.error ? `No pude revisar: ${out.error}` : out?.woke ? 'Hubo cambios: se puso a trabajar.' : 'Sin cambios.');
                  onChanged();
                }}
              >
                <RefreshCw size={14} />
              </button>
            )}
            <button type="button" className="mac-icon-btn" aria-label="Quitar rutina" onClick={async () => (await nodesApi.removeRoutine(node.id, r.id), onChanged())}>
              <Trash2 size={14} />
            </button>
          </li>
        ))}
      </ul>
      <div className="node-routine-form">
        <div className="node-seg" role="radiogroup" aria-label="Tipo">
          {(
            [
              ['time', 'Por horario'],
              ['web', 'Vigilar una web'],
              ['app', 'Cuando llegue algo a una app'],
            ] as const
          ).map(([k, label]) => (
            <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}>
              {label}
            </button>
          ))}
        </div>
        <input
          className="paper-input"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder={kind === 'web' ? 'Ej. Si bajó el precio, dime cuánto' : kind === 'app' ? 'Ej. ¿Es urgente? Prepárame un borrador' : 'Ej. Resumen del correo y la agenda'}
        />
        <div className="node-routine-when-row">
          {kind === 'web' && (
            <>
              <input className="paper-input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" aria-label="Dirección" />
              {everySelect}
            </>
          )}
          {kind === 'app' && (
            <>
              <select className="paper-input node-time" value={app} onChange={(e) => setApp(e.target.value)} aria-label="App">
                {Object.keys(node.apps).length ? (
                  Object.keys(node.apps).map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))
                ) : (
                  <option value="">Dele acceso a una app primero</option>
                )}
              </select>
              <input className="paper-input" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="Palabras clave (opcional, con comas)" aria-label="Palabras clave" />
              {everySelect}
            </>
          )}
          {kind === 'time' && (
            <>
              <div className="node-seg" role="radiogroup" aria-label="Cuándo">
                <button type="button" role="radio" aria-checked={mode === 'at'} onClick={() => setMode('at')}>
                  A una hora
                </button>
                <button type="button" role="radio" aria-checked={mode === 'every'} onClick={() => setMode('every')}>
                  Cada cierto tiempo
                </button>
              </div>
              {mode === 'at' ? (
                <>
                  <input className="paper-input node-time" type="time" value={at} onChange={(e) => setAt(e.target.value)} aria-label="Hora" />
                  <div className="node-days">
                    {DAYS.map((d, i) => (
                      <button
                        key={i}
                        type="button"
                        aria-pressed={days.includes(i)}
                        aria-label={['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][i]}
                        onClick={() => setDays(days.includes(i) ? days.filter((x) => x !== i) : [...days, i].sort())}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                everySelect
              )}
            </>
          )}
          <button type="button" className="paper-button" onClick={add} disabled={!task.trim()}>
            <Plus size={14} /> Añadir
          </button>
        </div>
      </div>
    </div>
  );
}
