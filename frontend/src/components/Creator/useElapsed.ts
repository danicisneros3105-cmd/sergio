import { useEffect, useState } from 'react';

/** Seconds since `busy` became truthy (0 when idle): long jobs show they are alive. */
export function useElapsed(busy: unknown): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    setSeconds(0);
    if (!busy) return;
    const start = Date.now();
    const t = window.setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => window.clearInterval(t);
  }, [busy]);
  return seconds;
}

export const SLOW_AI = 'Google va lento; Sergio ya pidió ayuda a otro modelo';

/** "· 12 s" after a few seconds, with a word on why it is slow. */
export function elapsedNote(seconds: number, slow: string = SLOW_AI): string {
  if (seconds < 4) return '';
  if (seconds < 25 || !slow) return ` · ${seconds} s`;
  return ` · ${seconds} s (${slow})`;
}
