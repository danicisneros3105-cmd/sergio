// Salud mental: the cover, the survey and its results, and the mental gym.

import { useCallback, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { clock, countdown, salud, type ScaleScore, type SurveyResult, type SurveyVariant } from '../../lib/salud';
import portada from '../../assets/salud/portada-salud-mental.webp';
import { HealthGym } from './HealthGym';
import { Credits } from './Credits';
import { MindSurvey, SURVEY_IMAGES, hasDraft } from './MindSurvey';

const PICTURE_IMAGE: Record<string, string> = {
  pic_suficiente: 'no-suficiente',
  pic_pensar: 'pensar-demasiado',
  pic_encajar: 'encajar',
};

function day(ts: number) {
  return new Date(ts * 1000).toLocaleDateString('es', { day: 'numeric', month: 'long', year: 'numeric' });
}

/** «Solo en este equipo»: health and mental health never reach the AI service. */
function LocalOnly() {
  const [local, setLocal] = useState<boolean | null>(null);
  useEffect(() => {
    void apiFetch('/v1/healthdata/privacy')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setLocal(d ? Boolean(d.local) : null))
      .catch(() => setLocal(null));
  }, []);
  if (local === null) return null;
  const change = async (on: boolean) => {
    try {
      const r = await apiFetch('/v1/healthdata/privacy', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ local: on }),
      });
      if (!r.ok) throw new Error();
      setLocal(Boolean((await r.json()).local));
    } catch {
      toast.error('No pude guardar la preferencia.');
    }
  };
  return (
    <label className="paper-meta mind-local">
      <input type="checkbox" checked={local} onChange={(e) => void change(e.target.checked)} />{' '}
      Solo en este equipo: la lectura la escribe Sergio sin la IA.{' '}
      {local
        ? ''
        : 'Si no, la lee Gemini (Google) sin su nombre ni datos de contacto; con una clave gratuita Google puede revisar lo enviado.'}
    </label>
  );
}

function Crisis({ text }: { text: string }) {
  return (
    <div className="mind-crisis" role="alert">
      <b>Antes de nada</b>
      <p>{text}</p>
    </div>
  );
}

