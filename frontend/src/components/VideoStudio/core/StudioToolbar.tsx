import { Undo2, Redo2, Save, FolderOpen, Settings, Download, Cpu } from 'lucide-react';

interface Props {
  studio: any;
}

export function StudioToolbar({ studio }: Props) {
  return (
    <div className="studio-toolbar">
      <span className="logo-mark">SERGIO</span>
      <input
        className="project-name"
        value={studio.projectName}
        onChange={e => studio.setProjectName(e.target.value)}
      />
      <div className="spacer" />
      <button className="tb-btn"><Undo2 size={13} /></button>
      <button className="tb-btn"><Redo2 size={13} /></button>
      <button className="tb-btn"><FolderOpen size={13} /> Abrir</button>
      <button className="tb-btn"><Save size={13} /> Guardar</button>
      <button className="tb-btn"><Settings size={13} /> Ajustes</button>
      <button className="tb-btn primary" onClick={() => studio.setShowExport?.(true)}>
        <Download size={13} /> Exportar
      </button>
    </div>
  );
}
