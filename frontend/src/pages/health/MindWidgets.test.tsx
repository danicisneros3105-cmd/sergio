// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const submitted: Array<[Record<string, number | string>, string]> = [];

vi.mock('../../lib/salud', () => {
  const opts = [
    { value: 0, label: 'Nunca' },
    { value: 1, label: 'Varios días' },
  ];
  return {
    clock: () => '15:30',
    salud: {
      widgets: async () => ({
        widgets: [{ key: 'w_nervios', label: 'Nervios', count: 2, scale: 'GAD-2', cite: '', last: null }],
        delay_minutes: 30,
      }),
      survey: async (variant: string) =>
        variant === 'w_nervios'
          ? {
              sections: [
                {
                  key: 'gad2',
                  title: 'Nervios',
                  items: [
                    { id: 'g1', kind: 'choice', text: '¿Nervioso?', options: opts },
                    { id: 'g2', kind: 'choice', text: '¿Sin poder parar de preocuparse?', options: opts },
                  ],
                },
              ],
            }
          : {
              sections: [
                {
                  key: 'inicio',
                  title: 'Para empezar',
                  items: [{ id: 'pic_pensar', kind: 'picture', image: 'pensar-demasiado', text: '¿Piensa demasiado?', options: opts }],
                },
              ],
            },
      submitSurvey: async (answers: Record<string, number | string>, variant: string) => {
        submitted.push([answers, variant]);
        return { id: 'r1', status: 'waiting', ready_at: 0, created: 0, variant };
      },
    },
  };
});

import { MindWidgets } from './MindWidgets';

afterEach(cleanup);

beforeEach(() => {
  submitted.length = 0;
  localStorage.clear();
});

describe('MindWidgets', () => {
  it('asks each question inside its card and sends itself after the last one', async () => {
    render(<MindWidgets onPick={() => {}} onOpen={() => {}} onSent={() => {}} />);
    expect(await screen.findByText('¿Nervioso?')).toBeTruthy();
    fireEvent.click(screen.getAllByRole('radio', { name: 'Varios días' })[0]);
    expect(await screen.findByText('¿Sin poder parar de preocuparse?')).toBeTruthy();
    fireEvent.click(screen.getAllByRole('radio', { name: 'Nunca' })[0]);
    await waitFor(() => expect(submitted).toEqual([[{ g1: 1, g2: 0 }, 'w_nervios']]));
    expect(await screen.findByText('Listo a las 15:30')).toBeTruthy();
  });

  it('keeps a picture answer for the full survey', async () => {
    render(<MindWidgets onPick={() => {}} onOpen={() => {}} onSent={() => {}} />);
    const picture = await screen.findByText('¿Piensa demasiado?');
    const card = picture.closest('article') as HTMLElement;
    fireEvent.click(card.querySelector('[role="radio"]') as HTMLElement);
    expect(JSON.parse(localStorage.getItem('sergio:salud-mental:borrador:corta') || '{}')).toEqual({ pic_pensar: 0 });
    expect(JSON.parse(localStorage.getItem('sergio:salud-mental:borrador:larga') || '{}')).toEqual({ pic_pensar: 0 });
  });
});
