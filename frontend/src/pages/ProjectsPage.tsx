// Projects: chats that share standing instructions and files, like the
// projects of the big chat apps (owner, 29 Oct 2026: «no veo dónde creas
// proyectos»). Server: /v1/proyectos (proyectos.py), kept on this computer.

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { FileText, FolderPlus, MessageSquarePlus, Paperclip, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { PaperPage } from '../components/Paper/PaperPage';
import {
  addProjectFile,
  createProject,
  deleteProject,
  listProjects,
  removeProjectFile,
  updateProject,
  type Project,
} from '../lib/projects';
import { useAppStore } from '../lib/store';
import './projects.css';

const fail = (e: unknown) => toast.error(e instanceof Error ? e.message : 'No se pudo.');

function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [making, setMaking] = useState(false);
  const [name, setName] = useState('');
  const [rules, setRules] = useState('');

  const reload = () => void listProjects().then(setProjects).catch((e) => (fail(e), setProjects([])));
  useEffect(reload, []);

  const current = projects?.find((p) => p.id === open) ?? null;

  return (
    <PaperPage title="Proyectos">
      {current ? (
        <ProjectDetail
          project={current}
          onBack={() => setOpen(null)}
          onChange={(p) => setProjects((all) => (all ?? []).map((x) => (x.id === p.id ? p : x)))}
          onGone={() => (setOpen(null), reload())}
        />
      ) : (
        <>
          {making ? (
            <form
              className="pj-new"
              onSubmit={(e) => {
                e.preventDefault();
                void createProject(name.trim(), rules)
                  .then((p) => {
                    setMaking(false);
                    setName('');
                    setRules('');
                    setProjects((all) => [p, ...(all ?? [])]);
                    setOpen(p.id);
                  })
                  .catch(fail);
              }}
            >
              <label className="pj-label">
                Nombre
                <input className="pj-input" value={name} onChange={(e) => setName(e.target.value)} autoFocus maxLength={80} />
              </label>
              <label className="pj-label">
                Instrucciones para todos sus chats
                <textarea
                  className="pj-input pj-area"
                  value={rules}
                  onChange={(e) => setRules(e.target.value)}
                  placeholder="Por ejemplo: «Es mi tienda de café. Responde con precios en dólares y tono cercano.»"
                />
              </label>
              <div className="pj-row">
                <button type="submit" className="pj-btn" data-primary disabled={!name.trim()}>
                  Crear proyecto
                </button>
                <button type="button" className="pj-btn" onClick={() => setMaking(false)}>
                  Cancelar
                </button>
              </div>
            </form>
          ) : (
            <button type="button" className="pj-btn pj-make" data-primary onClick={() => setMaking(true)}>
              <FolderPlus size={16} aria-hidden /> Nuevo proyecto
            </button>
          )}
          {!Array.isArray(projects) ? null : projects.length === 0 && !making ? (
            <p className="pj-empty">Un proyecto junta chats con las mismas instrucciones y archivos. Cree el primero.</p>
          ) : (
            <ul className="pj-list">
              {projects.map((p) => (
                <li key={p.id}>
                  <button type="button" className="pj-item" onClick={() => setOpen(p.id)}>
                    <b>{p.nombre}</b>
                    <span>
                      {p.archivos.length} archivo{p.archivos.length === 1 ? '' : 's'}
                      {p.instrucciones ? ' · con instrucciones' : ''}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </PaperPage>
  );
}

function ProjectDetail({
  project,
  onBack,
  onChange,
  onGone,
}: {
  project: Project;
  onBack: () => void;
  onChange: (p: Project) => void;
  onGone: () => void;
}) {
  const navigate = useNavigate();
  const [rules, setRules] = useState(project.instrucciones);
  const fileRef = useRef<HTMLInputElement>(null);
  const conversations = useAppStore((s) => s.conversations);
  const createConversation = useAppStore((s) => s.createConversation);
  const selectConversation = useAppStore((s) => s.selectConversation);
  const chats = conversations.filter((c) => c.projectId === project.id);

  const newChat = () => {
    createConversation(undefined, 'texto', project.id);
    navigate('/chat');
  };

  return (
    <div className="pj-detail">
      <button type="button" className="pj-back" onClick={onBack}>
        ‹ Proyectos
      </button>
      <h2 className="pj-h2">{project.nombre}</h2>
      <button type="button" className="pj-btn" data-primary onClick={newChat}>
        <MessageSquarePlus size={16} aria-hidden /> Nuevo chat en este proyecto
      </button>

      <section className="pj-section">
        <h3>Instrucciones</h3>
        <textarea className="pj-input pj-area" value={rules} onChange={(e) => setRules(e.target.value)} />
        {rules !== project.instrucciones && (
          <button type="button" className="pj-btn" onClick={() => void updateProject(project.id, { instrucciones: rules }).then(onChange).catch(fail)}>
            Guardar instrucciones
          </button>
        )}
      </section>

      <section className="pj-section">
        <h3>Archivos</h3>
        <ul className="pj-files">
          {project.archivos.map((f) => (
            <li key={f.nombre}>
              <FileText size={15} aria-hidden />
              <span className="pj-grow">{f.nombre}</span>
              <small>{size(f.bytes)}</small>
              <button type="button" className="pj-icon" aria-label={`Quitar ${f.nombre}`} onClick={() => void removeProjectFile(project.id, f.nombre).then(onChange).catch(fail)}>
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
        <input
          ref={fileRef}
          type="file"
          hidden
          multiple
          onChange={async (e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = '';
            for (const f of files) {
              try {
                onChange(await addProjectFile(project.id, f));
              } catch (err) {
                fail(err);
              }
            }
          }}
        />
        <button type="button" className="pj-btn" onClick={() => fileRef.current?.click()}>
          <Paperclip size={15} aria-hidden /> Añadir archivos
        </button>
      </section>

      <section className="pj-section">
        <h3>Chats</h3>
        {chats.length === 0 ? (
          <p className="pj-empty">Aún no hay chats en este proyecto.</p>
        ) : (
          <ul className="pj-list">
            {chats.map((c) => (
              <li key={c.id}>
                <button type="button" className="pj-item" onClick={() => (selectConversation(c.id), navigate('/chat'))}>
                  <b>{c.title}</b>
                  <span>{new Date(c.updatedAt).toLocaleDateString('es')}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <button
        type="button"
        className="pj-btn pj-danger"
        onClick={() => {
          if (window.confirm(`¿Mover «${project.nombre}» a la papelera? Sus chats se quedan.`)) {
            void deleteProject(project.id).then(onGone).catch(fail);
          }
        }}
      >
        <Trash2 size={15} aria-hidden /> Mover a la papelera
      </button>
    </div>
  );
}
