// The tour: ten small widgets that show, not tell, what Sergio does — one per
// step, each with «Probar» to go and do it (owner, 27 Oct 2026: «un tour
// tutorial con widgets para aprender a usar la app»). It opens once after
// signing in and again from Ayuda or the palette («Ver el tour»).

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { X } from 'lucide-react';
import { TOUR_SEEN, setFlag } from '../../lib/session';
import { useAppStore } from '../../lib/store';
import { pointAt } from '../../lib/pointer';
import './tour.css';

interface Step {
  key: string;
  title: string;
  text: string;
  to?: string;
  cta?: string;
  /** What opens once there: the model sheet or the video sheet. */
  then?: 'modelo' | 'video';
  /** Opens the second screen instead of going to a page. */
  split?: boolean;
  /** What Sergio's pointer shows once there (words of a button or a selector). */
  point?: string;
  widget: () => React.ReactNode;
}

const Chat = () => (
  <div className="tw-chat" aria-hidden="true">
    <span className="tw-bubble me">Hazme un resumen de mis correos</span>
    <span className="tw-bubble">Tiene 3 importantes, señor. El primero…</span>
    <span className="tw-bubble me">Perfecto</span>
  </div>
)
const Voice = () => (
  <div className="tw-voice" aria-hidden="true">
    <span className="tw-orb" />
    <span className="tw-wave">{Array.from({ length: 9 }, (_, i) => <i key={i} style={{ animationDelay: `${i * 0.09}s` }} />)}</span>
    <small>«Sergio, ¿qué tengo hoy?»</small>
  </div>
)
const Models = () => (
  <div className="tw-chips" aria-hidden="true">
    {['Gemini', 'GPT-5.6', 'Claude 5.5', 'DeepSeek V4', 'Grok', 'Llama', '+ cientos'].map((m) => (
      <span key={m} className="tw-chip">{m}</span>
    ))}
  </div>
)
const Nodes = () => (
  <div className="tw-nodes" aria-hidden="true">
    {[['Rihno', 'Organiza'], ['Manchas', 'Investiga'], ['Hous', 'Diseña'], ['Tennessee', 'Decide']].map(([n, r], i) => (
      <span key={n} className="tw-node" style={{ animationDelay: `${i * 0.15}s` }}>
        <b>{n}</b>
        <small>{r}</small>
      </span>
    ))}
  </div>
)
const Video = () => (
  <div className="tw-video" aria-hidden="true">
    <div className="tw-frame">
      <span className="tw-cap">LAS DECISIONES <em>INVISIBLES</em></span>
    </div>
    <div className="tw-track">
      {[3, 2, 4, 2, 3, 5, 2, 3].map((w, i) => <i key={i} style={{ flex: w }} />)}
    </div>
    <small>Guion · voz · clips reales · subtítulos · música</small>
  </div>
)
const Auto = () => (
  <div className="tw-rows" aria-hidden="true">
    <span><b>YouTube</b> 3 shorts al día <em>auto</em></span>
    <span><b>Clientes</b> 12 nuevos · 8 propuestas</span>
    <span><b>Trading</b> en papel · límites activos</span>
  </div>
)
const Health = () => (
  <div className="tw-ring" aria-hidden="true">
    <svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="26" /><circle className="tw-ring-on" cx="32" cy="32" r="26" /></svg>
    <small>Medicinas, metas y su mente</small>
  </div>
)
const Usage = () => (
  <div className="tw-meter" aria-hidden="true">
    <span><i style={{ width: '64%' }} /></span>
    <small>Uso de hoy · 64 %</small>
  </div>
)
const Palette = () => (
  <div className="tw-keys" aria-hidden="true">
    <kbd>Ctrl</kbd>
    <kbd>K</kbd>
    <small>Todo, en un atajo</small>
  </div>
)
const Split = () => (
  <div className="tw-split" aria-hidden="true">
    <span className="tw-pane tw-pane-a"><i /><i /><i /></span>
    <span className="tw-fold" />
    <span className="tw-pane tw-pane-b"><i /><i /></span>
  </div>
)
const Hello = () => (
  <div className="tw-hello" aria-hidden="true">
    <span className="tw-logo" />
  </div>
)

