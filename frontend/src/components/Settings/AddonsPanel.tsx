// Optional add-ons in Settings: each with its line and a switch.
import { useAddons } from '../../lib/addons';

export function AddonsPanel() {
  const { addons, problem, set } = useAddons();
  if (problem && !addons) return <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{problem}</p>;
  if (!addons) return null;
  return (
    <div>
      {addons.map((a) => (
        <div key={a.clave} className="flex items-center justify-between gap-4 py-2.5"
          style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
          <div className="min-w-0">
            <div className="text-sm" style={{ color: 'var(--color-text)' }}>{a.nombre}</div>
            <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{a.lema}</div>
          </div>
          <button type="button" role="switch" aria-checked={a.activo} aria-label={a.nombre} className="ext-switch"
            onClick={() => void set(a.clave, !a.activo)} />
        </div>
      ))}
      {problem && <p className="text-xs mt-2" style={{ color: 'var(--color-error)' }}>{problem}</p>}
    </div>
  );
}