function ScaleCard({ s }: { s: ScaleScore }) {
  if (s.score === null) {
    return (
      <div className="mind-scale" data-empty="1">
        <span>{s.label}</span>
        <b>—</b>
        <small>Incompleta ({s.answered} de {s.items})</small>
      </div>
    );
  }
  const pct = ((s.score - s.min) / Math.max(1, s.max - s.min)) * 100;
  return (
    <div className="mind-scale">
      <span>{s.label}</span>
      <b>
        {s.score}
        <small> / {s.max}</small>
      </b>
      <div className="mind-bar" aria-hidden>
        <i style={{ width: `${pct}%` }} />
      </div>
      <small>
        {s.words}
        {s.orientative ? ' · orientativa' : ''}
      </small>
      {s.subscales && (
        <ul className="mind-subscales">
          {s.subscales.map((x) => (
            <li key={x.key}>
              <span>{x.label}</span>
              <em>
                {x.score} / {x.max} · {x.words}
              </em>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Waiting({ result, onReady }: { result: SurveyResult; onReady: () => void }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      tick((n) => n + 1);
      if (Date.now() / 1000 >= result.ready_at) onReady();
    }, 1000);
    return () => window.clearInterval(id);
  }, [result.ready_at, onReady]);
  return (
    <div className="mind-waiting">
      {result.crisis && result.crisis_text && <Crisis text={result.crisis_text} />}
      <span className="paper-label">Analizando</span>
      <p className="mind-waiting-time">{countdown(result.ready_at)}</p>
      <p>Sergio está leyendo sus respuestas con calma. El resultado estará listo a las {clock(result.ready_at)}; puede cerrar esta pantalla y volver.</p>
    </div>
  );
}

function Result({ result, onBack }: { result: SurveyResult; onBack: () => void }) {
  const scores = result.scores;
  return (
    <div className="mind-result">
      <button type="button" className="paper-button" data-variant="quiet" onClick={onBack}>
        Volver
      </button>
      <h2 className="mind-result-title">
        Resultado del {day(result.created)}
        <small>{result.variant === 'corta' ? 'Encuesta corta' : 'Encuesta larga'}</small>
      </h2>
      {result.crisis && result.crisis_text && <Crisis text={result.crisis_text} />}
      {result.reading && (
        <section className="mind-reading">
          {/* Models put a heading and its text on consecutive lines: keep those breaks. */}
          <ReactMarkdown>{result.reading.replace(/([^\n])\n(?!\n|\s*[-*\d])/g, '$1  \n')}</ReactMarkdown>
          {result.reading_by === 'codigo' && <p className="paper-meta">Lectura escrita sin la IA: el motor no respondió a tiempo.</p>}
        </section>
      )}
      {scores && (
        <>
          <section className="salud-block">
            <h3 className="paper-label">Su punto de partida</h3>
            <div className="mind-pictures">
              {scores.pictures.map((p) => (
                <figure key={p.id}>
                  <img src={SURVEY_IMAGES[PICTURE_IMAGE[p.id]]} alt="" />
                  <figcaption>
                    <span>{p.domain}</span>
                    <b>{p.label || 'Sin responder'}</b>
                  </figcaption>
                </figure>
              ))}
            </div>
          </section>
          <section className="salud-block">
            <h3 className="paper-label">Escalas</h3>
            <div className="mind-scales">
              {scores.scales.map((s) => (
                <ScaleCard key={s.key} s={s} />
              ))}
            </div>
          </section>
        </>
      )}
      <Credits scope="mente" />
      <p className="paper-meta">Es una orientación a partir de escalas validadas, no un diagnóstico. Si algo le preocupa, hable con un profesional de salud mental.</p>
    </div>
  );
}

/** The mental gym still keeps its sessions in the older health hub. */
function Gym() {
  const [hub, setHub] = useState<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  useEffect(() => {
    apiFetch('/v1/desktop/health')
      .then((r) => r.json())
      .then((d) => setHub(d.hub ?? null))
      .catch(() => setHub(null));
  }, []);
  if (!hub) return null;
  return <HealthGym hub={hub} setHub={setHub} />;
}

export function MindTab() {
  const [mode, setMode] = useState<'home' | 'survey' | 'view'>('home');
  const [variant, setVariant] = useState<SurveyVariant>('corta');
  const [list, setList] = useState<SurveyResult[]>([]);
  const [current, setCurrent] = useState<SurveyResult | null>(null);

  const load = useCallback(() => {
    salud.surveys().then(setList).catch(() => setList([]));
  }, []);
  useEffect(load, [load]);

  const open = useCallback(async (id: string) => {
    try {
      setCurrent(await salud.surveyResult(id));
      setMode('view');
    } catch {
      toast.error('No pude abrir ese resultado.');
    }
  }, []);

  if (mode === 'survey') {
    return (
      <MindSurvey
        variant={variant}
        onClose={() => setMode('home')}
        onSent={(r) => {
          setCurrent(r);
          setMode('view');
          load();
        }}
      />
    );
  }

  if (mode === 'view' && current) {
    return current.status === 'waiting' ? (
      <div>
        <button type="button" className="paper-button" data-variant="quiet" onClick={() => setMode('home')}>
          Volver
        </button>
        <Waiting result={current} onReady={() => void open(current.id)} />
      </div>
    ) : (
      <Result
        result={current}
        onBack={() => {
          setMode('home');
          load();
        }}
      />
    );
  }

  return (
    <div className="mind-home">
      <section className="mind-cover">
        <img className="mind-cover-art" src={portada} width={754} height={1000} alt="Un cerebro flotando sobre un traje con corbata, sobre fondo rojo" />
        <div className="mind-cover-body">
          <h2>Encuesta de salud mental</h2>
          <ul className="mind-covers">
            <li>No sentirse suficiente</li>
            <li>Pensar demasiado y problemas acumulados</li>
            <li>Querer encajar siendo otra persona</li>
          </ul>
          <div className="mind-choose">
            {(
              [
                ['corta', 'Corta', '12 preguntas · unos 3 minutos'],
                ['larga', 'Larga', '56 preguntas · unos 12 minutos'],
              ] as const
            ).map(([key, label, meta]) => (
              <button
                key={key}
                type="button"
                className="mind-variant"
                onClick={() => {
                  setVariant(key);
                  setMode('survey');
                }}
              >
                <b>{hasDraft(key) ? `Continuar la ${label.toLowerCase()}` : label}</b>
                <span>{meta}</span>
              </button>
            ))}
          </div>
          <p className="paper-meta">El análisis de Sergio llega unos 30 minutos después de enviarla. No es un diagnóstico.</p>
          <LocalOnly />
        </div>
      </section>

      <div className="mind-strip" aria-label="Las tres preguntas con imagen">
        {(
          [
            ['no-suficiente', 'Un espejo roto frente a una silueta con sombrero', 'No sentirse suficiente'],
            ['pensar-demasiado', 'Una figura enterrada bajo montones de periódicos', 'Pensar demasiado'],
            ['encajar', 'Un hombre con máscara de león rodeado de leones rojos', 'Querer encajar'],
          ] as const
        ).map(([image, alt, caption]) => (
          <figure key={image}>
            <img src={SURVEY_IMAGES[image]} alt={alt} loading="lazy" />
            <figcaption>{caption}</figcaption>
          </figure>
        ))}
      </div>

      {list.length > 0 && (
        <section className="salud-block">
          <h3 className="paper-label">Sus resultados</h3>
          <ul className="mind-history">
            {list.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => void open(r.id)}>
                  <span>{day(r.created)}</span>
                  <em>{r.status === 'ready' ? 'Listo' : `Listo a las ${clock(r.ready_at)}`}</em>
                </button>
                <button
                  type="button"
                  className="mac-icon-btn"
                  aria-label="Borrar este resultado"
                  onClick={async () => {
                    if (!window.confirm('¿Borrar este resultado?')) return;
                    await salud.dropSurvey(r.id);
                    load();
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <Credits scope="mente" />

      <section className="salud-block">
        <h3 className="paper-label">Gimnasio mental</h3>
        <Gym />
      </section>
    </div>
  );
}
