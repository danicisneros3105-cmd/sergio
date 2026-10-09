import { describe, expect, it } from 'vitest';
import { AXIS_ES, STATUS_ES, isFinished, riskChips, type CoworkStep } from './CoworkPage';

const step = (scores: Record<string, number>): CoworkStep => ({
  index: 0,
  text: 'Compra el portátil',
  where: 'fondo',
  status: 'waiting_approval',
  result: '',
  actions: 0,
  verdict: { decision: 'ask', scores },
});

describe('riskChips', () => {
  it('lists only risky axes, highest first, in Spanish', () => {
    const chips = riskChips(step({ financial: 3, network: 1, privacy: 0 }));
    expect(chips.map((c) => c.label)).toEqual(['dinero', 'sale a internet']);
    expect(chips[0].score).toBe(3);
  });

  it('copes with a step that was never scored', () => {
    expect(riskChips({ ...step({}), verdict: {} })).toEqual([]);
  });
});

describe('labels', () => {
  it('has a Spanish label for each of the ten axes', () => {
    expect(Object.keys(AXIS_ES)).toHaveLength(10);
  });

  it('knows which runs are over', () => {
    expect(isFinished({ status: 'capped' })).toBe(true);
    expect(isFinished({ status: 'waiting_approval' })).toBe(false);
    expect(STATUS_ES.capped).toContain('tope');
  });
});
