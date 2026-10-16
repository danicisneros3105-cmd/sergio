// Creator → Código: an editor like VS Code / Cursor (Monaco, the editor
// inside VS Code). Files live in the owner's projects folder; Ctrl+S saves,
// "Ejecutar" runs Python or Node with bounded time and memory, and "Pedir a
// Sergio" proposes a whole new file that is shown as a diff to accept or
// discard: nothing changes on disk until the owner says so.

import { useCallback, useEffect, useRef, useState } from 'react';
import * as monaco from 'monaco-editor/editor';
import EditorWorker from 'monaco-editor/editor/editor.worker?worker';
import 'monaco-editor/languages/definitions/python/register';
import 'monaco-editor/languages/definitions/javascript/register';
import 'monaco-editor/languages/definitions/typescript/register';
import 'monaco-editor/languages/definitions/html/register';
import 'monaco-editor/languages/definitions/css/register';
import 'monaco-editor/languages/definitions/markdown/register';
import 'monaco-editor/languages/definitions/shell/register';
import 'monaco-editor/languages/definitions/yaml/register';
import { Check, FilePlus2, FileCode2, Play, Save, Sparkles, X } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { elapsedNote, useElapsed } from './useElapsed';

(self as unknown as { MonacoEnvironment: monaco.Environment }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};

const LANGUAGE: Record<string, string> = {
  py: 'python',
  js: 'javascript',
  mjs: 'javascript',
  jsx: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  html: 'html',
  css: 'css',
  json: 'javascript', // highlighted as JS (no JSON service loaded)
  md: 'markdown',
  sh: 'shell',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'ini',
  txt: 'plaintext',
};
export const languageOf = (path: string) => LANGUAGE[path.split('.').pop()?.toLowerCase() ?? ''] ?? 'plaintext';
const runnable = (path: string) => /\.(py|js|mjs)$/i.test(path);

interface RunResult {
  stdout: string;
  stderr: string;
  code: number | null;
  timed_out: boolean;
  ms: number;
}

const dark = () => document.documentElement.classList.contains('dark') || (!document.documentElement.classList.contains('light') && matchMedia('(prefers-color-scheme: dark)').matches);

