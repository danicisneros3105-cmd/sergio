// What a Workspace table does beyond Notion: a timeline with the critical
// path and the predicted delay, automations with AND/OR conditions, formulas
// written in words and whole tables made from a sentence.

import { useMemo, useState } from 'react';
import { Loader2, Plus, Sparkles, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { projectRisk, schedule, type CondOp, type Rule, type RuleAction } from '../../lib/workspace/brain';
import { aiFormula, aiTable } from '../../lib/workspace/ai';
import { newId, type TableData } from '../../lib/workspace/model';
import { useAppStore } from '../../lib/store';

const DAY = 86_400_000;

export function TimelineView({ table }: { table: TableData }) {
  const plan = useMemo(() => schedule(table), [table]);
  const risk = useMemo(() => projectRisk(table), [table]);
  if (!plan.tasks.length) return <p className="ws-empty">Sin filas.</p>;
  const start = Math.min(...plan.tasks.map((t) => t.start));
  const end = Math.max(plan.end, start + 7 * DAY);
  const span = end - start;
  const fmt = (t: number) => new Date(t).toLocaleDateString('es', { day: 'numeric', month: 'short' });
  return (
    <div className="ws-timeline">
      <div className="ws-timeline-head">
        <span>{fmt(start)}</span>
        <b data-late={risk.delayDays > 0 || undefined}>
          {risk.delayDays > 0 ? `+${risk.delayDays} d` : 'a tiempo'} · {fmt(risk.predictedEnd)}
        </b>
        <span>{fmt(end)}</span>
      </div>
      {plan.tasks.map((t) => (
        <div key={t.row.id} className="ws-timeline-row" title={t.critical ? 'Ruta crítica' : `Holgura: ${t.slack} d`}>
          <span className="ws-timeline-name">{t.name || '—'}</span>
          <span className="ws-timeline-track">
            <i
              data-critical={t.critical || undefined}
              data-done={t.done || undefined}
              style={{ left: `${((t.start - start) / span) * 100}%`, width: `${Math.max((t.days * DAY) / span, 0.012) * 100}%` }}
            />
          </span>
        </div>
      ))}
      {plan.cycle.length > 0 && <p className="ws-warn">Dependencias en círculo: {plan.cycle.join(', ')}</p>}
    </div>
  );
}

const OPS: Array<{ key: CondOp; label: string }> = [
  { key: 'is', label: 'es' },
  { key: 'not', label: 'no es' },
  { key: 'contains', label: 'contiene' },
  { key: 'gt', label: '>' },
  { key: 'lt', label: '<' },
  { key: 'filled', label: 'tiene valor' },
  { key: 'empty', label: 'está vacío' },
  { key: 'changed', label: 'cambia' },
];

/** «Cuando … y/o … entonces …», visual, per table. */
export function RulesEditor({ table, onChange, onClose }: { table: TableData; onChange: (t: TableData) => void; onClose: () => void }) {
  const rules = table.rules || [];
  const save = (next: Rule[]) => onChange({ ...table, rules: next });
  const patch = (id: string, p: Partial<Rule>) => save(rules.map((r) => (r.id === id ? { ...r, ...p } : r)));
  const first = table.columns[0]?.id || '';
  const add = () =>
    save([...rules, { id: newId('a'), name: 'Nueva regla', on: true, any: false, when: [{ column: table.columns[1]?.id || first, op: 'is', value: '' }], then: [{ kind: 'notify', text: '{' + (table.columns[0]?.name || 'Nombre') + '} cambió' }] }]);
  const actionLabel = { set: 'Poner', todo: 'Crear tarea', notify: 'Avisar', archive: 'Archivar fila', webhook: 'Llamar a una app' } as const;
  return (
    <div className="ws-rules">
      <div className="ws-rules-head">
        <b>Automatizaciones</b>
        <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={onClose}>
          <X size={14} />
        </button>
      </div>
      {rules.map((r) => (
        <div key={r.id} className="ws-rule" data-off={!r.on || undefined}>
          <div className="ws-rule-top">
            <input className="ws-mini-input" value={r.name} onChange={(e) => patch(r.id, { name: e.target.value })} aria-label="Nombre de la regla" />
            <button type="button" role="switch" aria-checked={r.on} className="ext-switch" aria-label="Activa" onClick={() => patch(r.id, { on: !r.on })} />
            <button type="button" className="mac-icon-btn" aria-label="Borrar regla" onClick={() => save(rules.filter((x) => x.id !== r.id))}>
              <Trash2 size={13} />
            </button>
          </div>
          <span className="ws-rule-k">Cuando</span>
          {r.when.map((c, i) => (
            <div key={i} className="ws-rule-line">
              {i > 0 && (
                <button type="button" className="mac-chip" onClick={() => patch(r.id, { any: !r.any })}>
                  {r.any ? 'o' : 'y'}
                </button>
              )}
              <select className="ws-mini-input" value={c.column} onChange={(e) => patch(r.id, { when: r.when.map((x, k) => (k === i ? { ...x, column: e.target.value } : x)) })}>
                {table.columns.map((col) => (
                  <option key={col.id} value={col.id}>
                    {col.name}
                  </option>
                ))}
              </select>
              <select className="ws-mini-input" value={c.op} onChange={(e) => patch(r.id, { when: r.when.map((x, k) => (k === i ? { ...x, op: e.target.value as CondOp } : x)) })}>
                {OPS.map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.label}
                  </option>
                ))}
              </select>
              {!['filled', 'empty', 'changed'].includes(c.op) && (
                <input className="ws-mini-input" value={c.value || ''} onChange={(e) => patch(r.id, { when: r.when.map((x, k) => (k === i ? { ...x, value: e.target.value } : x)) })} aria-label="Valor" />
              )}
              <button type="button" className="mac-icon-btn" aria-label="Quitar condición" onClick={() => patch(r.id, { when: r.when.filter((_x, k) => k !== i) })}>
                <X size={12} />
              </button>
            </div>
          ))}
          <button type="button" className="paper-tab" onClick={() => patch(r.id, { when: [...r.when, { column: first, op: 'is', value: '' }] })}>
            + condición
          </button>
          <span className="ws-rule-k">Entonces</span>
          {r.then.map((a, i) => {
            const setA = (na: RuleAction) => patch(r.id, { then: r.then.map((x, k) => (k === i ? na : x)) });
            return (
              <div key={i} className="ws-rule-line">
                <select
                  className="ws-mini-input"
                  value={a.kind}
                  onChange={(e) => {
                    const k = e.target.value as RuleAction['kind'];
                    setA(k === 'set' ? { kind: 'set', column: first, value: '' } : k === 'archive' ? { kind: 'archive' } : k === 'webhook' ? { kind: 'webhook', url: 'https://' } : { kind: k, text: '' });
                  }}
                >
                  {Object.entries(actionLabel).map(([k, l]) => (
                    <option key={k} value={k}>
                      {l}
                    </option>
                  ))}
                </select>
                {a.kind === 'set' && (
                  <>
                    <select className="ws-mini-input" value={a.column} onChange={(e) => setA({ ...a, column: e.target.value })}>
                      {table.columns.map((col) => (
                        <option key={col.id} value={col.id}>
                          {col.name}
                        </option>
                      ))}
                    </select>
                    <input className="ws-mini-input" value={a.value} onChange={(e) => setA({ ...a, value: e.target.value })} aria-label="Valor" />
                  </>
                )}
                {(a.kind === 'todo' || a.kind === 'notify') && <input className="ws-mini-input flex-1" value={a.text} onChange={(e) => setA({ ...a, text: e.target.value })} aria-label="Texto" />}
                {a.kind === 'webhook' && <input className="ws-mini-input flex-1" value={a.url} onChange={(e) => setA({ ...a, url: e.target.value })} aria-label="Dirección https" />}
                <button type="button" className="mac-icon-btn" aria-label="Quitar acción" onClick={() => patch(r.id, { then: r.then.filter((_x, k) => k !== i) })}>
                  <X size={12} />
                </button>
              </div>
            );
          })}
          <button type="button" className="paper-tab" onClick={() => patch(r.id, { then: [...r.then, { kind: 'notify', text: '' }] })}>
            + acción
          </button>
        </div>
      ))}
      <button type="button" className="ext-add" onClick={add}>
        <Plus size={13} /> Regla
      </button>
    </div>
  );
}

