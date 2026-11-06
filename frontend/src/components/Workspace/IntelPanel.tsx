import { scopedDataKey } from '../../lib/browserAccount';
// Sergio, next to a page: what it relates to, what to verify, how the
// project will go, relations nobody configured, how its template should
// evolve, and an agent that carries the page's goal out step by step — each
// step shown first, the risky ones approved by hand, results only in the page.

import { useMemo, useRef, useState } from 'react';
import { Brain, Check, Link2, Loader2, Play, ShieldCheck, Sparkles, X } from 'lucide-react';
import { toast } from 'sonner';
import { useWorkspace } from '../../lib/workspace/store';
import { detectRelations, evolveTemplate, inferTable, parseGrid, projectRisk, relatedPages, staleness } from '../../lib/workspace/brain';
import { aiPlan, aiStep, aiVerify, parseLines, type PlanStep } from '../../lib/workspace/ai';
import { block as makeBlock, plainText, TEMPLATES, type Block, type Page } from '../../lib/workspace/model';
import { useAppStore } from '../../lib/store';
import { nodesRequest } from '../../lib/nodes-api';

const TEMPLATE_KEY = scopedDataKey('sergio-templates');

function saveTemplate(key: string, blocks: Block[]) {
  try {
    const all = JSON.parse(localStorage.getItem(TEMPLATE_KEY) || '{}');
    all[key] = blocks.map((b) => ({ type: b.type, text: b.text }));
    localStorage.setItem(TEMPLATE_KEY, JSON.stringify(all));
  } catch {
    /* private mode */
  }
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <section className="ws-intel-sec">
      <h4>
        {icon}
        {title}
      </h4>
      {children}
    </section>
  );
}

