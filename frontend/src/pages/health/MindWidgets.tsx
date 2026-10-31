// «¿Cómo está hoy?» as widgets (owner, 29 Oct 2026: «solo pon las preguntas en
// forma de widget»): every card asks its own questions right there, one at a
// time, and sends itself when the last one is answered. The three picture
// questions are cards of their own with their picture; their answers wait in
// the full survey's draft, so it never asks them twice.

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { clock, salud, type MindWidget, type SurveyDefinition, type SurveyItem, type SurveyResult, type SurveyVariant } from '../../lib/salud';
import { SURVEY_IMAGES, hasDraft, readDraft, writeDraft } from './MindSurvey';

type Answers = Record<string, number | string>;

function itemsOf(def: SurveyDefinition | null): SurveyItem[] {
  return (def?.sections ?? []).flatMap((s) => s.items).filter((i) => i.kind !== 'open');
}

function Options({ item, value, onPick }: { item: SurveyItem; value?: number | string; onPick: (v: number) => void }) {
  return (
    <div className="mw-options" role="radiogroup" aria-label={item.text}>
      {item.options?.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} className="mw-option" onClick={() => onPick(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** One validated short scale, asked inside its card. */
function ScaleWidget({ w, onOpen, onSent }: { w: MindWidget; onOpen: (id: string) => void; onSent: (r: SurveyResult) => void }) {
  const [def, setDef] = useState<SurveyDefinition | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [at, setAt] = useState(0);
  const [asking, setAsking] = useState(!w.last);
  const [sending, setSending] = useState(false);
  const [last, setLast] = useState(w.last);

  useEffect(() => {
    if (asking && !def) salud.survey(w.key).then(setDef).catch(() => setDef(null));
  }, [asking, def, w.key]);

  const items = itemsOf(def);
  const item = items[at];

  const pick = async (value: number) => {
    if (!item) return;
    const next = { ...answers, [item.id]: value };
    setAnswers(next);
    if (at < items.length - 1) {
      window.setTimeout(() => setAt(at + 1), 160);
      return;
    }
    setSending(true);
    try {
      const r = await salud.submitSurvey(next, w.key as SurveyVariant);
      setLast(r);
      setAsking(false);
      setAnswers({});
      setAt(0);
      onSent(r);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude enviar sus respuestas.');
    } finally {
      setSending(false);
    }
  };

  return (
    <article className="mind-widget mw" data-asking={asking || undefined}>
      <header className="mw-head">
        <b>{w.label}</b>
        {asking && items.length > 0 && (
          <span className="mw-dots" aria-label={`Pregunta ${at + 1} de ${items.length}`}>
            {items.map((i, n) => (
              <i key={i.id} data-on={n <= at || undefined} />
            ))}
          </span>
        )}
      </header>
      {asking ? (
        !def ? (
          <p className="paper-meta">Leyendo…</p>
        ) : item ? (
          <div className="mw-q" key={item.id}>
            {at === 0 && def.sections[0]?.stem && <p className="mw-stem">{def.sections[0].stem}</p>}
            <p className="mw-text">{item.text}</p>
            <Options item={item} value={answers[item.id]} onPick={(v) => void pick(v)} />
            {sending && <span className="paper-meta">Enviando…</span>}
          </div>
        ) : null
      ) : (
        <div className="mw-done">
          <em data-ready={last?.status === 'ready'}>
            {last?.status === 'ready' ? 'Listo' : last ? `Listo a las ${clock(last.ready_at)}` : 'Sin responder'}
          </em>
          <div className="mind-widget-actions">
            <button type="button" className="mind-widget-go" onClick={() => setAsking(true)}>
              Otra vez
            </button>
            {last && (
              <button type="button" className="mind-widget-see" onClick={() => onOpen(last.id)}>
                Ver
              </button>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

/** A picture question in its own card: the answer waits for the full survey. */
function PictureWidget({ item }: { item: SurveyItem }) {
  const [value, setValue] = useState<number | string | undefined>(() => readDraft('corta')[item.id] ?? readDraft('larga')[item.id]);
  const pick = (v: number) => {
    setValue(v);
    for (const variant of ['corta', 'larga'] as const) writeDraft(variant, { ...readDraft(variant), [item.id]: v });
  };
  return (
    <article className="mind-widget mw mw-picture">
      {item.image && <img src={SURVEY_IMAGES[item.image]} alt={item.alt ?? ''} loading="lazy" />}
      <div className="mw-q">
        <p className="mw-text">{item.text}</p>
        <Options item={item} value={value} onPick={pick} />
        {value !== undefined && <span className="paper-meta">Guardada para la encuesta completa.</span>}
      </div>
    </article>
  );
}

export function MindWidgets({ onPick, onOpen, onSent }: { onPick: (v: SurveyVariant) => void; onOpen: (id: string) => void; onSent: (r: SurveyResult) => void }) {
  const [cards, setCards] = useState<MindWidget[] | null>(null);
  const [pictures, setPictures] = useState<SurveyItem[]>([]);
  useEffect(() => {
    salud.widgets().then((r) => setCards(r.widgets)).catch(() => setCards([]));
    salud
      .survey('corta')
      .then((d) => setPictures(d.sections.flatMap((s) => s.items).filter((i) => i.kind === 'picture')))
      .catch(() => setPictures([]));
  }, []);
  if (!cards) return <p className="paper-meta">Leyendo…</p>;
  return (
    <div className="mind-widgets mw-grid">
      {cards.map((w) => (
        <ScaleWidget key={w.key} w={w} onOpen={onOpen} onSent={onSent} />
      ))}
      {pictures.map((p) => (
        <PictureWidget key={p.id} item={p} />
      ))}
      <article className="mind-widget mind-widget-full mw">
        <b>Encuesta completa</b>
        <span>12 o 56 preguntas</span>
        <em>{hasDraft('corta') || hasDraft('larga') ? 'Tiene una a medias' : 'Con las tres imágenes'}</em>
        <div className="mind-widget-actions">
          <button type="button" className="mind-widget-go" onClick={() => onPick('corta')}>
            Corta
          </button>
          <button type="button" className="mind-widget-see" onClick={() => onPick('larga')}>
            Larga
          </button>
        </div>
      </article>
    </div>
  );
}