/** «precio por cantidad» → a new computed column. */
export function FormulaWords({ table, onChange }: { table: TableData; onChange: (t: TableData) => void }) {
  const model = useAppStore((s) => s.selectedModel);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="ws-formula-words"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!text.trim()) return;
        setBusy(true);
        try {
          const f = await aiFormula(text, table, model);
          const col = { id: newId('c'), name: text.trim().slice(0, 28), type: 'text' as const };
          onChange({ ...table, columns: [...table.columns, col], rows: table.rows.map((r) => ({ ...r, cells: { ...r.cells, [col.id]: f } })) });
          setText('');
          toast.success(f);
        } catch (err) {
          toast.error(err instanceof Error ? err.message : String(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <Sparkles size={13} />
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Columna calculada: «precio por cantidad»" aria-label="Fórmula en palabras" />
      {busy && <Loader2 size={13} className="ext-spin" />}
    </form>
  );
}

/** A whole table from a sentence (replaces an empty one). */
export function AiTable({ onTable }: { onTable: (t: TableData) => void }) {
  const model = useAppStore((s) => s.selectedModel);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="ws-formula-words"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!text.trim()) return;
        setBusy(true);
        try {
          onTable(await aiTable(text, model));
          setText('');
        } catch (err) {
          toast.error(err instanceof Error ? err.message : String(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <Sparkles size={13} />
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Describa la base de datos y Sergio la crea" aria-label="Crear tabla con IA" />
      {busy && <Loader2 size={13} className="ext-spin" />}
    </form>
  );
}
