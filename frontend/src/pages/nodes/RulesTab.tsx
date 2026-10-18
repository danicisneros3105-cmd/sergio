import { useState } from 'react';
import { X } from 'lucide-react';
import { toast } from 'sonner';
import { nodesApi, RULE_ES, type Catalog, type RuleChoice, type SergioNode } from '../../lib/nodes';

const RULE_IDEAS = [
  'Pídeme permiso antes de borrar archivos',
  'Nunca publiques nada en redes sociales',
  'No compres nada sin preguntarme',
  'Avísame antes de enviar correos a clientes',
];

/** The owner's own rules in plain words, reviewed by code before every action. */
function OwnRules({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const add = async (value = text) => {
    if (!value.trim()) return;
    setBusy(true);
    try {
      const out = await nodesApi.addOwnRule(node.id, value.trim());
      toast.success(`Entendido. ${out.rule.explain}.`);
      setText('');
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude guardar la regla.');
    } finally {
      setBusy(false);
    }
  };
  const rules = node.own_rules ?? [];
  return (
    <section className="node-own-rules" aria-label="Reglas propias">
      <h3>Reglas propias</h3>
      <p className="node-hint">
        Escríbalas como se las diría a una persona. Antes de cada acción, {node.name} las revisa por código (no a ojo):
        lo prohibido no se hace y lo demás le espera para su aprobación.
      </p>
      {rules.length > 0 && (
        <ul>
          {rules.map((r) => (
            <li key={r.id} data-effect={r.effect}>
              <span>
                <b>{r.text}</b>
                <small>{r.explain}</small>
              </span>
              <button
                type="button"
                className="mac-icon-btn"
                aria-label={`Quitar la regla ${r.text}`}
                onClick={() => void nodesApi.removeOwnRule(node.id, r.id).then(onChanged)}
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="node-own-rule-add"
        onSubmit={(e) => {
          e.preventDefault();
          void add();
        }}
      >
        <input
          className="paper-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="«Pídeme permiso antes de borrar archivos»"
          aria-label="Nueva regla propia"
          disabled={busy}
        />
        <button type="submit" className="paper-button" disabled={busy || text.trim().length < 6}>
          Añadir
        </button>
      </form>
      {rules.length === 0 && (
        <div className="studio-chips">
          {RULE_IDEAS.map((idea) => (
            <button key={idea} type="button" onClick={() => void add(idea)} disabled={busy}>
              {idea}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export function RulesTab({ node, catalog, onChanged }: { node: SergioNode; catalog: Catalog | null; onChanged: () => void }) {
  const set = async (key: string, choice: RuleChoice) => {
    await nodesApi.update(node.id, { rules: { ...node.rules, [key]: choice } });
    onChanged();
  };
  return (
    <div className="node-rules">
      <p className="node-hint">
        Qué hace {node.name} solo, qué le pregunta antes y qué no hará nunca. Enviar mensajes o correos, borrar y pagar
        nunca son automáticos: le deja el borrador y usted decide. Usar su PC está apagado hasta que usted lo permita.
      </p>
      {(catalog?.rules || []).map((r) => (
        <div key={r.key} className="node-rule">
          <span>{r.label}</span>
          <div className="node-seg" role="radiogroup" aria-label={r.label}>
            {(['allow', 'ask', 'block'] as RuleChoice[]).map((c) => (
              <button key={c} type="button" role="radio" aria-checked={node.rules[r.key] === c} disabled={!r.choices.includes(c)} onClick={() => set(r.key, c)}>
                {RULE_ES[c]}
              </button>
            ))}
          </div>
        </div>
      ))}
      <OwnRules node={node} onChanged={onChanged} />
    </div>
  );
}
