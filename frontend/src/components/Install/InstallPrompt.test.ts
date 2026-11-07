// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { isAppleMobile } from './InstallPrompt';

describe('install instructions', () => {
  it('recognizes an iPad reporting the desktop Safari user agent', () => {
    vi.stubGlobal('navigator', { userAgent: 'Macintosh Safari', maxTouchPoints: 5 });
    try {
      expect(isAppleMobile()).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('distinguishes iPhone and iPad from Android, macOS and Windows', () => {
    vi.stubGlobal('navigator', { maxTouchPoints: 0 });
    try {
      expect(isAppleMobile('iPhone Safari')).toBe(true);
      expect(isAppleMobile('iPad Safari')).toBe(true);
      for (const ua of ['Android Chrome', 'Macintosh Safari', 'Windows Chrome']) {
        expect(isAppleMobile(ua)).toBe(false);
      }
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
