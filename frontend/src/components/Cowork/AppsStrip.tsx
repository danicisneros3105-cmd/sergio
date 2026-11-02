// The apps Cowork can work in, as their own logos: one tap connects (the
// service's own sign-in opens), connected ones show a dot. Notion, Gmail,
// Shopify and the rest come from the connectors directory (mcp/directory.py).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { BrandMark } from '../Brand/BrandMark';
import { addConnector, connectConnector, fetchConnectors, fetchDirectory, type Connector } from '../../lib/mcp';
import './apps-strip.css';

const FIRST = ['gmail', 'notion', 'shopify', 'googlecalendar', 'googledrive', 'slack', 'github', 'figma', 'canva', 'stripe', 'linear', 'zapier'];

interface Entry {
  id: string;
  name: string;
  url?: string;
  description?: string;
}

export function AppsStrip({ limit = 12 }: { limit?: number }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [mine, setMine] = useState<Connector[]>([]);
  const [busy, setBusy] = useState('');

  const load = useCallback(() => {
    fetchConnectors()
      .then((d) => setMine(Array.isArray(d?.servers) ? d.servers : []))
      .catch(() => setMine([]));
  }, []);

  useEffect(() => {
    fetchDirectory()
      .then((d) => setEntries(((d?.connectors ?? []) as unknown as Entry[]).filter((e) => e && e.id)))
      .catch(() => setEntries([]));
    load();
  }, [load]);

  const shown = useMemo(() => {
    const byId = new Map(entries.map((e) => [e.id, e]));
    return FIRST.map((id) => byId.get(id)).filter(Boolean).slice(0, limit) as Entry[];
  }, [entries, limit]);

  const stateOf = (id: string) => mine.find((c) => c.directory_id === id || c.id === id);

  const connect = async (e: Entry) => {
    setBusy(e.id);
    try {
      let server = stateOf(e.id);
      if (!server) server = (await addConnector({ directory_id: e.id })).server;
      const res = await connectConnector(server.id);
      if (res.status === 'needs_auth' && res.auth_url) {
        window.open(res.auth_url, '_blank', 'noopener');
        toast(`Inicie sesión en ${e.name} en la pestaña que se abrió.`);
      } else {
        toast.success(`${e.name} conectado.`);
      }
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `No se pudo conectar ${e.name}.`);
    } finally {
      setBusy('');
    }
  };

  if (!shown.length) return null;
  return (
    <section className="apps-strip" aria-label="Conecte sus apps">
      <h2>Sus apps</h2>
      <ul>
        {shown.map((e) => {
          const s = stateOf(e.id);
          const on = s?.status === 'connected';
          return (
            <li key={e.id}>
              <button
                type="button"
                className="apps-tile"
                data-on={on || undefined}
                aria-busy={busy === e.id || undefined}
                title={on ? `${e.name}: conectado` : `Conectar ${e.name}`}
                onClick={() => (on ? toast(`${e.name} ya está conectado.`) : void connect(e))}
              >
                <BrandMark name={e.name} id={e.id} size={28} url={e.url} />
                <span>{e.name}</span>
                {on && <i aria-hidden="true" />}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default AppsStrip;
