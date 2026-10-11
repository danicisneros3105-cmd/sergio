import { useEffect, useState } from 'react';
import { apiFetch } from './api';
let cached: {at: number; request: Promise<boolean>} | undefined;
function checkDev(): Promise<boolean> {
  if (!cached || Date.now() - cached.at > 5000) {
    cached = {at: Date.now(), request: apiFetch('/v1/nodes/capabilities').then(async r => r.ok && !!(await r.json()).custom_api).catch(() => false)};
  }
  return cached.request;
}
export function useDevApi(): boolean {
  const [allowed, setAllowed] = useState(false);
  useEffect(() => { let live = true; checkDev().then(value => { if (live) setAllowed(value); }); return () => { live = false; }; }, []);
  return allowed;
}
