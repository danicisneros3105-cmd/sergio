import { ApprovalCard } from './ApprovalCard';
import { plainReply } from '../../lib/plainReply';
import { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import 'katex/dist/katex.min.css';
import { Copy, Check } from 'lucide-react';
import { AudioPlayer } from './AudioPlayer';
import { ToolCallCard } from './ToolCallCard';
import { ResearchTimeline } from './ResearchTimeline';
import { rehypeCitations } from '../../lib/rehype-citations';
import { XRayFooter } from './XRayFooter';
import { SpeakMessageButton } from './SpeakMessageButton';
import type { ChatMessage } from '../../types';
import { stripThinkTags } from '../../lib/message-text';
import { anatomyNames, withoutAnatomyLinks } from '../../lib/anatomy';
import { AnatomyEmbed } from './AnatomyEmbed';
import { isVideo, mediaOf } from '../../lib/imessage';

interface Props {
  message: ChatMessage;
  isLive?: boolean;
  /** Last bubble of a group (iMessage): it gets the tail. */
  tail?: boolean;
  /** «Entregado» / «Leído» under the owner's last message. */
  receipt?: '' | 'Entregado' | 'Leído';
}

function getTextContent(node: any): string {
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(getTextContent).join('');
  }
  if (node?.props?.children) {
    return getTextContent(node.props.children);
  }
  return '';
}

function CodeBlockPre({ children, ...props }: any) {
  const [copied, setCopied] = useState(false);
  const codeElement = Array.isArray(children) ? children[0] : children;
  const className = codeElement?.props?.className || '';
  const match = /language-([\w-]+)/.exec(className);
  const lang = match ? match[1] : '';
  const code = getTextContent(codeElement?.props?.children).replace(/\n$/, '');

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className="code-block-wrapper relative my-3"
      style={{ borderRadius: 'var(--radius-md)', overflow: 'hidden' }}
    >
      <div
        className="flex items-center justify-between px-4 py-1.5 text-xs"
        style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-tertiary)' }}
      >
        <span className="font-mono">{lang || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-0.5 rounded transition-colors cursor-pointer"
          style={{ color: 'var(--color-text-tertiary)' }}
          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--color-text-secondary)')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--color-text-tertiary)')}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copiado' : 'Copiar'}
        </button>
      </div>
      <pre {...props} style={{ margin: 0, borderRadius: 0 }}>
        {children}
      </pre>
    </div>
  );
}

function CopyMessageButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="msg-action p-1 rounded transition-opacity cursor-pointer"
      style={{ color: 'var(--color-text-tertiary)' }}
      title="Copiar mensaje"
      aria-label="Copiar mensaje"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

// What the tools are called for a person, not a programmer.
const TOOL_NAMES: Record<string, string> = {
  image_generate: 'Imagen',
  video_create: 'Video',
  video_essay: 'Video ensayo',
  video_pro: 'Video',
  video_edit: 'Video',
  web_search: 'Internet',
  screen_read: 'Pantalla',
  desktop_action: 'Su PC',
  camera_look: 'Cámara',
  files_organize: 'Archivos',
  photos_duplicates: 'Fotos',
  pc_checkup: 'Su PC',
  get_weather: 'Clima',
  calculator: 'Calculadora',
};

function toolSummary(calls: NonNullable<ChatMessage['toolCalls']>): string {
  const names = [...new Set(calls.map((c) => TOOL_NAMES[c.tool] || 'Herramienta'))];
  const running = calls.some((c) => c.status === 'running');
  const failed = calls.some((c) => c.status === 'error');
  return `${running ? 'Usando' : failed ? 'No funcionó' : 'Usó'}: ${names.join(', ')}`;
}

function Media({ src, alt }: { src: string; alt?: string }) {
  if (isVideo(src)) {
    return <video className="imsg-media" src={src} controls playsInline preload="metadata" />;
  }
  return <img className="imsg-media" src={src} alt={alt || 'Imagen'} loading="lazy" />;
}

const markdownComponents = {
  pre: CodeBlockPre,
  // Pictures and videos as in iMessage: rounded, the width of the bubble.
  img: ({ src, alt }: { src?: string; alt?: string }) => (src ? <Media src={src} alt={alt} /> : null),
};

