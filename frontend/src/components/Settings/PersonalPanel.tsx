// «Tú» in Configuración: how Sergio addresses this person, their language
// and country, the line above the chat, and which skills Sergio may use.
// Everything is saved on the server (`/v1/personal/*`), so the desktop app
// and every window agree.

import { useEffect, useState } from 'react';
import { apiFetch } from '../../lib/api';
import {
  ADDRESS_OPTIONS,
  TONE_OPTIONS,
  savePersonal,
  usePersonal,
  type Personal,
} from '../../lib/personal';
import { greetingLine } from '../../lib/greetings';

const LANGUAGES: { value: string; label: string }[] = [
  { value: 'auto', label: 'El del navegador' },
  { value: 'es', label: 'Español' },
  { value: 'en', label: 'English' },
  { value: 'pt', label: 'Português' },
  { value: 'fr', label: 'Français' },
  { value: 'de', label: 'Deutsch' },
  { value: 'it', label: 'Italiano' },
];

const field = {
  background: 'var(--color-bg-secondary)',
  color: 'var(--color-text)',
  border: '1px solid var(--color-border)',
} as const;

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label
      className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4 py-3"
      style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
    >
      <span className="text-sm" style={{ color: 'var(--color-text)' }}>{label}</span>
      {children}
    </label>
  );
}

export function PersonalPanel() {
  const personal = usePersonal();
  const [draft, setDraft] = useState<Personal>(personal);
  const [problem, setProblem] = useState('');
  useEffect(() => setDraft(personal), [personal]);

  const save = (changes: Partial<Personal>) => {
    setDraft((d) => ({ ...d, ...changes }));
    setProblem('');
    savePersonal(changes).catch((e: Error) => setProblem(e.message || 'No se pudo guardar.'));
  };

  return (
    <div>
      <p className="personal-preview" aria-live="polite">{greetingLine(draft)}</p>
      <Row label="Su nombre">
        <input
          className="text-sm px-3 py-1.5 rounded-lg outline-none"
          style={field}
          value={draft.nombre}
          maxLength={40}
          placeholder="Opcional"
          onChange={(e) => setDraft({ ...draft, nombre: e.target.value })}
          onBlur={() => draft.nombre !== personal.nombre && save({ nombre: draft.nombre })}
        />
      </Row>
      <Row label="Cómo le llamo">
        <select className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer" style={field}
          value={draft.trato} onChange={(e) => save({ trato: e.target.value as Personal['trato'] })}>
          {ADDRESS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </Row>
      <Row label="Idioma">
        <select className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer" style={field}
          value={draft.idioma} onChange={(e) => save({ idioma: e.target.value })}>
          {LANGUAGES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </Row>
      <Row label="País">
        <input
          className="text-sm px-3 py-1.5 rounded-lg outline-none"
          style={field}
          value={draft.pais}
          maxLength={40}
          placeholder="Ej.: Ecuador"
          onChange={(e) => setDraft({ ...draft, pais: e.target.value })}
          onBlur={() => draft.pais !== personal.pais && save({ pais: draft.pais })}
        />
      </Row>
      <Row label="Saludo">
        <select className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer" style={field}
          value={draft.tono_saludo} onChange={(e) => save({ tono_saludo: e.target.value as Personal['tono_saludo'] })}>
          {TONE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </Row>
      <details className="py-3">
        <summary className="text-sm cursor-pointer" style={{ color: 'var(--color-text-secondary)' }}>Saludos propios</summary>
        <div className="text-xs my-2" style={{ color: 'var(--color-text-tertiary)' }}>Uno por línea; {'{nombre}'} pone su nombre.</div>
        <textarea
          className="w-full text-sm px-3 py-2 rounded-lg outline-none"
          style={{ ...field, minHeight: 76 }}
          value={draft.saludos_propios.join('\n')}
          placeholder={'¡{nombre} ha vuelto!\nEl micrófono es tuyo, {nombre}.'}
          onChange={(e) => setDraft({ ...draft, saludos_propios: e.target.value.split('\n') })}
          onBlur={() => save({ saludos_propios: draft.saludos_propios.map((s) => s.trim()).filter(Boolean) })}
        />
      </details>
      {problem && <p className="text-xs" style={{ color: 'var(--color-error)' }}>{problem}</p>}
    </div>
  );
}

interface Skill {
  clave: string;
  nombre: string;
  hace: string;
  activa: boolean;
}

export function SkillsPanel() {
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [problem, setProblem] = useState('');
  useEffect(() => {
    apiFetch('/v1/personal/habilidades')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`Error ${r.status}`))))
      .then((d) => setSkills(d.habilidades ?? []))
      .catch(() => setProblem('Sergio no responde ahora.'));
  }, []);

  const flip = async (s: Skill) => {
    setSkills((all) => all?.map((x) => (x.clave === s.clave ? { ...x, activa: !s.activa } : x)) ?? null);
    const r = await apiFetch(`/v1/personal/habilidades/${encodeURIComponent(s.clave)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ activa: !s.activa }),
    });
    if (r.ok) setSkills((await r.json()).habilidades ?? []);
    else setProblem('No se pudo cambiar.');
  };

  if (problem && !skills) return <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{problem}</p>;
  if (!skills) return null;
  return (
    <div>
      <p className="text-xs mb-2" style={{ color: 'var(--color-text-tertiary)' }}>Lo que apague, Sergio no lo usa.</p>
      {skills.map((s) => (
        <div key={s.clave} className="flex items-center justify-between gap-4 py-2.5"
          style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
          <div className="min-w-0">
            <div className="text-sm" style={{ color: 'var(--color-text)' }}>{s.nombre}</div>
            {s.hace && <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{s.hace}</div>}
          </div>
          <button type="button" role="switch" aria-checked={s.activa} aria-label={s.nombre} className="ext-switch"
            onClick={() => void flip(s)} />
        </div>
      ))}
      {problem && <p className="text-xs mt-2" style={{ color: 'var(--color-error)' }}>{problem}</p>}
    </div>
  );
}
