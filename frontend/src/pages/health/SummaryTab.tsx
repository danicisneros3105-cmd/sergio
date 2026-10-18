import { useEffect, useState } from 'react';
import { Pin, PinOff, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { fmt, salud, STATUS_ES, type Catalog, type Correlation, type MetricSummary, type Summary } from '../../lib/salud';
import { Sparkline } from './Sparkline';

export function MetricCard({ s, onOpen, def }: { s: MetricSummary; onOpen: () => void; def?: { low: number | null; high: number | null; decimals: number } }) {
  const change = s.change_pct;
  return (
    <button type="button" className="salud-card" onClick={onOpen}>
      <span className="salud-card-label">{s.label}</span>
      <b>{fmt(s.value, s.unit, def?.decimals ?? 0)}</b>
      <Sparkline points={s.spark} low={def?.low} high={def?.high} />
      <span className="salud-card-meta">
        {s.partial && <em>Hoy, en curso</em>}
        {s.status && <em>{STATUS_ES[s.status]}</em>}
        {change !== null && <span>{`${change > 0 ? '+' : ''}${change.toFixed(0)} % vs. su media`}</span>}
        {s.goal != null && <span>{`Meta ${fmt(s.goal, s.unit)}`}</span>}
      </span>
    </button>
  );
}

function Readiness({ summary }: { summary: Summary }) {
  const r = summary.readiness;
  return (
    <div className="salud-readiness" data-empty={r.score === null ? '1' : undefined}>
      <div className="salud-ring" style={{ '--p': r.score ?? 0 } as React.CSSProperties}>
        <b>{r.score ?? '—'}</b>
      </div>
      <div>
        <span className="paper-label">Preparación</span>
        <p>{r.score === null ? 'Hacen falta al menos dos de: variabilidad, pulso en reposo y sueño.' : r.word}</p>
        <small>
          {r.inputs.length ? `Con: ${r.inputs.join(', ')}` : ''}
          {r.missing.length ? `${r.inputs.length ? ' · ' : ''}Falta: ${r.missing.join(', ')}` : ''}
        </small>
      </div>
    </div>
  );
}

function QuickAdd({ catalog, onDone }: { catalog: Catalog; onDone: () => void }) {
  const [metric, setMetric] = useState('weight_kg');
  const [value, setValue] = useState('');
  const def = catalog.metrics.find((m) => m.key === metric);
  const save = async () => {
    const n = Number(value.replace(',', '.'));
    if (!value.trim() || Number.isNaN(n)) return;
    try {
      await salud.add(metric, n);
      setValue('');
      toast.success('Anotado.');
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No se pudo guardar.');
    }
  };
  return (
    <form
      className="salud-add"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <select className="paper-input" value={metric} onChange={(e) => setMetric(e.target.value)} aria-label="Medida">
        {catalog.categories.map((c) => (
          <optgroup key={c.key} label={c.label}>
            {catalog.metrics
              .filter((m) => m.category === c.key)
              .map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
      <input className="paper-input" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder={def?.unit ? `Valor (${def.unit})` : 'Valor'} aria-label="Valor" />
      <button type="submit" className="paper-button" disabled={!value.trim()}>
        <Plus size={14} /> Anotar
      </button>
    </form>
  );
}

function DayNote({ summary, onDone }: { summary: Summary; onDone: () => void }) {
  const [text, setText] = useState(summary.note.text);
  const [tags, setTags] = useState(summary.note.tags.join(', '));
  const IDEAS = ['café tarde', 'alcohol', 'cena tarde', 'estrés', 'pantallas de noche', 'entreno fuerte'];
  const save = async (nextTags = tags) => {
    try {
      await salud.note(summary.today, text, nextTags.split(',').map((t) => t.trim()).filter(Boolean));
      toast.success('Nota del día guardada.');
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No se pudo guardar.');
    }
  };
  const current = tags.split(',').map((t) => t.trim()).filter(Boolean);
  return (
    <div className="salud-note">
      <input className="paper-input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Cómo fue el día" aria-label="Nota del día" maxLength={500} />
      <div className="salud-tags">
        {IDEAS.map((t) => (
          <button
            key={t}
            type="button"
            className="mac-chip"
            aria-pressed={current.includes(t)}
            onClick={() => {
              const next = current.includes(t) ? current.filter((x) => x !== t) : [...current, t];
              setTags(next.join(', '));
            }}
          >
            {t}
          </button>
        ))}
        <input className="paper-input salud-tag-input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Otras etiquetas, con comas" aria-label="Etiquetas" />
        <button type="button" className="paper-button" data-variant="quiet" onClick={() => void save()}>
          Guardar
        </button>
      </div>
    </div>
  );
}

function WhatAffects() {
  const [target, setTarget] = useState('sleep_h');
  const [data, setData] = useState<{ label: string; found: Correlation[]; min_days: number } | null>(null);
  useEffect(() => {
    salud.correlations(target).then(setData).catch(() => setData(null));
  }, [target]);
  return (
    <div className="salud-affects">
      <div className="node-seg" role="radiogroup" aria-label="Qué mirar">
        {[
          ['sleep_h', 'Sueño'],
          ['hrv', 'Variabilidad'],
          ['resting_hr', 'Pulso en reposo'],
          ['mood', 'Ánimo'],
        ].map(([k, label]) => (
          <button key={k} type="button" role="radio" aria-checked={target === k} onClick={() => setTarget(k)}>
            {label}
          </button>
        ))}
      </div>
      {!data || !data.found.length ? (
        <p className="paper-meta">Aún no hay suficientes días para ver relaciones (hacen falta {data?.min_days ?? 14} con datos).</p>
      ) : (
        <ul>
          {data.found.map((f) => (
            <li key={f.metric || f.tag}>
              {f.kind === 'metric' ? (
                <>
                  <b>{f.label}</b> {f.r! < 0 ? 'va con menos' : 'va con más'} {data.label.toLowerCase()}{' '}
                  <span className="paper-meta">(r = {f.r}, {f.days} días)</span>
                </>
              ) : (
                <>
                  <b>{f.label}</b>: {data.label.toLowerCase()} {f.with} frente a {f.without} el resto{' '}
                  <span className="paper-meta">({f.days} días)</span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="paper-meta">Que dos cosas vayan juntas no prueba que una cause la otra.</p>
    </div>
  );
}

function Ask() {
  const [q, setQ] = useState('');
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <div>
      <form
        className="salud-add"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!q.trim()) return;
          setBusy(true);
          try {
            setReply((await salud.ask(q.trim())).reply);
            setQ('');
          } catch {
            toast.error('No pude responder ahora.');
          } finally {
            setBusy(false);
          }
        }}
      >
        <input className="paper-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Una duda sobre su salud o su entrenamiento" aria-label="Pregunta" />
        <button type="submit" className="paper-button" disabled={busy || !q.trim()}>
          Preguntar
        </button>
      </form>
      {reply && <p className="salud-reply">{reply}</p>}
      <p className="paper-meta">Es un consejo general, no un diagnóstico. Ante un dolor o un síntoma, vea a un médico.</p>
    </div>
  );
}

export function SummaryTab({
  summary,
  catalog,
  onOpen,
  onChanged,
  onConnect,
}: {
  summary: Summary;
  catalog: Catalog;
  onOpen: (key: string) => void;
  onChanged: () => void;
  onConnect: () => void;
}) {
  const defs = Object.fromEntries(catalog.metrics.map((m) => [m.key, m]));
  const pinned = summary.pins.map((k) => summary.metrics[k]).filter(Boolean);
  const others = Object.values(summary.metrics).filter((m) => !summary.pins.includes(m.metric));
  const togglePin = async (key: string) => {
    const next = summary.pins.includes(key) ? summary.pins.filter((p) => p !== key) : [...summary.pins, key];
    await salud.pins(next);
    onChanged();
  };
  return (
    <div className="salud-summary">
      {summary.empty && (
        <div className="salud-empty">
          <p>Aún no hay datos. Conecte su reloj, anillo o báscula, importe un archivo o anote algo a mano.</p>
          <button type="button" className="paper-button" onClick={onConnect}>
            Conectar dispositivos
          </button>
        </div>
      )}
      <Readiness summary={summary} />
      {summary.highlights.length > 0 && (
        <section className="salud-block">
          <h2 className="paper-label">Lo destacado</h2>
          <ul className="salud-highlights">
            {summary.highlights.map((h) => (
              <li key={h.metric}>
                <button type="button" onClick={() => onOpen(h.metric)}>
                  {h.text}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {pinned.length > 0 && (
        <section className="salud-block">
          <h2 className="paper-label">Fijadas</h2>
          <div className="salud-grid">
            {pinned.map((s) => (
              <div key={s.metric} className="salud-card-wrap">
                <MetricCard s={s} def={defs[s.metric]} onOpen={() => onOpen(s.metric)} />
                <button type="button" className="mac-icon-btn salud-pin" aria-label={`Quitar ${s.label} de fijadas`} onClick={() => void togglePin(s.metric)}>
                  <PinOff size={13} />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
      {others.length > 0 && (
        <section className="salud-block">
          <h2 className="paper-label">Otras medidas</h2>
          <div className="salud-grid">
            {others.map((s) => (
              <div key={s.metric} className="salud-card-wrap">
                <MetricCard s={s} def={defs[s.metric]} onOpen={() => onOpen(s.metric)} />
                <button type="button" className="mac-icon-btn salud-pin" aria-label={`Fijar ${s.label}`} onClick={() => void togglePin(s.metric)}>
                  <Pin size={13} />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
      <section className="salud-block">
        <h2 className="paper-label">Anotar</h2>
        <QuickAdd catalog={catalog} onDone={onChanged} />
        <DayNote key={summary.today} summary={summary} onDone={onChanged} />
      </section>
      <section className="salud-block">
        <h2 className="paper-label">Qué influye</h2>
        <WhatAffects />
      </section>
      <section className="salud-block">
        <h2 className="paper-label">Preguntar</h2>
        <Ask />
      </section>
    </div>
  );
}
