// The owner's side of Sergio Pagos: what is ready to charge and what is
// missing, the sealed ledger (is it intact?), the last 30 days in money, a real
// $1 test with his own card (typed on the processor's page, never here) and
// the last orders, with «Devolver» to record a refund made in the processor's
// dashboard. Only the owner sees it (/v1/pagos/* answers 403 to anyone else).

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';

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

  const load = useCallback((online = false) => {
    apiFetch('/v1/pagos/resumen')
      .then((r) => (r.ok ? r.json() : null))
      .then(setS)
      .catch(() => setS(null));
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
