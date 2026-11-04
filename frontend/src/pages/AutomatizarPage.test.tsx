// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const calls: Array<{ path: string; method: string; body?: unknown }> = [];

vi.mock('sonner', () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));
vi.mock('../lib/api', () => ({
  apiFetch: vi.fn(async (path: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, method: init?.method || 'GET', body });
    const json = (data: unknown) => new Response(JSON.stringify(data), { status: 200 });
    if (path === '/v1/automatiza/charla') {
      return json({
        texto: 'Entendido: 2 videos al día sobre «datos curiosos».',
        tarjetas: [
          { tipo: 'accion', titulo: 'Canal: datos curiosos', detalle: '2 al día', boton: { etiqueta: 'Crear canal', metodo: 'POST', ruta: '/canal', cuerpo: { idea: 'datos curiosos', por_dia: 2 } } },
        ],
      });
    }
    if (path === '/v1/automatiza') {
      return json({
        canales: { youtube: { conectado: true, canal: 'Mi canal', cliente_oauth: true, nota: '' }, instagram: { conectado: false, usuario: '', enlace_publico: false }, por_dia: 3, respuestas_pendientes: 1 },
        programados: [{ id: 'a' }],
        oportunidades: { perfil: { busco: 'ambos', habilidades: [], servicio: '', tarifa: '' }, total: 4 },
        trading: { activo: false, real: false, estrategia: 'cruce_medias', simbolos: [], dinero_real: false, broker: false, detenido: false, ultimas: [], aviso: '' },
        skills: {},
      });
    }
    return json({});
  }),
}));

import { AutomatizarPage } from './AutomatizarPage';

afterEach(() => {
  cleanup();
  calls.length = 0;
  localStorage.clear();
});

describe('AutomatizarPage', () => {
  it('opens with the composer, what runs and every platform, not only two', async () => {
    render(<AutomatizarPage />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/mientras usted no está/);
    await waitFor(() => expect(screen.getByText('Conectado')).toBeTruthy());
    expect(screen.queryByText('canales programados')).toBeNull();  // the counters were removed (owner, 4 Nov 2026)
    for (const name of ['YouTube', 'Instagram', 'TikTok', 'Facebook', 'LinkedIn', 'X']) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0);
    }
    expect(screen.getByText('Conectado')).toBeTruthy();
  });

  it('answers in the thread and acts only when the card button is pressed', async () => {
    render(<AutomatizarPage />);
    fireEvent.change(screen.getByLabelText('Qué quiere que pase sin usted'), { target: { value: '2 shorts al día de datos curiosos' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));
    await waitFor(() => expect(screen.getByText('Canal: datos curiosos')).toBeTruthy());
    expect(calls.some((c) => c.path === '/v1/automatiza/canal')).toBe(false);
    fireEvent.click(screen.getAllByRole('button', { name: 'Crear canal' }).find((b) => b.classList.contains('ax-btn'))!);
    await waitFor(() => expect(calls.some((c) => c.path === '/v1/automatiza/canal' && c.method === 'POST')).toBe(true));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Hecho' })).toBeTruthy());
  });
});
