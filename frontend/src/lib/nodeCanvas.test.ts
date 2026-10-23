import { describe, expect, it } from 'vitest';
import { latestWork, withoutWork } from './nodeCanvas';

describe('the Node work panel', () => {
  it('shows the newest video or picture the Node made', () => {
    const work = latestWork([
      {
        role: 'node',
        text: 'Primero ![logo](/v1/creator/media/imagen-aaa.png)',
      },
      { role: 'user', text: 'otra' },
      { role: 'node', text: 'Listo ![Metas](/v1/creator/media/video-bbb.mp4)' },
    ]);
    expect(work).toEqual({
      kind: 'video',
      url: '/v1/creator/media/video-bbb.mp4',
      title: 'Metas',
    });
  });

  it('falls back to a page link, and nothing from the owner', () => {
    expect(
      latestWork([
        { role: 'node', text: 'Mire [el informe](https://example.org/x)' },
      ]),
    ).toEqual({
      kind: 'page',
      url: 'https://example.org/x',
      title: 'el informe',
    });
    expect(
      latestWork([
        { role: 'user', text: '![x](/v1/creator/media/video-c.mp4)' },
      ]),
    ).toBeNull();
  });

  it('does not show the same media twice', () => {
    const work = latestWork([
      { role: 'node', text: 'Aquí ![v](/v1/creator/media/video-d.mp4)' },
    ]);
    expect(withoutWork('Aquí ![v](/v1/creator/media/video-d.mp4)', work)).toBe(
      'Aquí',
    );
  });
});
