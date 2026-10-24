// Sergio's mind in zones like the fly brain: each region and the zone doing its
// job, the connections learned so far, and the keyboard reflexes.

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { PaperPage } from '../components/Paper/PaperPage';
import { CoreProof } from '../components/Shortcuts/CoreProof';
import { BY_ID, SHORTCUTS, brainMap, forgetLearned, type BrainMap } from '../lib/connectome';
import '../components/Shortcuts/shortcuts.css';

export function ConnectomePage() {
  const [map, setMap] = useState<BrainMap | null>(null);
  const [problem, setProblem] = useState('');

  const load = () =>
    brainMap()
      .then((m) => {
        setMap(m);
        setProblem('');
      })
      .catch(() => setProblem('No pude leer el mapa. Compruebe que Sergio está en marcha.'));
  useEffect(() => {
    void load();
  }, []);

  const keyed = SHORTCUTS.filter((s) => s.keys);

  return (
    <PaperPage title="Cerebro" wide>
      {problem && <p className="paper-meta">{problem}</p>}
      {map && (
        <>
          <p className="cn-lead">
            La mente de Sergio está hecha por zonas, como el cerebro de la mosca de la fruta ({map.facts.neurons}, {map.facts.synapses}): memoria, prompts y habilidades, conversación, herramientas. {map.learning}
          </p>
          <ol className="cn-flow">
            {map.regions.map((r) => (
              <li key={r.key} className="cn-region" data-key={r.key}>
                <div className="cn-fly">
                  <span className="paper-label">{r.fly}</span>
                  <p>{r.job}</p>
                </div>
                <div className="cn-sergio">
                  <p>{r.sergio}</p>
                  <kbd>{r.where}</kbd>
                </div>
              </li>
            ))}
          </ol>

          <CoreProof />

          <section className="salud-block">
            <h2 className="paper-label">Conexiones aprendidas</h2>
            <p className="cn-learned">
              {map.mind?.engrams
                ? `${map.mind.engrams} recuerdos, ${map.mind.synapses ?? 0} conexiones y ${map.mind.associations ?? 0} enlaces entre recuerdos. Ruta rápida en el ${Math.round((map.mind.fast_path ?? 0) * 100)} % de las respuestas.`
                : 'Todavía nada: cada conversación deja un recuerdo y las conexiones crecen con el uso.'}
            </p>
            {map.mind?.zones?.some((z) => z.connections) && (
              <ul className="cn-zones">
                {map.mind.zones
                  .filter((z) => z.key !== 'integracion')
                  .map((z) => (
                    <li key={z.key}>
                      <span className="paper-label">{z.fly}</span>
                      <strong>{z.connections ?? 0}</strong>
                      <span>{z.top?.length ? z.top.map((t) => t.name).join(' · ') : z.job}</span>
                    </li>
                  ))}
              </ul>
            )}
          </section>

          {map.mind?.neurons && (
            <section className="salud-block">
              <h2 className="paper-label">Neuronas que deciden</h2>
              <p className="cn-learned">
                {`${map.mind.shortcuts ?? 0} atajos internos, ${map.mind.learned_neurons ?? 0} neuronas nuevas. Eligió las herramientas en el ${Math.round((map.mind.narrowed ?? 0) * 100)} % de los pedidos.`}
              </p>
              <ul className="cn-zones">
                {map.mind.neurons.map((n) => (
                  <li key={n.key}>
                    <span className="paper-label">
                      {n.label}
                      {n.shortcut ? ' · atajo' : ''}
                    </span>
                    <strong>{n.connections}</strong>
                    <span>{n.job}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="salud-block">
            <h2 className="paper-label">Reflejos de teclado</h2>
            <ul className="cn-keys">
              <li>
                <kbd>Ctrl</kbd> <kbd>K</kbd>
                <span>Abrir la paleta de atajos</span>
              </li>
              {keyed.map((s) => (
                <li key={s.id}>
                  {s.keys!.split(' ').map((k, i) => (
                    <kbd key={i}>{k.length === 1 ? k.toUpperCase() : k}</kbd>
                  ))}
                  <span>{s.title}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="salud-block">
            <h2 className="paper-label">Atajos aprendidos</h2>
            {map.memory.synapses ? (
              <>
                <p className="cn-learned">
                  {map.memory.synapses} conexiones entre {map.memory.active_cells} de {map.memory.kenyon_cells} células de Kenyon.
                  {map.memory.top?.length ? ` Lo que más usa: ${map.memory.top.map(([id]) => BY_ID[id]?.title ?? id).join(', ')}.` : ''}
                </p>
                <button
                  type="button"
                  className="paper-button"
                  data-variant="quiet"
                  onClick={async () => {
                    if (!window.confirm('¿Olvidar todos los atajos aprendidos?')) return;
                    await forgetLearned();
                    toast.success('Atajos aprendidos olvidados.');
                    void load();
                  }}
                >
                  Olvidar lo aprendido
                </button>
              </>
            ) : (
              <p className="cn-learned">Todavía nada. Use la paleta (Ctrl K) y Sergio irá aprendiendo qué busca con cada palabra.</p>
            )}
          </section>

          <section className="salud-block">
            <h2 className="paper-label">Fuentes</h2>
            <ul className="cn-sources">
              {map.facts.sources.map((s) => (
                <li key={s.url}>
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.cite}
                  </a>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </PaperPage>
  );
}

export default ConnectomePage;
