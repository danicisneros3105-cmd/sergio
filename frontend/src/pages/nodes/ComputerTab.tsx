import { useEffect, useState } from 'react';
import { Download, HardDrive } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { nodesApi, STATUS_ES, type SergioNode } from '../../lib/nodes';

async function download(nodeId: string, path: string) {
  const res = await apiFetch(nodesApi.fileUrl(nodeId, path));
  if (!res.ok) {
    toast.error('No pude bajar ese archivo.');
    return;
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = path.split('/').pop() || 'archivo';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function ComputerTab({ node }: { node: SergioNode }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof nodesApi.computer>> | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      nodesApi
        .computer(node.id)
        .then((d) => alive && setData(d))
        .catch(() => {});
    load();
    const t = window.setInterval(load, 3000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [node.id]);
  return (
    <div className="node-computer">
      <div className="node-screen" aria-label="Su computadora ahora">
        <div className="node-screen-bar">
          <span />
          <span />
          <span />
          <em>{node.name} · computadora</em>
        </div>
        <div className="node-screen-body">
          {(data?.recent || []).slice(-14).map((r) => (
            <p key={r.id}>
              <span>{new Date(r.at * 1000).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span> {r.text}
            </p>
          ))}
          <p className="node-screen-now">
            {node.status === 'working' ? `▸ ${node.doing || 'trabajando…'}` : `${STATUS_ES[node.status]}.`}
            <i className="node-caret" />
          </p>
        </div>
      </div>
      <div className="node-files">
        <h3 className="paper-label">
          <HardDrive size={13} /> Archivos
        </h3>
        {data?.files.length ? (
          <ul>
            {data.files.map((f) => (
              <li key={f.path}>
                <span className="truncate">{f.path}</span>
                <span className="node-hint">{(f.size / 1024).toFixed(f.size < 10240 ? 1 : 0)} KB</span>
                <button type="button" className="mac-icon-btn" aria-label={`Bajar ${f.path}`} onClick={() => download(node.id, f.path)}>
                  <Download size={14} />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="node-hint">Lo que produzca (informes, tablas, notas) aparecerá aquí.</p>
        )}
        <p className="node-hint node-path">{data?.path}</p>
      </div>
    </div>
  );
}
