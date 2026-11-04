// «Primeros pasos»: what an everyday person does with Sergio, in five
// minutes, and how to keep him up to date. One product, one name.

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { usePersonal, welcome } from '../lib/personal';
import { Check, Clapperboard, Columns2, Copy, MessageSquare, Zap } from 'lucide-react';

const UPDATE =
  'wsl -d Ubuntu -- bash -lc "cd ~/sergio && git fetch origin main && git checkout -B main origin/main && bash scripts/actualizar-sergio.sh main"';

// Four things to do first, in plain words (owner, 28 Oct 2026: «mejora la
// bienvenida… que sea usable por cualquiera»). The update command waits
// folded below: a person who never opens a terminal never needs to see it.
const TILES: Array<{ icon: typeof Check; title: string; text: string; run: 'chat' | 'video' | 'split' | 'tour' | 'auto' }> = [
  { icon: MessageSquare, title: 'Pregúntele algo', text: 'Escriba o diga «Sergio». Recuerda lo que hablaron.', run: 'chat' },
  { icon: Clapperboard, title: 'Pídale un video', text: 'Del tema al video terminado, con clips reales.', run: 'video' },
  { icon: Columns2, title: 'Dos cosas a la vez', text: 'Divida la pantalla, como un iPhone plegable.', run: 'split' },
  { icon: Zap, title: 'Que trabaje solo', text: 'Canales, clientes y empleos en segundo plano.', run: 'auto' },
];

export const ONBOARDED = 'sergio-onboarded';

export function GetStartedPage() {
  const personal = usePersonal();
  const navigate = useNavigate();
  const [copied, setCopied] = useState(false);
  // Seen once: from now on Sergio opens where the owner asked (chat, Nodes…).
  useEffect(() => {
    try {
      localStorage.setItem(ONBOARDED, '1');
    } catch {
      // storage blocked: Layout never redirects then either
    }
  }, []);
  return (
    <div className="paper-page start-page">
      <h1 className="chat-hello">
        <span className="chat-hello-name">{welcome(personal)}</span>
      </h1>
      <div className="start-tiles">
        {TILES.map(({ icon: Icon, title, text, run }) => (
          <button
            key={title}
            type="button"
            className="start-tile"
            onClick={() => {
              if (run === 'auto') return navigate('/cowork?ver=automatizar');
              navigate('/chat');
              window.setTimeout(() => {
                if (run === 'video') window.dispatchEvent(new CustomEvent('sergio:video'));
                if (run === 'split') window.dispatchEvent(new CustomEvent('sergio:multitarea'));
              }, 250);
            }}
          >
            <span className="start-tile-icon" aria-hidden="true">
              <Icon size={20} strokeWidth={1.8} />
            </span>
            <b>{title}</b>
            <small>{text}</small>
          </button>
        ))}
      </div>
      <p className="start-tour">
        <button type="button" className="paper-button" onClick={() => window.dispatchEvent(new CustomEvent('sergio:tour'))}>
          Ver el tour de un minuto
        </button>
      </p>
      <details className="start-update">
        <summary>Actualizar Sergio</summary>
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
      </details>
    </div>
  );
}

export default GetStartedPage;
