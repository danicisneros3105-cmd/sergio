// Demo mode (`npm run build:demo`): the whole web app runs with no server.
// Every /v1 call is answered here, from answers recorded from a real
// Sergio server (fixtures.json) plus a small in-memory store, and the chat
// and the Nodes answer for real through the viewer's assistant when the
// page is opened where one is available (window.claude.use('sample')).
// Nothing here is part of the normal build.

import fixtures from './fixtures.json';
import { handleCowork } from './cowork';
import { handleExtensions } from './extensions';

type Json = Record<string, unknown>;
type Fixture = { status: number; json?: unknown; text?: string; ct?: string; sse?: boolean };
type Sampler = ((input: unknown, opts?: Json) => Promise<{ text: string }>) | null;

const recorded = fixtures as Record<string, Fixture>;
const store = new Map<string, unknown>(); // what the demo changed (PUT/POST)
const nodeMessages = new Map<string, Json[]>();

const PERSONA = `Eres Sergio, el asistente personal del usuario, a quien llamas «señor». \
Eres un caballero al estilo de JARVIS: preciso, con carisma y un humor seco y elegante (nunca \
sobre grupos, tragedias ni dolor). Respondes en español sencillo y breve salvo que te pidan \
detalle, con Markdown cuando ayude. Esto es un demo de la app en el iPad del señor: no tienes \
acceso a su PC, su correo ni internet; si te pide algo así, explica en una frase qué harías en \
la app real (por ejemplo, «en su PC abriría…») y ofrece lo que sí puedes hacer aquí. \
Sus empleados digitales se llaman «Nodes» (uno: «Node») en cualquier idioma, nunca «nodos». Nunca envíes mensajes, compres ni borres nada por tu cuenta. Si notas riesgo para su vida, \
dale con calma el número de emergencias local.`;

// ---- the assistant behind the demo ---------------------------------------
let sampler: Promise<Sampler> | null = null;

// A Node is a «Node» in every language (the owner's rule).
const nodeWord = (t: string) =>
  t.replace(/\b(nodos|nodo|nœuds|nœud|noeuds|noeud|knoten|nodi|nodes|node)\b/gi, (w) =>
    /^(nodos|nœuds|noeuds|nodi|nodes)$/i.test(w) ? 'Nodes' : 'Node');
function getSampler(): Promise<Sampler> {
  if (!sampler) {
    const claude = (window as unknown as { claude?: { use?: (n: string) => Promise<unknown> } }).claude;
    sampler = claude?.use
      ? claude.use('sample').then((s) => (s as Sampler) || null).catch(() => null)
      : Promise.resolve(null);
  }
  return sampler;
}

function canned(question: string): string {
  const q = question.toLowerCase();
  if (/hola|buen/.test(q)) return 'Buenas, señor. Aquí estoy: dígame qué necesita y me pongo con ello.';
  if (/qui[eé]n eres|qu[eé] eres/.test(q)) return 'Soy Sergio, su asistente. Hablo, escribo, organizo su Workspace, dirijo a los Nodes y, en su PC, veo la pantalla y la manejo.';
  return 'En este demo no puedo pensar la respuesta, señor (falta el permiso del asistente). En la app real le contestaría al momento.';
}

async function answer(history: Array<{ role: string; content: string }>, onDelta: (d: string) => void, persona = PERSONA): Promise<string> {
  const turns = history
    .filter((m) => (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string' && m.content)
    .slice(-16)
    .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }));
  while (turns.length && turns[0].role !== 'user') turns.shift();
  if (!turns.length || turns[turns.length - 1].role !== 'user') turns.push({ role: 'user', content: 'Hola' });
  turns[0] = { role: 'user', content: `${persona}\n\n---\n\n${turns[0].content}` };
  const sample = await getSampler();
  if (!sample) {
    const text = canned(history[history.length - 1]?.content || '');
    for (const word of text.split(/(?<=\s)/)) {
      onDelta(word);
      await new Promise((r) => setTimeout(r, 18));
    }
    return text;
  }
  let sent = '';
  try {
    const out = await sample(turns, {
      cache: false,
      modelTier: 'quick',
      onText: ({ text }: { text: string }) => {
        if (text.startsWith(sent) && text.length > sent.length) {
          onDelta(text.slice(sent.length));
          sent = text;
        }
      },
    });
    if (out.text.length > sent.length && out.text.startsWith(sent)) onDelta(out.text.slice(sent.length));
    return out.text;
  } catch (e) {
    const partial = (e as { text?: string }).text;
    if (partial) return partial;
    const text = 'Ahora no puedo pensar, señor (el asistente del demo no respondió). Pruebe otra vez en un momento.';
    onDelta(text);
    return text;
  }
}