const STEPS: Step[] = [
  { key: 'hola', title: 'Bienvenido a Sergio', text: 'Su asistente con todas las IA del mundo, no solo una. En diez pasos verá lo que puede hacer.', widget: Hello },
  { key: 'chat', title: 'Escriba o hable', text: 'Pídale lo que sea, como a una persona. Recuerda lo que hablaron antes.', to: '/chat', cta: 'Abrir el chat', point: 'textarea', widget: Chat },
  { key: 'voz', title: 'Conversación por voz', text: 'Diga «Sergio» y hable. Responde en voz alta y se le puede interrumpir.', to: '/chat', cta: 'Probar la voz', point: 'Conversación', widget: Voice },
  { key: 'modelos', title: 'Todos los modelos', text: 'Gemini, GPT, Claude, DeepSeek y cientos más. Elija uno o deje que Sergio elija el mejor.', to: '/chat', then: 'modelo', cta: 'Elegir modelo', widget: Models },
  { key: 'nodes', title: 'Su equipo: Nodes', text: 'Cuatro empleados que trabajan sin parar: organizan, investigan, diseñan y deciden.', to: '/nodes', cta: 'Conocer al equipo', widget: Nodes },
  { key: 'video', title: 'Videos de nivel', text: 'Del tema al video terminado: guion, voz, clips reales de internet, subtítulos y música.', to: '/chat', then: 'video', cta: 'Hacer un video', widget: Video },
  { key: 'auto', title: 'Automatice', text: 'Canales que publican solos, clientes y empleos que llegan, trading con límites.', to: '/automatizar', cta: 'Ver Automatizar', widget: Auto },
  { key: 'salud', title: 'Salud simple', text: 'Medicinas a su hora, metas y cómo se siente. Sin inventar datos.', to: '/salud', cta: 'Abrir Salud', widget: Health },
  { key: 'uso', title: 'Uso y plan', text: 'Cuánto lleva usado hoy y qué plan tiene, en una mirada.', to: '/uso', cta: 'Ver el uso', widget: Usage },
  { key: 'dividir', title: 'Dos cosas a la vez', text: 'El botón de dos columnas (arriba a la derecha del chat) abre una segunda pantalla al lado, como un iPhone plegable. Vuelva a tocarlo para unirlas.', cta: 'Probarlo ahora', split: true, point: 'Dividir', widget: Split },
  { key: 'atajos', title: 'Un atajo para todo', text: 'Ctrl K (⌘ K en Mac) busca páginas, acciones y modelos. Este tour vuelve desde Ayuda.', to: '/atajos', cta: 'Ver atajos', widget: Palette },
]

export function Tour({ onClose }: { onClose: () => void }) {
  const [i, setI] = useState(0);
  const navigate = useNavigate();
  const step = STEPS[i];
  const last = i === STEPS.length - 1;

  const close = () => {
    setFlag(TOUR_SEEN);
    setFlag('sergio-onboarded');
    onClose();
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
      if (e.key === 'ArrowRight') setI((n) => Math.min(STEPS.length - 1, n + 1));
      if (e.key === 'ArrowLeft') setI((n) => Math.max(0, n - 1));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const Widget = step.widget;
  return (
    <div className="tour-backdrop" role="dialog" aria-modal="true" aria-label="Tour de Sergio">
      <div className="tour-card" key={step.key}>
        <button type="button" className="tour-close" aria-label="Cerrar el tour" onClick={close}>
          <X size={16} />
        </button>
        <div className="tour-widget">
          <Widget />
        </div>
        <h2>{step.title}</h2>
        <p>{step.text}</p>
        <div className="tour-dots" aria-label={`Paso ${i + 1} de ${STEPS.length}`}>
          {STEPS.map((s, n) => (
            <button
              key={s.key}
              type="button"
              aria-label={`Ir al paso ${n + 1}`}
              className={n === i ? 'on' : ''}
              onClick={() => setI(n)}
            />
          ))}
        </div>
        <div className="tour-actions">
          {i > 0 ? (
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => setI(i - 1)}>
              Atrás
            </button>
          ) : (
            <button type="button" className="paper-button" data-variant="quiet" onClick={close}>
              Saltar
            </button>
          )}
          {(step.to || step.split) && (
            <button
              type="button"
              className="paper-button"
              data-variant="quiet"
              onClick={() => {
                close();
                if (step.point) window.setTimeout(() => pointAt({ target: step.point!, text: step.title }), 700);
                if (step.split) {
                  navigate('/chat');
                  window.setTimeout(() => window.dispatchEvent(new CustomEvent('sergio:split', { detail: 'on' })), 250);
                  return;
                }
                navigate(step.to!);
                if (step.then === 'modelo') useAppStore.getState().setCommandPaletteOpen(true);
                if (step.then === 'video') window.setTimeout(() => window.dispatchEvent(new CustomEvent('sergio:video')), 150);
              }}
            >
              {step.cta}
            </button>
          )}
          <button type="button" className="paper-button" onClick={() => (last ? close() : setI(i + 1))}>
            {last ? 'Empezar' : 'Siguiente'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default Tour;
