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
  it('draws the same 12 inked frames at any size, with no disc or ring', () => {
    for (const size of [30, 40, 132]) {
      const { container, unmount } = render(<NodeCritter look={{ shape: 'glove' }} size={size} />);
      expect(container.querySelectorAll('.critter-frame')).toHaveLength(FRAMES);
      expect(container.querySelector('[data-disc]')).toBeNull();
      expect(container.querySelector('.critter-ring')).toBeNull();
      unmount();
    }
  });

  it('gives each member of the team its own colours on the ink', () => {
    const html = (shape: 'rhino' | 'dalmatian' | 'glove' | 'orb') => render(<NodeCritter look={{ shape }} />).container.innerHTML;
    const rihno = html('rhino');
    expect(rihno).toContain('#efe3c4'); // cream horn
    expect(rihno).toContain('#8ecdf5'); // celeste stripes
    expect(html('glove')).toContain('#3d82dc'); // Hous, the blue glove
    expect(html('orb')).toContain('#d9a24a'); // Tennessee's leopard glasses
  });

  it('keeps its state on the element and is hidden from readers without a label', () => {
    const { container, rerender } = render(<NodeCritter look={{ shape: 'orb' }} status="working" talking />);
    const el = container.querySelector('.critter')!;
    expect(el.getAttribute('data-status')).toBe('working');
    expect(el.hasAttribute('data-talking')).toBe(true);
    expect(el.getAttribute('aria-hidden')).toBe('true');
    rerender(<NodeCritter look={{ shape: 'orb' }} status="needs_you" label="Tennessee: necesita su ayuda" />);
    expect(container.querySelector('[role="img"]')?.getAttribute('aria-label')).toBe('Tennessee: necesita su ayuda');
    expect(container.querySelector('.critter-alert')).not.toBeNull();
  });
});
