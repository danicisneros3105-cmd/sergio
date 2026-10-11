import { useEffect, useState } from 'react';
import { isOffline } from '../lib/offline';

// Follows the browser's online/offline events (the status bar and the
// composer say what still works without a connection).
export function useOnline(): boolean {
  const [online, setOnline] = useState(() => !isOffline());
  useEffect(() => {
    const update = () => setOnline(!isOffline());
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);
  return online;
}
