// @vitest-environment jsdom
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CRITTER_SHAPES, FRAMES, NodeCritter, blob, castOf, critterFrames, poseAt, rng, smooth } from './NodeCritter';

describe('the Nodes cast', () => {
  it('has four characters and maps any older shape to one of them, always the same', () => {
    expect(CRITTER_SHAPES).toEqual(['rhino', 'dalmatian', 'glove', 'orb']);
    for (const s of CRITTER_SHAPES) expect(castOf(s)).toBe(s);
    for (const old of ['bean', 'frog', 'star', 'planet', '', undefined]) {
      expect(CRITTER_SHAPES).toContain(castOf(old));
      expect(castOf(old)).toBe(castOf(old));
    }
  });

  it('inks every frame afresh, the way ink animation boils', () => {
    const a = blob(60, 60, 20, 20, rng(1));
    const b = blob(60, 60, 20, 20, rng(2));
    expect(a).not.toBe(b);
    expect(blob(60, 60, 20, 20, rng(1))).toBe(a); // but the same seed draws the same line
    expect(smooth([[0, 0], [10, 0], [10, 10]], true).endsWith('Z')).toBe(true);
    expect(critterFrames('rhino', false)).toHaveLength(FRAMES);
  });

  it('moves the mouth only while talking, and blinks once in the turn', () => {
    const quiet = Array.from({ length: FRAMES }, (_, i) => poseAt(i, false).mouth);
    const talking = Array.from({ length: FRAMES }, (_, i) => poseAt(i, true).mouth);
    expect(Math.max(...quiet)).toBe(0);
    expect(Math.max(...talking)).toBeGreaterThan(0.9);
    expect(Array.from({ length: FRAMES }, (_, i) => poseAt(i, false).blink).filter((b) => b === 1)).toHaveLength(1);
  });
});

describe('<NodeCritter>', () => {
  it('shows a medallion when small and the whole disc when large', () => {
    const small = render(<NodeCritter look={{ shape: 'glove' }} size={40} />);
    expect(small.container.querySelector('[data-disc]')).toBeNull();
    expect(small.container.querySelectorAll('.critter-frame')).toHaveLength(FRAMES);
    small.unmount();
    const big = render(<NodeCritter look={{ shape: 'glove' }} size={132} />);
    expect(big.container.querySelector('[data-disc]')).not.toBeNull();
    expect(big.container.querySelectorAll('.critter-frame')).toHaveLength(FRAMES);
    expect(big.container.querySelector('.critter-ring')).not.toBeNull();
  });

  it('keeps its state on the element and is hidden from readers without a label', () => {
    const { container, rerender } = render(<NodeCritter look={{ shape: 'orb' }} status="working" talking />);
    const el = container.querySelector('.critter')!;
    expect(el.getAttribute('data-status')).toBe('working');
    expect(el.hasAttribute('data-talking')).toBe(true);
    expect(el.getAttribute('aria-hidden')).toBe('true');
    rerender(<NodeCritter look={{ shape: 'orb' }} status="needs_you" label="Mía: necesita su ayuda" />);
    expect(container.querySelector('[role="img"]')?.getAttribute('aria-label')).toBe('Mía: necesita su ayuda');
    expect(container.querySelector('.critter-alert')).not.toBeNull();
  });
});
