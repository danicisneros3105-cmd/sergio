// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { NxSidebar, SETTINGS_ACTIONS } from './NxSidebar';

describe('Workspace sidebar like Notion', () => {
  afterEach(cleanup);

  it('keeps only Configuración, Plantillas and Papelera at the foot', () => {
    const onAction = vi.fn();
    const { container } = render(<NxSidebar onPick={() => {}} onAction={onAction} onCollapse={() => {}} />);
    const foot = container.querySelector('.nx-bottom') as HTMLElement;
    const labels = [...foot.querySelectorAll('.nx-row-label')].map((n) => n.textContent);
    expect(labels).toEqual(['Configuración', 'Plantillas', 'Papelera']);
  });

  it('opens Sergio’s tools from Configuración', () => {
    const onAction = vi.fn();
    render(<NxSidebar onPick={() => {}} onAction={onAction} onCollapse={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Configuración' }));
    const menu = screen.getByRole('menu');
    expect(within(menu).getAllByRole('menuitem')).toHaveLength(SETTINGS_ACTIONS.length);
    fireEvent.click(within(menu).getByRole('menuitem', { name: /Grafo/ }));
    expect(onAction).toHaveBeenCalledWith('graph');
    expect(screen.queryByRole('menu')).toBeNull();
  });
});
