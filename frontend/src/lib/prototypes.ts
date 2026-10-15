// «Prototipos»: Sergio designs a whole page (a prototype, slides, a one-pager,
// a wireframe) as one self-contained HTML file, and changes it by talking.
// Pure helpers here (tested); the screen is components/Creator/Prototypes.tsx.

export type ProtoKind = 'prototipo' | 'presentacion' | 'pagina' | 'boceto' | 'otro';

export const KINDS: Array<{ key: ProtoKind; label: string; hint: string }> = [
  { key: 'prototipo', label: 'Prototipo', hint: 'Una app o web que se puede tocar' },
  { key: 'presentacion', label: 'Presentación', hint: 'Diapositivas 16:9' },
  { key: 'pagina', label: 'Una página', hint: 'Informe, cartel o resumen' },
  { key: 'boceto', label: 'Boceto', hint: 'Estructura en grises, sin detalles' },
  { key: 'otro', label: 'Otro', hint: 'Lo que usted describa' },
];

export interface ProtoVersion {
  html: string;
  at: number;
  note: string;
}

export interface ProtoMessage {
  role: 'user' | 'sergio';
  text: string;
  at: number;
}

export interface Project {
  id: string;
  title: string;
  kind: ProtoKind;
  createdAt: number;
  updatedAt: number;
  versions: ProtoVersion[];
  current: number; // index of the version shown
  messages: ProtoMessage[];
  pending?: string; // the first request, sent when the editor opens
}

const KIND_GUIDE: Record<ProtoKind, string> = {
  prototipo: 'Un prototipo interactivo de alta fidelidad: navegación, estados, botones que responden (con JavaScript sencillo dentro del archivo).',
  presentacion:
    'Una presentación: cada diapositiva es un <section class="slide"> de 1920×1080 escalado para caber en el ancho de la ventana, una debajo de otra, con buena jerarquía tipográfica.',
  pagina: 'Un documento de una sola página (informe, cartel, resumen, currículum) cuidado como de imprenta.',
  boceto: 'Un boceto de baja fidelidad: solo grises, cajas y textos de muestra para decidir la estructura; nada de decoración.',
  otro: 'Lo que pida el usuario, con criterio de diseñador profesional.',
};

/** What Sergio is asked: the design brief or the change, plus the rules. */
export function designPrompt(opts: {
  kind: ProtoKind;
  request: string;
  html?: string;
  comments?: Array<{ target: string; text: string }>;
}): string {
  const rules = [
    'Eres un diseñador de producto de primer nivel. Responde en español.',
    'Devuelve primero UNA frase corta diciendo qué hiciste, y después el diseño completo en un único bloque ```html.',
    'El diseño es un solo archivo HTML autocontenido (<!doctype html> … </html>) con su CSS en <style> y, si hace falta, su JS en <script>.',
    'Nada externo salvo fuentes de Google Fonts: sin imágenes de internet (usa formas, degradados o SVG en línea), sin librerías.',
    'Define los colores y medidas principales como variables CSS en :root (por ejemplo --fondo, --texto, --acento, --radio, --espacio) y úsalas en todo el diseño, para poder ajustarlo después.',
    'Debe verse bien en escritorio, tableta y móvil. Textos reales y verosímiles, nunca «lorem ipsum».',
    `Tipo: ${KIND_GUIDE[opts.kind]}`,
  ];
  if (!opts.html) return `${rules.join('\n')}\n\nEncargo: ${opts.request}`;
  const notes = (opts.comments || [])
    .map((c, i) => `${i + 1}. Sobre ${c.target}: ${c.text}`)
    .join('\n');
  return [
    ...rules,
    'Este es el diseño actual. Aplica el cambio pedido y conserva todo lo demás igual. Devuelve el archivo completo.',
    '```html',
    opts.html,
    '```',
    notes ? `Comentarios del usuario sobre elementos concretos:\n${notes}` : '',
    `Cambio pedido: ${opts.request || 'aplica los comentarios'}`,
  ]
    .filter(Boolean)
    .join('\n\n');
}

/** The HTML in an answer (a ```html block, or the document itself), and the
 * words around it. */
