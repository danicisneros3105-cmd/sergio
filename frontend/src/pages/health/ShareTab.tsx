import { useState } from 'react';
import { Download, Printer } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { fmt, salud, STATUS_ES } from '../../lib/salud';

async function downloadCsv() {
  const res = await apiFetch(salud.exportUrl);
  if (!res.ok) return toast.error('No pude preparar el archivo.');
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = `salud-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function escape(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] || c);
}

/** A one-page summary for the doctor, printed (or saved as PDF) from the browser. */
async function printReport() {
  const r = await salud.report();
  if (!r.rows.length) return toast('Aún no hay datos que resumir.');
  const rows = r.rows
    .map((x) => `<tr><td>${escape(x.label)}</td><td>${escape(fmt(x.avg, x.unit, 1))}</td><td>${escape(fmt(x.min, '', 1))} – ${escape(fmt(x.max, '', 1))}</td><td>${x.days}</td><td>${escape(STATUS_ES[x.status] || '')}</td></tr>`)
    .join('');
  const notes = Object.entries(r.notes)
    .map(([d, n]) => `<li><b>${d}</b> ${escape(n.text)} ${n.tags.length ? `<i>(${escape(n.tags.join(', '))})</i>` : ''}</li>`)
    .join('');
  const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Resumen de salud</title>
<style>body{font:13px/1.5 system-ui,sans-serif;margin:32px;color:#111}h1{font-size:20px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:6px 4px;text-align:left}small{color:#666}</style></head>
<body><h1>Resumen de salud · últimos 30 días</h1><small>Generado el ${escape(r.generated)} por Sergio con los datos del propio paciente (no es un informe clínico).</small>
<table><thead><tr><th>Medida</th><th>Media</th><th>Mín – máx</th><th>Días</th><th>Orientación</th></tr></thead><tbody>${rows}</tbody></table>
${notes ? `<h2>Notas</h2><ul>${notes}</ul>` : ''}</body></html>`;
  const win = window.open('', '_blank');
  if (!win) return toast.error('El navegador bloqueó la ventana de impresión.');
  win.document.write(html);
  win.document.close();
  win.focus();
  win.print();
}

export function ShareTab() {
  const [busy, setBusy] = useState(false);
  return (
    <div className="salud-share">
      <section className="salud-block">
        <h2 className="paper-label">Para su médico</h2>
        <p>Una página con las medias de 30 días, el mínimo y el máximo, y sus notas. Se imprime o se guarda como PDF.</p>
        <button
          type="button"
          className="paper-button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            await printReport().catch(() => toast.error('No pude preparar el resumen.'));
            setBusy(false);
          }}
        >
          <Printer size={14} /> Resumen para imprimir
        </button>
      </section>
      <section className="salud-block">
        <h2 className="paper-label">Sus datos son suyos</h2>
        <p>Todo, en un CSV que abre cualquier hoja de cálculo o cualquier otra app de salud. Se guarda solo en este equipo.</p>
        <button type="button" className="paper-button" data-variant="quiet" onClick={() => void downloadCsv()}>
          <Download size={14} /> Descargar todo (CSV)
        </button>
      </section>
    </div>
  );
}
