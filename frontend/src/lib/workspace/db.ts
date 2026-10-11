// The Workspace's local copy: IndexedDB on this device, so every page opens
// in milliseconds and works with no network. Archived pages live in their
// own store («vault») and are not read at start-up, so the app stays light.
// Tests (and browsers that block storage) get an in-memory twin.

import type { Page } from './model';

export type StoreName = 'pages' | 'vault' | 'files' | 'meta';

export interface LocalDB {
  get<T>(store: StoreName, key: string): Promise<T | undefined>;
  all<T>(store: StoreName): Promise<T[]>;
  put(store: StoreName, key: string, value: unknown): Promise<void>;
  del(store: StoreName, key: string): Promise<void>;
}

export function memoryDB(): LocalDB {
  const data: Record<StoreName, Map<string, unknown>> = {
    pages: new Map(),
    vault: new Map(),
    files: new Map(),
    meta: new Map(),
  };
  const copy = <T,>(v: unknown) => (v === undefined ? undefined : (structuredClone(v) as T));
  return {
    async get<T>(store: StoreName, key: string) {
      return copy<T>(data[store].get(key));
    },
    async all<T>(store: StoreName) {
      return [...data[store].values()].map((v) => copy<T>(v) as T);
    },
    async put(store, key, value) {
      data[store].set(key, structuredClone(value));
    },
    async del(store, key) {
      data[store].delete(key);
    },
  };
}

const DB_NAME = 'sergio-workspace';
const VERSION = 1;

export function idbDB(factory: IDBFactory = indexedDB): LocalDB {
  let opening: Promise<IDBDatabase> | null = null;
  const open = () => {
    opening ??= new Promise<IDBDatabase>((resolve, reject) => {
      const req = factory.open(DB_NAME, VERSION);
      req.onupgradeneeded = () => {
        for (const name of ['pages', 'vault', 'files', 'meta']) {
          if (!req.result.objectStoreNames.contains(name)) req.result.createObjectStore(name);
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return opening;
  };
  const run = async <T,>(store: StoreName, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest): Promise<T> => {
    const db = await open();
    return new Promise<T>((resolve, reject) => {
      const tx = db.transaction(store, mode);
      const req = fn(tx.objectStore(store));
      req.onsuccess = () => resolve(req.result as T);
      req.onerror = () => reject(req.error);
    });
  };
  return {
    get: (store, key) => run(store, 'readonly', (s) => s.get(key)),
    all: (store) => run(store, 'readonly', (s) => s.getAll()),
    put: (store, key, value) => run(store, 'readwrite', (s) => s.put(value, key)),
    del: (store, key) => run(store, 'readwrite', (s) => s.delete(key)),
  };
}

export function defaultDB(): LocalDB {
  try {
    if (typeof indexedDB !== 'undefined') return idbDB();
  } catch {
    // storage blocked: work in memory for this visit
  }
  return memoryDB();
}

export type { Page };
