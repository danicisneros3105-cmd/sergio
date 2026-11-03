// Something Sergio made to be seen or used (a page, a poster, a chart, a small
// tool), shown finished in the chat. The frame is a sandbox: it cannot reach
// Sergio's page, its storage or its session, and the file itself forbids every
// network request (tools/artefacto.py).
import { useState } from 'react';
import { Download, ExternalLink, Maximize2, Minimize2 } from 'lucide-react';
import type { Artifact } from '../../lib/plainReply';
import { getBase } from '../../lib/api';

export function artifactUrl(file: string, base = ''): string {
  return `${base}/v1/creator/artefacto/${encodeURIComponent(file)}`;
}

export function ArtifactCard({ artifact }: { artifact: Artifact }) {
  const [big, setBig] = useState(false);
  const url = artifactUrl(artifact.file, getBase?.() ?? '');
  return (
    <figure className="artifact" data-big={big || undefined}>
      <figcaption className="artifact-head">
        <b title={artifact.title}>{artifact.title}</b>
        <span>
          <button type="button" aria-label={big ? 'Achicar' : 'Agrandar'} title={big ? 'Achicar' : 'Agrandar'} onClick={() => setBig(!big)}>
            {big ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
          <a href={url} target="_blank" rel="noopener noreferrer" aria-label="Abrir en una pestaña" title="Abrir en una pestaña">
            <ExternalLink size={15} />
          </a>
          <a href={url} download={`${artifact.title.replace(/[^\w-]+/g, '-') || 'artefacto'}.html`} aria-label="Descargar" title="Descargar">
            <Download size={15} />
          </a>
        </span>
      </figcaption>
      <iframe
        className="artifact-frame"
        title={artifact.title}
        src={url}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        loading="lazy"
      />
    </figure>
  );
}

export default ArtifactCard;
