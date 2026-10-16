import { beforeEach, describe, expect, it } from 'vitest';
import { memoryDB } from './db';
import type { Page } from './model';
import { configureWorkspace, flushWorkspace, saveMedia, useWorkspace, type Remote } from './store';

function fakeServer() {
  const pages = new Map<string, Page>();
  const calls: string[] = [];
  const remote: Remote = {
    async list() {
      return [...pages.values()].map((p) => ({ id: p.id, rev: p.rev, updatedAt: p.updatedAt, archived: p.archived }));
    },
    async get(id) {
      return pages.has(id) ? structuredClone(pages.get(id)!) : null;
    },
    async put(page, baseRev) {
      calls.push(`put ${page.id} ${baseRev}`);
      const current = pages.get(page.id);
      if (current && current.rev !== baseRev) {
        const copy = { ...structuredClone(page), id: `p_copy${pages.size}xx`, title: `${page.title} (copia en conflicto)`, rev: 1 };
        pages.set(copy.id, copy);
        return { ok: false as const, page: structuredClone(current), copy: copy.id };
      }
      const saved = { ...structuredClone(page), rev: (current?.rev || 0) + 1 };
      pages.set(page.id, saved);
      return { ok: true as const, page: structuredClone(saved) };
    },
    async del(id) {
      calls.push(`del ${id}`);
      pages.delete(id);
    },
    async upload(_blob, name) {
      calls.push(`upload ${name}`);
      return { file: 'f_server0001.webm', name, mime: 'audio/webm' };
    },
  };
  return { pages, remote, calls };
}

