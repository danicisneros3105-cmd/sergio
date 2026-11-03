import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ArrowUp, Check, CircleSlash, ExternalLink, Mic, Play, Plus, Volume2, VolumeX, X } from 'lucide-react';
import { toast } from 'sonner';
import { NodeCritter } from '../../components/Nodes/NodeCritter';
import { useTtsStore } from '../../lib/tts';
import { latestWork, withoutWork, type Work } from '../../lib/nodeCanvas';
import { nodesApi, type NodeMessage, type SergioNode } from '../../lib/nodes';
import { look } from './shared';
import { ApprovalCard } from '../../components/Chat/ApprovalCard';
import { WebVideo } from '../../components/Gallery/WebVideo';
import { plainReply, summarize } from '../../lib/plainReply';

type SpeechRec = { lang: string; interimResults: boolean; onresult: (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void; onend: () => void; start: () => void; stop: () => void };

function useDictation(onText: (t: string) => void) {
  const [listening, setListening] = useState(false);
  const rec = useRef<SpeechRec | null>(null);
  const W = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
  const Ctor = W.SpeechRecognition || W.webkitSpeechRecognition;
  const toggle = () => {
    if (!Ctor) {
      toast('Su navegador no dicta; use el micrófono del notch.');
      return;
    }
    if (listening) {
      rec.current?.stop();
      return;
    }
    const r = new Ctor();
    r.lang = navigator.language || 'es-ES';
    r.interimResults = false;
    r.onresult = (e) => onText(Array.from(e.results).map((x) => x[0].transcript).join(' '));
    r.onend = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };
  return { listening, toggle, available: !!Ctor };
}

export function ChatTab({ node, onChanged, onCancel }: { node: SergioNode; onChanged: () => void; onCancel: () => void }) {
  const [thread, setThread] = useState('main');
  const [messages, setMessages] = useState<NodeMessage[]>([]);
  const [text, setText] = useState('');
  const [aloud, setAloud] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const spoken = useRef<string | null>(null);
  const tts = useTtsStore();
  const dictation = useDictation((t) => setText((x) => (x ? `${x} ${t}` : t)));

  const load = useCallback(() => {
    nodesApi
      .messages(node.id, 0, thread)
      .then(setMessages)
      .catch(() => {});
  }, [node.id, thread]);

  useEffect(() => {
    load();
    const t = window.setInterval(load, 2000);
    return () => window.clearInterval(t);
  }, [load]);
  // Scroll only the Node's own pane (scrollIntoView would also move the shell).
  useEffect(() => {
    const pane = end.current?.closest('.node-body');
    if (pane) pane.scrollTop = pane.scrollHeight;
  }, [messages.length, node.status]);
  // Read new replies aloud (Sergio's voice), the face talks meanwhile.
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!aloud || !last || last.role !== 'node' || spoken.current === last.id) return;
    spoken.current = last.id;
    void tts.speak(`node-${last.id}`, last.text.replace(/[*_`#>|]/g, ''));
  }, [messages, aloud]); // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (preset?: string) => {
    const t = (preset ?? text).trim();
    if (!t) return;
    if (preset === undefined) setText('');
    try {
      await nodesApi.say(node.id, t, thread);
      load();
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No se envió.');
    }
  };

  const decide = async (aid: string, approve: boolean) => {
    try {
      await nodesApi.decide(node.id, aid, approve);
      onChanged();
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude.');
    }
  };

  const talking = tts.state === 'speaking' && !!tts.speakingId?.startsWith('node-');
  const work = latestWork(messages);
  const busy = node.status === 'working' || node.busy;
  return (
    <div className={work ? 'nchat has-work' : 'nchat'}>
      <div className="node-chat nchat-main">
        <div className="nchat-hero" aria-hidden="true">
          <NodeCritter look={look(node)} size={58} talking={talking} status={busy ? 'working' : undefined} />
          <span>{node.name}</span>
        </div>
      <div className="node-threads" role="tablist" aria-label="Hilos">
        {node.threads.map((t) => (
          <button key={t.id} type="button" role="tab" className="mac-chip" aria-pressed={thread === t.id} onClick={() => setThread(t.id)}>
            {t.title}
          </button>
        ))}
        <button
          type="button"
          className="mac-chip"
          onClick={async () => {
            const title = window.prompt('Nombre del hilo nuevo', '');
            if (title === null) return;
            const t = await nodesApi.newThread(node.id, title);
            onChanged();
            setThread(t.id);
          }}
        >
          <Plus size={13} /> Hilo
        </button>
        <span className="flex-1" />
        <button
          type="button"
          className="mac-icon-btn"
          aria-pressed={aloud}
          aria-label={aloud ? 'No leer en voz alta' : 'Leer sus respuestas en voz alta'}
          title={aloud ? 'No leer en voz alta' : 'Leer sus respuestas en voz alta'}
          onClick={() => (aloud && tts.stop(), setAloud(!aloud))}
        >
          {aloud ? <Volume2 size={16} /> : <VolumeX size={16} />}
        </button>
      </div>
      <div className="node-thread">
        {messages.map((m, i) => (
          <div key={m.id} className={m.role === 'user' ? 'nchat-row me' : 'nchat-row them'}>
            {m.source && m.source !== 'Encargo del usuario' && <span className="node-msg-source">{m.source}</span>}
            <div
              className={`${m.role === 'user' ? 'nchat-bubble me' : 'nchat-bubble them'}${
                // The tail on the last bubble of each run, as in WhatsApp and iMessage.
                i === messages.length - 1 || messages[i + 1].role !== m.role ? ' tail' : ''
              }`}
            >
              {m.role === 'user' ? (
                m.text
              ) : (
                <div className="prose prose-sm">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{plainReply(withoutWork(m.text, work)).text || ' '}</ReactMarkdown>
                </div>
              )}
              {m.role === 'node' && i === messages.length - 1 && (m.suggestions?.length ?? 0) > 0 && (
                <div className="node-next" aria-label="Siguientes pasos que propone">
                  {m.suggestions!.map((idea) => (
                    <button key={idea} type="button" className="node-next-chip" onClick={() => void send(idea)}>
                      {idea}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {node.approvals
          .filter((a) => (a.thread || 'main') === thread)
          .map((a) => (
            <div key={a.id} className="node-approval" role="group" aria-label="Aprobación pendiente">
              <ApprovalCard approval={{ category: a.category, ...summarize(a.what) }} />
              <div className="node-approval-actions">
                <button type="button" className="paper-button" data-variant="quiet" onClick={() => decide(a.id, false)}>
                  <X size={14} /> No
                </button>
                <button type="button" className="paper-button" onClick={() => decide(a.id, true)}>
                  <Check size={14} /> Aprobar
                </button>
              </div>
            </div>
          ))}
        {node.status === 'needs_you' && <TakeOver node={node} onChanged={onChanged} />}
        {busy && (
          <div className="nchat-row them nchat-working">
            <div className="nchat-bubble them tail node-working">{node.doing || 'Trabajando…'}</div>
            <button type="button" className="mac-chip node-cancel" onClick={onCancel}>
              <CircleSlash size={13} /> Cancelar acción
            </button>
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="node-composer nchat-composer">
        <textarea
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={`Encárguele algo a ${node.name}…`}
          aria-label={`Mensaje para ${node.name}`}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button
          type="button"
          className="mac-icon-btn"
          aria-pressed={dictation.listening}
          aria-label={dictation.listening ? 'Dejar de dictar' : 'Dictar'}
          onClick={dictation.toggle}
        >
          <Mic size={17} strokeWidth={1.6} />
        </button>
        <button type="button" className="nchat-send" onClick={() => void send()} disabled={!text.trim()} aria-label="Enviar">
          <ArrowUp size={17} strokeWidth={2.25} />
        </button>
      </div>
      </div>
      {work && <WorkPanel work={work} />}
    </div>
  );
}

/** Beside the chat: what the Node made last (as in the owner's reference). */
function WorkPanel({ work }: { work: Work }) {
  return (
    <aside className="nchat-work" aria-label="Lo que está haciendo">
      <header className="nchat-work-head">
        <span className="nchat-work-title">{work.title}</span>
        <a className="mac-icon-btn" href={work.url} target="_blank" rel="noreferrer" aria-label="Abrir aparte" title="Abrir aparte">
          <ExternalLink size={15} />
        </a>
      </header>
      <div className="nchat-work-body">
        {work.kind === 'video' && <WebVideo key={work.url} src={work.url} preload="metadata" />}
        {work.kind === 'image' && <img src={work.url} alt={work.title} />}
        {work.kind === 'page' && (
          <a className="nchat-work-page" href={work.url} target="_blank" rel="noreferrer">
            {work.title}
            <span>{work.url}</span>
          </a>
        )}
      </div>
    </aside>
  );
}

function TakeOver({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const url = node.waiting.match(/https?:\/\/\S+/)?.[0];
  return (
    <div className="node-approval node-takeover" role="group" aria-label="Tomar el control">
      <span className="paper-label">Le necesita a usted</span>
      <p>{node.waiting}</p>
      <div className="node-approval-actions">
        {url && (
          <a className="paper-button" data-variant="quiet" href={url} target="_blank" rel="noreferrer">
            <ExternalLink size={14} /> Tomar el control
          </a>
        )}
        <button
          type="button"
          className="paper-button"
          onClick={async () => {
            await nodesApi.handBack(node.id).catch(() => toast.error('No pude devolverle el control.'));
            onChanged();
          }}
        >
          <Play size={14} /> Listo, continúe
        </button>
      </div>
    </div>
  );
}
