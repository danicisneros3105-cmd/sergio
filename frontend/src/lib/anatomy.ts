// The hidden «Anatomy» skill: Sergio's isometric machine figures appear in the
// chat whenever a reply (or the tool's result) links to one.

const VIEW = /\/v1\/creator\/anatomy\/view\/([A-Za-z0-9][\w-]{0,79})(?![\w\u00C0-\u024F-])/g;

/** Names of the figures a text links to, in order, without repeats. */
export function anatomyNames(...texts: Array<string | undefined>): string[] {
  const out: string[] = [];
  for (const text of texts) {
    for (const m of (text || '').matchAll(VIEW)) if (!out.includes(m[1])) out.push(m[1]);
  }
  return out;
}

// The frame is sandboxed without same-origin (it cannot touch Sergio's
// storage or keys), so a figure that remembers its settings gets a storage
// that lives in memory instead of an error.
const MEMORY_STORAGE = `<script>(function(){try{window.localStorage.length}catch(e){var m={};var s={getItem:function(k){return Object.prototype.hasOwnProperty.call(m,k)?m[k]:null},setItem:function(k,v){m[k]=String(v)},removeItem:function(k){delete m[k]},clear:function(){m={}},key:function(i){return Object.keys(m)[i]||null},get length(){return Object.keys(m).length}};['localStorage','sessionStorage'].forEach(function(n){try{Object.defineProperty(window,n,{value:s,configurable:true})}catch(_){}})}})();</script>`;

export function withMemoryStorage(html: string): string {
  const head = /<head[^>]*>/i.exec(html);
  if (head) return html.slice(0, head.index + head[0].length) + MEMORY_STORAGE + html.slice(head.index + head[0].length);
  const doctype = /<!doctype[^>]*>/i.exec(html);
  if (doctype) return html.slice(0, doctype.index + doctype[0].length) + MEMORY_STORAGE + html.slice(doctype.index + doctype[0].length);
  return MEMORY_STORAGE + html;
}

/** The reply without the raw figure links (the figures are drawn below it). */
export function withoutAnatomyLinks(text: string): string {
  return text
    .replace(/[ \t]*\(?\/v1\/creator\/anatomy\/view\/[A-Za-z0-9][\w-]{0,79}\)?(?![\wÀ-ɏ-])/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .trim();
}
