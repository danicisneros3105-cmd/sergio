// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

const answers: Array<Record<string, string>> = [];
vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(async () => ({ ok: true, json: async () => answers.shift() ?? { estado: 'listo', url: '/x' } })),
}));

import { WebVideo } from './WebVideo';

afterEach(() => {
  cleanup();
  answers.length = 0;
});

const MINE = '/v1/creator/media/video-' + 'ab'.repeat(12) + '.mp4';

describe('WebVideo', () => {
  it('plays a file that is not Sergio\'s as it is, with no questions', () => {
    const { container } = render(<WebVideo src="https://example.com/a.mp4" />);
    expect(container.querySelector('video')?.getAttribute('src')).toBe('https://example.com/a.mp4');
  });

  it('plays the copy the server says is ready', async () => {
    answers.push({ estado: 'listo', url: '/v1/creator/reproducir/x.mp4' });
    const { container } = render(<WebVideo src={MINE} />);
    await waitFor(() => expect(container.querySelector('video')?.getAttribute('src')).toBe('/v1/creator/reproducir/x.mp4'));
  });

  it('says it is preparing a copy while the server makes it', async () => {
    answers.push({ estado: 'preparando' });
    render(<WebVideo src={MINE} />);
    expect(await screen.findByText(/Preparando el video/)).toBeTruthy();
  });

  it('says why when it cannot be played, and offers the file', async () => {
    answers.push({ estado: 'error', motivo: 'Sin ffmpeg.' });
    render(<WebVideo src={MINE} />);
    expect(await screen.findByText('Sin ffmpeg.')).toBeTruthy();
    expect(screen.getByText('Descargar el video').getAttribute('href')).toBe(MINE);
  });
});
