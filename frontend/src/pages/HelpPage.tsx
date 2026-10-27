// Help: how to use Sergio, shortcuts, voice, privacy, plans and where to ask.

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { PaperPage } from '../components/Paper/PaperPage';
import { apiFetch } from '../lib/api';
import './plans.css';

const TOPICS: Array<{ q: string; a: string[] }> = [
  {
    q: 'Cómo empezar',
    a: ['Escríbale en el chat o dígale «Sergio» en voz alta. Recuerda lo que hablaron antes, por chat o por voz.'],
  },
  {
    q: 'Atajos',
    a: [
      'Ctrl K (⌘ K en Mac) abre la paleta: páginas, acciones y modelos.',
      'G y una letra lleva a una página. Esc tres veces detiene Nodes, Swarm, Cowork y la voz.',
    ],
  },
  {
    q: 'La voz',
    a: [
      'Sergio solo responde lo que es para él: su nombre abre la conversación y, después de cada respuesta, tiene unos segundos para seguir sin nombrarlo.',
      'Si hay un video o la tele de fondo, no los responde. Para silenciarlo use el botón del micrófono o apague «Conversación siempre activa» en Configuración.',
    ],
  },
  {
    q: 'Planes, uso y pagos',
    a: [
      'En Planes ve su plan, cuánto ha usado hoy y cuánto cuesta cada plan en su moneda. El pago se hace en la página segura del procesador; Sergio nunca le pide la tarjeta.',
      'Si ya pagó, pegue su clave de licencia en Planes, Facturación.',
    ],
  },
  {
    q: 'Idioma',
    a: [
      'Configuración, Voz, «Idioma de Sergio»: español, inglés, francés, portugués, italiano o alemán. La interfaz está en español.',
    ],
  },
  {
    q: 'Privacidad',
    a: [
      'Sus datos viven en este equipo. En Salud mental puede marcar «Solo en este equipo» para que la IA nunca lea sus respuestas.',
      'Mensajes, llamadas, compras y borrados nunca los hace Sergio por su cuenta: siempre le pide permiso.',
    ],
  },
  {
    q: 'Algo no funciona',
    a: [
      'Registro muestra lo que pasó. Si Sergio tarda, es casi siempre el proveedor del modelo: Sergio cambia solo a otro.',
      'Para actualizar: botón «Actualizar» de la barra lateral.',
    ],
  },
];

export function HelpPage() {
  const navigate = useNavigate();
  const [support, setSupport] = useState('');
  useEffect(() => {
    apiFetch('/v1/plans/me')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setSupport(d?.support || ''))
      .catch(() => setSupport(''));
  }, []);
  return (
    <PaperPage title="Ayuda">
      <div className="help-list">
        {TOPICS.map((t) => (
          <details key={t.q}>
            <summary>{t.q}</summary>
            {t.a.map((x) => (
              <p key={x}>{x}</p>
            ))}
          </details>
        ))}
      </div>
      <p>
        <button type="button" className="paper-button" onClick={() => window.dispatchEvent(new CustomEvent('sergio:tour'))}>
          Ver el tour
        </button>{' '}
        <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/get-started')}>
          Primeros pasos
        </button>{' '}
        <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/logs')}>
          Registro
        </button>{' '}
        {support && (
          <a className="paper-button" href={`mailto:${support}`}>
            Escribir a soporte
          </a>
        )}
      </p>
    </PaperPage>
  );
}

export default HelpPage;
