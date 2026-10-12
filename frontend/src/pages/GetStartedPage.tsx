// «Primeros pasos»: what an everyday person does with Sergio, in five
// minutes, and how to keep him up to date. One product, one name.

import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Check, Copy, MessageSquare, NotebookPen, ScanFace, Shapes } from 'lucide-react';

const UPDATE =
  'wsl -d Ubuntu -- bash -lc "cd ~/sergio && git fetch origin main && git checkout -B main origin/main && bash scripts/actualizar-sergio.sh main"';

const STEPS: Array<{ icon: typeof Check; color: string; title: string; text: string; to: string; cta: string }> = [
  {
    icon: MessageSquare,
    color: 'var(--sec-chat)',
    title: 'Hable con él',
    text: 'Haga clic en cualquier parte y hable: Sergio le escucha siempre, como una persona. También puede escribir.',
    to: '/chat',
    cta: 'Ir al chat',
  },
  {
    icon: ScanFace,
    color: 'var(--sec-profile)',
    title: 'Configure su Face ID',
    text: 'Para aprobar lo importante (borrar, publicar, pagar) con la cara, con un código de respaldo.',
    to: '/faces',
    cta: 'Configurar',
  },
  {
    icon: NotebookPen,
    color: 'var(--sec-workspace)',
    title: 'Guarde sus ideas',
    text: 'El Workspace guarda notas, tareas y tablas en su equipo, también sin internet.',
    to: '/workspace',
    cta: 'Abrir Workspace',
  },
  {
    icon: Shapes,
    color: 'var(--sec-creator)',
    title: 'Cree algo',
    text: 'Creator diseña imágenes, láminas técnicas y modelos 3D a partir de lo que usted describa.',
    to: '/creator',
    cta: 'Abrir Creator',
  },
];

export function GetStartedPage() {
  const navigate = useNavigate();
  const [copied, setCopied] = useState(false);
  return (
    <div className="paper-page start-page">
      <h1 className="chat-hello">
        <span className="chat-hello-name">Bienvenido, señor</span>
        <span className="chat-hello-ask">Así se usa Sergio</span>
      </h1>
      <div className="start-steps">
        {STEPS.map(({ icon: Icon, color, title, text, to, cta }, i) => (
          <section key={title} className="start-step" style={{ '--sec': color } as React.CSSProperties}>
            <span className="starter-icon" aria-hidden="true">
              <Icon size={18} strokeWidth={1.8} />
            </span>
            <div>
              <h2>
                <small>{i + 1}</small> {title}
              </h2>
              <p>{text}</p>
            </div>
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate(to)}>
              {cta}
            </button>
          </section>
        ))}
      </div>
      <section className="start-update">
        <h2>Actualizar</h2>
        <p>En PowerShell de Windows, siempre el mismo comando:</p>
        <pre>{UPDATE}</pre>
        <button
          type="button"
          className="paper-button"
          onClick={() => {
            void navigator.clipboard?.writeText(UPDATE).then(() => setCopied(true));
          }}
        >
          {copied ? <Check size={15} /> : <Copy size={15} />} {copied ? 'Copiado' : 'Copiar comando'}
        </button>
      </section>
    </div>
  );
}

export default GetStartedPage;
