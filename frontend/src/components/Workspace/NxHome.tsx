import { Clock, LayoutTemplate } from 'lucide-react';
import { NxIcon } from './NxIcon';
import { useWorkspace } from '../../lib/workspace/store';
import { TEMPLATES } from '../../lib/workspace/model';
import { coverCss, greeting } from '../../lib/workspace/notion';

const TEMPLATE_ICON: Record<string, string> = { blank: 'i:file', meeting: 'i:users', project: 'i:rocket', journal: 'i:book', focus: 'i:clock' };

export function NxHome({ onPick, templatesOnly = false }: { onPick: (id: string) => void; templatesOnly?: boolean }) {
  const pages = useWorkspace((s) => s.pages);
  const create = useWorkspace((s) => s.create);
  const recent = Object.values(pages)
    .filter((p) => !p.archived)
    .sort((a, b) => (b.openedAt || b.updatedAt) - (a.openedAt || a.updatedAt))
    .slice(0, 12);

  return (
    <div className="nx-home">
      {!templatesOnly && <h1 className="nx-greeting">{greeting()}</h1>}

      {!templatesOnly && (
        <section className="nx-home-section">
          <h2 className="nx-home-label">
            <Clock size={14} /> Visitados recientemente
          </h2>
          <div className="nx-cards">
            {recent.map((p) => (
              <button key={p.id} type="button" className="nx-card" onClick={() => onPick(p.id)}>
                <span className="nx-card-cover" style={{ background: coverCss(p.cover) || 'var(--nx-hover)' }} />
                <span className="nx-card-icon"><NxIcon icon={p.icon} size={22} /></span>
                <span className="nx-card-title">{p.title || 'Sin título'}</span>
              </button>
            ))}
            <button type="button" className="nx-card nx-card-new" onClick={() => onPick(create({ open: false }).id)}>
              <span className="nx-card-cover" />
              <span className="nx-card-title">+ Página nueva</span>
            </button>
          </div>
        </section>
      )}

      <section className="nx-home-section">
        <h2 className="nx-home-label">
          <LayoutTemplate size={14} /> Plantillas
        </h2>
        <div className="nx-cards">
          {TEMPLATES.map((t) => (
            <button key={t.key} type="button" className="nx-card" onClick={() => onPick(create({ template: t.key, open: false }).id)}>
              <span className="nx-card-cover" style={{ background: 'var(--nx-hover)' }} />
              <span className="nx-card-icon"><NxIcon icon={TEMPLATE_ICON[t.key]} size={22} /></span>
              <span className="nx-card-title">{t.name}</span>
              <span className="nx-card-hint">{t.description}</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
