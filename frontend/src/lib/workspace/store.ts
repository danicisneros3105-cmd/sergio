// The Workspace state: local-first. Every edit lands in this device's
// IndexedDB at once (the page never waits for a network), and a quiet sync
// sends it to your Sergio server when there is one; from there the
// encrypted backup takes it to your cloud. Offline, nothing changes for you.

import { create } from 'zustand';
import { apiFetch, authHeaders, getBase } from '../api';
import { stalePages, tidyPage, DEFAULT_RULES, INBOX_TITLE } from './archive';
import { defaultDB, type LocalDB } from './db';
import { block, newPage, TEMPLATES, type Block, type Page } from './model';

export interface Remote {
  list(): Promise<Array<{ id: string; rev: number; updatedAt: number; archived?: boolean }>>;
  get(id: string): Promise<Page | null>;
  put(page: Page, baseRev: number): Promise<{ ok: true; page: Page } | { ok: false; page: Page; copy: string }>;
  del(id: string): Promise<void>;
  upload(blob: Blob, name: string): Promise<{ file: string; name: string; mime: string }>;
}

export const httpRemote: Remote = {
  async list() {
    const r = await apiFetch('/v1/workspace/pages');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return (await r.json()).pages;
  },
  async get(id) {
    const r = await apiFetch(`/v1/workspace/pages/${id}`);
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return (await r.json()).page;
  },
  async put(page, baseRev) {
    const r = await apiFetch(`/v1/workspace/pages/${page.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page, base_rev: baseRev }),
    });
    if (r.status === 409) {
      const body = await r.json();
      return { ok: false as const, page: body.page, copy: body.copy };
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return { ok: true as const, page: (await r.json()).page };
  },
  async del(id) {
    const r = await apiFetch(`/v1/workspace/pages/${id}`, { method: 'DELETE' });
    if (!r.ok && r.status !== 404) throw new Error(`HTTP ${r.status}`);
  },
  async upload(blob, name) {
    const form = new FormData();
    form.append('file', blob, name);
    const r = await apiFetch('/v1/workspace/files', { method: 'POST', body: form });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },
};

const LOCAL = 'local:';

// A voice note or photo: to the server when it answers, else kept on this
// device and uploaded by the next sync.
export async function saveMedia(blob: Blob, name: string): Promise<NonNullable<Block['media']>> {
  try {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) throw new Error('offline');
    const up = await remote.upload(blob, name);
    return { file: up.file, name: up.name || name, mime: up.mime || blob.type };
  } catch {
    const key = `l_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
    await db.put('files', key, blob);
    return { file: `${LOCAL}${key}`, name, mime: blob.type };
  }
}

// An address the <audio>/<img> can use (the server may need the key, so the
// bytes are fetched with it and shown from memory).
export async function mediaUrl(media: NonNullable<Block['media']>): Promise<string> {
  if (media.file.startsWith(LOCAL)) {
    const blob = await db.get<Blob>('files', media.file.slice(LOCAL.length));
    return blob ? URL.createObjectURL(blob) : '';
  }
  const r = await fetch(`${getBase()}/v1/workspace/files/${media.file}`, { headers: authHeaders() });
  if (!r.ok) return '';
  return URL.createObjectURL(await r.blob());
}

async function uploadPending(page: Page): Promise<Page | null> {
  let changed = false;
  const blocks: Block[] = [];
  for (const b of page.blocks) {
    if (b.media?.file.startsWith(LOCAL)) {
      const key = b.media.file.slice(LOCAL.length);
      const blob = await db.get<Blob>('files', key);
      if (blob) {
        const up = await remote.upload(blob, b.media.name);
        await db.del('files', key);
        blocks.push({ ...b, media: { ...b.media, file: up.file } });
        changed = true;
        continue;
      }
    }
    blocks.push(b);
  }
  return changed ? { ...page, blocks } : null;
}

export interface Layout {
  density: 'compact' | 'comfortable';
  fontSize: number; // px
  width: 'narrow' | 'wide' | 'full';
  margin: number; // px, side padding of the page
}

export const DEFAULT_LAYOUT: Layout = { density: 'comfortable', fontSize: 15, width: 'wide', margin: 32 };

interface Meta {
  dirty: string[];
  deleted: string[];
  tabs: string[];
  active: string | null;
  split: string | null;
  ratio: number;
  layout: Layout;
  lastArchive: number;
  lastSync: number;
}

export type SyncState = 'idle' | 'syncing' | 'offline' | 'error';

interface WorkspaceState extends Meta {
  ready: boolean;
  pages: Record<string, Page>;
  vault: Page[] | null; // loaded on demand
  sync: SyncState;
  // Decrypted blocks of sealed pages, in memory only (never stored).
  unlocked: Record<string, Block[]>;
  load: () => Promise<void>;
  create: (opts?: { template?: string; parent?: string | null; title?: string; open?: boolean }) => Page;
  update: (id: string, change: (p: Page) => Page) => void;
  remove: (id: string) => void;
  open: (id: string, where?: 'tab' | 'split') => void;
  close: (id: string) => void;
  setActive: (id: string) => void;
  setRatio: (ratio: number) => void;
  setLayout: (layout: Partial<Layout>) => void;
  archive: (id: string) => Promise<void>;
  restore: (id: string) => Promise<void>;
  loadVault: () => Promise<void>;
  autoArchive: (now?: number) => Promise<{ pages: number; rows: number; todos: number }>;
  capture: (item: { text?: string; media?: Block['media']; kind?: 'audio' | 'image' }) => Page;
  syncNow: () => Promise<void>;
  setUnlocked: (id: string, blocks: Block[] | null) => void;
}

let db: LocalDB = defaultDB();
let remote: Remote = httpRemote;
let saveTimer: ReturnType<typeof setTimeout> | null = null;
let syncTimer: ReturnType<typeof setTimeout> | null = null;
const pendingWrites = new Set<string>();

// Tests swap the database and the server.
export function configureWorkspace(next: { db?: LocalDB; remote?: Remote }): void {
  if (next.db) db = next.db;
  if (next.remote) remote = next.remote;
}

const META_KEY = 'state';

function metaOf(s: WorkspaceState): Meta {
  return {
    dirty: s.dirty,
    deleted: s.deleted,
    tabs: s.tabs,
    active: s.active,
    split: s.split,
    ratio: s.ratio,
    layout: s.layout,
    lastArchive: s.lastArchive,
    lastSync: s.lastSync,
  };
}

export const useWorkspace = create<WorkspaceState>()((set, get) => {
  const flush = async () => {
    saveTimer = null;
    const ids = [...pendingWrites];
    pendingWrites.clear();
    const { pages } = get();
    await Promise.all(ids.map((id) => (pages[id] ? db.put('pages', id, pages[id]) : db.del('pages', id))));
    await db.put('meta', META_KEY, metaOf(get()));
  };
  const persist = (id?: string) => {
    if (id) pendingWrites.add(id);
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => void flush(), 250); // typing never waits for the disk
  };
  const scheduleSync = (ms = 1200) => {
    if (syncTimer) clearTimeout(syncTimer);
    syncTimer = setTimeout(() => void get().syncNow(), ms);
  };
  const markDirty = (id: string) => {
    if (!get().dirty.includes(id)) set({ dirty: [...get().dirty, id] });
    persist(id);
    scheduleSync();
  };

  return {
    ready: false,
    pages: {},
    vault: null,
    sync: 'idle',
    unlocked: {},
    dirty: [],
    deleted: [],
    tabs: [],
    active: null,
    split: null,
    ratio: 0.5,
    layout: DEFAULT_LAYOUT,
    lastArchive: 0,
    lastSync: 0,

    async load() {
      const [list, meta] = await Promise.all([db.all<Page>('pages'), db.get<Meta>('meta', META_KEY)]);
      const pages = Object.fromEntries(list.map((p) => [p.id, p]));
      const m = meta || ({} as Partial<Meta>);
      const tabs = (m.tabs || []).filter((id) => pages[id]);
      set({
        ready: true,
        pages,
        dirty: m.dirty || [],
        deleted: m.deleted || [],
        tabs,
        active: m.active && pages[m.active] ? m.active : tabs[0] || null,
        split: m.split && pages[m.split] ? m.split : null,
        ratio: m.ratio || 0.5,
        layout: { ...DEFAULT_LAYOUT, ...(m.layout || {}) },
        lastArchive: m.lastArchive || 0,
        lastSync: m.lastSync || 0,
      });
      if (Date.now() - (m.lastArchive || 0) > 86_400_000) void get().autoArchive();
      scheduleSync(300);
    },

    create(opts = {}) {
      const tpl = TEMPLATES.find((t) => t.key === (opts.template || 'blank')) || TEMPLATES[0];
      const made = tpl.make();
      const page = newPage(opts.title ?? made.title, opts.parent ?? null, made.blocks);
      set({ pages: { ...get().pages, [page.id]: page } });
      markDirty(page.id);
      if (opts.parent) {
        get().update(opts.parent, (p) => ({ ...p, blocks: [...p.blocks, block('page', page.title, { pageId: page.id })] }));
      }
      if (opts.open !== false) get().open(page.id);
      return page;
    },

    update(id, change) {
      const current = get().pages[id];
      if (!current) return;
      const next = { ...change(current), updatedAt: Date.now() };
      set({ pages: { ...get().pages, [id]: next } });
      markDirty(id);
    },

    remove(id) {
      const { [id]: _gone, ...rest } = get().pages;
      const tabs = get().tabs.filter((t) => t !== id);
      set({
        pages: rest,
        tabs,
        active: get().active === id ? tabs[0] || null : get().active,
        split: get().split === id ? null : get().split,
        dirty: get().dirty.filter((d) => d !== id),
        deleted: _gone && _gone.rev > 0 ? [...get().deleted, id] : get().deleted,
      });
      persist(id);
      scheduleSync();
    },

    open(id, where = 'tab') {
      const s = get();
      if (!s.pages[id]) return;
      const tabs = s.tabs.includes(id) ? s.tabs : [...s.tabs, id].slice(-8);
      if (where === 'split') set({ tabs, split: id === s.active ? null : id });
      else set({ tabs, active: id });
      const page = get().pages[id];
      set({ pages: { ...get().pages, [id]: { ...page, openedAt: Date.now() } } });
      persist(id); // opening is local news only: no sync for it
    },

    close(id) {
      const s = get();
      const tabs = s.tabs.filter((t) => t !== id);
      set({
        tabs,
        active: s.active === id ? (s.split && s.split !== id ? s.split : tabs[tabs.length - 1] || null) : s.active,
        split: s.split === id || (s.active === id && s.split) ? null : s.split,
      });
      persist();
    },

    setActive(id) {
      set({ active: id });
      persist();
    },

    setRatio(ratio) {
      set({ ratio: Math.min(0.8, Math.max(0.2, ratio)) });
      persist();
    },

    setLayout(layout) {
      set({ layout: { ...get().layout, ...layout } });
      persist();
    },

    async archive(id) {
      const page = get().pages[id];
      if (!page) return;
      const archived = { ...page, archived: true, updatedAt: Date.now() };
      await db.put('vault', id, archived);
      const { [id]: _moved, ...rest } = get().pages;
      set({ pages: rest, tabs: get().tabs.filter((t) => t !== id), vault: get().vault ? [...get().vault!, archived] : null });
      await db.del('pages', id);
      set({ dirty: [...new Set([...get().dirty, id])] });
      persist();
      // the server keeps it too (archived), so other devices know
      void remote.put(archived, archived.rev).catch(() => undefined);
    },

    async restore(id) {
      const page = await db.get<Page>('vault', id);
      if (!page) return;
      const back = { ...page, archived: false, openedAt: Date.now(), updatedAt: Date.now() };
      await db.del('vault', id);
      set({ pages: { ...get().pages, [id]: back }, vault: (get().vault || []).filter((p) => p.id !== id) });
      markDirty(id);
    },

    async loadVault() {
      set({ vault: await db.all<Page>('vault') });
    },

    async autoArchive(now = Date.now()) {
      let rows = 0;
      let todos = 0;
      for (const page of Object.values(get().pages)) {
        if (page.sealed) continue;
        const tidy = tidyPage(page, now, DEFAULT_RULES);
        if (tidy.rows || tidy.todos) {
          rows += tidy.rows;
          todos += tidy.todos;
          set({ pages: { ...get().pages, [page.id]: tidy.page } });
          markDirty(page.id);
        }
      }
      const stale = stalePages(Object.values(get().pages), now, DEFAULT_RULES);
      for (const id of stale) await get().archive(id);
      set({ lastArchive: now });
      persist();
      return { pages: stale.length, rows, todos };
    },

    capture(item) {
      // Quick capture lands in the inbox at once (offline too).
      let inbox = Object.values(get().pages).find((p) => p.title === INBOX_TITLE);
      if (!inbox) inbox = get().create({ title: INBOX_TITLE, open: false });
      const stamp = new Date().toLocaleString('es', { dateStyle: 'short', timeStyle: 'short' });
      const added: Block[] = [];
      if (item.media && item.kind) added.push(block(item.kind, item.text || stamp, { media: item.media }));
      else if (item.text) added.push(block('bullet', `${item.text} — ${stamp}`));
      get().update(inbox.id, (p) => ({ ...p, blocks: [...p.blocks.filter((b) => b.text || b.type !== 'text'), ...added] }));
      return get().pages[inbox.id];
    },

    async syncNow() {
      if (get().sync === 'syncing') return;
      if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        set({ sync: 'offline' });
        return;
      }
      set({ sync: 'syncing' });
      try {
        for (const id of [...get().deleted]) {
          await remote.del(id);
          set({ deleted: get().deleted.filter((d) => d !== id) });
        }
        for (const id of [...get().dirty]) {
          const withFiles = get().pages[id] ? await uploadPending(get().pages[id]) : null;
          if (withFiles) set({ pages: { ...get().pages, [id]: withFiles } });
          const page = get().pages[id] || (await db.get<Page>('vault', id));
          if (!page) {
            set({ dirty: get().dirty.filter((d) => d !== id) });
            continue;
          }
          const result = await remote.put(page, page.rev);
          const stored = result.page;
          if (result.ok) {
            // keep any edit typed while the request was in flight
            const now = get().pages[id];
            const merged = now && now.updatedAt > page.updatedAt ? { ...now, rev: stored.rev } : stored;
            if (!stored.archived) set({ pages: { ...get().pages, [id]: merged } });
            if (!now || now.updatedAt <= page.updatedAt) set({ dirty: get().dirty.filter((d) => d !== id) });
          } else {
            // the server's copy wins in place; ours is saved there as a conflict copy
            set({ pages: { ...get().pages, [id]: stored }, dirty: get().dirty.filter((d) => d !== id) });
            const copy = await remote.get(result.copy);
            if (copy) set({ pages: { ...get().pages, [copy.id]: copy } });
            if (copy) pendingWrites.add(copy.id);
          }
          pendingWrites.add(id);
        }
        // What changed elsewhere (another device, Sergio himself).
        const summaries = await remote.list();
        const local = get().pages;
        for (const s of summaries) {
          const mine = local[s.id];
          if (s.archived) {
            if (mine && !get().dirty.includes(s.id)) {
              const full = (await remote.get(s.id)) || mine;
              await db.put('vault', s.id, full);
              const { [s.id]: _gone, ...rest } = get().pages;
              set({ pages: rest, tabs: get().tabs.filter((t) => t !== s.id) });
              pendingWrites.add(s.id);
            }
            continue;
          }
          if ((!mine || s.rev > mine.rev) && !get().dirty.includes(s.id)) {
            const full = await remote.get(s.id);
            if (full) {
              set({ pages: { ...get().pages, [s.id]: full } });
              pendingWrites.add(s.id);
            }
          }
        }
        const onServer = new Set(summaries.map((s) => s.id));
        for (const page of Object.values(get().pages)) {
          if (page.rev > 0 && !onServer.has(page.id) && !get().dirty.includes(page.id)) {
            const { [page.id]: _gone, ...rest } = get().pages; // deleted on another device
            set({ pages: rest, tabs: get().tabs.filter((t) => t !== page.id) });
            pendingWrites.add(page.id);
          }
        }
        set({ sync: 'idle', lastSync: Date.now() });
      } catch {
        set({ sync: typeof navigator !== 'undefined' && navigator.onLine === false ? 'offline' : 'error' });
      } finally {
        persist();
      }
    },

    setUnlocked(id, blocks) {
      const { [id]: _old, ...rest } = get().unlocked;
      set({ unlocked: blocks ? { ...rest, [id]: blocks } : rest });
    },
  };
});

// Flush pending writes right away (tests, and before the page unloads).
export async function flushWorkspace(): Promise<void> {
  if (saveTimer) {
    clearTimeout(saveTimer);
    saveTimer = null;
  }
  const ids = [...pendingWrites];
  pendingWrites.clear();
  const s = useWorkspace.getState();
  await Promise.all(ids.map((id) => (s.pages[id] ? db.put('pages', id, s.pages[id]) : db.del('pages', id))));
  await db.put('meta', META_KEY, metaOf(s));
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => void useWorkspace.getState().syncNow());
  window.addEventListener('pagehide', () => void flushWorkspace());
}
