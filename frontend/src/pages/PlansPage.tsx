// Plans and billing: the five plans in the visitor's own currency, today's use
// against the plan's limits, how to pay, and the account. Data from /v1/plans.
// Sergio never asks for card details: payment happens on the processor's page
// and comes back as a licence key that is checked offline.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router';
import { PaperPage } from '../components/Paper/PaperPage';
import { apiFetch } from '../lib/api';
import { detectCountry, percent, saveCountry, type Account, type Catalog, type Me, type Plan } from '../lib/plans';
import { voiceLanguage } from '../lib/liveSession';
import { celebrate } from '../lib/celebrate';
import { CreditsPanel } from './plans/CreditsPanel';
import { PagosPanel } from './plans/PagosPanel';
import { agree, getPersonal } from '../lib/personal';
import './plans.css';

/** «Bienvenido a» / «Bienvenida a» / «Ya tiene» (personal.ts). */
const welcomeWord = () => agree(getPersonal(), 'Bienvenido a', 'Bienvenida a', 'Ya tiene');

type Tab = 'planes' | 'uso' | 'facturacion' | 'cuenta';
const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'planes', label: 'Planes' },
  { id: 'uso', label: 'Uso' },
  { id: 'facturacion', label: 'Facturación' },
  { id: 'cuenta', label: 'Cuenta' },
];
const LANGUAGES = [
  ['es', 'Español'],
  ['en', 'English'],
  ['fr', 'Français'],
  ['pt', 'Português'],
  ['it', 'Italiano'],
  ['de', 'Deutsch'],
];

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(String((body as { detail?: string }).detail || 'No pude completar eso.'));
  return body as T;
}

