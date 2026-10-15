// Demo mode only: Cowork without a server. A task is planned and worked
// step by step here in the browser (the words come from the viewer's
// assistant when there is one), with the same shapes as /v1/cowork, so the
// real screen (pages/CoworkPage.tsx) shows it as it would on the PC.

type Json = Record<string, unknown>;
type Ask = (prompt: string) => Promise<string>;

interface Step {
  index: number;
  text: string;
  where: string;
  status: string;
  result: string;
  actions: number;
  verdict: { decision?: string; scores?: Record<string, number>; reasons?: string[] };
}

interface Run {
  id: string;
  goal: string;
  title: string;
  status: string;
  autonomy: string;
  max_actions: number;
  actions_used: number;
  summary: string;
  steps: Step[];
  progress: number;
  waiting: number[];
  created: number;
  updated: number;
  notes: Array<{ text: string; at: number }>;
  follows: string;
  context: string;
  plan_first: boolean;
}

const runs = new Map<string, Run>();
const trails = new Map<string, Array<{ seq: number; event: string; ts: number; data: Json }>>();
const answers = new Map<string, (yes: boolean) => void>();
const FINAL = ['done', 'partial', 'failed', 'capped', 'cancelled', 'interrupted'];
const RISKY = /compr|pag[ao]|transfer|env[ií]a|borra|elimina|publica/i;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const now = () => Date.now() / 1000;

function log(run: Run, event: string, data: Json = {}) {
  const list = trails.get(run.id) ?? [];
  list.push({ seq: list.length + 1, event, ts: now(), data });
  trails.set(run.id, list);
  run.updated = now();
}

function view(run: Run): Run {
  const done = run.steps.filter((s) => s.status === 'done').length;
  return {
    ...run,
    progress: run.steps.length ? done / run.steps.length : 0,
    waiting: run.steps.filter((s) => s.status === 'waiting_approval').map((s) => s.index),
    steps: run.steps.map((s) => ({ ...s })),
    notes: [...run.notes],
  };
}

function slug(text: string) {
  return (
    text
      .toLowerCase()
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 40) || 'resultado'
  );
}

async function plan(run: Run, ask: Ask): Promise<string[]> {
  const fallback = [
    'Entender exactamente qué resultado quiere',
    'Reunir la información necesaria',
    'Preparar el resultado',
    'Revisar que todo esté correcto y guardarlo',
  ];
  try {
    const text = await ask(
      `Planifica esta tarea en 3 a 5 pasos cortos, en español, uno por línea, sin numerar ni comentar nada más. ${run.context}\nTarea: ${run.goal.split(' [Adjunto: ')[0]}`,
    );
    const steps = text
      .split('\n')
      .map((l) => l.replace(/^\s*(?:\d+[.)]|[-*•])\s*/, '').trim())
      .filter((l) => l.length > 3)
      .slice(0, 5);
    return steps.length >= 2 ? steps : fallback;
  } catch {
    return fallback;
  }
}

function waitFor(run: Run, key: string): Promise<boolean> {
  return new Promise((resolve) => answers.set(`${run.id}|${key}`, resolve));
}

