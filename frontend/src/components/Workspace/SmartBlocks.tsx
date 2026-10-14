// Blocks Notion does not have (or has half of): dynamic forms with
// conditional fields, programmable buttons, live dashboards and video.

import { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Play, Plus, Share2, Trash2, Upload, X } from 'lucide-react';
import { toast } from 'sonner';
import { kpis, runButton, submitForm, visibleFields, type ButtonSpec, type ButtonStep, type FormField, type FormSpec } from '../../lib/workspace/brain';
import { ask } from '../../lib/workspace/ai';
import { block as makeBlock, plainText, type Block, type Page, type TableData } from '../../lib/workspace/model';
import { mediaUrl, saveMedia } from '../../lib/workspace/store';
import { useAppStore } from '../../lib/store';

// -- forms ------------------------------------------------------------------------

export function FormBlock({
  block,
  tables,
  onChange,
  onSubmitRow,
  onShare,
}: {
  block: Block;
  tables: Block[];
  onChange: (f: FormSpec) => void;
  onSubmitRow: (tableId: string, t: TableData) => void;
  onShare?: () => void;
}) {
  const spec: FormSpec = block.form || { table: tables[0]?.id || '', title: 'Formulario', fields: [] };
  const target = tables.find((t) => t.id === spec.table)?.table;
  const [editing, setEditing] = useState(!block.form);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!block.form && target) onChange({ ...spec, fields: target.columns.map((c) => ({ column: c.id })) });
  }, [block.form, target]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!tables.length) return <p className="ws-empty">Añada una tabla a la página: el formulario la llena.</p>;
  if (!target) return null;
  const col = (id: string) => target.columns.find((c) => c.id === id);
  const setField = (i: number, p: Partial<FormField>) => onChange({ ...spec, fields: spec.fields.map((f, k) => (k === i ? { ...f, ...p } : f)) });
  const shown = visibleFields(spec, target, values);
  return (
    <div className="ws-form">
      <div className="ws-form-head">
        <input className="ws-form-title" value={spec.title} onChange={(e) => onChange({ ...spec, title: e.target.value })} aria-label="Título del formulario" />
        <button type="button" className="paper-tab" onClick={() => setEditing(!editing)}>
          {editing ? 'Vista previa' : 'Editar'}
        </button>
        {onShare && (
          <button type="button" className="mac-icon-btn" aria-label="Compartir formulario" title="Compartir formulario" onClick={onShare}>
            <Share2 size={14} />
          </button>
        )}
      </div>
      {editing ? (
        <div className="ws-form-edit">
          <label className="ws-setting">
            Llena
            <select className="ws-mini-input" value={spec.table} onChange={(e) => onChange({ ...spec, table: e.target.value })}>
              {tables.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.text || 'Tabla'}
                </option>
              ))}
            </select>
          </label>
          {spec.fields.map((f, i) => (
            <div key={i} className="ws-rule-line">
              <select className="ws-mini-input" value={f.column} onChange={(e) => setField(i, { column: e.target.value })}>
                {target.columns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-1 text-[12px]">
                <input type="checkbox" checked={!!f.required} onChange={(e) => setField(i, { required: e.target.checked })} /> obligatorio
              </label>
              <select
                className="ws-mini-input"
                value={f.showIf?.column || ''}
                onChange={(e) => setField(i, { showIf: e.target.value ? { column: e.target.value, op: 'is', value: f.showIf?.value || '' } : null })}
                aria-label="Mostrar solo si"
              >
                <option value="">siempre</option>
                {target.columns
                  .filter((c) => c.id !== f.column)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      si {c.name} es…
                    </option>
                  ))}
              </select>
              {f.showIf && (
                <input className="ws-mini-input" value={f.showIf.value || ''} onChange={(e) => setField(i, { showIf: { ...f.showIf!, value: e.target.value } })} aria-label="Valor" />
              )}
              <button type="button" className="mac-icon-btn" aria-label="Quitar campo" onClick={() => onChange({ ...spec, fields: spec.fields.filter((_x, k) => k !== i) })}>
                <X size={12} />
              </button>
            </div>
          ))}
          <button type="button" className="paper-tab" onClick={() => onChange({ ...spec, fields: [...spec.fields, { column: target.columns[0].id }] })}>
            + campo
          </button>
        </div>
      ) : (
        <form
          className="ws-form-fill"
          onSubmit={(e) => {
            e.preventDefault();
            const out = submitForm(spec, target, values);
            setErrors(out.errors);
            if (out.table) {
              onSubmitRow(spec.table, out.table);
              setValues({});
              toast.success('Respuesta guardada en la tabla.');
            }
          }}
        >
          {shown.map((f) => {
            const c = col(f.column)!;
            const v = values[c.id] || '';
            const set = (x: string) => setValues({ ...values, [c.id]: x });
            return (
              <label key={c.id} className="ws-form-field">
                <span>
                  {f.label || c.name}
                  {f.required ? ' *' : ''}
                </span>
                {c.type === 'select' || c.type === 'multi' ? (
                  <select value={v} onChange={(e) => set(e.target.value)}>
                    <option value="" />
                    {(c.options || []).map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                ) : c.type === 'checkbox' ? (
                  <input type="checkbox" checked={v === 'true'} onChange={(e) => set(e.target.checked ? 'true' : 'false')} />
                ) : (
                  <input type={{ number: 'number', date: 'date', email: 'email', url: 'url', phone: 'tel' }[c.type as string] || 'text'} value={v} onChange={(e) => set(e.target.value)} />
                )}
                {errors[c.id] && <em>{errors[c.id]}</em>}
              </label>
            );
          })}
          <button type="submit" className="ext-btn" data-primary>
            Enviar
          </button>
        </form>
      )}
    </div>
  );
}