function PlanCard({
  plan,
  current,
  mult,
  setMult,
  onChoose,
}: {
  plan: Plan;
  current: boolean;
  mult: number;
  setMult: (n: number) => void;
  onChoose: () => void;
}) {
  const s = plan.stretch;
  return (
    <article className="plan-card" data-current={current}>
      <h2>
        {plan.name}
        {current && <small>Su plan</small>}
      </h2>
      <div className="plan-price">
        {plan.id === 'free' ? 'Gratis' : plan.price.text}
        {plan.id !== 'free' && <small> / mes</small>}
      </div>
      <p>{plan.tagline}</p>
      <p>
        {plan.id === 'free' ? 'Uso base' : `${plan.mult} ${plan.mult === 1 ? 'vez' : 'veces'} el uso de Free`}
      </p>
      {s && (
        <label className="plan-range">
          <span>
            Usted elige: {mult}x el uso de Free ({s.from} a {s.to})
          </span>
          <input
            type="range"
            min={s.mult_min}
            max={s.mult_max}
            value={mult}
            aria-label={`Uso de ${plan.name}`}
            onChange={(e) => setMult(Number(e.target.value))}
          />
        </label>
      )}
      <ul>
        {plan.includes.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
      {plan.id === 'free' ? (
        <button type="button" className="paper-button" data-variant="quiet" disabled>
          {current ? 'Su plan' : 'Siempre disponible'}
        </button>
      ) : (
        <button type="button" className="paper-button" onClick={onChoose}>
          {current ? 'Renovar o cambiar' : `Elegir ${plan.name}`}
        </button>
      )}
    </article>
  );
}

export function PlansPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('planes');
  const [country, setCountry] = useState(detectCountry);
  const [mults, setMults] = useState<Record<string, number>>({});
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [problem, setProblem] = useState('');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);

  const loadMe = useCallback(() => {
    json<Me>('/v1/plans/me')
      .then((d) => setMe(d))
      .catch(() => setProblem('No pude leer su plan. Compruebe que Sergio está en marcha.'));
  }, []);
  useEffect(loadMe, [loadMe]);

  const devMult = mults.dev || 0;
  const foundersMult = mults.founders || 0;
  useEffect(() => {
    let live = true;
    json<Catalog>(`/v1/plans?country=${country}&mult_dev=${devMult}&mult_founders=${foundersMult}`)
      .then((d) => live && (setCatalog(d), setProblem('')))
      .catch(() => live && setProblem('No pude leer los planes. Compruebe que Sergio está en marcha.'));
    return () => {
      live = false;
    };
  }, [country, devMult, foundersMult]);

  const account: Account | undefined = me?.account;
  const currentId = account?.plan ?? 'free';

  const choose = async (plan: Plan) => {
    // Sergio Pagos switched on: Sergio's own checkout, the plan turns on by itself.
    const own = await apiFetch('/v1/pagos/metodos')
      .then((r) => (r.ok ? r.json() : { metodos: [] }))
      .catch(() => ({ metodos: [] }));
    if ((own as { metodos?: unknown[] }).metodos?.length) {
      navigate(`/pagar?plan=${plan.id}&mult=${plan.mult}`);
      return;
    }
    try {
      const { url } = await json<{ url: string }>('/v1/plans/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan: plan.id, mult: plan.mult }),
      });
      window.open(url, '_blank', 'noopener,noreferrer');
      toast.success('Se abrió la página de pago. Al pagar recibirá una clave: péguela abajo.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude abrir el pago.');
      setTab('facturacion');
    }
  };

  const activate = async () => {
    if (!key.trim()) return;
    setBusy(true);
    try {
      const out = await json<{ account?: { plan?: string; plan_name?: string } }>('/v1/plans/license', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      });
      setKey('');
      const name = out.account?.plan_name || 'su plan nuevo';
      celebrate({ kind: 'plan', title: `${welcomeWord()} ${name}`, detail: 'Su plan quedó activado.' });
      loadMe();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude activar la clave.');
    } finally {
      setBusy(false);
    }
  };

  const removeKey = async () => {
    try {
      await json('/v1/plans/license', { method: 'DELETE' });
      toast.success('Licencia quitada: vuelve a Free.');
      loadMe();
    } catch {
      toast.error('No pude quitar la licencia.');
    }
  };

  const bar = useMemo(
    () =>
      catalog && (
        <div className="plans-bar">
          <label>
            País
            <select
              className="paper-input"
              aria-label="País para los precios"
              value={country}
              onChange={(e) => {
                saveCountry(e.target.value);
                setCountry(e.target.value);
              }}
            >
              {!catalog.countries.some((c) => c.code === country) && <option value={country}>{country}</option>}
              {catalog.countries.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <span className="paper-meta">Precios en {catalog.currency}</span>
        </div>
      ),
    [catalog, country],
  );

  return (
    <PaperPage title="Planes" wide>
      <div className="plans-tabs" role="tablist" aria-label="Secciones">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            className="paper-tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {problem && <p className="paper-meta">{problem}</p>}

      {tab === 'planes' && catalog && (
        <>
          {bar}
          <div className="plans-grid">
            {catalog.plans.map((p) => (
              <PlanCard
                key={p.id}
                plan={p}
                current={p.id === currentId}
                mult={mults[p.id] || p.mult}
                setMult={(n) => setMults((m) => ({ ...m, [p.id]: n }))}
                onChoose={() => void choose(p)}
              />
            ))}
          </div>
          <p className="plans-note">
            Go cuesta 5 dólares al mes o su equivalente en su moneda, nunca menos. Los precios en otras monedas se
            calculan con el cambio del {catalog.rates_date}
            {catalog.rates_live ? '' : ' (aproximado)'}; la página de pago confirma el monto exacto.
          </p>
        </>
      )}

      {tab === 'uso' && me && (
        <section>
          <p className="paper-meta">
            Uso de hoy, con el límite de su plan ({me.usage.multiplier}x el uso de Free). Se reinicia cada día.
            {me.usage.blocking
              ? ' Al llegar al límite, Sergio espera a mañana o a que suba de plan.'
              : ' En este equipo los límites se cuentan pero no detienen nada.'}
          </p>
          {me.usage.items.map((i) => (
            <div className="meter" key={i.kind}>
              <div className="meter-top">
                <span>{i.label}</span>
                <span>
                  {i.used} de {i.limit}
                </span>
              </div>
              <div
                className="meter-bar"
                role="progressbar"
                aria-label={i.label}
                aria-valuemin={0}
                aria-valuemax={i.limit}
                aria-valuenow={Math.min(i.used, i.limit)}
              >
                <i style={{ width: `${percent(i.used, i.limit)}%` }} />
              </div>
            </div>
          ))}
          <p>
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/uso')}>
              Ver modelos y costo
            </button>
          </p>
        </section>
      )}

      {tab === 'facturacion' && me && (
        <section>
          <div className="plans-rows">
            <div>
              <span>Plan</span>
              <span>{me.account.plan_name}</span>
            </div>
            <div>
              <span>Pagos</span>
              <span>{me.billing.payments_on ? 'Activados' : 'Todavía no activados en este equipo'}</span>
            </div>
            <div>
              <span>Próximo cobro</span>
              <span>{me.account.expires_text ? `Vence el ${me.account.expires_text}` : 'Sin cobros'}</span>
            </div>
            <div>
              <span>Facturas</span>
              <span>{me.billing.invoices.length ? `${me.billing.invoices.length}` : 'Ninguna todavía'}</span>
            </div>
          </div>
          <p className="plans-note">
            Sergio nunca le pide los datos de su tarjeta: el pago se hace en la página segura del procesador de pagos y
            de vuelta recibe una clave de licencia. Los datos de pago y las facturas están allí.
          </p>
          <p>
            {me.billing.portal && (
              <a className="paper-button" href={me.billing.portal} target="_blank" rel="noopener noreferrer">
                Administrar pagos y facturas
              </a>
            )}
          </p>
          <h2 className="paper-label">Tengo una clave de licencia</h2>
          <div className="plans-key">
            <input
              className="paper-input"
              aria-label="Clave de licencia"
              placeholder="sergio-lic-v1…"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void activate()}
            />
            <button type="button" className="paper-button" disabled={busy || !key.trim()} onClick={() => void activate()}>
              Activar
            </button>
          </div>
          <CreditsPanel country={country} />
          <PagosPanel />
        </section>
      )}

      {tab === 'cuenta' && account && (
        <section>
          <div className="plans-rows">
            <div>
              <span>Plan</span>
              <span>
                {account.plan_name}
                {account.mult > 1 ? ` · ${account.mult}x el uso de Free` : ''}
              </span>
            </div>
            <div>
              <span>Titular</span>
              <span>{account.holder || 'Este equipo'}</span>
            </div>
            <div>
              <span>Vence</span>
              <span>{account.expires_text || 'No vence'}</span>
            </div>
            <div>
              <span>Puestos</span>
              <span>{account.seats}</span>
            </div>
            <div>
              <span>Idioma de Sergio</span>
              <span>
                <select
                  className="paper-input"
                  aria-label="Idioma de Sergio"
                  defaultValue={voiceLanguage()}
                  onChange={(e) => {
                    try {
                      localStorage.setItem('sergio.lang', e.target.value);
                    } catch {
                      // private window: lasts this visit
                    }
                    toast.success('Listo. Vale desde la próxima conversación.');
                  }}
                >
                  {LANGUAGES.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </span>
            </div>
          </div>
          {account.problem && <p className="plans-note">{account.problem[0].toUpperCase() + account.problem.slice(1)}.</p>}
          <h2 className="paper-label">Lo que incluye su plan</h2>
          <div className="plans-rows">
            {account.features.map((f) => (
              <div key={f.id}>
                <span>{f.label}</span>
                <span>
                  {f.soon
                    ? 'Próximamente'
                    : f.on
                      ? 'Incluido'
                      : `Desde ${f.plan === 'founders' ? 'Founders' : f.plan[0].toUpperCase() + f.plan.slice(1)}`}
                </span>
              </div>
            ))}
          </div>
          <p className="plans-note">
            La interfaz está en español; el idioma de Sergio cambia cómo habla y qué entiende.
          </p>
          <p>
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/ayuda')}>
              Ayuda
            </button>{' '}
            {account.plan !== 'free' && (
              <button type="button" className="paper-button" data-variant="quiet" onClick={() => void removeKey()}>
                Quitar la licencia de este equipo
              </button>
            )}
          </p>
        </section>
      )}
    </PaperPage>
  );
}

export default PlansPage;
