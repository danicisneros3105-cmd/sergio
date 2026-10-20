// «Primeros pasos»: what an everyday person does with Sergio, in five
// minutes, and how to keep him up to date. One product, one name.

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { Check, Command, Copy, MessageSquare, ScanFace, Search, Users } from 'lucide-react';

const UPDATE =
  'wsl -d Ubuntu -- bash -lc "cd ~/sergio && git fetch origin main && git checkout -B main origin/main && bash scripts/actualizar-sergio.sh main"';

const STEPS: Array<{ icon: typeof Check; color: string; title: string; text: string; to: string; cta: string }> = [
  {
    icon: MessageSquare,
    color: 'var(--sec-chat)',
    title: 'Hable con él',
    text: 'Diga «Sergio» o escriba. Recuerda lo que hablaron antes, por chat o por voz.',
    to: '/chat',
    cta: 'Ir al chat',
  },
  {
    icon: Users,
    color: 'var(--sec-chat)',
    title: 'Su equipo',
    text: 'Rihno, Manchas, Hous y Tennessee trabajan para usted sin parar. Pídales algo en Nodes.',
    to: '/nodes',
    cta: 'Abrir Nodes',
  },
  {
    icon: Search,
    color: 'var(--sec-chat)',
    title: 'Investigue a lo grande',
    text: 'Agent Swarm reparte una pregunta grande entre muchos agentes y le entrega un informe.',
    to: '/swarm',
    cta: 'Abrir Agent Swarm',
  },
  {
    icon: ScanFace,
    color: 'var(--sec-profile)',
    title: 'Configure su Face ID',
    text: 'Para aprobar lo importante (borrar, publicar, pagar) con la cara.',
    to: '/faces',
    cta: 'Configurar',
  },
  {
    icon: Command,
    color: 'var(--sec-workspace)',
    title: 'Todo con Ctrl K',
    text: 'Abra la paleta y escriba lo que busca: páginas, acciones, modelos.',
    to: '/atajos',
    cta: 'Ver atajos',
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