// -- buttons -----------------------------------------------------------------------

const STEP_LABEL: Record<ButtonStep['kind'], string> = {
  insert: 'Insertar texto',
  row: 'Añadir fila',
  check: 'Marcar tareas',
  ai: 'Pedir a Sergio',
  open: 'Abrir página',
};

export function ButtonBlock({
  block,
  page,
  tables,
  onChange,
  onRun,
  onOpenPage,
}: {
  block: Block;
  page: Page;
  tables: Block[];
  onChange: (b: ButtonSpec) => void;
  onRun: (p: Page) => void;
  onOpenPage: (title: string) => void;
}) {
  const model = useAppStore((s) => s.selectedModel);
  const spec: ButtonSpec = block.button || { label: 'Botón', steps: [{ kind: 'insert', text: 'Nota del {hoy}', as: 'h3' }] };
  const [editing, setEditing] = useState(!block.button);
  const [busy, setBusy] = useState(false);
  const setStep = (i: number, st: ButtonStep) => onChange({ ...spec, steps: spec.steps.map((x, k) => (k === i ? st : x)) });
  const run = async () => {
    setBusy(true);
    try {
      const out = runButton(page, block.id, spec);
      let next = out.page;
      for (const step of out.pending) {
        if (step.kind === 'ai') {
          const text = await ask('Eres Sergio. Responde solo con el contenido pedido.', `${step.prompt}\n\nPágina:\n${plainText(next, 8000)}`, model);
          const i = next.blocks.findIndex((x) => x.id === block.id);
          const added = text.split('\n').filter(Boolean).map((line) => makeBlock(/^[-*]\s/.test(line) ? 'bullet' : 'text', line.replace(/^[-*]\s/, '')));
          next = { ...next, blocks: [...next.blocks.slice(0, i + 1), ...added, ...next.blocks.slice(i + 1)] };
        } else if (step.kind === 'open') onOpenPage(step.page);
      }
      onRun(next);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="ws-button-block">
      <button type="button" className="ext-btn" data-primary onClick={() => void run()} disabled={busy}>
        {busy ? <Loader2 size={14} className="ext-spin" /> : <Play size={13} />} {spec.label}
      </button>
      <button type="button" className="paper-tab" onClick={() => setEditing(!editing)}>
        {editing ? 'Listo' : 'Editar'}
      </button>
      {editing && (
        <div className="ws-form-edit">
          <input className="ws-mini-input" value={spec.label} onChange={(e) => onChange({ ...spec, label: e.target.value })} aria-label="Texto del botón" />
          {spec.steps.map((st, i) => (
            <div key={i} className="ws-rule-line">
              <select
                className="ws-mini-input"
                value={st.kind}
                onChange={(e) => {
                  const k = e.target.value as ButtonStep['kind'];
                  setStep(
                    i,
                    k === 'insert' ? { kind: 'insert', text: '', as: 'text' } : k === 'row' ? { kind: 'row', table: tables[0]?.id || '', values: {} } : k === 'check' ? { kind: 'check', all: true } : k === 'ai' ? { kind: 'ai', prompt: '' } : { kind: 'open', page: '' },
                  );
                }}
              >
                {Object.entries(STEP_LABEL).map(([k, l]) => (
                  <option key={k} value={k}>
                    {l}
                  </option>
                ))}
              </select>
              {st.kind === 'insert' && (
                <>
                  <select className="ws-mini-input" value={st.as || 'text'} onChange={(e) => setStep(i, { ...st, as: e.target.value as Block['type'] })}>
                    <option value="text">texto</option>
                    <option value="h3">título</option>
                    <option value="todo">tarea</option>
                    <option value="bullet">viñeta</option>
                  </select>
                  <input className="ws-mini-input flex-1" value={st.text} placeholder="{hoy} {hora}" onChange={(e) => setStep(i, { ...st, text: e.target.value })} />
                </>
              )}
              {st.kind === 'row' && (
                <select className="ws-mini-input" value={st.table} onChange={(e) => setStep(i, { ...st, table: e.target.value })}>
                  {tables.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.text || 'Tabla'}
                    </option>
                  ))}
                </select>
              )}
              {st.kind === 'check' && (
                <select className="ws-mini-input" value={st.all ? '1' : '0'} onChange={(e) => setStep(i, { kind: 'check', all: e.target.value === '1' })}>
                  <option value="1">todas hechas</option>
                  <option value="0">todas pendientes</option>
                </select>
              )}
              {st.kind === 'ai' && <input className="ws-mini-input flex-1" value={st.prompt} placeholder="«Resume esta página en 3 puntos»" onChange={(e) => setStep(i, { ...st, prompt: e.target.value })} />}
              {st.kind === 'open' && <input className="ws-mini-input flex-1" value={st.page} placeholder="Título de la página" onChange={(e) => setStep(i, { ...st, page: e.target.value })} />}
              <button type="button" className="mac-icon-btn" aria-label="Quitar paso" onClick={() => onChange({ ...spec, steps: spec.steps.filter((_x, k) => k !== i) })}>
                <Trash2 size={12} />
              </button>
            </div>
          ))}
          <button type="button" className="paper-tab" onClick={() => onChange({ ...spec, steps: [...spec.steps, { kind: 'insert', text: '', as: 'text' }] })}>
            <Plus size={12} /> paso
          </button>
        </div>
      )}
    </div>
  );
}