export function CodeStudio() {
  const host = useRef<HTMLDivElement>(null);
  const diffHost = useRef<HTMLDivElement>(null);
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const [files, setFiles] = useState<Array<{ path: string; size: number }>>([]);
  const [path, setPath] = useState('');
  const [saved, setSaved] = useState('');
  const [dirty, setDirty] = useState(false);
  const [run, setRun] = useState<RunResult | null>(null);
  const [busy, setBusy] = useState('');
  const elapsed = useElapsed(busy);
  const [instruction, setInstruction] = useState('');
  const [proposal, setProposal] = useState<string | null>(null);
  const pathRef = useRef(path);
  pathRef.current = path;

  const loadFiles = useCallback(async () => {
    const res = await apiFetch('/v1/creator/code/files');
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || 'No pude leer sus proyectos.');
    setFiles(body.files);
    return body.files as Array<{ path: string }>;
  }, []);

  const open = useCallback(async (p: string) => {
    const res = await apiFetch(`/v1/creator/code/file?path=${encodeURIComponent(p)}`);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) return toast.error(body.detail || 'No pude abrir el archivo.');
    const ed = editor.current;
    if (!ed) return;
    const old = ed.getModel();
    ed.setModel(monaco.editor.createModel(body.content, languageOf(p)));
    old?.dispose();
    setPath(p);
    setSaved(body.content);
    setDirty(false);
    setRun(null);
    setProposal(null);
  }, []);

  const save = useCallback(async () => {
    const ed = editor.current;
    const p = pathRef.current;
    if (!ed || !p) return false;
    const content = ed.getValue();
    const res = await apiFetch('/v1/creator/code/file', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: p, content }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      toast.error(body.detail || 'No pude guardar.');
      return false;
    }
    setSaved(content);
    setDirty(false);
    return true;
  }, []);

  // -- the editor (created once) --------------------------------------------------
  useEffect(() => {
    if (!host.current) return;
    const ed = monaco.editor.create(host.current, {
      value: '',
      language: 'plaintext',
      theme: dark() ? 'vs-dark' : 'vs',
      automaticLayout: true,
      fontSize: 14,
      fontFamily: "'SF Mono', 'JetBrains Mono', 'Cascadia Code', Consolas, monospace",
      minimap: { enabled: true },
      smoothScrolling: true,
      cursorSmoothCaretAnimation: 'on',
      tabSize: 4,
      padding: { top: 12 },
    });
    editor.current = ed;
    ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      void save().then((ok) => ok && toast.success('Guardado.'));
    });
    const sub = ed.onDidChangeModelContent(() => setDirty(true));
    loadFiles()
      .then((list) => list[0] && open(list[0].path))
      .catch(() => undefined); // no server yet: the list just stays empty
    return () => {
      sub.dispose();
      ed.getModel()?.dispose();
      ed.dispose();
      editor.current = null;
    };
  }, [loadFiles, open, save]);

  useEffect(() => {
    if (saved !== undefined) setDirty((editor.current?.getValue() ?? '') !== saved);
  }, [saved]);

  // -- the proposal as a diff ------------------------------------------------------
  useEffect(() => {
    if (proposal === null || !diffHost.current || !editor.current) return;
    const lang = languageOf(pathRef.current);
    const original = monaco.editor.createModel(editor.current.getValue(), lang);
    const modified = monaco.editor.createModel(proposal, lang);
    const diff = monaco.editor.createDiffEditor(diffHost.current, {
      theme: dark() ? 'vs-dark' : 'vs',
      automaticLayout: true,
      readOnly: true,
      renderSideBySide: (diffHost.current.clientWidth || 0) > 760,
      fontSize: 13,
    });
    diff.setModel({ original, modified });
    return () => {
      diff.dispose();
      original.dispose();
      modified.dispose();
    };
  }, [proposal]);

  const execute = async () => {
    if (!path) return;
    if (dirty && !(await save())) return;
    setBusy('Ejecutando…');
    try {
      const res = await apiFetch('/v1/creator/code/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'No pude ejecutarlo.');
      setRun(body as RunResult);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'No pude ejecutarlo.');
    } finally {
      setBusy('');
    }
  };

  const askSergio = async (text = instruction) => {
    const ed = editor.current;
    if (!ed || !path || text.trim().length < 3) return;
    setBusy('Sergio está escribiendo el cambio…');
    try {
      const res = await apiFetch('/v1/creator/code/ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, content: ed.getValue(), instruction: text.trim() }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'Sergio no pudo proponer el cambio.');
      if (body.content === ed.getValue()) toast.message('Sergio no vio nada que cambiar.');
      else setProposal(body.content);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Sergio no pudo proponer el cambio.');
    } finally {
      setBusy('');
    }
  };

  const accept = () => {
    const ed = editor.current;
    if (!ed || proposal === null) return;
    // One undoable edit (Ctrl+Z brings the old file back).
    ed.pushUndoStop();
    ed.executeEdits('sergio', [{ range: ed.getModel()!.getFullModelRange(), text: proposal }]);
    ed.pushUndoStop();
    setProposal(null);
    setInstruction('');
    toast.success('Cambio aplicado. Ctrl+S para guardar, Ctrl+Z para deshacer.');
  };

  const newFile = async () => {
    const name = window.prompt('Nombre del archivo (por ejemplo: juego/main.py)')?.trim();
    if (!name) return;
    const res = await apiFetch('/v1/creator/code/file', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: name, content: '' }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) return toast.error(body.detail || 'No pude crearlo.');
    await loadFiles();
    await open(body.path);
  };

  const failed = run && (run.code !== 0 || run.timed_out);

  return (
    <div className="studio-code">
      <aside className="studio-side studio-files" aria-label="Archivos">
        <section className="studio-panel">
          <h3>
            Proyectos
            <button type="button" className="mac-icon-btn" aria-label="Nuevo archivo" title="Nuevo archivo" onClick={() => void newFile()}>
              <FilePlus2 size={15} />
            </button>
          </h3>
          <ul className="studio-outliner">
            {files.map((f) => (
              <li key={f.path} aria-selected={f.path === path}>
                <button type="button" onClick={() => void open(f.path)}>
                  <FileCode2 size={14} />
                  {f.path}
                </button>
              </li>
            ))}
          </ul>
        </section>
      </aside>

      <div className="studio-view">
        <div className="code-bar">
          <span className="code-path">
            {path || 'Sin archivo'}
            {dirty && <i title="Sin guardar" aria-label="Sin guardar" />}
          </span>
          <button type="button" className="paper-button" data-variant="quiet" onClick={() => void save().then((ok) => ok && toast.success('Guardado.'))} disabled={!path || !dirty}>
            <Save size={15} /> Guardar
          </button>
          <button type="button" className="paper-button" onClick={() => void execute()} disabled={!path || !runnable(path) || !!busy}>
            <Play size={15} /> Ejecutar
          </button>
        </div>
        <div className="code-editor" ref={host} data-testid="code-editor" hidden={proposal !== null} />
        {proposal !== null && (
          <div className="code-proposal">
            <div className="code-proposal-bar">
              <b>Propuesta de Sergio</b>
              <span>Izquierda: ahora · Derecha: propuesta</span>
              <button type="button" className="paper-button" onClick={accept}>
                <Check size={15} /> Aceptar
              </button>
              <button type="button" className="paper-button" data-variant="quiet" onClick={() => setProposal(null)}>
                <X size={15} /> Descartar
              </button>
            </div>
            <div className="code-diff" ref={diffHost} />
          </div>
        )}
        {run && (
          <div className="code-output" data-failed={failed || undefined} role="log" aria-label="Salida">
            <div className="code-output-head">
              <b>{run.timed_out ? 'Tiempo agotado' : run.code === 0 ? 'Terminó bien' : `Terminó con error (${run.code})`}</b>
              <span>{run.ms} ms</span>
              {failed && (
                <button type="button" className="paper-button" data-variant="quiet" disabled={!!busy} onClick={() => void askSergio(`Arregla este error:\n${(run.stderr || run.stdout).slice(-1500)}`)}>
                  <Sparkles size={14} /> Arreglar con Sergio
                </button>
              )}
              <button type="button" className="mac-icon-btn" aria-label="Cerrar salida" onClick={() => setRun(null)}>
                <X size={14} />
              </button>
            </div>
            <pre>
              {run.stdout}
              {run.stderr && <span className="code-stderr">{run.stderr}</span>}
            </pre>
          </div>
        )}
        <form
          className="studio-ask"
          onSubmit={(e) => {
            e.preventDefault();
            void askSergio();
          }}
        >
          <input
            className="paper-input"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            disabled={!!busy || !path}
            aria-label="Pedir un cambio a Sergio"
            placeholder={busy ? busy + elapsedNote(elapsed) : 'Pídale un cambio: «añade una función que cuente palabras», «comenta el código», «hazlo más rápido»'}
          />
          <button type="submit" className="paper-button" disabled={!!busy || instruction.trim().length < 3 || !path}>
            <Sparkles size={15} /> Proponer
          </button>
        </form>
      </div>
    </div>
  );
}

export default CodeStudio;
