// Create an automation in three choices: when, what, who. A simple one is one
// sentence; a complex one adds steps. A template fills it in one tap; the
// sentence underneath says exactly what will happen before it is created.
import { useEffect, useMemo, useState } from 'react';
import { Minus, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { nodesApi, SHAPE_ES, type SergioNode } from '../../lib/nodes';
import {
  ALL_DAYS,
  problem,
  QUICK_WHEN,
  sentence,
  TEMPLATES,
  toRoutine,
  type Draft,
  type Template,
  type When,
} from '../../lib/automation';

const DAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

function sameWhen(a: When, b: When): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === 'every' && b.kind === 'every') return a.minutes === b.minutes;
  if (a.kind === 'at' && b.kind === 'at') return a.at === b.at && [...a.days].sort().join() === [...b.days].sort().join();
  return a.kind === 'web';
}

export function Builder({ nodes, onCreated }: { nodes: SergioNode[]; onCreated: () => void }) {
  const [draft, setDraft] = useState<Draft>({ when: QUICK_WHEN[0].when, steps: [''], node: '' });
  const [busy, setBusy] = useState(false);
  const many = draft.steps.length > 1;

  useEffect(() => {
    if (!draft.node && nodes.length) {
      const rihno = nodes.find((n) => n.avatar?.shape === 'rhino') || nodes[0];
      setDraft((d) => ({ ...d, node: rihno.id }));
    }
  }, [nodes, draft.node]);

  const nodeName = useMemo(() => nodes.find((n) => n.id === draft.node)?.name || 'Sergio', [nodes, draft.node]);
  const missing = problem(draft);
  const setWhen = (when: When) => setDraft((d) => ({ ...d, when }));
  const setStep = (i: number, v: string) => setDraft((d) => ({ ...d, steps: d.steps.map((s, j) => (j === i ? v : s)) }));

  const useTemplate = (t: Template) => {
    const n = nodes.find((x) => x.avatar?.shape === t.node);
    setDraft({ when: t.when, steps: [...t.steps], node: n?.id || draft.node });
    document.getElementById('auto-what-0')?.focus();
  };

  const create = async () => {
    if (missing) return;
    setBusy(true);
    try {
      await nodesApi.addRoutine(draft.node, toRoutine(draft));
      toast.success(`Lista: ${sentence(draft, nodeName)}`);
      setDraft((d) => ({ ...d, steps: [''] }));
      onCreated();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude crearla.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ab">
      <div className="ab-templates" role="list" aria-label="Plantillas">
        {TEMPLATES.map((t) => (
          <button key={t.id} type="button" role="listitem" className="ab-template" onClick={() => useTemplate(t)}>
            <b>{t.title}</b>
            <small>{SHAPE_ES[t.node]}</small>
          </button>
        ))}
      </div>

      <form
        className="ab-card"
        onSubmit={(e) => {
          e.preventDefault();
          void create();
        }}
      >
        <fieldset className="ab-step">
          <legend>
            <span>1</span> Cuándo
          </legend>
          <div className="ab-chips">
            {QUICK_WHEN.map((q) => (
              <button key={q.id} type="button" aria-pressed={sameWhen(draft.when, q.when)} onClick={() => setWhen(q.when)}>
                {q.label}
              </button>
            ))}
          </div>
          {draft.when.kind === 'at' && (
            <div className="ab-row">
              <input
                type="time"
                aria-label="Hora"
                value={draft.when.at}
                onChange={(e) => draft.when.kind === 'at' && setWhen({ ...draft.when, at: e.target.value })}
              />
              <div className="ab-days" role="group" aria-label="Días">
                {DAYS.map((d, i) => {
                  const w = draft.when as Extract<When, { kind: 'at' }>;
                  const on = w.days.includes(i);
                  return (
                    <button
                      key={d}
                      type="button"
                      aria-pressed={on}
                      aria-label={['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][i]}
                      onClick={() => {
                        const days = on ? w.days.filter((x) => x !== i) : [...w.days, i];
                        setWhen({ ...w, days: days.length ? days : ALL_DAYS });
                      }}
                    >
                      {d}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {draft.when.kind === 'web' && (
            <div className="ab-row">
              <input
                type="url"
                inputMode="url"
                placeholder="https://… la página que vigilo"
                aria-label="Página que vigilo"
                value={draft.when.url}
                onChange={(e) => draft.when.kind === 'web' && setWhen({ ...draft.when, url: e.target.value })}
              />
            </div>
          )}
        </fieldset>

        <fieldset className="ab-step">
          <legend>
            <span>2</span> Qué
          </legend>
          {draft.steps.map((s, i) => (
            <div key={i} className="ab-what">
              {many && <i aria-hidden="true">{i + 1}</i>}
              <input
                id={`auto-what-${i}`}
                value={s}
                placeholder={i === 0 ? 'Por ejemplo: resúmeme los correos sin leer' : 'Y después…'}
                aria-label={many ? `Paso ${i + 1}` : 'Qué debe hacer'}
                onChange={(e) => setStep(i, e.target.value)}
              />
              {many && (
                <button
                  type="button"
                  className="ab-icon"
                  aria-label={`Quitar el paso ${i + 1}`}
                  onClick={() => setDraft((d) => ({ ...d, steps: d.steps.filter((_, j) => j !== i) }))}
                >
                  <Minus size={14} />
                </button>
              )}
            </div>
          ))}
          {draft.steps.length < 8 && (
            <button type="button" className="ab-add" onClick={() => setDraft((d) => ({ ...d, steps: [...d.steps, ''] }))}>
              <Plus size={14} /> {many ? 'Otro paso' : 'Añadir un paso (automatización con varios pasos)'}
            </button>
          )}
        </fieldset>

        <fieldset className="ab-step">
          <legend>
            <span>3</span> Quién
          </legend>
          <div className="ab-chips">
            {nodes.map((n) => (
              <button key={n.id} type="button" aria-pressed={draft.node === n.id} onClick={() => setDraft((d) => ({ ...d, node: n.id }))}>
                {n.name}
              </button>
            ))}
            {nodes.length === 0 && <span className="ab-muted">Cargando su equipo…</span>}
          </div>
        </fieldset>

        <div className="ab-foot">
          <p className="ab-sentence" aria-live="polite">
            {missing || sentence(draft, nodeName)}
          </p>
          <button type="submit" className="ab-go" disabled={!!missing || busy}>
            {busy ? 'Creando…' : 'Crear automatización'}
          </button>
        </div>
        <p className="ab-note">Enviar, comprar, publicar o borrar siempre esperan su sí.</p>
      </form>
    </div>
  );
}

export default Builder;
