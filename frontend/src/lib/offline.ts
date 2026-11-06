import { scopedDataKey } from './browserAccount';
// Offline mode: the last answers Sergio gave, kept in IndexedDB so the
// phone (or a laptop on a plane) can still show them without a connection.
// Conversations already live in localStorage; this adds a lookup by
// question so asking the same thing offline gets the saved answer, marked
// with its date.

export const MAX_ANSWERS = 200;
const DB_NAME = scopedDataKey('sergio-offline');
const STORE = 'answers';

export interface SavedAnswer {
  key: string;
  question: string;
  answer: string;
  model: string;
  at: number;
}

// The few operations the cache needs; IndexedDB in the app, a Map in tests.
export interface AnswerStore {
  get(key: string): Promise<SavedAnswer | undefined>;
  put(item: SavedAnswer): Promise<void>;
  all(): Promise<SavedAnswer[]>;
  remove(key: string): Promise<void>;
}

export function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
}

// A follow-up like "¿y mañana?" means something else in each conversation,
// so the key includes the answer it follows (empty for a first question).
export function answerKey(question: string, previousAnswer = ''): string {
  return `${normalize(previousAnswer).slice(0, 200)}\u0000${normalize(question)}`;
}

export function memoryStore(): AnswerStore {
  const items = new Map<string, SavedAnswer>();
  return {
    get: async (key) => items.get(key),
    put: async (item) => {
      items.set(item.key, item);
    },
    all: async () => [...items.values()],
    remove: async (key) => {
      items.delete(key);
    },
  };
}

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export function idbStore(factory: IDBFactory = indexedDB): AnswerStore {
  let opened: Promise<IDBDatabase> | null = null;
  const db = () => {
    if (!opened) {
      const req = factory.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore(STORE, { keyPath: 'key' });
      };
      opened = request(req);
      opened.catch(() => {
        opened = null;
      });
    }
    return opened;
  };
  const run = async <T>(mode: IDBTransactionMode, op: (s: IDBObjectStore) => IDBRequest<T>) => {
    const tx = (await db()).transaction(STORE, mode);
    return request(op(tx.objectStore(STORE)));
  };
  return {
    get: (key) => run('readonly', (s) => s.get(key)),
    put: async (item) => {
      await run('readwrite', (s) => s.put(item));
    },
    all: () => run('readonly', (s) => s.getAll()),
    remove: async (key) => {
      await run('readwrite', (s) => s.delete(key));
    },
  };
}

let defaultStore: AnswerStore | null = null;

function store(): AnswerStore | null {
  if (!defaultStore && typeof indexedDB !== 'undefined') defaultStore = idbStore();
  return defaultStore;
}

export async function rememberAnswer(
  question: string,
  answer: string,
  opts: { previousAnswer?: string; model?: string; at?: number; store?: AnswerStore | null } = {},
): Promise<void> {
  const target = opts.store === undefined ? store() : opts.store;
  if (!target || !question.trim() || !answer.trim()) return;
  try {
    await target.put({
      key: answerKey(question, opts.previousAnswer),
      question: question.trim(),
      answer,
      model: opts.model ?? '',
      at: opts.at ?? Date.now(),
    });
    const items = await target.all();
    if (items.length > MAX_ANSWERS) {
      const oldest = items.sort((a, b) => a.at - b.at).slice(0, items.length - MAX_ANSWERS);
      await Promise.all(oldest.map((item) => target.remove(item.key)));
    }
  } catch {
    // Private browsing or a full disk: the cache is a convenience only.
  }
}

export async function findAnswer(
  question: string,
  opts: { previousAnswer?: string; store?: AnswerStore | null } = {},
): Promise<SavedAnswer | null> {
  const target = opts.store === undefined ? store() : opts.store;
  if (!target) return null;
  try {
    return (await target.get(answerKey(question, opts.previousAnswer))) ?? null;
  } catch {
    return null;
  }
}

export function isOffline(nav: { onLine?: boolean } | undefined = globalThis.navigator): boolean {
  return nav?.onLine === false;
}

// fetch() rejects with a TypeError when there is no network at all
// ("Failed to fetch" in Chrome, "NetworkError…" in Firefox, "Load failed"
// in Safari); a server that answers with an error is not "offline".
export function isNetworkError(err: unknown): boolean {
  if (!(err instanceof TypeError)) return false;
  return /failed to fetch|networkerror|load failed|network request failed/i.test(err.message);
}

export function offlineReply(saved: SavedAnswer, locale = 'es'): string {
  const when = new Date(saved.at).toLocaleString(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
  return `${saved.answer}\n\n_Sin conexión: esta es la respuesta que le di el ${when}._`;
}
