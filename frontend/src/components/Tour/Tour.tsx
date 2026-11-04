// The tour: a small silent motion-graphics clip per step (MotionClip.tsx,
// 4 Nov 2026) that shows, not tells, what Sergio does — one per
// step, each with «Probar» to go and do it (owner, 27 Oct 2026: «un tour
// tutorial con widgets para aprender a usar la app»). It opens once after
// signing in and again from Ayuda or the palette («Ver el tour»).

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { X } from 'lucide-react';
import { TOUR_SEEN, setFlag } from '../../lib/session';
import { MotionClip } from './MotionClip';
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
}

const STEPS: Step[] = [
  { key: 'hola', title: 'Bienvenido a Sergio', text: 'Su asistente con todas las IA del mundo, no solo una. En pocos pasos verá lo que puede hacer y dónde está cada cosa.' },
  { key: 'chat', title: 'Escriba o hable', text: 'Pídale lo que sea, como a una persona. Recuerda lo que hablaron antes.', to: '/chat', cta: 'Abrir el chat', point: 'textarea' },
  { key: 'voz', title: 'Conversación por voz', text: 'Diga «Sergio» y hable. Responde en voz alta y se le puede interrumpir.', to: '/chat', cta: 'Probar la voz', point: 'Conversación' },
  { key: 'modelos', title: 'Todos los modelos', text: 'Gemini, GPT, Claude, DeepSeek y cientos más. Elija uno o deje que Sergio elija el mejor.', to: '/chat', then: 'modelo', cta: 'Elegir modelo' },
  { key: 'nodes', title: 'Su equipo: Nodes', text: 'Cuatro empleados que trabajan sin parar: organizan, investigan, diseñan y deciden.', to: '/nodes', cta: 'Conocer al equipo' },
  { key: 'video', title: 'Videos de creador', text: 'Le muestra 3 videos que hoy funcionan para su idea, planea con usted el guion y una animación de cada toma, y edita lo que usted grabe con subtítulos, música y sonido de estudio. O lo hace entero.', to: '/chat', then: 'video', cta: 'Hacer un video' },
  { key: 'auto', title: 'Cowork: su día en un lugar', text: 'Cowork hace las tareas largas por usted. Debajo de la caja hay dos filas cerradas, «Organizador» (recordatorios y pendientes de hoy) y «Automatizaciones» (un resumen cada mañana, vigilar una web, videos programados). Ábralas con un toque. Lo que envía, compra o borra espera su sí.', to: '/cowork?ver=organizador', cta: 'Verlas en Cowork', point: 'Organizador' },
  { key: 'salud', title: 'Salud simple', text: 'Medicinas a su hora, metas y cómo se siente. Sin inventar datos.', to: '/salud', cta: 'Abrir Salud' },
  { key: 'uso', title: 'Uso y plan', text: 'Cuánto lleva usado hoy y qué plan tiene, en una mirada.', to: '/uso', cta: 'Ver el uso' },
  { key: 'dividir', title: 'Multitarea', text: 'El botón de dos columnas, arriba a la derecha del chat, pone dos apps de su equipo lado a lado (por ejemplo Chrome y Word). En el teléfono o el Mac le dice cómo hacerlo con su sistema.', cta: 'Probarlo ahora', split: true, point: 'Multitarea' },
  { key: 'atajos', title: 'Un atajo para todo', text: 'Ctrl K (⌘ K en Mac) busca páginas, acciones y modelos. Este tour vuelve desde Ayuda.', to: '/atajos', cta: 'Ver atajos' },
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

  return (
    <div className="tour-backdrop" role="dialog" aria-modal="true" aria-label="Tour de Sergio">
      <div className="tour-card" key={step.key}>
        <button type="button" className="tour-close" aria-label="Cerrar el tour" onClick={close}>
          <X size={16} />
        </button>
        <div className="tour-widget tour-clip">
          <MotionClip clip={step.key} label={step.title} />
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
                  window.setTimeout(() => window.dispatchEvent(new CustomEvent('sergio:multitarea')), 250);
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