describe('workspace store (local-first)', () => {
  let server: ReturnType<typeof fakeServer>;
  let db: ReturnType<typeof memoryDB>;

  beforeEach(async () => {
    server = fakeServer();
    db = memoryDB();
    configureWorkspace({ db, remote: server.remote });
    useWorkspace.setState({ pages: {}, dirty: [], deleted: [], tabs: [], active: null, split: null, vault: null, trash: null, sync: 'idle' });
    await useWorkspace.getState().load();
  });

  it('creates from a template, saves locally at once and syncs later', async () => {
    const page = useWorkspace.getState().create({ template: 'meeting' });
    expect(page.blocks[0].type).toBe('callout');
    expect(useWorkspace.getState().active).toBe(page.id);
    await flushWorkspace();
    expect((await db.get<Page>('pages', page.id))?.title).toBe(page.title);
    await useWorkspace.getState().syncNow();
    expect(server.pages.get(page.id)?.rev).toBe(1);
    expect(useWorkspace.getState().dirty).toEqual([]);
    expect(useWorkspace.getState().pages[page.id].rev).toBe(1);
  });

  it('works offline, then catches up; pulls what other devices changed', async () => {
    const page = useWorkspace.getState().create({ title: 'Lista' });
    Object.defineProperty(globalThis.navigator, 'onLine', { value: false, configurable: true });
    await useWorkspace.getState().syncNow();
    expect(useWorkspace.getState().sync).toBe('offline');
    expect(server.pages.size).toBe(0);
    Object.defineProperty(globalThis.navigator, 'onLine', { value: true, configurable: true });
    await useWorkspace.getState().syncNow();
    expect(server.pages.get(page.id)?.title).toBe('Lista');
    const other = { ...structuredClone(server.pages.get(page.id)!), title: 'Lista (desde el móvil)', rev: 5 };
    server.pages.set(page.id, other);
    await useWorkspace.getState().syncNow();
    expect(useWorkspace.getState().pages[page.id].title).toBe('Lista (desde el móvil)');
  });

  it('a conflict keeps both versions', async () => {
    const page = useWorkspace.getState().create({ title: 'Plan' });
    await useWorkspace.getState().syncNow();
    server.pages.set(page.id, { ...server.pages.get(page.id)!, title: 'Plan (otro equipo)', rev: 2 });
    useWorkspace.getState().update(page.id, (p) => ({ ...p, title: 'Plan (este equipo)' }));
    await useWorkspace.getState().syncNow();
    const titles = Object.values(useWorkspace.getState().pages).map((p) => p.title).sort();
    expect(titles).toEqual(['Plan (este equipo) (copia en conflicto)', 'Plan (otro equipo)']);
  });

  it('tabs, split view, delete and the inbox', async () => {
    const a = useWorkspace.getState().create({ title: 'A' });
    const b = useWorkspace.getState().create({ title: 'B' });
    useWorkspace.getState().open(a.id, 'split');
    expect(useWorkspace.getState().split).toBe(a.id);
    expect(useWorkspace.getState().active).toBe(b.id);
    useWorkspace.getState().setRatio(0.95);
    expect(useWorkspace.getState().ratio).toBe(0.8);
    useWorkspace.getState().close(b.id);
    expect(useWorkspace.getState().active).toBe(a.id);
    const inbox = useWorkspace.getState().capture({ text: 'comprar leche' });
    expect(inbox.title).toBe('Bandeja de entrada');
    expect(inbox.blocks.some((x) => x.text.startsWith('comprar leche'))).toBe(true);
    await useWorkspace.getState().syncNow();
    useWorkspace.getState().remove(a.id);
    await useWorkspace.getState().syncNow();
    expect(server.calls).toContain(`del ${a.id}`);
    expect(server.pages.has(a.id)).toBe(false);
  });

  it('the vault keeps archived pages out of the way and brings them back', async () => {
    const page = useWorkspace.getState().create({ title: 'Viejo' });
    await useWorkspace.getState().archive(page.id);
    expect(useWorkspace.getState().pages[page.id]).toBeUndefined();
    await useWorkspace.getState().loadVault();
    expect(useWorkspace.getState().vault?.map((p) => p.title)).toEqual(['Viejo']);
    await useWorkspace.getState().restore(page.id);
    expect(useWorkspace.getState().pages[page.id].archived).toBe(false);
  });

  it('reopens where it was left (tabs, layout) from the local copy', async () => {
    const page = useWorkspace.getState().create({ title: 'Persistente' });
    useWorkspace.getState().setLayout({ density: 'compact', fontSize: 14 });
    await flushWorkspace();
    useWorkspace.setState({ pages: {}, tabs: [], active: null });
    await useWorkspace.getState().load();
    expect(useWorkspace.getState().active).toBe(page.id);
    expect(useWorkspace.getState().layout.density).toBe('compact');
  });

  it('a voice note recorded offline is kept here and uploaded by the next sync', async () => {
    Object.defineProperty(globalThis.navigator, 'onLine', { value: false, configurable: true });
    const media = await saveMedia(new Blob(['ogg'], { type: 'audio/webm' }), 'nota.webm');
    expect(media.file.startsWith('local:')).toBe(true);
    const page = useWorkspace.getState().capture({ kind: 'audio', media });
    Object.defineProperty(globalThis.navigator, 'onLine', { value: true, configurable: true });
    await useWorkspace.getState().syncNow();
    expect(server.calls).toContain('upload nota.webm');
    const stored = server.pages.get(page.id)!;
    expect(stored.blocks.some((b) => b.media?.file === 'f_server0001.webm')).toBe(true);
  });

  it('deleting moves a page to the trash; it can come back or be gone for good', async () => {
    const page = useWorkspace.getState().create({ title: 'Borrador' });
    await useWorkspace.getState().syncNow();
    useWorkspace.getState().remove(page.id);
    await useWorkspace.getState().syncNow();
    expect(server.pages.has(page.id)).toBe(false);
    await useWorkspace.getState().loadTrash();
    expect(useWorkspace.getState().trash!.map((p) => p.title)).toEqual(['Borrador']);
    await useWorkspace.getState().loadVault();
    expect(useWorkspace.getState().vault).toEqual([]); // the trash is not the vault
    await useWorkspace.getState().restoreTrash(page.id);
    expect(useWorkspace.getState().pages[page.id].title).toBe('Borrador');
    await useWorkspace.getState().syncNow();
    expect(server.pages.get(page.id)?.title).toBe('Borrador');
    useWorkspace.getState().remove(page.id);
    await useWorkspace.getState().loadTrash();
    await useWorkspace.getState().purge(page.id);
    expect(useWorkspace.getState().trash).toEqual([]);
    expect(await db.get('vault', page.id)).toBeUndefined();
  });

  it('empties trash older than 30 days by itself', async () => {
    const page = useWorkspace.getState().create({ title: 'Viejo' });
    useWorkspace.getState().remove(page.id);
    await useWorkspace.getState().loadTrash(Date.now() + 31 * 86_400_000);
    expect(useWorkspace.getState().trash).toEqual([]);
  });

  it('hides and shows sidebar sections', () => {
    useWorkspace.getState().toggleSection('recents');
    expect(useWorkspace.getState().layout.hidden).toEqual(['recents']);
    useWorkspace.getState().toggleSection('recents', true);
    expect(useWorkspace.getState().layout.hidden).toEqual([]);
  });
});