async function work(run: Run, ask: Ask) {
  await sleep(900);
  const goal = run.goal.split(' [Adjunto: ')[0];
  const lines = await plan(run, ask);
  if (run.status === 'cancelled') return;
  run.title = goal.length > 48 ? `${goal.slice(0, 46).trimEnd()}…` : goal;
  run.steps = lines.map((text, index): Step => ({
    index,
    text,
    where: 'fondo',
    status: 'pending',
    result: '',
    actions: 0,
    verdict: RISKY.test(text)
      ? { decision: 'ask', scores: { financial: 3, network: 1 }, reasons: ['Siempre le pregunto: dinero o personas.'] }
      : { decision: 'allow', scores: { network: 1 } },
  }));
  run.status = 'running';
  log(run, 'planned', { text: `Plan: ${lines.length} pasos.` });

  if (run.plan_first) {
    run.status = 'waiting_plan';
    const yes = await waitFor(run, 'plan');
    log(run, 'plan_decision', { decision: yes ? 'aprobado' : 'rechazado' });
    if (!yes || run.status === 'cancelled') {
      run.status = 'cancelled';
      run.summary = 'Usted no aprobó el plan; no hice nada.';
      log(run, 'finished', { summary: run.summary });
      return;
    }
    run.status = 'running';
  }

  const done: string[] = [];
  for (const step of run.steps) {
    if (run.status === 'cancelled') break;
    if (step.verdict.decision === 'ask') {
      step.status = 'waiting_approval';
      run.status = 'waiting_approval';
      const yes = await waitFor(run, String(step.index));
      log(run, 'owner_decision', { decision: yes ? 'sí' : 'no' });
      if (run.status === 'cancelled') break;
      run.status = 'running';
      if (!yes) {
        step.status = 'skipped';
        step.result = 'Usted no lo aprobó.';
        continue;
      }
    }
    step.status = 'running';
    log(run, 'step_started', { text: step.text });
    await sleep(1600);
    const last = step.index === run.steps.length - 1;
    const notes = run.notes.map((n) => n.text).join('; ');
    let result = '';
    try {
      result = await ask(
        `Eres Sergio trabajando en modo Cowork (es un demo: no tienes internet ni la PC del usuario, así que describe con verosimilitud lo que harías y lo que saldría). Tarea: «${goal}». ${run.context}` +
          (notes ? ` Indicaciones del usuario: ${notes}.` : '') +
          `\nPasos ya hechos: ${done.join(' | ') || 'ninguno'}.\nPaso actual: ${step.text}.\nResponde en una o dos frases qué hiciste en este paso.` +
          (last ? ` Termina diciendo que lo guardó en Documentos/Sergio/${slug(goal)}.md` : ''),
      );
    } catch {
      result = last ? `Listo. Guardado en Documentos/Sergio/${slug(goal)}.md` : 'Hecho.';
    }
    if (run.status === 'cancelled') break;
    step.status = 'done';
    step.result = result.trim().slice(0, 600);
    step.actions = 2 + (step.index % 3);
    run.actions_used += step.actions;
    done.push(`${step.text} → ${step.result}`);
    log(run, 'step_finished', { result: step.result });
  }

  if (run.status === 'cancelled') {
    run.summary = run.summary || 'Cancelado.';
  } else {
    const ok = run.steps.every((s) => s.status === 'done');
    run.status = ok ? 'done' : run.steps.some((s) => s.status === 'done') ? 'partial' : 'failed';
    try {
      run.summary = (
        await ask(
          `Eres Sergio. Resume para el señor, en 2 a 4 frases sencillas y tratándole de usted, el resultado de esta tarea: «${goal}». Pasos: ${done.join(' | ')}. Menciona el archivo Documentos/Sergio/${slug(goal)}.md.`,
        )
      ).trim();
    } catch {
      run.summary = `Listo, señor. Lo dejé en Documentos/Sergio/${slug(goal)}.md`;
    }
  }
  log(run, 'finished', { summary: run.summary });
}

/** /v1/cowork in the demo; null when the path is not Cowork's. */
export function handleCowork(method: string, path: string, body: Json, ask: Ask): Response | null {
  if (!path.startsWith('/v1/cowork')) return null;
  if (path === '/v1/cowork' && method === 'GET') {
    return json({ runs: [...runs.values()].sort((a, b) => b.created - a.created).map(view) });
  }
  if (path === '/v1/cowork' && method === 'POST') {
    const goal = String(body.goal || '').trim();
    if (!goal) return json({ detail: 'Describa el resultado que quiere.' }, 400);
    const parent = body.follows ? runs.get(String(body.follows)) : undefined;
    const run: Run = {
      id: `demo-${Date.now().toString(36)}`,
      goal,
      title: '',
      status: 'planning',
      autonomy: String(body.autonomy || 'normal'),
      max_actions: Number(body.max_actions || 50),
      actions_used: 0,
      summary: '',
      steps: [],
      progress: 0,
      waiting: [],
      created: now(),
      updated: now(),
      notes: [],
      follows: parent?.id || '',
      context: parent ? `Esto continúa la tarea «${parent.title}» (resultado: ${parent.summary}).` : '',
      plan_first: Boolean(body.plan_first),
    };
    runs.set(run.id, run);
    log(run, 'started', { text: goal });
    void work(run, ask);
    return json(view(run));
  }
  const m = path.match(/^\/v1\/cowork\/([^/]+)(?:\/(\w+))?$/);
  const run = m ? runs.get(m[1]) : undefined;
  if (!m || !run) return json({ detail: 'No existe esa tarea de Cowork.' }, 404);
  const action = m[2];
  if (!action && method === 'GET') return json(view(run));
  if (action === 'audit') return json({ entries: trails.get(run.id) ?? [], intact: true, broken_at: null });
  if (action === 'note' && method === 'POST') {
    const text = String(body.text || '').trim();
    if (!text || FINAL.includes(run.status)) return json({ detail: 'Esa tarea ya terminó.' }, 409);
    run.notes.push({ text, at: now() });
    log(run, 'owner_note', { text });
    return json({ ok: true });
  }
  if (action === 'decision' && method === 'POST') {
    const step = Number(body.step);
    const key = `${run.id}|${step === 0 ? 'plan' : String(step - 1)}`;
    const resolve = answers.get(key);
    if (!resolve) return json({ detail: 'Ese paso no está esperando su respuesta.' }, 409);
    answers.delete(key);
    resolve(Boolean(body.approve));
    return json({ ok: true });
  }
  if (action === 'cancel' && method === 'POST') {
    if (!FINAL.includes(run.status)) {
      run.status = 'cancelled';
      run.summary = 'Cancelado.';
      for (const [key, resolve] of answers) {
        if (key.startsWith(`${run.id}|`)) {
          answers.delete(key);
          resolve(false);
        }
      }
      log(run, 'finished', { summary: run.summary });
    }
    return json({ ok: true });
  }
  return json({ detail: 'No disponible en el demo.' }, 503);
}