export function IntelPanel({ page, blocks, onBlocks, onClose }: { page: Page; blocks: Block[]; onBlocks: (b: Block[]) => void; onClose: () => void }) {
  const pages = useWorkspace((s) => s.pages);
  const open = useWorkspace((s) => s.open);
  const update = useWorkspace((s) => s.update);
  const model = useAppStore((s) => s.selectedModel);
  const all = useMemo(() => Object.values(pages), [pages]);
  const current = { ...page, blocks };
  const related = useMemo(() => relatedPages(all, current), [all, blocks]); // eslint-disable-line react-hooks/exhaustive-deps
  const stale = useMemo(() => staleness(current, all), [all, blocks]); // eslint-disable-line react-hooks/exhaustive-deps
  const tables = blocks.filter((b) => b.table);
  const risks = useMemo(() => tables.map((t) => ({ t, r: projectRisk(t.table!) })).filter((x) => x.r.risks.length || x.r.delayDays > 0 || x.r.budget), [blocks]); // eslint-disable-line react-hooks/exhaustive-deps
  const relations = useMemo(() => detectRelations(all).filter((h) => h.pageId === page.id), [all, page.id]);
  const uses = all.filter((p) => p.template && p.template === page.template);
  const evolved = page.template && uses.length >= 2 ? evolveTemplate(TEMPLATES.find((t) => t.key === page.template)?.make().blocks || [], uses) : null;

  const [doubts, setDoubts] = useState<string[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [goal, setGoal] = useState('');
  const [plan, setPlan] = useState<PlanStep[] | null>(null);
  const [working, setWorking] = useState(false);
  const [nodes, setNodes] = useState<Array<{ id: string; name: string }> | null>(null);

  const linkColumn = (h: (typeof relations)[number]) => {
    const target = h.target.kind === 'table' ? { kind: 'table' as const, block: h.target.ref.blockId, page: h.target.ref.pageId } : { kind: 'pages' as const };
    onBlocks(blocks.map((b) => (b.id === h.blockId && b.table ? { ...b, table: { ...b.table, columns: b.table.columns.map((c) => (c.id === h.column.id ? { ...c, relation: target } : c)) } } : b)));
    toast.success(`«${h.column.name}» quedó enlazada.`);
  };

  const blocksRef = useRef(blocks);
  blocksRef.current = blocks;
  const runStep = async (i: number, steps: PlanStep[]): Promise<PlanStep[]> => {
    const step = steps[i];
    let next = [...steps];
    try {
      const text = await aiStep(step, goal, steps.slice(0, i), model);
      next[i] = { ...step, status: 'hecho', result: text };
      const added: Block[] = [makeBlock('h3', step.title)];
      if (step.kind === 'tabla') {
        const grid = parseGrid(text.replace(/^```\w*\n?|```$/g, ''));
        added.push(grid.length > 1 ? makeBlock('table', step.title, { table: inferTable(grid) }) : makeBlock('text', text));
      } else added.push(...parseLines(text).map((l) => makeBlock(l.kind, l.text)));
      blocksRef.current = [...blocksRef.current, ...added];
      onBlocks(blocksRef.current);
    } catch (e) {
      next[i] = { ...step, status: 'error', result: e instanceof Error ? e.message : String(e) };
    }
    setPlan(next);
    return next;
  };

  const runAll = async (steps: PlanStep[]) => {
    setWorking(true);
    let s = steps;
    for (let i = 0; i < s.length; i++) {
      if (s[i].status !== 'pendiente') continue;
      if (s[i].approve) break; // supervised: waits for the owner
      s = await runStep(i, s);
    }
    setWorking(false);
  };

  return (
    <aside className="ws-intel" aria-label="Sergio en esta página">
      <header>
        <Brain size={16} />
        <b>Sergio</b>
        <button type="button" className="mac-icon-btn" aria-label="Cerrar" onClick={onClose}>
          <X size={15} />
        </button>
      </header>

      <Section icon={<Sparkles size={13} />} title="Agente">
        <form
          className="ws-formula-words"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!goal.trim()) return;
            setWorking(true);
            try {
              const steps = await aiPlan(goal, plainText(current, 6000), model);
              setPlan(steps);
              setWorking(false);
              void runAll(steps);
            } catch (err) {
              toast.error(err instanceof Error ? err.message : String(err));
              setWorking(false);
            }
          }}
        >
          <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Objetivo: «plan de lanzamiento en 4 semanas»" aria-label="Objetivo" />
          {working && <Loader2 size={13} className="ext-spin" />}
        </form>
        {plan && (
          <ol className="ws-plan">
            {plan.map((s, i) => (
              <li key={i} data-status={s.status}>
                <span>{s.title}</span>
                {s.status === 'pendiente' && s.approve && (
                  <button type="button" className="paper-tab" disabled={working} onClick={async () => {
                    setWorking(true);
                    const next = plan.map((x, k) => (k === i ? { ...x, approve: false } : x));
                    await runAll(next);
                  }}>
                    <Play size={11} /> Aprobar
                  </button>
                )}
                {s.status === 'hecho' && <Check size={13} />}
                {s.status === 'error' && <em>{s.result}</em>}
              </li>
            ))}
          </ol>
        )}
        <button
          type="button"
          className="paper-tab"
          onClick={async () => {
            if (nodes) return setNodes(null);
            try {
              const out = await nodesRequest<{ nodes: Array<{ id: string; name: string }> }>('');
              setNodes(out.nodes || []);
            } catch (e) {
              toast.error(e instanceof Error ? e.message : String(e));
            }
          }}
        >
          Encargar a un Node
        </button>
        {nodes && (
          <div className="ws-chips-row">
            {nodes.map((n) => (
              <button
                key={n.id}
                type="button"
                className="mac-chip"
                onClick={async () => {
                  try {
                    await nodesRequest(`/${n.id}/messages`, 'POST', {
                      text: `Encargo desde Workspace, página «${page.title || 'Sin título'}»:\n${goal || 'Lleve adelante esta página.'}\n\n${plainText(current, 6000)}`,
                    });
                    toast.success(`${n.name} se encarga.`);
                    setNodes(null);
                  } catch (e) {
                    toast.error(e instanceof Error ? e.message : String(e));
                  }
                }}
              >
                {n.name}
              </button>
            ))}
          </div>
        )}
      </Section>

      {risks.map(({ t, r }) => (
        <Section key={t.id} icon={<ShieldCheck size={13} />} title={t.text || 'Proyecto'}>
          <p className="ws-intel-big" data-late={r.delayDays > 0 || undefined}>
            {r.delayDays > 0 ? `+${r.delayDays} días` : 'A tiempo'} · {Math.round(r.progress * 100)} %
          </p>
          {r.budget && r.budget.planned > 0 && (
            <p className="ws-intel-line">
              {Math.round(r.budget.spent).toLocaleString('es')} / {Math.round(r.budget.planned).toLocaleString('es')} → {Math.round(r.budget.forecast).toLocaleString('es')}
            </p>
          )}
          <ul className="ws-intel-list">
            {r.risks.slice(0, 6).map((x) => (
              <li key={x.name} data-level={x.level}>
                <b>{x.name}</b> {x.reasons.join(' · ')}
              </li>
            ))}
            {r.needs.map((n) => (
              <li key={n} data-level="nota">
                {n}
              </li>
            ))}
          </ul>
        </Section>
      ))}

      <Section icon={<ShieldCheck size={13} />} title="Vigencia">
        {stale.reasons.length ? (
          <ul className="ws-intel-list">
            {stale.reasons.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        ) : (
          <p className="ws-intel-line">Al día.</p>
        )}
        {doubts && (
          <ul className="ws-intel-list">
            {doubts.length ? doubts.map((d) => <li key={d} data-level="medio">{d}</li>) : <li>Nada dudoso.</li>}
          </ul>
        )}
        <div className="ws-chips-row">
          <button
            type="button"
            className="paper-tab"
            disabled={checking}
            onClick={async () => {
              setChecking(true);
              try {
                setDoubts(await aiVerify(plainText(current, 12000), model));
              } catch (e) {
                toast.error(e instanceof Error ? e.message : String(e));
              } finally {
                setChecking(false);
              }
            }}
          >
            {checking ? <Loader2 size={12} className="ext-spin" /> : null} Comprobar
          </button>
          <button type="button" className="paper-tab" onClick={() => (update(page.id, (p) => ({ ...p, verifiedAt: Date.now() })), toast.success('Marcada como revisada.'))}>
            <Check size={12} /> Revisada
          </button>
        </div>
      </Section>

      {relations.length > 0 && (
        <Section icon={<Link2 size={13} />} title="Relaciones">
          {relations.map((h) => (
            <button key={h.column.id} type="button" className="mac-chip" onClick={() => linkColumn(h)}>
              {h.column.name} → {h.target.kind === 'table' ? h.target.ref.title : 'páginas'}
            </button>
          ))}
        </Section>
      )}

      {evolved && (evolved.added.length > 0 || evolved.removed.length > 0) && (
        <Section icon={<Sparkles size={13} />} title="Plantilla">
          <ul className="ws-intel-list">
            {evolved.added.map((a) => (
              <li key={a}>+ {a}</li>
            ))}
            {evolved.removed.map((a) => (
              <li key={a}>− {a}</li>
            ))}
          </ul>
          <button type="button" className="paper-tab" onClick={() => (saveTemplate(page.template!, evolved.blocks), toast.success('La plantilla aprendió.'))}>
            Actualizar plantilla
          </button>
        </Section>
      )}

      {related.length > 0 && (
        <Section icon={<Brain size={13} />} title="Relacionado">
          {related.map((r) => (
            <button key={r.page.id} type="button" className="ws-intel-related" onClick={() => open(r.page.id)}>
              <span>{r.page.title || 'Sin título'}</span>
              <small>{r.why}</small>
            </button>
          ))}
        </Section>
      )}
    </aside>
  );
}
