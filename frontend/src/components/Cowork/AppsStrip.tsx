// The apps Cowork can work in, as their own logos: one tap connects (the
// service's own sign-in opens), connected ones show a dot. Notion, Gmail,
// Shopify and the rest come from the connectors directory (mcp/directory.py).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { BrandMark } from '../Brand/BrandMark';
import { addConnector, connectConnector, fetchConnectors, fetchDirectory, type Connector } from '../../lib/mcp';
import './apps-strip.css';

const FIRST = ['gmail', 'notion', 'shopify', 'googlecalendar', 'googledrive', 'slack', 'github', 'figma', 'canva', 'stripe', 'linear', 'zapier'];

// What each connected app is good for: one tap fills the task box (owner,
// 3 Nov 2026: «hacer más grandes los logos en Cowork y darle una función útil»).
// Nothing is sent, published or bought by itself: each ends in a draft or a review.
export const APP_TASKS: Record<string, string[]> = {
  gmail: ['Resume mi correo sin leer de hoy y prepara borradores para lo urgente', 'Busca las facturas de este mes y hazme una tabla con montos y fechas'],
  notion: ['Ordena mi Notion: agrupa las páginas sueltas por proyecto', 'Convierte mis notas de esta semana en un plan con fechas'],
  shopify: ['Dime qué productos vendieron más esta semana y cuáles no se mueven', 'Prepara descripciones nuevas para los 5 productos con menos ventas (para revisar)'],
  googlecalendar: ['Mira mi semana y dime dónde tengo huecos de 2 horas para trabajar', 'Prepara la agenda de mañana con lo que tengo que llevar a cada reunión'],
  googledrive: ['Busca en mi Drive los documentos del proyecto y hazme un resumen de cada uno', 'Ordena mi carpeta de descargas de Drive por tipo y año (propuesta primero)'],
  slack: ['Resume lo que pasó hoy en mis canales y lo que me pidieron', 'Prepara respuestas para los mensajes que me mencionan (borradores)'],
  github: ['Revisa los issues abiertos y ordénalos por urgencia', 'Resume los cambios de esta semana en mi repositorio'],
  figma: ['Revisa este diseño y dame una lista de mejoras de jerarquía y espacio', 'Saca los colores y tipografías de mi archivo y arma una guía de estilo'],
  canva: ['Prepara 3 versiones de portada para mi próximo video', 'Adapta mi diseño a historias de Instagram y a un post cuadrado'],
  stripe: ['Dime cuánto cobré este mes y qué pagos fallaron', 'Hazme una tabla de clientes con lo que pagan cada mes'],
  linear: ['Ordena mi backlog por impacto y esfuerzo', 'Escribe el resumen de lo que mi equipo cerró esta semana'],
  zapier: ['Propón 3 automatizaciones que me ahorren tiempo con las apps que tengo', 'Revisa mis zaps y dime cuáles fallan'],
};

interface Entry {
  id: string;
  name: string;
  url?: string;
  description?: string;
}

export function AppsStrip({ limit = 12, onPick }: { limit?: number; onPick?: (task: string) => void }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [mine, setMine] = useState<Connector[]>([]);
  const [busy, setBusy] = useState('');
  const [open, setOpen] = useState('');

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
                aria-expanded={on ? open === e.id : undefined}
                onClick={() => (on ? setOpen(open === e.id ? '' : e.id) : void connect(e))}
              >
                <BrandMark name={e.name} id={e.id} size={44} url={e.url} />
                <span>{e.name}</span>
                {on && <i aria-hidden="true" />}
              </button>
              {on && open === e.id && (
                <div className="apps-tasks" role="menu" aria-label={`Tareas con ${e.name}`}>
                  {(APP_TASKS[e.id] ?? [`Usa ${e.name} para…`]).map((t) => (
                    <button key={t} type="button" role="menuitem" onClick={() => (setOpen(''), onPick ? onPick(t) : toast(t))}>
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default AppsStrip;
