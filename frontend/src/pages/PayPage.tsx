// Sergio Pagos: Sergio's own checkout. The plan, the price and the ways to pay
// that are switched on; the card itself is typed on the processor's secure
// page (Sergio never sees it). Back from it, /pagar/listo follows the order
// until the plan is on. Data from /v1/pagos.

import { useEffect, useState } from 'react';
import { ArrowUpRight, CreditCard, LockKeyhole, WalletCards } from 'lucide-react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { PaperPage } from '../components/Paper/PaperPage';
import { apiFetch } from '../lib/api';
import { celebrate } from '../lib/celebrate';
import './plans.css';

type Price = { plan: string; nombre: string; mult: number; usd: number; incluye: string[] };
type Method = { id: string; nombre: string; detalle: string; real: boolean };
type Order = {
  pedido: string;
  plan: string;
  usd: number;
  estado: string;
  hasta: number | null;
  recibo: string;
  pagado: number | null;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(String((body as { detail?: string }).detail || 'No pude completar eso.'));
  return body as T;
}

const money = (usd: number) => `$${(Number(usd) || 0).toFixed(2)}`;

function Checkout() {
  const [params] = useSearchParams();
  const plan = params.get('plan') || 'go';
  const rawMult = Number(params.get('mult') || 0);
  const mult = Number.isSafeInteger(rawMult) ? rawMult : 0;
  const once = plan === 'prueba';
  const [price, setPrice] = useState<Price | null>(null);
  const [methods, setMethods] = useState<Method[] | null>(null);
  const [busy, setBusy] = useState('');
  const [problem, setProblem] = useState(params.get('cancelado') ? 'Salió de la pasarela. Si autorizó un pago, compruebe su recibo antes de volver a intentar.' : '');
  const [methodProblem, setMethodProblem] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setPrice(null);
    setMethods(null);
    setMethodProblem(false);
    const init = { signal: controller.signal };
    call<Price>(`/v1/pagos/precio?plan=${encodeURIComponent(plan)}&mult=${mult}`, init)
      .then((p) => { if (!controller.signal.aborted) setPrice(p); })
      .catch((e: Error) => { if (!controller.signal.aborted) setProblem(e.message); });
    call<{ metodos: Method[] }>('/v1/pagos/metodos', init)
      .then((d) => { if (!controller.signal.aborted) setMethods(d.metodos); })
      .catch(() => { if (!controller.signal.aborted) setMethodProblem(true); });
    return () => controller.abort();
  }, [plan, mult]);

  const pay = async (m: Method) => {
    setBusy(m.id);
    setProblem('');
    try {
      const { url } = await call<{ url: string }>('/v1/pagos/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan: price?.plan, mult: price?.mult, metodo: m.id }),
      });
      window.location.assign(url);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : 'No pude abrir el pago.');
      setBusy('');
    }
  };

  const billing = async () => {
    setBusy('billing');
    try {
      const { url } = await call<{ url: string }>('/v1/pagos/portal', { method: 'POST' });
      window.location.assign(url);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : 'No pude abrir la suscripción.');
      setBusy('');
    }
  };

  return (
    <section className="pay-box pay-checkout">
      {price && (
        <div className="pay-summary">
          <span className="commerce-kicker"><LockKeyhole size={14} aria-hidden="true" /> Pago seguro · USD</span>
          <h2>{once ? price.nombre : `Sergio ${price.nombre}`}</h2>
          <div className="plan-price">
            {money(price.usd)}
            <small>{once ? ' una vez' : ' / mes, precio de lista'}</small>
          </div>
          <ul>
            {(price.incluye ?? []).map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </div>
      )}
      {problem && (
        <p className="pay-problem" role="alert">
          {problem}
        </p>
      )}
      {methods && methods.length > 0 && methods.every((m) => !m.real) && (
        <p className="pay-mode">Modo de prueba: no se cobra dinero real.</p>
      )}
      {methods && methods.length === 0 && (
        <p className="plans-note">Los pagos todavía no están activados en este Sergio.</p>
      )}
      {methodProblem && <p role="alert">No pude consultar las formas de pago. Recargue la pantalla.</p>}
      {!methods && !methodProblem && <p role="status">Consultando formas de pago…</p>}
      <div className="pay-methods" aria-label="Formas de pago">
        {(methods || []).map((m) => (
          <button
            key={m.id}
            type="button"
            className="pay-method"
            disabled={!!busy || !price}
            onClick={() => void pay(m)}
          >
            <span className="pay-mark" data-processor={m.id} aria-hidden="true">
              {m.id === 'stripe' ? <b>stripe</b> : m.id === 'paypal' ? <b>PayPal</b> : m.id === 'hyperswitch' ? <b>Hyperswitch</b> : <WalletCards size={20} />}
            </span>
            <span className="pay-method-copy">
              <strong>{busy === m.id ? 'Abriendo…' : m.nombre}</strong>
              <small>{once ? 'Pago único, sin renovación.' : m.detalle}{!m.real && ' · Prueba'}</small>
            </span>
            <ArrowUpRight size={16} aria-hidden="true" />
          </button>
        ))}
      </div>
      {!once && methods?.some((m) => m.id === 'stripe') && (
        <button type="button" className="paper-button" data-variant="quiet" disabled={!!busy} onClick={() => void billing()}>
          {busy === 'billing' ? 'Abriendo…' : 'Gestionar mi suscripción de Stripe'}
        </button>
      )}
      <p className="plans-note pay-trust"><CreditCard size={16} aria-hidden="true" />
        {once
          ? 'Escriba su tarjeta solo en la página segura del procesador. Después, devuelva el dólar desde su panel.'
          : 'La pasarela muestra los medios disponibles, sus logos y el total final con los descuentos aplicables. El plan se activa tras la confirmación del procesador.'}
      </p>
    </section>
  );
}

