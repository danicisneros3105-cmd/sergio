// The owner's side of Sergio Pagos: what is ready to charge and what is
// missing, the sealed ledger (is it intact?), the last 30 days in money, a real
// $1 test with his own card (typed on the processor's page, never here) and
// the last orders, with «Devolver» to record a refund made in the processor's
// dashboard. Only the owner sees it (/v1/pagos/* answers 403 to anyone else).

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { ManagementKeyForm } from '../../components/Chat/IaSetupCard';

type Totals = { ingreso: number; comision: number; proveedor: number; margen: number };
type Order = { id: string; plan: string; usd: number; method: string; status: string; created: number; recibo: string };
type Summary = {
  metodos: Array<{ id: string; nombre: string; real: boolean }>;
  mes: Totals;
  clientes_activos: number;
  ia_comprometida_usd: number;
  saldo_openrouter_usd: number | null;
  falta_saldo: boolean;
  claves_ia: boolean;
  libro: { integro: boolean; lineas: number; rota_en: number | null };
  ultimos: Order[];
};
type Customer = {
  cliente: string;
  plan: string;
  paga: number;
  comision: number;
  tope_ia: number;
  gasto_ia: number | null;
  ganancia: number | null;
  uso: number | null;
  modelos: string;
};
type Customers = {
  clientes: Customer[];
  totales: { paga: number; comision: number; gasto_ia: number; ganancia: number; sin_dato: number };
  acceso: Record<string, string>;
  claves_ia: boolean;
};
const PLAN_NAME: Record<string, string> = { free: 'Free', go: 'Go', work: 'Work', dev: 'Dev', founders: 'Founders' };
type Ready = { listo: boolean; pasos: Array<{ paso: string; ok: boolean; detalle: string }>; avisos: Record<string, string> };

const money = (usd: number) => `${usd < 0 ? '-' : ''}$${Math.abs(usd).toFixed(2)}`;
const STATUS: Record<string, string> = {
  abierto: 'Esperando pago',
  pagado: 'Pagado',
  reembolsado: 'Devuelto',
  vencido: 'Terminado',
  fallido: 'No se abrió',
  importe_incorrecto: 'Importe incorrecto',
  moneda_incorrecta: 'Moneda incorrecta',
};

