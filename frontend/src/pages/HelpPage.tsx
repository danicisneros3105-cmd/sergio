// Help: how to use Sergio, shortcuts, voice, privacy, plans and where to ask.

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { PaperPage } from '../components/Paper/PaperPage';
import { CONNECT_GUIDES, GuideList, LEARN_GUIDES } from '../components/Settings/Guides';
import { apiFetch } from '../lib/api';
import { clearCrashes, crashReport, readCrashes } from '../lib/crashlog';
import './plans.css';

const TOPICS: Array<{ q: string; a: string[] }> = [
  {
    q: 'Cómo empezar',
    a: ['Escríbale en el chat o dígale «Sergio» en voz alta. Recuerda lo que hablaron antes, por chat o por voz.'],
  },
  {
    q: 'Multitarea: dos apps lado a lado',
    a: [
      'Toque el botón de dos columnas, arriba a la derecha del chat, escriba las dos apps (por ejemplo Chrome y Word) y Sergio las pone una al lado de la otra en su PC. También puede decirlo: «pon Chrome y Word lado a lado».',
      'En el Mac, el iPad o Android, el mismo botón le dice cómo hacerlo con la pantalla dividida de su sistema.',
    ],
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

/** «Si algo falla»: the last errors kept on this device, to copy for whoever helps. */
function Faults() {
  const [list, setList] = useState(readCrashes);
  const [copied, setCopied] = useState(false);
  if (!list.length) return null;
  return (
    <details className="help-faults">
      <summary>Si algo falla ({list.length})</summary>
      <p>Sergio guarda en este equipo los últimos errores (nada se envía). Cópielos y mándelos a quien le ayude.</p>
      <pre style={{ maxHeight: 220, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 12 }}>{crashReport(list)}</pre>
      <button
        type="button"
        className="paper-button"
        onClick={() => {
          void navigator.clipboard?.writeText(crashReport(list)).then(() => setCopied(true));
        }}
      >
        {copied ? 'Copiado' : 'Copiar'}
      </button>{' '}
      <button
        type="button"
        className="paper-button"
        data-variant="quiet"
        onClick={() => {
          clearCrashes();
          setList([]);
        }}
      >
        Borrar
      </button>
    </details>
  );
}

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
    <PaperPage title="Ayuda y tutoriales">
      <h2 className="paper-label">Aprenda a usar Sergio</h2>
      <GuideList guides={LEARN_GUIDES} />
      <h2 className="paper-label" style={{ marginTop: 24 }}>Conectar claves, cuentas, plugins y skills</h2>
      <GuideList guides={CONNECT_GUIDES} />
      <h2 className="paper-label" style={{ marginTop: 24 }}>Preguntas</h2>
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
      <Faults />
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