// -- dashboards ---------------------------------------------------------------------

export function DashboardBlock({ tables }: { tables: Block[] }) {
  const cards = useMemo(() => tables.filter((t) => t.table).map((t) => ({ name: t.text || 'Tabla', kpis: kpis(t.table!) })), [tables]);
  if (!cards.length) return <p className="ws-empty">Añada una tabla a la página.</p>;
  return (
    <div className="ws-dash">
      {cards.map((c, i) => (
        <section key={i} className="ws-dash-card">
          <b>{c.name}</b>
          <div className="ws-dash-kpis">
            {c.kpis.map((k) => (
              <span key={k.label} className="ws-kpi">
                <strong>{k.value}</strong>
                <small>{k.label}</small>
              </span>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

// -- video (with trim points) ----------------------------------------------------------

export function VideoBlock({ block, onMedia }: { block: Block; onMedia: (m: NonNullable<Block['media']>) => void }) {
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLVideoElement>(null);
  const media = block.media;
  useEffect(() => {
    if (media) void mediaUrl(media).then(setUrl);
  }, [media]);
  const edit = media?.edit || {};
  if (!media)
    return (
      <label className="ws-media-drop">
        {busy ? <Loader2 size={16} className="ext-spin" /> : <Upload size={16} />} Video
        <input
          type="file"
          accept="video/mp4,video/webm,video/quicktime"
          hidden
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            setBusy(true);
            try {
              onMedia(await saveMedia(f, f.name));
            } finally {
              setBusy(false);
            }
          }}
        />
      </label>
    );
  return (
    <div className="ws-video">
      <video
        ref={ref}
        src={url ? `${url}#t=${edit.start || 0}${edit.end ? `,${edit.end}` : ''}` : undefined}
        controls
        playsInline
        style={{ filter: edit.filter || undefined, transform: `rotate(${edit.rotate || 0}deg)${edit.flip ? ' scaleX(-1)' : ''}` }}
        onTimeUpdate={(e) => {
          if (edit.end && e.currentTarget.currentTime > edit.end) e.currentTarget.pause();
        }}
      />
      <div className="ws-media-tools">
        <button type="button" className="paper-tab" onClick={() => onMedia({ ...media, edit: { ...edit, start: Math.round((ref.current?.currentTime || 0) * 10) / 10 } })}>
          Inicio aquí {edit.start ? `(${edit.start}s)` : ''}
        </button>
        <button type="button" className="paper-tab" onClick={() => onMedia({ ...media, edit: { ...edit, end: Math.round((ref.current?.currentTime || 0) * 10) / 10 } })}>
          Fin aquí {edit.end ? `(${edit.end}s)` : ''}
        </button>
        <MediaLook media={media} onMedia={onMedia} />
      </div>
    </div>
  );
}

const FILTERS: Array<[string, string]> = [
  ['', 'Original'],
  ['grayscale(1)', 'B/N'],
  ['sepia(.6) saturate(1.2)', 'Cálido'],
  ['saturate(1.6) contrast(1.1)', 'Vivo'],
  ['brightness(1.15) contrast(.92)', 'Claro'],
  ['hue-rotate(180deg) saturate(.8)', 'Frío'],
];

/** Rotate, mirror and a look — the same for images and video, non-destructive. */
export function MediaLook({ media, onMedia }: { media: NonNullable<Block['media']>; onMedia: (m: NonNullable<Block['media']>) => void }) {
  const edit = media.edit || {};
  return (
    <>
      <button type="button" className="paper-tab" onClick={() => onMedia({ ...media, edit: { ...edit, rotate: ((edit.rotate || 0) + 90) % 360 } })}>
        Girar
      </button>
      <button type="button" className="paper-tab" onClick={() => onMedia({ ...media, edit: { ...edit, flip: !edit.flip } })}>
        Espejo
      </button>
      <select className="ws-mini-input" value={edit.filter || ''} onChange={(e) => onMedia({ ...media, edit: { ...edit, filter: e.target.value } })} aria-label="Estilo">
        {FILTERS.map(([v, l]) => (
          <option key={l} value={v}>
            {l}
          </option>
        ))}
      </select>
      <input
        className="ws-mini-input flex-1"
        value={media.caption || ''}
        onChange={(e) => onMedia({ ...media, caption: e.target.value })}
        placeholder="Qué se ve (para buscarlo)"
        aria-label="Descripción"
      />
    </>
  );
}
