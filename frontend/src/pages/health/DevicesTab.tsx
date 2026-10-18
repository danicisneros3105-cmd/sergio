import { useEffect, useRef, useState } from 'react';
import { Copy, RefreshCw, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { salud, type Catalog, type Summary, type SyncInfo } from '../../lib/salud';

const WAYS: Record<string, string> = { api: 'Directo', push: 'Automático por el teléfono', file: 'Archivo' };

function copy(text: string) {
  void navigator.clipboard?.writeText(text).then(
    () => toast.success('Copiado.'),
    () => toast.error('No pude copiar; selecciónelo a mano.'),
  );
}

function SyncLink() {
  const [info, setInfo] = useState<SyncInfo | null>(null);
  const [show, setShow] = useState(false);
  useEffect(() => {
    salud.sync().then(setInfo).catch(() => setInfo(null));
  }, []);
  if (!info) return null;
  const url = `${window.location.origin}${info.path}`;
  return (
    <section className="salud-block">
      <h2 className="paper-label">Sincronización automática</h2>
      <p>
        Una app de automatización del teléfono (iPhone o Android) envía cada hora sus datos de salud, los del reloj incluidos, a esta
        dirección. El teléfono tiene que poder llegar a este PC: en la misma red Wi-Fi o con el acceso remoto de Sergio.
      </p>
      <div className="salud-sync">
        <label>
          <span className="paper-label">Dirección</span>
          <code>{url}</code>
          <button type="button" className="mac-icon-btn" aria-label="Copiar dirección" onClick={() => copy(url)}>
            <Copy size={14} />
          </button>
        </label>
        <label>
          <span className="paper-label">Cabecera</span>
          <code>{show ? info.header : 'Authorization: Bearer ••••••••••••'}</code>
          <button type="button" className="mac-icon-btn" aria-label="Copiar cabecera" onClick={() => copy(info.header)}>
            <Copy size={14} />
          </button>
        </label>
        <div className="salud-sync-actions">
          <button type="button" className="paper-button" data-variant="quiet" onClick={() => setShow((v) => !v)}>
            {show ? 'Ocultar clave' : 'Ver clave'}
          </button>
          <button
            type="button"
            className="paper-button"
            data-variant="quiet"
            onClick={async () => {
              if (!window.confirm('Los teléfonos con la clave anterior dejarán de sincronizar. ¿Cambiarla?')) return;
              await salud.rotate();
              setInfo(await salud.sync());
              toast.success('Clave nueva.');
            }}
          >
            <RefreshCw size={14} /> Cambiar clave
          </button>
        </div>
        <p className="paper-meta">
          Formato: el JSON de las apps de exportación de salud (métricas con «name», «units» y «data») o el de Sergio:{' '}
          <code>{JSON.stringify(info.example)}</code>
          {info.last_push && ` · Último envío: ${new Date(info.last_push.at * 1000).toLocaleString('es')} (${info.last_push.added} datos nuevos).`}
        </p>
      </div>
    </section>
  );
}

function ImportFile({ onDone }: { onDone: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [source, setSource] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <section className="salud-block">
      <h2 className="paper-label">Importar un archivo</h2>
      <p>La exportación completa del teléfono (export.zip), o el CSV/JSON de su reloj, anillo, báscula o tensiómetro. Importar dos veces no duplica nada.</p>
      <div className="salud-add">
        <input className="paper-input" value={source} onChange={(e) => setSource(e.target.value)} placeholder="De dónde viene (opcional, p. ej. báscula)" aria-label="Origen" />
        <button type="button" className="paper-button" disabled={busy} onClick={() => input.current?.click()}>
          <Upload size={14} /> {busy ? 'Leyendo…' : 'Elegir archivo'}
        </button>
        <input
          ref={input}
          type="file"
          hidden
          accept=".zip,.xml,.csv,.json,.txt"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (!file) return;
            setBusy(true);
            try {
              const out = await salud.importFile(file, source);
              toast.success(`Leídos ${out.read.toLocaleString('es')} datos; ${out.added.toLocaleString('es')} nuevos.`);
              onDone();
            } catch (err) {
              toast.error(err instanceof Error ? err.message : 'No pude leer el archivo.');
            } finally {
              setBusy(false);
            }
          }}
        />
      </div>
    </section>
  );
}

function DirectDevice({ id, connected, onDone }: { id: string; connected: boolean; onDone: () => void }) {
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<{ read: number; added: number }>) => {
    setBusy(true);
    try {
      const out = await fn();
      toast.success(`${out.added} datos nuevos.`);
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No respondió.');
    } finally {
      setBusy(false);
    }
  };
  if (connected) {
    return (
      <div className="salud-device-actions">
        <button type="button" className="paper-button" disabled={busy} onClick={() => void run(() => salud.deviceSync(id))}>
          <RefreshCw size={14} /> Sincronizar ahora
        </button>
        <button
          type="button"
          className="paper-button"
          data-variant="quiet"
          onClick={async () => {
            await salud.deviceForget(id);
            onDone();
          }}
        >
          Desconectar
        </button>
      </div>
    );
  }
  return (
    <div className="salud-device-actions">
      <input className="paper-input" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Token personal" aria-label="Token personal" />
      <button type="button" className="paper-button" disabled={busy || token.trim().length < 8} onClick={() => void run(() => salud.deviceKey(id, token.trim()))}>
        Conectar
      </button>
    </div>
  );
}

export function DevicesTab({ catalog, summary, onChanged }: { catalog: Catalog; summary: Summary; onChanged: () => void }) {
  const sources = Object.entries(summary.sources);
  return (
    <div className="salud-devices">
      {sources.length > 0 && (
        <section className="salud-block">
          <h2 className="paper-label">De dónde vienen sus datos</h2>
          <ul className="salud-sources">
            {sources.map(([name, s]) => (
              <li key={name}>
                <b>{name}</b>
                <span>{s.count.toLocaleString('es')} datos · último {new Date(s.last * 1000).toLocaleDateString('es')}</span>
                <button
                  type="button"
                  className="paper-button"
                  data-variant="quiet"
                  onClick={async () => {
                    if (!window.confirm(`¿Borrar los ${s.count} datos que trajo «${name}»?`)) return;
                    await salud.dropSource(name);
                    onChanged();
                  }}
                >
                  Borrar sus datos
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <SyncLink />
      <ImportFile onDone={onChanged} />
      <section className="salud-block">
        <h2 className="paper-label">Relojes, anillos y medidores</h2>
        <div className="salud-device-list">
          {catalog.devices.map((d) => (
            <article key={d.id} className="salud-device">
              <header>
                <b>{d.name}</b>
                <span>{d.ways.map((w) => WAYS[w]).join(' · ')}</span>
              </header>
              <p>{d.how}</p>
              {d.ways.includes('api') && <DirectDevice id={d.id} connected={summary.connected.includes(d.id)} onDone={onChanged} />}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
