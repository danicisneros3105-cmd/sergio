import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { nodesApi, type Catalog, type SergioNode } from '../../lib/nodes';
import { CharacterCard, look, memberOf, ToneSelect } from './shared';

export function SettingsTab({ node, catalog, onChanged, onDeleted }: { node: SergioNode; catalog: Catalog | null; onChanged: () => void; onDeleted: () => void }) {
  const member = memberOf(node, catalog);
  const [name, setName] = useState(node.name);
  const [what, setWhat] = useState(node.instructions);
  const [tone, setTone] = useState(node.tone);

  const save = async () => {
    try {
      // The team keeps its name and its own voice; only the owner's extra instructions change.
      await nodesApi.update(node.id, member ? { instructions: what } : { name, instructions: what, tone });
      toast.success('Guardado.');
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude guardar.');
    }
  };

  return (
    <div className="node-settings">
      <CharacterCard avatar={look(node)} member={member} />
      {member ? (
        <div className="node-member">
          <div className="node-field">
            <span className="paper-label">{member.archetype}</span>
            <p>{member.mission}</p>
          </div>
          <div className="node-field">
            <span className="paper-label">Cómo habla</span>
            <p>{member.voice}</p>
          </div>
          <blockquote className="node-signature">{member.signature}</blockquote>
          {catalog?.team_pitch && (
            <div className="node-field">
              <span className="paper-label">El equipo</span>
              <p>{catalog.team_pitch}</p>
            </div>
          )}
        </div>
      ) : (
        <label className="node-field">
          <span className="paper-label">Nombre</span>
          <input className="paper-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} />
        </label>
      )}
      <label className="node-field">
        <span className="paper-label">{member ? 'Indicaciones suyas' : 'De qué se encarga'}</span>
        <textarea className="paper-input" rows={5} value={what} onChange={(e) => setWhat(e.target.value)} />
      </label>
      {!member && (
        <div className="node-field">
          <span className="paper-label">Forma de hablar</span>
          <ToneSelect value={tone} onChange={setTone} catalog={catalog} />
        </div>
      )}
      <div className="node-row-end">
        {!node.team && (
          <button
            type="button"
            className="paper-button"
            data-variant="quiet"
            onClick={async () => {
              if (!window.confirm(`¿Borrar a ${node.name}, su computadora y su memoria?`)) return;
              await nodesApi.remove(node.id);
              onDeleted();
            }}
          >
            <Trash2 size={14} /> Borrar
          </button>
        )}
        <button type="button" className="paper-button" onClick={save}>
          Guardar
        </button>
      </div>
    </div>
  );
}
