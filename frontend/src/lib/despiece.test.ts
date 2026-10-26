import { describe, expect, it } from 'vitest';
import { despieceNames, explodedOffset, withoutDespieceLinks } from './despiece';

describe('models to take apart in the chat', () => {
  it('finds the links once and hides them from the text', () => {
    const text = 'Listo: /v1/creator/despiece/view/auto-deportivo. Y otra vez /v1/creator/despiece/view/auto-deportivo';
    expect(despieceNames(text, 'tool: /v1/creator/despiece/view/motor-v8')).toEqual(['auto-deportivo', 'motor-v8']);
    expect(withoutDespieceLinks('Aquí está (/v1/creator/despiece/view/motor-v8).\nGírelo.')).toBe('Aquí está\nGírelo.');
    expect(despieceNames('/v1/creator/despiece/view/../etc')).toEqual([]);
  });

  it('assembled at 0, apart along the group direction at 1', () => {
    expect(explodedOffset([1, 0, 0], [0, 0, 0], [0, 1, 0], 2, 0)).toEqual([0, 0, 0]);
    const [x, y, z] = explodedOffset([1, 0, 0], [0, 0, 0], [0, 1, 0], 2, 1);
    expect(y).toBeCloseTo(1.3); // the group goes up
    expect(x).toBeCloseTo(0.7); // and the piece away from the centre
    expect(z).toBeCloseTo(0);
  });
});
