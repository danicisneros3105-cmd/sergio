import { scopedDataKey } from '../../lib/browserAccount';
// The Salud mental survey: one question per screen, three picture questions first,
// then the validated scales, then the open questions. Keys 1-7 answer, Enter goes on,
// arrow left goes back; the draft survives closing the page.

import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, X } from 'lucide-react';
import { toast } from 'sonner';
import { salud, type SurveyDefinition, type SurveyItem, type SurveyResult, type SurveyVariant } from '../../lib/salud';
import noSuficiente from '../../assets/salud/no-suficiente.webp';
import pensarDemasiado from '../../assets/salud/pensar-demasiado.webp';
import encajar from '../../assets/salud/encajar.webp';

export const SURVEY_IMAGES: Record<string, string> = {
  'no-suficiente': noSuficiente,
  'pensar-demasiado': pensarDemasiado,
  encajar,
};

const draftKey = (variant: SurveyVariant) => `sergio:salud-mental:borrador:${variant}`;

type Answers = Record<string, number | string>;

interface Step {
  item: SurveyItem;
  section: { key: string; title: string; stem?: string };
  firstOfSection: boolean;
}

export function readDraft(variant: SurveyVariant): Answers {
  try {
    return JSON.parse(localStorage.getItem(scopedDataKey(draftKey(variant))) || '{}') as Answers;
  } catch {
    return {};
  }
}

export function writeDraft(variant: SurveyVariant, answers: Answers | null) {
  try {
    if (answers) localStorage.setItem(scopedDataKey(draftKey(variant)), JSON.stringify(answers));
    else localStorage.removeItem(scopedDataKey(draftKey(variant)));
  } catch {
    /* private window: the draft just is not kept */
  }
}

export function hasDraft(variant: SurveyVariant): boolean {
  return Object.keys(readDraft(variant)).length > 0;
}

export function MindSurvey({
  variant,
  onClose,
  onSent,
}: {
  variant: SurveyVariant;
  onClose: () => void;
  onSent: (r: SurveyResult) => void;
}) {
  const [def, setDef] = useState<SurveyDefinition | null>(null);
  const [answers, setAnswers] = useState<Answers>(() => readDraft(variant));
  const [at, setAt] = useState(0);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    salud.survey(variant).then(setDef).catch(() => toast.error('No pude cargar la encuesta.'));
  }, [variant]);

  const steps = useMemo<Step[]>(
    () =>
      (def?.sections ?? []).flatMap((section) =>
        section.items.map((item, i) => ({ item, section, firstOfSection: i === 0 })),
      ),
    [def],
  );

  // Resume where the draft stopped.
  useEffect(() => {
    if (!steps.length) return;
    const next = steps.findIndex((s) => answers[s.item.id] === undefined && s.item.kind !== 'open');
    setAt(next === -1 ? steps.length - 1 : next);
    // Only once, when the survey arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [steps.length]);

  useEffect(() => {
    writeDraft(variant, answers);
  }, [variant, answers]);

  const step = steps[at];
  const last = at === steps.length - 1;
  const answered = Object.keys(answers).length;

  const go = (delta: number) => setAt((n) => Math.min(steps.length - 1, Math.max(0, n + delta)));

  const choose = (value: number) => {
    if (!step) return;
    setAnswers((a) => ({ ...a, [step.item.id]: value }));
    if (!last) window.setTimeout(() => go(1), 180);
  };

  const send = async () => {
    setSending(true);
    try {
      const result = await salud.submitSurvey(answers, variant);
      writeDraft(variant, null);
      onSent(result);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude enviar la encuesta.');
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!step || (e.target as HTMLElement)?.tagName === 'TEXTAREA') return;
      const n = Number(e.key);
      const options = step.item.options ?? [];
      if (n >= 1 && n <= options.length) {
        e.preventDefault();
        choose(options[n - 1].value);
      } else if (e.key === 'ArrowLeft') {
        go(-1);
      } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
        if (!last) go(1);
      } else if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  if (!def || !step) return <p className="paper-meta">Leyendo…</p>;

  const { item, section } = step;
  const value = answers[item.id];

  return (
    <div className="mind-survey" role="dialog" aria-label="Encuesta de salud mental">
      <header className="mind-survey-top">
        <button type="button" className="mac-icon-btn" aria-label="Pregunta anterior" onClick={() => go(-1)} disabled={at === 0}>
          <ArrowLeft size={16} />
        </button>
        <div className="mind-progress" aria-hidden>
          <span style={{ width: `${((at + 1) / steps.length) * 100}%` }} />
        </div>
        <span className="mind-count">
          {at + 1} de {steps.length}
        </span>
        <button type="button" className="mac-icon-btn" aria-label="Salir (se guarda lo respondido)" onClick={onClose}>
          <X size={16} />
        </button>
      </header>

      <div className={`mind-question${item.kind === 'picture' ? ' mind-question--picture' : ''}`} key={item.id}>
        {item.kind === 'picture' && item.image && (
          <img className="mind-picture" src={SURVEY_IMAGES[item.image]} alt={item.alt ?? ''} />
        )}
        <div className="mind-question-body">
          <span className="paper-label">{section.title}</span>
          {section.stem && <p className="mind-stem">{section.stem}</p>}
          <h2 className="mind-text">{item.text}</h2>
          {item.kind === 'open' ? (
            <>
              <textarea
                className="paper-input mind-open"
                rows={5}
                maxLength={2000}
                value={String(value ?? '')}
                onChange={(e) => setAnswers((a) => ({ ...a, [item.id]: e.target.value }))}
                placeholder="Escriba lo que quiera; también puede saltarla."
                aria-label={item.text}
              />
              {!last && (
                <button type="button" className="paper-button" onClick={() => go(1)}>
                  {value ? 'Siguiente' : 'Saltar'}
                </button>
              )}
            </>
          ) : (
            <div className="mind-options" role="radiogroup" aria-label={item.text}>
              {item.options?.map((o, i) => (
                <button
                  key={o.value}
                  type="button"
                  role="radio"
                  aria-checked={value === o.value}
                  className="mind-option"
                  onClick={() => choose(o.value)}
                >
                  <kbd>{i + 1}</kbd>
                  {o.label}
                </button>
              ))}
            </div>
          )}
          {last && (
            <div className="mind-send">
              <button type="button" className="paper-button" disabled={sending} onClick={() => void send()}>
                {sending ? 'Enviando…' : 'Enviar y analizar'}
              </button>
              <span className="paper-meta">
                {answered} respuestas · su resultado estará listo en unos {def.delay_minutes} minutos
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
