// Something Sergio made to be seen or used (a page, a poster, a chart, a small
// tool), shown finished in the chat. The frame is a sandbox: it cannot reach
// Sergio's page, its storage or its session, and the file itself forbids every
// network request (tools/artefacto.py).
import { useId, useState } from 'react';
import { Download, Eye, EyeOff, Maximize2, Minimize2 } from 'lucide-react';
import type { Artifact } from '../../lib/plainReply';
import { getBase } from '../../lib/api';

export function artifactUrl(file: string, base = ''): string {
  return `${base}/v1/creator/artefacto/${encodeURIComponent(file)}`;
}

export function ArtifactCard({ artifact }: { artifact: Artifact }) {
  const [big, setBig] = useState(false);
  const [visible, setVisible] = useState(true);
  const frameId = useId();
  const url = artifactUrl(artifact.file, getBase?.() ?? '');
  return (
    <figure className="artifact" data-big={visible && big || undefined}>
      <figcaption className="artifact-head">
        <b title={artifact.title}>{artifact.title}</b>
        <span>
          <button type="button" aria-controls={frameId} aria-expanded={visible} aria-label={visible ? 'Ocultar vista previa' : 'Mostrar vista previa'} title={visible ? 'Ocultar vista previa' : 'Mostrar vista previa'} onClick={() => setVisible(!visible)}>
            {visible ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
          {visible && <button type="button" aria-controls={frameId} aria-pressed={big} aria-label={big ? 'Achicar' : 'Agrandar'} title={big ? 'Achicar' : 'Agrandar'} onClick={() => setBig(!big)}>
            {big ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>}
          <a href={url} download={`${artifact.title.replace(/[^\w-]+/g, '-') || 'artefacto'}.html`} aria-label="Descargar" title="Descargar">
            <Download size={15} />
          </a>
        </span>
      </figcaption>
      <iframe
        id={frameId}
        style={visible ? undefined : { display: 'none' }}
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
