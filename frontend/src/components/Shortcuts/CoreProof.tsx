// The fly core's proof, drawn: the wiring, a brain learning live, the
// specialists' curves against chance, the four Node brains and the hive.

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { coreProof, sleepNow, type CoreProof as Proof, type CurvePoint } from '../../lib/connectome';

const NODE_NAMES: Record<string, string> = { rihno: 'Rihno', manchas: 'Manchas', hous: 'Hous', tennessee: 'Tennessee' };
const pct = (v: number) => `${Math.round(v * 100)} %`;
const num = (v: number) => v.toLocaleString('es');

function Curve({ lines }: { lines: Array<{ label: string; points: CurvePoint[]; dim?: boolean }> }) {
  const W = 320;
  const H = 150;
  const pad = 24;
  const max = Math.max(1, ...lines.flatMap((l) => l.points.map((p) => p.epoch)));
  const x = (e: number) => pad + (e / max) * (W - pad * 2);
  const y = (v: number) => H - pad - v * (H - pad * 2);
  const chance = lines[0]?.points[0]?.chance_top3 ?? 0;
  return (
    <svg className="cp-curve" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Curva de aprendizaje">
      {[0, 0.5, 1].map((v) => (
        <g key={v}>
          <line x1={pad} x2={W - pad} y1={y(v)} y2={y(v)} className="cp-grid" />
          <text x={4} y={y(v) + 4} className="cp-tick">
            {Math.round(v * 100)}
          </text>
        </g>
      ))}
      <line x1={pad} x2={W - pad} y1={y(chance)} y2={y(chance)} className="cp-chance" />
      <text x={W - pad} y={y(chance) - 4} textAnchor="end" className="cp-tick">
        azar
      </text>
      {lines.map((l) => (
        <g key={l.label} className={l.dim ? 'cp-line cp-dim' : 'cp-line'}>
          <polyline points={l.points.map((p) => `${x(p.epoch)},${y(p.top3)}`).join(' ')} />
          {l.points.map((p) => (
            <circle key={p.epoch} cx={x(p.epoch)} cy={y(p.top3)} r={2.6} />
          ))}
        </g>
      ))}
    </svg>
  );
}

function Rounds({ proof }: { proof: Proof }) {
  const rounds = proof.live.rondas;
  return (
    <div className="cp-rounds">
      {rounds.map((r) => (
        <div key={r.ronda} className="cp-round">
          <div className="cp-bar">
            <span style={{ height: `${Math.max(2, r.acierto * 100)}%` }} />
          </div>
          <strong>{pct(r.acierto)}</strong>
          <span>{r.ronda === 0 ? 'nace' : `+${r.ronda}`}</span>
        </div>
      ))}
      <div className="cp-round cp-night">
        <div className="cp-bar">
          <span style={{ height: '100%' }} />
        </div>
        <strong>{num(Math.round(proof.live.dormir.memoria_lenta_despues))}</strong>
        <span>duerme</span>
      </div>
    </div>
  );
}

export function CoreProof() {
  const [proof, setProof] = useState<Proof | null>(null);
  const [busy, setBusy] = useState(false);

  const load = (fresh = false) =>
    coreProof(fresh)
      .then(setProof)
      .catch(() => setProof(null));
  useEffect(() => {
    void load();
  }, []);

  if (!proof) return null;
  const n = proof.wiring.neuronas;
  const last = proof.live.rondas[proof.live.rondas.length - 1];
  const kinds = Object.entries(proof.specialists);
  const keys = Object.keys(proof.nodes.instintos);

  return (
    <section className="salud-block cp">
      <h2 className="paper-label">El núcleo</h2>

      <div className="cp-wiring" data-real={proof.wiring.real}>
        <div>
          <strong>{num(n.proyeccion)}</strong>
          <span>sentidos</span>
        </div>
        <i aria-hidden />
        <div>
          <strong>{num(n.kenyon)}</strong>
          <span>Kenyon</span>
        </div>
        <i aria-hidden />
        <div>
          <strong>{num(n.salida)}</strong>
          <span>salida</span>
        </div>
        <i aria-hidden />
        <div>
          <strong>{num(n.dopamina)}</strong>
          <span>dopamina</span>
        </div>
        <em>{proof.wiring.real ? 'FlyWire real · verificado' : 'Sustituto'}</em>
      </div>

      <div className="cp-grid2">
        <figure className="cp-card">
          <figcaption>Aprende en vivo</figcaption>
          <Rounds proof={proof} />
          <p className="cp-foot">
            {num(last.cambiadas)} sinapsis cambian · {num(last.nuevas)} nacen
          </p>
        </figure>

        <figure className="cp-card">
          <figcaption>Especialistas</figcaption>
          <Curve lines={kinds.map(([k, s], i) => ({ label: k, points: s.curva, dim: i > 0 }))} />
          <p className="cp-foot cp-legend">
            {kinds.map(([k, s], i) => (
              <span key={k} data-dim={i > 0}>
                {k === 'cine' ? 'Cine' : 'Creadores'} {pct(s.curva[s.curva.length - 1].top3)}
              </span>
            ))}
          </p>
        </figure>
      </div>

      <figure className="cp-card">
        <figcaption>«{proof.nodes.pedido}»</figcaption>
        <ul className="cp-nodes">
          {keys.map((k) => (
            <li key={k}>
              <span className="paper-label">{NODE_NAMES[k] ?? k}</span>
              <strong>{proof.nodes.instintos[k][0]?.movida ?? '—'}</strong>
              <div className="cp-div">
                {keys.map((o) => (
                  <i
                    key={o}
                    title={o === k ? '' : `${NODE_NAMES[o] ?? o}: ${pct(proof.nodes.divergencia[k]?.[o] ?? 0)} distinto`}
                    style={{ opacity: o === k ? 0.08 : 0.15 + 0.85 * (proof.nodes.divergencia[k]?.[o] ?? 0) }}
                  />
                ))}
              </div>
            </li>
          ))}
        </ul>
      </figure>

      {proof.hive.organos.length > 0 && (
        <figure className="cp-card">
          <figcaption>Colmena</figcaption>
          <ul className="cp-hive">
            {proof.hive.organos.map((o) => (
              <li key={o.nombre}>
                <span>{o.nombre}</span>
                <strong>{num(o.veces)}</strong>
              </li>
            ))}
            <li>
              <span>supervisor</span>
              <strong>
                +{num(proof.hive.supervisor.recompensas)} / −{num(proof.hive.supervisor.castigos)}
              </strong>
            </li>
          </ul>
        </figure>
      )}

      <div className="cp-actions">
        <button
          type="button"
          className="paper-button"
          data-variant="quiet"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            const ok = await sleepNow().catch(() => false);
            setBusy(false);
            if (ok) toast.success('Durmió: lo aprendido pasó a la memoria lenta.');
            void load(true);
          }}
        >
          Dormir ahora
        </button>
        <button type="button" className="paper-button" data-variant="quiet" disabled={busy} onClick={() => void load(true)}>
          Medir de nuevo
        </button>
      </div>
    </section>
  );
}
