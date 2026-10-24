// Light mode for a slow device: when the computer or phone is short of memory
// or cores, saves data, or the page keeps freezing (long tasks), Sergio drops
// the costly effects — blur behind glass, big shadows, long animations — so
// typing and scrolling stay smooth. Nothing is turned off but decoration.

const WINDOW_MS = 10_000;
const LONG_TASKS = 6; // freezes over 50 ms in ten seconds before going light

interface Device {
  deviceMemory?: number;
  hardwareConcurrency?: number;
  connection?: { saveData?: boolean };
}

/** True for a device that should start light. */
export function weakDevice(nav: Device = typeof navigator !== 'undefined' ? (navigator as Device) : {}): boolean {
  if (nav.connection?.saveData) return true;
  if (typeof nav.deviceMemory === 'number' && nav.deviceMemory <= 2) return true;
  if (typeof nav.hardwareConcurrency === 'number' && nav.hardwareConcurrency <= 2) return true;
  return false;
}

/** Counts freezes in a sliding window; true once there are too many. */
export function freezeMeter(limit = LONG_TASKS, windowMs = WINDOW_MS) {
  const at: number[] = [];
  return (now: number): boolean => {
    at.push(now);
    while (at.length && now - at[0] > windowMs) at.shift();
    return at.length >= limit;
  };
}

function goLight(): void {
  document.documentElement.dataset.ligero = '1';
}

export function startPerf(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  if (weakDevice()) {
    goLight();
    return;
  }
  if (typeof PerformanceObserver === 'undefined') return;
  try {
    const tooMany = freezeMeter();
    const watch = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (tooMany(entry.startTime + entry.duration)) {
          goLight();
          watch.disconnect();
          return;
        }
      }
    });
    watch.observe({ type: 'longtask', buffered: false });
  } catch {
    // a browser without long-task timing: stays as it is
  }
}
