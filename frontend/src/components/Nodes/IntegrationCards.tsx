import type { IntegrationPreset } from '../../lib/nodes-api';

export function IntegrationCards({ presets, busy, onAdd }: {
  presets: IntegrationPreset[]; busy: boolean; onAdd: (preset: IntegrationPreset) => void;
}) {
  return <div className="space-y-3">{presets.map(p => <div key={p.id} className="border rounded-lg p-3">
    <strong>{p.name}</strong><p className="text-sm opacity-70">{p.note}</p>
    <a className="underline text-sm" href={p.repository} target="_blank" rel="noreferrer">Proyecto original</a>
    <button className="rounded-lg border px-3 py-2 disabled:opacity-40" disabled={busy || !p.available} onClick={() => onAdd(p)}>
      {p.available ? 'Agregar con revisión' : 'Requiere instalación en Ubuntu/WSL'}
    </button>
  </div>)}</div>;
}
