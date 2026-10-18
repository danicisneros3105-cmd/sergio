import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { nodesApi, type SergioNode } from '../../lib/nodes';

export function MemoryTab({ node, onChanged }: { node: SergioNode; onChanged: () => void }) {
  const [text, setText] = useState(node.memory);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (!dirty) setText(node.memory);
  }, [node.memory, dirty]);
  return (
    <div className="node-memory">
      <p className="node-hint">
        Lo que {node.name} recuerda de usted y de su trabajo. Lo escribe solo; usted puede leerlo, corregirlo o borrarlo.
      </p>
      <textarea className="paper-input" rows={14} value={text} onChange={(e) => (setText(e.target.value), setDirty(true))} placeholder="Todavía no recuerda nada." />
      <div className="node-row-end">
        <button
          type="button"
          className="paper-button"
          disabled={!dirty}
          onClick={async () => {
            await nodesApi.setMemory(node.id, text);
            setDirty(false);
            toast.success('Memoria guardada.');
            onChanged();
          }}
        >
          Guardar
        </button>
      </div>
    </div>
  );
}
