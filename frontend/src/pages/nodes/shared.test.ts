import { describe, expect, it } from 'vitest';
import type { Catalog } from '../../lib/nodes';
import { isActive, memberOf } from './shared';

describe('the Nodes page helpers', () => {
  it('offers «Cancelar acción» only while a Node is doing something', () => {
    expect(isActive({ busy: false, status: 'idle' })).toBe(false);
    expect(isActive({ busy: false, status: 'paused' })).toBe(false);
    expect(isActive({ busy: false, status: 'needs_you' })).toBe(false);
    expect(isActive({ busy: true, status: 'idle' })).toBe(true);
    expect(isActive({ busy: false, status: 'working' })).toBe(true);
    expect(isActive({ busy: false, status: 'waiting_approval' })).toBe(true);
  });

  it('finds the team member a Node is, and none for older Nodes', () => {
    const catalog = { team: [{ key: 'hous', name: 'Hous', role: 'Creativo' }] } as unknown as Catalog;
    expect(memberOf({ team: 'hous' }, catalog)?.name).toBe('Hous');
    expect(memberOf({ team: '' }, catalog)).toBeUndefined();
    expect(memberOf({ team: 'hous' }, null)).toBeUndefined();
  });
});