export function splitAnswer(answer: string): { html: string; note: string } {
  const fenced = answer.match(/```(?:html)?\s*\n([\s\S]*?)(?:```|$)/i);
  if (fenced && /<(html|body|!doctype|div|section)/i.test(fenced[1])) {
    const note = answer.replace(fenced[0], '').trim();
    return { html: fenced[1].trim(), note };
  }
  const start = answer.search(/<!doctype html|<html/i);
  if (start >= 0) return { html: answer.slice(start).trim(), note: answer.slice(0, start).trim() };
  return { html: '', note: answer.trim() };
}

export interface CssVar {
  name: string;
  value: string;
  kind: 'color' | 'length' | 'other';
}

/** The variables declared in the first :root block (the design's knobs). */
export function cssVars(html: string): CssVar[] {
  const root = html.match(/:root\s*{([^}]*)}/);
  if (!root) return [];
  const out: CssVar[] = [];
  for (const m of root[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    const value = m[2].trim();
    const kind = /^#([0-9a-f]{3}){1,2}$/i.test(value) || /^rgba?\(/i.test(value) ? 'color' : /^-?[\d.]+(px|rem|em|%)$/.test(value) ? 'length' : 'other';
    out.push({ name: m[1], value, kind });
  }
  return out;
}

/** The same HTML with one :root variable changed. */
export function setCssVar(html: string, name: string, value: string): string {
  return html.replace(/:root\s*{([^}]*)}/, (block) =>
    block.replace(new RegExp(`(${name.replace(/[-]/g, '\\-')}\\s*:\\s*)([^;]+)(;)`), `$1${value}$3`),
  );
}

export function titleFrom(request: string): string {
  const t = request.replace(/\s+/g, ' ').trim();
  return t.length > 48 ? `${t.slice(0, 46).trimEnd()}…` : t || 'Diseño sin título';
}

// The script put inside the preview so the page can be commented on and
// edited in place; it talks to Sergio's screen with postMessage and is
// removed again from anything saved or exported.
export const BRIDGE_MARK = 'data-sergio-bridge';
export const BRIDGE = `<script ${BRIDGE_MARK}>(function(){
var mode='view',hover=null;
function path(el){var p=[];while(el&&el.nodeType===1&&el!==document.body&&p.length<4){var s=el.tagName.toLowerCase();if(el.id)s+='#'+el.id;else if(el.classList.length)s+='.'+el.classList[0];p.unshift(s);el=el.parentElement;}return p.join(' > ');}
function clean(){var d=document.documentElement.cloneNode(true);d.querySelectorAll('[${BRIDGE_MARK}]').forEach(function(n){n.remove()});d.querySelectorAll('[data-sergio-hover]').forEach(function(n){n.removeAttribute('data-sergio-hover')});var b=d.querySelector('body');if(b)b.removeAttribute('contenteditable');return '<!doctype html>\\n'+d.outerHTML;}
var st=document.createElement('style');st.setAttribute('${BRIDGE_MARK}','');st.textContent='[data-sergio-hover]{outline:2px solid #111!important;outline-offset:2px;cursor:pointer}';document.head.appendChild(st);
document.addEventListener('mouseover',function(e){if(mode!=='comment')return;if(hover)hover.removeAttribute('data-sergio-hover');hover=e.target;hover.setAttribute('data-sergio-hover','');});
document.addEventListener('click',function(e){if(mode!=='comment')return;e.preventDefault();e.stopPropagation();var t=e.target;parent.postMessage({sergio:'pick',target:path(t),text:(t.innerText||'').slice(0,80)},'*');},true);
var timer;document.addEventListener('input',function(){if(mode!=='edit')return;clearTimeout(timer);timer=setTimeout(function(){parent.postMessage({sergio:'edited',html:clean()},'*');},500);});
window.addEventListener('message',function(e){var d=e.data||{};if(d.sergio==='mode'){mode=d.mode;document.body.contentEditable=mode==='edit'?'true':'false';if(hover&&mode!=='comment'){hover.removeAttribute('data-sergio-hover');hover=null;}}if(d.sergio==='print')window.print();});
})();</script>`;

/** The preview's HTML: the design plus the bridge (never saved). */
export function withBridge(html: string): string {
  if (!html) return '';
  return /<\/body>/i.test(html) ? html.replace(/<\/body>/i, `${BRIDGE}</body>`) : html + BRIDGE;
}

export function withoutBridge(html: string): string {
  return html.replace(new RegExp(`<script ${BRIDGE_MARK}>[\\s\\S]*?</script>`, 'g'), '').replace(new RegExp(`<style ${BRIDGE_MARK}[^>]*>[\\s\\S]*?</style>`, 'g'), '');
}
