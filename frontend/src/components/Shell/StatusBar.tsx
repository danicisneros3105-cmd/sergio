import { useEffect, useState } from 'react';
import { Cloud, CloudOff, Wifi, WifiOff } from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { useOnline } from '../../hooks/useOnline';

function clock(now: Date): string {
  return now.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
}

// The device's status bar: Sergio and the brain on the left; the server,
// the network and the time on the right. Small, quiet, always there.
export function StatusBar({ apiReachable }: { apiReachable: boolean | null }) {
  const online = useOnline();
  const selectedModel = useAppStore((s) => s.selectedModel);
  const serverInfo = useAppStore((s) => s.serverInfo);
  const modelLoading = useAppStore((s) => s.modelLoading);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    // Wake exactly on the next minute, then every minute.
    const first = 60_000 - (Date.now() % 60_000);
    let timer = window.setTimeout(function tick() {
      setNow(new Date());
      timer = window.setTimeout(tick, 60_000);
    }, first);
    return () => window.clearTimeout(timer);
  }, []);

  const model = modelLoading ? 'Cargando modelo…' : selectedModel || serverInfo?.model || '';
  const server = apiReachable === false ? 'Sergio no responde' : apiReachable ? 'Sergio' : 'Conectando…';

  return (
    <div className="paper-status" role="status" aria-label="Estado">
      <span className="flex items-center gap-2 min-w-0">
        <span
          aria-hidden="true"
          className="inline-block rounded-full shrink-0"
          style={{
            width: 6,
            height: 6,
            background: apiReachable === false ? 'var(--color-error)' : apiReachable ? 'var(--color-ink)' : 'var(--color-text-tertiary)',
          }}
        />
        <span className="truncate">
          {server}
          {model && apiReachable ? ` · ${model}` : ''}
        </span>
      </span>
      <span className="flex items-center gap-3 shrink-0">
        <span title={apiReachable ? 'Guardado en este equipo y en su servidor' : 'Guardado en este equipo'}>
          {apiReachable ? <Cloud aria-label="Sincronizado" /> : <CloudOff aria-label="Sin sincronizar" />}
        </span>
        <span title={online ? 'Con conexión' : 'Sin conexión'}>
          {online ? <Wifi aria-label="Con conexión" /> : <WifiOff aria-label="Sin conexión" />}
        </span>
        <time dateTime={now.toISOString()}>{clock(now)}</time>
      </span>
    </div>
  );
}
