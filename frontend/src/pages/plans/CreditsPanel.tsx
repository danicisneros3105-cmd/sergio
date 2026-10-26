// «Créditos» in Planes: more use today without changing plan (creditos.py).
// Each pack shows its price in the person's currency; «Comprar» opens the
// payment processor's page (Sergio never asks for card details) and the code
// that comes back is pasted below. Prices and what each use costs are in sight.

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { celebrate } from '../../lib/celebrate';

interface Pack {
  id: string;
  creditos: number;
  precio: { text: string; usd: number };
  pago: boolean;
}

interface Credits {
  saldo: number;
  packs: Pack[];
  costos: Record<string, number>;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(path, init);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(String((body as { detail?: string }).detail || 'No pude completar eso.'));
  return body as T;
}

export function CreditsPanel({ country }: { country: string }) {
  const [data, setData] = useState<Credits | null>(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    call<Credits>(`/v1/plans/creditos?country=${country}`).then(setData).catch(() => setData(null));
  }, [country]);
  if (!data) return null;

  const buy = async (pack: Pack) => {
    try {
      const { url } = await call<{ url: string }>('/v1/plans/creditos/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pack: pack.id }),
      });
      window.open(url, '_blank', 'noopener');
      toast.success('Se abrió la página de pago. Al pagar recibirá un código: péguelo abajo.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude abrir el pago.');
    }
  };
  const redeem = async () => {
    if (!code.trim()) return;
    setBusy(true);
    try {
      const before = data.saldo;
      const { saldo } = await call<{ saldo: number }>('/v1/plans/creditos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: code }),
      });
      setCode('');
      setData({ ...data, saldo });
      celebrate({ kind: 'plan', title: `+${saldo - before} créditos`, detail: `Ahora tiene ${saldo}.` });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude usar el código.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="credits">
      <h2 className="paper-label">Créditos</h2>
      <p className="plans-note">
        Para cuando se acaba el límite de hoy, sin cambiar de plan. Tiene <b>{data.saldo}</b> créditos.
      </p>
      <div className="credits-packs">
        {data.packs.map((p) => (
          <div key={p.id} className="credits-pack">
            <span className="credits-n">{p.creditos}</span>
            <span className="credits-label">créditos</span>
            <span className="credits-price">{p.precio.text}</span>
            <button type="button" className="paper-button" onClick={() => void buy(p)}>Comprar</button>
          </div>
        ))}
      </div>
      <p className="plans-note">
        Lo que cuesta cada uso de más:{' '}
        {Object.entries(data.costos).map(([what, n], i) => (
          <span key={what}>{i ? ' · ' : ''}{what.toLowerCase()}: {n}</span>
        ))}
        .
      </p>
      <div className="plans-key">
        <input
          className="paper-input"
          aria-label="Código de créditos"
          placeholder="sergio-cred-v1…"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void redeem()}
        />
        <button type="button" className="paper-button" disabled={busy || !code.trim()} onClick={() => void redeem()}>
          Usar código
        </button>
      </div>
    </section>
  );
}
