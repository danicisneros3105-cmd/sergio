// Salud mental: the cover, the survey and its results, and the mental gym.

import { useCallback, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { clock, countdown, salud, type ScaleScore, type SurveyResult } from '../../lib/salud';
import portada from '../../assets/salud/portada-salud-mental.webp';
import { HealthGym } from './HealthGym';
import { MindSurvey, SURVEY_IMAGES, hasDraft } from './MindSurvey';

const PICTURE_IMAGE: Record<string, string> = {
  pic_suficiente: 'no-suficiente',
  pic_pensar: 'pensar-demasiado',
  pic_encajar: 'encajar',
};

function day(ts: number) {
  return new Date(ts * 1000).toLocaleDateString('es', { day: 'numeric', month: 'long', year: 'numeric' });
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
      <h2 className="mind-result-title">Resultado del {day(result.created)}</h2>
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
      {result.sources && (
        <section className="salud-block">
          <h3 className="paper-label">Fuentes</h3>
          <ul className="mind-sources">
            {result.sources.map((s) => (
              <li key={s.scale}>
                <b>{s.scale}.</b> {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.cite}</a> : s.cite}
              </li>
            ))}
          </ul>
        </section>
      )}
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

  const draft = hasDraft();
  return (
    <div className="mind-home">
      <section className="mind-cover">
        <img src={portada} alt="Un cerebro flotando sobre un traje con corbata, sobre fondo rojo" />
        <div className="mind-cover-body">
          <h2>Encuesta de salud mental</h2>
          <ul className="mind-covers">
            <li>No sentirse suficiente</li>
            <li>Pensar demasiado y problemas acumulados</li>
            <li>Querer encajar siendo otra persona</li>
          </ul>
          <button type="button" className="paper-button" onClick={() => setMode('survey')}>
            {draft ? 'Continuar la encuesta' : 'Empezar la encuesta'}
          </button>
          <p className="paper-meta">56 preguntas, unos 10 minutos, con escalas validadas de Columbia, Penn State, Michigan, Chicago y UCLA, entre otras. El análisis llega unos 30 minutos después.</p>
        </div>
      </section>

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

      <section className="salud-block">
        <h3 className="paper-label">Gimnasio mental</h3>
        <Gym />
      </section>
    </div>
  );
}