export function PagosPanel() {
  const navigate = useNavigate();
  const [s, setS] = useState<Summary | null>(null);
  const [ready, setReady] = useState<Ready | null>(null);
  const [checking, setChecking] = useState(false);
  const [people, setPeople] = useState<Customers | null>(null);

  const load = useCallback((online = false) => {
    apiFetch('/v1/pagos/resumen')
      .then((r) => (r.ok ? r.json() : null))
      .then(setS)
      .catch(() => setS(null));
    apiFetch('/v1/pagos/clientes')
      .then((r) => (r.ok ? r.json() : null))
      .then(setPeople)
      .catch(() => setPeople(null));
    setChecking(online);
    apiFetch(`/v1/pagos/estado${online ? '?revisar=true' : ''}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setReady)
      .catch(() => setReady(null))
      .finally(() => setChecking(false));
  }, []);
  useEffect(() => load(), [load]);

  const giveBack = async (o: Order) => {
    if (!window.confirm(`¿Ya devolvió ${money(o.usd)} en el panel del procesador? Sergio lo anotará y quitará el plan.`)) return;
    const r = await apiFetch(`/v1/pagos/pedido/${o.id}/devolver`, { method: 'POST' });
    if (r.ok) {
      toast.success('Devolución anotada.');
      load();
    } else {
      toast.error('No pude anotar la devolución.');
    }
  };

  if (!s) return null;
  return (
    <section className="pagos-panel" aria-label="Cobros">
      <h2 className="paper-label">Cobros de Sergio</h2>

      {ready && (
        <div className="pagos-steps">
          {ready.pasos.map((p) => (
            <div key={p.paso} className="pagos-step" data-ok={p.ok}>
              <span aria-hidden="true">{p.ok ? '✓' : '!'}</span>
              <div>
                <strong>{p.paso}</strong>
                <small>{p.detalle}</small>
              </div>
            </div>
          ))}
          {Object.entries(ready.avisos).map(([k, url]) => (
            <div key={k} className="pagos-step" data-ok="true">
              <span aria-hidden="true">→</span>
              <div>
                <strong>Dirección de avisos para {k}</strong>
                <small>
                  <code>{url}</code>
                </small>
              </div>
            </div>
          ))}
          <div className="pagos-actions">
            <button type="button" className="paper-button" data-variant="quiet" disabled={checking} onClick={() => load(true)}>
              {checking ? 'Revisando…' : 'Revisar claves con los procesadores'}
            </button>
            {s.metodos.length > 0 && (
              <button type="button" className="paper-button" onClick={() => navigate('/pagar?plan=prueba')}>
                Probar con mi tarjeta ($1)
              </button>
            )}
          </div>
        </div>
      )}

      <div className="plans-rows">
        <div>
          <span>Libro de cuentas</span>
          <span>
            {s.libro.integro
              ? `Sellado e intacto (${s.libro.lineas} líneas)`
              : `Alterado en la línea ${s.libro.rota_en}`}
          </span>
        </div>
        <div>
          <span>Cobrado (30 días)</span>
          <span>{money(s.mes.ingreso)}</span>
        </div>
        <div>
          <span>Comisión del procesador (estimada)</span>
          <span>{money(s.mes.comision)}</span>
        </div>
        <div>
          <span>Tope de IA de los clientes</span>
          <span>{money(s.mes.proveedor)}</span>
        </div>
        <div>
          <span>Su ganancia</span>
          <span>{money(s.mes.margen)}</span>
        </div>
        <div>
          <span>Clientes activos</span>
          <span>{s.clientes_activos}</span>
        </div>
        <div>
          <span>Saldo en OpenRouter</span>
          <span>
            {s.saldo_openrouter_usd == null
              ? s.claves_ia
                ? 'No se pudo leer'
                : 'Falta la clave de gestión'
              : `${money(s.saldo_openrouter_usd)} de ${money(s.ia_comprometida_usd)} comprometidos`}
          </span>
        </div>
      </div>
      {!s.libro.integro && (
        <p className="pay-problem" role="alert">
          Alguien cambió el libro de cuentas fuera de Sergio. Compare con el panel del procesador antes de seguir.
        </p>
      )}
      {s.falta_saldo && (
        <p className="pay-problem" role="alert">
          El saldo de OpenRouter no cubre lo que sus clientes pueden gastar este mes. Active la recarga automática en
          OpenRouter.
        </p>
      )}

      {!s.claves_ia && (
        <div className="pagos-gestion">
          <strong>Clave de gestión de OpenRouter</strong>
          <small>
            Con ella Sergio crea la clave de cada cliente con el tope de su plan y lee lo que gasta de verdad. Créela en
            openrouter.ai → Settings → Provisioning API keys.
          </small>
          <ManagementKeyForm onSaved={() => load()} />
        </div>
      )}

      {people && (
        <>
          <h2 className="paper-label">Ganancia por cliente (este mes)</h2>
          {people.clientes.length === 0 ? (
            <p className="pagos-empty">Aún no hay clientes con un plan pagado.</p>
          ) : (
            <div className="pagos-table" role="table" aria-label="Ganancia por cliente">
              <div role="row" className="pagos-th">
                <span>Cliente</span>
                <span>Paga</span>
                <span>IA usada</span>
                <span>Ganancia</span>
              </div>
              {people.clientes.map((c, i) => (
                <div role="row" key={i} data-loss={c.ganancia != null && c.ganancia < 0}>
                  <span>
                    {c.cliente}
                    <small>{PLAN_NAME[c.plan] || c.plan}</small>
                  </span>
                  <span>{money(c.paga)}</span>
                  <span>
                    {c.gasto_ia == null ? 'No se pudo leer' : money(c.gasto_ia)}
                    {c.uso != null && (
                      <i className="pagos-use" aria-label={`${Math.round(c.uso * 100)} % del tope`}>
                        <b style={{ width: `${Math.round(c.uso * 100)}%` }} />
                      </i>
                    )}
                  </span>
                  <span>{c.ganancia == null ? '—' : money(c.ganancia)}</span>
                </div>
              ))}
              <div role="row" className="pagos-tf">
                <span>Total</span>
                <span>{money(people.totales.paga)}</span>
                <span>{money(people.totales.gasto_ia)}</span>
                <span>{money(people.totales.ganancia)}</span>
              </div>
            </div>
          )}
          {people.totales.sin_dato > 0 && (
            <p className="pagos-empty">
              {people.totales.sin_dato} cliente(s) sin dato de gasto: OpenRouter no respondió. No se suma nada inventado.
            </p>
          )}
          <h2 className="paper-label">Modelos por plan</h2>
          <div className="plans-rows">
            {Object.entries(people.acceso).map(([plan, words]) => (
              <div key={plan}>
                <span>{PLAN_NAME[plan] || plan}</span>
                <span>{words}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {s.ultimos.length > 0 && (
        <>
          <h2 className="paper-label">Últimos pedidos</h2>
          <div className="plans-rows">
            {s.ultimos.map((o) => (
              <div key={o.id}>
                <span>
                  {o.recibo || new Date(o.created * 1000).toLocaleDateString()} · {o.plan === 'prueba' ? 'Prueba' : o.plan} ·{' '}
                  {money(o.usd)}
                </span>
                <span>
                  {STATUS[o.status] || o.status}
                  {o.status === 'pagado' && (
                    <button type="button" className="pagos-link" onClick={() => void giveBack(o)}>
                      Devolver
                    </button>
                  )}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
