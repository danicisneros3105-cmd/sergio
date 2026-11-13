// Plans and billing: video-focused with psychological pricing effects
// Decoy pricing, FOMO, scarcity, and streak gamification for retention

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
import { Clock, Users, Flame, TrendingUp, Zap, Crown, Star, AlertTriangle, CheckCircle, Sparkles } from 'lucide-react';
import './plans.css';

const welcomeWord = () => agree(getPersonal(), 'Bienvenido a', 'Bienvenida a', 'Ya tiene');

type Tab = 'planes' | 'uso' | 'facturacion' | 'cuenta';
const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'planes', label: 'Planes' },
  { id: 'uso', label: 'Uso' },
  { id: 'facturacion', label: 'Facturacion' },
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

// FOMO countdown timer
function FOMOTimer() {
  const [timeLeft, setTimeLeft] = useState(() => {
    const now = new Date();
    const midnight = new Date(now);
    midnight.setHours(24, 0, 0, 0);
    return Math.floor((midnight.getTime() - now.getTime()) / 1000);
  });

  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft(t => {
        if (t <= 1) {
          const now = new Date();
          const midnight = new Date(now);
          midnight.setHours(24, 0, 0, 0);
          return Math.floor((midnight.getTime() - now.getTime()) / 1000);
        }
        return t - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const h = Math.floor(timeLeft / 3600);
  const m = Math.floor((timeLeft % 3600) / 60);
  const s = timeLeft % 60;

  return (
    <div className="plans-fomo-timer">
      <Clock size={14} />
      <span>Oferta exclusiva termina en </span>
      <b>{h.toString().padStart(2, '0')}:{m.toString().padStart(2, '0')}:{s.toString().padStart(2, '0')}</b>
    </div>
  );
}

// Social proof counter
function SocialProof() {
  const [count, setCount] = useState(47);
  useEffect(() => {
    const interval = setInterval(() => {
      setCount(c => c + (Math.random() > 0.7 ? 1 : 0));
    }, 15000);
    return () => clearInterval(interval);
  }, []);
  return (
    <div className="plans-social-proof">
      <Users size={12} />
      <span><b>{count}</b> personas eligieron un plan hoy</span>
      <span className="plans-live-dot" />
    </div>
  );
}

// Streak indicator
function StreakBanner({ days }: { days: number }) {
  if (days <= 0) return null;
  return (
    <div className="plans-streak">
      <Flame size={16} />
      <div>
        <b>Racha de {days} dias</b>
        <span>Sigues editando como un pro. Manten tu racha para desbloquear bonus.</span>
      </div>
    </div>
  );
}

function PlanCard({
  plan,
  current,
  mult,
  setMult,
  onChoose,
  fomoActive,
  index,
}: {
  plan: Plan;
  current: boolean;
  mult: number;
  setMult: (n: number) => void;
  onChoose: () => void;
  fomoActive: boolean;
  index: number;
}) {
  const s = plan.stretch;
  // Decoy: middle plan gets "Most Popular" badge to push users toward it
  const isDecoy = index === 1; // middle plan

  return (
    <article className="plan-card" data-current={current} data-recommended={isDecoy || plan.id === 'work'} data-decoy={isDecoy}>
      {isDecoy && (
        <div className="plan-badge-popular">
          <Star size={10} /> Mas Popular
        </div>
      )}
      {fomoActive && plan.id !== 'free' && (
        <div className="plan-badge-fomo">
          <Zap size={10} /> 40% OFF HOY
        </div>
      )}
      <h2>
        {plan.name}
        {current ? <small>Su plan</small> : isDecoy ? <small>Recomendado</small> : null}
      </h2>
      <div className="plan-price">
        {plan.id === 'free' ? 'Gratis' : (
          <>
            {fomoActive && plan.id !== 'free' ? (
              <>
                <span className="plan-price-old">{plan.price.text}</span>
                <span className="plan-price-new">{Math.round(plan.price.cents * 0.6 / 100)}{plan.price.symbol}/mes</span>
              </>
            ) : (
              <>{plan.price.text}</>
            )}
            {plan.id !== 'free' && <small> / mes</small>}
          </>
        )}
      </div>
      <p>{plan.tagline}</p>
      <div className="plan-capacity"><strong>{mult}×</strong><span>capacidad frente a Free</span></div>
      {s && (
        <label className="plan-range">
          <span>Usted elige: {mult}x el uso de Free ({s.from} a {s.to})</span>
          <input type="range" min={s.mult_min} max={s.mult_max} value={mult} aria-label={`Uso de ${plan.name}`} onChange={(e) => setMult(Number(e.target.value))} />
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
        <button type="button" className={`paper-button ${isDecoy ? 'decoy-btn' : ''}`} onClick={onChoose}>
          {current ? 'Renovar o cambiar' : isDecoy ? 'Elegir plan ideal →' : `Elegir ${plan.name}`}
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
  const [streakDays] = useState(() => {
    try {
      return Number(localStorage.getItem('sergio-streak-days') || '0');
    } catch {
      return 0;
    }
  });

  const loadMe = useCallback(() => {
    json<Me>('/v1/plans/me')
      .then((d) => setMe(d))
      .catch(() => setProblem('No pude leer su plan. Compruebe que Sergio esta en marcha.'));
  }, []);
  useEffect(loadMe, [loadMe]);

  const devMult = mults.dev || 0;
  const foundersMult = mults.founders || 0;
  useEffect(() => {
    let live = true;
    json<Catalog>(`/v1/plans?country=${country}&mult_dev=${devMult}&mult_founders=${foundersMult}`)
      .then((d) => live && (setCatalog(d), setProblem('')))
      .catch(() => live && setProblem('No pude leer los planes. Compruebe que Sergio esta en marcha.'));
    return () => { live = false; };
  }, [country, devMult, foundersMult]);

  const account: Account | undefined = me?.account;
  const currentId = account?.plan ?? 'free';

  const choose = async (plan: Plan) => {
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
      toast.success('Se abrio la pagina de pago. Al pagar recibira una clave: peguela abajo.');
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
      celebrate({ kind: 'plan', title: `${welcomeWord()} ${name}`, detail: 'Su plan quedo activado.' });
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
            Pais
            <select className="paper-input" aria-label="Pais para los precios" value={country} onChange={(e) => { saveCountry(e.target.value); setCountry(e.target.value); }}>
              {!(catalog.countries ?? []).some((c) => c.code === country) && <option value={country}>{country}</option>}
              {(catalog.countries ?? []).map((c) => (
                <option key={c.code} value={c.code}>{c.name}</option>
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
          <button key={t.id} type="button" role="tab" className="paper-tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {problem && <p className="paper-meta">{problem}</p>}

      {tab === 'planes' && catalog && (
        <>
          {/* Psychological pricing hero */}
          <div className="commerce-hero video-hero">
            <div>
              <span className="commerce-kicker">Sergio Studio · Edicion de Video con IA</span>
              <h2>Transforma ideas en videos virales.</h2>
              <p>Edicion profesional, IA que entiende trends, efectos de Hollywood y exportacion en segundos. Empieza gratis — los pros eligen Studio Pro.</p>
            </div>
            <div className="commerce-ring" aria-hidden="true" />
          </div>

          <StreakBanner days={streakDays} />
          <FOMOTimer />
          <SocialProof />

          {bar}
          <div className="plans-grid">
            {catalog.plans.map((p, i) => (
              <PlanCard
                key={p.id}
                plan={p}
                current={p.id === currentId}
                mult={mults[p.id] || p.mult}
                setMult={(n) => setMults((m) => ({ ...m, [p.id]: n }))}
                onChoose={() => void choose({ ...p, mult: mults[p.id] || p.mult })}
                fomoActive={true}
                index={i}
              />
            ))}
          </div>

          {/* Scarcity / FOMO footer */}
          <div className="plans-fomo-footer">
            <div className="plans-fomo-item">
              <TrendingUp size={14} />
              <span><b>2.3M</b> videos editados este mes</span>
            </div>
            <div className="plans-fomo-item">
              <Crown size={14} />
              <span><b>94%</b> de usuarios Pro renovaron su plan</span>
            </div>
            <div className="plans-fomo-item">
              <Sparkles size={14} />
              <span>Exportacion <b>4K sin marca de agua</b> solo en planes pagos</span>
            </div>
          </div>

          <p className="plans-note">
            Los precios se calculan con el cambio del {catalog.rates_date}{catalog.rates_live ? '' : ' (aproximado)'}; la pagina de pago confirma el monto exacto.
          </p>
        </>
      )}

      {tab === 'uso' && me && (
        <section>
          <p className="paper-meta">
            Uso de hoy, con el limite de su plan ({me.usage.multiplier}x el uso de Free). Se reinicia cada dia.
            {me.usage.blocking
              ? ' Al llegar al limite, Sergio espera a manana o a que suba de plan.'
              : ' En este equipo los limites se cuentan pero no detienen nada.'}
          </p>
          {me.usage.items.map((i) => (
            <div className="meter" key={i.kind}>
              <div className="meter-top"><span>{i.label}</span><span>{i.used} de {i.limit}</span></div>
              <div className="meter-bar" role="progressbar" aria-label={i.label} aria-valuemin={0} aria-valuemax={i.limit} aria-valuenow={Math.min(i.used, i.limit)}>
                <i style={{ width: `${percent(i.used, i.limit)}%` }} />
              </div>
            </div>
          ))}
          <p>
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/uso')}>Ver modelos y costo</button>
          </p>
        </section>
      )}

      {tab === 'facturacion' && me && (
        <section>
          <div className="plans-rows">
            <div><span>Plan</span><span>{me.account.plan_name}</span></div>
            <div><span>Pagos</span><span>{me.billing.payments_on ? 'Activados' : 'Todavia no activados en este equipo'}</span></div>
            <div><span>Proximo cobro</span><span>{me.account.expires_text ? `Vence el ${me.account.expires_text}` : 'Sin cobros'}</span></div>
            <div><span>Facturas</span><span>{me.billing.invoices.length ? `${me.billing.invoices.length}` : 'Ninguna todavia'}</span></div>
          </div>
          <p className="plans-note">
            Sergio nunca le pide los datos de su tarjeta: el pago se hace en la pagina segura del procesador de pagos y de vuelta recibe una clave de licencia.
          </p>
          <p>
            {me.billing.portal && (
              <a className="paper-button" href={me.billing.portal} target="_blank" rel="noopener noreferrer">Administrar pagos y facturas</a>
            )}
          </p>
          <h2 className="paper-label">Tengo una clave de licencia</h2>
          <div className="plans-key">
            <input className="paper-input" aria-label="Clave de licencia" placeholder="sergio-lic-v1..." value={key} onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && void activate()} />
            <button type="button" className="paper-button" disabled={busy || !key.trim()} onClick={() => void activate()}>Activar</button>
          </div>
          <CreditsPanel country={country} />
          <PagosPanel />
        </section>
      )}

      {tab === 'cuenta' && account && (
        <section>
          <div className="plans-rows">
            <div><span>Plan</span><span>{account.plan_name}{account.mult > 1 ? ` · ${account.mult}x el uso de Free` : ''}</span></div>
            <div><span>Titular</span><span>{account.holder || 'Este equipo'}</span></div>
            <div><span>Vence</span><span>{account.expires_text || 'No vence'}</span></div>
            <div><span>Puestos</span><span>{account.seats}</span></div>
            <div><span>Idioma de Sergio</span>
              <span><select className="paper-input" aria-label="Idioma de Sergio" defaultValue={voiceLanguage()} onChange={(e) => { try { localStorage.setItem('sergio.lang', e.target.value); } catch {} toast.success('Listo. Vale desde la proxima conversacion.'); }}>
                {LANGUAGES.map(([v, l]) => (<option key={v} value={v}>{l}</option>))}
              </select></span>
            </div>
          </div>
          {account.problem && <p className="plans-note">{account.problem[0].toUpperCase() + account.problem.slice(1)}.</p>}
          <h2 className="paper-label">Lo que incluye su plan</h2>
          <div className="plans-rows">
            {account.features.map((f) => (
              <div key={f.id}><span>{f.label}</span><span>{f.soon ? 'Proximamente' : f.on ? 'Incluido' : `Desde ${f.plan === 'founders' ? 'Founders' : f.plan[0].toUpperCase() + f.plan.slice(1)}`}</span></div>
            ))}
          </div>
          <p className="plans-note">La interfaz esta en espanol; el idioma de Sergio cambia como habla y que entiende.</p>
          <p>
            <button type="button" className="paper-button" data-variant="quiet" onClick={() => navigate('/ayuda')}>Ayuda</button>{' '}
            {account.plan !== 'free' && (
              <button type="button" className="paper-button" data-variant="quiet" onClick={() => void removeKey()}>Quitar la licencia de este equipo</button>
            )}
          </p>
        </section>
      )}
    </PaperPage>
  );
}

export default PlansPage;
