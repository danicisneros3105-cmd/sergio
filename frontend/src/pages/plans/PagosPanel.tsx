// The owner's ledger of Sergio Pagos: what came in this month, the processors'
// fees, what his customers' AI may cost, his margin and whether his OpenRouter
// balance covers it. Only the owner sees it (/v1/pagos/resumen answers 403
// to anyone else, and then nothing is shown).

import { useEffect, useState } from 'react';
import { apiFetch } from '../../lib/api';

type Totals = { ingreso: number; comision: number; proveedor: number; margen: number };
type Summary = {
  metodos: Array<{ id: string; nombre: string }>;
  mes: Totals;
  total: Totals;
  clientes_activos: number;
  ia_comprometida_usd: number;
  saldo_openrouter_usd: number | null;
  falta_saldo: boolean;
  claves_ia: boolean;
};

const money = (usd: number) => `$${usd.toFixed(2)}`;

export function PagosPanel() {
  const [s, setS] = useState<Summary | null>(null);
  useEffect(() => {
    let live = true;
    apiFetch('/v1/pagos/resumen')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => live && setS(d))
      .catch(() => live && setS(null));
    return () => {
      live = false;
    };
  }, []);
  if (!s) return null;
  return (
    <section className="pagos-panel" aria-label="Cobros">
      <h2 className="paper-label">Cobros de Sergio (últimos 30 días)</h2>
      <div className="plans-rows">
        <div>
          <span>Formas de pago</span>
          <span>{s.metodos.length ? s.metodos.map((m) => m.nombre).join(', ') : 'Ninguna activada'}</span>
        </div>
        <div>
          <span>Cobrado</span>
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
      {s.falta_saldo && (
        <p className="pay-problem" role="alert">
          El saldo de OpenRouter no cubre lo que sus clientes pueden gastar este mes. Active la recarga automática en
          OpenRouter.
        </p>
      )}
    </section>
  );
}
