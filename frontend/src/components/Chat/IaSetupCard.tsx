// First run on this computer with no AI connected (owner, 2 Nov 2026: «inicié
// sesión pero no tengo ninguna clave API»). Keys cannot appear out of nothing:
// they live in the owner's own OpenRouter account. So one clear step: connect
// with one click; and, for selling plans, the management key in a password
// field (Sergio then creates every customer's capped key by itself).
import { useEffect, useState } from 'react';
import { aiState, connectOneClick, saveManagementKey, type AiState } from '../../lib/conectar';

export function ManagementKeyForm({ onSaved }: { onSaved?: (ia: boolean) => void }) {
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState('');
  const save = async () => {
    setBusy(true);
    setSaid('');
    try {
      const r = await saveManagementKey(key.trim());
      setKey('');
      setSaid(r.ia ? 'Guardada. Su clave y las de sus clientes se crean solas.' : 'Guardada.');
      onSaved?.(r.ia);
    } catch (e) {
      setSaid((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="ia-gestion"
      onSubmit={(e) => {
        e.preventDefault();
        if (key.trim()) void save();
      }}
    >
      <input
        type="password"
        autoComplete="off"
        spellCheck={false}
        placeholder="sk-or-… (clave de gestión)"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        aria-label="Clave de gestión de OpenRouter"
      />
      <button type="submit" disabled={busy || !key.trim()}>
        {busy ? 'Comprobando…' : 'Guardar'}
      </button>
      {said && <p role="status">{said}</p>}
    </form>
  );
}

export function IaSetupCard() {
  const [st, setSt] = useState<AiState | null>(null);
  const [problem, setProblem] = useState('');
  useEffect(() => {
    void aiState().then(setSt);
  }, []);
  if (!st || st.ia || !st.local) return null;
  return (
    <div className="ia-setup">
      <b>Falta conectar la IA</b>
      <p>
        Las claves viven en su cuenta de OpenRouter; Sergio no puede crearlas sin ella. Un toque: inicia sesión allí,
        aprueba, y Sergio guarda la clave solo.
      </p>
      <button type="button" className="ia-setup-go" onClick={() => connectOneClick().catch((e) => setProblem((e as Error).message))}>
        Conectar la IA con un clic
      </button>
      {problem && <p className="ia-setup-problem">{problem}</p>}
      <details>
        <summary>¿Va a vender planes? Clave de gestión</summary>
        <p>
          Créela en openrouter.ai → Settings → Provisioning API keys y péguela aquí (nunca en el chat). Con ella Sergio
          crea su clave y la de cada cliente, con el tope de su plan.
        </p>
        <ManagementKeyForm onSaved={(ia) => ia && setSt({ ...st, ia: true, gestion: true })} />
      </details>
    </div>
  );
}

export default IaSetupCard;