// What the Windows app would tell (it is not running here): example data,
// said to be an example.
const EXAMPLES: Record<string, unknown> = {
  '/v1/desktop/health': {
    text: 'Datos de ejemplo del demo. Esta semana durmió 6,8 horas de media, media hora menos que la anterior; caminó más los días de oficina. Le propongo acostarse 20 minutos antes y un paseo corto después de comer.',
    metrics: { imc: 23.4, gasto_diario: 2350 },
    trends: { pasos: { '7d': 8240 }, sueno_h: { '7d': 6.8 }, fc_reposo: { '7d': 61 } },
    report: { metas: ['Dormir 7 h y media entre semana', '9.000 pasos al día', 'Tres sesiones del gimnasio mental'] },
  },
  '/v1/desktop/profile': {
    text: 'Perfil de ejemplo del demo. Trabaja mejor por la mañana, prefiere respuestas cortas y directas y le gusta que Sergio proponga el siguiente paso. Está aprendiendo inglés y diseño 3D; los viernes revisa sus finanzas.',
    updates: 14,
  },
};

// ---- responses ------------------------------------------------------------
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

function chatStream(body: Json): Response {
  const enc = new TextEncoder();
  const id = 'chatcmpl-demo' + Date.now().toString(36);
  const model = String(body.model || 'sergio');
  const chunk = (delta: Json, finish: string | null = null) =>
    enc.encode(`data: ${JSON.stringify({ id, object: 'chat.completion.chunk', created: Date.now() / 1000, model, choices: [{ index: 0, delta, finish_reason: finish }] })}\n\n`);
  const stream = new ReadableStream<Uint8Array>({
    async start(ctrl) {
      ctrl.enqueue(chunk({ role: 'assistant', content: null }));
      await answer((body.messages as Array<{ role: string; content: string }>) || [], (d) => ctrl.enqueue(chunk({ content: d })));
      ctrl.enqueue(chunk({}, 'stop'));
      ctrl.enqueue(enc.encode('data: [DONE]\n\n'));
      ctrl.close();
    },
  });
  return new Response(stream, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

// Spoken replies: the iPad's own voice reads it; the app plays a silent clip
// as long as the sentence, so its "speaking" state matches.
function speak(text: string): Response {
  try {
    const u = new SpeechSynthesisUtterance(text.replace(/[*_`#>]/g, ''));
    u.lang = 'es-ES';
    u.rate = 1.04;
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  } catch { /* no voice here: the clip is just silence */ }
  const rate = 8000;
  const n = Math.round(rate * Math.min(60, Math.max(1, text.length * 0.065)));
  const buf = new ArrayBuffer(44 + n);
  const v = new DataView(buf);
  const w = (o: number, t: string) => [...t].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, 'RIFF'); v.setUint32(4, 36 + n, true); w(8, 'WAVE'); w(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate, true); v.setUint16(32, 1, true); v.setUint16(34, 8, true);
  w(36, 'data'); v.setUint32(40, n, true);
  new Uint8Array(buf, 44).fill(128);
  return new Response(buf, { status: 200, headers: { 'content-type': 'audio/wav' } });
}

function messagesOf(nodeId: string, thread: string): Json[] {
  const key = `${nodeId}|${thread}`;
  if (!nodeMessages.has(key)) {
    const hit = Object.entries(recorded).find(([k]) => k.startsWith(`GET /v1/nodes/${nodeId}/messages`) && k.includes(`thread=${thread}`));
    nodeMessages.set(key, ((hit?.[1].json as { messages?: Json[] })?.messages || []).slice());
  }
  return nodeMessages.get(key)!;
}

function nodeReply(nodeId: string, thread: string, text: string): Json {
  const list = messagesOf(nodeId, thread);
  const now = Date.now() / 1000;
  const mine = { id: Math.random().toString(16).slice(2, 12), at: now, role: 'user', text, thread };
  list.push(mine);
  const node = ((recorded['GET /v1/nodes']?.json as { nodes?: Json[] })?.nodes || []).find((n) => n.id === nodeId);
  const persona = `Eres ${node?.name || 'un Node'}, un empleado digital persistente de la app Sergio (estilo Dots). \
Tus instrucciones: ${node?.instructions || ''}\nHablas al usuario de usted, en español, breve y con calidez. Es un demo: no tienes internet ni su PC; \
responde con lo que harías y una propuesta concreta. Te llamas «Node» (plural «Nodes») en cualquier idioma, nunca «nodo».`;
  const history = list.map((m) => ({ role: m.role === 'user' ? 'user' : 'assistant', content: String(m.text || '') }));
  void answer(history, () => {}, persona).then((reply) => {
    list.push({ id: Math.random().toString(16).slice(2, 12), at: Date.now() / 1000, role: 'node', text: nodeWord(reply), thread, source: 'Encargo del usuario' });
  });
  return mine;
}

function recordedFor(method: string, path: string, search: string): Fixture | undefined {
  const exact = recorded[`${method} ${path}${search}`] || recorded[`${method} ${path}`];
  if (exact) return exact;
  const prefix = `${method} ${path}?`;
  const loose = Object.keys(recorded).find((k) => k.startsWith(prefix));
  return loose ? recorded[loose] : undefined;
}

async function handle(method: string, url: URL, init?: RequestInit): Promise<Response> {
  const path = url.pathname.replace(/^.*?(?=\/(v1|health|api)(\/|$))/, '');
  let body: Json = {};
  if (init?.body && typeof init.body === 'string') {
    try { body = JSON.parse(init.body); } catch { /* not JSON */ }
  }
  if (path === '/health') return json({ status: 'ok' });
  if (method === 'POST' && path === '/v1/speech/synthesize') return speak(String(body.text || ''));
  if (method === 'POST' && path === '/v1/chat/completions') return chatStream(body);

  const extension = handleExtensions(method, path, url, body);
  if (extension) return extension;
  const cowork = handleCowork(method, path, body, async (prompt) => {
    if (!(await getSampler())) throw new Error('no assistant here');
    return answer([{ role: 'user', content: prompt }], () => {});
  });
  if (cowork) return cowork;

  const nodeMsg = path.match(/^\/v1\/nodes\/([^/]+)\/messages$/);
  if (nodeMsg) {
    const thread = url.searchParams.get('thread') || String(body.thread || 'main');
    if (method === 'POST') return json({ message: nodeReply(nodeMsg[1], thread, String(body.text || '')) });
    const after = Number(url.searchParams.get('after') || 0);
    return json({ messages: messagesOf(nodeMsg[1], thread).filter((m) => Number(m.at) > after) });
  }

  // Workspace pages (the editor itself is local-first, this is the sync).
  const page = path.match(/^\/v1\/workspace\/pages\/([^/]+)$/);
  if (page && method === 'PUT') {
    const p = { ...((body.page as Json) || {}), rev: Number((body.page as Json)?.rev || 0) + 1 };
    store.set(`page:${page[1]}`, p);
    return json({ page: p });
  }
  if (page && method === 'GET') {
    const p = store.get(`page:${page[1]}`);
    return p ? json({ page: p }) : json({ detail: 'No encuentro esa página.' }, 404);
  }
  if (page && method === 'DELETE') { store.delete(`page:${page[1]}`); return json({ ok: true }); }
  if (path === '/v1/workspace/pages' && method === 'GET') {
    const pages = [...store.entries()].filter(([k]) => k.startsWith('page:')).map(([, v]) => v as Json);
    return json({ pages: pages.map((p) => ({ id: p.id, rev: p.rev, updatedAt: p.updatedAt, archived: p.archived })) });
  }

  const example = EXAMPLES[path];
  if (method === 'GET' && example) return json(example);

  if (method === 'GET') {
    const hit = recordedFor('GET', path, url.search);
    if (hit) {
      if (hit.json !== undefined) return json(hit.json, hit.status);
      if (hit.text !== undefined) return new Response(hit.text, { status: hit.status, headers: { 'content-type': hit.ct || 'text/plain' } });
    }
    return json({ detail: 'No disponible en el demo.' }, 503);
  }
  // Anything else that changes something: accepted, nothing leaves the iPad.
  return json({ ok: true, demo: true, ...body });
}


// Example Workspace pages (the editor is local-first; it pulls these from
// the «server» on its first sync), marked as examples in their text.
function seedWorkspace() {
  const now = Date.now();
  const b = (id: string, type: string, text = '', extra: Json = {}) => ({ id, type, text, ...extra });
  const page = (id: string, title: string, icon: string, blocks: Json[], extra: Json = {}) => ({
    id, title, icon, parent: null, blocks, createdAt: now - 86_400_000, updatedAt: now - 3_600_000, openedAt: now - 3_600_000,
    rev: 1, tags: [], sealed: null, ...extra,
  });
  const cName = 'c_nombre', cState = 'c_estado', cOwner = 'c_resp', cDate = 'c_fecha', cCost = 'c_coste';
  const table = {
    columns: [
      { id: cName, name: 'Tarea', type: 'text' },
      { id: cState, name: 'Estado', type: 'select', options: ['Por hacer', 'En curso', 'Hecho'] },
      { id: cOwner, name: 'Responsable', type: 'select', options: ['Señor', 'Leo', 'Mía', 'Ordo'] },
      { id: cDate, name: 'Fecha', type: 'date' },
      { id: cCost, name: 'Coste', type: 'number' },
    ],
    rows: [
      ['Definir el precio', 'Hecho', 'Señor', 2, 0],
      ['Investigar a la competencia', 'Hecho', 'Leo', 4, 120],
      ['Diseñar la web', 'En curso', 'Mía', 9, 900],
      ['Preparar la campaña', 'En curso', 'Ordo', 12, 450],
      ['Lanzamiento', 'Por hacer', 'Señor', 20, 300],
    ].map(([n, st, o, d, c], i) => ({
      id: `r_${i}`,
      cells: { [cName]: n, [cState]: st, [cOwner]: o, [cDate]: new Date(now + Number(d) * 86_400_000).toISOString().slice(0, 10), [cCost]: String(c) },
    })),
    views: [
      { id: 'v_tabla', name: 'Tabla', kind: 'table' },
      { id: 'v_tablero', name: 'Tablero', kind: 'board', groupBy: cState },
      { id: 'v_cal', name: 'Calendario', kind: 'calendar' },
    ],
    view: 'v_tabla',
  };
  const pages = [
    page('p_demo_bienvenida', 'Bienvenido a su Workspace', 'i:file', [
      b('b1', 'callout', 'Página de ejemplo del demo. Escriba en cualquier sitio, pulse «/» para insertar bloques o «@» para enlazar otra página.'),
      b('b2', 'h2', 'Lo básico'),
      b('b3', 'todo', 'Pulse **/** en una línea vacía y elija un bloque', { checked: true }),
      b('b4', 'todo', 'Seleccione texto para ponerlo en **negrita**, *cursiva* o `código`', { checked: false }),
      b('b5', 'todo', 'Arrastre el ⋮⋮ de la izquierda para mover un bloque', { checked: false }),
      b('b6', 'todo', 'Añada un icono y una portada (pase el ratón sobre el título)', { checked: false }),
      b('b7', 'h2', 'Sus páginas'),
      b('b8', 'text', 'El plan está en [[Lanzamiento de la tienda]] y las notas en [[Reunión del lunes]].'),
      b('b9', 'toggle', 'Qué más sabe hacer Sergio aquí\nResumir, sacar tareas, buscar por significado, cifrar páginas, compartir solo una parte y ver el historial de versiones.', { open: false }),
      b('b10', 'quote', 'La mejor forma de empezar es empezar.', { color: 'gray' }),
    ], { cover: 'g3', favorite: true }),
    page('p_demo_lanzamiento', 'Lanzamiento de la tienda', 'i:rocket', [
      b('l1', 'text', 'Ejemplo: el plan de lanzamiento, con su base de datos de tareas.'),
      b('l2', 'h2', 'Tareas'),
      b('l3', 'table', '', { table }),
      b('l4', 'h2', 'Riesgos'),
      b('l5', 'bullet', 'La web podría retrasarse una semana', { color: 'orange' }),
      b('l6', 'bullet', 'El presupuesto de campaña está al 80 %'),
    ], { cover: 'g2' }),
    page('p_demo_reunion', 'Reunión del lunes', 'i:users', [
      b('m1', 'h2', 'Asistentes'),
      b('m2', 'bullet', 'Señor, Leo y Mía'),
      b('m3', 'h2', 'Decisiones'),
      b('m4', 'number', 'Lanzar en tres semanas'),
      b('m5', 'number', 'Mía cierra el diseño el viernes'),
      b('m6', 'h2', 'Tareas'),
      b('m7', 'todo', 'Enviar el resumen a todos', { checked: false }),
      b('m8', 'page', 'Ideas para la campaña', { pageId: 'p_demo_ideas' }),
    ]),
    page('p_demo_ideas', 'Ideas para la campaña', 'i:bulb', [
      b('i1', 'bullet', 'Vídeo corto con el antes y el después'),
      b('i2', 'bullet', 'Descuento para los primeros 100'),
    ], { parent: 'p_demo_reunion' }),
  ];
  for (const p of pages) store.set(`page:${p.id}`, p);
}
seedWorkspace();

// ---- install ---------------------------------------------------------------
const realFetch = window.fetch.bind(window);
const API = /(^|\/)(v1|health|api)(\/|$)/;
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  const url = new URL(raw, location.href);
  const sameApp = url.origin === location.origin || /^(127\.0\.0\.1|localhost)$/.test(url.hostname);
  if (sameApp && API.test(url.pathname)) {
    const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    await new Promise((r) => setTimeout(r, 60)); // a real server is never instant
    return handle(method, url, init);
  }
  if (sameApp && url.pathname.endsWith('/version.json')) return json({ build: 'demo' });
  return realFetch(input, init);
};

// Live sockets (agents' events, voice) stay quiet in the demo.
class QuietSocket extends EventTarget {
  static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
  readyState = 0; url: string; protocol = ''; extensions = ''; bufferedAmount = 0; binaryType: BinaryType = 'blob';
  onopen: ((e: Event) => void) | null = null; onclose: ((e: CloseEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null; onmessage: ((e: MessageEvent) => void) | null = null;
  constructor(url: string | URL) { super(); this.url = String(url); }
  send() { /* nobody listening */ }
  close() { this.readyState = 3; }
}
const RealWS = window.WebSocket;
window.WebSocket = function (url: string | URL, protocols?: string | string[]) {
  return API.test(new URL(String(url), location.href).pathname) ? new QuietSocket(url) : new RealWS(url, protocols);
} as unknown as typeof WebSocket;
const RealES = window.EventSource;
window.EventSource = function (url: string | URL, conf?: EventSourceInit) {
  return API.test(new URL(String(url), location.href).pathname) ? new QuietSocket(url) : new RealES(url, conf);
} as unknown as typeof EventSource;

// The always-on voice needs the microphone, which the demo page cannot use:
// it starts off (the Conversación button still shows how it asks).
try {
  if (localStorage.getItem('sergio.live') === null) localStorage.setItem('sergio.live', 'off');
} catch { /* storage blocked */ }

export {};
