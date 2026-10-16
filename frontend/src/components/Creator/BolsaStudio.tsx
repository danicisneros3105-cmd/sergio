// Creator → Bolsa: a stock, index or crypto forecast with Kronos (an open
// model for price candles). The last months of real prices, then the
// model's path for the next days, drawn on one chart. It is a model's guess,
// never financial advice, and the page says so.

import { useMemo, useState } from 'react';
import { Download, LineChart, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '../../lib/api';
import { installProgram, type Program } from '../../lib/creatorPrograms';
import { elapsedNote, useElapsed } from './useElapsed';

interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Forecast {
  symbol: string;
  model: string;
  history: Candle[];
  forecast: Candle[];
  last_close: number;
  end_close: number;
  change_pct: number;
  note: string;
}

const IDEAS = ['AAPL', 'MSFT', 'NVDA', 'TSLA', '^GSPC', 'BTC-USD'];
const W = 760;
const H = 300;
const PAD = 36;

/** Points of the chart: history then forecast on one price scale. */
export function chartPaths(history: Candle[], forecast: Candle[]) {
  const all = [...history, ...forecast];
  const lo = Math.min(...all.map((c) => c.low));
  const hi = Math.max(...all.map((c) => c.high));
  const span = hi - lo || 1;
  const x = (i: number) => PAD + (i / Math.max(1, all.length - 1)) * (W - PAD * 2);
  const y = (v: number) => H - PAD - ((v - lo) / span) * (H - PAD * 2);
  const line = (rows: Candle[], from: number) =>
    rows.map((c, i) => `${i ? 'L' : 'M'}${x(from + i).toFixed(1)} ${y(c.close).toFixed(1)}`).join(' ');
  const past = line(history, 0);
  const ahead = forecast.length ? `M${x(history.length - 1).toFixed(1)} ${y(history[history.length - 1].close).toFixed(1)} ` + line(forecast, history.length).replace(/^M/, 'L') : '';
  const band = forecast.length
    ? forecast.map((c, i) => `${i ? 'L' : 'M'}${x(history.length + i).toFixed(1)} ${y(c.high).toFixed(1)}`).join(' ') +
      ' ' +
      [...forecast].reverse().map((c, i) => `L${x(history.length + forecast.length - 1 - i).toFixed(1)} ${y(c.low).toFixed(1)}`).join(' ') +
      ' Z'
    : '';
  return { past, ahead, band, lo, hi, split: x(history.length - 1) };
}

export default function BolsaStudio({ programs, reload }: { programs: Program[] | null; reload: () => void }) {
  const kronos = programs?.find((p) => p.id === 'kronos');
  const [symbol, setSymbol] = useState('AAPL');
  const [horizon, setHorizon] = useState(20);
  const [busy, setBusy] = useState('');
  const elapsed = useElapsed(busy);
  const [result, setResult] = useState<Forecast | null>(null);
  const [error, setError] = useState('');
  const paths = useMemo(() => (result ? chartPaths(result.history, result.forecast) : null), [result]);

  const run = async (sym = symbol) => {
    setBusy('Leyendo las velas…');
    setError('');
    try {
      const res = await apiFetch('/v1/creator/bolsa/forecast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: sym, horizon }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || 'No se pudo predecir.');
      setResult(body as Forecast);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy('');
    }
  };

  if (kronos && !kronos.installed) {
    return (
      <div className="program-missing">
        <div className="program-missing-card">
          <b>Bolsa</b>
          <p className="studio-note">
            {kronos.installing
              ? `Instalando: ${kronos.step || 'empezando'}… (la primera vez tarda unos minutos)`
              : 'Sin instalar en este equipo (unos 800 MB): se instala con la próxima actualización.'}
          </p>
          {kronos.installing ? (
            <Loader2 className="program-spin" size={18} />
          ) : (
            <button
              type="button"
              className="paper-button"
              onClick={() =>
                installProgram('kronos')
                  .then(reload)
                  .catch((e) => toast.error(e instanceof Error ? e.message : String(e)))
              }
            >
              <Download size={15} /> Instalar
            </button>
          )}
          {kronos.error && <p className="studio-error">{kronos.error}</p>}
        </div>
      </div>
    );
  }

  const up = (result?.change_pct ?? 0) >= 0;
  return (
    <div className="bolsa">
      <form
        className="bolsa-form"
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <label>
          Símbolo
          <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="AAPL" aria-label="Símbolo" />
        </label>
        <label>
          Días
          <input type="number" min={1} max={60} value={horizon} onChange={(e) => setHorizon(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} aria-label="Días a predecir" />
        </label>
        <button type="submit" className="paper-button" disabled={!!busy || !symbol.trim()}>
          <LineChart size={15} /> Predecir
        </button>
        <div className="bolsa-ideas">
          {IDEAS.map((s) => (
            <button
              key={s}
              type="button"
              className="mac-chip"
              disabled={!!busy}
              onClick={() => {
                setSymbol(s);
                void run(s);
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </form>

      {busy && (
        <p className="studio-note">
          {busy}{elapsedNote(elapsed, "")}
        </p>
      )}
      {error && <p className="studio-error">{error}</p>}

      {result && paths && (
        <section className="bolsa-result">
          <header>
            <h2>{result.symbol}</h2>
            <p>
              Último cierre <b>{result.last_close.toFixed(2)}</b> → en {result.forecast.length} días{' '}
              <b>{result.end_close.toFixed(2)}</b>{' '}
              <span data-up={up}>
                ({up ? '+' : ''}
                {result.change_pct.toFixed(2)} %)
              </span>
            </p>
          </header>
          <svg viewBox={`0 0 ${W} ${H}`} className="bolsa-chart" role="img" aria-label={`Precio de ${result.symbol} y la predicción`}>
            <line x1={paths.split} x2={paths.split} y1={PAD / 2} y2={H - PAD} className="bolsa-split" />
            <path d={paths.band} className="bolsa-band" />
            <path d={paths.past} className="bolsa-past" />
            <path d={paths.ahead} className="bolsa-ahead" />
            <text x={PAD} y={PAD / 2 + 4} className="bolsa-axis">
              {paths.hi.toFixed(2)}
            </text>
            <text x={PAD} y={H - PAD / 3} className="bolsa-axis">
              {paths.lo.toFixed(2)}
            </text>
            <text x={paths.split + 6} y={PAD / 2 + 4} className="bolsa-axis">
              predicción
            </text>
          </svg>
          <p className="bolsa-note">
            {result.note}
          </p>
        </section>
      )}
      {!result && !busy && !error && (
        <p className="studio-note bolsa-empty">
          No es un consejo financiero.
        </p>
      )}
    </div>
  );
}