function Back({ problem }: { problem: boolean }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const id = params.get('pedido') || '';
  const [order, setOrder] = useState<Order | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    if (!id) return;
    let live = true;
    call<Order>(`/v1/pagos/pedido/${encodeURIComponent(id)}`)
      .then((o) => {
        if (!live) return;
        setOrder(o);
        if (o.estado === 'pagado') {
          celebrate({
            kind: 'plan',
            title: 'Pago recibido',
            detail: o.plan === 'prueba' ? 'La prueba de cobro funcionó.' : 'Su plan quedó activado.',
          });
        } else if (tries < 20) {
          window.setTimeout(() => live && setTries((t) => t + 1), 3000);
        }
      })
      .catch(() => live && setOrder(null));
    return () => {
      live = false;
    };
  }, [id, tries]);

  const paid = order?.estado === 'pagado';
  return (
    <section className="pay-box">
      <h2>{paid ? 'Listo' : problem ? 'No se completó el pago' : 'Confirmando el pago…'}</h2>
      {paid && order && (
        <div className="plans-rows pay-receipt">
          <div>
            <span>Recibo</span>
            <span>{order.recibo}</span>
          </div>
          <div>
            <span>Importe</span>
            <span>{money(order.usd)}</span>
          </div>
          <div>
            <span>Fecha</span>
            <span>{order.pagado ? new Date(order.pagado * 1000).toLocaleString() : ''}</span>
          </div>
        </div>
      )}
      <p className="plans-note">
        {paid && order?.plan === 'prueba'
          ? 'Todo el camino funcionó con su tarjeta. Devuelva el dólar desde el panel del procesador y márquelo en Cobros.'
          : paid
          ? `Su plan ${order?.plan} está activo${order?.hasta ? ` hasta el ${new Date(order.hasta * 1000).toLocaleDateString()}` : ''}.`
          : problem
            ? 'No hay un pago confirmado en Sergio. Si autorizó un cargo, revise su recibo antes de volver a intentarlo.'
            : tries >= 20
              ? 'El procesador todavía no confirma. Si ya pagó, su plan se activará solo en unos minutos.'
              : 'El procesador de pagos está confirmando. Esto tarda unos segundos.'}
      </p>
      <button type="button" className="paper-button" onClick={() => navigate(paid ? '/' : '/planes')}>
        {paid ? 'Ir a Sergio' : 'Volver a los planes'}
      </button>
    </section>
  );
}

export default function PayPage() {
  const { estado } = useParams();
  return (
    <PaperPage title="Pagar">
      {estado === 'listo' || estado === 'problema' ? <Back problem={estado === 'problema'} /> : <Checkout />}
    </PaperPage>
  );
}
