import { useEffect, useState, type FormEvent } from 'react';
import { Gift } from 'lucide-react';
import { apiFetch } from '../../lib/api';

type Referral = {
  activo: boolean;
  codigo?: string;
  vinculado?: boolean;
  puede_vincular?: boolean;
  disponibles?: number;
  en_revision?: number;
};

export function ReferralPanel() {
  const [data, setData] = useState<Referral | null>(null);
  const [code, setCode] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch('/v1/pagos/referidos', { signal: controller.signal })
      .then((r) => r.ok ? r.json() : null)
      .then((r) => { if (!controller.signal.aborted) setData(r); })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  if (!data?.activo) return null;

  const link = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    try {
      const r = await apiFetch('/v1/pagos/referidos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codigo: code.trim() }),
      });
      const result = await r.json();
      if (!r.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'No pude vincular el código.');
      setData(result);
      setMessage('Código vinculado.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'No pude vincular el código.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="profile-referrals" aria-labelledby="profile-referrals-title">
      <div className="profile-referrals-icon"><Gift aria-hidden="true" size={23} /></div>
      <div>
        <h2 id="profile-referrals-title">Invita a alguien</h2>
        <p>Hasta 5 % para cada uno cuando la persona compra su primer plan elegible. El descuento se habilita tras 30 días y se aplica al siguiente pago elegible por PayPal o a una nueva suscripción de Stripe. No se acumula ni cambia una renovación activa.</p>
        {data.codigo && (
          <div className="profile-referrals-actions">
            <code>{data.codigo}</code>
            <button className="paper-button" type="button" onClick={async () => {
              try {
                await navigator.clipboard.writeText(data.codigo || '');
                setMessage('Código copiado.');
              } catch {
                setMessage('Seleccione el código para copiarlo.');
              }
            }}>Copiar código</button>
          </div>
        )}
        {data.puede_vincular && (
          <form className="profile-referrals-actions" onSubmit={link}>
            <input className="paper-input" aria-label="Código de invitación" placeholder="Código de invitación" value={code} maxLength={16} onChange={(e) => setCode(e.target.value.toUpperCase())} required />
            <button className="paper-button" type="submit" disabled={busy || !/^[0-9A-F]{16}$/.test(code.trim())}>Vincular</button>
          </form>
        )}
        {data.vinculado && <p>Invitación vinculada.</p>}
        {!!data.en_revision && <p>Descuentos en revisión: {data.en_revision}</p>}
        {!!data.disponibles && <p>Descuentos disponibles: {data.disponibles}</p>}
        {message && <p role="status">{message}</p>}
      </div>
    </section>
  );
}
