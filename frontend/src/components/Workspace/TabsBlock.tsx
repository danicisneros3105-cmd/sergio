// The tabs block (Notion's «/tabs»): named panes, one visible at a time.
// Each pane holds free text with the page's inline formatting.

import { useEffect, useRef, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { newId, type TabPane } from '../../lib/workspace/model';

export function tabsText(tabs: TabPane[]): string {
  return tabs.map((t) => `${t.name}\n${t.text}`.trim()).join('\n\n');
}

export function TabsBlock({
  tabs,
  active,
  readOnly,
  onChange,
}: {
  tabs: TabPane[];
  active?: string;
  readOnly?: boolean;
  onChange: (tabs: TabPane[], active: string) => void;
}) {
  const current = tabs.find((t) => t.id === active) || tabs[0];
  const [renaming, setRenaming] = useState<string | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [current?.text, current?.id]);

  if (!current) return null;
  const set = (id: string, change: Partial<TabPane>) => onChange(tabs.map((t) => (t.id === id ? { ...t, ...change } : t)), current.id);

  return (
    <div className="nx-tabsblock">
      <div className="nx-tabsblock-bar" role="tablist">
        {tabs.map((t) =>
          renaming === t.id ? (
            <input
              key={t.id}
              className="nx-tabsblock-name"
              autoFocus
              defaultValue={t.name}
              aria-label="Nombre de la pestaña"
              onBlur={(e) => {
                set(t.id, { name: e.target.value.trim() || t.name });
                setRenaming(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === 'Escape') (e.target as HTMLInputElement).blur();
              }}
            />
          ) : (
            <span key={t.id} className="nx-tabsblock-tab" data-active={t.id === current.id || undefined}>
              <button
                type="button"
                role="tab"
                aria-selected={t.id === current.id}
                title={readOnly ? undefined : 'Doble clic para cambiar el nombre'}
                onClick={() => onChange(tabs, t.id)}
                onDoubleClick={() => !readOnly && setRenaming(t.id)}
              >
                {t.name || 'Sin nombre'}
              </button>
              {!readOnly && tabs.length > 1 && t.id === current.id && (
                <button
                  type="button"
                  className="nx-tabsblock-x"
                  aria-label={`Quitar la pestaña ${t.name}`}
                  onClick={() => {
                    if (t.text.trim() && !window.confirm(`¿Quitar «${t.name}» y su contenido?`)) return;
                    const rest = tabs.filter((x) => x.id !== t.id);
                    onChange(rest, rest[Math.max(0, tabs.indexOf(t) - 1)].id);
                  }}
                >
                  <X size={12} />
                </button>
              )}
            </span>
          ),
        )}
        {!readOnly && (
          <button
            type="button"
            className="nx-tabsblock-add"
            aria-label="Añadir una pestaña"
            onClick={() => {
              const tab = { id: newId('t'), name: `Pestaña ${tabs.length + 1}`, text: '' };
              onChange([...tabs, tab], tab.id);
              setRenaming(tab.id);
            }}
          >
            <Plus size={14} />
          </button>
        )}
      </div>
      <textarea
        ref={area}
        className="nx-tabsblock-body"
        role="tabpanel"
        rows={2}
        value={current.text}
        readOnly={readOnly}
        placeholder="Escriba aquí el contenido de la pestaña"
        onChange={(e) => set(current.id, { text: e.target.value })}
      />
    </div>
  );
}