export function MessageBubble({ message, isLive = false, tail = true, receipt = '' }: Props) {
  const isUser = message.role === 'user';

  const rawContent = useMemo(() => stripThinkTags(message.content), [message.content]);
  // Internal tags never reach the screen; a permission request becomes a card.
  const plain = useMemo(() => plainReply(rawContent), [rawContent]);
  // Figure links become the figures themselves (drawn below), never raw text.
  const cleanContent = useMemo(() => withoutAnatomyLinks(plain.text), [plain.text]);
  const extraMedia = useMemo(() => mediaOf(message), [message]);

  // Build a ref→source lookup once per render. Memoized so the rehype plugin
  // identity stays stable until the source list actually changes.
  const sourcesMap = useMemo(() => {
    const m = new Map<number, NonNullable<ChatMessage['researchSources']>[number]>();
    for (const s of message.researchSources ?? []) {
      if (typeof s.ref === 'number') m.set(s.ref, s);
    }
    return m;
  }, [message.researchSources]);

  const rehypePlugins = useMemo(() => {
    const base: any[] = [[rehypeHighlight, { detect: true }], rehypeKatex];
    if (sourcesMap.size > 0) base.push([rehypeCitations, { sources: sourcesMap }]);
    return base;
  }, [sourcesMap]);

  if (isUser) {
    return (
      <div className={`imsg-row me${tail ? ' end' : ''}`}>
        <div className={`imsg-bubble me${tail ? ' tail' : ''}`}>{message.content}</div>
        {receipt && <div className="imsg-receipt">{receipt}</div>}
      </div>
    );
  }

  return (
    <div className={`group imsg-row them${tail ? ' end' : ''}`}>
      {/* Deep Research timeline (steps + status) */}
      {(message.isResearch || (message.researchTraces && message.researchTraces.length > 0)) && (
        <ResearchTimeline
          traces={message.researchTraces ?? []}
          isLive={isLive}
          hasContent={cleanContent.length > 0}
        />
      )}

      {/* What Sergio used, in one small line; the details open on a click. */}
      {message.toolCalls && message.toolCalls.length > 0 && (
        <details className="imsg-tools">
          <summary>{toolSummary(message.toolCalls)}</summary>
          <div className="mt-2 flex flex-col gap-2">
            {message.toolCalls.map((tc) => (
              <ToolCallCard key={tc.id} toolCall={tc} />
            ))}
          </div>
        </details>
      )}

      {/* Audio player (e.g. morning digest) */}
      {message.audio?.url && <AudioPlayer src={message.audio.url} />}

      {cleanContent && (
        <div className={`imsg-bubble them prose${tail && !extraMedia.length ? ' tail' : ''}`}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={rehypePlugins}
            components={markdownComponents as any}
          >
            {cleanContent}
          </ReactMarkdown>
        </div>
      )}

      {plain.approvals.map((a, i) => (
        <ApprovalCard
          key={i}
          approval={a}
          onAnswer={
            isLive
              ? undefined
              : (yes) => window.dispatchEvent(new CustomEvent('sergio:send', { detail: yes ? 'Sí, hazlo.' : 'No, no lo hagas.' }))
          }
        />
      ))}

      {extraMedia.map((src) => (
        <div key={src} className="imsg-media-row">
          <Media src={src} />
        </div>
      ))}

      {/* Anatomy figures Sergio drew for this answer (the hidden skill) */}
      {!isLive &&
        anatomyNames(rawContent, ...(message.toolCalls ?? []).map((tc) => tc.result)).map((name) => (
          <AnatomyEmbed key={name} name={name} />
        ))}

      {/* Copy and read aloud, quietly under the bubble */}
      {!isLive && cleanContent && (
        <div className="imsg-actions">
          <CopyMessageButton content={cleanContent} />
          <SpeakMessageButton messageId={message.id} content={cleanContent} />
        </div>
      )}
      <XRayFooter
        usage={message.usage}
        telemetry={message.telemetry}
        isResearch={message.isResearch}
      />
    </div>
  );
}
